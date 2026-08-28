"""Guide Designer v3 + binding + graph, driven by the fake backend (no Maya)."""

import pytest

from tik.shared.ui.binding import BindingManager, bind
from tik.shared.ui.Qt import QtCore, QtWidgets
from tik.trigger.core import clear_registries, register_module
from tik.trigger.core.schemas import ParentRef
from tik.trigger.ui.graph_view import WireItem
from tik.trigger.ui.guide_designer import GuideDesigner
from trigger_fakes import FakeBackend, ToyChain, ToyRoot


class FakeAdapter:
    store: dict = {}
    observers: dict = {}

    def __init__(self, plug_path):
        self.plug_path = plug_path

    def exists(self):
        return self.plug_path in FakeAdapter.store

    def get(self):
        return FakeAdapter.store[self.plug_path]

    def set(self, value):
        FakeAdapter.store[self.plug_path] = value

    def observe(self, callback):
        FakeAdapter.observers[self.plug_path] = callback

    def unobserve(self):
        FakeAdapter.observers.pop(self.plug_path, None)

    @classmethod
    def poke(cls, plug_path, value):
        cls.store[plug_path] = value
        if plug_path in cls.observers:
            cls.observers[plug_path]()


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    FakeAdapter.store.clear()
    FakeAdapter.observers.clear()
    yield
    clear_registries()


def test_binders_both_directions(qapp):
    FakeAdapter.store["node.count"] = 3
    spin = QtWidgets.QSpinBox()
    manager = BindingManager()
    binder = manager.add(bind("node.count", spin, adapter=FakeAdapter("node.count")))
    assert binder.active and spin.value() == 3
    spin.setValue(7)
    assert FakeAdapter.store["node.count"] == 7
    FakeAdapter.poke("node.count", 9)
    assert spin.value() == 9
    manager.clear()
    assert "node.count" not in FakeAdapter.observers


@pytest.fixture
def designer(qapp):
    backend = FakeBackend()

    def adapter_factory(plug_path):
        FakeAdapter.store.setdefault(plug_path, 2 if plug_path.endswith("segments") else True)
        return FakeAdapter(plug_path)

    window = GuideDesigner(backend, binding_adapter=adapter_factory)
    window.show()
    yield window
    window.close()


def _keys(tree):
    found = []
    iterator = QtWidgets.QTreeWidgetItemIterator(tree)
    while iterator.value():
        item = iterator.value()
        found.append((item.text(0), item.parent().text(0) if item.parent() else None, item.text(3)))
        iterator += 1
    return found


def test_window_shell(designer):
    assert [action.text() for action in designer.menuBar().actions()] == ["&File", "&Edit", "&View", "&Build", "&Help"]
    assert designer.status.text("modules") == "0 module(s)"
    assert designer.tree_pane.isVisible() and designer.graph_pane.isVisible()
    designer.graph_action.setChecked(False)
    designer.set_pane_visible(designer.graph_pane, False)
    assert not designer.graph_pane.isVisible()


def test_create_prefills_primary_input_and_tree_graph_agree(designer):
    designer.set_side("C")
    body = designer.create_guides("toy_root")[0]
    designer.set_side("Both")
    chains = designer.create_guides("toy_chain")
    assert [item.side.value for item in chains] == ["L", "R"]
    assert all(item.inputs == {"root": "toy_root.root"} for item in chains)
    rows = _keys(designer.tree)
    assert ("L_toy_chain", "toy_root", "toy_root.root") in rows and ("R_toy_chain", "toy_root", "toy_root.root") in rows
    graph = designer.graph.graph
    assert set(graph.nodes) == {"toy_root", "L_toy_chain", "R_toy_chain"}
    assert len(graph.wires) == 2 and all(wire.primary for wire in graph.wires)
    assert designer.status.text("connections").startswith("2 connection(s)")
    # creating with a selected guide joint in the scene parents under THAT joint's role
    designer.backend.selection = ParentRef(chains[0].instance_id, "segment", 1)
    designer.set_side("L")
    child = designer.create_guides("toy_chain")[0]
    assert child.inputs == {"root": "L_toy_chain.root"}  # 'segment' is not an output -> first output
    designer.backend.selection = None


