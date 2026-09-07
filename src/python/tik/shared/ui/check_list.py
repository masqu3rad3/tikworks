"""A tick list for a ``ListField`` that declares ``choices_from``.

The list only ever sees ``(label, value)`` pairs, which is what makes it
repurposable: it shows each option by its label and stores its *value*, so a
list of uuids nobody would type by hand becomes editable. Options are re-read
on every ``set_value``, because the thing being offered -- a session's modules,
say -- changes while the panel is open.

Declaring ``filterable`` adds the furniture a list of dozens needs: the shared
``FilterBar``, a "show only selected" box whose state is a saved setting, and a
context menu for the bulk edits. A list without it is exactly the bare list it
has always been.
"""

from __future__ import annotations

from typing import Callable, Optional

from tik.shared.ui.filter_bar import FilterBar
from tik.shared.ui.Qt import QtCore, QtWidgets

#: Appended to a choice the target no longer offers, so a row referencing a
#: renamed or removed option stays visible instead of being rewritten.
MISSING_SUFFIX = " (missing)"

#: Display order, by menu label. Sorting is a *view*: the stored value stays in
#: document order whatever is picked here, so looking at a list alphabetically
#: can never dirty the session.
SORT_MODES = (
    ("document", "Document Order"),
    ("az", "Sort A-Z"),
    ("za", "Sort Z-A"),
)


