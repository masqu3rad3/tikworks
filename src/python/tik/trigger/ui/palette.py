"""Search palette (Tab): type to filter, Enter adds after the selection, Shift+Enter as a child."""

from __future__ import annotations

from typing import Optional, Sequence

from tik.shared.ui import theme
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets


class PaletteEntry:
    __slots__ = ("key", "label", "category", "keywords")

    def __init__(
        self, key: str, label: str, category: str = "", keywords: Sequence[str] = ()
    ) -> None:
        self.key = key
        self.label = label
        self.category = category
        self.keywords = [item.lower() for item in keywords]

    def matches(self, text: str) -> bool:
        text = text.lower().strip()
        if not text:
            return True
        haystack = [
            self.key.lower(),
            self.label.lower(),
            self.category.lower(),
            *self.keywords,
        ]
        return any(text in item for item in haystack)


class SearchPalette(QtWidgets.QFrame):
    """A popup list with a filter line. Reusable for actions and modules."""

    chosen = QtCore.Signal(str, bool)  # key, as_child
    dismissed = QtCore.Signal()

    MAX_RECENT = 6

    def __init__(
        self,
        entries: Sequence[PaletteEntry],
        parent=None,
        colors: Optional[dict] = None,
    ) -> None:
        super().__init__(parent, QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.entries = list(entries)
        self.colors = colors or theme.CATEGORY
        self.recent: list[str] = []
        self.setObjectName("SearchPalette")
        self.setStyleSheet(
            f"#SearchPalette {{ background: {theme.INPUT}; border: 1px solid {theme.LINE}; border-radius: 6px; }}"
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText(
            "Type to search…  Enter: add after · Shift+Enter: add as child"
        )
        self.list = QtWidgets.QListWidget()
        self.list.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.list.setIconSize(QtCore.QSize(18, 18))
        layout.addWidget(self.search)
        layout.addWidget(self.list)
        self.resize(380, 320)
        self.search.textChanged.connect(self.refilter)
        self.search.installEventFilter(self)
        self.list.itemActivated.connect(lambda item: self._choose(False))
        self.refilter()

    # ----------------------------------------------------------- filtering
    def refilter(self) -> None:
        text = self.search.text()
        self.list.clear()
        entries = [entry for entry in self.entries if entry.matches(text)]
        if not text:
            recent = [
                entry for key in self.recent for entry in entries if entry.key == key
            ]
            others = [entry for entry in entries if entry.key not in self.recent]
            ordered = recent + sorted(
                others, key=lambda entry: (entry.category, entry.label)
            )
            if recent:
                self._add_header("recent")
                for entry in recent:
                    self._add_entry(entry)
                current_category = None
                for entry in sorted(
                    others, key=lambda entry: (entry.category, entry.label)
                ):
                    if entry.category != current_category:
                        current_category = entry.category
                        self._add_header(current_category)
                    self._add_entry(entry)
            else:
                current_category = None
                for entry in ordered:
                    if entry.category != current_category:
                        current_category = entry.category
                        self._add_header(current_category)
                    self._add_entry(entry)
        else:
            for entry in sorted(
                entries,
                key=lambda entry: (
                    not entry.label.lower().startswith(text.lower()),
                    entry.label,
                ),
            ):
                self._add_entry(entry)
        for row in range(self.list.count()):
            if self.list.item(row).flags() & QtCore.Qt.ItemIsSelectable:
                self.list.setCurrentRow(row)
                break

    def _add_header(self, text: str) -> None:
        item = QtWidgets.QListWidgetItem(text.upper())
        item.setFlags(QtCore.Qt.NoItemFlags)
        item.setForeground(QtGui.QColor(theme.TEXT_DIM))
        font = item.font()
        font.setPointSizeF(max(font.pointSizeF() - 2, 6))
        item.setFont(font)
        self.list.addItem(item)

    def _add_entry(self, entry: PaletteEntry) -> None:
        item = QtWidgets.QListWidgetItem(
            glyph_icon(
                initials(entry.label),
                self.colors.get(entry.category, theme.CATEGORY["utility"]),
            ),
            entry.label,
        )
        item.setData(QtCore.Qt.UserRole, entry.key)
        item.setToolTip(f"{entry.key} · {entry.category}")
        self.list.addItem(item)

    def current_key(self) -> Optional[str]:
        item = self.list.currentItem()
        return item.data(QtCore.Qt.UserRole) if item is not None else None

    def visible_keys(self) -> list[str]:
        return [
            self.list.item(row).data(QtCore.Qt.UserRole)
            for row in range(self.list.count())
            if self.list.item(row).data(QtCore.Qt.UserRole)
        ]

    # ----------------------------------------------------------- choosing
    def _choose(self, as_child: bool) -> None:
        key = self.current_key()
        if key is None:
            return
        if key in self.recent:
            self.recent.remove(key)
        self.recent.insert(0, key)
        del self.recent[self.MAX_RECENT :]
        self.hide()
        self.chosen.emit(key, as_child)

    def _move(self, delta: int) -> None:
        row = self.list.currentRow()
        count = self.list.count()
        for _step in range(count):
            row = (row + delta) % count
            if self.list.item(row).flags() & QtCore.Qt.ItemIsSelectable:
                self.list.setCurrentRow(row)
                return

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.search and event.type() == QtCore.QEvent.KeyPress:
            key = event.key()
            if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                self._choose(bool(event.modifiers() & QtCore.Qt.ShiftModifier))
                return True
            if key == QtCore.Qt.Key_Down:
                self._move(1)
                return True
            if key == QtCore.Qt.Key_Up:
                self._move(-1)
                return True
            if key == QtCore.Qt.Key_Escape:
                self.hide()
                self.dismissed.emit()
                return True
        return super().eventFilter(obj, event)

    def popup(self, global_pos: QtCore.QPoint) -> None:
        self.search.clear()
        self.refilter()
        self.move(global_pos)
        self.show()
        self.search.setFocus()
