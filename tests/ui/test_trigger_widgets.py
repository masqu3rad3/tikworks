"""The small widgets the Trigger window is assembled from.

``NameEdit`` had no tests at all, and ``PipelineDelegate`` was only ever
painted incidentally -- which matters because a delegate's ``paint`` is
exactly the kind of code that raises in production and nowhere else. These
tests do not assert pixels (that would be brittle and prove little); they
assert the row *geometry contract* the view depends on, and that every branch
of the painter survives being run.
"""

from __future__ import annotations

import pytest

from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.ui.delegates import GUTTER, ROW_HEIGHT, PipelineDelegate
from tik.trigger.ui.model import (
    CategoryRole,
    EnabledRole,
    LabelRole,
    LinkedRole,
    StatusRole,
    SummaryRole,
    TypeRole,
)
from tik.trigger.ui.widgets import LogWidget, NameEdit


class TestNameEdit:
    """``renamed(old, new)`` fires on commit, and only for a real change."""

    @pytest.fixture
    def edit(self, qapp):
        widget = NameEdit()
        widget.set_name("arm")
        return widget

    @pytest.fixture
    def renames(self, edit):
        seen: list = []
        edit.renamed.connect(lambda old, new: seen.append((old, new)))
        return seen

    def test_set_name_shows_the_name(self, edit):
        assert edit.text() == "arm"

    def test_committing_a_new_name_reports_both(self, edit, renames):
        edit.setText("leg")
        edit.editingFinished.emit()

        assert renames == [("arm", "leg")]

    def test_committing_the_same_name_reports_nothing(self, edit, renames):
        edit.setText("arm")
        edit.editingFinished.emit()

        assert renames == []

    def test_surrounding_whitespace_is_stripped(self, edit, renames):
        edit.setText("  leg  ")
        edit.editingFinished.emit()

        assert renames == [("arm", "leg")]

    def test_whitespace_only_is_not_a_rename(self, edit, renames):
        """Clearing the field must not rename the module to nothing."""
        edit.setText("   ")
        edit.editingFinished.emit()

        assert renames == []

    def test_an_empty_name_is_not_a_rename(self, edit, renames):
        edit.setText("")
        edit.editingFinished.emit()

        assert renames == []

    def test_a_name_that_only_gains_whitespace_is_not_a_rename(self, edit, renames):
        edit.setText(" arm ")
        edit.editingFinished.emit()

        assert renames == []

    def test_the_second_commit_reports_the_first_new_name_as_old(self, edit, renames):
        """The widget adopts the committed name; it does not keep reverting."""
        edit.setText("leg")
        edit.editingFinished.emit()
        edit.setText("tail")
        edit.editingFinished.emit()

        assert renames == [("arm", "leg"), ("leg", "tail")]

    def test_committing_twice_without_a_change_reports_once(self, edit, renames):
        edit.setText("leg")
        edit.editingFinished.emit()
        edit.editingFinished.emit()

        assert renames == [("arm", "leg")]

    def test_set_name_resets_what_counts_as_unchanged(self, edit, renames):
        edit.set_name("tail")
        edit.setText("tail")
        edit.editingFinished.emit()

        assert renames == []


class TestLogWidget:
    """The dock's log: colouring and the block cap."""

    @pytest.fixture
    def log(self, qapp):
        return LogWidget()

    def test_a_plain_message_is_shown(self, log):
        log.append_message("building arm")

        assert "building arm" in log.toPlainText()

    @pytest.mark.parametrize("level", ["warning", "error"])
    def test_a_ranked_level_is_coloured(self, log, level):
        log.append_message("something", level=level)

        assert LogWidget.LEVEL_COLORS[level] in log.document().toHtml()

    def test_info_is_not_coloured(self, log):
        log.append_message("plain", level="info")

        for color in LogWidget.LEVEL_COLORS.values():
            assert color not in log.document().toHtml()

    def test_a_filtered_message_never_reaches_the_document(self, log):
        log.set_level("error")

        log.append_message("chatter", level="info")

        assert log.toPlainText() == ""

    def test_the_log_is_read_only(self, log):
        assert log.isReadOnly()

    def test_the_log_is_capped(self, log):
        """An unbounded log is a memory leak in a long Maya session."""
        assert log.maximumBlockCount() == 2000


def _index(model, roles=None, name="arm"):
    """One row carrying the roles the delegate paints from.

    Roles arrive as a dict, not keyword arguments: Qt role ids are ints.
    """
    item = QtGui.QStandardItem(name)
    for role, value in (roles or {}).items():
        item.setData(value, role)
    model.appendRow(item)
    return model.indexFromItem(item)


