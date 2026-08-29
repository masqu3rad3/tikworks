"""Guide Designer: dockable tool window — modules · tree · graph · properties.

Tree and graph are two views of the same connections (see ``Guides``);
the properties panel shows the module's Inputs first. Connections are data
only: the designer never parents guide joints into each other and never
selects joints in Maya on its own — use *Select guides* for that. Scene
structure changes (new/removed/undone guides) reach the UI through a
debounced ``SceneWatcher``; our own edits are muted.

Everything the designer authors (connections, scene-node groups, node
positions, collapse modes) lives in ``Guides`` / ``Guides.layout`` and is
exported with the ``.trg``; only window geometry and selection are transient.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tik.core.side import Side
from tik.shared.ui import theme
from tik.shared.ui.binding import BindingManager, bind
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.filter_bar import FilterBar
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.maya_window import MayaToolWindow
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.scene_watcher import SceneWatcher
from tik.shared.ui.status import StatusFields
from tik.shared.ui.tile_grid import TileEntry, TileGrid
from tik.trigger.core import registry
from tik.trigger.core.builder import split_source
from tik.trigger.core.exceptions import TriggerError
from tik.trigger.guides import EXTENSION as GUIDE_EXTENSION
from tik.trigger.guides import GuideHandle, Guides

from .graph_view import GraphView
from .palette import PaletteEntry, SearchPalette
from .session_view import pane

MIME_MODULE = "application/x-trigger-module-type"
SIDES = ("L", "R", "C", "Both", "Auto")
SCENE_NODE = "__scene_node__"  # pseudo module: a group of arbitrary scene nodes modules can connect to
MODULE_COLORS = {"body": "#c9a24a", "limbs": "#5b8fd0", "generic": "#7fa86a", "face": "#b86b9a", "scene": "#8a93a0"}
MODULE_CATEGORY = {"base": "body", "spine": "body", "head": "body", "arm": "limbs", "leg": "limbs",
                   "finger": "limbs", "fkchain": "generic", "tail": "generic", "surface": "generic"}


def module_entries():
    tiles, palette = [], []
    for module_cls in registry.iter_modules():
        category = MODULE_CATEGORY.get(module_cls.module_type, "generic")
        tiles.append(TileEntry(module_cls.module_type, module_cls.display_label(), category))
        palette.append(PaletteEntry(module_cls.module_type, module_cls.display_label(), category))
    tiles.append(TileEntry(SCENE_NODE, "Scene", "scene"))
    palette.append(PaletteEntry(SCENE_NODE, "Scene Nodes", "scene"))
    return tiles, palette


class GuideTree(QtWidgets.QTreeWidget):
    """Instances tree; dragging a row onto another sets its primary input."""

    reparent_requested = QtCore.Signal(str, object)  # instance_id, parent instance_id or None
    palette_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideTree")
        self.setHeaderLabels(["Module", "Type", "Side", "Primary input"])
        header = self.header()
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(30)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)
        self.setColumnWidth(0, 150)
        for column in (1, 2):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == QtCore.Qt.Key_Tab:
            self.palette_requested.emit()
            return
        super().keyPressEvent(event)

    def focusNextPrevChild(self, next_child: bool) -> bool:  # noqa: N802
        return False

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != QtCore.Qt.LeftButton:
            # middle/right must never start a drag (a middle drag crashed Maya)
            self.setDragEnabled(False)
            try:
                super().mousePressEvent(event)
            finally:
                self.setDragEnabled(True)
            return
        super().mousePressEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        target = self.itemAt(position)
        moved = self.currentItem()
        event.setDropAction(QtCore.Qt.IgnoreAction)
        event.accept()
        if moved is None:
            return
        moved_id = moved.data(0, QtCore.Qt.UserRole)
        target_id = target.data(0, QtCore.Qt.UserRole) if target is not None else None
        if target_id != moved_id:
            # rebuilding the tree while Qt is still inside the drop crashes; do it next tick
            QtCore.QTimer.singleShot(0, lambda: self.reparent_requested.emit(moved_id, target_id))


class InputRow(QtWidgets.QWidget):
    """One input: source editor + "from selection" + clear.

    Right-click the field for a menu of every other module (submenu = its
    outputs) and the scene nodes of every group.
    """

    changed = QtCore.Signal(str, str)  # input name, source ("" = disconnect)

    def __init__(self, input_decl, parent=None, picker=None, sources=None) -> None:
        super().__init__(parent)
        self.input = input_decl
        self.picker = picker
        self.sources = sources  # callable -> (modules: [(key, label, [outputs])], scene_nodes: [(group, node)])
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.line = QtWidgets.QLineEdit()
        self.line.setPlaceholderText("module.output or scene node" + ("  (optional)" if input_decl.optional else ""))
        self.pick = QtWidgets.QToolButton()
        self.pick.setText("◦")
        self.pick.setToolTip("Use the selected guide (its module output) or scene node")
        self.clear = QtWidgets.QToolButton()
        self.clear.setText("×")
        self.clear.setToolTip("Disconnect")
        layout.addWidget(self.line, 1)
        layout.addWidget(self.pick)
        layout.addWidget(self.clear)
        self.line.editingFinished.connect(lambda: self.changed.emit(self.input.name, self.line.text().strip()))
        self.line.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.line.customContextMenuRequested.connect(self._menu)
        self.pick.clicked.connect(self._pick)
        self.clear.clicked.connect(lambda: (self.line.setText(""), self.changed.emit(self.input.name, "")))

    def set_source(self, source: str) -> None:
        self.line.setText(source or "")

    def choose(self, source: str) -> None:
        self.line.setText(source)
        self.changed.emit(self.input.name, source)

    def build_menu(self, parent=None) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(parent or self)
        modules, scene_nodes = self.sources() if self.sources else ([], [])
        for key, label, outputs in modules:
            sub = menu.addMenu(f"{key}  ·  {label}")
            for output in outputs:
                sub.addAction(output, lambda source=f"{key}.{output}": self.choose(source))
        if scene_nodes:
            if modules:
                menu.addSeparator()
            groups: dict[str, QtWidgets.QMenu] = {}
            for group, node in scene_nodes:
                sub = groups.get(group)
                if sub is None:
                    sub = groups[group] = menu.addMenu(f"{group}  ·  scene nodes")
                sub.addAction(node, lambda source=node: self.choose(source))
        if not modules and not scene_nodes:
            menu.addAction("No other modules or scene nodes").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Disconnect", lambda: self.choose(""))
        return menu

    def _menu(self, point) -> None:
        self.build_menu().exec(self.line.mapToGlobal(point))

    def _pick(self) -> None:
        if self.picker is None:
            return
        source = self.picker()
        if source:
            self.line.setText(source)
            self.changed.emit(self.input.name, source)


class SceneNodesPanel(QtWidgets.QWidget):
    """Outputs of a scene-nodes group: one scene node per row, pickable from the Maya selection."""

    changed = QtCore.Signal(list)  # new node list

    def __init__(self, parent=None, picker=None) -> None:
        super().__init__(parent)
        self.picker = picker  # callable -> [selected scene node names]
        self.rows: list[QtWidgets.QLineEdit] = []
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        caption = QtWidgets.QLabel("SCENE NODES")
        caption.setObjectName("FieldCaption")
        layout.addWidget(caption)
        self.rows_layout = QtWidgets.QVBoxLayout()
        self.rows_layout.setSpacing(4)
        layout.addLayout(self.rows_layout)
        buttons = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton("+ Add")
        self.add_button.setToolTip("Add a row (pre-filled from the Maya selection)")
        self.add_selected_button = QtWidgets.QPushButton("< Add selected")
        self.add_selected_button.setToolTip("One row per selected Maya node")
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.add_selected_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)
        self.add_button.clicked.connect(lambda: self._add_rows([self._picked()[:1] or [""]][0] or [""]))
        self.add_selected_button.clicked.connect(lambda: self._add_rows(self._picked() or [""]))

    def _picked(self) -> list[str]:
        return list(self.picker() or []) if self.picker else []

    def set_nodes(self, nodes: list[str]) -> None:
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.rows = []
        for node in nodes:
            self._append_row(node)

    def nodes(self) -> list[str]:
        return [row.text().strip() for row in self.rows if row.text().strip()]

    def _append_row(self, node: str) -> QtWidgets.QLineEdit:
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        line = QtWidgets.QLineEdit(node)
        line.setPlaceholderText("scene node name")
        pick = QtWidgets.QToolButton()
        pick.setText("<")
        pick.setToolTip("Use the selected Maya node")
        remove = QtWidgets.QToolButton()
        remove.setText("×")
        row.addWidget(line, 1)
        row.addWidget(pick)
        row.addWidget(remove)
        self.rows_layout.addWidget(holder)
        self.rows.append(line)
        line.editingFinished.connect(self._emit)
        pick.clicked.connect(lambda: (line.setText((self._picked() or [line.text()])[0]), self._emit()))
        remove.clicked.connect(lambda: self._remove(line, holder))
        return line

    def _add_rows(self, names: list[str]) -> None:
        for name in names:
            self._append_row(name)
        if names and not names[-1]:
            self.rows[-1].setFocus()
        self._emit()

    def _remove(self, line, holder) -> None:
        self.rows.remove(line)
        holder.deleteLater()
        self._emit()

    def _emit(self) -> None:
        self.changed.emit(self.nodes())


class GuideDesigner(MayaToolWindow):
    WINDOW_NAME = "TriggerGuideDesigner"

    def __init__(self, backend, parent=None, events=None, file_browser=None, binding_adapter=None) -> None:
        super().__init__(parent)
        self.backend = backend
        self.guides = Guides(backend, events)
        self.events = self.guides.events
        self.file_browser = file_browser
        self.binding_adapter = binding_adapter
        self.file_path: str = ""
        self.bindings = BindingManager()
        self._current: Optional[GuideHandle] = None
        self._multi: list[GuideHandle] = []  # every selected module when they share a type
        self._external: Optional[str] = None  # selected scene-nodes group (graph only)
        self._module_obj = None
        self._input_rows: dict[str, InputRow] = {}
        self._syncing = False
        self.setWindowTitle("Guide Designer")
        self.resize(1240, 680)
        self._build_central()
        self._build_menus()
        self._build_status()
        theme.apply(self)
        self.watcher = SceneWatcher(
            self._on_scene_event,
            install_job=getattr(backend, "install_scene_job", None),
            kill_job=getattr(backend, "kill_scene_job", None),
            parent=self,
        )
        self.watcher.install()
        self.refresh()

    # ------------------------------------------------------------------ ui
    def _build_central(self) -> None:
        tiles, palette_entries = module_entries()
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.splitter.setHandleWidth(6)

        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)
        header = QtWidgets.QLabel("SIDE")
        header.setObjectName("PaneHeader")
        left_layout.addWidget(header)
        self.side_combo = QtWidgets.QComboBox()
        self.side_combo.addItems(SIDES)
        self.side_combo.setToolTip("Side of the modules you add next (Both = L and R, Auto = follow the selected module)")
        left_layout.addWidget(self.side_combo)
        modules_header = QtWidgets.QLabel("MODULES")
        modules_header.setObjectName("PaneHeader")
        left_layout.addWidget(modules_header)
        self.shelf = TileGrid(tiles, MIME_MODULE, colors=MODULE_COLORS)
        self.shelf.activated.connect(lambda key: self.create_guides(key))
        left_layout.addWidget(self.shelf, 1)
        self.splitter.addWidget(left)

        self.tree = GuideTree()
        self.tree_filter = FilterBar(placeholder="Filter modules…  (Enter to keep a keyword)")
        tree_holder = QtWidgets.QWidget()
        tree_layout = QtWidgets.QVBoxLayout(tree_holder)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(6)
        tree_layout.addWidget(self.tree_filter)
        tree_layout.addWidget(self.tree, 1)
        self.tree_pane = pane("Tree", tree_holder)
        self.splitter.addWidget(self.tree_pane)

        self.graph = GraphView(self.guides, events=self.events)
        self.graph_pane = pane("Graph", self.graph)
        self.splitter.addWidget(self.graph_pane)

        self.properties = QtWidgets.QWidget()
        props = QtWidgets.QVBoxLayout(self.properties)
        props.setContentsMargins(12, 10, 12, 10)
        props.setSpacing(8)
        head = QtWidgets.QHBoxLayout()
        self.icon = QtWidgets.QLabel()
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("instance name")
        self.type_label = QtWidgets.QLabel("")
        self.type_label.setObjectName("PanelSubtitle")
        head.addWidget(self.icon)
        head.addWidget(self.name_edit, 1)
        head.addWidget(self.type_label)
        props.addLayout(head)
        self.multi_label = QtWidgets.QLabel("")
        self.multi_label.setObjectName("LinkedNote")
        self.multi_label.setVisible(False)
        props.addWidget(self.multi_label)
        self.inputs_caption = QtWidgets.QLabel("INPUTS")
        self.inputs_caption.setObjectName("FieldCaption")
        props.addWidget(self.inputs_caption)
        self.inputs_form = QtWidgets.QFormLayout()
        self.inputs_form.setContentsMargins(4, 0, 4, 4)
        props.addLayout(self.inputs_form)
        self.guides_caption = QtWidgets.QLabel("GUIDES")
        self.guides_caption.setObjectName("FieldCaption")
        props.addWidget(self.guides_caption)
        self.inherit_orientation = QtWidgets.QCheckBox("Inherit orientation from guides")
        props.addWidget(self.inherit_orientation)
        self.module_caption = QtWidgets.QLabel("MODULE")
        self.module_caption.setObjectName("FieldCaption")
        props.addWidget(self.module_caption)
        self.form = FormBuilder()
        self.form_scroll = QtWidgets.QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.form_scroll.setWidget(self.form)
        props.addWidget(self.form_scroll, 1)
        self.scene_panel = SceneNodesPanel(picker=self._selected_scene_nodes)
        self.scene_panel.setVisible(False)
        props.addWidget(self.scene_panel, 1)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.select_button = QtWidgets.QPushButton("Select guides")
        self.mirror_button = QtWidgets.QPushButton("Mirror")
        self.test_button = QtWidgets.QPushButton("Build selected")
        self.build_all_button = QtWidgets.QPushButton("Build all")
        self.build_all_button.setObjectName("PrimaryButton")
        for button in (self.select_button, self.mirror_button, self.test_button, self.build_all_button):
            buttons.addWidget(button)
        props.addLayout(buttons)
        self.splitter.addWidget(self.properties)

        for index, stretch in enumerate((0, 1, 2, 1)):
            self.splitter.setStretchFactor(index, stretch)
        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, True)
        self.splitter.setCollapsible(2, True)
        self.splitter.setCollapsible(3, False)
        self.splitter.setSizes([170, 280, 520, 270])
        self.setCentralWidget(self.splitter)

        self.palette = SearchPalette(palette_entries, self, colors=MODULE_COLORS)
        self.palette.chosen.connect(lambda key, _child: self.create_guides(key))

        self.tree_filter.filter_changed.connect(self.apply_tree_filter)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        self.tree.reparent_requested.connect(self.reparent)
        self.tree.palette_requested.connect(self.show_palette)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.graph.palette_requested.connect(self.show_palette)
        self.graph.selection_changed.connect(self._on_graph_selection)
        self.graph.external_selection_changed.connect(self._on_external_selection)
        self.graph.node_menu_requested.connect(lambda _key, pos: self.module_menu().exec(pos))
        self.graph.edited.connect(lambda: self.refresh(keep_graph=True))
        self.select_button.clicked.connect(self.select_current)
        self.mirror_button.clicked.connect(self.mirror_current)
        self.test_button.clicked.connect(lambda: self.test_build())
        self.build_all_button.clicked.connect(lambda: self.test_build(all_modules=True))
        self.name_edit.editingFinished.connect(self._rename_current)
        self.form.changed.connect(self._on_setting_changed)
        self.form.error.connect(lambda _name, message: self.events.log(message, level="warning"))
        self.scene_panel.changed.connect(self._on_scene_nodes_changed)
        QtWidgets.QShortcut(QtGui.QKeySequence("Delete"), self.tree, self.delete_current)

    def _action(self, menu, text, slot, shortcut=None, checkable=False):
        action = menu.addAction(text)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        if checkable:
            action.setCheckable(True)
        return action

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        self._action(file_menu, "Clear Scene Guides", self.clear_guides)
        file_menu.addSeparator()
        self._action(file_menu, "Import .trg…", lambda: self.import_file(), "Ctrl+O")
        self._action(file_menu, "Export .trg…", lambda: self.export_file(ask=True), "Ctrl+S")
        self._action(file_menu, "Export Selected…", lambda: self.export_file(ask=True, selected=True))
        file_menu.addSeparator()
        self._action(file_menu, "Close", self.close, "Ctrl+W")
        edit_menu = bar.addMenu("&Edit")
        self._action(edit_menu, "Add Module…", self.show_palette, "Tab")
        self._action(edit_menu, "Add Scene Nodes", lambda: self.create_guides(SCENE_NODE), "Ctrl+N")
        edit_menu.addSeparator()
        self._action(edit_menu, "Select Root", self.select_root)
        self._action(edit_menu, "Select All Guides", self.select_current)
        self._action(edit_menu, "Mirror", self.mirror_current, "Ctrl+M")
        self._action(edit_menu, "Rename", lambda: self.name_edit.setFocus(), "F2")
        self._action(edit_menu, "Delete", self.delete_current)
        edit_menu.addSeparator()
        self._action(edit_menu, "Connect Input…", self.connect_dialog)
        self._action(edit_menu, "Disconnect Primary Input", self.disconnect_primary)
        self._action(edit_menu, "Sever Connections", self.sever_current, "Ctrl+D")
        view_menu = bar.addMenu("&View")
        self.tree_action = self._action(view_menu, "Tree", lambda: self.set_pane_visible(self.tree_pane, self.tree_action.isChecked()), checkable=True)
        self.graph_action = self._action(view_menu, "Graph", lambda: self.set_pane_visible(self.graph_pane, self.graph_action.isChecked()), checkable=True)
        self.tree_action.setChecked(True)
        self.graph_action.setChecked(True)
        view_menu.addSeparator()
        self.grid_action = self._action(view_menu, "Grid", lambda: self.graph.set_grid(self.grid_action.isChecked()), "G", checkable=True)
        self.snap_action = self._action(view_menu, "Snap to Grid", lambda: self.graph.set_snap(self.snap_action.isChecked()), "Shift+G", checkable=True)
        self.grid_action.setChecked(True)
        self.snap_action.setChecked(True)
        self._action(view_menu, "Auto Layout", self.graph.auto_layout, "Ctrl+L")
        self._action(view_menu, "Fit Graph", self.graph.fit, "F")
        view_menu.addSeparator()
        self._action(view_menu, "Collapse: Header Only", lambda: self.graph.set_selected_mode(0), "1")
        self._action(view_menu, "Collapse: Connected Plugs", lambda: self.graph.set_selected_mode(1), "2")
        self._action(view_menu, "Collapse: Everything", lambda: self.graph.set_selected_mode(2), "3")
        view_menu.addSeparator()
        self._action(view_menu, "Refresh", self.refresh, "F5")
        build_menu = bar.addMenu("&Build")
        self._action(build_menu, "Build Selected", lambda: self.test_build(), "Ctrl+B")
        self._action(build_menu, "Build All", lambda: self.test_build(all_modules=True), "Ctrl+Shift+B")
        help_menu = bar.addMenu("&Help")
        self._action(help_menu, "About Guide Designer", lambda: QtWidgets.QMessageBox.about(self, "Guide Designer", "Author module guides and connections; export a .trg for the Kinematics action."))
        for action in (self.grid_action, self.snap_action):
            action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
            self.graph.addAction(action)

    def module_menu(self) -> QtWidgets.QMenu:
        """Right-click menu for the selected module(s); shared by the tree and the graph."""
        menu = QtWidgets.QMenu(self)
        handles = self.selected_handles()
        menu.addAction("Select root", self.select_root)
        menu.addAction("Select all guides", self.select_current)
        menu.addSeparator()
        menu.addAction("Mirror", self.mirror_current)
        menu.addAction("Build", lambda: self.test_build())
        menu.addSeparator()
        menu.addAction("Sever connections", self.sever_current)
        menu.addAction("Disconnect primary input", self.disconnect_primary)
        menu.addSeparator()
        menu.addAction("Rename", lambda: (self.name_edit.setFocus(), self.name_edit.selectAll()))
        menu.addAction("Delete", self.delete_current)
        for action in menu.actions():
            if not action.isSeparator():
                action.setEnabled(bool(handles))
        return menu

    def _tree_menu(self, point) -> None:
        item = self.tree.itemAt(point)
        if item is not None and not item.isSelected():
            self.tree.setCurrentItem(item)
        self.module_menu().exec(self.tree.viewport().mapToGlobal(point))

    def _build_status(self) -> None:
        self.status = StatusFields(self.statusBar(), ("modules", "connections", "file"))
        self.status.set_activity("Ready")

    # ------------------------------------------------------------ state
    @property
    def side(self) -> str:
        return self.side_combo.currentText() or "L"

    def set_side(self, side: str) -> None:
        index = self.side_combo.findText(side)
        if index >= 0:
            self.side_combo.setCurrentIndex(index)

    @property
    def current(self) -> Optional[GuideHandle]:
        return self._current

    def set_pane_visible(self, widget, visible: bool) -> None:
        widget.setVisible(visible)

    def selected_handles(self) -> list[GuideHandle]:
        handles = []
        for item in self.tree.selectedItems():
            handle = self.guides.get(item.data(0, QtCore.Qt.UserRole))
            if handle is not None:
                handles.append(handle)
        return handles

    def set_file(self, path: str) -> None:
        self.file_path = path
        self.status.set("file", Path(path).name if path else "")
        self.setWindowTitle(f"Guide Designer — {Path(path).name}" if path else "Guide Designer")

    # --------------------------------------------------------------- refresh
    def refresh(self, *_args, keep_graph: bool = False) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            keep = [handle.instance_id for handle in (self._multi or ([self._current] if self._current else []))]
            self.guides.invalidate()  # one scene scan per refresh; handles share it
            handles = self.guides.instances()
            by_key = {handle.key: handle for handle in handles}
            self._clear_tree()
            items: dict[str, QtWidgets.QTreeWidgetItem] = {}
            pending = list(handles)
            # parent in the tree = the primary input's producer
            def parent_key(handle):
                primary = handle.module_class.primary_input()
                source = handle.inputs.get(primary.name) if primary else None
                key, _output = split_source(source) if source else (None, None)
                return key if key in by_key else None

            while pending:
                remaining = []
                for handle in pending:
                    p_key = parent_key(handle)
                    if p_key and by_key[p_key].instance_id not in items:
                        remaining.append(handle)
                        continue
                    instance = handle.instance
                    module_cls = handle.module_class
                    label = module_cls.display_label()
                    if module_cls.guides.multi:
                        count = sum(1 for role, _index in instance.guide_pairs if role == module_cls.guides.multi)
                        label = f"{label} · {count}"
                    primary = module_cls.primary_input()
                    primary_text = handle.inputs.get(primary.name, "") if primary else ""
                    item = QtWidgets.QTreeWidgetItem([handle.key, label, instance.side, primary_text or "—"])
                    item.setData(0, QtCore.Qt.UserRole, handle.instance_id)
                    item.setIcon(0, glyph_icon(initials(module_cls.display_label()), theme.SIDE.get(instance.side, theme.SIDE["C"])))
                    item.setFlags(item.flags() | QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsDropEnabled)
                    if p_key:
                        items[by_key[p_key].instance_id].addChild(item)
                    else:
                        self.tree.addTopLevelItem(item)
                    items[handle.instance_id] = item
                if len(remaining) == len(pending):
                    for handle in remaining:  # cycles / unresolved: flat
                        item = QtWidgets.QTreeWidgetItem([handle.key, handle.module_class.display_label(), handle.side.value, "?"])
                        item.setData(0, QtCore.Qt.UserRole, handle.instance_id)
                        self.tree.addTopLevelItem(item)
                        items[handle.instance_id] = item
                    break
                pending = remaining
            self.tree.expandAll()
            self.apply_tree_filter()
            self.graph.rebuild()
            connections = self.guides.connections()
            externals = [item["source"] for item in connections if split_source(item["source"])[0] not in by_key]
            missing = [name for name in externals if getattr(self.backend, "scene_node", lambda _n: True)(name) is None]
            self.status.set("modules", f"{len(handles)} module(s)")
            self.status.set("connections", f"{len(connections)} connection(s)" + (f" · {len(missing)} missing scene node(s)" if missing else ""))
            kept = [items[instance_id] for instance_id in keep if instance_id in items]
            if kept:
                self.tree.setCurrentItem(kept[0], 0, QtCore.QItemSelectionModel.NoUpdate)
                for item in kept:
                    item.setSelected(True)
                self._select_handles([self.guides.get(item.data(0, QtCore.Qt.UserRole)) for item in kept])
            elif self._external is not None and self._external in self.graph.graph.nodes:
                self.graph.select_key(self._external)
                self._set_current_external(self._external)
            else:
                self._set_current(None)
        finally:
            self._syncing = False

    def _clear_tree(self) -> None:
        """Drop every row without Qt signalling into a half-torn-down tree (PySide crashed on plain clear())."""
        tree = self.tree
        tree.blockSignals(True)
        try:
            tree.setCurrentItem(None)
            tree.clearSelection()
            while tree.topLevelItemCount():
                item = tree.takeTopLevelItem(0)
                item.takeChildren()
        finally:
            tree.blockSignals(False)

    def apply_tree_filter(self) -> None:
        """Hide rows that match no keyword; a row stays when any descendant matches."""
        model = self.tree_filter.model

        def visit(item) -> bool:
            text = " ".join(item.text(column) for column in range(item.columnCount()))
            shown = model.matches(text)
            for index in range(item.childCount()):
                shown = visit(item.child(index)) or shown
            item.setHidden(not shown)
            return shown

        for index in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(index))
        hidden = 0
        iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            hidden += iterator.value().isHidden()
            iterator += 1
        total = len(self.guides.instances())
        self.status.set("modules", f"{total - hidden} of {total} module(s)" if model.is_active else f"{total} module(s)")

    def item_for(self, instance_id: str) -> Optional[QtWidgets.QTreeWidgetItem]:
        iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, QtCore.Qt.UserRole) == instance_id:
                return item
            iterator += 1
        return None

    # ----------------------------------------------------------- selection
    def _select_handles(self, handles: list[GuideHandle], sync_graph: bool = True) -> None:
        """Properties for one module, or for several of the same type (edited together)."""
        handles = [handle for handle in handles if handle is not None]
        if sync_graph:
            self.graph.select_keys([handle.key for handle in handles])
        if len(handles) <= 1:
            self._set_current(handles[0] if handles else None)
            return
        types = {handle.module_type for handle in handles}
        if len(types) == 1:
            self._set_current(handles[0], group=handles)
        else:
            self._set_current(None)
            self.multi_label.setText(f"{len(handles)} modules of {len(types)} different types — nothing to edit together.")
            self.multi_label.setVisible(True)
            self.status.set_activity(f"{len(handles)} modules selected (mixed types)")

    def _on_tree_selection(self) -> None:
        if self._syncing:
            return
        self._select_handles(self.selected_handles())

    def _on_external_selection(self, name: str) -> None:
        self._syncing = True
        try:
            self.tree.clearSelection()
        finally:
            self._syncing = False
        self._set_current_external(name)

    def _set_current_external(self, name: str) -> None:
        """Properties for a scene-nodes group: its name and the scene nodes it exposes."""
        self._set_current(None)
        self._external = name
        self.name_edit.setText(name)
        self.name_edit.setEnabled(True)
        self.name_edit.setPlaceholderText("scene nodes group name")
        self.type_label.setText("Scene nodes")
        self.icon.setPixmap(glyph_icon("SN", MODULE_COLORS["scene"], 24).pixmap(24, 24))
        for widget in (self.inputs_caption, self.guides_caption, self.inherit_orientation, self.module_caption, self.form_scroll):
            widget.setVisible(False)
        self.scene_panel.set_nodes(self.guides.scene_groups().get(name, []))
        self.scene_panel.setVisible(True)
        self.status.set_activity(f"{name} — scene nodes (each row is an output; Delete removes the group)")

    def _on_graph_selection(self, key: str) -> None:
        handle = self.guides.by_key(key)
        if handle is None:
            return
        selected = {node.key for node in self.graph.graph.selected_nodes()}
        self._syncing = True
        try:
            self.tree.clearSelection()
            first = None
            for item_handle in self.guides.instances():
                if item_handle.key in selected:
                    item = self.item_for(item_handle.instance_id)
                    if item is not None:
                        item.setSelected(True)
                        first = first or item
            if first is not None:
                self.tree.setCurrentItem(first, 0, QtCore.QItemSelectionModel.NoUpdate)  # keep the others selected
        finally:
            self._syncing = False
        handles = self.selected_handles() or [handle]
        self._select_handles(handles, sync_graph=False)  # never fight a rubber band in progress

    def _on_scene_event(self, name: str) -> None:
        if name == "SelectionChanged":
            return  # selection is not synced; structure changes are
        self.refresh()

    # ---------------------------------------------------------- properties
    def _set_current(self, handle: Optional[GuideHandle], group: Optional[list[GuideHandle]] = None) -> None:
        self._current = handle
        self._multi = list(group or [])
        self._external = None
        self.bindings.clear()
        while self.inputs_form.count():
            item = self.inputs_form.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
                item.widget().deleteLater()
        self._input_rows.clear()
        self.scene_panel.setVisible(False)
        for widget in (self.guides_caption, self.inherit_orientation, self.module_caption, self.form_scroll):
            widget.setVisible(True)
        self.multi_label.setVisible(False)
        self.name_edit.setEnabled(True)
        self.name_edit.setPlaceholderText("instance name")
        if handle is None:
            self._module_obj = None
            self.form.set_target(None)
            self.name_edit.setText("")
            self.type_label.setText("")
            self.icon.clear()
            self.inputs_caption.setVisible(False)
            self.inherit_orientation.setEnabled(False)
            self.status.set_activity("Select a module, or add one from the shelf (Tab to search).")
            return
        instance = handle.instance
        module_cls = handle.module_class
        self._module_obj = module_cls(name=instance.name, side=instance.side, settings=instance.settings)
        self.name_edit.setText(instance.name)
        self.type_label.setText(f"{module_cls.display_label()} · {instance.side}")
        self.icon.setPixmap(glyph_icon(initials(module_cls.display_label()), theme.SIDE.get(instance.side, theme.SIDE["C"]), 24).pixmap(24, 24))
        multi = len(self._multi) > 1
        if multi:
            self.name_edit.setEnabled(False)
            self.name_edit.setText(", ".join(item.key for item in self._multi))
            self.multi_label.setText(f"Editing {len(self._multi)} {module_cls.display_label()} modules together — every change applies to all of them.")
            self.multi_label.setVisible(True)
            self.inputs_caption.setVisible(False)
        else:
            for declared in module_cls.inputs:
                row = InputRow(declared, picker=self._pick_source, sources=self._source_choices)
                row.set_source(handle.inputs.get(declared.name, ""))
                row.changed.connect(self._on_input_changed)
                label = declared.name + (" ●" if declared.primary else "")
                self.inputs_form.addRow(label, row)
                self._input_rows[declared.name] = row
            self.inputs_caption.setVisible(bool(module_cls.inputs))
        self.form.set_target(self._module_obj)
        self.inherit_orientation.setEnabled(True)
        if not multi:
            self._bind_properties(handle)
            self.status.set_activity(f"{handle.key} — {module_cls.display_label()}")
        else:
            self.status.set_activity(f"{len(self._multi)} × {module_cls.display_label()} selected")

    def _bind_properties(self, handle: GuideHandle) -> None:
        plug_factory = getattr(self.backend, "settings_plug", None)
        if plug_factory is None:
            return
        for name in self._module_obj.fields():
            widget = self.form._widgets.get(name)
            if widget is None or not isinstance(widget, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox, QtWidgets.QCheckBox, QtWidgets.QComboBox, QtWidgets.QLineEdit)):
                continue
            try:
                plug = plug_factory(handle.instance_id, name)
            except TriggerError:
                continue
            plug_path = plug if isinstance(plug, str) else plug.path
            adapter = self.binding_adapter(plug_path) if self.binding_adapter else None
            self.bindings.add(bind(plug_path, widget, direction="to_widget", adapter=adapter))
        try:
            plug = plug_factory(handle.instance_id, "useRefOri")
            plug_path = plug if isinstance(plug, str) else plug.path
            adapter = self.binding_adapter(plug_path) if self.binding_adapter else None
            self.bindings.add(bind(plug_path, self.inherit_orientation, direction="both", adapter=adapter))
        except TriggerError:
            pass

    def _source_choices(self):
        """Every other module (with its outputs) and the scene nodes of every group."""
        current = self._current.instance_id if self._current else None
        modules = [
            (handle.key, handle.module_class.display_label(), list(handle.outputs))
            for handle in self.guides.instances()
            if handle.instance_id != current and handle.outputs
        ]
        return modules, self.graph.scene_nodes()

    def _selected_scene_nodes(self) -> list[str]:
        picker = getattr(self.backend, "selected_node_names", None)
        if picker is not None:
            return list(picker() or [])
        name = getattr(self.backend, "selected_node_name", lambda: "")()
        return [name] if name else []

    def _pick_source(self) -> str:
        picked = self.backend.selected_guide() if hasattr(self.backend, "selected_guide") else None
        if picked is not None:
            handle = self.guides.get(picked.instance_id)
            if handle is not None:
                output = handle.module_class.output_for_role(picked.role)
                return f"{handle.key}.{output}" if output else ""
        name = getattr(self.backend, "selected_node_name", lambda: "")()
        return name or ""

    def _on_input_changed(self, input_name: str, source: str) -> None:
        if self._current is None:
            return
        try:
            if source:
                self.guides.connect(f"{self._current.key}.{input_name}", source)
            else:
                self.guides.disconnect(f"{self._current.key}.{input_name}")
        except TriggerError as error:
            self.events.log(str(error), level="warning")
            self._input_rows[input_name].set_source(self._current.inputs.get(input_name, ""))
            return
        self.refresh()

    def _on_setting_changed(self, name: str, _value) -> None:
        if self._current is None or self._module_obj is None:
            return
        value = getattr(self._module_obj, name)
        targets = self._multi or [self._current]
        with self.watcher.mute():
            for handle in targets:
                setattr(handle, name, value)
        if name in ("segments",):
            self.refresh()

    def _on_scene_nodes_changed(self, nodes: list) -> None:
        if self._external is None:
            return
        try:
            self.guides.set_scene_group(self._external, list(nodes))
        except TriggerError as error:
            self.events.log(str(error), level="warning")
            return
        self.graph.rebuild()  # keep the rows the user is typing in; only the graph/tree change
        self.graph.select_key(self._external)
        connections = self.guides.connections()
        self.status.set("connections", f"{len(connections)} connection(s)")

    def _rename_current(self) -> None:
        new_name = self.name_edit.text().strip()
        if self._current is None and self._external is not None:
            if new_name and new_name != self._external:
                old = self._external
                try:
                    self.guides.rename_scene_group(old, new_name)
                except TriggerError as error:
                    self.events.log(str(error), level="warning")
                    self.name_edit.setText(old)
                    return
                self._external = new_name
                self.refresh()
            return
        if self._current is None or self._multi:
            return
        if new_name and new_name != self._current.name:
            try:
                self._current.name = new_name
            except TriggerError as error:
                self.events.log(str(error), level="warning")
                self.name_edit.setText(self._current.name)
                return
            self.refresh()

    # ------------------------------------------------------------ actions
    def show_palette(self) -> None:
        self.palette.popup(QtGui.QCursor.pos())

    def create_guides(self, module_type: str) -> list[GuideHandle]:
        if module_type == SCENE_NODE:
            name = self.graph.add_scene_group(nodes=self._selected_scene_nodes())
            self._on_external_selection(name)
            self.name_edit.setFocus()
            self.name_edit.selectAll()
            return []
        module_cls = registry.get_module(module_type)
        parent_handle = self._current  # tree/graph selection only; nothing selected = no connection
        inputs = {}
        primary = module_cls.primary_input()
        if parent_handle is not None and primary is not None and parent_handle.outputs:
            inputs = {primary.name: f"{parent_handle.key}.{parent_handle.outputs[0]}"}
        choice = self.side
        if not module_cls.sided:
            sides = [Side.CENTER]
        elif choice == "Both":
            sides = [Side.LEFT, Side.RIGHT]
        elif choice == "Auto":
            sides = [parent_handle.side if parent_handle is not None and parent_handle.side is not Side.CENTER else Side.LEFT]
        else:
            sides = [Side.from_value(choice)]
        created = []
        try:
            with self.watcher.mute():
                for side in sides:
                    created.append(self.guides.add(module_type, side=side.value, inputs=inputs))
        except TriggerError as error:
            self.events.log(str(error), level="warning")
        self.refresh()
        if created:
            item = self.item_for(created[-1].instance_id)
            if item is not None:
                self.tree.setCurrentItem(item)
        return created

    def reparent(self, instance_id: str, parent_id: Optional[str]) -> None:
        handle = self.guides.get(instance_id)
        if handle is None:
            return
        parent = self.guides.get(parent_id) if parent_id else None
        primary = handle.module_class.primary_input()
        if primary is None:
            return
        try:
            with self.watcher.mute():
                if parent is not None:
                    self.guides.connect(f"{handle.key}.{primary.name}", f"{parent.key}.{parent.outputs[0]}")
                else:
                    self.guides.disconnect(f"{handle.key}.{primary.name}")
        except TriggerError as error:
            self.events.log(str(error), level="warning")
        self.refresh()

    def connect_dialog(self) -> None:
        if self._current is None or not self._current.input_names():
            return
        text, ok = QtWidgets.QInputDialog.getText(self, "Connect input", f"{self._current.key}.<input> = <source>", text=f"{self._current.input_names()[0]} = ")
        if ok and "=" in text:
            input_name, _eq, source = text.partition("=")
            self._on_input_changed(input_name.strip(), source.strip())

    def sever_current(self) -> None:
        for handle in self.selected_handles() or ([self._current] if self._current else []):
            self.graph.sever(handle.key)

    def disconnect_primary(self) -> None:
        if self._current is None:
            return
        primary = self._current.module_class.primary_input()
        if primary is not None:
            self._on_input_changed(primary.name, "")

    def select_root(self) -> None:
        """Select the root guide joint(s) of the selected module(s) in the viewport."""
        select = getattr(self.backend, "select_nodes", None)
        with self.watcher.mute():
            roots = [handle.root for handle in self.selected_handles() if handle.root is not None]
            if select is not None:
                select(roots)
            else:
                for root in roots:
                    getattr(root, "select", lambda: None)()

    def select_current(self) -> None:
        with self.watcher.mute():
            for handle in self.selected_handles():
                handle.select()

    def mirror_current(self) -> None:
        with self.watcher.mute():
            for handle in self.selected_handles():
                try:
                    self.guides.mirror(handle)
                except TriggerError as error:
                    self.events.log(str(error), level="warning")
        self.refresh()

    def delete_current(self) -> None:
        if self.graph.hasFocus() and self.graph.delete_selected():
            return  # Delete in the graph disconnects wires / removes scene-node groups
        if self._current is None and self._external is not None:
            self.graph.remove_scene_group(self._external)
            self._external = None
            self.refresh()
            return
        with self.watcher.mute():
            for handle in self.selected_handles():
                self.guides.remove(handle)
        self._current = None
        self._multi = []
        self.refresh()

    def clear_guides(self) -> None:
        with self.watcher.mute():
            self.guides.clear()
            self.guides.set_layout({})
        self._current = None
        self._multi = []
        self._external = None
        self.refresh()

    def test_build(self, all_modules: bool = False):
        handles = [] if all_modules else self.selected_handles()
        try:
            with self.watcher.mute():
                report = self.guides.test_build(*handles)
            self.status.set_activity(f"Test build: {report.count} module(s), {len(report.connections)} connection(s)")
            return report
        except TriggerError as error:
            self.events.log(str(error), level="error")
            self.status.set_activity(str(error))
            return None
        finally:
            self.refresh()

    # --------------------------------------------------------------- files
    def _pick(self, mode: str) -> str:
        if self.file_browser is not None:
            return self.file_browser(mode, [GUIDE_EXTENSION], self.file_path) or ""
        if mode == "save":
            path, _f = QtWidgets.QFileDialog.getSaveFileName(self, "Export guides", self.file_path, f"Guides (*{GUIDE_EXTENSION})")
        else:
            path, _f = QtWidgets.QFileDialog.getOpenFileName(self, "Import guides", self.file_path, f"Guides (*{GUIDE_EXTENSION})")
        return path

    def export_file(self, path: Optional[str] = None, ask: bool = False, selected: bool = False) -> Optional[Path]:
        path = path or ("" if ask else self.file_path) or self._pick("save")
        if not path:
            return None
        handles = self.selected_handles() if selected else []
        written = self.guides.export(path, *handles)
        self.set_file(str(written))
        self.events.log(f"Guides exported: {written}")
        return written

    def import_file(self, path: Optional[str] = None, reset: bool = False) -> list[GuideHandle]:
        path = path or self._pick("open")
        if not path:
            return []
        with self.watcher.mute():
            handles = self.guides.import_(path, reset=reset)
        self.set_file(path)
        self.refresh()
        return handles

    def closeEvent(self, event) -> None:  # noqa: N802
        self.bindings.clear()
        self.watcher.uninstall()
        super().closeEvent(event)
