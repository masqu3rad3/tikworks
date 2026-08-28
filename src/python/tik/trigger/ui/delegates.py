"""Painting of pipeline rows: status stripe, category icon, name, summary, linked look."""

from __future__ import annotations

from tik.shared.ui import theme
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets

from .model import CategoryRole, EnabledRole, LabelRole, LinkedRole, StatusRole, SummaryRole, TypeRole

ROW_HEIGHT = 26
STRIPE = 3


class PipelineDelegate(QtWidgets.QStyledItemDelegate):
    def sizeHint(self, option, index):  # noqa: N802
        return QtCore.QSize(200, ROW_HEIGHT)

    def paint(self, painter: QtGui.QPainter, option, index) -> None:
        painter.save()
        rect = option.rect
        selected = bool(option.state & QtWidgets.QStyle.State_Selected)
        enabled = bool(index.data(EnabledRole))
        linked = bool(index.data(LinkedRole))
        status = index.data(StatusRole) or ""
        category = index.data(CategoryRole) or "utility"

        # row background
        background = QtGui.QColor(theme.PANEL_ALT if selected else theme.PANEL)
        if linked and not selected:
            background = QtGui.QColor("#292929")
        if status == "running" and not selected:
            background = QtGui.QColor("#3a2e1f")
        painter.fillRect(rect.adjusted(0, 1, 0, -1), background)

        # status / selection stripe
        stripe_color = QtGui.QColor(theme.ACCENT if selected else theme.STATUS.get(status, theme.STATUS[""]))
        pen = QtGui.QPen(stripe_color, STRIPE)
        if linked and not selected and not status:
            pen.setStyle(QtCore.Qt.DashLine)
            pen.setColor(QtGui.QColor(theme.LINKED))
        painter.setPen(pen)
        painter.drawLine(rect.left() + 1, rect.top() + 3, rect.left() + 1, rect.bottom() - 2)

        opacity = 1.0 if enabled else 0.4
        painter.setOpacity(opacity * (0.8 if linked else 1.0))

        # checkbox for linked rows
        x = rect.left() + 8
        if linked:
            box = QtCore.QRect(x, rect.center().y() - 6, 12, 12)
            painter.setPen(QtGui.QPen(QtGui.QColor(theme.LINKED), 1))
            painter.setBrush(QtGui.QColor(theme.STATUS["done"]) if enabled else QtCore.Qt.NoBrush)
            painter.drawRoundedRect(box, 2, 2)
            x += 18

        # icon
        icon = glyph_icon(initials(index.data(LabelRole) or index.data(TypeRole) or "?"), theme.CATEGORY.get(category, theme.CATEGORY["utility"]))
        icon.paint(painter, QtCore.QRect(x, rect.center().y() - 9, 18, 18))
        x += 24

        # name
        font = painter.font()
        painter.setFont(font)
        painter.setPen(QtGui.QColor(theme.TEXT_BRIGHT if selected else theme.TEXT))
        name = index.data(QtCore.Qt.DisplayRole) or ""
        if linked:
            name = "⛓ " + name
        metrics = painter.fontMetrics()
        name_width = metrics.horizontalAdvance(name)
        painter.drawText(QtCore.QRect(x, rect.top(), name_width + 4, rect.height()), QtCore.Qt.AlignVCenter, name)
        x += name_width + 12

        # summary
        summary = index.data(SummaryRole) or ""
        if status == "failed":
            summary = "failed — " + (index.data(QtCore.Qt.ToolTipRole) or "")
        if summary:
            painter.setPen(QtGui.QColor(theme.STATUS["failed"] if status == "failed" else theme.TEXT_DIM))
            small = QtGui.QFont(font)
            small.setPointSizeF(max(font.pointSizeF() - 1, 7))
            painter.setFont(small)
            elided = painter.fontMetrics().elidedText(summary, QtCore.Qt.ElideMiddle, max(rect.right() - x - 6, 20))
            painter.drawText(QtCore.QRect(x, rect.top(), rect.right() - x - 4, rect.height()), QtCore.Qt.AlignVCenter, elided)
        painter.restore()

    def checkbox_rect(self, option, index) -> QtCore.QRect:
        rect = option.rect
        return QtCore.QRect(rect.left() + 8, rect.center().y() - 6, 12, 12)

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: N802
        if (event.type() == QtCore.QEvent.MouseButtonRelease and index.data(LinkedRole)
                and self.checkbox_rect(option, index).adjusted(-3, -3, 3, 3).contains(event.pos())):
            state = QtCore.Qt.Unchecked if index.data(EnabledRole) else QtCore.Qt.Checked
            return model.setData(index, state, QtCore.Qt.CheckStateRole)
        return super().editorEvent(event, model, option, index)
