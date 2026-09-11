"""Each node filters its own ports.

Separate from the graph-wide search: that one finds a node in a big rig,
this one finds a port on a crowded node, and each node remembers its own.
"""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module
from tik.trigger.ui.graph.constants import PORT_FILTER_MIN
from tik.trigger.ui.graph.view import GraphView


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


@pytest.fixture
def crowded(qapp):
    """A module with enough copies to earn a filter row."""
    scene = StubScene()
    handle = scene.add("toy_chain", name="arm", side="L")
    handle.copies = [
        {"slug": "", "name": "arm", "segments": 2},
        {"slug": "c1", "name": "arm1", "segments": 2},
        {"slug": "c2", "name": "arm2", "segments": 2},
    ]
    view = GraphView(guides=scene)
    view.rebuild()
    view.show()
    yield view, scene, handle
    view.close()


def _shown(node):
    ins, outs = node.visible_ports()
    return sorted([port.name for port in ins] + [port.name for port in outs])


def test_a_crowded_node_gets_a_filter_row(crowded):
    view, _scene, handle = crowded
    node = view.graph.nodes[handle.key]
    assert len(node.inputs) + len(node.outputs) >= PORT_FILTER_MIN
    assert node.port_filter_widget is not None


def test_a_small_node_does_not(qapp):
    scene = StubScene()
    handle = scene.add("toy_root", name="spine")
    view = GraphView(guides=scene)
    view.rebuild()
    node = view.graph.nodes[handle.key]
    assert len(node.inputs) + len(node.outputs) < PORT_FILTER_MIN
    assert node.port_filter_widget is None


def test_typing_narrows_that_nodes_ports(crowded):
    view, _scene, handle = crowded
    node = view.graph.nodes[handle.key]
    before = _shown(node)
    node.set_port_filter("arm1")
    after = _shown(node)
    assert after
    assert len(after) < len(before)
    assert all(name.startswith("c1_") for name in after)


def test_the_slug_is_not_searchable(crowded):
    """It is never shown, so searching it would be searching for something
    that is not on screen."""
    view, _scene, handle = crowded
    node = view.graph.nodes[handle.key]
    node.set_port_filter("c1")
    assert _shown(node) == []


def test_the_filter_matches_the_label_not_the_stored_key(crowded):
    """A port shows `root` and stores `c1_root`; typing what you see works."""
    view, _scene, handle = crowded
    node = view.graph.nodes[handle.key]
    node.set_port_filter("end")
    assert _shown(node)
    assert all(node.outputs[name].label == "end" for name in _shown(node))


def test_the_copy_name_matches_too(crowded):
    """The heading is part of what you are reading, so it is searchable."""
    view, _scene, handle = crowded
    node = view.graph.nodes[handle.key]
    node.set_port_filter("arm2")
    assert all(name.startswith("c2_") for name in _shown(node))


def test_an_empty_group_draws_no_heading(crowded):
    view, _scene, handle = crowded
    node = view.graph.nodes[handle.key]
    node.set_port_filter("arm1")
    headings = [label for kind, label, _i, _o in node.row_plan() if kind == "group"]
    assert headings == ["arm1"]


def test_clearing_restores_every_port(crowded):
    view, _scene, handle = crowded
    node = view.graph.nodes[handle.key]
    before = _shown(node)
    node.set_port_filter("arm1")
    node.set_port_filter("")
    assert _shown(node) == before


def test_one_nodes_filter_leaves_another_alone(crowded):
    view, scene, handle = crowded
    other = scene.add("toy_chain", name="leg", side="L")
    other.copies = [
        {"slug": "", "name": "leg", "segments": 2},
        {"slug": "c1", "name": "leg1", "segments": 2},
        {"slug": "c2", "name": "leg2", "segments": 2},
    ]
    view.rebuild()
    view.graph.nodes[handle.key].set_port_filter("arm1")
    narrowed = _shown(view.graph.nodes[handle.key])
    assert narrowed, "the filter must leave something, or this proves nothing"
    assert len(_shown(view.graph.nodes[other.key])) > len(narrowed)


def test_a_filter_survives_a_rebuild(crowded):
    view, _scene, handle = crowded
    view.graph.nodes[handle.key].set_port_filter("arm1")
    view.rebuild()
    node = view.graph.nodes[handle.key]
    assert node.port_filter == "arm1"
    shown = _shown(node)
    assert shown, "the filter must leave something, or this proves nothing"
    assert all(name.startswith("c1_") for name in shown)


def test_a_filtered_port_keeps_a_place_for_its_wire(crowded):
    """Hidden, not removed: a wire into it still has somewhere to land."""
    view, _scene, handle = crowded
    node = view.graph.nodes[handle.key]
    node.set_port_filter("arm1")
    hidden = node.inputs["root"]
    assert not hidden.isVisible()
    assert hidden.scenePos() is not None
