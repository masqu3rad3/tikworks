"""A reference draws as a frame in the graph, and collapses to one node."""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


@pytest.fixture
def scene():
    return StubScene()


# ----------------------------------------------------------- the storage
def test_frames_start_empty(scene):
    assert scene.frames == {}


def test_set_frame_stores_position_and_collapse(scene):
    scene.set_frame("r1", position=(10.0, 20.0), collapsed=True)
    assert scene.frames["r1"]["position"] == [10.0, 20.0]
    assert scene.frames["r1"]["collapsed"] is True


def test_set_frame_updates_one_thing_at_a_time(scene):
    scene.set_frame("r1", position=(10.0, 20.0), collapsed=True)
    scene.set_frame("r1", collapsed=False)
    assert scene.frames["r1"]["position"] == [10.0, 20.0]
    assert scene.frames["r1"]["collapsed"] is False


def test_frames_survive_a_layout_write(scene):
    """The bug this section exists to prevent: a node drag deleting a frame."""
    scene.add("toy_root", name="spine")
    scene.set_frame("r1", position=(10.0, 20.0), collapsed=True)
    scene.set_layout({"positions": {"spine": [100.0, 100.0]}})
    assert scene.frames["r1"]["collapsed"] is True


def test_frames_survive_a_document_round_trip():
    from tik.trigger.core.guide_document import GuideDocument

    document = GuideDocument(frames={"r1": {"position": [1.0, 2.0], "collapsed": True}})
    again = GuideDocument.from_dict(document.to_dict())
    assert again.frames["r1"] == {"position": [1.0, 2.0], "collapsed": True}


# ------------------------------------------------------------- the item
def _frame(qapp, collapsed=False, rect=None):
    from tik.shared.ui.Qt import QtCore
    from tik.trigger.ui.graph.items import FrameItem, FrameSpec
    from tik.trigger.ui.graph.scene import GraphScene

    graph = GraphScene()
    spec = FrameSpec(ref_id="r1", title="baseRig.tr", collapsed=collapsed)
    item = graph.add_frame(spec, rect or QtCore.QRectF(0, 0, 200, 120))
    assert isinstance(item, FrameItem)
    return graph, item


def test_a_frame_encloses_what_it_was_given(qapp):
    from tik.trigger.ui.graph.items import FramePadding

    _graph, item = _frame(qapp)
    bounds = item.boundingRect()
    assert bounds.width() >= 200 + FramePadding * 2
    assert bounds.height() >= 120 + FramePadding * 2


def test_a_frame_carries_the_reference_name(qapp):
    _graph, item = _frame(qapp)
    assert item.title == "baseRig.tr"
    assert item.ref_id == "r1"


def test_a_frame_sits_behind_the_nodes(qapp):
    from tik.trigger.ui.graph.items import NodeSpec

    graph, item = _frame(qapp)
    node = graph.add_node(
        NodeSpec(
            key="spine",
            title="spine",
            subtitle="Base",
            inputs=[],
            outputs=["root"],
            color="#888888",
        )
    )
    assert item.zValue() < node.zValue()


def test_an_expanded_frame_is_a_backdrop_not_a_handle(qapp):
    """Dragging the frame would fight the nodes sitting inside it."""
    from tik.shared.ui.Qt import QtWidgets

    _graph, item = _frame(qapp)
    assert not item.flags() & QtWidgets.QGraphicsItem.ItemIsMovable
    assert not item.flags() & QtWidgets.QGraphicsItem.ItemIsSelectable


def test_clicking_the_glyph_asks_to_toggle(qapp):
    from tik.shared.ui.Qt import QtCore, QtWidgets

    graph, item = _frame(qapp)
    asked = []
    graph.frame_toggle_requested.connect(asked.append)

    event = QtWidgets.QGraphicsSceneMouseEvent()
    event.setButton(QtCore.Qt.LeftButton)
    event.setPos(item.glyph_rect().center())
    item.mousePressEvent(event)
    assert asked == ["r1"]


def test_clicking_elsewhere_does_not_toggle(qapp):
    from tik.shared.ui.Qt import QtCore, QtWidgets

    graph, item = _frame(qapp)
    asked = []
    graph.frame_toggle_requested.connect(asked.append)

    event = QtWidgets.QGraphicsSceneMouseEvent()
    event.setButton(QtCore.Qt.LeftButton)
    event.setPos(item.boundingRect().bottomLeft() + QtCore.QPointF(4, -4))
    item.mousePressEvent(event)
    assert asked == []


def test_clearing_the_graph_drops_frames(qapp):
    graph, _item = _frame(qapp)
    assert graph.frames
    graph.clear_graph()
    assert graph.frames == {}


# ----------------------------------------------------- expanded / collapsed
@pytest.fixture
def wired(qapp):
    """Two referenced modules and a local one wired to the second."""
    from tik.trigger.ui.graph import GraphView

    scene = StubScene()
    body = scene.add("toy_root", name="body")
    arm = scene.add("toy_chain", name="arm", side="L")
    scene.connect(f"{arm.key}.root", f"{body.key}.root")
    wing = scene.add("toy_chain", name="wing", side="R")
    scene.connect(f"{wing.key}.root", f"{arm.key}.end")
    for handle in (body, arm):
        scene.borrow(handle.instance_id, ref_id="r1", file="baseRig.tr")
    view = GraphView(scene)
    view.rebuild()
    return view, scene, body, arm, wing


def _keys(view):
    return set(view.graph.nodes)


def test_expanded_draws_every_member_and_a_frame(wired):
    view, _scene, _body, _arm, _wing = wired
    assert {"body", "L_arm", "R_wing"} <= _keys(view)
    assert set(view.graph.frames) == {"r1"}


