"""One session tab: [tile shelf | pipeline | properties] in a splitter + build bar."""

from __future__ import annotations

from typing import Optional

from tik.shared.ui import theme
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.tile_grid import TileEntry, TileGrid
from tik.trigger.core import registry
from tik.trigger.core.exceptions import ActionExecutionError, SessionError, TriggerError
from tik.trigger.core.steps import STEP_FAILED, STEP_FINISHED, STEP_STARTED
from tik.trigger.session import ActionHandle, Session

from .delegates import PipelineDelegate
from .model import MIME_TYPE, PipelineModel
from .palette import PaletteEntry, SearchPalette
from .settings_panel import ActionSettingsPanel


def action_entries() -> list[PaletteEntry]:
    return [
        PaletteEntry(cls.action_type, cls.display_label(), getattr(cls, "category", "utility"), [cls.description()[:40]])
        for cls in registry.iter_actions()
    ]


def tile_entries() -> list[TileEntry]:
    return [
        TileEntry(cls.action_type, cls.display_label(), getattr(cls, "category", "utility"), cls.description()[:80])
        for cls in registry.iter_actions()
    ]


class PipelineTree(QtWidgets.QTreeView):
    palette_requested = QtCore.Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == QtCore.Qt.Key_Tab:
            self.palette_requested.emit()
            return
        super().keyPressEvent(event)

    def focusNextPrevChild(self, next_child: bool) -> bool:  # noqa: N802
        return False


