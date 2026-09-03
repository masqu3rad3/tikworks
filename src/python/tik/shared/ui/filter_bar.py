"""Keyword filter bar: a line edit plus removable keyword pills, OR-ed together.

Ported from creature_kit ``face_control/designer/ui/track_filter.py``.
The text being typed filters immediately as one more provisional keyword;
Enter freezes it into a pill; Backspace on an empty field drops the last
pill. No Maya, no colours of its own — the object names below are styled
by ``tik.shared.ui.theme``.
"""

from __future__ import annotations


from tik.shared.ui.Qt import QtCore, QtWidgets


class FilterModel(QtCore.QObject):
    """Case-insensitive OR substring matching over committed + pending keywords."""

    filter_changed = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._keywords: list[str] = []
        self._pending = ""

    def set_keywords(self, keywords) -> None:
        self._keywords = [
            keyword.strip().lower() for keyword in keywords or () if keyword and keyword.strip()
        ]
        self.filter_changed.emit()

    def set_pending_text(self, text) -> None:
        self._pending = (text or "").strip().lower()
        self.filter_changed.emit()

    @property
    def keywords(self) -> list[str]:
        return list(self._keywords)

    @property
    def is_active(self) -> bool:
        return bool(self._keywords or self._pending)

    def _terms(self) -> list[str]:
        return self._keywords + ([self._pending] if self._pending else [])

    def matches(self, text) -> bool:
        """OR logic: any term found in ``text`` is a match; no terms = everything matches."""
        terms = self._terms()
        if not terms:
            return True
        if not text:
            return False
        lowered = text.lower()
        return any(term in lowered for term in terms)


class _Pill(QtWidgets.QFrame):
    remove_clicked = QtCore.Signal(str)

    def __init__(self, keyword: str, parent=None) -> None:
        super().__init__(parent)
        self._keyword = keyword
        self.setObjectName("FilterPill")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(7, 0, 3, 0)
        layout.setSpacing(4)
        label = QtWidgets.QLabel(keyword, self)
        label.setObjectName("FilterPillLabel")
        layout.addWidget(label)
        close = QtWidgets.QToolButton(self)
        close.setObjectName("FilterPillClose")
        close.setText("✕")
        close.setToolTip("Remove this keyword")
        close.clicked.connect(lambda: self.remove_clicked.emit(self._keyword))
        layout.addWidget(close)

    def keyword(self) -> str:
        return self._keyword


class _FilterLineEdit(QtWidgets.QLineEdit):
    backspace_on_empty = QtCore.Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == QtCore.Qt.Key_Backspace and not self.text():
            self.backspace_on_empty.emit()
            return
        super().keyPressEvent(event)


class FilterBar(QtWidgets.QWidget):
    """Line edit plus a row of committed keyword pills."""

    filter_changed = QtCore.Signal()

    def __init__(self, parent=None, placeholder: str = "Filter…  (Enter to keep a keyword)") -> None:
        super().__init__(parent)
        self.setObjectName("FilterBar")
        self._model = FilterModel(self)
        self._pills: list[_Pill] = []
        self._line_edit = _FilterLineEdit(self)
        self._line_edit.setObjectName("FilterInput")
        self._line_edit.setPlaceholderText(placeholder)
        self._line_edit.setClearButtonEnabled(True)
        self._pill_row = QtWidgets.QWidget(self)
        self._pill_layout = QtWidgets.QHBoxLayout(self._pill_row)
        self._pill_layout.setContentsMargins(0, 0, 0, 0)
        self._pill_layout.setSpacing(4)
        self._pill_layout.addStretch(1)
        self._pill_row.setVisible(False)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._line_edit)
        layout.addWidget(self._pill_row)
        self._line_edit.textChanged.connect(self._model.set_pending_text)
        self._line_edit.returnPressed.connect(self.commit)
        self._line_edit.backspace_on_empty.connect(self._remove_last)
        self._model.filter_changed.connect(self.filter_changed.emit)

    @property
    def model(self) -> FilterModel:
        return self._model

    @property
    def keywords(self) -> list[str]:
        return self._model.keywords

    @property
    def line_edit(self) -> QtWidgets.QLineEdit:
        return self._line_edit

    def matches(self, text) -> bool:
        return self._model.matches(text)

    def set_text(self, text: str) -> None:
        self._line_edit.setText(text)

    def clear(self) -> None:
        for pill in list(self._pills):
            self._discard_pill(pill)
        self._pills = []
        self._pill_row.setVisible(False)
        self._line_edit.clear()
        self._model.set_keywords([])

    def commit(self) -> None:
        """Freeze the typed text into a pill."""
        keyword = self._line_edit.text().strip()
        if not keyword:
            return
        if keyword.lower() in [pill.keyword().lower() for pill in self._pills]:
            self._line_edit.clear()
            return
        pill = _Pill(keyword, self._pill_row)
        pill.remove_clicked.connect(self._remove_keyword)
        self._pill_layout.insertWidget(self._pill_layout.count() - 1, pill)
        self._pills.append(pill)
        self._pill_row.setVisible(True)
        self._line_edit.clear()
        self._publish()

    def _remove_keyword(self, keyword: str) -> None:
        for pill in list(self._pills):
            if pill.keyword() == keyword:
                self._pills.remove(pill)
                self._discard_pill(pill)
                break
        self._pill_row.setVisible(bool(self._pills))
        self._publish()

    def _remove_last(self) -> None:
        if self._pills:
            self._remove_keyword(self._pills[-1].keyword())

    def _discard_pill(self, pill) -> None:
        self._pill_layout.removeWidget(pill)
        pill.setParent(None)
        pill.deleteLater()

    def _publish(self) -> None:
        self._model.set_keywords([pill.keyword() for pill in self._pills])
