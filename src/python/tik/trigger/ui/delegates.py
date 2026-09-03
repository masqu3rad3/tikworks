"""Pipeline row painter.

    [status dot][stripe] [icon] name  summary                    (26px rows)

- left stripe: category colour (dashed + dimmed for linked rows)
- gutter dot: run status (done / running / failed)
- selection: muted tint + 2px accent bar, never the solid orange fill
"""

from __future__ import annotations

from tik.shared.ui import theme
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets

from .model import CategoryRole, EnabledRole, LabelRole, LinkedRole, StatusRole, SummaryRole, TypeRole

ROW_HEIGHT = 26
GUTTER = 16
STRIPE = 2
SELECTION_TINT = "#332a20"
ZEBRA = ("#151515", "#191919")


class PipelineDelegate(QtWidgets.QStyledItemDelegate):
    def sizeHint(self, option, index):  # noqa: N802
        return QtCore.QSize(220, ROW_HEIGHT)

    def paint(self, painter: QtGui.QPainter, option, index) -> None:
        painter.save()
        try:
            self._paint(painter, option, index)
        finally:
            painter.restore()

    def _paint(self, painter, option, index) -> None:
        rect = option.rect
        selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        hovered = bool(option.state & QtWidgets.QStyle.State_MouseOver)
        enabled = bool(index.data(EnabledRole))
        linked = bool(index.data(LinkedRole))
        status = index.data(StatusRole) or ""
        category = index.data(CategoryRole) or "utility"
        category_color = theme.CATEGORY.get(category, theme.CATEGORY["utility"])

        # background: zebra by visual row, tint when selected, faint when hovered
        row_parity = (rect.top() // ROW_HEIGHT) % 2
        painter.fillRect(rect, QtGui.QColor(ZEBRA[row_parity]))
        if selected:
            painter.fillRect(rect, QtGui.QColor(SELECTION_TINT))
        elif hovered:
            painter.fillRect(rect, QtGui.QColor(255, 255, 255, 8))
        if selected:
            painter.fillRect(QtCore.QRect(rect.left(), rect.top(), 2, rect.height()), QtGui.QColor(theme.ACCENT))

        # gutter status dot
        dot_color = theme.STATUS.get(status) if status else None
        if dot_color:
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(dot_color))
            center = QtCore.QPointF(rect.left() + 3 + GUTTER / 2, rect.center().y() + 0.5)
            painter.drawEllipse(center, 3.5, 3.5)
            if status == "running":
                painter.setBrush(QtGui.QColor(254, 126, 0, 60))
                painter.drawEllipse(center, 6.0, 6.0)

        pen_x = rect.left() + 3 + GUTTER + 2
        # category stripe
        pen = QtGui.QPen(QtGui.QColor(theme.LINKED if linked else category_color), STRIPE)
        if linked:
            pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(pen_x, rect.top() + 5, pen_x, rect.bottom() - 4)
        pen_x += 8

        painter.setOpacity((1.0 if enabled else 0.4) * (0.85 if linked else 1.0))

        if linked:  # checkbox
            box = QtCore.QRect(pen_x, rect.center().y() - 5, 11, 11)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setPen(QtGui.QPen(QtGui.QColor(theme.LINKED), 1))
            painter.setBrush(QtGui.QColor(theme.STATUS["done"]) if enabled else QtCore.Qt.NoBrush)
            painter.drawRoundedRect(box, 2, 2)
            pen_x += 17

        icon = glyph_icon(initials(index.data(LabelRole) or index.data(TypeRole) or "?"), category_color, size=16)
        icon.paint(painter, QtCore.QRect(pen_x, rect.center().y() - 8, 16, 16))
        pen_x += 22

        font = QtGui.QFont(option.font)
        if linked:
            font.setItalic(True)
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#e6e6e6" if selected else ("#a8b3c2" if linked else theme.TEXT)))
        name = index.data(QtCore.Qt.DisplayRole) or ""
        if linked:  # painted chain glyph (fonts rarely have U+26D3)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            pen = QtGui.QPen(QtGui.QColor(theme.LINKED), 1.4)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            cy = rect.center().y() + 0.5
            painter.drawEllipse(QtCore.QRectF(pen_x, cy - 3, 6, 6))
            painter.drawEllipse(QtCore.QRectF(pen_x + 5, cy - 3, 6, 6))
            pen_x += 15
            painter.setPen(QtGui.QColor("#e6e6e6" if selected else "#a8b3c2"))
        metrics = QtGui.QFontMetrics(font)
        name_width = metrics.horizontalAdvance(name)
        painter.drawText(QtCore.QRect(pen_x, rect.top(), name_width + 4, rect.height()), QtCore.Qt.AlignVCenter, name)
        pen_x += name_width + 12

        summary = index.data(SummaryRole) or ""
        if status == "failed":
            summary = "failed — " + (index.data(QtCore.Qt.ToolTipRole) or "")
        if summary and pen_x < rect.right() - 30:
            small = QtGui.QFont(option.font)
            small.setPointSizeF(max(option.font.pointSizeF() - 1, 7))
            painter.setFont(small)
            painter.setPen(QtGui.QColor(theme.STATUS["failed"] if status == "failed" else theme.TEXT_DIM))
            elided = QtGui.QFontMetrics(small).elidedText(summary, QtCore.Qt.ElideMiddle, rect.right() - pen_x - 8)
            painter.drawText(QtCore.QRect(pen_x, rect.top(), rect.right() - pen_x - 6, rect.height()), QtCore.Qt.AlignVCenter, elided)

    def checkbox_rect(self, option, index) -> QtCore.QRect:
        pen_x = option.rect.left() + 3 + GUTTER + 2 + 8
        return QtCore.QRect(pen_x, option.rect.center().y() - 5, 11, 11)

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: N802
        if (event.type() == QtCore.QEvent.MouseButtonRelease and index.data(LinkedRole)
                and self.checkbox_rect(option, index).adjusted(-3, -3, 3, 3).contains(event.pos())):
            state = QtCore.Qt.Unchecked if index.data(EnabledRole) else QtCore.Qt.Checked
            return model.setData(index, state, QtCore.Qt.CheckStateRole)
        return super().editorEvent(event, model, option, index)
