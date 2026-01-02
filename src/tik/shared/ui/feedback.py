from collections.abc import Callable
from pathlib import Path

from tik.shared.ui.Qt import QtWidgets


class Feedback:
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        self.parent = parent
        self.result: str | None = None

    def pop_info(
        self,
        title: str = "Info",
        text: str = "",
        details: str = "",
        critical: bool = False,
        modal: bool = True,
        on_close: Callable[[int], None] | None = None,
    ) -> int:
        """
        Show an informational dialog box.

        Args:
            title: The title of the dialog.
            text: The main text.
            details: The informative text (smaller).
            critical: If True, shows a critical icon.
            modal: If True, the dialog is modal.
            on_close: Optional callback to run when closed.

        Returns:
            The result code from the dialog execution.
        """
        message_box = QtWidgets.QMessageBox(parent=self.parent)
        icon = (
            QtWidgets.QMessageBox.Critical
            if critical
            else QtWidgets.QMessageBox.Information
        )
        message_box.setIcon(icon)
        message_box.setWindowTitle(title)
        message_box.setModal(modal)
        message_box.setText(text)
        message_box.setInformativeText(details)
        message_box.setStandardButtons(QtWidgets.QMessageBox.Ok)

        result = message_box.exec()
        if on_close:
            on_close(result)
        return result

    def pop_error(
        self,
        title: str = "Error",
        text: str = "",
        details: str = "",
        modal: bool = True,
        on_close: Callable[[int], None] | None = None,
    ) -> int:
        """Show an error dialog box."""
        return self.pop_info(
            title=title,
            text=text,
            details=details,
            critical=True,
            modal=modal,
            on_close=on_close,
        )

    def pop_question(
        self,
        title: str = "Question",
        text: str = "",
        details: str = "",
        buttons: list[str] | None = None,
        modal: bool = True,
    ) -> str | None:
        """
        Show a question dialog box with configurable buttons.

        Args:
            title: The title of the dialog.
            text: The main text.
            details: The informative text.
            buttons: List of button keys (e.g., "save", "cancel").
            modal: If True, the dialog is modal.

        Returns:
            The key of the clicked button, or None.
        """
        if buttons is None:
            buttons = ["save", "no", "cancel"]

        button_map = {
            "yes": QtWidgets.QMessageBox.Yes,
            "yes_to_all": QtWidgets.QMessageBox.YesToAll,
            "save": QtWidgets.QMessageBox.Save,
            "ok": QtWidgets.QMessageBox.Ok,
            "open": QtWidgets.QMessageBox.Open,
            "close": QtWidgets.QMessageBox.Close,
            "continue": QtWidgets.QMessageBox.Yes,
            "discard": QtWidgets.QMessageBox.Discard,
            "apply": QtWidgets.QMessageBox.Apply,
            "reset": QtWidgets.QMessageBox.Reset,
            "restore_defaults": QtWidgets.QMessageBox.RestoreDefaults,
            "help": QtWidgets.QMessageBox.Help,
            "save_all": QtWidgets.QMessageBox.SaveAll,
            "no": QtWidgets.QMessageBox.No,
            "no_to_all": QtWidgets.QMessageBox.NoToAll,
            "cancel": QtWidgets.QMessageBox.Cancel,
            "ignore": QtWidgets.QMessageBox.Ignore,
            "abort": QtWidgets.QMessageBox.Abort,
            "retry": QtWidgets.QMessageBox.Retry,
        }

        button_widgets = []
        for button_key in buttons:
            widget = button_map.get(button_key)
            if not widget:
                raise ValueError(
                    f"Invalid button: {button_key}. Valid buttons are: {list(button_map.keys())}"
                )
            button_widgets.append(widget)

        message_box = QtWidgets.QMessageBox(parent=self.parent)
        message_box.setIcon(QtWidgets.QMessageBox.Question)
        message_box.setWindowTitle(title)
        message_box.setModal(modal)
        message_box.setText(text)
        message_box.setInformativeText(details)

        # Combine buttons using bitwise OR operator
        combined_buttons = button_widgets[0]
        for widget in button_widgets[1:]:
            combined_buttons |= widget

        message_box.setStandardButtons(combined_buttons)

        result_code = message_box.exec()

        # Check against requested buttons first to ensure correct mapping
        # (e.g. distinguishing 'continue' from 'yes')
        for key in buttons:
            if result_code == button_map[key]:
                self.result = key
                return key

        # Fallback for implicit returns (like Escape key mapping to Cancel/No)
        for key, value in button_map.items():
            if result_code == value:
                self.result = key
                return key

        return None

    def browse_directory(self, modal: bool = True) -> str | None:
        """
        Browse for a directory.

        Deprecated: Consider moving to a utility function.
        """
        file_dialog = QtWidgets.QFileDialog(parent=self.parent)
        file_dialog.setModal(modal)
        file_dialog.setFileMode(QtWidgets.QFileDialog.Directory)
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                return str(Path(selected_files[0]))
        return None
