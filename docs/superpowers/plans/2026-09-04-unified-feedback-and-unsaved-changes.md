# Unified Feedback and Unsaved-Changes Guards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Closing a session tab or the Trigger window with unsaved work offers Save / Discard / Cancel, guide poses in the Maya scene count as unsaved work, and `shared/ui/feedback.py` becomes the one module in the repo that shows a dialog.

**Architecture:** `Feedback` grows from three message-box helpers into the full dialog surface — message boxes, file browsers, text prompts — with two module-level seams: `set_browser` (a pipeline supplies its own file picker) and `set_handler` (tests answer message boxes without a modal). `TriggerWindow` gets one guard, `_confirm_close(view)`, used by `close_tab`, `closeEvent` and Maya's `dockCloseEventTriggered`; it captures guide poses for the checked-out session before testing `is_modified`. The twelve raw Qt dialog call sites move over, and an ast-based boundary test keeps them there.

**Tech Stack:** Python 3.10+, Qt via `tik.shared.ui.Qt` (PySide2/6 through `tik/vendor/Qt.py`), pytest. UI tests run under `mayapy` with `TIK_TESTS_NO_MAYA=1` and `QT_QPA_PLATFORM=offscreen`.

**Spec:** `docs/superpowers/specs/2026-09-04-unified-feedback-and-unsaved-changes-design.md`

## Global Constraints

- No third-party dependencies. Stdlib and Maya-bundled modules only.
- Qt is imported as `from tik.shared.ui.Qt import QtWidgets` — never `PySide2`/`PySide6` directly.
- `tik/trigger/core` stays pure Python (no Maya, no Qt). Nothing in this plan touches it.
- Lines wrap at 88 columns; `black`, `isort` (profile black) and `flake8` must pass. Run `make format` before committing.
- No single-letter names.
- Test commands (from the repo root, Windows PowerShell):
  - UI: `$env:PYTHONPATH="$PWD\src\python"; $env:TIK_TESTS_NO_MAYA="1"; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui -q`
  - Unit: `$env:PYTHONPATH="$PWD\src\python"; mayapy -m pytest tests/unit -q`
- Baseline before any change: `tests/ui` is 177 passed.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/python/tik/shared/ui/feedback.py` | **Modify.** The whole dialog surface: message boxes, file browsers, text prompt, and the `set_browser` / `set_handler` seams. |
| `src/python/tik/trigger/ui/main.py` | **Modify.** `ask_save_discard`, `_confirm_close`, `_save_view`; `close_tab` / `closeEvent` / `dockCloseEventTriggered` wiring; the `open_session` untouched-tab fix; the `_touch` fix; four file dialogs and two message boxes routed through `Feedback`. |
| `src/python/tik/trigger/ui/settings_panel.py` | **Modify.** One `QMessageBox.information` → `pop_info`. |
| `src/python/tik/trigger/ui/designer/commands.py` | **Modify.** `QInputDialog.getText` → `ask_text`; `_pick`'s two `QFileDialog` calls → `browse_open` / `browse_save`. |
| `src/python/tik/shared/ui/fields.py` | **Modify.** `_browse` fallback → `Feedback`. |
| `src/python/tik/shared/ui/versioned_field.py` | **Modify.** `_browse` fallback → `Feedback`. |
| `tests/ui/test_feedback.py` | **Create.** The `Feedback` surface and its two seams. |
| `tests/ui/test_unsaved_changes.py` | **Create.** The close guard, end to end through `TriggerWindow`. |
| `tests/unit/test_dialog_boundaries.py` | **Create.** No raw dialog classes outside `feedback.py`. |
| `tests/ui/test_menus.py`, `tests/ui/test_pipeline_ui.py` | **Modify.** `ask_discard` → `ask_save_discard`. |

Task order matters: Task 1 builds the surface everything else consumes, Task 2 the guard, Task 3 the sweep, Task 4 the rule that holds the sweep in place.

---

### Task 1: The `Feedback` dialog surface

**Files:**
- Modify: `src/python/tik/shared/ui/feedback.py`
- Test: `tests/ui/test_feedback.py` (create)

**Interfaces:**
- Consumes: `tik.shared.ui.Qt.QtWidgets`, `tik.shared.ui.qtmaya.get_main_window`.
- Produces:
  - `Feedback(parent: QWidget | None = None)`
  - `Feedback.pop_info(title, text, details="", critical=False, modal=True, on_close=None) -> int`
  - `Feedback.pop_error(title, text, details="", modal=True, on_close=None) -> int`
  - `Feedback.pop_warning(title, text, details="", modal=True, on_close=None) -> int`
  - `Feedback.pop_about(title="About", text="") -> None`
  - `Feedback.pop_question(title, text, details="", buttons=None, modal=True) -> str | None`
  - `Feedback.browse_open(caption="Open", start="", extensions=(), file_filter=None) -> str`
  - `Feedback.browse_save(caption="Save", start="", extensions=(), file_filter=None) -> str`
  - `Feedback.browse_dir(caption="Choose folder", start="") -> str`
  - `Feedback.browse_directory(modal=True) -> str | None` (deprecated alias)
  - `Feedback.ask_text(title, label, text="") -> str | None`
  - `set_browser(fn) -> previous` where `fn(mode, extensions, current) -> str`, `mode` in `"open" | "save" | "dir"`
  - `set_handler(fn) -> previous` where `fn(kind, title, text, details, buttons) -> str | None`, `kind` in `"info" | "error" | "warning" | "about" | "question"`

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_feedback.py`:

