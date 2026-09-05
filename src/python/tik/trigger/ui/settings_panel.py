"""Settings of the selected action.

Header, generated form, override marks and the step buttons.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from tik.shared.io import open_external
from tik.shared.ui.feedback import Feedback
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.Qt import QtCore, QtWidgets
from tik.trigger.config import trigger_settings
from tik.trigger.core import registry
from tik.trigger.core.document import BUILD
from tik.trigger.session import ActionHandle
from tik.trigger.ui.iconography import action_icon

NEW_SCRIPT_TIP = "Write a versioned stub into the session's scripts folder"
UNSAVED_TIP = "Save the session first: scripts live beside the .tr file"


class ActionSettingsPanel(QtWidgets.QWidget):
    """Header, generated form and step buttons for the selected action."""

    run_requested = QtCore.Signal(str)  # path
    save_requested = QtCore.Signal(str)
    edited = QtCore.Signal(str)  # path
    open_file_requested = QtCore.Signal(str, str)  # path, extension
    handle_changed = QtCore.Signal(object)  # the ActionHandle shown, or None

    def __init__(
        self,
        parent=None,
        file_browser: Optional[Callable] = None,
        base_dir: Optional[Callable[[], str]] = None,
    ) -> None:
        super().__init__(parent)
        self._handle: Optional[ActionHandle] = None
        self._action = None
        self._base_dir = base_dir
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        header = QtWidgets.QHBoxLayout()
        self.icon = QtWidgets.QLabel()
        self.title = QtWidgets.QLabel("No action selected")
        self.title.setObjectName("PanelTitle")
        self.subtitle = QtWidgets.QLabel("")
        self.subtitle.setObjectName("PanelSubtitle")
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
        self.linked_note.setObjectName("LinkedNote")
        self.linked_note.setVisible(False)
        layout.addWidget(self.linked_note)
        self.form = FormBuilder(
            file_browser=file_browser,
            file_extras={
                ".trg": ("✎", lambda path: self.open_file_requested.emit(path, ".trg")),
                ".py": ("✎", self.open_externally),
            },
            base_dir=base_dir,
        )
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(self.form)
        layout.addWidget(scroll, 1)
        buttons = QtWidgets.QHBoxLayout()
        self.guides_button = QtWidgets.QPushButton("Open Guide Designer")
        self.guides_button.setToolTip(
            "Author the guides file of this action in the Guide Designer"
        )
        self.guides_button.setVisible(False)
        buttons.addWidget(self.guides_button)
        self.new_script_button = QtWidgets.QPushButton("New Script…")
        self.new_script_button.setToolTip(NEW_SCRIPT_TIP)
        self.new_script_button.setVisible(False)
        buttons.addWidget(self.new_script_button)
        self.save_button = QtWidgets.QPushButton("Save from scene")
        self.reset_button = QtWidgets.QPushButton("Reset overrides")
        self.run_button = QtWidgets.QPushButton("Run step")
        buttons.addStretch(1)
        for button in (self.save_button, self.reset_button, self.run_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.form.changed.connect(self._on_changed)
        self.run_button.clicked.connect(lambda: self._emit(self.run_requested))
        self.save_button.clicked.connect(lambda: self._emit(self.save_requested))
        self.reset_button.clicked.connect(self._reset_overrides)
        self.guides_button.clicked.connect(self._open_guides)
        self.new_script_button.clicked.connect(lambda: self.new_script())
        self.info_button.clicked.connect(self._show_info)
        self.set_handle(None)

    # ------------------------------------------------------------- binding
    @property
    def handle(self) -> Optional[ActionHandle]:
        """The action being edited, or None."""
        return self._handle

    def set_handle(self, handle: Optional[ActionHandle]) -> None:
        """Show the settings of ``handle`` (None shows the empty state)."""
        self._handle = handle
        enabled = handle is not None
        for widget in (self.run_button, self.info_button):
            widget.setEnabled(enabled)
        # Publish actions never run on their own: the only way one executes is
        # as the tail of a full clean build.
        runnable = enabled and getattr(handle, "phase", BUILD) == BUILD
        self.run_button.setVisible(runnable)
        if handle is None:
            self.title.setText("No action selected")
            self.subtitle.setText(
                "Pick an action in the pipeline, or press Tab to add one."
            )
            self.icon.clear()
            self.form.set_target(None)
            self.linked_note.setVisible(False)
            self.save_button.setVisible(False)
            self.reset_button.setVisible(False)
            self.guides_button.setVisible(False)
            self.new_script_button.setVisible(False)
            self.handle_changed.emit(None)
            return
        action_cls = registry.get_action(handle.type)
        self._action = action_cls(settings=handle.settings)
        self.icon.setPixmap(action_icon(action_cls, size=26).pixmap(26, 26))
        self.title.setText(handle.name)
        self.subtitle.setText(f"{action_cls.display_label()} · {handle.path}")
        self.form.set_target(self._action)
        self.linked_note.setVisible(handle.is_linked)
        self.reset_button.setVisible(handle.is_linked)
        self.guides_button.setVisible(self._guides_field_name() is not None)
        self.new_script_button.setVisible(self._py_field_name() is not None)
        self._refresh_new_script_state()
        self.save_button.setVisible(self._has_save(action_cls))
        if handle.is_linked:
            self.linked_note.setText(
                "Referenced action — "
                "edits here are stored as overrides in this session."
            )
            self._refresh_override_marks()
        else:
            self.form.mark_overrides(())
        self.handle_changed.emit(handle)

    def _py_field_name(self) -> Optional[str]:
        """Name of the first ``.py`` FileField on the current action, if any."""
        if self._action is None:
            return None
        for name, field in type(self._action).fields().items():
            if ".py" in (getattr(field, "extensions", None) or ()):
                return name
        return None

    def _session_dir(self) -> str:
        return (self._base_dir() if self._base_dir else "") or ""

    def _refresh_new_script_state(self) -> None:
        saved = bool(self._session_dir())
        self.new_script_button.setEnabled(saved)
        self.new_script_button.setToolTip(NEW_SCRIPT_TIP if saved else UNSAVED_TIP)

    def open_externally(self, path: str) -> None:
        """Open ``path`` (relative to the session) in the external editor."""
        if not path:
            return
        target = Path(path)
        base = self._session_dir()
        if not target.is_absolute() and base:
            target = Path(base) / target
        try:
            open_external(target, trigger_settings.get("external_editor") or "")
        except OSError as error:
            Feedback(self).pop_warning(
                "Open script", f"Could not open {target}", str(error)
            )

    def new_script(self, name: Optional[str] = None) -> Optional[Path]:
        """Write a stub into ``scripts/``, point the file field at it, open it."""
        from tik.trigger.actions.script.script import create_script_file

        field_name = self._py_field_name()
        base = self._session_dir()
        if self._handle is None or field_name is None or not base:
            return None
        if name is None:
            name = Feedback(self).ask_text("New Script", "Script name", "")
            if not name:
                return None
        try:
            created = create_script_file(base, name)
        except (ValueError, OSError) as error:
            Feedback(self).pop_warning("New Script", str(error))
            return None
        relative = created.relative_to(Path(base)).as_posix()
        setattr(self._handle, field_name, relative)
        setattr(self._action, field_name, relative)
        self.form.refresh()
        self.title.setText(self._handle.name)
        self.edited.emit(self._handle.path)
        self.open_externally(relative)
        return created

    def _guides_field_name(self) -> Optional[str]:
        """Name of the first ``.trg`` FileField on the current action, if any."""
        if self._action is None:
            return None
        for name, field in type(self._action).fields().items():
            if ".trg" in (getattr(field, "extensions", None) or ()):
                return name
        return None

    def _open_guides(self) -> None:
        name = self._guides_field_name()
        if name is None:
            return
        self.open_file_requested.emit(
            str(getattr(self._action, name, "") or ""), ".trg"
        )

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
        Feedback(self).pop_info(
            action_cls.display_label(),
            action_cls.description() or "No description.",
        )
