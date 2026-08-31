"""Trigger main window: a dockable host for modes — Trigger and Guide Designer.

Each mode is a bundle of three plain widgets (a ``QMenuBar``, a content
widget, a status strip) held in three parallel stacks. The mode tab bar and
the menu stack go in together through ``setMenuWidget``, which is what puts
the tabs *above* the menus. Nothing is installed with ``setMenuBar`` or
``setStatusBar``, so Qt never takes ownership of a bundle widget.

The two modes bind the same keys (Ctrl+B/S/O/N/D/L, Tab, F2) and never
collide: a ``WindowShortcut`` only matches while its action's widget is
visible, and the inactive mode's menu bar sits in a hidden stack page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tik.shared.ui import theme
from tik.shared.ui.maya_window import HAS_MAYA, MayaToolWindow
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.status import StatusFields
from tik.trigger.core import ERROR, LOG, EventBus, versioning
from tik.trigger.core.document import EXTENSION
from tik.trigger.session import Session

from .session_view import SessionView
from .widgets import LogWidget

FILE_FILTER = f"Trigger session (*{EXTENSION})"
VERSION = "0.2.0"
MAX_RECENT = 8
TRIGGER_MODE = 0
DESIGNER_MODE = 1


def _holder() -> QtWidgets.QWidget:
    """An empty widget whose zero-margin layout a mode bundle drops into."""
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    return widget


class TriggerWindow(MayaToolWindow):
    WINDOW_NAME = "TriggerWindow"

    def __init__(self, parent=None, file_browser=None, designer_factory=None) -> None:
        super().__init__(parent)
        self.file_browser = file_browser
        self.events = EventBus()
        self.designer_factory = designer_factory
        # one Designer per session view: each session owns its guides, so
        # each owns a Designer and a checkout of the scene
        self._designers: dict = {}
        self.recent_files: list[str] = []
        self.setWindowTitle(f"Trigger {VERSION}")
        self.resize(1180, 720)
        self.setMinimumWidth(900)
        self._build_shell()
        self._build_trigger_mode()
        self._build_designer_mode()
        self.mode_bar.currentChanged.connect(self._activate_mode)
        theme.apply(self)
        self.events.subscribe(LOG, self._on_log)
        self.events.subscribe(ERROR, self._on_error)
        self.new_session()

    # ------------------------------------------------------------------ ui
    def _build_shell(self) -> None:
        self.mode_bar = QtWidgets.QTabBar()
        self.mode_bar.setDrawBase(False)
        self.mode_bar.setExpanding(False)
        self.menu_stack = QtWidgets.QStackedWidget()
        header = QtWidgets.QWidget()
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        header_layout.addWidget(self.mode_bar)
        header_layout.addWidget(self.menu_stack)
        self.setMenuWidget(header)  # the tabs sit above the menus
        self.pages = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.pages)
        self.status_stack = QtWidgets.QStackedWidget()
        self.statusBar().addWidget(self.status_stack, 1)
        self._mode_menus: dict[int, QtWidgets.QMenuBar] = {}
        self._active_mode = TRIGGER_MODE
        self.log = LogWidget()
        self.log_dock = QtWidgets.QDockWidget("Log", self)
        self.log_dock.setObjectName("TriggerLogDock")
        self.log_dock.setWidget(self.log)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.log_dock)
        self.log_dock.hide()

    def add_mode(self, title: str, menu_widget, content, status_widget) -> int:
        """Register one mode; the three stacks stay index-aligned."""
        index = self.mode_bar.addTab(title)
        self.menu_stack.insertWidget(index, menu_widget)
        self.pages.insertWidget(index, content)
        self.status_stack.insertWidget(index, status_widget)
        return index

    @property
    def menu_bar(self) -> Optional[QtWidgets.QMenuBar]:
        return self._mode_menus.get(self._active_mode)

    def _build_trigger_mode(self) -> None:
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.trigger_menus = QtWidgets.QMenuBar()
        self._build_menus(self.trigger_menus)
        self.trigger_status_strip = QtWidgets.QWidget()
        self._build_status(self.trigger_status_strip)
        self._mode_menus[TRIGGER_MODE] = self.trigger_menus
        self.add_mode("Trigger", self.trigger_menus, self.tabs, self.trigger_status_strip)

    def _build_designer_mode(self) -> None:
        """Register the tab now, build the Designer on first use.

        ``GuideDesigner`` constructs a ``GuideScene``, which imports Maya, so it
        cannot be built at window startup — the UI tests run without Maya.
        """
        self.designer_menus = QtWidgets.QStackedWidget()
        self.designer_pages = QtWidgets.QStackedWidget()
        self.designer_status = QtWidgets.QStackedWidget()
        for stack in (self.designer_menus, self.designer_pages, self.designer_status):
            stack.addWidget(_holder())  # shown before any Designer is built
        self.add_mode("Guide Designer", self.designer_menus,
                      self.designer_pages, self.designer_status)

    def _activate_mode(self, index: int) -> None:
        if index == DESIGNER_MODE:
            self._show_active_designer()
        self._active_mode = index
        self.menu_stack.setCurrentIndex(index)
        self.pages.setCurrentIndex(index)
        self.status_stack.setCurrentIndex(index)
        self._update_title()

    def _action(self, menu, text, slot, shortcut: Optional[str] = None, checkable: bool = False):
        action = menu.addAction(text)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        if checkable:
            action.setCheckable(True)
        return action

    def _build_menus(self, bar) -> None:
        file_menu = bar.addMenu("&File")
        self._action(file_menu, "New Session", self.new_session, "Ctrl+N")
        self._action(file_menu, "Open…", self.open_session, "Ctrl+O")
        self.recent_menu = file_menu.addMenu("Open Recent")
        file_menu.addSeparator()
        self._action(file_menu, "Save", self.save_session, "Ctrl+S")
        self._action(file_menu, "Save As…", self.save_session_as, "Ctrl+Shift+S")
        self._action(file_menu, "Increment Version", self.increment_session, "Ctrl+Alt+S")
        file_menu.addSeparator()
        self._action(file_menu, "Import Actions…", self.import_actions)
        self._action(file_menu, "Export Actions…", self.export_actions)
        file_menu.addSeparator()
        self._action(file_menu, "Close Tab", lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W")
        self._action(file_menu, "Quit", self.close, "Ctrl+Q")

        edit_menu = bar.addMenu("&Edit")
        self._action(edit_menu, "Undo", self.undo, "Ctrl+Z")
        self._action(edit_menu, "Redo", self.redo, "Ctrl+Y")
        edit_menu.addSeparator()
        self._action(edit_menu, "Add Action…", lambda: self._view_call("show_palette"), "Tab")
        self._action(edit_menu, "Add Child Action…", lambda: self._view_call("add_child_via_palette"))
        self._action(edit_menu, "Duplicate", lambda: self._view_call("duplicate_current"), "Ctrl+D")
        self._action(edit_menu, "Rename", lambda: self._view_call("rename_current"), "F2")
        self._action(edit_menu, "Delete", lambda: self._view_call("remove_current"), "Del")
        self._action(edit_menu, "Enable / Disable", lambda: self._view_call("toggle_current"), "Ctrl+E")

        session_menu = bar.addMenu("&Session")
        self._action(session_menu, "Build Rig", lambda: self._view_call("build"), "Ctrl+B")
        self._action(session_menu, "Build Until Here", lambda: self._view_call("build_until", self._current_path()), "Ctrl+Shift+B")
        self._action(session_menu, "Run Step", lambda: self._view_call("run_step", self._current_path()), "Ctrl+R")
        session_menu.addSeparator()
        self._action(session_menu, "Validate", self.validate_session)
        self._action(session_menu, "Clear Statuses", lambda: self._view_call("clear_statuses"))

        tools_menu = bar.addMenu("&Tools")
        self._action(tools_menu, "Guide Designer", lambda: self.open_guide_designer(), "Ctrl+G")
        tools_menu.addSeparator()
        self.shelf_action = self._action(tools_menu, "Show Action Shelf", self.toggle_shelf, "Ctrl+Shift+A", checkable=True)
        self.shelf_action.setChecked(True)
        self.log_action = self._action(tools_menu, "Show Log", self.toggle_log, "Ctrl+L", checkable=True)
        tools_menu.addSeparator()
        self._action(tools_menu, "Settings…", self.open_settings)

        help_menu = bar.addMenu("&Help")
        self._action(help_menu, "Documentation", self.open_docs)
        self._action(help_menu, "About Trigger", self.about)
        self._update_recent_menu()

    def _build_status(self, strip) -> None:
        self.status = StatusFields(strip, ("references", "maya", "version"))
        maya_text = "Maya"
        if HAS_MAYA:
            try:
                from maya import cmds

                maya_text = f"Maya {cmds.about(version=True)}"
            except Exception:  # noqa: BLE001
                pass
        self.status.set("maya", maya_text)
        self.status.set("version", f"tik.trigger {VERSION}")
        self.status.set_activity("Ready")

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

    def _view_call(self, method: str, *args):
        view = self.current_view
        if view is not None:
            return getattr(view, method)(*args)
        return None

    def _current_path(self) -> Optional[str]:
        view = self.current_view
        return view.current_path() if view else None

    def add_session(self, session: Session) -> SessionView:
        view = SessionView(session, file_browser=self.file_browser)
        view.title_changed.connect(self._update_title)
        view.open_guides_requested.connect(self.open_guide_designer)
        view.activity.connect(self.status.set_activity)
        index = self.tabs.addTab(view, session.name)
        self.tabs.setCurrentIndex(index)
        self._update_title()
        return view

    def new_session(self) -> SessionView:
        return self.add_session(Session(events=self.events))

    def open_session(self, path: Optional[str] = None) -> Optional[SessionView]:
        if not path:
            path, _f = QtWidgets.QFileDialog.getOpenFileName(self, "Open session", "", FILE_FILTER)
        if not path:
            return None
        for view in self.views:
            if view.session.file_path and Path(view.session.file_path) == Path(path):
                self.tabs.setCurrentWidget(view)
                return view
        session = Session.open(path, events=self.events)
        view = self.add_session(session)
        for item in [v for v in self.views if v is not view and not v.session.actions and not v.session.file_path]:
            self.tabs.removeTab(self.tabs.indexOf(item))
        self._remember(path)
        return view

    def save_session(self) -> None:
        session = self.session
        if session is None:
            return
        if session.file_path is None:
            self.save_session_as()
            return
        session.save()
        self._remember(str(session.file_path))
        self._update_title()

    def save_session_as(self, path: Optional[str] = None) -> None:
        session = self.session
        if session is None:
            return
        if not path:
            path, _f = QtWidgets.QFileDialog.getSaveFileName(self, "Save session", "", FILE_FILTER)
        if not path:
            return
        session.save(path)
        self._remember(str(session.file_path))
        self._update_title()

    def increment_session(self) -> None:
        session = self.session
        if session is None:
            return
        if session.file_path is None:
            self.save_session_as()
            return
        session.increment()
        self._remember(str(session.file_path))
        self._update_title()

    def import_actions(self, path: Optional[str] = None) -> None:
        session = self.session
        if session is None:
            return
        if not path:
            path, _f = QtWidgets.QFileDialog.getOpenFileName(self, "Import actions", "", FILE_FILTER)
        if not path:
            return
        from tik.trigger.core.document import Document

        for node in Document.load(path).actions:
            session.document.add(node)
        session._touch()
        self._view_call("refresh")

    def export_actions(self, path: Optional[str] = None) -> None:
        session = self.session
        if session is None:
            return
        if not path:
            path, _f = QtWidgets.QFileDialog.getSaveFileName(self, "Export actions", "", FILE_FILTER)
        if not path:
            return
        session.document.save(path if path.endswith(EXTENSION) else path + EXTENSION)

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
        self._drop_designer(view)
        self.tabs.removeTab(index)
        if self.tabs.count() == 0:
            self.new_session()
        return True

    # ----------------------------------------------------------- commands
    def undo(self) -> None:
        session = self.session
        if session is not None and session.undo():
            self._view_call("refresh")

    def redo(self) -> None:
        session = self.session
        if session is not None and session.redo():
            self._view_call("refresh")

    def validate_session(self) -> None:
        session = self.session
        if session is None:
            return
        problems = session.validate()
        if problems:
            for problem in problems:
                self.events.log(problem, level="warning")
            self.status.set_activity(f"{len(problems)} problem(s) — see log")
            self.log_dock.show()
            self.log_action.setChecked(True)
        else:
            self.status.set_activity("Session valid")

    def toggle_shelf(self) -> None:
        view = self.current_view
        if view is not None:
            view.set_shelf_visible(not view.shelf_visible)
            self.shelf_action.setChecked(view.shelf_visible)

    def toggle_log(self) -> None:
        self.log_dock.setVisible(not self.log_dock.isVisible())
        self.log_action.setChecked(self.log_dock.isVisible())

    def open_settings(self) -> None:
        QtWidgets.QMessageBox.information(self, "Settings", "Settings are not available yet.")

    def open_docs(self) -> None:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl("https://github.com/masqu3rad3/tikworks"))

    def about(self) -> None:
        QtWidgets.QMessageBox.about(self, "About Trigger", f"Trigger {VERSION}\nModular rigging on tik.maya.")

    # -------------------------------------------------------------- recent
    def _remember(self, path: str) -> None:
        path = str(Path(path))
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        del self.recent_files[MAX_RECENT:]
        self._update_recent_menu()

    def _update_recent_menu(self) -> None:
        self.recent_menu.clear()
        if not self.recent_files:
            self.recent_menu.addAction("(none)").setEnabled(False)
        for path in self.recent_files:
            self.recent_menu.addAction(path, lambda checked=False, p=path: self.open_session(p))

    # -------------------------------------------------------------- title
    def _update_title(self) -> None:
        for index, view in enumerate(self.views):
            self.tabs.setTabText(index, view.session.name + ("*" if view.session.is_modified else ""))
        if self._active_mode == DESIGNER_MODE and self.active_designer is not None:
            self.setWindowTitle(f"Trigger {VERSION} — {self.active_designer.title}")
            return
        session = self.session
        if session is None:
            self.setWindowTitle(f"Trigger {VERSION}")
            return
        flag = "*" if session.is_modified else ""
        self.setWindowTitle(f"Trigger {VERSION} — {session.name}{flag}")
        state = ""
        if session.file_path is not None:
            _stem, version, _suffix = versioning.parse(session.file_path)
            if version is not None:
                latest = versioning.latest_version(session.file_path)
                state = "latest" if latest is None or versioning.parse(latest)[1] <= version else f"older · latest v{versioning.parse(latest)[1]:03d}"
        references = sum(1 for handle in session.walk() if handle.type == "reference")
        self.status.set("references", f"{references} reference(s)" + (f" · {state}" if state else ""))

    # ------------------------------------------------------------ guides
    def designer_for(self, view):
        """The Guide Designer for one session view, built on first use."""
        key = id(view)
        designer = self._designers.get(key)
        if designer is not None:
            return designer
        if self.designer_factory is not None:
            designer = self.designer_factory()
        else:
            from .designer import GuideDesigner

            designer = GuideDesigner(events=self.events, file_browser=self.file_browser)
        designer.title_changed.connect(
            lambda title, owner=designer: self._on_designer_title(owner, title)
        )
        self._designers[key] = designer
        self.designer_menus.addWidget(designer.menu_bar)
        self.designer_pages.addWidget(designer)
        self.designer_status.addWidget(designer.status_strip)
        return designer

    def _on_designer_title(self, owner, title: str) -> None:
        """Only the tab in front gets to name the mode."""
        if owner is not self.active_designer:
            return
        self.mode_bar.setTabText(DESIGNER_MODE, title)
        self._update_title()

    @property
    def active_designer(self):
        """The Designer of the active session tab, or None before one is built."""
        view = self.current_view
        return self._designers.get(id(view)) if view is not None else None

    def current_menu_bar(self):
        """The menu bar the window is showing for the active mode."""
        if self._active_mode == DESIGNER_MODE:
            designer = self.active_designer
            if designer is not None:
                return designer.menu_bar
        return self._mode_menus.get(self._active_mode)

    def _show_active_designer(self):
        """Put the active tab's Designer in front, building it if needed."""
        view = self.current_view
        if view is None:
            return None
        designer = self.designer_for(view)
        self.designer_menus.setCurrentWidget(designer.menu_bar)
        self.designer_pages.setCurrentWidget(designer)
        self.designer_status.setCurrentWidget(designer.status_strip)
        self._mode_menus[DESIGNER_MODE] = designer.menu_bar
        self.mode_bar.setTabText(DESIGNER_MODE, designer.title)
        self._update_title()
        return designer

    def _on_tab_changed(self, _index: int) -> None:
        if self._active_mode == DESIGNER_MODE:
            self._show_active_designer()
        self._update_title()

    def _drop_designer(self, view) -> None:
        """Tear down and forget a closed tab's Designer."""
        designer = self._designers.pop(id(view), None)
        if designer is None:
            return
        designer.teardown()
        for stack, widget in (
            (self.designer_menus, designer.menu_bar),
            (self.designer_pages, designer),
            (self.designer_status, designer.status_strip),
        ):
            stack.removeWidget(widget)
            widget.setParent(None)

    def open_guide_designer(self, guides_path: str = ""):
        designer = self._show_active_designer()
        if designer is not None and guides_path:
            designer.set_file(guides_path)
        self.mode_bar.setCurrentIndex(DESIGNER_MODE)
        return designer

    # -------------------------------------------------------------- events
    def _on_log(self, level: str = "info", message: str = "", **_kw) -> None:
        self.log.append_message(message, level)
        self.status.set_activity(message)
        self._update_title()

    def _on_error(self, exception=None, context: str = "", **_kw) -> None:
        self.log.append_message(f"{context}: {exception}", "error")
        self.log_dock.show()
        self.log_action.setChecked(True)

    def closeEvent(self, event) -> None:  # noqa: N802
        for view in self.views:
            if view.session.is_modified and not self.ask_discard(view.session):
                event.ignore()
                return
        for designer in list(self._designers.values()):
            designer.teardown()
        super().closeEvent(event)


def show(dockable: bool = True) -> TriggerWindow:
    """Open (or re-open) the single Trigger window."""
    import tik.trigger as trigger

    trigger.load_plugins()
    TriggerWindow.teardown_workspace_control()
    window = TriggerWindow()
    window.show_tool(dockable=dockable)
    return window