```python
"""The shared dialog surface: every tikworks dialog goes through it."""

from __future__ import annotations

import pytest

from tik.shared.ui import feedback
from tik.shared.ui.feedback import Feedback


@pytest.fixture(autouse=True)
def _clean_seams():
    """Never let a seam leak into another test -- they are module state."""
    previous_handler = feedback.set_handler(None)
    previous_browser = feedback.set_browser(None)
    yield
    feedback.set_handler(previous_handler)
    feedback.set_browser(previous_browser)


def test_handler_answers_a_question_without_a_modal(qapp):
    """The seam that makes a headless run impossible to hang."""
    seen = []

    def handler(kind, title, text, details, buttons):
        seen.append((kind, title, buttons))
        return "discard"

    feedback.set_handler(handler)
    answer = Feedback().pop_question(
        title="Unsaved changes",
        text="Save changes?",
        buttons=["save", "discard", "cancel"],
    )
    assert answer == "discard"
    assert seen == [("question", "Unsaved changes", ["save", "discard", "cancel"])]


def test_handler_answers_info_error_warning_and_about(qapp):
    kinds = []
    feedback.set_handler(
        lambda kind, title, text, details, buttons: kinds.append(kind) or "ok"
    )
    box = Feedback()
    box.pop_info("Info", "hello")
    box.pop_error("Error", "boom")
    box.pop_warning("Careful", "hmm")
    box.pop_about("About", "v1")
    assert kinds == ["info", "error", "warning", "about"]


def test_set_handler_returns_the_previous_handler(qapp):
    first = lambda *args: "ok"  # noqa: E731 - a stand-in, not a definition
    assert feedback.set_handler(first) is None
    assert feedback.set_handler(None) is first


def test_pop_question_rejects_an_unknown_button(qapp):
    with pytest.raises(ValueError):
        Feedback().pop_question(buttons=["save", "explode"])


def test_browse_helpers_use_the_module_browser(qapp):
    calls = []

    def browser(mode, extensions, current):
        calls.append((mode, tuple(extensions), current))
        return "D:/picked.tr"

    feedback.set_browser(browser)
    box = Feedback()
    assert box.browse_open("Open", "D:/start", [".tr"]) == "D:/picked.tr"
    assert box.browse_save("Save", "", [".tr"]) == "D:/picked.tr"
    assert box.browse_dir("Folder", "D:/here") == "D:/picked.tr"
    assert calls == [
        ("open", (".tr",), "D:/start"),
        ("save", (".tr",), ""),
        ("dir", (), "D:/here"),
    ]


def test_a_browser_that_cancels_returns_an_empty_string(qapp):
    feedback.set_browser(lambda mode, extensions, current: None)
    assert Feedback().browse_open() == ""


def test_file_filter_is_derived_from_extensions_but_can_be_given(qapp):
    assert Feedback._file_filter(()) == "All files (*)"
    assert Feedback._file_filter((".tr",)) == "Files (*.tr)"
    assert Feedback._file_filter((".tr", ".trg")) == "Files (*.tr *.trg)"


def test_parent_falls_back_to_the_maya_main_window_lazily(qapp, monkeypatch):
    """Resolved at dialog time: a Feedback built at import must not capture
    a main window that does not exist yet."""
    box = Feedback()
    assert box.parent is None
    monkeypatch.setattr(feedback, "get_main_window", lambda: "main-window")
    assert box._host() == "main-window"
    explicit = Feedback("mine")
    assert explicit._host() == "mine"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$env:PYTHONPATH="$PWD\src\python"; $env:TIK_TESTS_NO_MAYA="1"; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui/test_feedback.py -q`

