"""Read-only viewer for the selected script action's file and inline code.

It never edits: editing is external (spec 2026-09-06, decision 4). A
``QFileSystemWatcher`` reloads the view when the file changes on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tik.shared.io import open_external
from tik.shared.ui.feedback import Feedback
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.actions.script.script import editor_command

PLACEHOLDER = "Select a script action."
RULE = "\n\n# " + "-" * 60 + "  inline code\n\n"


class ScriptViewer(QtWidgets.QWidget):
    """Path header, Open button, monospace read-only text."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)
        header = QtWidgets.QHBoxLayout()
        self.path_label = QtWidgets.QLabel("")
        self.path_label.setObjectName("PanelSubtitle")
        self.open_button = QtWidgets.QToolButton()
        self.open_button.setText("Open")
        self.open_button.setToolTip("Open the file in the external editor")
        self.open_button.setEnabled(False)
        header.addWidget(self.path_label, 1)
        header.addWidget(self.open_button)
        layout.addLayout(header)
        self.text = QtWidgets.QPlainTextEdit()
        self.text.setObjectName("ScriptViewerText")
        self.text.setReadOnly(True)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        font.setStyleHint(QtGui.QFont.Monospace)
        font.setFixedPitch(True)
        self.text.setFont(font)
        layout.addWidget(self.text, 1)
        self._watcher = QtCore.QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(lambda _path: self._reload())
        self._path: Optional[Path] = None
        self._code = ""
        self.open_button.clicked.connect(self._open)
        self.clear()

    # ------------------------------------------------------------- binding
    def show_handle(self, handle, base_dir: str) -> None:
        """Show ``handle``'s script file and code, or the placeholder."""
        self._unwatch()
        if handle is None or handle.type != "script":
            self.clear()
            return
        settings = dict(handle.settings)
        raw = settings.get("file_path") or ""
        self._code = settings.get("code") or ""
        self._path = None
        if raw:
            path = Path(raw)
            if not path.is_absolute() and base_dir:
                path = Path(base_dir) / path
            self._path = path
        self.open_button.setEnabled(self._path is not None)
        self._reload()

    def clear(self) -> None:
        """The empty state."""
        self._unwatch()
        self._path = None
        self._code = ""
        self.path_label.setText("")
        self.open_button.setEnabled(False)
        self.text.setPlainText(PLACEHOLDER)

    # ------------------------------------------------------------- content
    def _unwatch(self) -> None:
        files = self._watcher.files()
        if files:
            self._watcher.removePaths(files)

    def _watch(self) -> None:
        if self._path is None or not self._path.exists():
            return
        if str(self._path) not in self._watcher.files():
            # editors that replace the file drop the watch: re-add it
            self._watcher.addPath(str(self._path))

    def _reload(self) -> None:
        parts = []
        if self._path is not None:
            if self._path.exists():
                self.path_label.setText(str(self._path))
                parts.append(self._path.read_text(encoding="utf-8", errors="replace"))
                self._watch()
            else:
                self.path_label.setText(f"{self._path}  (missing)")
        else:
            self.path_label.setText("inline code only" if self._code else "")
        if self._code:
            parts.append((RULE if parts else "") + self._code)
        self.text.setPlainText("".join(parts))

    def _open(self) -> None:
        if self._path is None:
            return
        try:
            open_external(self._path, editor_command())
        except OSError as error:
            Feedback(self).pop_warning(
                "Open script", f"Could not open {self._path}", str(error)
            )

    # -------------------------------------------------------------- events
    def hideEvent(self, event) -> None:  # noqa: N802 - Qt style
        # never hold a handle on a file the rigger may be renaming
        self._unwatch()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._path is not None:
            self._reload()
