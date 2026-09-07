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


def _pixels(item, width=200, height=120):
    """Render one node and give back every colour it painted, as names."""
    from tik.shared.ui.Qt import QtGui, QtWidgets

    image = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32)
    image.fill(QtGui.QColor("#242424"))
    painter = QtGui.QPainter(image)
    try:
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem(), None)
    finally:
        painter.end()
    return [image.pixelColor(x, y).name() for x in range(width) for y in range(height)]


def test_out_of_date_paints_the_warning_ink_not_the_accent(node):
    """The stripe says 'contradicts the session', never 'selected'."""
    from tik.shared.ui import theme
    from tik.trigger.ui.draw_state import STALE_INK

    painted = _pixels(node(STALE))
    assert STALE_INK.lower() in painted
    assert theme.ACCENT.lower() not in painted


def test_the_stale_stripe_is_the_full_width(node):
    """It was 3px and read as a hairline; the marker has to carry across a
    node whose header already covers the top of it."""
    from tik.shared.ui.Qt import QtGui, QtWidgets
    from tik.trigger.ui.draw_state import STALE_INK
    from tik.trigger.ui.graph.constants import HEADER, STATE_STRIPE

    item = node(STALE)
    image = QtGui.QImage(200, 120, QtGui.QImage.Format_ARGB32)
    image.fill(QtGui.QColor("#242424"))
    painter = QtGui.QPainter(image)
    try:
        item.paint(painter, QtWidgets.QStyleOptionGraphicsItem(), None)
    finally:
        painter.end()

    row = HEADER + 6  # below the header, where the stripe is visible
    stripe = [
        x
        for x in range(STATE_STRIPE + 4)
        if image.pixelColor(x, row).name() == STALE_INK.lower()
    ]
    assert stripe == list(range(STATE_STRIPE))


def test_only_the_out_of_date_node_wears_a_header_badge(node):
    """The badge is the part that survives the gold module tints, so it must
    appear for STALE and for nothing else."""
    from tik.shared.ui.Qt import QtGui, QtWidgets
    from tik.trigger.ui.draw_state import STALE_INK
    from tik.trigger.ui.graph.constants import HEADER

    def header_band(state):
        item = node(state)
        image = QtGui.QImage(200, 120, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor("#242424"))
        painter = QtGui.QPainter(image)
        try:
            item.paint(painter, QtWidgets.QStyleOptionGraphicsItem(), None)
        finally:
            painter.end()
        # Clear of the left edge on purpose: the header's rounded corner lets
        # the stripe peek out at x<6, and sampling that would let this pass on
        # the stripe rather than on the badge it is meant to be about.
        return [
            image.pixelColor(x, y).name()
            for x in range(8, 20)
            for y in range(3, HEADER - 3)
        ]

    assert STALE_INK.lower() in header_band(STALE)
    assert STALE_INK.lower() not in header_band(DRAWN)
    assert STALE_INK.lower() not in header_band(NOT_DRAWN)
