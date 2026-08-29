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
    scene = designer.graph.graph.nodes["scene"]  # ungrouped scene sources show under an implicit group
    assert scene.external and "some_jnt" in scene.outputs
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


def test_scene_node_groups_and_side_combo(designer):
    designer.set_side("L")
    chain = designer.create_guides("toy_chain")[0]
    # a group of scene nodes = one dashed node with one output per scene node
    designer.graph.add_scene_group("world", ["hip_jnt", "chest_jnt"])
    assert designer.graph.graph.nodes["world"].external
    assert list(designer.graph.graph.nodes["world"].outputs) == ["hip_jnt", "chest_jnt"]
    designer.refresh()  # persisted in the layout, survives a refresh while unconnected
    assert "world" in designer.graph.graph.nodes and designer.guides.scene_groups() == {"world": ["hip_jnt", "chest_jnt"]}
    graph = designer.graph.graph
    graph.start_wire(graph.nodes["world"].outputs["hip_jnt"], QtCore.QPointF(0, 0))
    graph.finish_wire(graph.nodes["L_toy_chain"].inputs["space"])
    assert designer.guides.get(chain.instance_id).inputs == {"space": "hip_jnt"}  # plain scene node name
    # Scene Nodes from the shelf/palette: group named in the properties, rows pre-filled from the selection
    designer.backend.selected_names = ["pelvis_jnt"]
    designer.create_guides("__scene_node__")
    assert designer._external == "sceneNodes1" and designer.name_edit.text() == "sceneNodes1"
    assert designer.scene_panel.isVisible() and designer.scene_panel.nodes() == ["pelvis_jnt"]
    designer.name_edit.setText("anchors")
    designer.name_edit.editingFinished.emit()
    assert designer._external == "anchors" and "anchors" in designer.graph.graph.nodes and "sceneNodes1" not in designer.guides.scene_groups()
    designer.backend.selected_names = []
    designer.scene_panel.add_button.click()
    designer.scene_panel.rows[-1].setText("neck_jnt")
    designer.scene_panel.rows[-1].editingFinished.emit()
    assert designer.guides.scene_groups()["anchors"] == ["pelvis_jnt", "neck_jnt"]
    # removing a scene node from the group drops connections that used it
    designer.guides.connect("L_toy_chain.root", "neck_jnt")
    designer.guides.set_scene_group("anchors", ["pelvis_jnt"])
    assert designer.guides.get(chain.instance_id).inputs == {"space": "hip_jnt"}
    designer.graph.remove_scene_group("world")
    assert designer.guides.get(chain.instance_id).inputs == {} and "world" not in designer.graph.graph.nodes
    # right-click menu on an input field lists other modules -> outputs, and scene nodes by group
    designer.tree.setCurrentItem(designer.item_for(chain.instance_id))
    modules, scene_nodes = designer._input_rows["root"].sources()
    assert [m[0] for m in modules] == [] and scene_nodes == [("anchors", "pelvis_jnt")]
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


def test_unique_names_layout_persistence_and_slice(designer, tmp_path):
    designer.set_side("L")
    first = designer.create_guides("toy_chain")[0]
    second = designer.create_guides("toy_chain")[0]  # connected to first, and uniquely named
    assert (first.key, second.key) == ("L_toy_chain", "L_toy_chain1")
    designer.tree.setCurrentItem(designer.item_for(second.instance_id))
    designer.name_edit.setText("toy_chain")
    designer.name_edit.editingFinished.emit()  # refused: reverts
    assert designer.guides.get(second.instance_id).key == "L_toy_chain1" and designer.name_edit.text() == "toy_chain1"
    # positions / collapse are layout data
    node = designer.graph.graph.nodes["L_toy_chain1"]
    node.setPos(300, 40)
    designer.graph.graph.nodes_moved.emit()
    assert designer.guides.layout["positions"]["L_toy_chain1"] == [300.0, 40.0]
    designer.graph.set_mode("L_toy_chain1", 1)
    assert designer.guides.layout["collapse"]["L_toy_chain1"] == 1
    designer.refresh()
    node = designer.graph.graph.nodes["L_toy_chain1"]
    assert node.pos() == QtCore.QPointF(300, 40) and node.mode == 1
    assert node.inputs["root"].isVisible() and not node.inputs["space"].isVisible()  # connected plugs only
    designer.graph.select_keys(["L_toy_chain1"])
    designer.graph.set_selected_mode(0)
    assert not node.inputs["root"].isVisible() and node.boundingRect().height() < 40
    # renaming keeps the layout entry
    designer.name_edit.setText("tail")
    designer.name_edit.editingFinished.emit()
    assert designer.guides.layout["positions"]["L_tail"] == [300.0, 40.0] and "L_toy_chain1" not in designer.guides.layout["positions"]
    designer.graph.add_scene_group("world", ["hip_jnt"])
    designer.guides.connect("L_toy_chain.space", "hip_jnt")
    designer.refresh()
    # Ctrl+drag slice: every wire crossing the line is disconnected
    graph = designer.graph.graph
    wire = graph.wires[0]
    middle = wire.path().pointAtPercent(0.5)
    cut = graph.slice_wires(QtCore.QLineF(middle.x(), middle.y() - 50, middle.x(), middle.y() + 50))
    assert cut and all(designer.guides.by_key(key.rsplit(".", 1)[0]).inputs.get(key.rsplit(".", 1)[1]) is None for key in cut)
    # auto layout writes positions (undoable via the backend) and grid/snap toggles
    designer.graph.auto_layout()
    assert set(designer.guides.layout["positions"]) >= {"L_toy_chain", "L_tail", "world"}
    designer.grid_action.trigger()
    designer.snap_action.trigger()
    assert not designer.graph.graph.show_grid and not designer.graph.graph.snap  # on by default, toggled off
    designer.grid_action.trigger()
    designer.snap_action.trigger()
    assert designer.graph.graph.show_grid and designer.graph.graph.snap
    designer.graph.graph.nodes["L_tail"].setPos(33, 47)
    assert designer.graph.graph.nodes["L_tail"].pos() == QtCore.QPointF(40, 40)
    designer.graph.graph.nodes_moved.emit()
    # export / import round-trips everything the designer authored (joint records are the backend's job)
    designer.backend.export_guide_records = lambda wanted=None: []
    designer.backend.import_guide_instances = lambda instances: []
    path = designer.export_file(str(tmp_path / "g.trg"))
    import json
    data = json.loads(path.read_text())
    assert data["designer"]["scene_nodes"] == {"world": ["hip_jnt"]}
    assert data["designer"]["positions"]["L_tail"] == [40.0, 40.0] and data["designer"]["collapse"]["L_tail"] == 0
    designer.clear_guides()
    assert designer.guides.layout == {}
    designer.import_file(str(path))
    assert designer.guides.scene_groups() == {"world": ["hip_jnt"]}
    assert designer.guides.layout["positions"]["L_tail"] == [40.0, 40.0]


