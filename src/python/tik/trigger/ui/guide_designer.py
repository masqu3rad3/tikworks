"""Guide Designer: dockable tool window — modules · tree · graph · properties.

Tree and graph are two views of the same connections (see ``Guides``);
the properties panel shows the module's Inputs first. Scene sync goes
through a debounced ``SceneWatcher``; our own selection changes are muted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tik.core.side import Side
from tik.shared.ui import theme
from tik.shared.ui.binding import BindingManager, bind
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.maya_window import MayaToolWindow
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.scene_watcher import SceneWatcher
from tik.shared.ui.status import StatusFields
from tik.shared.ui.tile_grid import TileEntry, TileGrid
from tik.trigger.core import registry
from tik.trigger.core.builder import split_source
from tik.trigger.core.exceptions import TriggerError
from tik.trigger.core.schemas import ParentRef
from tik.trigger.guides import EXTENSION as GUIDE_EXTENSION
from tik.trigger.guides import GuideHandle, Guides

from .graph_view import GraphView
from .palette import PaletteEntry, SearchPalette
from .session_view import pane

MIME_MODULE = "application/x-trigger-module-type"
SIDES = ("L", "R", "C", "Both", "Auto")
MODULE_COLORS = {"body": "#c9a24a", "limbs": "#5b8fd0", "generic": "#7fa86a", "face": "#b86b9a"}
MODULE_CATEGORY = {"base": "body", "spine": "body", "head": "body", "arm": "limbs", "leg": "limbs",
                   "finger": "limbs", "fkchain": "generic", "tail": "generic", "surface": "generic"}


def module_entries():
    tiles, palette = [], []
    for module_cls in registry.iter_modules():
        category = MODULE_CATEGORY.get(module_cls.module_type, "generic")
        tiles.append(TileEntry(module_cls.module_type, module_cls.display_label(), category))
        palette.append(PaletteEntry(module_cls.module_type, module_cls.display_label(), category))
    return tiles, palette


class GuideTree(QtWidgets.QTreeWidget):
    """Instances tree; dragging a row onto another sets its primary input (and reparents the guides)."""

    reparent_requested = QtCore.Signal(str, object)  # instance_id, parent instance_id or None
    palette_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideTree")
        self.setHeaderLabels(["Module", "Type", "Side", "Primary input"])
        header = self.header()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(30)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == QtCore.Qt.Key_Tab:
            self.palette_requested.emit()
            return
        super().keyPressEvent(event)

    def focusNextPrevChild(self, next_child: bool) -> bool:  # noqa: N802
        return False

    def dropEvent(self, event) -> None:  # noqa: N802
        target = self.itemAt(event.pos())
        moved = self.currentItem()
        event.setDropAction(QtCore.Qt.IgnoreAction)
        event.accept()
        if moved is None:
            return
        moved_id = moved.data(0, QtCore.Qt.UserRole)
        target_id = target.data(0, QtCore.Qt.UserRole) if target is not None else None
        if target_id != moved_id:
            self.reparent_requested.emit(moved_id, target_id)


class InputRow(QtWidgets.QWidget):
    """One input: source editor + "from selection" + clear."""

    changed = QtCore.Signal(str, str)  # input name, source ("" = disconnect)

    def __init__(self, input_decl, parent=None, picker=None) -> None:
        super().__init__(parent)
        self.input = input_decl
        self.picker = picker
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
        self.pick.clicked.connect(self._pick)
        self.clear.clicked.connect(lambda: (self.line.setText(""), self.changed.emit(self.input.name, "")))

    def set_source(self, source: str) -> None:
        self.line.setText(source or "")

    def _pick(self) -> None:
        if self.picker is None:
            return
        source = self.picker()
        if source:
            self.line.setText(source)
            self.changed.emit(self.input.name, source)


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
        side_row = QtWidgets.QHBoxLayout()
        side_row.setSpacing(2)
        self.side_group = QtWidgets.QButtonGroup(self)
        for value in SIDES:
            button = QtWidgets.QToolButton()
            button.setText(value)
            button.setCheckable(True)
            button.setProperty("side", value)
            button.setChecked(value == "L")
            self.side_group.addButton(button)
            side_row.addWidget(button)
        side_row.addStretch(1)
        left_layout.addLayout(side_row)
        modules_header = QtWidgets.QLabel("MODULES")
        modules_header.setObjectName("PaneHeader")
        left_layout.addWidget(modules_header)
        self.shelf = TileGrid(tiles, MIME_MODULE, colors=MODULE_COLORS)
        self.shelf.activated.connect(lambda key: self.create_guides(key))
        left_layout.addWidget(self.shelf, 1)
        self.splitter.addWidget(left)

        self.tree = GuideTree()
        self.tree_pane = pane("Tree", self.tree)
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
        self.inputs_caption = QtWidgets.QLabel("INPUTS")
        self.inputs_caption.setObjectName("FieldCaption")
        props.addWidget(self.inputs_caption)
        self.inputs_form = QtWidgets.QFormLayout()
        self.inputs_form.setContentsMargins(4, 0, 4, 4)
        props.addLayout(self.inputs_form)
        guides_caption = QtWidgets.QLabel("GUIDES")
        guides_caption.setObjectName("FieldCaption")
        props.addWidget(guides_caption)
        self.inherit_orientation = QtWidgets.QCheckBox("Inherit orientation from guides")
        props.addWidget(self.inherit_orientation)
        self.module_caption = QtWidgets.QLabel("MODULE")
        self.module_caption.setObjectName("FieldCaption")
        props.addWidget(self.module_caption)
        self.form = FormBuilder()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(self.form)
        props.addWidget(scroll, 1)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.select_button = QtWidgets.QPushButton("Select guides")
        self.mirror_button = QtWidgets.QPushButton("Mirror")
        self.test_button = QtWidgets.QPushButton("Test build")
        self.test_button.setObjectName("PrimaryButton")
        for button in (self.select_button, self.mirror_button, self.test_button):
            buttons.addWidget(button)
        props.addLayout(buttons)
        self.splitter.addWidget(self.properties)

        for index, stretch in enumerate((0, 1, 2, 1)):
            self.splitter.setStretchFactor(index, stretch)
        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, True)
        self.splitter.setCollapsible(2, True)
        self.splitter.setCollapsible(3, False)
        self.splitter.setSizes([170, 300, 470, 300])
        self.setCentralWidget(self.splitter)

        self.palette = SearchPalette(palette_entries, self, colors=MODULE_COLORS)
        self.palette.chosen.connect(lambda key, _child: self.create_guides(key))

        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        self.tree.reparent_requested.connect(self.reparent)
        self.tree.palette_requested.connect(self.show_palette)
        self.graph.selection_changed.connect(self._on_graph_selection)
        self.graph.edited.connect(lambda: self.refresh(keep_graph=True))
        self.select_button.clicked.connect(self.select_current)
        self.mirror_button.clicked.connect(self.mirror_current)
        self.test_button.clicked.connect(self.test_build)
        self.name_edit.editingFinished.connect(self._rename_current)
        self.form.changed.connect(self._on_setting_changed)
        self.form.error.connect(lambda _name, message: self.events.log(message, level="warning"))
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
        self._action(edit_menu, "Mirror", self.mirror_current, "Ctrl+M")
        self._action(edit_menu, "Rename", lambda: self.name_edit.setFocus(), "F2")
        self._action(edit_menu, "Delete", self.delete_current, "Del")
        edit_menu.addSeparator()
        self._action(edit_menu, "Connect Input…", self.connect_dialog)
        self._action(edit_menu, "Disconnect Primary Input", self.disconnect_primary)
        view_menu = bar.addMenu("&View")
        self.tree_action = self._action(view_menu, "Tree", lambda: self.set_pane_visible(self.tree_pane, self.tree_action.isChecked()), checkable=True)
        self.graph_action = self._action(view_menu, "Graph", lambda: self.set_pane_visible(self.graph_pane, self.graph_action.isChecked()), checkable=True)
        self.tree_action.setChecked(True)
        self.graph_action.setChecked(True)
        view_menu.addSeparator()
        self._action(view_menu, "Refresh", self.refresh, "F5")
        build_menu = bar.addMenu("&Build")
        self._action(build_menu, "Test Build Selected", self.test_build, "Ctrl+B")
        self._action(build_menu, "Test Build All", lambda: self.test_build(all_modules=True), "Ctrl+Shift+B")
        help_menu = bar.addMenu("&Help")
        self._action(help_menu, "About Guide Designer", lambda: QtWidgets.QMessageBox.about(self, "Guide Designer", "Author module guides and connections; export a .trg for the Kinematics action."))

    def _build_status(self) -> None:
        self.status = StatusFields(self.statusBar(), ("modules", "connections", "file"))
        self.status.set_activity("Ready")

    # ------------------------------------------------------------ state
    @property
    def side(self) -> str:
        button = self.side_group.checkedButton()
        return button.property("side") if button else "L"

    def set_side(self, side: str) -> None:
        for button in self.side_group.buttons():
            if button.property("side") == side:
                button.setChecked(True)

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
            keep = self._current.instance_id if self._current else None
            handles = self.guides.instances()
            by_key = {handle.key: handle for handle in handles}
            self.tree.clear()
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
            self.graph.rebuild()
            connections = self.guides.connections()
            externals = [item["source"] for item in connections if split_source(item["source"])[0] not in by_key]
            missing = [name for name in externals if getattr(self.backend, "scene_node", lambda _n: True)(name) is None]
            self.status.set("modules", f"{len(handles)} module(s)")
            self.status.set("connections", f"{len(connections)} connection(s)" + (f" · {len(missing)} missing scene node(s)" if missing else ""))
            if keep in items:
                self.tree.setCurrentItem(items[keep])
                self._set_current(self.guides.get(keep))
            else:
                self._set_current(None)
        finally:
            self._syncing = False

    def item_for(self, instance_id: str) -> Optional[QtWidgets.QTreeWidgetItem]:
        iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, QtCore.Qt.UserRole) == instance_id:
                return item
            iterator += 1
        return None

    # ----------------------------------------------------------- selection
    def _on_tree_selection(self) -> None:
        if self._syncing:
            return
        handles = self.selected_handles()
        self._set_current(handles[0] if handles else None)
        self.graph.select_key(handles[0].key if handles else None)
        if handles and hasattr(self.backend, "select_guides"):
            with self.watcher.mute():
                for handle in handles:
                    self.backend.select_guides(handle.instance_id)

    def _on_graph_selection(self, key: str) -> None:
        handle = self.guides.by_key(key)
        if handle is None:
            return
        item = self.item_for(handle.instance_id)
        if item is not None:
            self._syncing = True
            try:
                self.tree.setCurrentItem(item)
            finally:
                self._syncing = False
        self._set_current(handle)
        if hasattr(self.backend, "select_guides"):
            with self.watcher.mute():
                self.backend.select_guides(handle.instance_id)

    def _on_scene_event(self, name: str) -> None:
        if name == "SelectionChanged":
            picked = self.backend.selected_guide()
            if picked is None:
                return
            item = self.item_for(picked.instance_id)
            if item is not None and not item.isSelected():
                self._syncing = True
                try:
                    self.tree.setCurrentItem(item)
                finally:
                    self._syncing = False
                self._set_current(self.guides.get(picked.instance_id))
                self.graph.select_key(self._current.key if self._current else None)
            return
        self.refresh()

    # ---------------------------------------------------------- properties
    def _set_current(self, handle: Optional[GuideHandle]) -> None:
        self._current = handle
        self.bindings.clear()
        while self.inputs_form.count():
            item = self.inputs_form.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
                item.widget().deleteLater()
        self._input_rows.clear()
        if handle is None:
            self._module_obj = None
            self.form.set_target(None)
            self.name_edit.setText("")
            self.type_label.setText("")
            self.icon.clear()
            self.inherit_orientation.setEnabled(False)
            self.status.set_activity("Select a module, or add one from the shelf (Tab to search).")
            return
        instance = handle.instance
        module_cls = handle.module_class
        self._module_obj = module_cls(name=instance.name, side=instance.side, settings=instance.settings)
        self.name_edit.setText(instance.name)
        self.type_label.setText(f"{module_cls.display_label()} · {instance.side}")
        self.icon.setPixmap(glyph_icon(initials(module_cls.display_label()), theme.SIDE.get(instance.side, theme.SIDE["C"]), 24).pixmap(24, 24))
        for declared in module_cls.inputs:
            row = InputRow(declared, picker=self._pick_source)
            row.set_source(handle.inputs.get(declared.name, ""))
            row.changed.connect(self._on_input_changed)
            label = declared.name + (" ●" if declared.primary else "")
            self.inputs_form.addRow(label, row)
            self._input_rows[declared.name] = row
        self.inputs_caption.setVisible(bool(module_cls.inputs))
        self.form.set_target(self._module_obj)
        self.inherit_orientation.setEnabled(True)
        self._bind_properties(handle)
        self.status.set_activity(f"{handle.key} — {module_cls.display_label()}")

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
        setattr(self._current, name, getattr(self._module_obj, name))
        if name in ("segments",):
            self.refresh()

    def _rename_current(self) -> None:
        if self._current is None:
            return
        new_name = self.name_edit.text().strip()
        if new_name and new_name != self._current.name:
            self._current.name = new_name
            self.refresh()

    # ------------------------------------------------------------ actions
    def show_palette(self) -> None:
        self.palette.popup(self.tree.viewport().mapToGlobal(QtCore.QPoint(20, 20)))

    def create_guides(self, module_type: str) -> list[GuideHandle]:
        module_cls = registry.get_module(module_type)
        picked = self.backend.selected_guide() if hasattr(self.backend, "selected_guide") else None
        parent_ref = picked
        if parent_ref is None and self._current is not None:
            parent_ref = ParentRef(self._current.instance_id, self._current.module_class.guides.root)
        parent_handle = self.guides.get(parent_ref.instance_id) if parent_ref else None
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
                    created.append(self.guides.add(module_type, side=side.value, parent=parent_ref))
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
        try:
            with self.watcher.mute():
                self.guides.reparent(handle, parent)
                if primary is not None:
                    if parent is not None:
                        output = parent.module_class.output_for_role(parent.module_class.guides.root)
                        self.guides.connect(f"{handle.key}.{primary.name}", f"{parent.key}.{output}")
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

    def disconnect_primary(self) -> None:
        if self._current is None:
            return
        primary = self._current.module_class.primary_input()
        if primary is not None:
            self._on_input_changed(primary.name, "")

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
        with self.watcher.mute():
            for handle in self.selected_handles():
                self.guides.remove(handle)
        self._current = None
        self.refresh()

    def clear_guides(self) -> None:
        with self.watcher.mute():
            self.guides.clear()
        self._current = None
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
