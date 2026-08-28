"""Small shared widgets for the Trigger window."""

from __future__ import annotations

from tik.shared.ui.Qt import QtCore, QtWidgets


class LogWidget(QtWidgets.QPlainTextEdit):
    """Read-only log fed by the event bus."""

    LEVEL_COLORS = {"warning": "#d9a400", "error": "#e05555"}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(2000)

    def append_message(self, message: str, level: str = "info") -> None:
        color = self.LEVEL_COLORS.get(level)
        text = message if not color else f'<span style="color:{color}">{message}</span>'
        self.appendHtml(text)


class NameEdit(QtWidgets.QLineEdit):
    """Line edit that emits ``renamed(old, new)`` on commit when the text changed."""

    renamed = QtCore.Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._original = ""
        self.editingFinished.connect(self._commit)

    def set_name(self, name: str) -> None:
        self._original = name
        self.setText(name)

    def _commit(self) -> None:
        new = self.text().strip()
        if new and new != self._original:
            old, self._original = self._original, new
            self.renamed.emit(old, new)
