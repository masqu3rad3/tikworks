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
    # the scene selection is ignored; the current tree/graph module is the parent
    designer.backend.selection = ParentRef(body.instance_id, "root")
    designer.tree.setCurrentItem(designer.item_for(chains[0].instance_id))
    designer.set_side("L")
    child = designer.create_guides("toy_chain")[0]
    assert child.inputs == {"root": "L_toy_chain.root"}
    assert all(call[0] != "reparent" for call in designer.backend.calls)  # joints are never parented
    # nothing selected -> no connection at all
    designer.tree.clearSelection()
    designer._set_current(None)
    loose = designer.create_guides("toy_chain")[0]
    assert loose.inputs == {}
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
    assert all(call[0] != "reparent" for call in designer.backend.calls)  # data only, no scene parenting
    designer.reparent(chain.instance_id, None)
    assert designer.guides.get(chain.instance_id).inputs == {}
    # scene selection does NOT drive the UI selection any more; structure events refresh
    designer.backend.selection = ParentRef(body.instance_id, "root")
    designer.backend.fire("SelectionChanged")
    designer.watcher.flush()
    assert designer.current.instance_id == chain.instance_id  # unchanged
    assert all(call[0] != "select" for call in designer.backend.calls)
    designer.backend.fire("DagObjectCreated")
    designer.watcher.flush()
    assert designer.status.text("modules") == "2 module(s)"


def test_pick_up_wire_delete_and_sever(designer):
    designer.set_side("C")
    body = designer.create_guides("toy_root")[0]
    designer.set_side("L")
    chain = designer.create_guides("toy_chain")[0]
    graph = designer.graph.graph
    assert designer.guides.get(chain.instance_id).inputs == {"root": "toy_root.root"}
    # pick the wire up from its input end and drop it on empty space -> disconnected
    wire = graph.wires[0]
    graph.pick_up_wire(wire, QtCore.QPointF(0, 0))
    assert graph._detached == "L_toy_chain.root" and graph.wires == []
    graph.finish_wire(None)
    assert designer.guides.get(chain.instance_id).inputs == {}
    # reconnect, select the wire, Delete in the graph disconnects (and does not delete modules)
    designer.guides.connect("L_toy_chain.root", "toy_root.root")
    designer.refresh()
    graph = designer.graph.graph
    graph.wires[0].setSelected(True)
    designer.graph.setFocus()
    assert designer.graph.delete_selected()
    assert designer.guides.get(chain.instance_id).inputs == {}
    assert len(designer.guides.instances()) == 2
    # sever everything touching a node (context menu / Edit > Sever Connections)
    designer.guides.connect("L_toy_chain.root", "toy_root.root")
    designer.refresh()
    designer.graph.sever("toy_root")
    assert designer.guides.get(chain.instance_id).inputs == {}


def test_manual_scene_node_and_side_combo(designer):
    designer.set_side("L")
    chain = designer.create_guides("toy_chain")[0]
    designer.graph.add_scene_node("hip_jnt")
    assert "hip_jnt" in designer.graph.graph.nodes and designer.graph.graph.nodes["hip_jnt"].external
    designer.refresh()  # survives a refresh even while unconnected
    assert "hip_jnt" in designer.graph.graph.nodes
    graph = designer.graph.graph
    graph.start_wire(graph.nodes["hip_jnt"].outputs["node"], QtCore.QPointF(0, 0))
    graph.finish_wire(graph.nodes["L_toy_chain"].inputs["space"])
    assert designer.guides.get(chain.instance_id).inputs == {"space": "hip_jnt"}
    designer.graph.remove_scene_node("hip_jnt")
    assert designer.guides.get(chain.instance_id).inputs == {} and "hip_jnt" not in designer.graph.graph.nodes
    # Scene Node from the shelf/palette: placeholder, rename via the properties name field
    designer.create_guides("__scene_node__")
    assert designer._external == "sceneNode1" and designer.name_edit.text() == "sceneNode1"
    graph = designer.graph.graph
    graph.start_wire(graph.nodes["sceneNode1"].outputs["node"], QtCore.QPointF(0, 0))
    graph.finish_wire(graph.nodes["L_toy_chain"].inputs["space"])
    assert designer.guides.get(chain.instance_id).inputs == {"space": "sceneNode1"}
    designer.graph.select_key("sceneNode1")
    designer._on_external_selection("sceneNode1")
    designer.name_edit.setText("pelvis_jnt")
    designer.name_edit.editingFinished.emit()
    assert designer.guides.get(chain.instance_id).inputs == {"space": "pelvis_jnt"}
    assert "pelvis_jnt" in designer.graph.graph.nodes and "sceneNode1" not in designer.graph.graph.nodes
    # right-click menu on an input field lists other modules -> outputs, and scene nodes
    designer.tree.setCurrentItem(designer.item_for(chain.instance_id))
    modules, scene_nodes = designer._input_rows["root"].sources()
    assert [m[0] for m in modules] == [] and scene_nodes == ["pelvis_jnt"]
    designer.set_side("C")
    designer.create_guides("toy_root")
    designer.tree.setCurrentItem(designer.item_for(chain.instance_id))
    modules, _ = designer._input_rows["root"].sources()
    assert modules == [("toy_root", "Toy Root", ["root"])] or modules[0][0] == "toy_root"
    menu = designer._input_rows["root"].build_menu()
    assert any(action.menu() is not None for action in menu.actions())
    designer.tree.clearSelection()
    designer._set_current(None)
    assert designer.side == "C"
    designer.set_side("Both")
    assert designer.side_combo.currentText() == "Both"
    assert [item.side.value for item in designer.create_guides("toy_chain")] == ["L", "R"]


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


def test_handles_share_one_scene_scan(designer):
    designer.set_side("C")
    designer.create_guides("toy_root")
    designer.set_side("Both")
    designer.create_guides("toy_chain")
    backend = designer.backend
    calls = {"n": 0}
    original = backend.find_instances

    def counting(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    backend.find_instances = counting
    designer.refresh()
    assert calls["n"] == 1  # tree + graph + status from a single scan
    calls["n"] = 0
    for handle in designer.guides.instances():
        _ = (handle.key, handle.inputs, handle.outputs, handle.settings, handle.instance)
    assert calls["n"] == 0
    designer.guides.connect("L_toy_chain.root", "toy_root.root")
    assert calls["n"] == 1  # a write invalidates once
    backend.find_instances = original


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
    designer.build_all_button.click()
    assert designer.build_all_button.text() == "Build all" and designer.test_button.text() == "Build selected"
