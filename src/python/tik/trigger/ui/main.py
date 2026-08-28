"""Trigger main window: tabs of sessions, file menu, log, Guide Designer entry."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tik.shared.ui import theme
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.core import ERROR, LOG, EventBus
from tik.trigger.core.document import EXTENSION
from tik.trigger.handler import Session

from .session_view import SessionView
from .widgets import LogWidget

FILE_FILTER = f"Trigger session (*{EXTENSION})"


class TriggerWindow(QtWidgets.QMainWindow):
    def __init__(self, backend, parent=None, file_browser=None) -> None:
        super().__init__(parent)
        self.backend = backend
        self.file_browser = file_browser
        self.events = EventBus()
        self._guide_designer = None
        self.setWindowTitle("Trigger")
        self.resize(1100, 700)
        theme.apply(self)
        self._build_ui()
        self.events.subscribe(LOG, self._on_log)
        self.events.subscribe(ERROR, self._on_error)
        self.new_session()

    # ------------------------------------------------------------------ ui
    def _build_ui(self) -> None:
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(lambda _index: self._update_title())
        self.setCentralWidget(self.tabs)

        toolbar = self.addToolBar("Session")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self._add(toolbar, "New", self.new_session, "Ctrl+N")
        self._add(toolbar, "Open…", self.open_session, "Ctrl+O")
        self._add(toolbar, "Save", self.save_session, "Ctrl+S")
        self._add(toolbar, "Save As…", self.save_session_as, "Ctrl+Shift+S")
        self._add(toolbar, "Increment", self.increment_session, "Ctrl+Alt+S")
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        self._add(toolbar, "Shelf", self.toggle_shelf, "Ctrl+B")
        self.designer_action = self._add(toolbar, "Guide Designer", lambda: self.open_guide_designer(), "Ctrl+G")

        self.log = LogWidget()
        dock = QtWidgets.QDockWidget("Log", self)
        dock.setWidget(self.log)
        dock.setFeatures(QtWidgets.QDockWidget.DockWidgetClosable | QtWidgets.QDockWidget.DockWidgetMovable)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, dock)
        self.log_dock = dock
        self.statusBar()

    def _add(self, toolbar, label, slot, shortcut: Optional[str] = None) -> QtGui.QAction:
        action = toolbar.addAction(label)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    # ---------------------------------------------------------------- tabs
    @property
    def views(self) -> list[SessionView]:
        return [self.tabs.widget(index) for index in range(self.tabs.count())]

    @property
    def current_view(self) -> Optional[SessionView]:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, SessionView) else None

    @property
    def session(self) -> Optional[Session]:
        view = self.current_view
        return view.session if view else None

    def add_session(self, session: Session) -> SessionView:
        view = SessionView(session, file_browser=self.file_browser)
        view.title_changed.connect(self._update_title)
        view.open_guides_requested.connect(self.open_guide_designer)
        index = self.tabs.addTab(view, session.name)
        self.tabs.setCurrentIndex(index)
        self._update_title()
        return view

    def new_session(self) -> SessionView:
        return self.add_session(Session(self.backend, events=self.events))

    def open_session(self, path: Optional[str] = None) -> Optional[SessionView]:
        if not path:
            path, _filter = QtWidgets.QFileDialog.getOpenFileName(self, "Open session", "", FILE_FILTER)
        if not path:
            return None
        for view in self.views:
            if view.session.file_path and Path(view.session.file_path) == Path(path):
                self.tabs.setCurrentWidget(view)
                return view
        session = Session.open(path, backend=self.backend, events=self.events)
        view = self.add_session(session)
        empty = [item for item in self.views if item is not view and not item.session.actions and not item.session.file_path]
        for item in empty:
            self.tabs.removeTab(self.tabs.indexOf(item))
        return view

    def save_session(self) -> None:
        session = self.session
        if session is None:
            return
        if session.file_path is None:
            self.save_session_as()
            return
        session.save()
        self._update_title()

    def save_session_as(self, path: Optional[str] = None) -> None:
        session = self.session
        if session is None:
            return
        if not path:
            path, _filter = QtWidgets.QFileDialog.getSaveFileName(self, "Save session", "", FILE_FILTER)
        if not path:
            return
        session.save(path)
        self._update_title()

    def increment_session(self) -> None:
        session = self.session
        if session is None:
            return
        if session.file_path is None:
            self.save_session_as()
            return
        session.increment()
        self._update_title()

    def ask_discard(self, session: Session) -> bool:
        answer = QtWidgets.QMessageBox.question(
            self, "Unsaved changes", f"Discard unsaved changes in {session.name}?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        return answer == QtWidgets.QMessageBox.Yes

    def close_tab(self, index: int) -> bool:
        view = self.tabs.widget(index)
        if isinstance(view, SessionView) and view.session.is_modified and not self.ask_discard(view.session):
            return False
        self.tabs.removeTab(index)
        if self.tabs.count() == 0:
            self.new_session()
        return True

    def toggle_shelf(self) -> None:
        view = self.current_view
        if view is not None:
            view.shelf.set_collapsed(not view.shelf.collapsed)

    def _update_title(self) -> None:
        for index, view in enumerate(self.views):
            flag = "*" if view.session.is_modified else ""
            self.tabs.setTabText(index, f"{view.session.name}{flag}")
        session = self.session
        self.setWindowTitle(f"Trigger — {session.name}{'*' if session and session.is_modified else ''}" if session else "Trigger")

    # ------------------------------------------------------------ guides
    def open_guide_designer(self, guides_path: str = ""):
        from .guide_designer import GuideDesigner

        if self._guide_designer is None:
            self._guide_designer = GuideDesigner(self.backend, parent=self, events=self.events, file_browser=self.file_browser)
        if guides_path:
            self._guide_designer.set_file(guides_path)
        self._guide_designer.show()
        self._guide_designer.raise_()
        return self._guide_designer

    # -------------------------------------------------------------- events
    def _on_log(self, level: str = "info", message: str = "", **_kw) -> None:
        self.log.append_message(message, level)
        self.statusBar().showMessage(message, 4000)
        self._update_title()

    def _on_error(self, exception=None, context: str = "", **_kw) -> None:
        self.log.append_message(f"{context}: {exception}", "error")

    def closeEvent(self, event) -> None:  # noqa: N802
        for view in self.views:
            if view.session.is_modified and not self.ask_discard(view.session):
                event.ignore()
                return
        event.accept()