def test_multi_selection_edits_same_type_together(designer):
    designer.set_side("Both")
    chains = designer.create_guides("toy_chain")
    designer.set_side("C")
    body = designer.create_guides("toy_root")[0]
    designer.tree.clearSelection()
    for chain in chains:
        designer.item_for(chain.instance_id).setSelected(True)
    assert designer.multi_label.isVisible() and "2 Toy Chain" in designer.multi_label.text()
    assert not designer.name_edit.isEnabled()
    designer.form.widget("segments").setValue(5)
    assert all(designer.backend.settings[chain.instance_id]["segments"] == 5 for chain in chains)
    designer.item_for(body.instance_id).setSelected(True)
    assert designer.current is None and "different types" in designer.multi_label.text()
    assert "segments" not in designer.form._widgets
    # the shared context menu works from the tree and the graph
    menu = designer.module_menu()
    labels = [action.text() for action in menu.actions() if not action.isSeparator()]
    assert labels[:4] == ["Select root", "Select all guides", "Mirror", "Build"]
    designer.select_root()
    assert designer.backend.calls[-1][0] == "select_nodes"


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


def test_grid_snap_default_and_free_placement(designer):
    assert designer.grid_action.isChecked() and designer.snap_action.isChecked()
    assert designer.graph.graph.show_grid and designer.graph.graph.snap
    designer.set_side("C")
    body = designer.create_guides("toy_root")[0]
    # park the body where the next auto-placed node would land
    designer.tree.clearSelection()
    designer._set_current(None)
    designer.set_side("L")
    chain = designer.create_guides("toy_chain")[0]
    auto = designer.graph.graph.nodes[chain.key].pos()
    designer.graph.graph.nodes[body.key].setPos(auto)
    designer.graph.graph.nodes_moved.emit()
    designer.tree.clearSelection()
    designer._set_current(None)
    designer.set_side("R")
    other = designer.create_guides("toy_chain")[0]
    nodes = designer.graph.graph.nodes
    rect = lambda key: nodes[key].sceneBoundingRect()  # noqa: E731
    assert not rect(other.key).intersects(rect(body.key)) and not rect(other.key).intersects(rect(chain.key))
    assert nodes[other.key].pos().x() % 20 == 0 and nodes[other.key].pos().y() % 20 == 0  # snapped


def test_tree_filter_and_ctrl_click_toggle(designer):
    designer.set_side("C")
    body = designer.create_guides("toy_root")[0]
    designer.set_side("Both")
    chains = designer.create_guides("toy_chain")
    designer.tree_filter.set_text("R_")
    assert designer.item_for(chains[1].instance_id).isHidden() is False
    assert designer.item_for(chains[0].instance_id).isHidden()
    assert not designer.item_for(body.instance_id).isHidden()  # parent of a match stays
    assert designer.status.text("modules").startswith("2 of 3")
    designer.tree_filter.commit()
    assert designer.tree_filter.keywords == ["r_"]  # keywords are lower-cased
    designer.tree_filter.set_text("L_")  # OR: widens
    assert not designer.item_for(chains[0].instance_id).isHidden()
    designer.tree_filter.clear()
    assert designer.status.text("modules") == "3 module(s)"
    designer.refresh()
    assert all(not designer.item_for(h.instance_id).isHidden() for h in chains)
    # Ctrl+click toggles selection without slicing; the graph selection is not echoed back by the tree
    view = designer.graph
    view.graph.select_keys([])
    view.toggle_node_at(view.mapFromScene(view.graph.nodes["L_toy_chain"].sceneBoundingRect().center()))
    view.toggle_node_at(view.mapFromScene(view.graph.nodes["R_toy_chain"].sceneBoundingRect().center()))
    assert {n.key for n in view.graph.selected_nodes()} == {"L_toy_chain", "R_toy_chain"}
    assert len(designer.selected_handles()) == 2 and designer.multi_label.isVisible()
    view.toggle_node_at(view.mapFromScene(view.graph.nodes["L_toy_chain"].sceneBoundingRect().center()))
    assert {n.key for n in view.graph.selected_nodes()} == {"R_toy_chain"}
    assert len(view.graph.wires) == 2  # nothing sliced
