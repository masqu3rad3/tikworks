"""Guides tab: create/inspect module guides and build the rig."""

from __future__ import annotations

from typing import Optional

from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.Qt import QtCore, QtWidgets
from tik.trigger.core import AFTERLIFE_MODES, Builder, ParentRef, Side, iter_modules, registry
from tik.trigger.core.schemas import ModuleInstance

from .widgets import NameEdit

SIDES = ["Left", "Right", "Center", "Both"]


class GuidesPanel(QtWidgets.QWidget):
    """Module palette + instance tree + property editor."""

    built = QtCore.Signal(object)

    def __init__(self, backend, session, parent=None) -> None:
        super().__init__(parent)
        self.backend = backend
        self.session = session
        self._instances: dict[str, ModuleInstance] = {}
        self._current: Optional[ModuleInstance] = None
        self._module_obj = None
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ ui
    def _build_ui(self) -> None:
        layout = QtWidgets.QHBoxLayout(self)
        splitter = QtWidgets.QSplitter()
        layout.addWidget(splitter)

        # left: palette
        palette = QtWidgets.QWidget()
        palette_layout = QtWidgets.QVBoxLayout(palette)
        palette_layout.addWidget(QtWidgets.QLabel("<b>Modules</b>"))
        self.module_list = QtWidgets.QListWidget()
        for module_cls in iter_modules():
            item = QtWidgets.QListWidgetItem(module_cls.display_label())
            item.setData(QtCore.Qt.UserRole, module_cls.module_type)
            self.module_list.addItem(item)
        palette_layout.addWidget(self.module_list)
        side_row = QtWidgets.QHBoxLayout()
        side_row.addWidget(QtWidgets.QLabel("Side"))
        self.side_combo = QtWidgets.QComboBox()
        self.side_combo.addItems(SIDES)
        side_row.addWidget(self.side_combo)
        palette_layout.addLayout(side_row)
        self.create_button = QtWidgets.QPushButton("Create Guides")
        self.create_button.setToolTip("Creates guides under the selected guide (if any)")
        palette_layout.addWidget(self.create_button)
        splitter.addWidget(palette)

        # middle: instance tree
        tree_widget = QtWidgets.QWidget()
        tree_layout = QtWidgets.QVBoxLayout(tree_widget)
        tree_layout.addWidget(QtWidgets.QLabel("<b>Guides in scene</b>"))
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Module", "Side"])
        self.tree.setColumnWidth(0, 160)
        tree_layout.addWidget(self.tree)
        buttons = QtWidgets.QHBoxLayout()
        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.select_button = QtWidgets.QPushButton("Select")
        self.delete_button = QtWidgets.QPushButton("Delete")
        for button in (self.refresh_button, self.select_button, self.delete_button):
            buttons.addWidget(button)
        tree_layout.addLayout(buttons)
        build_box = QtWidgets.QGroupBox("Build")
        build_layout = QtWidgets.QFormLayout(build_box)
        self.rig_name = QtWidgets.QLineEdit("trigger")
        self.afterlife = QtWidgets.QComboBox()
        self.afterlife.addItems(list(AFTERLIFE_MODES))
        self.afterlife.setCurrentText("keep")
        self.build_button = QtWidgets.QPushButton("Build Rig")
        build_layout.addRow("Rig name", self.rig_name)
        build_layout.addRow("Guides after build", self.afterlife)
        build_layout.addRow(self.build_button)
        tree_layout.addWidget(build_box)
        splitter.addWidget(tree_widget)

        # right: properties
        props = QtWidgets.QWidget()
        props_layout = QtWidgets.QVBoxLayout(props)
        props_layout.addWidget(QtWidgets.QLabel("<b>Properties</b>"))
        self.name_edit = NameEdit()
        self.name_edit.setPlaceholderText("instance name")
        props_layout.addWidget(self.name_edit)
        self.form = FormBuilder(node_picker=self._pick_node)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form)
        props_layout.addWidget(scroll)
        splitter.addWidget(props)
        splitter.setSizes([160, 320, 280])

        self.create_button.clicked.connect(self.create_guides)
        self.refresh_button.clicked.connect(self.refresh)
        self.select_button.clicked.connect(self.select_current)
        self.delete_button.clicked.connect(self.delete_current)
        self.build_button.clicked.connect(self.build)
        self.tree.currentItemChanged.connect(self._on_tree_selection)
        self.name_edit.renamed.connect(self._rename_current)
        self.form.changed.connect(self._on_setting_changed)
        self.form.error.connect(lambda name, message: self.session.events.log(message, level="warning"))

    # ---------------------------------------------------------------- data
    def refresh(self) -> None:
        current_id = self._current.instance_id if self._current else None
        self._instances = {item.instance_id: item for item in self.backend.find_instances()}
        self.tree.clear()
        items: dict[str, QtWidgets.QTreeWidgetItem] = {}
        pending = list(self._instances.values())
        while pending:
            remaining = []
            for instance in pending:
                parent_id = instance.parent.instance_id if instance.parent else None
                if parent_id and parent_id in self._instances and parent_id not in items:
                    remaining.append(instance)
                    continue
                item = QtWidgets.QTreeWidgetItem([instance.name, instance.module_type, instance.side])
                item.setData(0, QtCore.Qt.UserRole, instance.instance_id)
                if parent_id in items:
                    items[parent_id].addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
                items[instance.instance_id] = item
            if len(remaining) == len(pending):
                break  # orphaned parents; add flat
            pending = remaining
        self.tree.expandAll()
        if current_id in items:
            self.tree.setCurrentItem(items[current_id])
        else:
            self._set_current(None)

    def _on_tree_selection(self, item, _previous=None) -> None:
        instance_id = item.data(0, QtCore.Qt.UserRole) if item is not None else None
        self._set_current(self._instances.get(instance_id))

    def _set_current(self, instance: Optional[ModuleInstance]) -> None:
        self._current = instance
        if instance is None:
            self._module_obj = None
            self.form.set_target(None)
            self.name_edit.set_name("")
            return
        module_cls = registry.get_module(instance.module_type)
        self._module_obj = module_cls.from_instance(instance)
        self.name_edit.set_name(instance.name)
        self.form.set_target(self._module_obj)

    @property
    def current(self) -> Optional[ModuleInstance]:
        return self._current

    def selected_module_type(self) -> Optional[str]:
        item = self.module_list.currentItem()
        return item.data(QtCore.Qt.UserRole) if item else None

    # ------------------------------------------------------------- actions
    def create_guides(self) -> list[ModuleInstance]:
        module_type = self.selected_module_type()
        if not module_type:
            self.session.events.log("Pick a module first.", level="warning")
            return []
        module_cls = registry.get_module(module_type)
        parent_ref = self._parent_from_selection()
        side_text = self.side_combo.currentText()
        sides = [Side.LEFT, Side.RIGHT] if side_text == "Both" else [Side.from_value(side_text)]
        if not module_cls.sided:
            sides = [Side.CENTER]
        created = []
        for side in sides:
            module = module_cls(side=side)
            created.append(self.backend.create_guides(module, parent=parent_ref))
        self.refresh()
        if created:
            self._select_instance(created[-1].instance_id)
        return created

    def _parent_from_selection(self) -> Optional[ParentRef]:
        picker = getattr(self.backend, "selected_guide", None)
        if picker is None:
            return None
        return picker()

    def _select_instance(self, instance_id: str) -> None:
        iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, QtCore.Qt.UserRole) == instance_id:
                self.tree.setCurrentItem(item)
                return
            iterator += 1

    def select_current(self) -> None:
        if self._current is None:
            return
        selector = getattr(self.backend, "select_guides", None)
        if selector is not None:
            selector(self._current.instance_id)

    def delete_current(self) -> None:
        if self._current is None:
            return
        self.backend.delete_guides(self._current.instance_id)
        self._current = None
        self.refresh()

    def _rename_current(self, _old: str, new: str) -> None:
        if self._current is None:
            return
        self.backend.rename_instance(self._current.instance_id, new)
        self.refresh()

    def _on_setting_changed(self, _name: str, _value) -> None:
        if self._current is None or self._module_obj is None:
            return
        self.backend.write_settings(self._current.instance_id, self._module_obj.values())

    def _pick_node(self) -> str:
        picker = getattr(self.backend, "selected_node_name", None)
        return picker() if picker else ""

    def build(self):
        builder = Builder(self.backend, self.session.events)
        report = builder.build(rig_name=self.rig_name.text() or "trigger", afterlife=self.afterlife.currentText())
        self.refresh()
        self.built.emit(report)
        return report
