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
#: File name of the reference a module came through, or None when it is ours.
OriginRole = QtCore.Qt.UserRole + 21
#: How many things this module differs from its source by. 0 when it is local.
OverrideRole = QtCore.Qt.UserRole + 22
#: True for a referenced module deliberately left out of this rig.
DisabledRole = QtCore.Qt.UserRole + 23

#: Provenance is information, not a warning, so the chip is muted -- the
#: accent belongs to the one state that says the scene contradicts the
#: session. An override *does* earn visible ink: it is the thing that quietly
#: stops an upstream fix from arriving.
ORIGIN_INK = "#6f8fa8"
OVERRIDE_INK = "#c9a227"


class GuideStateDelegate(QtWidgets.QStyledItemDelegate):
    """Paints a state dot in a left gutter, then the row as usual."""

    GUTTER = 14
    DOT = 7

    CHIP_HEIGHT = 12
    CHIP_PAD = 5
    DIAMOND = 7

    def paint(self, painter: QtGui.QPainter, option, index) -> None:
        state = index.data(DrawStateRole) or DRAWN
        origin = index.data(OriginRole)
        overrides = int(index.data(OverrideRole) or 0)
        disabled = bool(index.data(DisabledRole))
        shifted = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(shifted, index)
        shifted.rect = option.rect.adjusted(self.GUTTER, 0, 0, 0)
        marks = self._marks_width(shifted, origin, overrides)
        if marks:
            # keep the name from running under the chip
            shifted.rect = shifted.rect.adjusted(0, 0, -marks, 0)
        if disabled:
            font = QtGui.QFont(shifted.font)
            font.setStrikeOut(True)
            shifted.font = font
            for role in (QtGui.QPalette.Text, QtGui.QPalette.HighlightedText):
                shifted.palette.setColor(role, QtGui.QColor(DIMMED_TEXT))
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
        self._paint_marks(painter, option, origin, overrides)

    # ------------------------------------------------------------- marks
    def _chip_text(self, origin) -> str:
        """The reference's name, without its extension."""
        return str(origin).rsplit(".", 1)[0] if origin else ""

    def _marks_width(self, option, origin, overrides: int) -> int:
        """How much room the right-hand marks need, in pixels."""
        width = 0
        metrics = QtGui.QFontMetrics(option.font)
        if origin:
            width += metrics.horizontalAdvance(self._chip_text(origin))
            width += self.CHIP_PAD * 2 + 4
        if overrides:
            width += self.DIAMOND + 4 + metrics.horizontalAdvance(str(overrides)) + 4
        return width

    def _paint_marks(self, painter, option, origin, overrides: int) -> None:
        """The origin chip and the override diamond, right-aligned."""
        if not origin and not overrides:
            return
        painter.save()
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            metrics = QtGui.QFontMetrics(option.font)
            right = option.rect.right() - 4
            middle = option.rect.center().y() + 1
            if origin:
                text = self._chip_text(origin)
                width = metrics.horizontalAdvance(text) + self.CHIP_PAD * 2
                chip = QtCore.QRectF(
                    right - width,
                    middle - self.CHIP_HEIGHT / 2.0,
                    width,
                    self.CHIP_HEIGHT,
                )
                ink = QtGui.QColor(ORIGIN_INK)
                fill = QtGui.QColor(ink)
                fill.setAlpha(48)
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(fill)
                painter.drawRoundedRect(chip, 3, 3)
                painter.setPen(ink)
                painter.drawText(chip, QtCore.Qt.AlignCenter, text)
                right -= width + 4
            if overrides:
                count = str(overrides)
                text_width = metrics.horizontalAdvance(count)
                painter.setPen(QtGui.QColor(OVERRIDE_INK))
                painter.drawText(
                    QtCore.QRectF(right - text_width, middle - 8, text_width, 16),
                    QtCore.Qt.AlignCenter,
                    count,
                )
                right -= text_width + 4
                centre = QtCore.QPointF(right - self.DIAMOND / 2.0, middle)
                size = self.DIAMOND / 2.0
                diamond = QtGui.QPolygonF(
                    [
                        QtCore.QPointF(centre.x(), centre.y() - size),
                        QtCore.QPointF(centre.x() + size, centre.y()),
                        QtCore.QPointF(centre.x(), centre.y() + size),
                        QtCore.QPointF(centre.x() - size, centre.y()),
                    ]
                )
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(QtGui.QColor(OVERRIDE_INK))
                painter.drawPolygon(diamond)
        finally:
            painter.restore()
