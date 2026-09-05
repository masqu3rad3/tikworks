"""The guide tree's draw-state dot.

    [dot] [icon] name

One marker per module, in the same three states the graph paints, fed from the
same diff object -- the two panes must never disagree about what is actually in
the scene. Follows the gutter-dot idiom ``tik.trigger.ui.delegates`` already
establishes for the pipeline tree. The state vocabulary and its palette live
in :mod:`tik.trigger.ui.draw_state`, shared with the graph.

The dot is where "is this module in Maya?" gets answered, which is what lets
the action bar drop its count pills: the bar says there is work pending in a
direction, the tree says which modules.
"""

from __future__ import annotations

from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.ui.draw_state import COLORS, DIMMED_TEXT, DRAWN, NOT_DRAWN

#: Item role carrying one of the ``draw_state`` constants.
DrawStateRole = QtCore.Qt.UserRole + 20


class GuideStateDelegate(QtWidgets.QStyledItemDelegate):
    """Paints a state dot in a left gutter, then the row as usual."""

    GUTTER = 14
    DOT = 7

    def paint(self, painter: QtGui.QPainter, option, index) -> None:
        state = index.data(DrawStateRole) or DRAWN
        shifted = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(shifted, index)
        shifted.rect = option.rect.adjusted(self.GUTTER, 0, 0, 0)
        if state == NOT_DRAWN:
            # absent from the scene: say it in the text too, so a glance
            # separates "not there" from "there and wrong"
            for role in (QtGui.QPalette.Text, QtGui.QPalette.HighlightedText):
                shifted.palette.setColor(role, QtGui.QColor(DIMMED_TEXT))
        super().paint(painter, shifted, index)

        painter.save()
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            centre = QtCore.QPointF(
                option.rect.left() + self.GUTTER / 2.0,
                option.rect.center().y() + 1,
            )
            color = QtGui.QColor(COLORS.get(state, COLORS[DRAWN]))
            if state == NOT_DRAWN:
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.setPen(QtGui.QPen(color, 1.0))
            else:
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(color)
            radius = self.DOT / 2.0
            painter.drawEllipse(centre, radius, radius)
        finally:
            painter.restore()
