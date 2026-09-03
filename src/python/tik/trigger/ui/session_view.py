"""One session tab: [tile shelf | build+publish pipelines | properties] + build bar."""

from __future__ import annotations

from typing import Optional

from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.tile_grid import TileEntry, TileGrid
from tik.trigger.core import registry
from tik.trigger.core.document import BUILD, PHASES, PUBLISH
from tik.trigger.core.exceptions import ActionExecutionError, SessionError, TriggerError
from tik.trigger.core.steps import STEP_FAILED, STEP_FINISHED, STEP_STARTED
from tik.trigger.session import ActionHandle, Session

from .delegates import PipelineDelegate
from .model import MIME_TYPE, PipelineModel
from .palette import PaletteEntry, SearchPalette
from .settings_panel import ActionSettingsPanel


def action_entries(scope: str = BUILD) -> list[PaletteEntry]:
    """Palette entries for the actions allowed in ``scope``."""
    return [
        PaletteEntry(
            cls.action_type,
            cls.display_label(),
            getattr(cls, "category", "utility"),
            [cls.description()[:40]],
        )
        for cls in registry.iter_actions(scope=scope)
    ]


def tile_entries(scope: str = BUILD) -> list[TileEntry]:
    """Shelf tiles for the actions allowed in ``scope``."""
    return [
        TileEntry(
            cls.action_type,
            cls.display_label(),
            getattr(cls, "category", "utility"),
            cls.description()[:80],
        )
        for cls in registry.iter_actions(scope=scope)
    ]


class PipelineTree(QtWidgets.QTreeView):
    """The action tree; Tab opens the palette."""

    palette_requested = QtCore.Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == QtCore.Qt.Key_Tab:
            self.palette_requested.emit()
            return
        super().keyPressEvent(event)

    def focusNextPrevChild(self, next_child: bool) -> bool:  # noqa: N802
        return False


def pane(title: str, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """``widget`` under an upper-case caption, as the panes of a view."""
    holder = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(holder)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)
    header = QtWidgets.QLabel(title.upper())
    header.setObjectName("PaneHeader")
    layout.addWidget(header)
    layout.addWidget(widget, 1)
    return holder


#: Sub-tab indices. A session is one document with two views of it.
SESSION_TAB = 0
DESIGNER_TAB = 1