Expected: FAIL — `AttributeError: module 'tik.shared.ui.feedback' has no attribute 'set_handler'`.

- [ ] **Step 3: Rewrite `feedback.py`**

Replace the whole file with:

```python
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
        buttons: list[str],
        modal: bool,
        on_close: Optional[Callable] = None,
    ):
        """Build, show and decode one message box. The single Qt entry point."""
        if _handler is not None:
            answered = _handler(kind, title, text, details, list(buttons))
            if answered is not None:
                if on_close:
                    on_close(BUTTONS.get(answered, 0))
                return answered

        unknown = [key for key in buttons if key not in BUTTONS]
        if unknown:
            raise ValueError(
                f"Invalid button(s): {unknown}. Valid buttons are: "
                f"{sorted(BUTTONS)}"
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
        buttons: Optional[list[str]] = None,
        modal: bool = True,
    ) -> Optional[str]:
        """Ask a question; returns the key of the button that was clicked.

        The first key in ``buttons`` becomes the default, so the safe answer
        is the one Enter picks.
        """
        return self._pop(
            "question", title, text, details, list(buttons or ["save", "no", "cancel"]), modal
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
        return QtWidgets.QFileDialog.getExistingDirectory(
            self._host(), caption, start
        ) or ""

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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$env:PYTHONPATH="$PWD\src\python"; $env:TIK_TESTS_NO_MAYA="1"; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui/test_feedback.py -q`

Expected: PASS, 8 tests.

Then confirm nothing regressed: `mayapy -m pytest tests/ui -q` → 185 passed.

- [ ] **Step 5: Format and commit**

```bash
python -m black src/python/tik/shared/ui/feedback.py tests/ui/test_feedback.py
python -m isort src/python/tik/shared/ui/feedback.py tests/ui/test_feedback.py
git add src/python/tik/shared/ui/feedback.py tests/ui/test_feedback.py
git commit -m "feat(ui): make feedback.py the shared dialog surface"
```

---

### Task 2: The close guard

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py`
- Modify: `tests/ui/test_menus.py:224`, `tests/ui/test_pipeline_ui.py:268`
- Test: `tests/ui/test_unsaved_changes.py` (create)

**Interfaces:**
- Consumes: `Feedback` and `set_handler` from Task 1; `Session.capture_guides() -> bool`, `Session.is_modified`, `Session.save(file_path=None)`, `Session.touch()`.
- Produces:
  - `TriggerWindow.ask_save_discard(session) -> "save" | "discard" | "cancel"`
  - `TriggerWindow._confirm_close(view) -> bool`
  - `TriggerWindow._save_view(view, path=None) -> bool`
  - `TriggerWindow.ask_discard` is **removed**.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_unsaved_changes.py`:

```python
"""Closing must never silently drop a rigger's work."""

from __future__ import annotations

import pytest

from tik.shared.ui import feedback
from tik.trigger.ui.main import TriggerWindow


@pytest.fixture
def window(qapp):
    made = TriggerWindow()
    yield made
    # never let a stuck dialog hang teardown
    made.ask_save_discard = lambda session: "discard"
    made.close()


@pytest.fixture(autouse=True)
def _clean_seams():
    previous = feedback.set_handler(None)
    yield
    feedback.set_handler(previous)


def _answer(window, *replies):
    """Queue answers for ask_save_discard and record what it was asked."""
    asked = []
    answers = list(replies)

    def ask(session):
        asked.append(session.name)
        return answers.pop(0) if answers else "cancel"

    window.ask_save_discard = ask
    return asked


def test_a_clean_tab_closes_without_asking(window):
    asked = _answer(window, "cancel")
    assert window.close_tab(0) is True
    assert asked == []


def test_discard_closes_the_tab(window):
    window.current_view.add_action("mark")
    asked = _answer(window, "discard")
    assert window.close_tab(0) is True
    assert asked == ["untitled"]


def test_cancel_keeps_the_tab(window):
    view = window.current_view
    view.add_action("mark")
    _answer(window, "cancel")
    assert window.close_tab(0) is False
    assert window.tabs.count() == 1
    assert window.current_view is view


def test_save_writes_the_session_then_closes(window, tmp_path, monkeypatch):
    view = window.current_view
    view.add_action("mark")
    target = tmp_path / "hero.tr"
    monkeypatch.setattr(
        feedback.Feedback, "browse_save", lambda self, *args, **kw: str(target)
    )
    _answer(window, "save")
    assert window.close_tab(0) is True
    assert target.exists()


def test_a_cancelled_save_as_blocks_the_close(window, monkeypatch):
    view = window.current_view
    view.add_action("mark")
    monkeypatch.setattr(feedback.Feedback, "browse_save", lambda self, *a, **k: "")
    _answer(window, "save")
    assert window.close_tab(0) is False
    assert window.tabs.count() == 1


def test_close_event_asks_once_per_dirty_tab(window):
    window.current_view.add_action("mark")
    second = window.new_session()
    second.add_action("mark")
    asked = _answer(window, "discard", "discard")
    window.close()
    assert len(asked) == 2


def test_cancel_on_the_second_tab_aborts_the_whole_close(window, tmp_path):
    """The first tab is saved and stays saved -- Cancel stops the close, it
    does not roll a completed save back."""
    first = window.current_view
    first.add_action("mark")
    first.session.save(str(tmp_path / "first.tr"))
    first.add_action("mark")
    second = window.new_session()
    second.add_action("mark")

    asked = _answer(window, "save", "cancel")
    event = _CloseEvent()
    window.closeEvent(event)
    assert event.ignored is True
    assert asked == ["first.tr", "untitled"]
    assert first.session.is_modified is False


class _CloseEvent:
    """A QCloseEvent stand-in: closeEvent only ever calls ignore()."""

    def __init__(self) -> None:
        self.ignored = False

    def ignore(self) -> None:
        self.ignored = True

    def accept(self) -> None:
        pass


def test_guide_drift_is_captured_before_the_dirty_check(window):
    """Nothing in Maya fires when a guide is dragged, so a clean-looking
    session must be re-read from the scene before we believe it."""
    view = window.current_view
    window._checked_out_view = view
    captured = []

    def capture():
        captured.append(True)
        view.session.document.meta["dragged"] = "yes"
        return True

    view.session.capture_guides = capture
    asked = _answer(window, "discard")
    assert window.close_tab(0) is True
    assert captured == [True]
    assert asked == ["untitled"]


def test_a_tab_that_does_not_own_the_scene_is_not_captured(window):
    view = window.current_view
    window._checked_out_view = None
    called = []
    view.session.capture_guides = lambda: called.append(True)
    window.close_tab(0)
    assert called == []


def test_a_failing_capture_does_not_trap_the_window(window):
    view = window.current_view
    window._checked_out_view = view

    def explode():
        raise RuntimeError("no scene")

    view.session.capture_guides = explode
    _answer(window, "cancel")
    assert window.close_tab(0) is True  # clean session: closes anyway


def test_open_session_keeps_a_modified_untitled_tab(window, tmp_path):
    """The untouched-tab sweep judged emptiness by the action list, so a tab
    holding guides but no actions was destroyed without a word."""
    saved = window.current_view
    saved.add_action("mark")
    saved.session.save(str(tmp_path / "hero.tr"))
    window.close_tab(0)

    scratch = window.current_view
    scratch.session.document.meta["note"] = "unsaved guide work"
    scratch.session.touch()
    assert scratch.session.is_modified

    window.open_session(str(tmp_path / "hero.tr"))
    assert scratch in window.views


def test_import_actions_records_an_undo_step(window, tmp_path):
    """main.import_actions called session._touch(), which does not exist."""
    source = window.new_session()
    source.add_action("mark")
    source.session.save(str(tmp_path / "source.tr"))
    window.close_tab(window.tabs.indexOf(source))

    target = window.current_view
    window.tabs.setCurrentWidget(target)
    window.import_actions(str(tmp_path / "source.tr"))
    assert target.session.paths() == ["mark"]
    assert target.session.can_undo is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `... mayapy -m pytest tests/ui/test_unsaved_changes.py -q`

Expected: FAIL — `AttributeError: 'TriggerWindow' object has no attribute 'ask_save_discard'` on the first test that assigns it is fine (assignment succeeds), so the real first failure is `test_discard_closes_the_tab`, where `close_tab` still calls `ask_discard` and never consults the stub.

- [ ] **Step 3: Implement the guard in `main.py`**

Add the import beside the other shared-ui imports:

```python
from tik.shared.ui.feedback import Feedback
```

Replace `ask_discard` (currently at `main.py:638-645`) with:

```python
    def ask_save_discard(self, session: Session) -> str:
        """Ask what to do with ``session``'s unsaved changes.

        Returns ``"save"``, ``"discard"`` or ``"cancel"`` -- never a Qt enum,
        so the callers stay readable and a test can answer with a string.
        """
        answer = Feedback(self).pop_question(
            title="Unsaved changes",
            text=f"Save changes to {session.name} before closing?",
            details="Your changes will be lost if you discard them.",
            buttons=["save", "discard", "cancel"],
        )
        return answer or "cancel"

    def _save_view(self, view, path: Optional[str] = None) -> bool:
        """Save ``view``'s session; False when it could not be written.

        Targets a view rather than the current tab: closing the window saves
        tabs that are not the one in front.
        """
        session = view.session
        if not path and session.file_path is None:
            path = Feedback(self).browse_save(
                "Save session", "", (EXTENSION,), FILE_FILTER
            )
            if not path:
                return False
        try:
            session.save(path or None)
        except Exception as error:  # noqa: BLE001 - report, never trap
            self.events.log(f"Could not save {session.name}: {error}", "warning")
            return False
        self._remember(str(session.file_path))
        self._update_title()
        return not session.is_modified

    def _confirm_close(self, view) -> bool:
        """True when ``view``'s tab may close: clean, saved, or discarded."""
        if not isinstance(view, SessionView):
            return True
        if view is self._checked_out_view:
            # nothing in Maya fires when a guide is dragged, so a session can
            # look clean while the scene holds an afternoon of posing
            try:
                view.session.capture_guides()
            except Exception as error:  # noqa: BLE001 - never trap the window
                self.events.log(f"Could not read the guides: {error}", "warning")
        if not view.session.is_modified:
            return True
        answer = self.ask_save_discard(view.session)
        if answer == "discard":
            return True
        if answer != "save":
            return False
        return self._save_view(view)
