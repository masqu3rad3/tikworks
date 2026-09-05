"""The graph node's draw-state stripe: the tree's dot, on a node.

The two panes are fed from one diff, so they can never disagree about what is
actually in the scene.
"""

import pytest

from tik.trigger.ui.draw_state import DRAWN, NOT_DRAWN, STALE
from tik.trigger.ui.graph.items import NodeItem, NodeSpec


def spec(state=None):
    kwargs = {} if state is None else {"draw_state": state}
    return NodeSpec(
        key="L_arm",
        title="L_arm",
        subtitle="Arm",
        inputs=["root"],
        outputs=["hand"],
        color="#5b8fd0",
        primary_input="root",
        **kwargs,
    )


@pytest.fixture
def node(qapp):
    def _make(state=None):
        return NodeItem(spec(state))

    return _make


def test_a_node_defaults_to_drawn():
    assert spec().draw_state == DRAWN


def test_not_drawn_recedes(node):
    """Nothing in Maya to look at, so the node says so before you read it."""
    assert node(NOT_DRAWN).opacity() < 1.0


def test_drawn_and_stale_are_fully_opaque(node):
    assert node(DRAWN).opacity() == 1.0
    assert node(STALE).opacity() == 1.0


def test_the_node_carries_its_state(node):
    assert node(STALE).draw_state == STALE


def test_every_state_paints_without_error(node, qapp):
    """The stripe is clipped to a rounded rect; a bad path would raise here."""
    from tik.shared.ui.Qt import QtGui, QtWidgets

    for state in (NOT_DRAWN, DRAWN, STALE):
        item = node(state)
        image = QtGui.QImage(200, 120, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor("#242424"))
        painter = QtGui.QPainter(image)
        try:
            item.paint(painter, QtWidgets.QStyleOptionGraphicsItem(), None)
        finally:
            painter.end()
