"""The one place a tikworks tool asks the user something.

Every dialog in the repo goes through here: message boxes, file browsers and
text prompts alike. That is not tidiness for its own sake -- it is what makes
three things possible at all. A pipeline can replace file picking everywhere
with one ``set_browser`` call; a headless test run can answer message boxes
with ``set_handler`` instead of hanging on a modal; and parenting under Maya
is fixed in one place rather than twelve.

Widgets that already accept their own ``browser`` callable keep it, and it
still wins: being handed a picker is more specific than the module default.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Optional

from tik.shared.ui.Qt import QtWidgets
from tik.shared.ui.qtmaya import get_main_window

#: Button key -> ``QMessageBox`` standard button. Keys are what callers pass
#: and what ``pop_question`` gives back, so a call site never touches a Qt
#: enum: ``buttons=["save", "discard", "cancel"]`` in, ``"discard"`` out.
#: An entry may also be ``(key, label)`` -- ``("yes", "Sync and redraw")`` --
#: to say what the button reads without changing the key it answers with.
BUTTONS = {
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

_ICONS = {
    "info": QtWidgets.QMessageBox.Information,
    "error": QtWidgets.QMessageBox.Critical,
    "warning": QtWidgets.QMessageBox.Warning,
    "question": QtWidgets.QMessageBox.Question,
    "about": QtWidgets.QMessageBox.Information,
}

#: ``fn(mode, extensions, current) -> str``; ``mode`` is open/save/dir.
_browser: Optional[Callable] = None
#: ``fn(kind, title, text, details, buttons) -> str | None``. Returning None
#: falls through to a real dialog.
_handler: Optional[Callable] = None


def set_browser(browser: Optional[Callable]) -> Optional[Callable]:
    """Route every file dialog through ``browser``; returns the previous one.

    The hook a pipeline uses to put its own asset browser behind every Browse
    button in every tool at once.
    """
    global _browser
    previous, _browser = _browser, browser
    return previous


def set_handler(handler: Optional[Callable]) -> Optional[Callable]:
    """Answer message boxes with ``handler``; returns the previous one.

    Returning ``None`` from the handler falls through to a real dialog, so a
    handler can intercept one kind of question and leave the rest alone.
    """
    global _handler
    previous, _handler = _handler, handler
    return previous


class Feedback:
    """Dialogs, parented to ``parent`` (or Maya's main window when None)."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        self.parent = parent
        self.result: Optional[str] = None

    def _host(self):
        """The dialog's parent, resolved at dialog time, not at construction.

        A ``Feedback`` built during import would otherwise capture a main
        window that does not exist yet.
        """
        return self.parent if self.parent is not None else get_main_window()

    # ------------------------------------------------------ message boxes
    def _pop(
        self,
        kind: str,
        title: str,
        text: str,
        details: str,
        buttons: list,
        modal: bool,
        on_close: Optional[Callable] = None,
    ) -> Optional[str]:
        """Build, show and decode one message box. The single Qt entry point."""
        # A button may carry a custom label: ("yes", "Sync and redraw"). The
        # key is what callers pass and what comes back, so a three-way
        # question can read in the caller's own words without any call site
        # -- or the handler seam -- learning a Qt enum.
        labels: dict = {}
        keys: list = []
        for item in buttons:
            if isinstance(item, tuple):
                key, label = item
                labels[key] = label
            else:
                key = item
            keys.append(key)
        buttons = keys

        if _handler is not None:
            answered = _handler(kind, title, text, details, list(buttons))
            if answered is not None:
                if on_close:
                    on_close(BUTTONS.get(answered, 0))
                self.result = answered
                return answered

        unknown = [key for key in buttons if key not in BUTTONS]
        if unknown:
            raise ValueError(
                f"Invalid button(s): {unknown}. Valid buttons are: {sorted(BUTTONS)}"
            )

        message_box = QtWidgets.QMessageBox(parent=self._host())
        message_box.setIcon(_ICONS[kind])
        message_box.setWindowTitle(title)
        message_box.setModal(modal)
        message_box.setText(text)
        message_box.setInformativeText(details)

        standard = BUTTONS[buttons[0]]
        for key in buttons[1:]:
            standard |= BUTTONS[key]
        message_box.setStandardButtons(standard)
        # the first button offered is the safe one -- Save, not Discard
        message_box.setDefaultButton(BUTTONS[buttons[0]])
        for key, label in labels.items():
            button = message_box.button(BUTTONS[key])
            if button is not None:
                button.setText(label)

        code = message_box.exec()
        if on_close:
            on_close(code)

        # requested buttons first: "continue" and "yes" share a Qt value, and
        # the caller's own vocabulary is the one to answer in
        for key in buttons:
            if code == BUTTONS[key]:
                self.result = key
                return key
        for key, value in BUTTONS.items():
            if code == value:
                self.result = key
                return key
        return None

    def pop_info(
        self,
        title: str = "Info",
        text: str = "",
        details: str = "",
        critical: bool = False,
        modal: bool = True,
        on_close: Optional[Callable[[int], None]] = None,
    ) -> int:
        """Show an informational dialog; ``critical`` makes it an error."""
        self._pop(
            "error" if critical else "info",
            title,
            text,
            details,
            ["ok"],
            modal,
            on_close,
        )
        return QtWidgets.QMessageBox.Ok

    def pop_error(
        self,
        title: str = "Error",
        text: str = "",
        details: str = "",
        modal: bool = True,
        on_close: Optional[Callable[[int], None]] = None,
    ) -> int:
        """Show an error dialog."""
        return self.pop_info(
            title=title,
            text=text,
            details=details,
            critical=True,
            modal=modal,
            on_close=on_close,
        )

    def pop_warning(
        self,
        title: str = "Warning",
        text: str = "",
        details: str = "",
        modal: bool = True,
        on_close: Optional[Callable[[int], None]] = None,
    ) -> int:
        """Show a warning: something worth stopping for, but not a failure."""
        self._pop("warning", title, text, details, ["ok"], modal, on_close)
        return QtWidgets.QMessageBox.Ok

    def pop_about(self, title: str = "About", text: str = "") -> None:
        """Show a version/about box."""
        self._pop("about", title, text, "", ["ok"], True)

    def pop_question(
        self,
        title: str = "Question",
        text: str = "",
        details: str = "",
        buttons: Optional[list] = None,
        modal: bool = True,
    ) -> Optional[str]:
        """Ask a question; returns the key of the button that was clicked.

        The first key in ``buttons`` becomes the default, so the safe answer
        is the one Enter picks.
        """
        return self._pop(
            "question",
            title,
            text,
            details,
            list(buttons or ["save", "no", "cancel"]),
            modal,
        )

    # ----------------------------------------------------------- browsing
    @staticmethod
    def _file_filter(extensions: Sequence[str]) -> str:
        """A Qt name filter for ``extensions`` (``.tr`` -> ``Files (*.tr)``)."""
        if not extensions:
            return "All files (*)"
        return "Files (" + " ".join(f"*{ext}" for ext in extensions) + ")"

    def browse_open(
        self,
        caption: str = "Open",
        start: str = "",
        extensions: Sequence[str] = (),
        file_filter: Optional[str] = None,
    ) -> str:
        """Ask for an existing file; ``""`` when the user cancels."""
        if _browser is not None:
            return _browser("open", tuple(extensions), start) or ""
        picked, _selected = QtWidgets.QFileDialog.getOpenFileName(
            self._host(), caption, start, file_filter or self._file_filter(extensions)
        )
        return picked or ""

    def browse_save(
        self,
        caption: str = "Save",
        start: str = "",
        extensions: Sequence[str] = (),
        file_filter: Optional[str] = None,
    ) -> str:
        """Ask where to write a file; ``""`` when the user cancels."""
        if _browser is not None:
            return _browser("save", tuple(extensions), start) or ""
        picked, _selected = QtWidgets.QFileDialog.getSaveFileName(
            self._host(), caption, start, file_filter or self._file_filter(extensions)
        )
        return picked or ""

    def browse_dir(self, caption: str = "Choose folder", start: str = "") -> str:
        """Ask for a folder; ``""`` when the user cancels."""
        if _browser is not None:
            return _browser("dir", (), start) or ""
        picked = QtWidgets.QFileDialog.getExistingDirectory(
            self._host(), caption, start
        )
        return picked or ""

    def browse_directory(self, modal: bool = True) -> Optional[str]:
        """Deprecated: use ``browse_dir``."""
        picked = self.browse_dir()
        return str(Path(picked)) if picked else None

    # -------------------------------------------------------------- input
    def ask_text(
        self, title: str = "", label: str = "", text: str = ""
    ) -> Optional[str]:
        """Ask for a line of text; ``None`` when the user cancels."""
        entered, accepted = QtWidgets.QInputDialog.getText(
            self._host(), title, label, text=text
        )
        return entered if accepted else None
