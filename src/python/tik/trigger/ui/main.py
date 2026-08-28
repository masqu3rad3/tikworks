"""Trigger main window."""

from __future__ import annotations

from typing import Optional

from tik.shared.ui.Qt import QtCore, QtWidgets
from tik.trigger.core import ERROR, LOG, PROGRESS, EventBus
from tik.trigger.session import EXTENSION, RigSession

from .actions_panel import ActionsPanel
from .guides_panel import GuidesPanel
from .widgets import LogWidget

FILE_FILTER = f"Trigger session (*{EXTENSION})"


class TriggerWindow(QtWidgets.QMainWindow):
    """Guides + Actions tabs, file menu, progress bar and log."""

    def __init__(self, backend, session: Optional[RigSession] = None, parent=None) -> None:
        super().__init__(parent)
        self.backend = backend
        self.session = session or RigSession(backend, events=EventBus())
        self.setWindowTitle("Trigger")
        self.resize(960, 640)
        self._build_ui()
        self._connect_events()
        self._update_title()

    # ------------------------------------------------------------------ ui
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        self.tabs = QtWidgets.QTabWidget()
        self.guides_panel = GuidesPanel(self.backend, self.session)
        self.actions_panel = ActionsPanel(self.session)
        self.tabs.addTab(self.guides_panel, "Guides")
        self.tabs.addTab(self.actions_panel, "Actions")
        layout.addWidget(self.tabs, 1)
        self.log = LogWidget()
        self.log.setMaximumHeight(140)
        layout.addWidget(self.log)
        self.setCentralWidget(central)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setMaximumWidth(240)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress)

        file_menu = self.menuBar().addMenu("File")
        self._add_action(file_menu, "New", self.new_session, "Ctrl+N")
        self._add_action(file_menu, "Open...", self.open_session, "Ctrl+O")
        self._add_action(file_menu, "Save", self.save_session, "Ctrl+S")
        self._add_action(file_menu, "Save As...", self.save_session_as, "Ctrl+Shift+S")
        file_menu.addSeparator()
        self._add_action(file_menu, "Import Guides...", self.import_guides)
        self._add_action(file_menu, "Export Guides...", self.export_guides)
        self._add_action(file_menu, "Import Actions...", self.import_actions)
        self._add_action(file_menu, "Export Actions...", self.export_actions)
        guides_menu = self.menuBar().addMenu("Guides")
        self._add_action(guides_menu, "Snapshot scene guides into session", self.snapshot_guides)
        self._add_action(guides_menu, "Restore session guides into scene", self.restore_guides)

    def _add_action(self, menu, label, slot, shortcut: Optional[str] = None) -> QtWidgets.QAction:
        action = menu.addAction(label)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    def _connect_events(self) -> None:
        events = self.session.events
        events.subscribe(LOG, self._on_log)
        events.subscribe(PROGRESS, self._on_progress)
        events.subscribe(ERROR, self._on_error)

    # -------------------------------------------------------------- events
    def _on_log(self, level: str = "info", message: str = "", **_kwargs) -> None:
        self.log.append_message(message, level)
        self.statusBar().showMessage(message, 4000)
        self._update_title()

    def _on_progress(self, current: int = 0, total: int = 0, label: str = "", **_kwargs) -> None:
        self.progress.setVisible(current < total)
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(current)
        if label:
            self.statusBar().showMessage(label)
        QtWidgets.QApplication.processEvents()

    def _on_error(self, exception=None, context: str = "", **_kwargs) -> None:
        self.log.append_message(f"{context}: {exception}", "error")
        self.progress.setVisible(False)

    def _update_title(self) -> None:
        name = self.session.file_path.name if self.session.file_path else "untitled"
        flag = "*" if self.session.is_modified else ""
        self.setWindowTitle(f"Trigger - {name}{flag}")

    # ---------------------------------------------------------------- file
    def _confirm_discard(self) -> bool:
        if not self.session.is_modified:
            return True
        return self.ask_discard()

    def ask_discard(self) -> bool:
        """Modal question; replaced in tests to avoid blocking dialogs."""
        answer = QtWidgets.QMessageBox.question(
            self, "Unsaved changes", "Discard unsaved changes?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        return answer == QtWidgets.QMessageBox.Yes

    def new_session(self) -> None:
        if not self._confirm_discard():
            return
        self.session.new()
        self.actions_panel.refresh()
        self._update_title()

    def open_session(self, path: Optional[str] = None) -> None:
        if not path:
            if not self._confirm_discard():
                return
            path, _filter = QtWidgets.QFileDialog.getOpenFileName(self, "Open session", "", FILE_FILTER)
        if not path:
            return
        self.session.load(path)
        self.actions_panel.refresh()
        self._update_title()

    def save_session(self) -> None:
        if self.session.file_path is None:
            self.save_session_as()
            return
        self.session.save()
        self._update_title()

    def save_session_as(self, path: Optional[str] = None) -> None:
        if not path:
            path, _filter = QtWidgets.QFileDialog.getSaveFileName(self, "Save session", "", FILE_FILTER)
        if not path:
            return
        self.session.save(path)
        self._update_title()

    def _pick_open(self, title: str) -> str:
        path, _filter = QtWidgets.QFileDialog.getOpenFileName(self, title, "", FILE_FILTER)
        return path

    def _pick_save(self, title: str) -> str:
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(self, title, "", FILE_FILTER)
        return path

    def import_guides(self, path: Optional[str] = None) -> None:
        path = path or self._pick_open("Import guides")
        if path:
            self.session.import_guides(path)
            self._update_title()

    def export_guides(self, path: Optional[str] = None) -> None:
        path = path or self._pick_save("Export guides")
        if path:
            self.snapshot_guides()
            self.session.export_guides(path)

    def import_actions(self, path: Optional[str] = None) -> None:
        path = path or self._pick_open("Import actions")
        if path:
            self.session.import_actions(path)
            self.actions_panel.refresh()
            self._update_title()

    def export_actions(self, path: Optional[str] = None) -> None:
        path = path or self._pick_save("Export actions")
        if path:
            self.session.export_actions(path)

    # -------------------------------------------------------------- guides
    def snapshot_guides(self) -> None:
        self.session.snapshot_guides()
        self._update_title()

    def restore_guides(self) -> None:
        self.session.restore_guides()
        self.guides_panel.refresh()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
