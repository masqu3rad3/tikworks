"""The guide tree's draw-state dot: not drawn, drawn, out of date."""

import pytest

from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.ui.designer.delegates import DrawStateRole, GuideStateDelegate
from tik.trigger.ui.draw_state import DRAWN, NOT_DRAWN, STALE

ACCENT = "#fe7e00"


@pytest.fixture
def painted(qapp):
    """Render one row in a given state; give back the gutter's pixels."""

    def _paint(state):
        tree = QtWidgets.QTreeWidget()
        tree.setColumnCount(1)
        item = QtWidgets.QTreeWidgetItem(["L_arm"])
        item.setData(0, DrawStateRole, state)
        tree.addTopLevelItem(item)
        delegate = GuideStateDelegate()

        image = QtGui.QImage(200, 20, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor("#151515"))
        painter = QtGui.QPainter(image)
        option = QtWidgets.QStyleOptionViewItem()
        option.rect = QtCore.QRect(0, 0, 200, 20)
        try:
            delegate.paint(painter, option, tree.model().index(0, 0))
        finally:
            painter.end()
        gutter = [
            image.pixelColor(x, y).name()
            for x in range(GuideStateDelegate.GUTTER)
            for y in range(20)
        ]
        tree.deleteLater()
        return gutter

    return _paint


def test_out_of_date_paints_the_accent(painted):
    assert ACCENT in painted(STALE)


def test_drawn_and_not_drawn_never_paint_the_accent(painted):
    """Orange is reserved for 'the scene contradicts the session'."""
    assert ACCENT not in painted(DRAWN)
    assert ACCENT not in painted(NOT_DRAWN)


def test_the_three_states_paint_differently(painted):
    """A rigger has to tell them apart at a glance, so they cannot share ink."""
    inks = [frozenset(painted(state)) for state in (NOT_DRAWN, DRAWN, STALE)]
    assert len(set(inks)) == 3


def test_a_row_with_no_state_still_paints(painted):
    """Missing data must render as an ordinary drawn row, never crash."""
    assert painted(None)