def test_the_frame_encloses_its_members(wired):
    view, _scene, _body, _arm, _wing = wired
    frame = view.graph.frames["r1"]
    bounds = frame.sceneBoundingRect()
    for key in ("body", "L_arm"):
        assert bounds.contains(view.graph.nodes[key].sceneBoundingRect())


def test_collapsed_replaces_the_members_with_one_node(wired):
    view, scene, _body, _arm, _wing = wired
    scene.set_frame("r1", collapsed=True)
    view.rebuild()
    keys = _keys(view)
    assert "body" not in keys and "L_arm" not in keys
    assert "@r1" in keys
    assert "R_wing" in keys


def test_a_crossing_wire_lands_on_the_collapsed_node(wired):
    view, scene, _body, _arm, _wing = wired
    scene.set_frame("r1", collapsed=True)
    view.rebuild()
    node = view.graph.nodes["@r1"]
    assert "L_arm:end" in node.outputs
    assert any(
        wire.source.node.key == "@r1" and wire.target.node.key == "R_wing"
        for wire in view.graph.wires
    )


def test_an_internal_connection_is_not_a_port(wired):
    """Collapsing exists to hide what is internal; only crossings survive."""
    view, scene, _body, _arm, _wing = wired
    scene.set_frame("r1", collapsed=True)
    view.rebuild()
    node = view.graph.nodes["@r1"]
    assert "body:root" not in node.outputs
    assert not node.inputs


def test_expanding_again_restores_the_members_and_the_wire(wired):
    view, scene, _body, _arm, _wing = wired
    scene.set_frame("r1", collapsed=True)
    view.rebuild()
    scene.set_frame("r1", collapsed=False)
    view.rebuild()
    assert {"body", "L_arm", "R_wing"} <= _keys(view)
    assert any(
        wire.source.node.key == "L_arm" and wire.target.node.key == "R_wing"
        for wire in view.graph.wires
    )


def test_a_reference_with_no_crossings_still_collapses(qapp):
    from tik.trigger.ui.graph import GraphView

    scene = StubScene()
    body = scene.add("toy_root", name="body")
    scene.borrow(body.instance_id, ref_id="r1", file="baseRig.tr")
    scene.set_frame("r1", collapsed=True)
    view = GraphView(scene)
    view.rebuild()
    assert "@r1" in view.graph.nodes
    node = view.graph.nodes["@r1"]
    assert not node.inputs and not node.outputs


def test_toggling_a_frame_flips_its_stored_state(wired):
    view, scene, _body, _arm, _wing = wired
    view.toggle_frame("r1")
    assert scene.frames["r1"]["collapsed"] is True
    assert "@r1" in view.graph.nodes
    view.toggle_frame("r1")
    assert scene.frames["r1"]["collapsed"] is False
    assert "@r1" not in view.graph.nodes


def test_a_collapsed_frames_position_is_not_stored_as_a_module(wired):
    """It is not a module, so a layout write must not carry it."""
    view, scene, _body, _arm, _wing = wired
    view.toggle_frame("r1")
    view.graph.nodes["@r1"].setPos(140.0, 260.0)
    view.save_positions()
    assert scene.frames["r1"]["position"] == [140.0, 260.0]
    assert "@r1" not in scene.layout.get("positions", {})


# ------------------------------------------- a collapsed frame is not a group
def test_a_collapsed_frame_is_not_a_scene_group(wired):
    """`external` means scene-nodes group; a reference must not borrow it."""
    view, scene, _body, _arm, _wing = wired
    scene.set_frame("r1", collapsed=True)
    view.rebuild()
    node = view.graph.nodes["@r1"]
    assert node.reference is True
    assert node.external is False


def test_selecting_a_collapsed_frame_is_not_a_group_selection(wired):
    """Otherwise the properties panel offers Scene Nodes > Add."""
    view, scene, _body, _arm, _wing = wired
    scene.set_frame("r1", collapsed=True)
    view.rebuild()
    externals, frames = [], []
    view.graph.external_selected.connect(externals.append)
    view.graph.frame_selected.connect(frames.append)
    view.graph.nodes["@r1"].setSelected(True)
    assert externals == []
    assert frames == ["r1"]


def test_the_glyph_on_a_collapsed_frame_expands_it(wired):
    """The only way back: there is no backdrop to click while collapsed."""
    from tik.shared.ui.Qt import QtCore, QtWidgets

    view, scene, _body, _arm, _wing = wired
    scene.set_frame("r1", collapsed=True)
    view.rebuild()
    node = view.graph.nodes["@r1"]

    event = QtWidgets.QGraphicsSceneMouseEvent()
    event.setButton(QtCore.Qt.LeftButton)
    event.setPos(node.glyph_rect().center())
    node.mousePressEvent(event)

    assert scene.frames["r1"]["collapsed"] is False
    assert "@r1" not in view.graph.nodes
    assert {"body", "L_arm"} <= set(view.graph.nodes)


def test_the_glyph_does_not_change_the_display_mode(wired):
    """A reference node has one toggle, and it is not the 1/2/3 collapse mode."""
    from tik.shared.ui.Qt import QtCore, QtWidgets

    view, scene, _body, _arm, _wing = wired
    scene.set_frame("r1", collapsed=True)
    view.rebuild()
    node = view.graph.nodes["@r1"]
    modes = []
    view.graph.mode_change_requested.connect(lambda key, mode: modes.append(key))

    event = QtWidgets.QGraphicsSceneMouseEvent()
    event.setButton(QtCore.Qt.LeftButton)
    event.setPos(node.glyph_rect().center())
    node.mousePressEvent(event)
    assert modes == []