class SessionView(QtWidgets.QWidget):
    """Edit and build one ``Session``: its pipeline and its guides.

    The session is the outer container -- its guides live in the ``.tr`` -- so
    the Guide Designer is a *view of this document*, not a separate mode of the
    window. It is built on first use because ``GuideDesigner`` constructs a
    ``GuideScene``, which imports Maya.
    """

    title_changed = QtCore.Signal()
    open_guides_requested = QtCore.Signal(str)
    activity = QtCore.Signal(str)
    sub_tab_changed = QtCore.Signal(int)

    def __init__(
        self,
        session: Session,
        parent=None,
        file_browser=None,
        designer_factory=None,
        events=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.model = PipelineModel(session, self, phase=BUILD)
        self.publish_model = PipelineModel(session, self, phase=PUBLISH)
        self.models = {BUILD: self.model, PUBLISH: self.publish_model}
        self._focus_phase = BUILD
        self._menu = None  # kept alive between building a context menu and showing it
        self._running = False
        self.file_browser = file_browser
        self.designer_factory = designer_factory
        self.events = events or session.events
        self.designer = None
        self._build_ui(file_browser)
        self._connect_events()

    # -------------------------------------------------------- sub views
    def ensure_designer(self):
        """Build this session's Guide Designer on first use."""
        if self.designer is not None:
            return self.designer
        # the session's guides, never a fresh GuideScene: an unbound one would
        # show nothing and edit a document no session ever sees
        scene = self.session.guides
        if self.designer_factory is not None:
            designer = self.designer_factory(scene)
        else:
            from .designer import GuideDesigner

            designer = GuideDesigner(
                events=self.events, file_browser=self.file_browser, scene=scene
            )
        self.designer = designer
        self._designer_page.layout().addWidget(designer)
        return designer

    def _on_sub_tab_changed(self, index: int) -> None:
        if index == DESIGNER_TAB:
            designer = self.ensure_designer()
            # Belt-and-suspenders alongside GuideDesigner.showEvent: on the
            # very first activation the page is already the current tab when
            # the widget gets built and added to it, so Qt may never deliver
            # a separate show event for it. Cheap and idempotent either way.
            designer.refresh_drift()
        self.sub_tab_changed.emit(index)

    @property
    def on_designer_tab(self) -> bool:
        """True when the Guide Designer sub-tab is current."""
        return self.sub_tabs.currentIndex() == DESIGNER_TAB

    def teardown(self) -> None:
        """Release the Designer's scene jobs. Safe to call more than once."""
        if self.designer is not None:
            self.designer.teardown()

    # ------------------------------------------------------------------ ui
    def _make_tree(self, model: PipelineModel) -> PipelineTree:
        """One pipeline tree. Both phases get an identical one -- the model
        they are given is the only difference."""
        tree = PipelineTree()
        tree.setObjectName("PipelineTree")
        tree.setModel(model)
        tree.setItemDelegate(PipelineDelegate(tree))
        tree.setHeaderHidden(True)
        tree.setIndentation(18)
        tree.setMouseTracking(True)
        tree.setDragEnabled(True)
        tree.setAcceptDrops(True)
        tree.setDropIndicatorShown(True)
        tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop)
        tree.setDefaultDropAction(QtCore.Qt.MoveAction)
        tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        tree.setEditTriggers(
            QtWidgets.QAbstractItemView.EditKeyPressed
            | QtWidgets.QAbstractItemView.SelectedClicked
        )
        tree.setUniformRowHeights(True)
        tree.expandAll()
        tree.installEventFilter(self)
        return tree

    def _build_ui(self, file_browser) -> None:
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sub_tabs = QtWidgets.QTabWidget()
        # named so the theme can inset this strip from the session tab strip
        # above it without touching every QTabWidget in the tool
        self.sub_tabs.setObjectName("SessionSubTabs")
        self.sub_tabs.setDocumentMode(True)
        outer.addWidget(self.sub_tabs)

        session_page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(session_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.splitter.setHandleWidth(6)

        self.splitter.addWidget(self._build_shelf_pane())
        self.splitter.addWidget(self._build_pipeline_pane())
        self.settings = ActionSettingsPanel(
            file_browser=file_browser, base_dir=lambda: self.session.directory
        )
        self.splitter.addWidget(self.settings)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 1)
        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, False)
        self.splitter.setCollapsible(2, False)
        self.splitter.setSizes([170, 460, 420])
        layout.addWidget(self.splitter, 1)

        layout.addWidget(self._build_build_bar())

        self.sub_tabs.addTab(session_page, "Session")
        # a placeholder until the Designer is built on first activation
        self._designer_page = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(self._designer_page).setContentsMargins(0, 0, 0, 0)
        self.sub_tabs.addTab(self._designer_page, "Guide Designer")
        self.sub_tabs.currentChanged.connect(self._on_sub_tab_changed)

        self.palette = SearchPalette(action_entries(BUILD), self)
        self.palette.chosen.connect(self.add_action)

        self._connect_signals()

    def _build_shelf_pane(self) -> QtWidgets.QWidget:
        self.shelves = {
            BUILD: TileGrid(tile_entries(BUILD), MIME_TYPE),
            PUBLISH: TileGrid(tile_entries(PUBLISH), MIME_TYPE),
        }
        self.shelf_stack = QtWidgets.QStackedWidget()
        for phase in PHASES:
            self.shelves[phase].activated.connect(
                lambda key: self.add_action(key, as_child=False)
            )
            self.shelf_stack.addWidget(self.shelves[phase])
        self.shelf = self.shelves[BUILD]  # menus and tests reach for the focused one
        self.shelf_pane = pane("Actions", self.shelf_stack)
        return self.shelf_pane

    def _build_pipeline_pane(self) -> QtWidgets.QWidget:
        self.tree = self._make_tree(self.model)
        self.publish_tree = self._make_tree(self.publish_model)
        self.trees = {BUILD: self.tree, PUBLISH: self.publish_tree}

        # Publish is a short list, so it gets a small bottom pane. Both visible
        # at once: dragging between them is how an action changes phase.
        self.pipeline_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.pipeline_splitter.setHandleWidth(6)
        self.pipeline_splitter.addWidget(pane("Build", self.tree))
        self.pipeline_splitter.addWidget(pane("Publish", self.publish_tree))
        self.pipeline_splitter.setStretchFactor(0, 3)
        self.pipeline_splitter.setStretchFactor(1, 1)
        self.pipeline_splitter.setCollapsible(0, False)
        self.pipeline_splitter.setCollapsible(1, True)
        self.pipeline_splitter.setSizes([360, 120])
        return self.pipeline_splitter

    def _build_build_bar(self) -> QtWidgets.QWidget:
        bar_frame = QtWidgets.QFrame()
        bar_frame.setObjectName("BuildBar")
        bar = QtWidgets.QHBoxLayout(bar_frame)
        bar.setContentsMargins(10, 7, 10, 7)
        bar.setSpacing(8)
        self.build_button = QtWidgets.QPushButton("▶  Build rig")
        self.build_button.setObjectName("PrimaryButton")
        self.publish_button = QtWidgets.QPushButton("Build && Publish")
        self.publish_button.setToolTip(
            "Build the rig from scratch, then run the publish actions"
        )
        self.progress = QtWidgets.QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.counter = QtWidgets.QLabel("")
        self.counter.setObjectName("PanelSubtitle")
        bar.addWidget(self.build_button)
        bar.addWidget(self.publish_button)
        bar.addWidget(self.progress, 1)
        bar.addWidget(self.counter)
        return bar_frame

    def _connect_signals(self) -> None:
        for phase in PHASES:
            tree = self.trees[phase]
            model = self.models[phase]
            tree.selectionModel().currentChanged.connect(
                lambda current, _previous, phase=phase: self._on_current_changed(
                    phase, current
                )
            )
            tree.customContextMenuRequested.connect(
                lambda point, phase=phase: self._context_menu(phase, point)
            )
            tree.doubleClicked.connect(
                lambda index, phase=phase: self._on_double_clicked(phase, index)
            )
            tree.palette_requested.connect(self.show_palette)
            model.edited.connect(self._after_edit)
            model.cross_phase_moved.connect(self._rebuild_all)

        self.settings.edited.connect(self._on_settings_edited)
        self.settings.run_requested.connect(self.run_step)
        self.settings.save_requested.connect(self.save_from_scene)
        self.settings.open_file_requested.connect(
            lambda path, _ext: self.open_guides_requested.emit(path)
        )
        self.build_button.clicked.connect(self.build)
        self.publish_button.clicked.connect(self.build_and_publish)

        for tree in self.trees.values():
            QtWidgets.QShortcut(QtGui.QKeySequence("Delete"), tree, self.remove_current)
            QtWidgets.QShortcut(
                QtGui.QKeySequence("Ctrl+D"), tree, self.duplicate_current
            )
        QtWidgets.QShortcut(QtGui.QKeySequence("F5"), self, self.refresh)

    def _connect_events(self) -> None:
        events = self.session.events
        events.subscribe(
            STEP_STARTED,
            lambda path="", phase=BUILD, **_kw: self._step(
                path, "running", phase=phase
            ),
        )
        events.subscribe(
            STEP_FINISHED,
            lambda path="", phase=BUILD, **_kw: self._step(path, "done", phase=phase),
        )
        events.subscribe(
            STEP_FAILED,
            lambda path="", error="", phase=BUILD, **_kw: self._step(
                path, "failed", error, phase
            ),
        )
        events.subscribe("progress", self._on_progress)

    # ------------------------------------------------------------ helpers
    @property
    def shelf_visible(self) -> bool:
        """True while the shelf has width."""
        return self.splitter.sizes()[0] > 0

    def set_shelf_visible(self, visible: bool) -> None:
        """Show or hide the shelf."""
        sizes = self.splitter.sizes()
        if visible and sizes[0] == 0:
            sizes[0] = 170
        elif not visible:
            sizes[0] = 0
        self.splitter.setSizes(sizes)

    # -------------------------------------------------------------- focus
    #
    # A session tab shows two lists at once, so "which one am I working in?"
    # has to have an answer: the tree that last had focus. It steers the
    # shelf, the palette, the properties panel and the build bar together.

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() == QtCore.QEvent.FocusIn:
            for phase, tree in self.trees.items():
                if watched is tree:
                    self.set_focus_phase(phase)
                    break
        return super().eventFilter(watched, event)

    @property
    def focus_phase(self) -> str:
        """The phase list (build or publish) that has the focus."""
        return self._focus_phase

    @property
    def current_phase(self) -> str:
        """The phase list (build or publish) that has the focus."""
        return self._focus_phase

    def set_focus_phase(self, phase: str) -> None:
        """Give the focus to ``phase`` and show its selection's settings."""
        if phase not in PHASES:
            return
        self._point_at(phase)
        self.settings.set_handle(self.current_handle())

    def _point_at(self, phase: str) -> None:
        """Aim the shared widgets at one phase, without touching the selection."""
        self._focus_phase = phase
        self.shelf_stack.setCurrentWidget(self.shelves[phase])
        self.shelf = self.shelves[phase]
        self.palette.entries = action_entries(phase)
        self.palette.refilter()

    @property
    def current_model(self) -> PipelineModel:
        """The model of the focused phase."""
        return self.models[self._focus_phase]

    @property
    def current_tree(self) -> PipelineTree:
        """The tree of the focused phase."""
        return self.trees[self._focus_phase]

    def current_handle(self) -> Optional[ActionHandle]:
        """The selected action in the focused phase, or None."""
        return self.current_model.handle(self.current_tree.currentIndex())

    def current_path(self) -> Optional[str]:
        """The selected action's path, or None."""
        handle = self.current_handle()
        return handle.path if handle else None

    def select_path(self, path: Optional[str], phase: Optional[str] = None) -> None:
        """Select the action at ``path`` (in ``phase``, default the focused one)."""
        if not path:
            return
        phase = phase or self._focus_phase
        index = self.models[phase].index_for_path(path)
        if index.isValid():
            self.trees[phase].setCurrentIndex(index)
            self.trees[phase].scrollTo(index)

    def _rebuild_all(self) -> None:
        for phase in PHASES:
            self.models[phase].rebuild()
            self.trees[phase].expandAll()

    def refresh(self, keep: Optional[str] = None) -> None:
        """Rebuild both trees and reselect ``keep`` (default: the current path)."""
        keep = keep or self.current_path()
        phase = self._focus_phase
        self._rebuild_all()
        self.select_path(keep, phase)
        self.settings.set_handle(self.current_handle())
        self.title_changed.emit()

    def _after_edit(self) -> None:
        for tree in self.trees.values():
            tree.expandAll()
        self.title_changed.emit()

    def _on_settings_edited(self, path: str) -> None:
        phase = self._focus_phase
        handle = self.models[phase].handle(self.trees[phase].currentIndex())
        # a reference gained/changed its file: its children changed too
        if handle is not None and handle.type == "reference":
            self.refresh(path)
        else:
            index = self.models[phase].index_for_path(path)
            self.models[phase].dataChanged.emit(index, index)
            self.title_changed.emit()

    def _on_current_changed(self, phase: str, current) -> None:
        self._point_at(phase)
        self.settings.set_handle(self.models[phase].handle(current))

    def _on_double_clicked(self, phase: str, index) -> None:
        # publish actions are never individually runnable
        if phase != BUILD:
            return
        handle = self.models[phase].handle(index)
        if handle is not None:
            self.run_step(handle.path)

    # ------------------------------------------------------------ editing
    def show_palette(self) -> None:
        """Open the action palette next to the selection."""
        tree = self.current_tree
        anchor = (
            tree.visualRect(tree.currentIndex())
            if tree.currentIndex().isValid()
            else tree.rect()
        )
        point = tree.viewport().mapToGlobal(anchor.bottomLeft() + QtCore.QPoint(20, 4))
        self.palette.popup(point)

    def add_action(
        self, action_type: str, as_child: bool = False
    ) -> Optional[ActionHandle]:
        """Add ``action_type`` after the selection, or under it with ``as_child``."""
        view = self.session.view(self._focus_phase)
        current = self.current_handle()
        try:
            if current is None:
                handle = view.add(action_type)
            elif as_child:
                if current.is_linked:
                    raise SessionError("Cannot add inside a referenced session.")
                handle = view.add(action_type, parent=current.path)
            else:
                target = current
                while target.is_linked:
                    target = view[target.path.rsplit("/", 1)[0]]
                handle = view.add(action_type, after=target.path)
        except TriggerError as error:
            self.session.events.log(str(error), level="warning")
            return None
        self.refresh(handle.path)
        return handle

    def remove_current(self) -> None:
        """Delete the selected action (not inside a reference)."""
        handle = self.current_handle()
        if handle is None or handle.is_linked:
            return
        self.session.view(self._focus_phase).remove(handle.path)
        self.refresh(None)

    def duplicate_current(self) -> None:
        """Copy the selected action next to itself."""
        handle = self.current_handle()
        if handle is None or handle.is_linked:
            return
        self.refresh(self.session.view(self._focus_phase).duplicate(handle.path).path)

    def rename_current(self) -> None:
        """Start editing the selected action's name in place."""
        tree = self.current_tree
        index = tree.currentIndex()
        if index.isValid() and not self.current_model.handle(index).is_linked:
            tree.edit(index)

    def toggle_current(self) -> None:
        """Flip the selected action's enabled flag."""
        index = self.current_tree.currentIndex()
        if index.isValid():
            self.current_model.toggle(index)

    def add_child_via_palette(self) -> None:
        """Open the palette; the chosen action becomes a child of the selection."""

        def _once(key, _as_child):
            self.palette.chosen.disconnect(_once)
            self.add_action(key, as_child=True)

        self.palette.chosen.connect(_once)
        self.show_palette()

    def context_menu_actions(self, phase: str, handle: Optional[ActionHandle]) -> list:
        """Build the menu for one row and return its entries.

        Split out from ``_context_menu`` so the entries can be read without
        popping a modal menu, which is also how the tests check that publish
        rows carry no run affordance.
        """
        menu = QtWidgets.QMenu(self)
        if handle is not None:
            # publish actions are never individually runnable
            if phase == BUILD:
                menu.addAction("Run step", lambda: self.run_step(handle.path))
                menu.addAction(
                    "Build until here", lambda: self.build_until(handle.path)
                )
                menu.addSeparator()
            menu.addAction(
                "Disable" if handle.enabled else "Enable", self.toggle_current
            )
            if not handle.is_linked:
                menu.addAction("Rename", self.rename_current)
                menu.addAction("Duplicate", self.duplicate_current)
                menu.addAction("Delete", self.remove_current)
            menu.addSeparator()
        menu.addAction("Add action…  (Tab)", self.show_palette)
        child = menu.addAction("Add child action…", self.add_child_via_palette)
        child.setEnabled(handle is not None and not handle.is_linked)
        self._menu = menu  # keep it alive for the caller
        return menu.actions()

    def _context_menu(self, phase: str, point) -> None:
        tree = self.trees[phase]
        index = tree.indexAt(point)
        handle = self.models[phase].handle(index)
        if handle is not None:
            tree.setCurrentIndex(index)
        self.set_focus_phase(phase)
        self.context_menu_actions(phase, handle)
        self._menu.exec_(tree.viewport().mapToGlobal(point))

    # ------------------------------------------------------------ running
    def _step(
        self, path: str, status: str, error: str = "", phase: str = BUILD
    ) -> None:
        self.models.get(phase, self.model).set_status(path, status, error)
        self.activity.emit(f"{status}: {path}" + (f" — {error}" if error else ""))
        QtWidgets.QApplication.processEvents()

    def _on_progress(self, current=0, total=0, label="", **_kw) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(current)
        self.counter.setText(f"{current} / {total}" + (f" · {label}" if label else ""))

    def _run(self, callback) -> bool:
        if self._running:
            return False
        self._running = True
        for model in self.models.values():
            model.clear_status()
        self.build_button.setEnabled(False)
        self.publish_button.setEnabled(False)
        try:
            callback()
            return True
        except (ActionExecutionError, TriggerError) as error:
            self.session.events.log(str(error), level="error")
            return False
        finally:
            self._running = False
            self.build_button.setEnabled(True)
            self.publish_button.setEnabled(True)

    def build(self) -> bool:
        """Run the build list; True when it finished without errors."""
        return self._run(lambda: self.session.build())

    def build_and_publish(self) -> bool:
        """Build the rig from scratch, then run the publish actions."""
        return self._run(lambda: self.session.build(publish=True))

    def build_until(self, path: Optional[str]) -> bool:
        """Run the build list up to and including ``path``."""
        return bool(path) and self._run(lambda: self.session.build(until=path))

    def run_step(self, path: Optional[str]) -> bool:
        """Run the single action at ``path``."""
        return bool(path) and self._run(lambda: self.session.run(path))

    def clear_statuses(self) -> None:
        """Reset every run status, the progress bar and the counter."""
        for model in self.models.values():
            model.clear_status()
        self.progress.setValue(0)
        self.counter.setText("")

    def save_from_scene(self, path: str) -> None:
        """Ask the action at ``path`` to store the scene state into its settings."""
        handle = self.session.view(self._focus_phase)[path]
        action = registry.get_action(handle.type)(settings=handle.settings)
        from tik.trigger.core.action import ActionContext

        ctx = ActionContext(
            session=self.session,
            events=self.session.events,
            base_dir=self.session.directory,
            path=path,
        )
        written = action.save_from_scene(ctx)
        self.session.events.log(f"{path}: saved {len(written)} file(s)")
        self.settings.set_handle(handle)
