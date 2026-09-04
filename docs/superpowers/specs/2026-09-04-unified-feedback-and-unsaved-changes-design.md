# Unified feedback and unsaved-changes guards

**Date:** 2026-09-04
**Status:** approved
**Ticket:** TW-13 — warn users when closing non-saved sessions

## 1. Problem

Two problems, one root.

**Closing loses work.** `TriggerWindow.ask_discard` asks *"Discard unsaved changes
in hero.tr?"* with Yes and No. There is no way to say *save it* — the rigger
either throws the work away or cancels and goes hunting for Ctrl+S. Worse, the
question is often never asked at all: `Session.is_modified` compares the
document against the last saved state, and a guide dragged in the viewport is
not in the document. `GuideScene._apply` says it outright — *nothing in Maya
fires when a guide is dragged* — so ten minutes of posing reads as a clean
session and closes without a word.

**Every dialog is bespoke.** `shared/ui/feedback.py` exists and nothing imports
it. Twelve call sites reach for `QMessageBox`, `QFileDialog` or `QInputDialog`
directly, each parenting, titling and captioning to its own taste. There is no
one place to fix a dialog's parenting under Maya, hand file picking to a
pipeline, or answer dialogs in a headless test run.

## 2. Goals

1. Closing a tab or the window with unsaved work offers **Save**, **Discard**
   and **Cancel**, and Cancel really cancels.
2. Guide poses in the scene count as unsaved work.
3. `shared/ui/feedback.py` is the one module the whole repo — tik.trigger today,
   any tool tomorrow — uses to ask the user something. No raw `QMessageBox`,
   `QFileDialog` or `QInputDialog` outside it.

Non-goals: a progress/busy reporter (no call site needs one yet); restyling
dialogs; touching `SnapshotDialog` or any other purpose-built dialog class.

## 3. `feedback.Feedback` — the dialog surface

The existing `Feedback(parent)` class stays the shape. Nothing imports it yet,
so it could have become module-level functions, but the class earns its keep:
one idiom (`Feedback(self).pop_question(...)`), one object to monkeypatch in a
test, and an obvious home for the parent.

### 3.1 What it gains

| Method | Replaces |
|---|---|
| `pop_warning(title, text, details)` | nothing — the missing middle between info and error |
| `pop_about(title, text)` | `QMessageBox.about` in `main.about` |
| `browse_open(caption, start, extensions)` | 4 `getOpenFileName` sites |
| `browse_save(caption, start, extensions)` | 3 `getSaveFileName` sites |
| `browse_dir(caption, start)` | 2 `getExistingDirectory` sites |
| `ask_text(title, label, text)` | `QInputDialog.getText` in `designer/commands` |

`pop_info`, `pop_error` and `pop_question` keep their signatures. `browse_directory`
stays as a deprecated one-line alias of `browse_dir` so nothing breaks.

### 3.2 Parent fallback

`Feedback(parent=None)` resolves its parent lazily through
`qtmaya.get_main_window()`. Resolution is lazy — at dialog time, not construction
time — so a `Feedback` built during import does not capture a main window that
does not exist yet. Outside Maya `get_main_window()` returns `None` and Qt
parents the dialog to the active window, which is the current behaviour.

### 3.3 The browser hook

`shared/ui/fields.py` and `shared/ui/versioned_field.py` already accept an
injected `browser(mode, extensions, current) -> str`, and
`designer/commands._pick` accepts a `file_browser` with the same shape. That is
the seam a pipeline uses to replace Qt's file dialog with its own asset browser,
and today each widget wires it separately.

`feedback.set_browser(fn)` lifts the same hook to module level. The `browse_*`
helpers consult it first; when it is unset they fall back to `QFileDialog`.
Per-widget injection stays and still wins over the module hook — a widget that
was handed a browser has been told something more specific than the default.

Mode strings stay `"open"`, `"save"`, `"dir"` to match the existing callables.

### 3.4 Test seam

`feedback.set_handler(fn)` intercepts message boxes: `fn(kind, title, text,
details, buttons) -> str | None` returns the button key to answer with, or
`None` to fall through to a real dialog. `kind` is one of `"info"`, `"error"`,
`"warning"`, `"question"`, `"about"`. Tests use it to answer dialogs without
monkeypatching Qt; it is the reason a headless run can never hang on a modal.

`set_browser` and `set_handler` both return the previous value, so a test can
restore it.

## 4. The close flow

### 4.1 The question

