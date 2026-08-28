"""Settings of the selected action: header, generated form, override marks, step buttons."""

from __future__ import annotations

from typing import Callable, Optional

from tik.shared.ui import theme
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.Qt import QtCore, QtWidgets
from tik.trigger.core import registry
from tik.trigger.handler import ActionHandle


class ActionSettingsPanel(QtWidgets.QWidget):
    run_requested = QtCore.Signal(str)  # path
    run_until_requested = QtCore.Signal(str)
    save_requested = QtCore.Signal(str)
    edited = QtCore.Signal(str)  # path
    open_file_requested = QtCore.Signal(str, str)  # path, extension

    def __init__(self, parent=None, file_browser: Optional[Callable] = None) -> None:
        super().__init__(parent)
        self._handle: Optional[ActionHandle] = None
        self._action = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        header = QtWidgets.QHBoxLayout()
        self.icon = QtWidgets.QLabel()
        self.title = QtWidgets.QLabel("No action selected")
        self.title.setStyleSheet("font-size: 14px; font-weight: 600; color: #ffffff;")
        self.subtitle = QtWidgets.QLabel("")
        self.subtitle.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self.info_button = QtWidgets.QToolButton()
        self.info_button.setText("?")
        self.info_button.setAutoRaise(True)
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header.addWidget(self.icon)
        header.addLayout(titles, 1)
        header.addWidget(self.info_button)
        layout.addLayout(header)
        self.linked_note = QtWidgets.QLabel("")
        self.linked_note.setStyleSheet(f"color: {theme.LINKED}; font-size: 11px;")
        self.linked_note.setVisible(False)
        layout.addWidget(self.linked_note)
        self.form = FormBuilder(
            file_browser=file_browser,
            file_extras={".trg": ("✎", lambda path: self.open_file_requested.emit(path, ".trg"))},
        )
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(self.form)
        layout.addWidget(scroll, 1)
        buttons = QtWidgets.QHBoxLayout()
        self.save_button = QtWidgets.QPushButton("Save from scene")
        self.reset_button = QtWidgets.QPushButton("Reset overrides")
        self.run_button = QtWidgets.QPushButton("Run step")
        self.until_button = QtWidgets.QPushButton("Run until here")
        for button in (self.save_button, self.reset_button, self.run_button, self.until_button):
            button.setFlat(True)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.form.changed.connect(self._on_changed)
        self.run_button.clicked.connect(lambda: self._emit(self.run_requested))
        self.until_button.clicked.connect(lambda: self._emit(self.run_until_requested))
        self.save_button.clicked.connect(lambda: self._emit(self.save_requested))
        self.reset_button.clicked.connect(self._reset_overrides)
        self.info_button.clicked.connect(self._show_info)
        self.set_handle(None)

    # ------------------------------------------------------------- binding
    @property
    def handle(self) -> Optional[ActionHandle]:
        return self._handle

    def set_handle(self, handle: Optional[ActionHandle]) -> None:
        self._handle = handle
        enabled = handle is not None
        for widget in (self.run_button, self.until_button, self.info_button):
            widget.setEnabled(enabled)
        if handle is None:
            self.title.setText("No action selected")
            self.subtitle.setText("Pick an action in the pipeline, or press Tab to add one.")
            self.icon.clear()
            self.form.set_target(None)
            self.linked_note.setVisible(False)
            self.save_button.setVisible(False)
            self.reset_button.setVisible(False)
            return
        action_cls = registry.get_action(handle.type)
        self._action = action_cls(settings=handle.settings)
        self.icon.setPixmap(glyph_icon(initials(action_cls.display_label()), theme.CATEGORY.get(action_cls.category, theme.CATEGORY["utility"]), 26).pixmap(26, 26))
        self.title.setText(handle.name)
        self.subtitle.setText(f"{action_cls.display_label()} · {handle.path}")
        self.form.set_target(self._action)
        self.linked_note.setVisible(handle.is_linked)
        self.reset_button.setVisible(handle.is_linked)
        self.save_button.setVisible(type(self._action).save_from_scene is not registry.get_action(handle.type).__mro__[-2].save_from_scene if False else self._has_save(action_cls))
        if handle.is_linked:
            self.linked_note.setText("Referenced action — edits here are stored as overrides in this session.")
            self._refresh_override_marks()
        else:
            self.form.mark_overrides(())

    @staticmethod
    def _has_save(action_cls) -> bool:
        from tik.trigger.core.action import Action

        return action_cls.save_from_scene is not Action.save_from_scene

    def _refresh_override_marks(self) -> None:
        handle = self._handle
        if handle is None or not handle.is_linked:
            return
        override = handle._override().get("settings", {})
        reference = dict(handle.node.settings)
        self.form.mark_overrides(set(override), reference)

    def _on_changed(self, name: str, value) -> None:
        if self._handle is None:
            return
        setattr(self._handle, name, value)
        self.title.setText(self._handle.name)
        if self._handle.is_linked:
            self._refresh_override_marks()
        self.edited.emit(self._handle.path)

    def _reset_overrides(self) -> None:
        if self._handle is not None and self._handle.is_linked:
            self._handle.reset()
            self.set_handle(self._handle)
            self.edited.emit(self._handle.path)

    def _emit(self, signal) -> None:
        if self._handle is not None:
            signal.emit(self._handle.path)

    def _show_info(self) -> None:
        if self._handle is None:
            return
        action_cls = registry.get_action(self._handle.type)
        QtWidgets.QMessageBox.information(self, action_cls.display_label(), action_cls.description() or "No description.")
