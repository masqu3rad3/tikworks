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
from tik.shared.ui.feedback import Feedback
from tik.shared.ui.maya_window import HAS_MAYA, MayaToolWindow
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.scene_watcher import SceneWatcher
from tik.shared.ui.status import StatusFields
from tik.trigger.core import ERROR, LOG, EventBus, versioning
from tik.trigger.core.document import EXTENSION
from tik.trigger.core.exceptions import SessionError
from tik.trigger.session import Session

from .autosave import AutosaveTimer
from .autosave import clear as clear_autosave
from .autosave import recoverable
from .designer.widgets import SCENE_NODE
from .script_dock import ScriptViewer
from .session_view import DESIGNER_TAB, SessionView
from .widgets import LogWidget

FILE_FILTER = f"Trigger session (*{EXTENSION})"
VERSION = "0.2.0"


def _holder() -> QtWidgets.QWidget:
    """An empty widget whose zero-margin layout a mode bundle drops into."""
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    return widget


def prefs_value(page: str, field: str):
    """One preference value, read lazily so imports stay cheap."""
    from tik.trigger.config import prefs

    return getattr(prefs.page(page), field)


class TriggerWindow(MayaToolWindow):
    """The Trigger main window: session tabs, menus, log dock and status bar."""

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
        self.log.set_level(prefs_value("interface", "log_verbosity"))
        self.log.setMaximumBlockCount(prefs_value("interface", "log_max_lines"))
        self.restore_window_state()
        self._load_recent()
        self.autosave = AutosaveTimer(self, prefs_value("files", "autosave_interval"))
        self.autosave.reconfigure()

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
        self.script_viewer = ScriptViewer()
        self.script_dock = QtWidgets.QDockWidget("Script", self)
        self.script_dock.setObjectName("TriggerScriptDock")
        self.script_dock.setWidget(self.script_viewer)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.script_dock)
        self.script_dock.hide()
        # closing the dock from its title bar must un-tick the menu entry
        self.script_dock.visibilityChanged.connect(self.script_action.setChecked)

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

    def _action(
        self, menu, text, slot, shortcut: Optional[str] = None, checkable: bool = False
    ):
        action = menu.addAction(text)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        if checkable:
            action.setCheckable(True)
        return action

    def _build_menus(self, bar) -> None:
        self._menus: dict = {}
        self._build_file_menu(self._add_menu(bar, "&File"))
        self._build_edit_menu(self._add_menu(bar, "&Edit"))
        self._build_session_menu(self._add_menu(bar, "&Session"))
        guides_menu = self._add_menu(bar, "&Guides")
        self._build_guides_menu(guides_menu)
        self._build_layout_menu(guides_menu)
        self._build_tools_menu(self._add_menu(bar, "&Tools"))
        self._build_help_menu(self._add_menu(bar, "&Help"))
        self._update_recent_menu()

    def _add_menu(self, bar, title: str) -> QtWidgets.QMenu:
        # Built with the bar as their C++ parent, not via ``bar.addMenu(str)``:
        # that hands ownership to Python, and the menu dies with the local that
        # held it -- leaving the bar showing titles backed by dead objects.
        menu = QtWidgets.QMenu(title, bar)
        bar.addMenu(menu)
        self._menus[title] = menu
        return menu

    def _build_file_menu(self, file_menu) -> None:
        self._action(file_menu, "New Session", self.new_session, "Ctrl+N")
        self._action(file_menu, "Open…", self.open_session, "Ctrl+O")
        self.recent_menu = file_menu.addMenu("Open Recent")
        file_menu.addSeparator()
        self._action(file_menu, "Save", self.save_session, "Ctrl+S")
        self._action(file_menu, "Save As…", self.save_session_as, "Ctrl+Shift+S")
        self._action(
            file_menu, "Increment Version", self.increment_session, "Ctrl+Alt+S"
        )
        file_menu.addSeparator()
        self._action(file_menu, "Import Actions…", self.import_actions)
        self._action(file_menu, "Export Actions…", self.export_actions)
        file_menu.addSeparator()
        # a .trg is a guide *library* now, not this session's document, so it
        # gets no save shortcut -- Ctrl+S saves the session, guides included
        self._action(
            file_menu, "Import Guides…", lambda: self._designer_call("import_file")
        )
        self._action(
            file_menu,
            "Export Guides…",
            lambda: self._designer_call("export_file", ask=True),
        )
        file_menu.addSeparator()
        # A .trg import copies modules in; this links them, so upstream
        # changes keep arriving. Two different acts, deliberately apart.
        self._action(
            file_menu,
            "Reference Modules…",
            lambda: self._designer_call("reference_modules"),
        )
        file_menu.addSeparator()
        # no shortcut: it throws the scene away, and there is nothing to undo
        self._action(file_menu, "Reset Scene", self.reset_scene)
        file_menu.addSeparator()
        self._action(file_menu, "Settings…", self.open_settings, "Ctrl+,")
        file_menu.addSeparator()
        self._action(
            file_menu,
            "Close Tab",
            lambda: self.close_tab(self.tabs.currentIndex()),
            "Ctrl+W",
        )
        self._action(file_menu, "Quit", self.close, "Ctrl+Q")

    def _build_edit_menu(self, edit_menu) -> None:
        # One Edit menu for both views: the verbs mean the same thing, so they
        # act on whichever of the two is in front rather than fighting over
        # Ctrl+D / F2 / Del.
        self._action(edit_menu, "Undo", self.undo, "Ctrl+Z")
        self._action(edit_menu, "Redo", self.redo, "Ctrl+Y")
        edit_menu.addSeparator()
        self._action(
            edit_menu,
            "Add…",
            lambda: self._either("show_palette", "show_palette"),
            "Tab",
        )
        self._action(
            edit_menu,
            "Add Child Action…",
            lambda: self._view_call("add_child_via_palette"),
        )
        self._action(
            edit_menu,
            "Duplicate",
            lambda: self._either("duplicate_current", "duplicate_current"),
            "Ctrl+D",
        )
        self._action(
            edit_menu,
            "Rename",
            lambda: self._either("rename_current", "rename_current"),
            "F2",
        )
        self._action(
            edit_menu,
            "Delete",
            lambda: self._either("remove_current", "delete_current"),
            "Del",
        )
        self._action(
            edit_menu,
            "Enable / Disable",
            lambda: self._view_call("toggle_current"),
            "Ctrl+E",
        )

    def _build_session_menu(self, session_menu) -> None:
        self.session_menu_action = session_menu.menuAction()
        self._action(
            session_menu, "Build Rig", lambda: self._view_call("build"), "Ctrl+B"
        )
        self._action(
            session_menu,
            "Build & Publish",
            lambda: self._view_call("build_and_publish"),
            "Ctrl+Shift+P",
        )
        self._action(
            session_menu,
            "Build Until Here",
            lambda: self._view_call("build_until", self._current_path()),
            "Ctrl+Shift+B",
        )
        self._action(
            session_menu,
            "Run Step",
            lambda: self._view_call("run_step", self._current_path()),
            "Ctrl+R",
        )
        session_menu.addSeparator()
        self._action(session_menu, "Validate", self.validate_session)
        self._action(
            session_menu, "Clear Statuses", lambda: self._view_call("clear_statuses")
        )

    def _build_guides_menu(self, guides_menu) -> None:
        self.guides_menu_action = guides_menu.menuAction()
        self._action(
            guides_menu, "Add Module…", lambda: self._designer_call("show_palette")
        )
        self._action(
            guides_menu,
            "Add Scene Nodes",
            lambda: self._designer_call("create_guides", SCENE_NODE),
        )
        guides_menu.addSeparator()
        self._action(
            guides_menu, "Select Root", lambda: self._designer_call("select_root")
        )
        self._action(
            guides_menu,
            "Select All Guides",
            lambda: self._designer_call("select_current"),
        )
        self._action(
            guides_menu,
            "Mirror",
            lambda: self._designer_call("mirror_current"),
            "Ctrl+M",
        )
        guides_menu.addSeparator()
        self._action(
            guides_menu, "Connect Input…", lambda: self._designer_call("connect_dialog")
        )
        self._action(
            guides_menu,
            "Disconnect Primary Input",
            lambda: self._designer_call("disconnect_primary"),
        )
        self._action(
            guides_menu,
            "Sever Connections",
            lambda: self._designer_call("sever_current"),
            "Ctrl+Shift+D",
        )
        guides_menu.addSeparator()
        self._action(
            guides_menu,
            "Build Selected Guides",
            lambda: self._designer_call("test_build"),
        )
        self._action(
            guides_menu,
            "Build All Guides",
            lambda: self._designer_call("test_build", True),
        )
        guides_menu.addSeparator()
        # The verbs that cross the session/scene line, grouped by direction:
        # Draw pushes the session into Maya, Sync and Snapshot pull back.
        self._action(
            guides_menu,
            "Draw Selected Guides",
            lambda: self._designer_call("draw_selected"),
        )
        self._action(
            guides_menu,
            "Draw All Guides",
            lambda: self._designer_call("draw_all"),
            "F5",
        )
        self.draw_on_create_action = self._action(
            guides_menu,
            "Draw New Modules",
            lambda: self._designer_call(
                "set_draw_on_create", self.draw_on_create_action.isChecked()
            ),
            checkable=True,
        )
        self.draw_on_create_action.setChecked(True)
        guides_menu.addSeparator()
        self._action(
            guides_menu,
            "Sync From Scene",
            lambda: self._designer_call("sync_now"),
            "F6",
        )
        self.auto_sync_action = self._action(
            guides_menu,
            "Auto Sync",
            lambda: self._designer_call(
                "set_auto_sync", self.auto_sync_action.isChecked()
            ),
            checkable=True,
        )
        self.auto_sync_action.setChecked(True)
        self._action(
            guides_menu,
            "Snapshot Guides From Scene…",
            lambda: self._designer_call("snapshot_guides"),
        )
        guides_menu.addSeparator()
        # Not "Clear Scene Guides": this deletes every module from the
        # session document, not just the rendering, and under the Draw/Sync
        # vocabulary the old label read as "undraw everything".
        self._action(
            guides_menu,
            "Delete All Modules",
            lambda: self._designer_call("clear_guides"),
        )

    def _build_layout_menu(self, guides_menu) -> None:
        layout_menu = QtWidgets.QMenu("Layout", guides_menu)
        guides_menu.addMenu(layout_menu)
        self._menus["Layout"] = layout_menu
        self._action(
            layout_menu,
            "Auto Layout",
            lambda: self._graph_call("auto_layout"),
            "Ctrl+L",
        )
        self._action(layout_menu, "Fit Graph", lambda: self._graph_call("fit"), "F")
        layout_menu.addSeparator()
        self._action(
            layout_menu,
            "Collapse: Header Only",
            lambda: self._graph_call("set_selected_mode", 0),
            "1",
        )
        self._action(
            layout_menu,
            "Collapse: Connected Plugs",
            lambda: self._graph_call("set_selected_mode", 1),
            "2",
        )
        self._action(
            layout_menu,
            "Collapse: Everything",
            lambda: self._graph_call("set_selected_mode", 2),
            "3",
        )
        layout_menu.addSeparator()
        # Was "Refresh". It redraws the UI from the document; "Sync From Scene"
        # (above, in &Guides) runs the other way -- scene into the document.
        # Two neighbouring commands that both read as "update" is exactly the
        # ambiguity this whole piece of work exists to remove. The underlying
        # method stays `refresh`; only the label and shortcut assignment move.
        self._action(
            layout_menu, "Redraw Views", lambda: self._designer_call("refresh"), "F5"
        )

    def _build_tools_menu(self, tools_menu) -> None:
        self._action(
            tools_menu, "Guide Designer", lambda: self.open_guide_designer(), "Ctrl+G"
        )
        tools_menu.addSeparator()
        self.shelf_action = self._action(
            tools_menu,
            "Show Action Shelf",
            self.toggle_shelf,
            "Ctrl+Shift+A",
            checkable=True,
        )
        self.shelf_action.setChecked(True)
        self.log_action = self._action(
            tools_menu, "Show Log", self.toggle_log, "Ctrl+L", checkable=True
        )
        self.script_action = self._action(
            tools_menu,
            "Show Script Viewer",
            self.toggle_script_viewer,
            "Ctrl+Shift+L",
            checkable=True,
        )

    def _build_help_menu(self, help_menu) -> None:
        self._action(help_menu, "Documentation", self.open_docs)
        self._action(help_menu, "About Trigger", self.about)

    def _build_status(self, strip) -> None:
        self.status = StatusFields(strip, ("references", "maya", "version"))
        maya_text = "Maya"
        if HAS_MAYA:
            try:
                from maya import cmds

                maya_text = f"Maya {cmds.about(version=True)}"
            except Exception:  # noqa: BLE001 - a mocked maya has no about()
                pass
        self.status.set("maya", maya_text)
        self.status.set("version", f"tik.trigger {VERSION}")
        self.status.set_activity("Ready")

    # ---------------------------------------------------------------- tabs
    @property
    def views(self) -> list[SessionView]:
        """One ``SessionView`` per open tab."""
        return [self.tabs.widget(index) for index in range(self.tabs.count())]

    @property
    def current_view(self) -> Optional[SessionView]:
        """The view on the active tab, or None."""
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, SessionView) else None

    @property
    def session(self) -> Optional[Session]:
        """The session on the active tab, or None."""
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
        """Each sub-tab shows the menu that belongs to it, and hides the other.

        Visibility follows the *mode*: Session on the Session tab, Guides on
        the Guide Designer tab. Enablement follows the *target*, which is not
        the same question -- the Guides verbs all route through
        ``_designer_call``, and a Designer is built lazily, so off its tab
        there is nothing for them to act on.

        Hiding a menu leaves its actions alone, so the shortcuts underneath
        (Ctrl+B, Ctrl+M) still fire either way. That costs nothing: on the
        Session tab the Guides verbs no-op through the guard above, and
        building from the Designer tab was always meaningful.

        Also where the Auto Sync menu action gets bound to whatever Designer
        just became active: a Designer is built lazily, one per session tab,
        so there is no single spot at window construction to wire this -- it
        happens here, every time the active tab (session or sub-tab) changes.
        """
        on_designer = self._designer is not None
        if hasattr(self, "guides_menu_action"):
            self.guides_menu_action.setEnabled(on_designer)
            self.guides_menu_action.setVisible(on_designer)
        if hasattr(self, "session_menu_action"):
            self.session_menu_action.setVisible(not on_designer)
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
        """Open ``session`` in a new tab and make it current."""
        view = SessionView(
            session,
            file_browser=self.file_browser,
            designer_factory=self.designer_factory,
            events=self.events,
        )
        view.sub_tab_changed.connect(
            lambda index, session_view=view: self._on_sub_tab_changed(
                session_view, index
            )
        )
        view.title_changed.connect(self._update_title)
        view.open_guides_requested.connect(self.open_guide_designer)
        view.activity.connect(self.status.set_activity)
        view.handle_changed.connect(
            lambda handle, session_view=view: self._on_handle_changed(
                session_view, handle
            )
        )
        index = self.tabs.addTab(view, session.name)
        self.tabs.setCurrentIndex(index)
        self._update_title()
        return view

    def new_session(self) -> SessionView:
        """Open an empty session in a new tab."""
        return self.add_session(Session(events=self.events))

    def open_session(self, path: Optional[str] = None) -> Optional[SessionView]:
        """Open a ``.tr`` file (asking for one when ``path`` is empty)."""
        if not path:
            path = Feedback(self).browse_open(
                "Open session", self.browse_folder(), (EXTENSION,), FILE_FILTER
            )
        if not path:
            return None
        for view in self.views:
            if view.session.file_path and Path(view.session.file_path) == Path(path):
                self.tabs.setCurrentWidget(view)
                return view
        path = self._offer_recovery(path)
        session = Session.open(path, events=self.events)
        view = self.add_session(session)
        untouched = [
            other
            for other in self.views
            if other is not view
            and not other.session.is_modified
            and not other.session.file_path
        ]
        for item in untouched:
            self.tabs.removeTab(self.tabs.indexOf(item))
        self._remember(path)
        return view

    def _offer_recovery(self, path: str) -> str:
        """Offer a newer autosave in place of ``path``, returning what to open.

        A sidecar newer than the session means Trigger stopped between an
        autosave and a save. The rigger decides which one is the real work --
        we never substitute it silently.
        """
        found = recoverable(path)
        if found is None:
            return path
        answer = Feedback(self).pop_question(
            title="Recover autosave",
            text=f"A newer autosave exists for {Path(path).name}.",
            details=(f"{found}\n\nOpen the autosave instead of the saved session?"),
            buttons=["open autosave", "open session"],
        )
        return str(found) if answer == "open autosave" else path

    def save_session(self) -> None:
        """Save the current session, asking for a path if it has none."""
        view = self.current_view
        if view is not None:
            self._save_view(view)

    def save_session_as(self, path: Optional[str] = None) -> None:
        """Save the current session to ``path`` (asking when empty)."""
        session = self.session
        if session is None:
            return
        if not path:
            path = Feedback(self).browse_save(
                "Save session", self.browse_folder(), (EXTENSION,), FILE_FILTER
            )
        if not path:
            return
        session.save(path)
        self._remember(str(session.file_path))
        self._update_title()

    def increment_session(self) -> None:
        """Save the current session to its next version number."""
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
        """Append the actions of another ``.tr`` file to the current session."""
        session = self.session
        if session is None:
            return
        if not path:
            path = Feedback(self).browse_open(
                "Import actions", "", (EXTENSION,), FILE_FILTER
            )
        if not path:
            return
        from tik.trigger.core.document import Document

        for node in Document.load(path).actions:
            session.document.add(node)
        session.touch()
        self._view_call("refresh")

    def export_actions(self, path: Optional[str] = None) -> None:
        """Write the current session's actions to a ``.tr`` file."""
        session = self.session
        if session is None:
            return
        if not path:
            path = Feedback(self).browse_save(
                "Export actions", "", (EXTENSION,), FILE_FILTER
            )
        if not path:
            return
        session.document.save(path if path.endswith(EXTENSION) else path + EXTENSION)

    def ask_save_discard(self, session: Session) -> str:
        """Ask what to do with ``session``'s unsaved changes.

        Returns ``"save"``, ``"discard"`` or ``"cancel"`` -- never a Qt enum,
        so the callers stay readable and a test can answer with a string.

        With ``files.confirm_unsaved_close`` turned off the question is not
        asked and the changes are discarded, which is what turning the warning
        off means.
        """
        if not prefs_value("files", "confirm_unsaved_close"):
            return "discard"
        return self._ask_save_discard_dialog(session)

    def _ask_save_discard_dialog(self, session: Session) -> str:
        """The unsaved-changes question itself, split out so it can be skipped."""
        answer = Feedback(self).pop_question(
            title="Unsaved changes",
            text=f"Save changes to {session.name} before closing?",
            details="Your changes will be lost if you discard them.",
            buttons=["save", "discard", "cancel"],
        )
        return answer or "cancel"

    def _save_view(self, view, path: Optional[str] = None) -> bool:
        """Save ``view``'s session; False when it could not be written.

        Targets a view rather than the current tab: closing the window saves
        tabs that are not the one in front.
        """
        session = view.session
        if not path and session.file_path is None:
            path = Feedback(self).browse_save(
                "Save session", self.browse_folder(), (EXTENSION,), FILE_FILTER
            )
            if not path:
                return False
        try:
            session.save(path or None)
        except Exception as error:  # noqa: BLE001 - report, never trap
            self.events.log(f"Could not save {session.name}: {error}", level="warning")
            return False
        clear_autosave(str(session.file_path))
        self._remember(str(session.file_path))
        self._update_title()
        return not session.is_modified

    def _confirm_close(self, view) -> bool:
        """True when ``view``'s tab may close: clean, saved, or discarded."""
        if not isinstance(view, SessionView):
            return True
        if view is self._checked_out_view:
            # nothing in Maya fires when a guide is dragged, so a session can
            # look clean while the scene holds an afternoon of posing
            try:
                view.session.capture_guides()
            except Exception as error:  # noqa: BLE001 - never trap the window
                self.events.log(f"Could not read the guides: {error}", level="warning")
        if not view.session.is_modified:
            return True
        answer = self.ask_save_discard(view.session)
        if answer == "discard":
            return True
        if answer != "save":
            return False
        return self._save_view(view)

    def close_tab(self, index: int) -> bool:
        """Close the tab at ``index`` unless the user keeps unsaved changes."""
        view = self.tabs.widget(index)
        if not self._confirm_close(view):
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
        """Undo the last document edit of the current session."""
        session = self.session
        if session is not None and session.undo():
            self._after_document_change()

    def redo(self) -> None:
        """Redo the last undone document edit of the current session."""
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
        """Report the current session's problems, or that there are none."""
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
        """Show or hide the action shelf of the current tab."""
        view = self.current_view
        if view is not None:
            view.set_shelf_visible(not view.shelf_visible)
            self.shelf_action.setChecked(view.shelf_visible)

    def toggle_log(self) -> None:
        """Show or hide the log dock."""
        self.log_dock.setVisible(not self.log_dock.isVisible())
        self.log_action.setChecked(self.log_dock.isVisible())

    def toggle_script_viewer(self) -> None:
        """Show or hide the Script viewer dock."""
        self.script_dock.setVisible(not self.script_dock.isVisible())
        self.script_action.setChecked(self.script_dock.isVisible())
        if self.script_dock.isVisible():
            self._refresh_script_viewer()

    def _refresh_script_viewer(self) -> None:
        view = self.current_view
        if view is None:
            self.script_viewer.clear()
            return
        self.script_viewer.show_handle(view.current_handle(), view.session.directory)

    def _on_handle_changed(self, view, handle) -> None:
        # only the active tab drives the viewer; background tabs keep quiet
        if view is self.current_view:
            self.script_viewer.show_handle(handle, view.session.directory)

    def reset_scene(self) -> None:
        """Wipe the Maya scene, after asking.

        The guides are not redrawn: the session document still holds them, so
        nothing is lost, and a rigger who resets usually wants the empty scene
        they asked for. The run statuses go with it -- the build they described
        no longer exists.
        """
        if prefs_value("guides", "confirm_reset_scene"):
            answer = Feedback(self).pop_question(
                title="Reset Scene",
                text="Delete everything in the Maya scene?",
                details=(
                    "Your session and its guides are kept. Anything built or "
                    "imported into the scene is lost."
                ),
                buttons=["cancel", "reset"],
            )
            if answer != "reset":
                return
        from tik.trigger.guides import nodes

        nodes.new_scene()
        view = self.current_view
        if view is not None:
            view.clear_statuses()
        self.status.set_activity("Scene reset")

    def open_settings(self, *, exec_: bool = True):
        """Open the preferences dialog.

        ``exec_`` is keyword-only on purpose. ``QAction.triggered`` emits a
        ``checked`` boolean, and PySide hands it to any slot whose signature
        accepts a positional argument -- so as a positional parameter this
        bound ``exec_=False`` on every menu click, building the dialog,
        skipping the modal loop and discarding it without a word.

        Args:
            exec_: Run the modal loop. Tests pass False to inspect the dialog.

        Returns:
            The dialog, so a caller can inspect it.
        """
        from tik.shared.ui.prefs_dialog import PrefsDialog
        from tik.trigger.config import prefs

        # Held on self: a modeless dialog assigned to a local is garbage
        # collected the moment this returns.
        self._prefs_dialog = PrefsDialog(prefs, self)
        self._prefs_dialog.applied.connect(self._on_prefs_applied)
        if exec_:
            self._prefs_dialog.exec()
        return self._prefs_dialog

    def _on_prefs_applied(self, changed: list) -> None:
        """Push applied preferences into the widgets that cache them.

        Only settings that a *live* widget holds a copy of need pushing.
        Everything else is read at the point of use and picks the new value
        up on its own, which is why this table stays short.
        """
        if "interface.log_max_lines" in changed:
            self.log.setMaximumBlockCount(prefs_value("interface", "log_max_lines"))
        if "interface.log_verbosity" in changed:
            self.log.set_level(prefs_value("interface", "log_verbosity"))
        if any(key.startswith("files.autosave") for key in changed):
            self.autosave.reconfigure()
        if "files.max_recent" in changed:
            del self.recent_files[prefs_value("files", "max_recent") :]
            self._save_recent()
            self._update_recent_menu()

    def open_docs(self) -> None:
        """Open the project page in the browser."""
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl("https://github.com/masqu3rad3/tikworks")
        )

    def about(self) -> None:
        """Show the version box."""
        Feedback(self).pop_about(
            "About Trigger", f"Trigger {VERSION}\nModular rigging on tik.maya."
        )

    # -------------------------------------------------------------- recent
    def _remember(self, path: str) -> None:
        """Put ``path`` at the top of the recent list and persist it."""
        path = str(Path(path))
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        del self.recent_files[prefs_value("files", "max_recent") :]
        self._remember_folder(path)
        self._save_recent()
        self._update_recent_menu()

    def _load_recent(self) -> None:
        """Fill the recent list from the preferences file."""
        if not prefs_value("files", "remember_recent"):
            self.recent_files = []
        else:
            stored = prefs_value("files", "recent_sessions") or []
            self.recent_files = [str(item) for item in stored]
            del self.recent_files[prefs_value("files", "max_recent") :]
        self._update_recent_menu()

    def _save_recent(self) -> None:
        """Persist the recent list, unless the user asked us not to."""
        from tik.trigger.config import prefs

        prefs.files.recent_sessions = (
            list(self.recent_files) if prefs_value("files", "remember_recent") else []
        )
        prefs.save()

    def browse_folder(self) -> str:
        """Where a file browser should open."""
        if prefs_value("files", "remember_last_folder"):
            last = prefs_value("files", "last_folder")
            if last:
                return str(last)
        return str(prefs_value("files", "default_folder") or "")

    def _remember_folder(self, path: str) -> None:
        """Store ``path``'s folder as the one browsers reopen in."""
        if not prefs_value("files", "remember_last_folder"):
            return
        from tik.trigger.config import prefs

        prefs.files.last_folder = str(Path(path).parent)
        prefs.save()

    def _update_recent_menu(self) -> None:
        self.recent_menu.clear()
        if not self.recent_files:
            self.recent_menu.addAction("(none)").setEnabled(False)
        for path in self.recent_files:
            self.recent_menu.addAction(
                path, lambda checked=False, file_path=path: self.open_session(file_path)
            )

    # -------------------------------------------------------------- title
    def _update_title(self) -> None:
        for index, view in enumerate(self.views):
            self.tabs.setTabText(
                index, view.session.name + ("*" if view.session.is_modified else "")
            )
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
                state = (
                    "latest"
                    if latest is None or versioning.parse(latest)[1] <= version
                    else f"older · latest v{versioning.parse(latest)[1]:03d}"
                )
        references = sum(1 for handle in session.walk() if handle.type == "reference")
        self.status.set(
            "references",
            f"{references} reference(s)" + (f" · {state}" if state else ""),
        )

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
        if self.script_dock.isVisible():
            self._refresh_script_viewer()

    def _on_sub_tab_changed(self, view, index: int) -> None:
        """The first time a session's Designer opens, its guides get the scene.

        Claiming the scene is all it does. Opening the Designer used to redraw
        guides a build had cleared, which is exactly the kind of unasked-for
        draw this design removes -- the modules are reported not-drawn and
        Draw is the rigger's to press.
        """
        if index == DESIGNER_TAB:
            self._hand_over_to(view)
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
        if prefs_value("interface", "log_open_on_error"):
            self.log_dock.show()
            self.log_action.setChecked(True)

    # ------------------------------------------------------------ autosave
    def autosave_target(self) -> str:
        """The active session's file path, or ``""`` when it has none."""
        session = self.session
        if session is None or session.file_path is None:
            return ""
        return str(session.file_path)

    def is_modified(self) -> bool:
        """True when the active session has unsaved changes."""
        session = self.session
        return bool(session is not None and session.is_modified)

    def write_autosave(self, target) -> None:
        """Write the active session to ``target`` without changing its path.

        Goes through ``Document.save`` rather than ``Session.save``: the
        latter reassigns ``Session.file_path``, which would quietly rename the
        open session to its own recovery file.
        """
        session = self.session
        if session is not None:
            session.document.save(str(target))

    # -------------------------------------------------------- window state
    #: Opaque Qt blobs, kept out of the readable JSON file on purpose.
    STATE_ORG, STATE_APP = "tikworks", "trigger"

    def save_window_state(self) -> None:
        """Store geometry and dock layout as Qt blobs."""
        settings = QtCore.QSettings(self.STATE_ORG, self.STATE_APP)
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/state", self.saveState())

    def restore_window_state(self) -> None:
        """Put back whatever the preferences allow, tolerating missing blobs.

        Geometry and dock layout are opaque Qt byte blobs that vary by Qt
        version and monitor arrangement, so they live in ``QSettings`` rather
        than polluting the hand-editable preferences file. The two booleans
        that gate them are ordinary preferences.
        """
        settings = QtCore.QSettings(self.STATE_ORG, self.STATE_APP)
        if prefs_value("interface", "restore_geometry"):
            blob = settings.value("window/geometry")
            if blob:
                self.restoreGeometry(blob)
        if prefs_value("interface", "restore_dock_layout"):
            blob = settings.value("window/state")
            if blob:
                self.restoreState(blob)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt style
        """Remember the layout, then let the base class decide about closing.

        The unsaved-changes question lives in ``MayaToolWindow.closeEvent`` and
        must be asked exactly once, so this override must not repeat it. Saving
        the layout unconditionally is harmless: if the user cancels the close,
        the window keeps the geometry that was just stored.
        """
        self.save_window_state()
        super().closeEvent(event)

    def confirm_close(self) -> bool:
        """Ask about every dirty tab in order; the first Cancel stops the close.

        Serves both entrances -- the Qt ``closeEvent`` and Maya's workspace
        control -- so a Cancel behaves the same whichever X was pressed.
        """
        return all(self._confirm_close(view) for view in self.views)

    def teardown(self) -> None:
        for view in self.views:
            view.teardown()
        super().teardown()


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
