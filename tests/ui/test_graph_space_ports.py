"""An anim-space row adds one port to the node, not two.

``input_names`` already contains the ports an anim-space row derives, so a
node that also walked ``spec.spaces`` built a second ``Port`` for each and
overwrote the dict entry. The first one stayed a child item of the node --
never in ``inputs``, so ``relayout`` never positioned or hid it -- and drew
at the node's local origin, a dead plug in its top-left corner.
"""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module
from tik.trigger.ui.graph.items import Port
from tik.trigger.ui.graph.view import GraphView


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


def _node(qapp, spaces, copies=None):
    scene = StubScene()
    handle = scene.add("toy_chain", name="arm", side="L")
    settings = dict(handle.settings)
    settings["anim_spaces"] = spaces
    if copies is not None:
        settings["copies"] = copies
    scene.write_settings(handle.instance_id, settings)
    view = GraphView(guides=scene)
    view.rebuild()
    view.show()
    return view, view.graph.nodes[handle.key]


def _port_children(node):
    return [item for item in node.childItems() if isinstance(item, Port)]


def test_a_space_row_makes_exactly_one_port(qapp):
    view, node = _node(qapp, [{"control": "fk0", "mode": "parent", "label": "world"}])
    try:
        assert len(_port_children(node)) == len(node.inputs) + len(node.outputs)
    finally:
        view.close()


def test_no_port_is_left_at_the_nodes_origin(qapp):
    """The visible symptom: a dead plug in the node's top-left corner."""
    view, node = _node(qapp, [{"control": "fk0", "mode": "parent", "label": "world"}])
    try:
        stranded = [
            port
            for port in _port_children(node)
            if port.isVisible() and port.pos().x() == 0 and port.pos().y() == 0
        ]
        assert stranded == []
    finally:
        view.close()


def test_the_space_port_is_the_one_in_inputs_and_is_coloured_as_a_space(qapp):
    """Wires resolve through ``inputs``; that port must be the space port."""
    view, node = _node(qapp, [{"control": "fk0", "mode": "parent", "label": "world"}])
    try:
        port = node.inputs["fk0_world"]
        assert port.space is True
        assert port in _port_children(node)
    finally:
        view.close()


def test_a_later_copys_space_port_is_coloured_too(qapp):
    """``space_inputs`` names are bare; the node's keys are qualified.

    Passing the bare names through meant only the first copy's space port was
    ever recognised as one.
    """
    view, node = _node(
        qapp,
        [{"control": "fk0", "mode": "parent", "label": "world"}],
        copies=[
            {"slug": "", "name": "arm", "segments": 2},
            {"slug": "c1", "name": "arm1", "segments": 2},
        ],
    )
    try:
        assert node.inputs["c1_fk0_world"].space is True
    finally:
        view.close()
