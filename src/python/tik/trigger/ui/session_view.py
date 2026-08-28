"""One session tab: shelf | pipeline tree | settings, with the build bar."""

from __future__ import annotations

from typing import Optional

from tik.shared.ui import theme
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.core import registry
from tik.trigger.core.exceptions import ActionExecutionError, SessionError, TriggerError
from tik.trigger.core.runner import STEP_FAILED, STEP_FINISHED, STEP_STARTED
from tik.trigger.handler import ActionHandle, Session

from .delegates import PipelineDelegate
from .model import MIME_TYPE, PipelineModel
from .palette import PaletteEntry, SearchPalette
from .settings_panel import ActionSettingsPanel
from .shelf import Shelf


def action_entries() -> list[PaletteEntry]:
    return [
        PaletteEntry(cls.action_type, cls.display_label(), getattr(cls, "category", "utility"), [cls.description()[:40]])
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
        return False  # keep Tab for the palette


class SessionView(QtWidgets.QWidget):
    """Edit and build one ``Session``."""

    title_changed = QtCore.Signal()
    open_guides_requested = QtCore.Signal(str)  # .trg path

    def __init__(self, session: Session, parent=None, file_browser=None) -> None:
        super().__init__(parent)
        self.session = session
        self.model = PipelineModel(session, self)
        self._build_ui(file_browser)
        self._connect_events()
        self._running = False

    # ------------------------------------------------------------------ ui
    def _build_ui(self, file_browser) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.shelf = Shelf(action_entries(), MIME_TYPE, title="Actions")
        self.shelf.add_requested.connect(lambda key: self.add_action(key, as_child=False))
        body.addWidget(self.shelf)

        self.splitter = QtWidgets.QSplitter()
        self.tree = PipelineTree()
        self.tree.setModel(self.model)
        self.tree.setItemDelegate(PipelineDelegate(self.tree))
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(18)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop)
        self.tree.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.EditKeyPressed | QtWidgets.QAbstractItemView.SelectedClicked)
        self.tree.expandAll()
        self.splitter.addWidget(self.tree)

        self.settings = ActionSettingsPanel(file_browser=file_browser)
        self.splitter.addWidget(self.settings)
        self.splitter.setSizes([420, 420])
        body.addWidget(self.splitter, 1)
        layout.addLayout(body, 1)

        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(10, 6, 10, 6)
        self.build_button = QtWidgets.QPushButton("▶  Build rig")
        self.build_button.setDefault(True)
        self.until_button = QtWidgets.QPushButton("Build until here")
        self.until_button.setFlat(True)
        self.publish_button = QtWidgets.QPushButton("Build && Publish")
        self.publish_button.setFlat(True)
        self.publish_button.setToolTip("Publishing is not wired yet")
        self.publish_button.setEnabled(False)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.counter = QtWidgets.QLabel("")
        self.counter.setStyleSheet(f"color: {theme.TEXT_DIM};")
        bar.addWidget(self.build_button)
        bar.addWidget(self.until_button)
        bar.addWidget(self.publish_button)
        bar.addWidget(self.progress, 1)
        bar.addWidget(self.counter)
        frame = QtWidgets.QFrame()
        frame.setLayout(bar)
        frame.setStyleSheet(f"QFrame {{ background: #2a2a2a; border-top: 1px solid {theme.LINE}; }}")
        layout.addWidget(frame)

        self.palette = SearchPalette(action_entries(), self)
        self.palette.chosen.connect(self.add_action)

        # signals
        self.tree.selectionModel().currentChanged.connect(self._on_current_changed)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.doubleClicked.connect(lambda index: self.run_step(self.model.handle(index).path))
        self.tree.palette_requested.connect(self.show_palette)
        self.model.edited.connect(self._after_edit)
        self.settings.edited.connect(lambda _path: self._after_edit(refresh_tree=False))
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
        self.title_changed.emit()

    def _after_edit(self, refresh_tree: bool = True) -> None:
        if refresh_tree:
            self.tree.expandAll()
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
                while target.is_linked:  # after a linked row = after its reference
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
        self.settings.set_handle(None)

    def duplicate_current(self) -> None:
        handle = self.current_handle()
        if handle is None or handle.is_linked:
            return
        copy = self.session.duplicate(handle.path)
        self.refresh(copy.path)

    def toggle_current(self) -> None:
        index = self.tree.currentIndex()
        if index.isValid():
            self.model.toggle(index)

    def _context_menu(self, point) -> None:
        index = self.tree.indexAt(point)
        handle = self.model.handle(index)
        menu = QtWidgets.QMenu(self)
        if handle is not None:
            self.tree.setCurrentIndex(index)
            menu.addAction("Run", lambda: self.run_step(handle.path))
            menu.addAction("Run until here", lambda: self.build_until(handle.path))
            menu.addSeparator()
            menu.addAction("Disable" if handle.enabled else "Enable", self.toggle_current)
            if not handle.is_linked:
                menu.addAction("Rename", lambda: self.tree.edit(index))
                menu.addAction("Duplicate", self.duplicate_current)
                menu.addAction("Delete", self.remove_current)
            menu.addSeparator()
        menu.addAction("Add action…  (Tab)", self.show_palette)
        add_child = menu.addAction("Add child action…", lambda: self._palette_child())
        add_child.setEnabled(handle is not None and not handle.is_linked)
        menu.exec_(self.tree.viewport().mapToGlobal(point))

    def _palette_child(self) -> None:
        def _once(key, _as_child):
            self.palette.chosen.disconnect(_once)
            self.add_action(key, as_child=True)

        self.palette.chosen.connect(_once)
        self.show_palette()

    # ------------------------------------------------------------ running
    def _step(self, path: str, status: str, error: str = "") -> None:
        self.model.set_status(path, status, error)
        QtWidgets.QApplication.processEvents()

    def _on_progress(self, current=0, total=0, label="", **_kw) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(current)
        self.counter.setText(f"{current} / {total}")

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
        if not path:
            return False
        return self._run(lambda: self.session.build(until=path))

    def run_step(self, path: Optional[str]) -> bool:
        if not path:
            return False
        return self._run(lambda: self.session.run(path))

    def save_from_scene(self, path: str) -> None:
        handle = self.session[path]
        action = registry.get_action(handle.type)(settings=handle.settings)
        from tik.trigger.core.action import ActionContext

        ctx = ActionContext(backend=self.session.backend, session=self.session, events=self.session.events,
                            base_dir=self.session.directory, path=path)
        written = action.save_from_scene(ctx)
        self.session.events.log(f"{path}: saved {len(written)} file(s)")
        self.settings.set_handle(handle)
