"""Actions tab: ordered action pipeline with a property editor."""

from __future__ import annotations

from typing import Optional

from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.Qt import QtCore, QtWidgets
from tik.trigger.core import iter_actions, registry

from .widgets import NameEdit


class ActionsPanel(QtWidgets.QWidget):
    """List of actions (checkable = enabled) plus editor and run buttons."""

    def __init__(self, session, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self._action_obj = None
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ ui
    def _build_ui(self) -> None:
        layout = QtWidgets.QHBoxLayout(self)
        splitter = QtWidgets.QSplitter()
        layout.addWidget(splitter)

        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        add_row = QtWidgets.QHBoxLayout()
        self.type_combo = QtWidgets.QComboBox()
        for action_cls in iter_actions():
            self.type_combo.addItem(action_cls.display_label(), action_cls.action_type)
        self.add_button = QtWidgets.QPushButton("Add")
        add_row.addWidget(self.type_combo, 1)
        add_row.addWidget(self.add_button)
        left_layout.addLayout(add_row)
        self.list = QtWidgets.QListWidget()
        left_layout.addWidget(self.list)
        tools = QtWidgets.QHBoxLayout()
        self.up_button = QtWidgets.QPushButton("Up")
        self.down_button = QtWidgets.QPushButton("Down")
        self.duplicate_button = QtWidgets.QPushButton("Duplicate")
        self.remove_button = QtWidgets.QPushButton("Remove")
        for button in (self.up_button, self.down_button, self.duplicate_button, self.remove_button):
            tools.addWidget(button)
        left_layout.addLayout(tools)
        run_row = QtWidgets.QHBoxLayout()
        self.run_button = QtWidgets.QPushButton("Run")
        self.run_until_button = QtWidgets.QPushButton("Run Until")
        self.run_all_button = QtWidgets.QPushButton("Run All")
        for button in (self.run_button, self.run_until_button, self.run_all_button):
            run_row.addWidget(button)
        left_layout.addLayout(run_row)
        splitter.addWidget(left)

        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.addWidget(QtWidgets.QLabel("<b>Action settings</b>"))
        self.name_edit = NameEdit()
        right_layout.addWidget(self.name_edit)
        self.form = FormBuilder()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form)
        right_layout.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setSizes([320, 400])

        self.add_button.clicked.connect(self.add_action)
        self.remove_button.clicked.connect(self.remove_current)
        self.duplicate_button.clicked.connect(self.duplicate_current)
        self.up_button.clicked.connect(lambda: self.move_current(-1))
        self.down_button.clicked.connect(lambda: self.move_current(1))
        self.run_button.clicked.connect(self.run_current)
        self.run_until_button.clicked.connect(self.run_until_current)
        self.run_all_button.clicked.connect(self.run_all)
        self.list.currentItemChanged.connect(self._on_selection)
        self.list.itemChanged.connect(self._on_item_changed)
        self.name_edit.renamed.connect(self._rename_current)
        self.form.changed.connect(self._on_setting_changed)
        self.form.error.connect(lambda name, message: self.session.events.log(message, level="warning"))

    # ---------------------------------------------------------------- data
    def refresh(self, select: Optional[str] = None) -> None:
        current = select or self.current_name()
        self.list.blockSignals(True)
        self.list.clear()
        for action in self.session.actions:
            item = QtWidgets.QListWidgetItem(f"{action.name}  ({action.action_type})")
            item.setData(QtCore.Qt.UserRole, action.name)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if action.enabled else QtCore.Qt.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)
        for row in range(self.list.count()):
            if self.list.item(row).data(QtCore.Qt.UserRole) == current:
                self.list.setCurrentRow(row)
                return
        self._on_selection(self.list.currentItem())

    def current_name(self) -> Optional[str]:
        item = self.list.currentItem()
        return item.data(QtCore.Qt.UserRole) if item else None

    def _on_selection(self, item, _previous=None) -> None:
        name = item.data(QtCore.Qt.UserRole) if item is not None else None
        if not name:
            self._action_obj = None
            self.form.set_target(None)
            self.name_edit.set_name("")
            return
        self._action_obj = self.session.action_object(name)
        self.name_edit.set_name(name)
        self.form.set_target(self._action_obj)

    def _on_item_changed(self, item) -> None:
        name = item.data(QtCore.Qt.UserRole)
        self.session.set_enabled(name, item.checkState() == QtCore.Qt.Checked)

    # ------------------------------------------------------------- actions
    def add_action(self):
        action_type = self.type_combo.currentData()
        if not action_type:
            return None
        current = self.current_name()
        index = self.session.action_names().index(current) + 1 if current else None
        instance = self.session.add_action(action_type, index=index)
        self.refresh(select=instance.name)
        return instance

    def remove_current(self) -> None:
        name = self.current_name()
        if name:
            self.session.remove_action(name)
            self.refresh()

    def duplicate_current(self) -> None:
        name = self.current_name()
        if name:
            copy_instance = self.session.duplicate_action(name)
            self.refresh(select=copy_instance.name)

    def move_current(self, delta: int) -> None:
        name = self.current_name()
        if not name:
            return
        names = self.session.action_names()
        index = names.index(name) + delta
        if 0 <= index < len(names):
            self.session.move_action(name, index)
            self.refresh(select=name)

    def _rename_current(self, old: str, new: str) -> None:
        try:
            self.session.rename_action(old, new)
        except Exception as error:  # noqa: BLE001 - surface to log
            self.session.events.log(str(error), level="warning")
            self.name_edit.set_name(old)
            return
        self.refresh(select=new)

    def _on_setting_changed(self, _name: str, _value) -> None:
        name = self.current_name()
        if name and self._action_obj is not None:
            self.session.update_action_settings(name, self._action_obj.values())

    def run_current(self) -> None:
        name = self.current_name()
        if name:
            self.session.run_action(name)

    def run_until_current(self) -> None:
        name = self.current_name()
        if name:
            self.session.run_all(until=name)

    def run_all(self) -> None:
        self.session.run_all()