def test_inputs_panel_edits_connections(designer):
    designer.set_side("C")
    body = designer.create_guides("toy_root")[0]
    designer.backend.selection = None
    designer.tree.clearSelection()
    designer._set_current(None)
    designer.set_side("L")
    chain = designer.create_guides("toy_chain")[0]
    assert chain.inputs == {}
    row = designer._input_rows["root"]
    row.line.setText("toy_root.root")
    row.line.editingFinished.emit()
    assert designer.guides.get(chain.instance_id).inputs == {"root": "toy_root.root"}
    space = designer._input_rows["space"]
    space.line.setText("some_jnt")
    space.line.editingFinished.emit()
    assert designer.guides.get(chain.instance_id).inputs == {"root": "toy_root.root", "space": "some_jnt"}
    assert "missing scene node" in designer.status.text("connections")
    assert "some_jnt" in designer.graph.graph.nodes and designer.graph.graph.nodes["some_jnt"].external
    designer.backend.scene_nodes.add("some_jnt")
    designer.refresh()
    assert "missing" not in designer.status.text("connections")
    space = designer._input_rows["space"]
    space.clear.click()
    assert designer.guides.get(chain.instance_id).inputs == {"root": "toy_root.root"}
    row = designer._input_rows["root"]
    row.line.setText("toy_root.nope")
    row.line.editingFinished.emit()  # rejected, reverted
    assert designer.guides.get(chain.instance_id).inputs == {"root": "toy_root.root"}
    assert row.line.text() == "toy_root.root"


def test_graph_wiring_and_disconnect(designer):
    designer.set_side("C")
    body = designer.create_guides("toy_root")[0]
    designer.tree.clearSelection()
    designer._set_current(None)
    designer.backend.selection = None
    designer.set_side("L")
    chain = designer.create_guides("toy_chain")[0]
    graph = designer.graph.graph
    assert graph.wires == []
    graph.start_wire(graph.nodes["toy_root"].outputs["root"], QtCore.QPointF(0, 0))
    graph.finish_wire(graph.nodes["L_toy_chain"].inputs["root"])
    assert designer.guides.get(chain.instance_id).inputs == {"root": "toy_root.root"}
    graph = designer.graph.graph
    assert len(graph.wires) == 1
    wire = graph.wires[0]
    assert isinstance(wire, WireItem)
    graph.disconnect_requested.emit(wire.target_key)
    assert designer.guides.get(chain.instance_id).inputs == {}


def test_tree_drag_sets_primary_and_scene_sync(designer):
    designer.set_side("C")
    body = designer.create_guides("toy_root")[0]
    designer.tree.clearSelection()
    designer._set_current(None)
    designer.backend.selection = None
    designer.set_side("L")
    chain = designer.create_guides("toy_chain")[0]
    designer.reparent(chain.instance_id, body.instance_id)
    assert designer.guides.get(chain.instance_id).inputs == {"root": "toy_root.root"}
    assert ("reparent", chain.instance_id, body.instance_id) in designer.backend.calls
    designer.reparent(chain.instance_id, None)
    assert designer.guides.get(chain.instance_id).inputs == {}
    # scene selection -> tree/graph selection (debounced watcher)
    designer.backend.selection = ParentRef(body.instance_id, "root")
    designer.backend.fire("SelectionChanged")
    designer.watcher.flush()
    assert designer.current.instance_id == body.instance_id
    designer.backend.fire("DagObjectCreated")
    designer.watcher.flush()
    assert designer.status.text("modules") == "2 module(s)"


def test_properties_binding_rename_mirror_delete(designer):
    designer.set_side("L")
    chain = designer.create_guides("toy_chain")[0]
    designer.form.widget("segments").setValue(4)
    assert designer.backend.settings[chain.instance_id]["segments"] == 4
    FakeAdapter.poke(f"{chain.instance_id}.segments", 6)
    assert designer.form.widget("segments").value() == 6  # refreshed form, live-bound
    designer.name_edit.setText("tail")
    designer.name_edit.editingFinished.emit()
    assert designer.current.name == "tail" and designer.current.key == "L_tail"
    designer.mirror_current()
    assert sorted(handle.key for handle in designer.guides.instances()) == ["L_tail", "R_tail"]
    designer.tree.setCurrentItem(designer.item_for(chain.instance_id))
    designer.delete_current()
    assert [handle.key for handle in designer.guides.instances()] == ["R_tail"]


def test_export_import_and_test_build(designer, tmp_path, monkeypatch):
    designer.set_side("C")
    designer.create_guides("toy_root")
    calls = []
    monkeypatch.setattr(designer.guides, "export", lambda path, *handles: calls.append(("export", str(path), len(handles))) or tmp_path / "g.trg")
    monkeypatch.setattr(designer.guides, "import_", lambda path, reset=False: calls.append(("import", str(path), reset)) or [])
    designer.export_file(str(tmp_path / "g.trg"))
    assert calls[-1] == ("export", str(tmp_path / "g.trg"), 0)
    assert designer.status.text("file") == "g.trg"
    designer.import_file(str(tmp_path / "g.trg"), reset=True)
    assert calls[-1] == ("import", str(tmp_path / "g.trg"), True)
    report = designer.test_build(all_modules=True)
    assert report.count == 1 and ("rig_root", "test") in designer.backend.calls