```python
TriggerWindow.ask_save_discard(session) -> "save" | "discard" | "cancel"
```

built on `pop_question(buttons=["save", "discard", "cancel"])`, worded
*"Save changes to `<name>` before closing?"*. It replaces `ask_discard`, which
is deleted rather than kept as an alias: two tests monkeypatch it and both get
updated, so a deprecated shim would only preserve a worse question.

### 4.2 The guard

```python
TriggerWindow._confirm_close(view) -> bool   # True = this tab may close
```

1. If `view is self._checked_out_view`, call `view.session.capture_guides()`
   first. Only the checked-out session's guides are in the scene; every other
   tab's document is already the truth, and capturing for them would read
   another session's joints.
2. `capture_guides` is wrapped: it touches Maya, and a scene error while closing
   must not trap the rigger in a window that will not shut. A failure is logged
   and the flow continues on `is_modified` alone.
3. Not modified → `True`, no dialog.
4. Ask. `"discard"` → `True`. `"cancel"` → `False`.
5. `"save"` → save the view's session; a session with no file path routes to
   Save As, and a cancelled Save As returns `False`. Saving is verified by
   re-reading `is_modified`, so a save that silently did nothing cannot be
   mistaken for a clean close.

### 4.3 Where it is used

- `close_tab(index)` guards the one tab.
- `closeEvent` walks the tabs in order and guards each; the first `False` calls
  `event.ignore()` and returns immediately. Tabs already saved stay saved —
  that is what Cancel means everywhere else, and pretending to roll a save back
  would be worse.
- `open_session` drops "untouched" tabs to keep the tab bar tidy, judged today
  by `not session.actions and not session.file_path`. A session holding guides
  but no actions passes that test and is destroyed without a word. The
  condition becomes `not session.is_modified and not session.file_path`.

### 4.4 Docked in Maya

The workspace control's ✕ calls `dockCloseEventTriggered`, and Maya does not
honour a veto there — returning early does not keep the control alive. The
mitigation is best-effort and honest about it: `TriggerWindow` overrides
`dockCloseEventTriggered`, runs the same guard, and on cancel re-shows itself
via `show_tool()` instead of tearing down. The work survives; a flicker is
possible. Undocked, and outside Maya, `closeEvent` vetoes cleanly.

### 4.5 A bug in the blast radius

`main.py:621` calls `session._touch()`. `Session` defines `touch()`; `_touch` is
`GuideScene`'s. `Import Actions…` therefore raises `AttributeError` after
mutating the document — the actions are added, the undo step is not recorded,
and the user sees a traceback. Fixed to `session.touch()` with a regression test,
because it is precisely a dirty-tracking failure and belongs to this change.

## 5. The sweep

Moved to `Feedback`: `main.open_settings`, `main.about`, `main.open_session`,
`main.save_session_as`, `main.import_actions`, `main.export_actions`,
`settings_panel._show_info`, `designer/commands.connect_dialog`,
`designer/commands._pick`, `fields._browse`, `versioned_field._browse`.

`tik/vendor/` is exempt — it is vendored Qt.py, not ours.

## 6. Testing

- `tests/ui/test_feedback.py` — button-key round-trip including `discard`,
  the `set_handler` seam, `set_browser` precedence over the Qt fallback,
  per-widget injection beating the module hook, lazy parent resolution.
- `tests/ui/test_unsaved_changes.py` — a clean tab closes silently; Save,
  Discard and Cancel each do what they say; Cancel aborts a multi-tab
  `closeEvent` and leaves earlier saves in place; Save with no path routes to
  Save As and a cancelled Save As blocks the close; captured guide drift turns
  a clean session dirty; a `capture_guides` that raises does not trap the
  window; `open_session` no longer drops a modified untitled tab.
- `tests/unit/test_dialog_boundaries.py` — in the style of
  `test_import_boundaries.py`: no `QMessageBox`, `QFileDialog` or `QInputDialog`
  outside `shared/ui/feedback.py` and `vendor/`. This is the rule that keeps
  goal 3 true for tools that do not exist yet.
- Updated: `test_menus.py:224` and `test_pipeline_ui.py:268` move from
  `ask_discard` to `ask_save_discard`.

## 7. Files

`shared/ui/feedback.py`, `shared/ui/fields.py`, `shared/ui/versioned_field.py`,
`trigger/ui/main.py`, `trigger/ui/settings_panel.py`,
`trigger/ui/designer/commands.py`, plus the tests above.