```

Note `self.events.log(msg, "warning")` — check the existing call style in this
file, which is `self.events.log(msg, level="warning")`; use that keyword form.

Rewrite `close_tab`:

```python
    def close_tab(self, index: int) -> bool:
        """Close the tab at ``index`` unless the user keeps unsaved changes."""
        view = self.tabs.widget(index)
        if not self._confirm_close(view):
            return False
        self._drop_designer(view)
        self.tabs.removeTab(index)
        if self.tabs.count() == 0:
            self.new_session()
        return True
```

Rewrite `closeEvent` and add the dock override:

```python
    def closeEvent(self, event) -> None:  # noqa: N802
        for view in self.views:
            if not self._confirm_close(view):
                event.ignore()
                return
        for view in self.views:
            view.teardown()
        super().closeEvent(event)

    def dockCloseEventTriggered(self) -> None:  # noqa: N802
        """Maya's workspace-control close, which cannot be vetoed.

        Returning early does not keep the control alive, so a cancel re-shows
        the window instead. The work survives; a flicker is possible.
        """
        for view in self.views:
            if not self._confirm_close(view):
                self.show_tool()
                return
        super().dockCloseEventTriggered()
```

Fix the untouched-tab sweep in `open_session` (currently `main.py:554-559`):

```python
        untouched = [
            other
            for other in self.views
            if other is not view
            and not other.session.is_modified
            and not other.session.file_path
        ]