def pane(title: str, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
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

    def __init__(self, session: Session, parent=None, file_browser=None,
                 designer_factory=None, events=None) -> None:
        super().__init__(parent)
        self.session = session
        self.model = PipelineModel(session, self)
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
            self.ensure_designer()
        self.sub_tab_changed.emit(index)

    @property
    def on_designer_tab(self) -> bool:
        return self.sub_tabs.currentIndex() == DESIGNER_TAB

    def teardown(self) -> None:
        """Release the Designer's scene jobs. Safe to call more than once."""
        if self.designer is not None:
            self.designer.teardown()

    # ------------------------------------------------------------------ ui
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

        self.shelf = TileGrid(tile_entries(), MIME_TYPE)
        self.shelf.activated.connect(lambda key: self.add_action(key, as_child=False))
        self.shelf_pane = pane("Actions", self.shelf)
        self.splitter.addWidget(self.shelf_pane)

        self.tree = PipelineTree()
        self.tree.setObjectName("PipelineTree")
        self.tree.setModel(self.model)
        self.tree.setItemDelegate(PipelineDelegate(self.tree))
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(18)
        self.tree.setMouseTracking(True)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop)
        self.tree.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.EditKeyPressed | QtWidgets.QAbstractItemView.SelectedClicked)
        self.tree.setUniformRowHeights(True)
        self.tree.expandAll()
        self.splitter.addWidget(pane("Pipeline", self.tree))

        self.settings = ActionSettingsPanel(file_browser=file_browser, base_dir=lambda: self.session.directory)
        self.splitter.addWidget(self.settings)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 1)
        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, False)
        self.splitter.setCollapsible(2, False)
        self.splitter.setSizes([170, 460, 420])
        layout.addWidget(self.splitter, 1)

        bar_frame = QtWidgets.QFrame()
        bar_frame.setObjectName("BuildBar")
        bar = QtWidgets.QHBoxLayout(bar_frame)
        bar.setContentsMargins(10, 7, 10, 7)
        bar.setSpacing(8)
        self.build_button = QtWidgets.QPushButton("▶  Build rig")
        self.build_button.setObjectName("PrimaryButton")
        self.until_button = QtWidgets.QPushButton("Build until here")
        self.publish_button = QtWidgets.QPushButton("Build && Publish")
        self.publish_button.setToolTip("Publishing is not wired yet")
        self.publish_button.setEnabled(False)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.counter = QtWidgets.QLabel("")
        self.counter.setObjectName("PanelSubtitle")
        bar.addWidget(self.build_button)
        bar.addWidget(self.until_button)
        bar.addWidget(self.publish_button)
        bar.addWidget(self.progress, 1)
        bar.addWidget(self.counter)
        layout.addWidget(bar_frame)

        self.sub_tabs.addTab(session_page, "Session")
        # a placeholder until the Designer is built on first activation
        self._designer_page = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(self._designer_page).setContentsMargins(0, 0, 0, 0)
        self.sub_tabs.addTab(self._designer_page, "Guide Designer")
        self.sub_tabs.currentChanged.connect(self._on_sub_tab_changed)

        self.palette = SearchPalette(action_entries(), self)
        self.palette.chosen.connect(self.add_action)

        self.tree.selectionModel().currentChanged.connect(self._on_current_changed)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.doubleClicked.connect(lambda index: self.run_step(self.model.handle(index).path))
        self.tree.palette_requested.connect(self.show_palette)
        self.model.edited.connect(self._after_edit)
        self.settings.edited.connect(self._on_settings_edited)
        self.settings.run_requested.connect(self.run_step)
        self.settings.run_until_requested.connect(self.build_until)
        self.settings.save_requested.connect(self.save_from_scene)
        self.settings.open_file_requested.connect(lambda path, _ext: self.open_guides_requested.emit(path))
        self.build_button.clicked.connect(self.build)
        self.until_button.clicked.connect(lambda: self.build_until(self.current_path()))

        QtWidgets.QShortcut(QtGui.QKeySequence("Delete"), self.tree, self.remove_current)
        QtWidgets.QShortcut(QtGui.QKeySequence("F5"), self, self.refresh)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+D"), self.tree, self.duplicate_current)

    def _connect_events(self) -> None:
        events = self.session.events
        events.subscribe(STEP_STARTED, lambda path="", **_kw: self._step(path, "running"))
        events.subscribe(STEP_FINISHED, lambda path="", **_kw: self._step(path, "done"))
        events.subscribe(STEP_FAILED, lambda path="", error="", **_kw: self._step(path, "failed", error))
        events.subscribe("progress", self._on_progress)

    # ------------------------------------------------------------ helpers
    @property
    def shelf_visible(self) -> bool:
        return self.splitter.sizes()[0] > 0

    def set_shelf_visible(self, visible: bool) -> None:
        sizes = self.splitter.sizes()
        if visible and sizes[0] == 0:
            sizes[0] = 170
        elif not visible:
            sizes[0] = 0
        self.splitter.setSizes(sizes)

    def current_handle(self) -> Optional[ActionHandle]:
        return self.model.handle(self.tree.currentIndex())

    def current_path(self) -> Optional[str]:
        handle = self.current_handle()
        return handle.path if handle else None

    def select_path(self, path: Optional[str]) -> None:
        if not path:
            return
        index = self.model.index_for_path(path)
        if index.isValid():
            self.tree.setCurrentIndex(index)
            self.tree.scrollTo(index)

    def refresh(self, keep: Optional[str] = None) -> None:
        keep = keep or self.current_path()
        self.model.rebuild()
        self.tree.expandAll()
        self.select_path(keep)
        self.settings.set_handle(self.current_handle())
        self.title_changed.emit()

    def _after_edit(self) -> None:
        self.tree.expandAll()
        self.title_changed.emit()

    def _on_settings_edited(self, path: str) -> None:
        handle = self.session.find(path)
        # a reference gained/changed its file: its children changed too
        if handle is not None and handle.type == "reference":
            self.refresh(path)
        else:
            self.model.dataChanged.emit(self.model.index_for_path(path), self.model.index_for_path(path))
            self.title_changed.emit()

    def _on_current_changed(self, current, _previous) -> None:
        self.settings.set_handle(self.model.handle(current))

    # ------------------------------------------------------------ editing
    def show_palette(self) -> None:
        anchor = self.tree.visualRect(self.tree.currentIndex()) if self.tree.currentIndex().isValid() else self.tree.rect()
        point = self.tree.viewport().mapToGlobal(anchor.bottomLeft() + QtCore.QPoint(20, 4))
        self.palette.popup(point)

    def add_action(self, action_type: str, as_child: bool = False) -> Optional[ActionHandle]:
        current = self.current_handle()
        try:
            if current is None:
                handle = self.session.add(action_type)
            elif as_child:
                if current.is_linked:
                    raise SessionError("Cannot add inside a referenced session.")
                handle = self.session.add(action_type, parent=current.path)
            else:
                target = current
                while target.is_linked:
                    target = self.session[target.path.rsplit("/", 1)[0]]
                handle = self.session.add(action_type, after=target.path)
        except TriggerError as error:
            self.session.events.log(str(error), level="warning")
            return None
        self.refresh(handle.path)
        return handle

    def remove_current(self) -> None:
        handle = self.current_handle()
        if handle is None or handle.is_linked:
            return
        self.session.remove(handle.path)
        self.refresh(None)

    def duplicate_current(self) -> None:
        handle = self.current_handle()
        if handle is None or handle.is_linked:
            return
        self.refresh(self.session.duplicate(handle.path).path)

    def rename_current(self) -> None:
        index = self.tree.currentIndex()
        if index.isValid() and not self.model.handle(index).is_linked:
            self.tree.edit(index)

    def toggle_current(self) -> None:
        index = self.tree.currentIndex()
        if index.isValid():
            self.model.toggle(index)

    def add_child_via_palette(self) -> None:
        def _once(key, _as_child):
            self.palette.chosen.disconnect(_once)
            self.add_action(key, as_child=True)

        self.palette.chosen.connect(_once)
        self.show_palette()

    def _context_menu(self, point) -> None:
        index = self.tree.indexAt(point)
        handle = self.model.handle(index)
        menu = QtWidgets.QMenu(self)
        if handle is not None:
            self.tree.setCurrentIndex(index)
            menu.addAction("Run step", lambda: self.run_step(handle.path))
            menu.addAction("Build until here", lambda: self.build_until(handle.path))
            menu.addSeparator()
            menu.addAction("Disable" if handle.enabled else "Enable", self.toggle_current)
            if not handle.is_linked:
                menu.addAction("Rename", self.rename_current)
                menu.addAction("Duplicate", self.duplicate_current)
                menu.addAction("Delete", self.remove_current)
            menu.addSeparator()
        menu.addAction("Add action…  (Tab)", self.show_palette)
        child = menu.addAction("Add child action…", self.add_child_via_palette)
        child.setEnabled(handle is not None and not handle.is_linked)
        menu.exec_(self.tree.viewport().mapToGlobal(point))

    # ------------------------------------------------------------ running
    def _step(self, path: str, status: str, error: str = "") -> None:
        self.model.set_status(path, status, error)
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
        self.model.clear_status()
        self.build_button.setEnabled(False)
        try:
            callback()
            return True
        except (ActionExecutionError, TriggerError) as error:
            self.session.events.log(str(error), level="error")
            return False
        finally:
            self._running = False
            self.build_button.setEnabled(True)

    def build(self) -> bool:
        return self._run(lambda: self.session.build())

    def build_until(self, path: Optional[str]) -> bool:
        return bool(path) and self._run(lambda: self.session.build(until=path))

    def run_step(self, path: Optional[str]) -> bool:
        return bool(path) and self._run(lambda: self.session.run(path))

    def clear_statuses(self) -> None:
        self.model.clear_status()
        self.progress.setValue(0)
        self.counter.setText("")

    def save_from_scene(self, path: str) -> None:
        handle = self.session[path]
        action = registry.get_action(handle.type)(settings=handle.settings)
        from tik.trigger.core.action import ActionContext

        ctx = ActionContext(session=self.session, events=self.session.events,
                            base_dir=self.session.directory, path=path)
        written = action.save_from_scene(ctx)
        self.session.events.log(f"{path}: saved {len(written)} file(s)")
        self.settings.set_handle(handle)