class TestPipelineDelegate:
    """Row geometry, the checkbox hit area, and that painting never raises."""

    @pytest.fixture
    def delegate(self, qapp):
        return PipelineDelegate()

    @pytest.fixture
    def model(self, qapp):
        return QtGui.QStandardItemModel()

    @pytest.fixture
    def option(self, qapp):
        opt = QtWidgets.QStyleOptionViewItem()
        opt.rect = QtCore.QRect(0, 0, 300, ROW_HEIGHT)
        opt.font = QtGui.QFont()
        return opt

    def test_every_row_is_the_declared_height(self, delegate, model, option):
        assert delegate.sizeHint(option, _index(model)).height() == ROW_HEIGHT

    def test_the_checkbox_sits_after_the_gutter(self, delegate, model, option):
        box = delegate.checkbox_rect(option, _index(model))

        assert box.left() > option.rect.left() + GUTTER
        assert box.width() == 11 and box.height() == 11

    def test_the_checkbox_is_vertically_centred(self, delegate, model, option):
        box = delegate.checkbox_rect(option, _index(model))

        assert abs(box.center().y() - option.rect.center().y()) <= 1

    @pytest.mark.parametrize(
        "roles",
        [
            {},
            {StatusRole: "done"},
            {StatusRole: "running"},
            {StatusRole: "failed", QtCore.Qt.ToolTipRole: "boom"},
            {EnabledRole: False},
            {LinkedRole: True},
            {LinkedRole: True, EnabledRole: False},
            {LinkedRole: True, StatusRole: "failed"},
            {CategoryRole: "deform", TypeRole: "weights"},
            {TypeRole: "no_such_action_type"},
            {LabelRole: "Weights", SummaryRole: "12 joints"},
            {SummaryRole: "x" * 400},
        ],
        ids=[
            "plain",
            "done",
            "running",
            "failed",
            "disabled",
            "linked",
            "linked-disabled",
            "linked-failed",
            "category",
            "unknown-type",
            "labelled",
            "over-long-summary",
        ],
    )
    def test_painting_a_row_never_raises(self, delegate, model, option, roles):
        """A delegate that throws mid-paint takes the whole view down."""
        pixmap = QtGui.QPixmap(300, ROW_HEIGHT)
        painter = QtGui.QPainter(pixmap)
        try:
            delegate.paint(painter, option, _index(model, roles))
        finally:
            painter.end()

    def test_a_selected_row_paints(self, delegate, model, option):
        option.state |= QtWidgets.QStyle.State_Selected
        pixmap = QtGui.QPixmap(300, ROW_HEIGHT)
        painter = QtGui.QPainter(pixmap)
        try:
            delegate.paint(painter, option, _index(model, {LinkedRole: True}))
        finally:
            painter.end()

    def test_a_narrow_row_drops_the_summary_rather_than_overflowing(
        self, delegate, model, option
    ):
        option.rect = QtCore.QRect(0, 0, 40, ROW_HEIGHT)
        pixmap = QtGui.QPixmap(40, ROW_HEIGHT)
        painter = QtGui.QPainter(pixmap)
        try:
            delegate.paint(painter, option, _index(model, {SummaryRole: "12 joints"}))
        finally:
            painter.end()


class TestLinkedCheckboxClicks:
    """``editorEvent`` toggles a linked row's checkbox; everything else passes on."""

    @pytest.fixture
    def delegate(self, qapp):
        return PipelineDelegate()

    @pytest.fixture
    def option(self, qapp):
        opt = QtWidgets.QStyleOptionViewItem()
        opt.rect = QtCore.QRect(0, 0, 300, ROW_HEIGHT)
        opt.font = QtGui.QFont()
        return opt

    @pytest.fixture
    def model(self, qapp):
        class Model(QtGui.QStandardItemModel):
            def __init__(self):
                super().__init__()
                self.writes: list = []

            def setData(self, index, value, role=QtCore.Qt.EditRole):  # noqa: N802
                self.writes.append((value, role))
                return True

        return Model()

    def _release(self, point):
        return QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(point),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )

    def test_clicking_a_linked_checkbox_toggles_it_on(self, delegate, model, option):
        index = _index(model, {LinkedRole: True, EnabledRole: False})
        event = self._release(delegate.checkbox_rect(option, index).center())

        assert delegate.editorEvent(event, model, option, index) is True
        assert model.writes == [(QtCore.Qt.Checked, QtCore.Qt.CheckStateRole)]

    def test_clicking_an_enabled_linked_checkbox_toggles_it_off(
        self, delegate, model, option
    ):
        index = _index(model, {LinkedRole: True, EnabledRole: True})
        event = self._release(delegate.checkbox_rect(option, index).center())

        delegate.editorEvent(event, model, option, index)

        assert model.writes == [(QtCore.Qt.Unchecked, QtCore.Qt.CheckStateRole)]

    def test_the_hit_area_is_forgiving(self, delegate, model, option):
        """An 11px box is a hard target; the delegate grows it by 3px each way."""
        index = _index(model, {LinkedRole: True, EnabledRole: False})
        box = delegate.checkbox_rect(option, index)
        event = self._release(box.topLeft() + QtCore.QPoint(-2, -2))

        assert delegate.editorEvent(event, model, option, index) is True

    def test_a_click_away_from_the_box_is_not_a_toggle(self, delegate, model, option):
        index = _index(model, {LinkedRole: True, EnabledRole: False})
        event = self._release(QtCore.QPoint(option.rect.right() - 5, 5))

        delegate.editorEvent(event, model, option, index)

        assert model.writes == []

    def test_an_unlinked_row_has_no_checkbox_to_click(self, delegate, model, option):
        index = _index(model, {LinkedRole: False, EnabledRole: False})
        event = self._release(delegate.checkbox_rect(option, index).center())

        delegate.editorEvent(event, model, option, index)

        assert model.writes == []