```

Fix `import_actions` (`main.py:621`): `session._touch()` → `session.touch()`.

Update the two tests that monkeypatch the old name:
- `tests/ui/test_menus.py:224`: `monkeypatch.setattr(window, "ask_discard", lambda session: True)` → `monkeypatch.setattr(window, "ask_save_discard", lambda session: "discard")`
- `tests/ui/test_pipeline_ui.py:268`: `window.ask_discard = lambda session: True` → `window.ask_save_discard = lambda session: "discard"`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `... mayapy -m pytest tests/ui -q`

Expected: PASS — 185 from before plus 12 new.

- [ ] **Step 5: Format and commit**

```bash
python -m black src/python/tik/trigger/ui/main.py tests/ui
python -m isort src/python/tik/trigger/ui/main.py tests/ui
git add src/python/tik/trigger/ui/main.py tests/ui
git commit -m "feat(trigger): offer Save/Discard/Cancel when closing unsaved work"
```

---

### Task 3: The sweep

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py` (four `QFileDialog`, two `QMessageBox`)
- Modify: `src/python/tik/trigger/ui/settings_panel.py:194`
- Modify: `src/python/tik/trigger/ui/designer/commands.py:131,339,346`
- Modify: `src/python/tik/shared/ui/fields.py:251-268`
- Modify: `src/python/tik/shared/ui/versioned_field.py:207-224`

**Interfaces:**
- Consumes: the full `Feedback` surface from Task 1.
- Produces: nothing new. This is a behaviour-preserving substitution, guarded by the existing suite.

- [ ] **Step 1: Replace the file dialogs in `main.py`**

`open_session`:

```python
            path = Feedback(self).browse_open(
                "Open session", "", (EXTENSION,), FILE_FILTER
            )
```

`save_session_as`:

```python
            path = Feedback(self).browse_save(
                "Save session", "", (EXTENSION,), FILE_FILTER
            )
```

`import_actions`:

```python
            path = Feedback(self).browse_open(
                "Import actions", "", (EXTENSION,), FILE_FILTER
            )
```

