"""Guide Designer: modules · scene guides · properties; outputs a .trg and test builds.

Layout A from the mockups. The tree mirrors the scene both ways: tree
selection selects the guides, viewport selection highlights the row,
drag-parenting in the tree reparents the Maya guides.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tik.core.side import Side
from tik.shared.ui import theme
from tik.shared.ui.binding import BindingManager, bind
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.core import registry
from tik.trigger.core.exceptions import TriggerError
from tik.trigger.core.schemas import ParentRef
from tik.trigger.guides import EXTENSION as GUIDE_EXTENSION
from tik.trigger.guides import GuideHandle, Guides

from .palette import PaletteEntry, SearchPalette
from .shelf import Shelf

MIME_MODULE = "application/x-trigger-module-type"
MIME_INSTANCE = "application/x-trigger-guide-instance"
SIDES = [("L", "L"), ("R", "R"), ("C", "C"), ("Both", "Both"), ("Auto", "Auto")]
MODULE_COLORS = {"body": "#c9a24a", "limbs": "#5b8fd0", "generic": "#7fa86a", "face": "#b86b9a"}
MODULE_CATEGORY = {"base": "body", "spine": "body", "head": "body", "arm": "limbs", "leg": "limbs",
                   "finger": "limbs", "fkchain": "generic", "tail": "generic", "surface": "generic"}


def module_entries() -> list[PaletteEntry]:
    entries = []
    for module_cls in registry.iter_modules():
        category = MODULE_CATEGORY.get(module_cls.module_type, "generic")
        entries.append(PaletteEntry(module_cls.module_type, module_cls.display_label(), category))
    return entries


class GuideTree(QtWidgets.QTreeWidget):
    """Instances tree with internal drag-parenting."""

    reparent_requested = QtCore.Signal(str, object)  # instance_id, parent instance_id or None
    palette_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Guides in scene", "Module", "Side"])
        self.setColumnWidth(0, 200)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

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
        if moved is None:
            event.ignore()
            return
        moved_id = moved.data(0, QtCore.Qt.UserRole)
        target_id = target.data(0, QtCore.Qt.UserRole) if target is not None else None
        if target_id == moved_id:
            event.ignore()
            return
        event.setDropAction(QtCore.Qt.IgnoreAction)
        event.accept()
        self.reparent_requested.emit(moved_id, target_id)


class GuideDesigner(QtWidgets.QMainWindow):
    def __init__(self, backend, parent=None, events=None, file_browser=None, binding_adapter=None) -> None:
        super().__init__(parent)
        self.backend = backend
        self.guides = Guides(backend, events)
        self.events = self.guides.events
        self.file_browser = file_browser
        self.binding_adapter = binding_adapter  # factory(plug_path) for tests
        self.file_path: str = ""
        self.bindings = BindingManager()
        self._current: Optional[GuideHandle] = None
        self._module_obj = None
        self._syncing = False
        self.setWindowTitle("Guide Designer")
        self.resize(1000, 620)
        theme.apply(self)
        self._build_ui()
        self.observer = backend.make_observer(self._on_scene_event) if hasattr(backend, "make_observer") else None
        if self.observer is not None:
            self.observer.start()
        self.refresh()

    # ------------------------------------------------------------------ ui
    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # left: side + module shelf
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(6, 6, 0, 6)
        side_box = QtWidgets.QHBoxLayout()
        self.side_group = QtWidgets.QButtonGroup(self)
        for label, value in SIDES:
            button = QtWidgets.QPushButton(label)
            button.setCheckable(True)
            button.setFlat(True)
            button.setFixedWidth(30 if len(label) == 1 else 44)
            button.setProperty("side", value)
            self.side_group.addButton(button)
            side_box.addWidget(button)
            if value == "L":
                button.setChecked(True)
        side_box.addStretch(1)
        left_layout.addLayout(side_box)
        self.shelf = Shelf(module_entries(), MIME_MODULE, colors=MODULE_COLORS, title="Modules")
        self.shelf.add_requested.connect(lambda key: self.create_guides(key))
        left_layout.addWidget(self.shelf, 1)
        body.addWidget(left)

        # middle: tree
        middle = QtWidgets.QWidget()
        middle_layout = QtWidgets.QVBoxLayout(middle)
        self.tree = GuideTree()
        middle_layout.addWidget(self.tree, 1)
        buttons = QtWidgets.QHBoxLayout()
        self.select_button = QtWidgets.QPushButton("Select")
        self.mirror_button = QtWidgets.QPushButton("Mirror")
        self.delete_button = QtWidgets.QPushButton("Delete")
        for button in (self.select_button, self.mirror_button, self.delete_button):
            button.setFlat(True)
            buttons.addWidget(button)
        middle_layout.addLayout(buttons)
        body.addWidget(middle, 1)

        # right: properties
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        header = QtWidgets.QHBoxLayout()
        self.icon = QtWidgets.QLabel()
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("instance name")
        self.type_label = QtWidgets.QLabel("")
        self.type_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
        header.addWidget(self.icon)
        header.addWidget(self.name_edit, 1)
        header.addWidget(self.type_label)
        right_layout.addLayout(header)
        self.inherit_orientation = QtWidgets.QCheckBox("Inherit orientation from guides")
        right_layout.addWidget(self.inherit_orientation)
        self.form = FormBuilder()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(self.form)
        right_layout.addWidget(scroll, 1)
        body.addWidget(right, 1)
        layout.addLayout(body, 1)

        # bottom bar
        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(10, 6, 10, 6)
        self.import_button = QtWidgets.QPushButton("Import .trg")
        self.import_button.setFlat(True)
        self.export_button = QtWidgets.QPushButton("Export .trg")
        self.file_label = QtWidgets.QLabel("")
        self.file_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self.test_button = QtWidgets.QPushButton("Test build")
        self.test_button.setFlat(True)
        bar.addWidget(self.import_button)
        bar.addWidget(self.export_button)
        bar.addWidget(self.file_label, 1)
        bar.addWidget(self.test_button)
        frame = QtWidgets.QFrame()
        frame.setLayout(bar)
        frame.setStyleSheet(f"QFrame {{ background: #2a2a2a; border-top: 1px solid {theme.LINE}; }}")
        layout.addWidget(frame)
        self.setCentralWidget(central)

        self.palette = SearchPalette(module_entries(), self, colors=MODULE_COLORS)
        self.palette.chosen.connect(lambda key, _child: self.create_guides(key))

        # signals
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        self.tree.reparent_requested.connect(self.reparent)
        self.tree.palette_requested.connect(self.show_palette)
        self.select_button.clicked.connect(self.select_current)
        self.mirror_button.clicked.connect(self.mirror_current)
        self.delete_button.clicked.connect(self.delete_current)
        self.name_edit.editingFinished.connect(self._rename_current)
        self.inherit_orientation.toggled.connect(self._on_inherit_toggled)
        self.form.changed.connect(self._on_setting_changed)
        self.form.error.connect(lambda _name, message: self.events.log(message, level="warning"))
        self.import_button.clicked.connect(lambda: self.import_file())
        self.export_button.clicked.connect(lambda: self.export_file())
        self.test_button.clicked.connect(self.test_build)
        QtWidgets.QShortcut(QtGui.QKeySequence("Delete"), self.tree, self.delete_current)
        QtWidgets.QShortcut(QtGui.QKeySequence("F5"), self, self.refresh)

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

    def selected_handles(self) -> list[GuideHandle]:
        handles = []
        for item in self.tree.selectedItems():
            handle = self.guides.get(item.data(0, QtCore.Qt.UserRole))
            if handle is not None:
                handles.append(handle)
        return handles

    def set_file(self, path: str) -> None:
        self.file_path = path
        self.file_label.setText(Path(path).name if path else "")
        self.setWindowTitle(f"Guide Designer — {Path(path).name}" if path else "Guide Designer")

    # --------------------------------------------------------------- tree
    def refresh(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            keep = self._current.instance_id if self._current else None
            self.tree.clear()
            handles = self.guides.instances()
            items: dict[str, QtWidgets.QTreeWidgetItem] = {}
            pending = list(handles)
            while pending:
                remaining = []
                for handle in pending:
                    instance = handle.instance
                    parent_id = instance.parent.instance_id if instance.parent else None
                    if parent_id and parent_id not in items and any(h.instance_id == parent_id for h in handles):
                        remaining.append(handle)
                        continue
                    module_cls = handle.module_class
                    label = module_cls.display_label()
                    if module_cls.guides.multi:
                        count = sum(1 for role, _index in instance.guide_pairs if role == module_cls.guides.multi)
                        label = f"{label} · {count}"
                    item = QtWidgets.QTreeWidgetItem([instance.name, label, instance.side])
                    item.setData(0, QtCore.Qt.UserRole, handle.instance_id)
                    item.setIcon(0, glyph_icon(initials(module_cls.display_label()), theme.SIDE.get(instance.side, theme.SIDE["C"])))
                    item.setFlags(item.flags() | QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsDropEnabled)
                    if parent_id in items:
                        items[parent_id].addChild(item)
                    else:
                        self.tree.addTopLevelItem(item)
                    items[handle.instance_id] = item
                if len(remaining) == len(pending):
                    break
                pending = remaining
            self.tree.expandAll()
            if keep in items:
                self.tree.setCurrentItem(items[keep])
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

    def _on_tree_selection(self) -> None:
        if self._syncing:
            return
        handles = self.selected_handles()
        self._set_current(handles[0] if handles else None)
        if handles and hasattr(self.backend, "select_guides"):
            if self.observer is not None:
                self.observer.muted = True
            try:
                for handle in handles:
                    self.backend.select_guides(handle.instance_id)
            finally:
                if self.observer is not None:
                    self.observer.muted = False

    def _on_scene_event(self, name: str) -> None:
        if name == "SelectionChanged":
            picked = self.backend.selected_guide()
            if picked is not None:
                item = self.item_for(picked.instance_id)
                if item is not None and not item.isSelected():
                    self._syncing = True
                    try:
                        self.tree.setCurrentItem(item)
                    finally:
                        self._syncing = False
                    self._set_current(self.guides.get(picked.instance_id))
            return
        self.refresh()

    # --------------------------------------------------------- properties
    def _set_current(self, handle: Optional[GuideHandle]) -> None:
        self._current = handle
        self.bindings.clear()
        if handle is None:
            self._module_obj = None
            self.form.set_target(None)
            self.name_edit.setText("")
            self.type_label.setText("")
            self.icon.clear()
            self.inherit_orientation.setEnabled(False)
            return
        instance = handle.instance
        module_cls = handle.module_class
        self._module_obj = module_cls(name=instance.name, side=instance.side, settings=instance.settings)
        self.name_edit.setText(instance.name)
        self.type_label.setText(f"{module_cls.display_label()} · {instance.side}")
        self.icon.setPixmap(glyph_icon(initials(module_cls.display_label()), theme.SIDE.get(instance.side, theme.SIDE["C"]), 24).pixmap(24, 24))
        self.form.set_target(self._module_obj)
        self.inherit_orientation.setEnabled(True)
        self._bind_properties(handle)

    def _bind_properties(self, handle: GuideHandle) -> None:
        """Maya -> widget updates (widget -> Maya goes through the handle)."""
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

    def _on_setting_changed(self, name: str, _value) -> None:
        if self._current is None or self._module_obj is None:
            return
        setattr(self._current, name, getattr(self._module_obj, name))
        self.refresh() if name in ("segments",) else None

    def _on_inherit_toggled(self, _state: bool) -> None:
        pass  # bound directly to the useRefOri attribute

    def _rename_current(self) -> None:
        if self._current is None:
            return
        new_name = self.name_edit.text().strip()
        if new_name and new_name != self._current.name:
            self._current.name = new_name
            self.refresh()

    # ------------------------------------------------------------ actions
    def show_palette(self) -> None:
        point = self.tree.viewport().mapToGlobal(QtCore.QPoint(20, 20))
        self.palette.popup(point)

    def create_guides(self, module_type: str) -> list[GuideHandle]:
        module_cls = registry.get_module(module_type)
        parent = self._current
        side_choice = self.side
        if not module_cls.sided:
            sides = [Side.CENTER]
        elif side_choice == "Both":
            sides = [Side.LEFT, Side.RIGHT]
        elif side_choice == "Auto":
            sides = [parent.side if parent is not None and parent.side is not Side.CENTER else Side.LEFT]
        else:
            sides = [Side.from_value(side_choice)]
        created = []
        try:
            for side in sides:
                created.append(self.guides.add(module_type, side=side.value, parent=parent))
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
        try:
            self.guides.reparent(handle, parent)
        except TriggerError as error:
            self.events.log(str(error), level="warning")
        self.refresh()

    def select_current(self) -> None:
        for handle in self.selected_handles():
            handle.select()

    def mirror_current(self) -> None:
        for handle in self.selected_handles():
            try:
                self.guides.mirror(handle)
            except TriggerError as error:
                self.events.log(str(error), level="warning")
        self.refresh()

    def delete_current(self) -> None:
        for handle in self.selected_handles():
            self.guides.remove(handle)
        self._current = None
        self.refresh()

    def test_build(self):
        handles = self.selected_handles()
        try:
            return self.guides.test_build(*handles)
        except TriggerError as error:
            self.events.log(str(error), level="error")
            return None
        finally:
            self.refresh()

    # --------------------------------------------------------------- files
    def _pick(self, mode: str) -> str:
        if self.file_browser is not None:
            return self.file_browser(mode, [GUIDE_EXTENSION], self.file_path) or ""
        if mode == "save":
            path, _filter = QtWidgets.QFileDialog.getSaveFileName(self, "Export guides", self.file_path, f"Guides (*{GUIDE_EXTENSION})")
        else:
            path, _filter = QtWidgets.QFileDialog.getOpenFileName(self, "Import guides", self.file_path, f"Guides (*{GUIDE_EXTENSION})")
        return path

    def export_file(self, path: Optional[str] = None) -> Optional[Path]:
        path = path or self.file_path or self._pick("save")
        if not path:
            return None
        written = self.guides.export(path, *self.selected_handles())
        self.set_file(str(written))
        self.events.log(f"Guides exported: {written}")
        return written

    def import_file(self, path: Optional[str] = None, reset: bool = False) -> list[GuideHandle]:
        path = path or self._pick("open")
        if not path:
            return []
        handles = self.guides.import_(path, reset=reset)
        self.set_file(path)
        self.refresh()
        return handles

    def closeEvent(self, event) -> None:  # noqa: N802
        self.bindings.clear()
        if self.observer is not None:
            self.observer.stop()
        event.accept()
