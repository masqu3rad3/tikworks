"""Guide Designer: a mode of the Trigger window — modules · tree · graph · properties.

Tree and graph are two views of the same connections (see ``GuideScene``);
the properties panel shows the module's Inputs first. Connections are data
only: the designer never parents guide joints into each other and never
selects joints in Maya on its own — use *Select guides* for that. Scene
structure changes (new/removed/undone guides) reach the UI through a
debounced ``SceneWatcher``; our own edits are muted.

The designer is a page, not a window: it builds ``menu_bar`` and
``status_strip`` and leaves the hosting to ``ui/main.py``, which shows it as a
mode tab of the Trigger window.

Everything the designer authors (connections, scene-node groups, node
positions, collapse modes) lives in ``GuideScene`` / ``GuideScene.layout`` and is
exported with the ``.trg``; only window geometry and selection are transient.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from tik.core.side import Side
from tik.shared.ui import theme
from tik.shared.ui.binding import BindingManager, MayaAttributeAdapter, bind
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.filter_bar import FilterBar
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.scene_watcher import SceneWatcher
from tik.shared.ui.status import StatusFields
from tik.shared.ui.tile_grid import TileEntry, TileGrid
from tik.trigger.core import registry
from tik.trigger.core.schemas import split_source
from tik.trigger.core.exceptions import TriggerError
from tik.trigger.guides import EXTENSION as GUIDE_EXTENSION

if TYPE_CHECKING:  # the scene layer imports Maya; the UI only needs the name
    from tik.trigger.guides import GuideHandle

from ..graph import GraphView
from ..palette import PaletteEntry, SearchPalette
from ..session_view import pane
from .commands import DesignerCommands
from .properties import DesignerProperties
from .widgets import (
    MIME_MODULE,
    MODULE_COLORS,
    SCENE_NODE,
    GuideTree,
    InputRow,
    SceneNodesPanel,
    module_entries,
)

SIDES = ("L", "R", "C", "Both", "Auto")


def diff_summary(diff) -> str:
    """One-line description of a reconcile result for the status strip.

    Pose drift is deliberately absent: it is capture's job, and calling it a
    redraw would tell the rigger their guides are about to move when they are
    not.
    """
    parts = []
    if diff.structural:
        parts.append(f"{len(diff.structural)} module(s) need redraw")
    if diff.orphans:
        parts.append(f"{len(diff.orphans)} orphan guide(s)")
    if diff.duplicates:
        parts.append(f"{len(diff.duplicates)} duplicate guide(s)")
    return " · ".join(parts)


class GuideDesigner(DesignerCommands, DesignerProperties, QtWidgets.QWidget):
    """A plain widget on purpose.

    The designer is hosted as a *mode* of the Trigger window (``ui/main.py``).
    It builds ``menu_bar`` and ``status_strip`` but installs neither, so the
    host decides where they go.
    """

    title_changed = QtCore.Signal(str)

    def __init__(self, parent=None, events=None, file_browser=None, binding_adapter=None,
                 scene=None) -> None:
        super().__init__(parent)
        # ``scene`` is an injection point for tests; normally the designer owns
        # the scene's guides.
        if scene is None:
            from tik.trigger.guides import GuideScene

            scene = GuideScene(events)
        self.guides = scene
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
        self._torn_down = False
        # SceneWatcher probes objectName() to notice a destroyed C++ object
        self.setObjectName("TriggerGuideDesigner")
        self.setWindowTitle(self.title)
        self.resize(1240, 680)
        self._build_central()
        self._build_menus()
        self._build_status()
        theme.apply(self)
        self.watcher = SceneWatcher(
            self._on_scene_event,
            owner=self,
            install_job=getattr(self.guides, "install_scene_job", None),
            kill_job=getattr(self.guides, "kill_scene_job", None),
            parent=self,
            # deleting a guide in the outliner has no scriptJob event
            api_callbacks=True,
        )
        self.watcher.install()
        # closeEvent is not the only teardown path; a destroyed dock leaves the
        # jobs installed and the zero-timer firing into a dead widget. Captured
        # in a closure so nothing touches self during destruction.
        watcher = self.watcher
        self.destroyed.connect(lambda *_args: watcher.uninstall())
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
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

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
        self.inherit_orientation.toggled.connect(self._on_inherit_toggled)
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
        bar = self.menu_bar = QtWidgets.QMenuBar(self)
        file_menu = bar.addMenu("&File")
        self._action(file_menu, "Clear Scene Guides", self.clear_guides)
        file_menu.addSeparator()
        self._action(file_menu, "Import .trg…", lambda: self.import_file(), "Ctrl+O")
        self._action(file_menu, "Export .trg…", lambda: self.export_file(ask=True), "Ctrl+S")
        self._action(file_menu, "Export Selected…", lambda: self.export_file(ask=True, selected=True))
        edit_menu = bar.addMenu("&Edit")
        self._action(edit_menu, "Add Module…", self.show_palette, "Tab")
        self._action(edit_menu, "Add Scene Nodes", lambda: self.create_guides(SCENE_NODE), "Ctrl+N")
        edit_menu.addSeparator()
        self._action(edit_menu, "Select Root", self.select_root)
        self._action(edit_menu, "Select All Guides", self.select_current)
        self._action(edit_menu, "Mirror", self.mirror_current, "Ctrl+M")
        self._action(edit_menu, "Duplicate", self.duplicate_current, "Ctrl+D")
        self._action(edit_menu, "Rename", lambda: self.name_edit.setFocus(), "F2")
        self._action(edit_menu, "Delete", self.delete_current)
        edit_menu.addSeparator()
        self._action(edit_menu, "Connect Input…", self.connect_dialog)
        self._action(edit_menu, "Disconnect Primary Input", self.disconnect_primary)
        self._action(edit_menu, "Sever Connections", self.sever_current, "Ctrl+Shift+D")
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
        menu.addAction("Duplicate\tCtrl+D", self.duplicate_current)
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
        self.status_strip = QtWidgets.QWidget()
        self.status = StatusFields(self.status_strip, ("modules", "connections", "file"))
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

    @property
    def title(self) -> str:
        return f"Guide Designer — {Path(self.file_path).name}" if self.file_path else "Guide Designer"

    def set_file(self, path: str) -> None:
        self.file_path = path
        self.status.set("file", Path(path).name if path else "")
        self.setWindowTitle(self.title)
        self.title_changed.emit(self.title)

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
                    # the document entry, not a scene scan: the tree describes
                    # what the rig *is*, and one refresh reads the scene once
                    entry = handle.entry
                    module_cls = handle.module_class
                    label = module_cls.display_label()
                    if module_cls.guides.multi:
                        count = sum(1 for role, _index in entry.pairs if role == module_cls.guides.multi)
                        label = f"{label} · {count}"
                    primary = module_cls.primary_input()
                    primary_text = handle.inputs.get(primary.name, "") if primary else ""
                    item = QtWidgets.QTreeWidgetItem([handle.key, label, entry.side, primary_text or "—"])
                    item.setData(0, QtCore.Qt.UserRole, handle.instance_id)
                    item.setIcon(0, glyph_icon(initials(module_cls.display_label()), theme.SIDE.get(entry.side, theme.SIDE["C"])))
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
            missing = [name for name in externals if getattr(self.guides, "scene_node", lambda _n: True)(name) is None]
            self.status.set("modules", f"{len(handles)} module(s)")
            notes = [f"{len(connections)} connection(s)"]
            if missing:
                notes.append(f"{len(missing)} missing scene node(s)")
            # Computed on every refresh, reported and nothing more: this is the
            # substrate both lockstep and a checkpointed policy build on.
            try:
                summary = diff_summary(self.guides.diff())
            except Exception:  # noqa: BLE001 - a stub scene has no diff()
                summary = ""
            if summary:
                notes.append(summary)
            self.status.set("connections", " · ".join(notes))
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
        # Muted throughout: sync() deletes and recreates joints, which fires the
        # removal callback that brought us here and would re-enter.
        with self.watcher.mute():
            try:
                self.guides.sync()
            except Exception as error:  # noqa: BLE001 - keep the tool alive
                self.events.log(f"Guide sync failed: {error}", level="warning")
        self.refresh()

    # ---------------------------------------------------------- properties
    def _set_current(self, handle: Optional[GuideHandle], group: Optional[list[GuideHandle]] = None) -> None:
        self._current = handle
        self._multi = list(group or [])
        self._external = None
        self.bindings.clear()
        for row in self._input_rows.values():
            row.blockSignals(True)
            row.line.blockSignals(True)
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
        entry = handle.entry
        module_cls = handle.module_class
        self._module_obj = module_cls(name=entry.name, side=entry.side, settings=entry.settings)
        self.name_edit.setText(entry.name)
        self.type_label.setText(f"{module_cls.display_label()} · {entry.side}")
        self.icon.setPixmap(glyph_icon(initials(module_cls.display_label()), theme.SIDE.get(entry.side, theme.SIDE["C"]), 24).pixmap(24, 24))
        multi = len(self._multi) > 1
        if multi:
            self.name_edit.setEnabled(False)
            self.name_edit.setText(", ".join(item.key for item in self._multi))
            self.multi_label.setText(f"Editing {len(self._multi)} {module_cls.display_label()} modules together — every change applies to all of them.")
            self.multi_label.setVisible(True)
            self.inputs_caption.setVisible(False)
        else:
            declared_inputs = list(module_cls.inputs) + module_cls.space_inputs(handle.settings)
            for declared in declared_inputs:
                row = InputRow(declared, picker=self._pick_source, sources=self._source_choices)
                row.set_source(handle.inputs.get(declared.name, ""))
                row.changed.connect(self._on_input_changed)
                label = declared.name + (" ●" if declared.primary else "")
                self.inputs_form.addRow(label, row)
                self._input_rows[declared.name] = row
            self.inputs_caption.setVisible(bool(declared_inputs))
        self.form.set_target(self._module_obj)
        self.inherit_orientation.setEnabled(True)
        if not multi:
            self._bind_properties(handle)
            self.status.set_activity(f"{handle.key} — {module_cls.display_label()}")
        else:
            adapter = self._plug_adapter(handle, "useRefOri")
            self.inherit_orientation.blockSignals(True)
            try:
                self.inherit_orientation.setChecked(bool(adapter.get()) if adapter is not None and adapter.exists() else True)
            finally:
                self.inherit_orientation.blockSignals(False)
            self.status.set_activity(f"{len(self._multi)} × {module_cls.display_label()} selected")


    # -------------------------------------------------------------- teardown
    def teardown(self) -> None:
        """Release bindings and scene jobs. Safe to call more than once.

        A page never gets its own close event, so the host calls this; the
        close event below still fires when the designer is shown as a window.
        """
        if self._torn_down:
            return
        self._torn_down = True
        self.bindings.clear()
        self.watcher.uninstall()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.teardown()
        super().closeEvent(event)