`export_actions`:

```python
            path = Feedback(self).browse_save(
                "Export actions", "", (EXTENSION,), FILE_FILTER
            )
```

Each of these replaces a `path, _f = QtWidgets.QFileDialog.get...(...)` pair, so
delete the now-unused `_f` unpacking. `save_session` becomes:

```python
    def save_session(self) -> None:
        """Save the current session, asking for a path if it has none."""
        view = self.current_view
        if view is not None:
            self._save_view(view)
```

- [ ] **Step 2: Replace the message boxes in `main.py`**

```python
    def open_settings(self) -> None:
        """Placeholder until the settings dialog exists."""
        Feedback(self).pop_info("Settings", "Settings are not available yet.")

    def about(self) -> None:
        """Show the version box."""
        Feedback(self).pop_about(
            "About Trigger", f"Trigger {VERSION}\nModular rigging on tik.maya."
        )
```

- [ ] **Step 3: Replace the remaining call sites**

`settings_panel.py` — add `from tik.shared.ui.feedback import Feedback` and:

```python
        Feedback(self).pop_info(
            action_cls.display_label(),
            action_cls.description() or "No description.",
        )
```

`designer/commands.py` — add the import and:

```python
        text = Feedback(self).ask_text(
            "Connect input",
            f"{self._current.key}.<input> = <source>",
            f"{self._current.input_names()[0]} = ",
        )
        if text and "=" in text:
```

and in `_pick`:

```python
    def _pick(self, mode: str) -> str:
        if self.file_browser is not None:
            return (
                self.file_browser(mode, [GUIDE_EXTENSION], self.last_guide_file) or ""
            )
        dialog = Feedback(self)
        guide_filter = f"GuideLayout (*{GUIDE_EXTENSION})"
        if mode == "save":
            return dialog.browse_save(
                "Export guides", self.last_guide_file, (GUIDE_EXTENSION,), guide_filter
            )
        return dialog.browse_open(
            "Import guides", self.last_guide_file, (GUIDE_EXTENSION,), guide_filter
        )
```

`fields.py` `_browse`:

```python
    def _browse(self) -> None:
        if self.browser is not None:
            picked = self.browser(self.mode, self.extensions, self.value())
        else:
            dialog = Feedback(self)
            start = self.value()
            if self.mode == "dir":
                picked = dialog.browse_dir("Choose folder", start)
            elif self.mode == "save":
                picked = dialog.browse_save("Save", start, self.extensions)
            else:
                picked = dialog.browse_open("Open", start, self.extensions)
        if picked:
            self.line.setText(picked)
            self.valueChanged.emit(picked)
```

`_filter` in `fields.py` becomes unused — delete it; `Feedback._file_filter`
produces the same string.

`versioned_field.py` `_browse`:

```python
    def _browse(self) -> None:
        start = str(self.resolved() or "")
        if self.browser is not None:
            picked = self.browser(self.mode, self.extensions, start)
        else:
            dialog = Feedback(self)
            if self.mode == "dir":
                picked = dialog.browse_dir("Choose folder", start)
            elif self.mode == "save":
                picked = dialog.browse_save("Save", start, self.extensions)
            else:
                picked = dialog.browse_open("Open", start, self.extensions)
        if picked:
            self.line.setText(str(picked).replace("\\", "/"))
            self._commit()
```

`_filter` in `versioned_field.py` becomes unused — delete it too.

- [ ] **Step 4: Run the whole UI suite**

Run: `... mayapy -m pytest tests/ui -q`

Expected: PASS, 197.

- [ ] **Step 5: Format and commit**

```bash
python -m black src/python/tik tests
python -m isort src/python/tik tests
git add -A src/python/tik tests
git commit -m "refactor(ui): route every dialog through shared feedback"
```

---

### Task 4: The boundary rule

**Files:**
- Test: `tests/unit/test_dialog_boundaries.py` (create)