class CheckListEditor(QtWidgets.QWidget):
    """Tick list over ``(label, value)`` options, optionally filterable.

    Signals:
        valueChanged(list): the ticked values, in document order.
        onlySelectedChanged(bool): the user toggled "show only selected".
            Setting it programmatically is silent -- pushing a stored value in
            is not somebody changing it.
    """

    valueChanged = QtCore.Signal(list)  # noqa: N815 - Qt signal naming
    onlySelectedChanged = QtCore.Signal(bool)  # noqa: N815 - Qt signal naming

    def __init__(
        self,
        options: Callable[[], list],
        filterable: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._options = options
        self._value: list = []
        #: ``(label, value)`` in document order -- the order the stored value
        #: is written in, whatever order the rows are shown in.
        self._entries: list = []
        self._items: dict = {}
        self._loading = False
        self._only_selected = False
        self._sort_mode = "document"
        #: Values unticked since the last read while "only selected" was on.
        #: They stay on screen so a row never vanishes out from under the
        #: cursor that just clicked it; the next read drops them.
        self._kept: set = set()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        self.filter_bar: Optional[FilterBar] = None
        self.only_selected_box: Optional[QtWidgets.QCheckBox] = None
        self.count_label: Optional[QtWidgets.QLabel] = None
        if filterable:
            self.filter_bar = FilterBar(self, placeholder="Filter…")
            layout.addWidget(self.filter_bar)
            layout.addWidget(self._build_header())

        self.list = QtWidgets.QListWidget(self)
        self.list.setObjectName("CheckList")
        self.list.setUniformItemSizes(True)
        # The filter bar and header cost height a properties panel does not
        # have to spare, so the list itself gives some back.
        self.list.setMaximumHeight(150 if filterable else 160)
        self.list.setProperty("onlySelected", False)
        self.list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._show_menu)
        self.list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list)

        if self.filter_bar is not None:
            self.filter_bar.filter_changed.connect(self._apply_visibility)

    def _build_header(self) -> QtWidgets.QWidget:
        header = QtWidgets.QWidget(self)
        header.setObjectName("CheckListHeader")
        row = QtWidgets.QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.only_selected_box = QtWidgets.QCheckBox("Only selected", header)
        self.only_selected_box.setObjectName("CheckListOnlySelected")
        self.only_selected_box.setToolTip(
            "Hide the rows that are not ticked. Typing in the filter still "
            "reveals everything it matches."
        )
        self.only_selected_box.toggled.connect(self._on_box_toggled)
        self.count_label = QtWidgets.QLabel("", header)
        self.count_label.setObjectName("CheckListCount")
        row.addWidget(self.only_selected_box)
        row.addStretch(1)
        row.addWidget(self.count_label)
        return header

    # ------------------------------------------------------------- the value
    def value(self) -> list:
        """The ticked values, in the order the options offer them."""
        return list(self._value)

    def set_value(self, value) -> None:
        """Show ``value`` as ticks, re-reading the options first."""
        self._value = [str(item) for item in (value or [])]
        self._kept.clear()
        offered = []
        entries = []
        for label, item_value in self._options() or []:
            offered.append(str(item_value))
            entries.append((str(label), str(item_value)))
        # A stored value nothing offers any more is kept, ticked, and marked.
        # Dropping it would silently shrink whatever the list governs the
        # moment somebody opened the panel.
        for stored in self._value:
            if stored not in offered:
                entries.append((f"{stored}{MISSING_SUFFIX}", stored))
        self._entries = entries
        self._repopulate()

    # ------------------------------------------------- only selected & sorting
    @property
    def only_selected(self) -> bool:
        """True while unticked rows are hidden."""
        return self._only_selected

    def set_only_selected(self, state) -> None:
        """Hide or show the unticked rows without reporting a user change."""
        state = bool(state)
        if self.only_selected_box is not None:
            blocked = self.only_selected_box.blockSignals(True)
            try:
                self.only_selected_box.setChecked(state)
            finally:
                self.only_selected_box.blockSignals(blocked)
        self._set_only_selected(state)

    @property
    def sort_mode(self) -> str:
        """The display order: ``document``, ``az`` or ``za``."""
        return self._sort_mode

    def set_sort_mode(self, mode: str) -> None:
        """Reorder the rows. The stored value is untouched."""
        if mode not in dict(SORT_MODES):
            raise ValueError(f"unknown sort mode {mode!r}")
        if mode == self._sort_mode:
            return
        self._sort_mode = mode
        self._repopulate()

    def _set_only_selected(self, state: bool) -> None:
        self._only_selected = state
        self._kept.clear()
        self.list.setProperty("onlySelected", state)
        # A dynamic property changes nothing until the style is asked again.
        self.list.style().unpolish(self.list)
        self.list.style().polish(self.list)
        self._apply_visibility()

    def _on_box_toggled(self, state) -> None:
        self._set_only_selected(bool(state))
        self.onlySelectedChanged.emit(bool(state))

    # -------------------------------------------------------- the bulk edits
    def select_all(self) -> None:
        """Tick every option -- the whole list, not only the visible rows."""
        self._set_all(lambda _value: True)

    def select_none(self) -> None:
        """Untick every option."""
        self._set_all(lambda _value: False)

    def invert_selection(self) -> None:
        """Tick what is unticked and untick what is ticked."""
        ticked = set(self._value)
        self._set_all(lambda value: value not in ticked)

    def _set_all(self, wanted: Callable[[str], bool]) -> None:
        self._loading = True
        try:
            for _label, value in self._entries:
                item = self._items[value]
                item.setCheckState(
                    QtCore.Qt.Checked if wanted(value) else QtCore.Qt.Unchecked
                )
                if self._only_selected and not wanted(value):
                    self._kept.add(value)
        finally:
            self._loading = False
        self._recompute()

    # ------------------------------------------------------------- the menu
    def context_menu(self) -> QtWidgets.QMenu:
        """The right-click menu, built fresh so the sort ticks stay honest."""
        menu = QtWidgets.QMenu(self)
        menu.addAction("Select All", self.select_all)
        menu.addAction("Select None", self.select_none)
        menu.addAction("Invert Selection", self.invert_selection)
        menu.addSeparator()
        group = QtWidgets.QActionGroup(menu)
        group.setExclusive(True)
        for mode, label in SORT_MODES:
            action = QtWidgets.QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(mode == self._sort_mode)
            action.triggered.connect(
                lambda _checked=False, m=mode: self.set_sort_mode(m)
            )
            group.addAction(action)
            menu.addAction(action)
        return menu

    def _show_menu(self, point) -> None:
        self.context_menu().exec_(self.list.viewport().mapToGlobal(point))

    # ------------------------------------------------------------- rendering
    def _repopulate(self) -> None:
        """Rebuild the rows in the current sort order, ticks intact."""
        self._loading = True
        try:
            self.list.clear()
            self._items = {}
            for label, value in self._ordered():
                item = QtWidgets.QListWidgetItem(label)
                item.setData(QtCore.Qt.UserRole, value)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(
                    QtCore.Qt.Checked if value in self._value else QtCore.Qt.Unchecked
                )
                self.list.addItem(item)
                self._items[value] = item
        finally:
            self._loading = False
        self._apply_visibility()

    def _ordered(self) -> list:
        if self._sort_mode == "az":
            return sorted(self._entries, key=lambda entry: entry[0].lower())
        if self._sort_mode == "za":
            return sorted(
                self._entries, key=lambda entry: entry[0].lower(), reverse=True
            )
        return list(self._entries)

    def _apply_visibility(self) -> None:
        """Hide the rows the filter and the only-selected box rule out.

        Rows are hidden, never removed: tick state, selection and scroll
        position all survive typing. An active filter overrides only-selected,
        so finding one more module to add does not mean untick the box first.
        """
        filtering = self.filter_bar is not None and self.filter_bar.model.is_active
        shown = 0
        for value, item in self._items.items():
            visible = self.filter_bar is None or self.filter_bar.matches(item.text())
            if visible and self._only_selected and not filtering:
                visible = value in self._value or value in self._kept
            item.setHidden(not visible)
            shown += int(visible)
        self._update_count(shown)

    def _update_count(self, shown: int) -> None:
        if self.count_label is None:
            return
        total = len(self._entries)
        text = f"{len(self._value)} of {total}"
        if shown != total:
            text = f"{text} · {shown} shown"
        self.count_label.setText(text)

    def _on_item_changed(self, item) -> None:
        if self._loading:
            return
        if self._only_selected and item.checkState() != QtCore.Qt.Checked:
            self._kept.add(item.data(QtCore.Qt.UserRole))
        self._recompute()

    def _recompute(self) -> None:
        """Read the ticks back in document order and report them once."""
        ticked = [
            value
            for _label, value in self._entries
            if self._items[value].checkState() == QtCore.Qt.Checked
        ]
        self._value = ticked
        self._apply_visibility()
        self.valueChanged.emit(list(ticked))
