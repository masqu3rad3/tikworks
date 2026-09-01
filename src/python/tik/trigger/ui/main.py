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
from tik.shared.ui.scene_watcher import SceneWatcher
from tik.shared.ui.status import StatusFields
from tik.trigger.core import ERROR, LOG, EventBus, versioning
from tik.trigger.core.exceptions import SessionError
from tik.trigger.core.document import EXTENSION
from tik.trigger.session import Session

from .designer.widgets import SCENE_NODE
from .session_view import DESIGNER_TAB, SessionView
from .widgets import LogWidget

FILE_FILTER = f"Trigger session (*{EXTENSION})"
VERSION = "0.2.0"
MAX_RECENT = 8


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
        # which session tab's guides are currently in the scene
        self._checked_out_view = None
        self.recent_files: list[str] = []
        self.setWindowTitle(f"Trigger {VERSION}")
        self.resize(1180, 720)
        self.setMinimumWidth(900)
        self._build_shell()
        self._build_tabs()
        theme.apply(self)
        self.events.subscribe(LOG, self._on_log)
        self.events.subscribe(ERROR, self._on_error)
        self.new_session()
        self._sync_menu_state()

    # ------------------------------------------------------------------ ui
    def _build_shell(self) -> None:
        """One menu bar over the session tabs.

        The session is the outer container: its guides live in the ``.tr``, so
        Session and Guide Designer are two views of one document and sit inside
        the tab rather than above it.
        """
        self.menus = QtWidgets.QMenuBar()
        self._build_menus(self.menus)
        self.setMenuWidget(self.menus)
        self.status_strip = QtWidgets.QWidget()
        self._build_status(self.status_strip)
        self.statusBar().addWidget(self.status_strip, 1)
        self.log = LogWidget()
        self.log_dock = QtWidgets.QDockWidget("Log", self)
        self.log_dock.setObjectName("TriggerLogDock")
        self.log_dock.setWidget(self.log)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.log_dock)
        self.log_dock.hide()

    @property
    def menu_bar(self) -> QtWidgets.QMenuBar:
        """The window's one menu bar."""
        return self.menus

    def _build_tabs(self) -> None:
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

    def _action(self, menu, text, slot, shortcut: Optional[str] = None, checkable: bool = False):
        action = menu.addAction(text)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        if checkable:
            action.setCheckable(True)
        return action

    def _build_menus(self, bar) -> None:
        # Built with the bar as their C++ parent, not via ``bar.addMenu(str)``:
        # that hands ownership to Python, and the menu dies with the local that
        # held it -- leaving the bar showing titles backed by dead objects.
        self._menus: dict = {}

        def add_menu(title: str):
            found = QtWidgets.QMenu(title, bar)
            bar.addMenu(found)
            self._menus[title] = found
            return found

        file_menu = add_menu("&File")
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
        # a .trg is a guide *library* now, not this session's document, so it
        # gets no save shortcut -- Ctrl+S saves the session, guides included
        self._action(file_menu, "Import Guides…", lambda: self._designer_call("import_file"))
        self._action(file_menu, "Export Guides…", lambda: self._designer_call("export_file", ask=True))
        file_menu.addSeparator()
        self._action(file_menu, "Close Tab", lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W")
        self._action(file_menu, "Quit", self.close, "Ctrl+Q")

        # One Edit menu for both views: the verbs mean the same thing, so they
        # act on whichever of the two is in front rather than fighting over
        # Ctrl+D / F2 / Del.
        edit_menu = add_menu("&Edit")
        self._action(edit_menu, "Undo", self.undo, "Ctrl+Z")
        self._action(edit_menu, "Redo", self.redo, "Ctrl+Y")
        edit_menu.addSeparator()
        self._action(edit_menu, "Add…", lambda: self._either("show_palette", "show_palette"), "Tab")
        self._action(edit_menu, "Add Child Action…", lambda: self._view_call("add_child_via_palette"))
        self._action(edit_menu, "Duplicate", lambda: self._either("duplicate_current", "duplicate_current"), "Ctrl+D")
        self._action(edit_menu, "Rename", lambda: self._either("rename_current", "rename_current"), "F2")
        self._action(edit_menu, "Delete", lambda: self._either("remove_current", "delete_current"), "Del")
        self._action(edit_menu, "Enable / Disable", lambda: self._view_call("toggle_current"), "Ctrl+E")

        session_menu = add_menu("&Session")
        self._action(session_menu, "Build Rig", lambda: self._view_call("build"), "Ctrl+B")
        self._action(session_menu, "Build Until Here", lambda: self._view_call("build_until", self._current_path()), "Ctrl+Shift+B")
        self._action(session_menu, "Run Step", lambda: self._view_call("run_step", self._current_path()), "Ctrl+R")
        session_menu.addSeparator()
        self._action(session_menu, "Validate", self.validate_session)
        self._action(session_menu, "Clear Statuses", lambda: self._view_call("clear_statuses"))

        guides_menu = add_menu("&Guides")
        self.guides_menu_action = guides_menu.menuAction()
        self._action(guides_menu, "Add Module…", lambda: self._designer_call("show_palette"))
        self._action(guides_menu, "Add Scene Nodes", lambda: self._designer_call("create_guides", SCENE_NODE))
        guides_menu.addSeparator()
        self._action(guides_menu, "Select Root", lambda: self._designer_call("select_root"))
        self._action(guides_menu, "Select All Guides", lambda: self._designer_call("select_current"))
        self._action(guides_menu, "Mirror", lambda: self._designer_call("mirror_current"), "Ctrl+M")
        guides_menu.addSeparator()
        self._action(guides_menu, "Connect Input…", lambda: self._designer_call("connect_dialog"))
        self._action(guides_menu, "Disconnect Primary Input", lambda: self._designer_call("disconnect_primary"))
        self._action(guides_menu, "Sever Connections", lambda: self._designer_call("sever_current"), "Ctrl+Shift+D")
        guides_menu.addSeparator()
        self._action(guides_menu, "Build Selected Guides", lambda: self._designer_call("test_build"))
        self._action(guides_menu, "Build All Guides", lambda: self._designer_call("test_build", True))
        guides_menu.addSeparator()
        # The four verbs that cross the session/scene line, together: pull from
        # the scene, rebuild from the scene, wipe the scene.
        self._action(guides_menu, "Sync From Scene", lambda: self._designer_call("sync_now"), "F6")
        self.auto_sync_action = self._action(
            guides_menu, "Auto Sync",
            lambda: self._designer_call("set_auto_sync", self.auto_sync_action.isChecked()),
            checkable=True,
        )
        self.auto_sync_action.setChecked(True)
        self._action(
            guides_menu, "Snapshot Guides From Scene…",
            lambda: self._designer_call("snapshot_guides"),
        )
        guides_menu.addSeparator()
        self._action(guides_menu, "Clear Scene Guides", lambda: self._designer_call("clear_guides"))
        layout_menu = QtWidgets.QMenu("Layout", guides_menu)
        guides_menu.addMenu(layout_menu)
        self._menus["Layout"] = layout_menu
        self._action(layout_menu, "Auto Layout", lambda: self._graph_call("auto_layout"), "Ctrl+L")
        self._action(layout_menu, "Fit Graph", lambda: self._graph_call("fit"), "F")
        layout_menu.addSeparator()
        self._action(layout_menu, "Collapse: Header Only", lambda: self._graph_call("set_selected_mode", 0), "1")
        self._action(layout_menu, "Collapse: Connected Plugs", lambda: self._graph_call("set_selected_mode", 1), "2")
        self._action(layout_menu, "Collapse: Everything", lambda: self._graph_call("set_selected_mode", 2), "3")
        layout_menu.addSeparator()
        # Was "Refresh". It redraws the UI from the document; "Sync From Scene"
        # (above, in &Guides) runs the other way -- scene into the document.
        # Two neighbouring commands that both read as "update" is exactly the
        # ambiguity this whole piece of work exists to remove. The underlying
        # method stays `refresh`; only the label and shortcut assignment move.
        self._action(layout_menu, "Redraw Views", lambda: self._designer_call("refresh"), "F5")

        tools_menu = add_menu("&Tools")
        self._action(tools_menu, "Guide Designer", lambda: self.open_guide_designer(), "Ctrl+G")
        tools_menu.addSeparator()
        self.shelf_action = self._action(tools_menu, "Show Action Shelf", self.toggle_shelf, "Ctrl+Shift+A", checkable=True)
        self.shelf_action.setChecked(True)
        self.log_action = self._action(tools_menu, "Show Log", self.toggle_log, "Ctrl+L", checkable=True)
        tools_menu.addSeparator()
        self._action(tools_menu, "Settings…", self.open_settings)

        help_menu = add_menu("&Help")
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

    @property
    def _designer(self):
        """The active session's Designer, but only while its tab is in front."""
        view = self.current_view
        if view is None or not view.on_designer_tab:
            return None
        return view.designer

    def _designer_call(self, method: str, *args, **kwargs):
        designer = self._designer
        if designer is None:
            return None
        return getattr(designer, method)(*args, **kwargs)

    def _graph_call(self, method: str, *args):
        designer = self._designer
        if designer is None:
            return None
        return getattr(designer.graph, method)(*args)

    def _either(self, session_method: str, designer_method: str, *args, **kwargs):
        """Run the verb on whichever view is in front."""
        if self._designer is not None:
            return self._designer_call(designer_method, *args, **kwargs)
        return self._view_call(session_method, *args, **kwargs)

    def _sync_menu_state(self) -> None:
        """The Guides menu is only offered where it has a target.

        Also where the Auto Sync menu action gets bound to whatever Designer
        just became active: a Designer is built lazily, one per session tab,
        so there is no single spot at window construction to wire this -- it
        happens here, every time the active tab (session or sub-tab) changes.
        """
        if hasattr(self, "guides_menu_action"):
            self.guides_menu_action.setEnabled(self._designer is not None)
        designer = self._designer
        if designer is not None:
            self._connect_designer_auto_sync(designer)
            self._on_designer_auto_sync_changed(designer.guides.auto_sync)

    def _connect_designer_auto_sync(self, designer) -> None:
        """Wire the Auto Sync menu action to ``designer``'s signal, once.

        Marked on the Designer itself rather than tracked by id() in a
        window-level set: tabs are closable (``close_tab`` ->
        ``_drop_designer`` -> ``view.teardown()``), and once a closed tab's
        Designer is garbage-collected, CPython is free to reuse its address
        for a later Designer -- an id-set would then see that id as "already
        connected" and silently never wire the new instance's signal. A
        fresh Designer never carries this attribute regardless of what
        address it landed on, so there is nothing to go stale and nothing to
        prune.
        """
        if getattr(designer, "_menu_auto_sync_bound", False):
            return
        designer.auto_sync_changed.connect(self._on_designer_auto_sync_changed)
        designer._menu_auto_sync_bound = True

    def _on_designer_auto_sync_changed(self, on: bool) -> None:
        """Mirror the Designer's setting without reporting it back as a click.

        Blocked the same way ``DesignerActionBar.set_auto_sync`` blocks its
        checkbox -- without this the menu action and the Designer would
        ping-pong through ``set_auto_sync``.
        """
        self.auto_sync_action.blockSignals(True)
        try:
            self.auto_sync_action.setChecked(bool(on))
        finally:
            self.auto_sync_action.blockSignals(False)

    def _view_call(self, method: str, *args):
        view = self.current_view
        if view is not None:
            return getattr(view, method)(*args)
        return None

    def _current_path(self) -> Optional[str]:
        view = self.current_view
        return view.current_path() if view else None

    def add_session(self, session: Session) -> SessionView:
        view = SessionView(
            session, file_browser=self.file_browser,
            designer_factory=self.designer_factory, events=self.events,
        )
        view.sub_tab_changed.connect(lambda index, v=view: self._on_sub_tab_changed(v, index))
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
        # The session's stack on both tabs: guide *structure* is a document
        # edit. Moving a guide is a scene edit and stays on Maya's stack,
        # undone with focus in the viewport.
        session = self.session
        if session is not None and session.undo():
            self._after_document_change()

    def redo(self) -> None:
        session = self.session
        if session is not None and session.redo():
            self._after_document_change()

    def _after_document_change(self) -> None:
        """Undo/redo replaced the document; put the views back in step with it.

        The guides need a sync as well as a repaint: undo restores the document
        in memory, and lockstep is what draws the difference.
        """
        self._view_call("refresh")
        designer = self.active_designer
        if designer is None:
            return
        try:
            designer.guides.sync()
        except Exception as error:  # noqa: BLE001 - keep the tool alive
            self.events.log(f"Could not redraw guides: {error}", level="warning")
        designer.refresh()

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
        view = self.current_view
        if view is not None and view.on_designer_tab:
            self.setWindowTitle(f"Trigger {VERSION} — {view.session.name} — Guides")
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
    # --------------------------------------------------------------- guides
    @property
    def active_designer(self):
        """The Guide Designer of the active session tab, if it has been built."""
        view = self.current_view
        return view.designer if view is not None else None

    def open_guide_designer(self, guides_path: str = ""):
        """Show the active session's Guide Designer."""
        view = self.current_view
        if view is None:
            return None
        view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
        if guides_path and view.designer is not None:
            # remembered for the Import dialog, not imported: opening the
            # Designer from a path field should not change the rig
            view.designer.set_file(guides_path)
        return view.designer

    def _hand_over_to(self, view) -> None:
        """Give the scene's checkout to ``view``'s session.

        Switching *session tabs* is the hand-off; switching between a session's
        own sub-tabs changes nothing about the scene.
        """
        outgoing = self._checked_out_view
        if outgoing is view:
            return
        if outgoing is not None and outgoing not in self.views:
            outgoing = None  # its tab is gone; nothing to hand over
        try:
            Session.hand_over(
                outgoing.session if outgoing is not None else None, view.session
            )
            self._checked_out_view = view
        except SessionError as error:
            self.events.log(str(error), level="warning")
        except Exception as error:  # noqa: BLE001 - keep the tool alive
            self.events.log(f"Could not check out guides: {error}", level="warning")

    def _on_tab_changed(self, _index: int) -> None:
        view = self.current_view
        if view is not None and view.designer is not None:
            self._hand_over_to(view)
        self._sync_menu_state()
        self._update_title()

    def _on_sub_tab_changed(self, view, index: int) -> None:
        """The first time a session's Designer opens, its guides get the scene."""
        if index == DESIGNER_TAB:
            self._hand_over_to(view)
            # a build may have cleared the guides on purpose; opening the
            # Designer is the ask to see them again
            designer = view.designer
            try:
                if designer is not None and getattr(designer.guides, "dismissed", False):
                    designer.guides.restore()
                    designer.refresh()
            except Exception as error:  # noqa: BLE001 - keep the tool alive
                self.events.log(f"Could not redraw guides: {error}", level="warning")
        self._sync_menu_state()
        self._update_title()

    def _drop_designer(self, view) -> None:
        if self._checked_out_view is view:
            self._checked_out_view = None
        view.teardown()

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
        for view in self.views:
            view.teardown()
        super().closeEvent(event)


def show(dockable: bool = True) -> TriggerWindow:
    """Open (or re-open) the single Trigger window."""
    import tik.trigger as trigger

    trigger.load_plugins()
    # a previous instance's watchers are still registered with Maya, and after a
    # module reload they fire into stale code
    SceneWatcher.uninstall_all()
    TriggerWindow.teardown_workspace_control()
    window = TriggerWindow()
    window.show_tool(dockable=dockable)
    return window