**Interfaces:**
- Consumes: nothing at runtime — it parses source with `ast`.
- Produces: the rule that keeps goal 3 true for tools that do not exist yet.

- [ ] **Step 1: Write the test**

Create `tests/unit/test_dialog_boundaries.py`:

```python
"""One dialog surface for the whole repo.

``shared/ui/feedback.py`` is where a tikworks tool asks the user something.
A raw ``QMessageBox`` anywhere else is how twelve dialogs ended up with
twelve different ideas about parenting, wording and cancellation -- and how
a headless test run ends up hanging on a modal nobody can click.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "python" / "tik"

DIALOGS = {"QMessageBox", "QFileDialog", "QInputDialog", "QErrorMessage"}

#: The surface itself, and vendored Qt.py which is not ours to police.
ALLOWED = {Path("shared/ui/feedback.py"), Path("vendor")}


def _is_allowed(py_file: Path) -> bool:
    relative = py_file.relative_to(SRC)
    return any(
        relative == allowed or allowed in relative.parents for allowed in ALLOWED
    )


def _dialog_names(py_file: Path):
    """Every ``QMessageBox``-style name the file actually references.

    Parsed rather than grepped so a mention in a docstring or a comment --
    like the one at the top of this file -- is not a violation.
    """
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in DIALOGS:
            yield node.attr
        elif isinstance(node, ast.Name) and node.id in DIALOGS:
            yield node.id


def test_dialogs_only_come_from_the_shared_feedback_module():
    violations = [
        f"{py_file.relative_to(SRC)} uses {name}"
        for py_file in SRC.rglob("*.py")
        if not _is_allowed(py_file)
        for name in sorted(set(_dialog_names(py_file)))
    ]
    assert violations == []
```

- [ ] **Step 2: Run it**

Run: `$env:PYTHONPATH="$PWD\src\python"; mayapy -m pytest tests/unit/test_dialog_boundaries.py -q`

Expected: PASS. If it fails it names the file and the class — move that call
site onto `Feedback` rather than widening `ALLOWED`.

- [ ] **Step 3: Run everything and lint**

```bash
mayapy -m pytest tests/unit -q
mayapy -m pytest tests/ui -q
python -m black --check src/python/tik tests
python -m isort --check-only src/python/tik tests
python -m flake8 src/python/tik tests
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_dialog_boundaries.py
git commit -m "test: keep every dialog behind the shared feedback module"
```

---

## Self-Review

**Spec coverage.** §3.1 → Task 1 Step 3. §3.2 (lazy parent) → Task 1, `_host`,
tested by `test_parent_falls_back_to_the_maya_main_window_lazily`. §3.3
(browser hook, per-widget wins) → Task 1 `set_browser` + Task 3's `_browse`
rewrites, which check `self.browser` first. §3.4 (handler) → Task 1
`set_handler`. §4.1 → Task 2 `ask_save_discard`. §4.2 → Task 2 `_confirm_close`
and `_save_view`, all five sub-points tested. §4.3 → Task 2's `close_tab`,
`closeEvent` and the `open_session` fix. §4.4 → Task 2
`dockCloseEventTriggered`. §4.5 → Task 2's `touch()` fix plus
`test_import_actions_records_an_undo_step`. §5 → Task 3. §6 → Tasks 1, 2, 4.

**Placeholders.** None: every step carries the code it asks for.

**Type consistency.** `ask_save_discard` returns the same three strings the
tests queue. `browse_open`/`browse_save`/`browse_dir` all return `str` (never
`None`), which is why the call sites test `if picked:` rather than `is not
None`. `ask_text` is the one that returns `Optional[str]`, and its single call
site tests `if text and "=" in text`. The injected `browser(mode, extensions,
current)` signature matches the existing `file_browser`/`browser` callables in
`fields.py`, `versioned_field.py` and `designer/commands.py` unchanged.
