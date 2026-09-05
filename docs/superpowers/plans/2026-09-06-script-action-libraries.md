# Script Action Libraries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the `script` action into a library loader: a file becomes a named module riggers call from later actions, with a two-tier lifetime, external editing, versioned stubs, and a read-only viewer dock.

**Architecture:** A `ScriptSpace` owned by the Maya runner holds one `trigger_build` module per run; script actions load files into it with `importlib` under an alias and exec inline code in its globals. The UI gains a `TextField` widget, a `.py` file field with pencil and `New Script…`, and a `QDockWidget` viewer that follows the selected action.

**Tech Stack:** Python 3.10, Maya 2024 `mayapy` for unit/integration tests, PySide (via `tik.shared.ui.Qt`) for UI tests run offscreen.

**Spec:** `docs/superpowers/specs/2026-09-06-script-action-libraries-design.md`

## Global Constraints

- `tik/trigger/core` stays pure Python: no Maya, no Qt (`tests/unit/test_import_boundaries.py`).
- `tik.shared` never imports `tik.trigger`.
- Every dialog goes through `tik.shared.ui.feedback.Feedback` (`tests/unit/test_dialog_boundaries.py`).
- No third-party dependencies. stdlib and Maya-bundled only.
- The new field is named `lifetime`, never `scope` (`scope` is action-list placement).
- Trigger writes a `.py` file in exactly one place: `New Script…`.
- Style: black, isort (profile black), flake8. Run `make lint` before each commit.
- Test commands (from repo root, PowerShell):
  - unit/integration under mayapy: `make tests-unit` / `make tests-integration`. For a single file, read the `MAYAPY` value at the top of the Makefile and run `<mayapy> -m pytest <file> -q` from the repo root (`PYTHONPATH` set as the Makefile's `SET_PYTHONPATH` does).
  - UI: `make tests-ui` (sets `TIK_TESTS_NO_MAYA=1` and `QT_QPA_PLATFORM=offscreen`). A single UI file: `$env:TIK_TESTS_NO_MAYA=1; $env:QT_QPA_PLATFORM="offscreen"; <mayapy> -m pytest tests/ui/<file> -q`.
- Commit messages end with the trailer block used on this branch:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_017gXwnrR9tFeTx3BYzjUhBV
  ```

---

## File map

| File | Responsibility |
|---|---|
| `src/python/tik/core/fields.py` | add `TextField` |
| `src/python/tik/trigger/core/__init__.py` | re-export `TextField` |
| `src/python/tik/shared/ui/fields.py` | `_TextEditor` widget, `text` kind, full-row placement |
| `src/python/tik/trigger/maya/scripts.py` (new) | `ScriptSpace` |
| `src/python/tik/trigger/core/action.py` | `ActionContext.scripts`, `Action.migrate_settings` |
| `src/python/tik/trigger/core/document.py` | call `migrate_settings` in `ActionNode.from_dict` |
| `src/python/tik/trigger/maya/runner.py` | create the space per run, `add_path` per step |
| `src/python/tik/trigger/actions/script/script.py` | the action |
| `src/python/tik/trigger/actions/script/stub.py.tmpl` (new) | the `New Script…` template |
| `src/python/tik/shared/io.py` | `open_external(path, command="")` |
| `src/python/tik/trigger/config/defaults.py`, `defaults.json` | `external_editor` key |
| `src/python/tik/trigger/ui/settings_panel.py` | `.py` pencil, `New Script…`, `handle_changed` |
| `src/python/tik/trigger/ui/session_view.py` | route `.py` opens, re-emit `handle_changed` |
| `src/python/tik/trigger/ui/script_dock.py` (new) | the viewer |
| `src/python/tik/trigger/ui/main.py` | dock, menu toggle, selection following |

---

### Task 1: `TextField`

**Files:**
- Modify: `src/python/tik/core/fields.py` (after `StringField`, ~line 190)
- Modify: `src/python/tik/trigger/core/__init__.py` (the `tik.core.fields` import list)
- Test: `tests/unit/test_fields.py`

**Interfaces:**
- Produces: `TextField(default="", *, language="", **kwargs)` with `type_name = "text"`, attribute `language`; `to_schema()` includes `"language"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_fields.py`:

```python
def test_text_field_normalises_line_breaks_and_none():
    from tik.core.fields import TextField

    class Note(Schema):
        body = TextField("", language="python")

    note = Note()
    note.body = "a\r\nb\rc"
    assert note.body == "a\nb\nc"
    note.body = None
    assert note.body == ""
    with pytest.raises(FieldValidationError):
        note.body = 3
    schema = Note.schema()["body"]
    assert schema["type"] == "text" and schema["language"] == "python"


def test_text_field_is_exported_by_trigger_core():
    from tik.trigger.core import TextField as exported
    from tik.core.fields import TextField

    assert exported is TextField
```

- [ ] **Step 2: Run to verify they fail**

Run: `<mayapy> -m pytest tests/unit/test_fields.py -q -k text_field`
Expected: FAIL with `ImportError: cannot import name 'TextField'`.

- [ ] **Step 3: Implement**

In `src/python/tik/core/fields.py`, after `StringField`:

```python
class TextField(Field):
    """Multi-line text, stored as one string with ``\\n`` line breaks.

    ``language`` is advisory for editors: ``"python"`` asks for a monospace
    font and space-inserting Tab; anything else renders as plain text.
    """

    type_name = "text"

    def __init__(self, default: str = "", *, language: str = "", **kwargs) -> None:
        self.language = language
        super().__init__(default, **kwargs)

    def coerce(self, value):
        """Accept strings (``None`` becomes ``""``); normalise line breaks."""
        if value is None:
            return ""
        if not isinstance(value, str):
            raise FieldValidationError(self.name, value, "must be a string")
        return value.replace("\r\n", "\n").replace("\r", "\n")

    def to_schema(self) -> dict:
        """The base schema plus ``language``."""
        data = super().to_schema()
        data["language"] = self.language
        return data
```

In `src/python/tik/trigger/core/__init__.py`, add `TextField,` to the `from tik.core.fields import (...)` list (alphabetical, after `StringField`), and to `__all__` if the file has one (check with `grep -n __all__`).

- [ ] **Step 4: Run to verify they pass**

Run: `<mayapy> -m pytest tests/unit/test_fields.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/core/fields.py src/python/tik/trigger/core/__init__.py tests/unit/test_fields.py
git commit -m "TW-16: TextField for multi-line settings"
```

---

### Task 2: The text editor widget in `FormBuilder`

**Files:**
- Modify: `src/python/tik/shared/ui/fields.py` (new `_TextEditor` class before `FormBuilder`; `_make_widget` gains a `text` branch; `set_target` places text fields full-row)
- Test: `tests/ui/test_form_builder.py`

**Interfaces:**
- Consumes: `TextField` from Task 1.
- Produces: `_TextEditor(language="", parent=None)` with `valueChanged(object)`, `value() -> str`, `setValue(str)`, commits on focus-out and Ctrl+Return. `FormBuilder.widget("code")` returns it. `FormBuilder._set_widget_value` already handles widgets with `setValue`, check it does (line ~572) and add a branch if it keys on type.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_form_builder.py`:

```python
def test_text_field_renders_full_row_and_commits_on_focus_out(qapp):
    from tik.core.fields import TextField
    from tik.shared.ui.fields import _TextEditor

    class Snippet(Schema):
        title = StringField("x")
        code = TextField("print(1)", language="python")

    form = FormBuilder(Snippet())
    editor = form.widget("code")
    assert isinstance(editor, _TextEditor)
    assert editor.value() == "print(1)"
    assert editor.edit.font().fixedPitch() or "Mono" in editor.edit.font().family() \
        or editor.edit.font().styleHint() == editor.edit.font().Monospace
    seen = []
    form.changed.connect(lambda name, value: seen.append((name, value)))
    editor.edit.setPlainText("a = 1\nb = 2")
    editor.commit()
    assert seen == [("code", "a = 1\nb = 2")]
    assert form.target.code == "a = 1\nb = 2"
    # full row: the label sits above the editor, not beside it, so the form
    # layout holds the editor as a spanning row
    row, role = form._plain.getWidgetPosition(editor)
    assert role == QtWidgets.QFormLayout.SpanningRole
```

- [ ] **Step 2: Run to verify it fails**

Run: `$env:TIK_TESTS_NO_MAYA=1; $env:QT_QPA_PLATFORM="offscreen"; <mayapy> -m pytest tests/ui/test_form_builder.py -q -k text_field`
Expected: FAIL with `ImportError: cannot import name '_TextEditor'`.

- [ ] **Step 3: Implement the widget**

In `src/python/tik/shared/ui/fields.py`, before `class FormBuilder`, add:

```python
class _TextEditor(QtWidgets.QWidget):
    """Multi-line editor: commits on focus-out and Ctrl+Return, not per key."""

    valueChanged = QtCore.Signal(object)
    MIN_LINES = 6
    MAX_LINES = 20

    def __init__(self, language: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QtWidgets.QPlainTextEdit()
        self.edit.setObjectName("TextFieldEditor")
        self.language = language
        if language == "python":
            font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
            self.edit.setFont(font)
            self.edit.setTabStopDistance(
                4 * QtGui.QFontMetricsF(font).horizontalAdvance(" ")
            )
        layout.addWidget(self.edit)
        self._committed = ""
        self.edit.installEventFilter(self)
        self.edit.textChanged.connect(self._fit_height)
        self._fit_height()

    def _fit_height(self) -> None:
        metrics = QtGui.QFontMetrics(self.edit.font())
        lines = max(self.MIN_LINES, min(self.MAX_LINES, self.edit.blockCount()))
        frame = 2 * self.edit.frameWidth() + 8
        self.edit.setFixedHeight(lines * metrics.lineSpacing() + frame)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt style
        if obj is self.edit:
            if event.type() == QtCore.QEvent.FocusOut:
                self.commit()
            elif event.type() == QtCore.QEvent.KeyPress:
                key, mods = event.key(), event.modifiers()
                if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and (
                    mods & QtCore.Qt.ControlModifier
                ):
                    self.commit()
                    return True
                if key == QtCore.Qt.Key_Tab and self.language == "python":
                    self.edit.insertPlainText("    ")
                    return True
        return super().eventFilter(obj, event)

    def commit(self) -> None:
        """Emit the text if it changed since the last commit."""
        text = self.value()
        if text != self._committed:
            self._committed = text
            self.valueChanged.emit(text)

    def value(self) -> str:
        return self.edit.toPlainText()

    def setValue(self, value) -> None:  # noqa: N802
        text = str(value or "")
        self._committed = text
        self.edit.setPlainText(text)
```

Make sure `QtGui` is imported at the top of the file: `from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets`.

- [ ] **Step 4: Wire the kind and the full-row placement**

In `FormBuilder._make_widget`, before the `else:` fallback, add:

```python
        elif kind == "text":
            widget = _TextEditor(getattr(field, "language", ""))
            widget.valueChanged.connect(
                lambda value, field_name=name: self._on_change(field_name, value)
            )
```

In `FormBuilder.set_target`, replace the loop body `form.addRow(label, widget)` with:

```python
                if field.type_name == "text":
                    form.addRow(label)
                    form.addRow(widget)
                else:
                    form.addRow(label, widget)
```

Check `_set_widget_value` (around line 572): if it dispatches on `isinstance(widget, QtWidgets.QLineEdit)` and so on, add `elif hasattr(widget, "setValue"): widget.setValue(value)` is already the fallback used by `_VectorEditor` and friends. Confirm by reading the function; only add a branch if `_TextEditor` would fall through to a `setText` call.

- [ ] **Step 5: Run to verify it passes**

Run: `$env:TIK_TESTS_NO_MAYA=1; $env:QT_QPA_PLATFORM="offscreen"; <mayapy> -m pytest tests/ui/test_form_builder.py -q`
Expected: all PASS. If the font assertion is flaky offscreen, keep only the `fixedPitch()` check via `QtGui.QFontInfo(editor.edit.font()).fixedPitch()`.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/shared/ui/fields.py tests/ui/test_form_builder.py
git commit -m "TW-16: multi-line text editor for TextField in FormBuilder"
```

---

### Task 3: `ScriptSpace`

**Files:**
- Create: `src/python/tik/trigger/maya/scripts.py`
- Test: `tests/unit/test_script_space_trigger.py` (new; pure Python, no Maya calls, runs under mayapy like the rest)

**Interfaces:**
- Produces:
  ```python
  class ScriptError(Exception)
  class ScriptSpace:
      name = "trigger_build"
      module: ModuleType | None
      aliases: set[str]          # loaded this run
      def __enter__(self) -> "ScriptSpace"
      def __exit__(self, *exc) -> None
      def add_path(self, scripts_dir) -> None
      def load(self, path, alias: str) -> ModuleType
      def globals(self, ctx) -> dict
      def keep(self, alias: str) -> None
      def is_reserved(self, alias: str) -> bool
      def hint_for(self, error: ImportError) -> str
  ```

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_script_space_trigger.py`:

```python
"""ScriptSpace: the per-run module namespace script actions share."""

import sys
from pathlib import Path

import pytest

from tik.trigger.maya.scripts import ScriptError, ScriptSpace


@pytest.fixture(autouse=True)
def _clean_modules():
    before = set(sys.modules)
    before_path = list(sys.path)
    yield
    for name in set(sys.modules) - before:
        if name.startswith(("gen_rig", "cfx_utils", "hero", "trigger_build", "keep")):
            sys.modules.pop(name, None)
    sys.path[:] = before_path


def _write(folder: Path, name: str, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return path


def test_enter_registers_the_build_module_and_exit_drops_it():
    with ScriptSpace() as space:
        assert sys.modules["trigger_build"] is space.module
    assert "trigger_build" not in sys.modules


def test_load_registers_an_alias_and_files_can_import_each_other(tmp_path):
    scripts = tmp_path / "scripts"
    gen = _write(scripts, "general_rig_utils_v001.py", "def hello():\n    return 'gen'\n")
    cfx = _write(
        scripts,
        "cfx_utils_v001.py",
        "import gen_rig\n\ndef hello():\n    return 'cfx+' + gen_rig.hello()\n",
    )
    with ScriptSpace() as space:
        space.add_path(scripts)
        space.load(gen, "gen_rig")
        space.load(cfx, "cfx_utils")
        assert sys.modules["gen_rig"].__name__ == "gen_rig"
        assert sys.modules["cfx_utils"].hello() == "cfx+gen"
        namespace = space.globals(ctx="CTX")
        assert namespace["cfx_utils"] is sys.modules["cfx_utils"]
        assert namespace["ctx"] == "CTX"
        assert namespace["__name__"] == "trigger_build"
        assert str(scripts) in sys.path
    assert "gen_rig" not in sys.modules and "cfx_utils" not in sys.modules
    assert str(scripts) not in sys.path


def test_a_failing_file_is_unregistered(tmp_path):
    bad = _write(tmp_path, "hero_v001.py", "raise RuntimeError('boom')\n")
    with ScriptSpace() as space:
        with pytest.raises(RuntimeError):
            space.load(bad, "hero")
        assert "hero" not in sys.modules
        assert "hero" not in space.aliases


def test_kept_aliases_survive_and_the_next_run_replaces_them(tmp_path):
    first = _write(tmp_path / "a", "keep_me_v001.py", "VALUE = 1\n")
    second = _write(tmp_path / "b", "keep_me_v002.py", "VALUE = 2\n")
    with ScriptSpace() as space:
        space.add_path(first.parent)
        space.load(first, "keep_me")
        space.keep("keep_me")
    assert sys.modules["keep_me"].VALUE == 1
    assert sys.modules["trigger_build"].keep_me.VALUE == 1
    assert sys.modules["trigger_build"].ctx is None
    assert str(first.parent) in sys.path
    with ScriptSpace() as space:
        assert "keep_me" not in sys.modules  # torn down on enter
        assert str(first.parent) not in sys.path
        space.load(second, "keep_me")
    # not kept this time: gone after the run
    assert "keep_me" not in sys.modules
    assert "trigger_build" not in sys.modules


def test_reserved_names_are_refused():
    with ScriptSpace() as space:
        assert space.is_reserved("sys")
        assert not space.is_reserved("gen_rig")
        with pytest.raises(ScriptError):
            space.load(Path("whatever.py"), "sys")


def test_import_error_hint_names_the_missing_alias(tmp_path):
    scripts = tmp_path / "scripts"
    cfx = _write(scripts, "cfx_utils_v001.py", "import gen_rig\n")
    with ScriptSpace() as space:
        space.add_path(scripts)
        with pytest.raises(ImportError) as info:
            space.load(cfx, "cfx_utils")
        hint = space.hint_for(info.value)
        assert "gen_rig is not loaded yet" in hint
        # a name that does exist on disk gets no hint: it is a real import error
        _write(scripts, "gen_rig_v001.py", "import nothing_here\n")
        with pytest.raises(ImportError) as info:
            space.load(cfx, "cfx_utils")
        assert space.hint_for(info.value) == ""
```

- [ ] **Step 2: Run to verify they fail**

Run: `<mayapy> -m pytest tests/unit/test_script_space_trigger.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tik.trigger.maya.scripts'`.

- [ ] **Step 3: Implement**

Create `src/python/tik/trigger/maya/scripts.py`:

```python
"""The per-run module namespace that script actions share.

``trigger_build`` is a real module registered in ``sys.modules`` for the
duration of a run. Script files are loaded into it under an alias with
``importlib``; inline code execs in its globals. This touches ``sys.modules``
and ``sys.path`` -- process state, not Maya state -- and sits in the Maya
layer because the runner is its only client.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Optional


class ScriptError(Exception):
    """A script file or alias cannot be loaded."""


class ScriptSpace:
    """The modules and globals script actions share for one run.

    Enter it around a run. ``build``-lifetime aliases vanish on exit;
    ``keep`` marks an alias as ``maya``-lifetime, which leaves it and the
    ``trigger_build`` module importable until the next run tears them down
    on enter. Last run wins.
    """

    name = "trigger_build"

    def __init__(self) -> None:
        self.module: Optional[types.ModuleType] = None
        self.aliases: set[str] = set()
        self._paths: list[str] = []
        self._kept: set[str] = set()

    # ------------------------------------------------------------ lifetime
    def __enter__(self) -> "ScriptSpace":
        self._teardown_previous()
        self.module = types.ModuleType(self.name)
        self.module.ctx = None
        self.module._trigger_aliases = ()
        self.module._trigger_paths = ()
        sys.modules[self.name] = self.module
        return self

    def __exit__(self, *_exc) -> None:
        module = self.module
        if module is None:
            return
        module.ctx = None
        for alias in sorted(self.aliases - self._kept):
            sys.modules.pop(alias, None)
            module.__dict__.pop(alias, None)
        if self._kept:
            module._trigger_aliases = tuple(sorted(self._kept))
            module._trigger_paths = tuple(self._paths)
        else:
            for entry in self._paths:
                _remove_path(entry)
            sys.modules.pop(self.name, None)
        self.module = None

    @classmethod
    def _teardown_previous(cls) -> None:
        previous = sys.modules.pop(cls.name, None)
        if previous is None:
            return
        for alias in getattr(previous, "_trigger_aliases", ()):
            sys.modules.pop(alias, None)
        for entry in getattr(previous, "_trigger_paths", ()):
            _remove_path(entry)

    # ---------------------------------------------------------------- paths
    def add_path(self, scripts_dir) -> None:
        """Put ``scripts_dir`` first on ``sys.path`` for the run, once."""
        folder = Path(scripts_dir)
        if not folder.is_dir():
            return
        entry = str(folder)
        if entry in self._paths:
            return
        self._paths.append(entry)
        if entry not in sys.path:
            sys.path.insert(0, entry)

    # -------------------------------------------------------------- loading
    def is_reserved(self, alias: str) -> bool:
        """True when ``alias`` names a module Trigger did not load."""
        return alias in sys.modules and alias not in self.aliases

    def load(self, path, alias: str) -> types.ModuleType:
        """Execute ``path`` as module ``alias`` and register it."""
        if self.module is None:
            raise ScriptError("ScriptSpace is not entered.")
        if self.is_reserved(alias):
            raise ScriptError(
                f"'{alias}' is already a module in this Maya; pick another Import As."
            )
        path = Path(path)
        spec = importlib.util.spec_from_file_location(alias, str(path))
        if spec is None or spec.loader is None:
            raise ScriptError(f"Cannot load {path} as a module.")
        module = importlib.util.module_from_spec(spec)
        sys.modules.pop(alias, None)  # a previous load this run: reload fresh
        sys.modules[alias] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(alias, None)
            self.module.__dict__.pop(alias, None)
            self.aliases.discard(alias)
            raise
        self.aliases.add(alias)
        setattr(self.module, alias, module)
        return module

    def globals(self, ctx: Any) -> dict:
        """The exec namespace for inline code: aliases, ``ctx``, ``__name__``."""
        if self.module is None:
            raise ScriptError("ScriptSpace is not entered.")
        self.module.ctx = ctx
        return self.module.__dict__

    def keep(self, alias: str) -> None:
        """Mark ``alias`` as ``maya``-lifetime."""
        if alias in self.aliases:
            self._kept.add(alias)

    def hint_for(self, error: ImportError) -> str:
        """An ordering hint when an alias is missing, else ``""``."""
        name = getattr(error, "name", None)
        if not name or name in sys.modules:
            return ""
        top = name.split(".")[0]
        for entry in self._paths:
            if any(Path(entry).glob(f"{top}*.py")):
                return ""
        return (
            f"{top} is not loaded yet; a script action that loads it must run "
            "before this one."
        )


def _remove_path(entry: str) -> None:
    while entry in sys.path:
        sys.path.remove(entry)
```

- [ ] **Step 4: Run to verify they pass**

Run: `<mayapy> -m pytest tests/unit/test_script_space_trigger.py tests/unit/test_import_boundaries.py -q`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/maya/scripts.py tests/unit/test_script_space_trigger.py
git commit -m "TW-16: ScriptSpace, the per-run module namespace for script actions"
```

---

### Task 4: The runner owns a `ScriptSpace` per run

**Files:**
- Modify: `src/python/tik/trigger/core/action.py` (`ActionContext` gains `scripts`)
- Modify: `src/python/tik/trigger/maya/runner.py` (`run` and `_run_step`)
- Test: `tests/unit/test_runner_trigger.py`

**Interfaces:**
- Consumes: `ScriptSpace` from Task 3.
- Produces: `ActionContext.scripts` (the entered `ScriptSpace` during a run, `None` otherwise). `Runner._run_step(step, session, space)` signature.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_runner_trigger.py` (the file already imports `Document`, `ActionNode`, `Runner`, `register_action`; the `Mark` toy action lives in `tests/helpers/toy_modules.py` or at the top of the file, reuse whatever the file already registers):

```python
def test_the_runner_enters_one_script_space_per_run_and_tears_it_down():
    import sys

    from tik.trigger.core import Action

    seen = []

    class Peek(Action):
        def run(self, ctx):
            seen.append((ctx.scripts, "trigger_build" in sys.modules))
            ctx.scripts.add_path(ctx.base_dir + "/scripts")

    register_action("peek", category="build")(Peek)
    doc = Document()
    doc.add(ActionNode("a", "peek"))
    doc.add(ActionNode("b", "peek"))
    Runner().run(doc, "D:/nowhere")
    assert len(seen) == 2
    assert seen[0][0] is seen[1][0]  # one space for the run
    assert seen[0][1] and seen[1][1]
    assert "trigger_build" not in sys.modules
```

If the file has a fixture that clears the registries between tests (look for `clear_registries` near the top), the local `register_action` call above is enough; otherwise wrap it in `try/finally: unregister_action("peek")`.

- [ ] **Step 2: Run to verify it fails**

Run: `<mayapy> -m pytest tests/unit/test_runner_trigger.py -q -k script_space`
Expected: FAIL with `AttributeError: 'NoneType' object has no attribute 'add_path'` (or `ActionContext` has no `scripts`).

- [ ] **Step 3: Add `scripts` to `ActionContext`**

In `src/python/tik/trigger/core/action.py`, after the `rig` field:

```python
    scripts: Any = None  # the run's ScriptSpace, set by the Maya runner; core never reads it
```

- [ ] **Step 4: Enter the space in `Runner.run` and hand it to each step**

In `src/python/tik/trigger/maya/runner.py`, add the import near the top: `from .scripts import ScriptSpace`. Replace the tail of `run()` from `results: list[StepResult] = []` onward with:

```python
        results: list[StepResult] = []
        total = len(steps)
        with ScriptSpace() as space:
            for number, step in enumerate(steps, start=1):
                self.events.progress(number, total, step.path)
                results.append(self._run_step(step, session, space))
        return results
```

Change `_run_step` to `def _run_step(self, step: Step, session, space) -> StepResult:` and, right after `ctx = ActionContext(...)` is built, add:

```python
        ctx.scripts = space
        space.add_path(Path(step.base_dir) / "scripts")
```

with `from pathlib import Path` at the top. `add_path` is a no-op when the folder does not exist, so a session without scripts costs nothing.

- [ ] **Step 5: Run the runner tests**

Run: `<mayapy> -m pytest tests/unit/test_runner_trigger.py -q`
Expected: all PASS, including the existing `test_a_script_can_extend_the_preferences_control` (the action still uses `code`, and Task 5 keeps that field).

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/core/action.py src/python/tik/trigger/maya/runner.py tests/unit/test_runner_trigger.py
git commit -m "TW-16: the runner enters one ScriptSpace per run"
```

---

### Task 5: The `script` action

**Files:**
- Modify: `src/python/tik/trigger/actions/script/script.py` (rewrite)
- Test: `tests/unit/test_runner_trigger.py` (Maya; the three-module pipeline, lifetime, reference folder)

**Interfaces:**
- Consumes: `TextField` (Task 1), `ScriptSpace` and `ScriptError` (Task 3), `ActionContext.scripts` (Task 4).
- Produces: `Script` fields `file_path`, `import_as`, `code`, `lifetime`; `Script.alias()`; `Script.validate(ctx)`; `Script.run(ctx)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_runner_trigger.py`:

```python
def _script_session(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "general_rig_utils_v001.py").write_text(
        "def tag():\n    return 'gen'\n", encoding="utf-8"
    )
    (scripts / "cfx_utils_v001.py").write_text(
        "import gen_rig\n\ndef tag():\n    return 'cfx+' + gen_rig.tag()\n",
        encoding="utf-8",
    )
    (scripts / "hero_build_v001.py").write_text(
        "import cfx_utils\n\n"
        "def finalize(ctx):\n"
        "    from maya import cmds\n"
        "    cmds.createNode('transform', name='mark_' + cfx_utils.tag().replace('+', '_'))\n",
        encoding="utf-8",
    )
    return tmp_path


def test_script_actions_load_libraries_that_call_each_other(tmp_path):
    import sys

    from maya import cmds

    from tik.trigger.actions.script.script import Script

    register_action("script", category="structure", scope="both")(Script)
    base = _script_session(tmp_path)
    doc = Document()
    doc.add(ActionNode("gen", "script", settings={
        "file_path": "scripts/general_rig_utils_v001.py", "import_as": "gen_rig"}))
    doc.add(ActionNode("cfx", "script", settings={
        "file_path": "scripts/cfx_utils_v001.py"}))
    doc.add(ActionNode("hero", "script", settings={
        "file_path": "scripts/hero_build_v001.py"}))
    doc.add(ActionNode("finalize", "script", settings={
        "code": "hero_build.finalize(ctx)"}))
    Runner().run(doc, str(base))
    assert cmds.objExists("mark_cfx_gen")
    # build lifetime: nothing survives the run
    assert not {"gen_rig", "cfx_utils", "hero_build", "trigger_build"} & set(sys.modules)
    assert str(base / "scripts") not in sys.path


def test_maya_lifetime_keeps_the_module_until_the_next_run(tmp_path):
    import sys

    from tik.trigger.actions.script.script import Script

    register_action("script", category="structure", scope="both")(Script)
    base = _script_session(tmp_path)
    doc = Document()
    doc.add(ActionNode("gen", "script", settings={
        "file_path": "scripts/general_rig_utils_v001.py",
        "import_as": "gen_rig", "lifetime": "maya"}))
    Runner().run(doc, str(base))
    import trigger_build  # noqa: E402 - the point of the test

    assert trigger_build.gen_rig.tag() == "gen"
    assert trigger_build.ctx is None
    assert sys.modules["gen_rig"] is trigger_build.gen_rig
    # a second run with build lifetime replaces and then drops it
    doc.find("gen").settings["lifetime"] = "build"
    Runner().run(doc, str(base))
    assert "gen_rig" not in sys.modules and "trigger_build" not in sys.modules


def test_a_missing_alias_fails_with_an_ordering_hint(tmp_path):
    from tik.trigger.actions.script.script import Script
    from tik.trigger.core.exceptions import ActionExecutionError

    register_action("script", category="structure", scope="both")(Script)
    base = _script_session(tmp_path)
    doc = Document()
    doc.add(ActionNode("cfx", "script", settings={
        "file_path": "scripts/cfx_utils_v001.py"}))
    with pytest.raises(ActionExecutionError) as info:
        Runner().run(doc, str(base))
    assert "gen_rig is not loaded yet" in str(info.value)


def test_script_validation_rejects_bad_aliases_and_missing_files(tmp_path):
    from tik.trigger.actions.script.script import Script
    from tik.trigger.core.action import ActionContext

    ctx = ActionContext(base_dir=str(tmp_path))
    assert "file not found" in Script({"file_path": "nope.py"}).validate(ctx)[0]
    (tmp_path / "x.py").write_text("", encoding="utf-8")
    bad = Script({"file_path": "x.py", "import_as": "my alias"}).validate(ctx)
    assert "not a valid module name" in bad[0]
    assert Script({"file_path": "x.py", "import_as": "sys"}).validate(ctx)
    assert Script({"file_path": "x.py"}).validate(ctx) == []
    assert Script({}).validate(ctx) == []
    assert Script({"file_path": "scripts/hero_build_v001.py"}).alias() == "hero_build"
    assert Script({"file_path": "a_v002.py", "import_as": "b"}).summary() == "a_v002.py as b"


def test_a_referenced_session_loads_scripts_from_its_own_folder(tmp_path):
    from maya import cmds

    from tik.trigger.actions.reference.reference import Reference
    from tik.trigger.actions.script.script import Script

    register_action("script", category="structure", scope="both")(Script)
    register_action("reference", category="structure")(Reference)
    ref_dir = tmp_path / "base"
    (ref_dir / "scripts").mkdir(parents=True)
    (ref_dir / "scripts" / "base_lib_v001.py").write_text(
        "def mark():\n    from maya import cmds\n    cmds.createNode('transform', name='from_ref')\n",
        encoding="utf-8",
    )
    base = Document()
    base.add(ActionNode("lib", "script", settings={"file_path": "scripts/base_lib_v001.py"}))
    base.add(ActionNode("call", "script", settings={"code": "base_lib.mark()"}))
    base.save(ref_dir / "base_v001.tr")
    hero_dir = tmp_path / "hero"
    hero_dir.mkdir()
    hero = Document()
    hero.add(ActionNode("base", "reference", settings={"file_path": "../base/base_v001.tr"}))
    Runner().run(hero, str(hero_dir))
    assert cmds.objExists("from_ref")
```

Check the `Reference` settings key by reading `src/python/tik/trigger/actions/reference/reference.py` (`grep -n "FileField" `); use the name it declares.

- [ ] **Step 2: Run to verify they fail**

Run: `<mayapy> -m pytest tests/unit/test_runner_trigger.py -q -k "script or alias or referenced"`
Expected: FAIL (`AttributeError: 'Script' object has no attribute 'alias'`, unknown field errors).

- [ ] **Step 3: Rewrite the action**

Replace `src/python/tik/trigger/actions/script/script.py` with:

```python
"""Load a Python file as a named module, then run inline code.

A script file is a library: it is executed as a real module under an alias
(``import_as``, default the file stem) and registered in ``sys.modules``, so
later files can ``import`` it and later actions call into it. Inline code runs
in the shared ``trigger_build`` namespace where every alias loaded so far is a
global, next to ``ctx``. Pipeline order is the dependency order.
"""

from __future__ import annotations

import keyword
from pathlib import Path

from tik.trigger.core import (
    Action,
    ChoiceField,
    FileField,
    StringField,
    TextField,
    register_action,
    versioning,
)
from tik.trigger.core.action import ActionContext
from tik.trigger.core.exceptions import ActionExecutionError

BUILD_LIFETIME = "build"
MAYA_LIFETIME = "maya"


@register_action("script", category="structure", icon="script", scope="both")
class Script(Action):
    """Load a Python file as a named module, then run inline code.

    Either half is optional. Files loaded earlier in the pipeline are
    importable by alias; inline code sees them as globals next to ``ctx``.
    With ``lifetime`` ``maya`` the module stays importable from the Script
    Editor (``import trigger_build``) until the next run replaces it.
    """

    label = "Script"

    file_path = FileField("", extensions=[".py"], label="Script File")
    import_as = StringField(
        "", label="Import As", help="Module name for the file; defaults to its stem"
    )
    code = TextField(
        "",
        label="Code",
        language="python",
        help="Runs after the file, with every loaded module and ctx in scope",
    )
    lifetime = ChoiceField(
        BUILD_LIFETIME,
        choices=[BUILD_LIFETIME, MAYA_LIFETIME],
        help="build: names vanish when the run ends. "
        "maya: they stay importable until the next run (last run wins)",
    )

    # ------------------------------------------------------------ helpers
    def alias(self) -> str:
        """The module name the file loads under."""
        if self.import_as:
            return self.import_as
        if self.file_path:
            return versioning.parse(self.file_path)[0]
        return ""

    def summary(self) -> str:
        """``name.py`` or ``name.py as alias`` when the alias is not the stem."""
        if not self.file_path:
            return ""
        name = Path(self.file_path).name
        alias = self.alias()
        if alias and alias != versioning.parse(self.file_path)[0]:
            return f"{name} as {alias}"
        return name

    @classmethod
    def migrate_settings(cls, settings: dict) -> dict:
        """Accept the legacy ``script_file_path`` / ``commands`` keys."""
        data = dict(settings)
        legacy_path = data.pop("script_file_path", None)
        if legacy_path and not data.get("file_path"):
            data["file_path"] = legacy_path
        commands = data.pop("commands", None)
        if isinstance(commands, list) and commands and not data.get("code"):
            data["code"] = "\n".join(str(line) for line in commands)
        return data

    # --------------------------------------------------------------- steps
    def validate(self, ctx: ActionContext) -> list[str]:
        """Missing file (inherited), bad alias, reserved alias."""
        problems = super().validate(ctx)
        if not self.file_path:
            return problems
        alias = self.alias()
        if not alias.isidentifier() or keyword.iskeyword(alias):
            problems.append(f"import_as: '{alias}' is not a valid module name")
            return problems
        from tik.trigger.maya.scripts import ScriptSpace

        space = ctx.scripts if ctx.scripts is not None else ScriptSpace()
        if space.is_reserved(alias):
            problems.append(
                f"import_as: '{alias}' is already a module in this Maya; "
                "pick another name"
            )
        return problems

    def run(self, ctx: ActionContext) -> None:
        """Load the file under its alias, then exec the inline code."""
        from tik.trigger.maya.scripts import ScriptSpace

        if ctx.scripts is not None:
            self._run_in(ctx.scripts, ctx)
            return
        # run outside a Runner (tests, tools): a private build-lifetime space
        with ScriptSpace() as space:
            if ctx.base_dir:
                space.add_path(Path(ctx.base_dir) / "scripts")
            self._run_in(space, ctx)

    def _run_in(self, space, ctx: ActionContext) -> None:
        if self.file_path:
            path = ctx.resolve(self.file_path)
            if not path.exists():
                raise ActionExecutionError(f"Script not found: {path}")
            alias = self.alias()
            try:
                space.load(path, alias)
            except ImportError as error:
                raise ActionExecutionError(self._import_message(space, error)) from error
            ctx.log(f"Loaded {path.name} as {alias}")
            if self.lifetime == MAYA_LIFETIME:
                space.keep(alias)
        if self.code:
            namespace = space.globals(ctx)
            try:
                exec(compile(self.code, f"<{ctx.path or 'script'}>", "exec"), namespace)
            except ImportError as error:
                raise ActionExecutionError(self._import_message(space, error)) from error

    @staticmethod
    def _import_message(space, error: ImportError) -> str:
        hint = space.hint_for(error)
        return f"{error}. {hint}" if hint else str(error)
```

`versioning` is already re-exported by `tik.trigger.core` (see its `__init__`). `ActionContext.resolve` exists on the base context.

- [ ] **Step 4: Run to verify they pass**

Run: `<mayapy> -m pytest tests/unit/test_runner_trigger.py tests/unit/test_core_trigger.py tests/integration/trigger/test_session_build_trigger.py tests/integration/trigger/test_publish_phase_trigger.py -q`
Expected: all PASS. The existing integration tests use `code=` only and keep working.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/actions/script/script.py tests/unit/test_runner_trigger.py
git commit -m "TW-16: script action loads files as named modules with a lifetime"
```

---

### Task 6: Legacy settings migrate on load

**Files:**
- Modify: `src/python/tik/trigger/core/action.py` (`Action.migrate_settings` default)
- Modify: `src/python/tik/trigger/core/document.py` (`ActionNode.from_dict`)
- Test: `tests/unit/test_document_trigger.py`

**Interfaces:**
- Consumes: `Script.migrate_settings` (Task 5), `registry.is_action_registered` / `get_action`.
- Produces: `Action.migrate_settings(cls, settings) -> dict` (identity by default), applied by `ActionNode.from_dict` for registered types.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_document_trigger.py`:

```python
def test_legacy_script_settings_migrate_on_load():
    from tik.trigger.actions.script.script import Script
    from tik.trigger.core.registry import (
        is_action_registered,
        register_action,
        unregister_action,
    )

    if not is_action_registered("script"):
        register_action("script", category="structure", scope="both")(Script)
    try:
        doc = Document.load(DATA / "crabMonster_main_session_v002.tr")
        node = next(node for node in doc.actions if node.type == "script")
        assert node.settings["file_path"].endswith("claw_setup_v001.py")
        assert "script_file_path" not in node.settings
        assert "commands" not in node.settings
        # idempotent: a second pass through from_dict changes nothing
        assert ActionNode.from_dict(node.to_dict()).settings == node.settings
    finally:
        unregister_action("script")
```

Check `unregister_action` exists in `registry.py` (it does, line ~184) and whether a module-level fixture in this test file already registers actions; adapt the guard accordingly.

- [ ] **Step 2: Run to verify it fails**

Run: `<mayapy> -m pytest tests/unit/test_document_trigger.py -q -k legacy_script`
Expected: FAIL with `KeyError: 'file_path'`.

- [ ] **Step 3: Implement**

In `src/python/tik/trigger/core/action.py`, on `Action` after `description()`:

```python
    @classmethod
    def migrate_settings(cls, settings: dict) -> dict:
        """Translate settings written by an older version of this action.

        Called when a document is loaded. Must be idempotent. The default
        keeps the settings as they are.
        """
        return settings
```

In `src/python/tik/trigger/core/document.py`, `ActionNode.from_dict`, replace `settings=dict(settings or {}),` with a migrated value:

```python
        settings = dict(settings or {})
        settings = _migrate_settings(data["type"], settings)
        return cls(
            name=data["name"],
            type=data["type"],
            enabled=bool(data.get("enabled", True)),
            settings=settings,
            children=[cls.from_dict(item) for item in data.get("children", [])],
        )
```

and add, at module level below `ActionNode`:

```python
def _migrate_settings(action_type: str, settings: dict) -> dict:
    """Let a registered action translate its own legacy settings."""
    from . import registry  # local: registry imports this module

    if not registry.is_action_registered(action_type):
        return settings
    return registry.get_action(action_type).migrate_settings(settings)
```

- [ ] **Step 4: Run to verify it passes**

Run: `<mayapy> -m pytest tests/unit/test_document_trigger.py tests/unit/test_core_trigger.py tests/unit/test_session_trigger.py -q`
Expected: all PASS, including `test_old_flat_session_converts` (its `{"x": 1}` settings carry no legacy keys, so they are untouched).

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/core/action.py src/python/tik/trigger/core/document.py tests/unit/test_document_trigger.py
git commit -m "TW-16: actions migrate their legacy settings on document load"
```

---

### Task 7: Stub creation and opening files externally

**Files:**
- Create: `src/python/tik/trigger/actions/script/stub.py.tmpl`
- Modify: `src/python/tik/trigger/actions/script/script.py` (`create_script_file` module function)
- Modify: `src/python/tik/shared/io.py` (`open_external`)
- Modify: `src/python/tik/trigger/config/defaults.py` and `defaults.json` (`external_editor`)
- Test: `tests/unit/test_script_space_trigger.py` (stub), `tests/unit/test_shared_io.py` if it exists, else add the `open_external` test to `tests/unit/test_script_space_trigger.py`

**Interfaces:**
- Produces:
  - `tik.trigger.actions.script.script.create_script_file(session_dir, name) -> Path` writes `<session_dir>/scripts/<name>_v001.py` (or the next version if one exists) from the template and returns the path.
  - `tik.shared.io.open_external(path, command: str = "") -> None`; raises `OSError` on failure.
  - settings key `external_editor` default `""`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_script_space_trigger.py`:

```python
def test_create_script_file_writes_a_versioned_stub(tmp_path):
    from tik.trigger.actions.script.script import create_script_file

    first = create_script_file(tmp_path, "claw setup")
    assert first == tmp_path / "scripts" / "claw_setup_v001.py"
    text = first.read_text(encoding="utf-8")
    assert "claw_setup" in text and "def build(ctx)" in text
    assert "{" not in text.replace("{rig.root.long_name}", "")
    second = create_script_file(tmp_path, "claw_setup")
    assert second.name == "claw_setup_v002.py"
    with pytest.raises(ValueError):
        create_script_file(tmp_path, "9lives")


def test_open_external_uses_the_configured_command(monkeypatch, tmp_path):
    from tik.shared import io

    launched = []
    monkeypatch.setattr(io.subprocess, "Popen", lambda args, **kw: launched.append(args))
    target = tmp_path / "a.py"
    target.write_text("", encoding="utf-8")
    io.open_external(target, command="code --goto {path}")
    assert launched == [["code", "--goto", str(target)]]
    io.open_external(target, command="subl")
    assert launched[-1] == ["subl", str(target)]
```

- [ ] **Step 2: Run to verify they fail**

Run: `<mayapy> -m pytest tests/unit/test_script_space_trigger.py -q -k "stub or external"`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write the template**

Create `src/python/tik/trigger/actions/script/stub.py.tmpl` (Python `string.Template` syntax, `$name` / `$alias`):

```python
"""$name -- session scripts.

Loaded by the Trigger script action as ``$alias``. Functions here receive the
build context explicitly; nothing is injected.
"""

from tik.trigger.maya import scaffold  # noqa: F401 - handy for post-build helpers


def build(ctx):
    """Called from an inline snippet: ``$alias.build(ctx)``."""
    rig = ctx.rig
    ctx.log(f"$alias.build running on {rig.root.long_name}")
```

- [ ] **Step 4: Add `create_script_file`**

In `src/python/tik/trigger/actions/script/script.py`, add imports `import re` and `from string import Template`, and at module level (below the class):

```python
_TEMPLATE = Path(__file__).with_name("stub.py.tmpl")


def create_script_file(session_dir, name: str) -> Path:
    """Write a versioned stub into ``<session_dir>/scripts`` and return it.

    ``name`` is slugged to an identifier (spaces and dashes become
    underscores). The one place Trigger writes a ``.py`` file.
    """
    slug = re.sub(r"[^0-9A-Za-z_]+", "_", name.strip()).strip("_").lower()
    if not slug.isidentifier() or keyword.iskeyword(slug):
        raise ValueError(f"'{name}' is not a valid script name")
    folder = Path(session_dir) / "scripts"
    folder.mkdir(parents=True, exist_ok=True)
    target = versioning.next_version(folder / f"{slug}.py")
    text = Template(_TEMPLATE.read_text(encoding="utf-8")).substitute(
        name=target.stem, alias=slug
    )
    target.write_text(text, encoding="utf-8")
    return target
```

`versioning.next_version(folder / "claw_setup.py")` returns `claw_setup_v001.py` when nothing exists and `_v002` after it (see `versioning.next_version`).

- [ ] **Step 5: Add `open_external`**

In `src/python/tik/shared/io.py`, add `import os`, `import shlex`, `import subprocess`, `import sys` to the imports, and at the end of the file:

```python
def open_external(path, command: str = "") -> None:
    """Open ``path`` in an external application.

    ``command`` is a user-configured launcher: ``{path}`` is substituted when
    present, otherwise the path is appended. Without one the OS default
    handler opens the file. Raises ``OSError`` when the launch fails.
    """
    target = str(Path(path))
    if command.strip():
        if "{path}" in command:
            args = [part.replace("{path}", target) for part in shlex.split(command)]
        else:
            args = shlex.split(command) + [target]
        subprocess.Popen(args)
        return
    if sys.platform.startswith("win"):
        os.startfile(target)  # noqa: S606 - the OS handler is the point
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])
```

- [ ] **Step 6: Add the settings key**

In `src/python/tik/trigger/config/defaults.py` add `"external_editor": "",` after `"debug_mode": False,`; in `defaults.json` add `"external_editor": "",` after `"debug_mode": false,`.

- [ ] **Step 7: Run to verify they pass**

Run: `<mayapy> -m pytest tests/unit/test_script_space_trigger.py tests/unit -q -k "stub or external or settings or defaults"`
Expected: PASS. If a test asserts `defaults.py` and `defaults.json` are equal, it now still passes because both were changed.

- [ ] **Step 8: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/actions/script/ src/python/tik/shared/io.py src/python/tik/trigger/config/defaults.py src/python/tik/trigger/config/defaults.json tests/unit/test_script_space_trigger.py
git commit -m "TW-16: versioned script stubs and open_external"
```

---

### Task 8: Settings panel: `.py` pencil, `New Script…`, and a `handle_changed` signal

**Files:**
- Modify: `src/python/tik/trigger/ui/settings_panel.py`
- Modify: `src/python/tik/trigger/ui/session_view.py` (route `open_file_requested` by extension; re-emit `handle_changed`)
- Test: `tests/ui/test_pipeline_ui.py`

**Interfaces:**
- Consumes: `create_script_file`, `open_external` (Task 7), `trigger_settings`.
- Produces:
  - `ActionSettingsPanel.handle_changed = Signal(object)` emitted at the end of `set_handle`.
  - `ActionSettingsPanel.new_script(name: Optional[str] = None) -> Optional[Path]`; with `name=None` it prompts through `Feedback.ask_text`.
  - `ActionSettingsPanel.new_script_button`.
  - `ActionSettingsPanel.open_externally(path: str)`.
  - `SessionView.handle_changed = Signal(object)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_pipeline_ui.py` (the `view` fixture and `_registered` fixture are there; register the real `Script` inside the test since `_registered` clears registries):

```python
def test_py_file_field_gets_a_pencil_and_new_script_writes_a_stub(view, tmp_path, monkeypatch):
    from tik.trigger.actions.script.script import Script
    from tik.trigger.core.registry import register_action
    from tik.trigger.ui import settings_panel

    register_action("script", category="structure", scope="both")(Script)
    opened = []
    monkeypatch.setattr(settings_panel, "open_external", lambda path, command="": opened.append(str(path)))
    view.add_action("script")
    panel = view.settings
    assert panel.new_script_button.isVisible()
    # unsaved session: disabled with a reason
    assert not panel.new_script_button.isEnabled()
    assert "save" in panel.new_script_button.toolTip().lower()
    view.session.file_path = tmp_path / "hero_v001.tr"
    panel.set_handle(panel.handle)
    assert panel.new_script_button.isEnabled()
    created = panel.new_script("claw setup")
    assert created == tmp_path / "scripts" / "claw_setup_v001.py"
    assert view.session["script"].file_path == "scripts/claw_setup_v001.py"
    assert opened == [str(created)]
    # the pencil on the file field opens the same way
    field = panel.form.widget("file_path")
    assert field.extra_button is not None
    field.extra_button.click()
    assert opened[-1] == str(created)


def test_the_panel_announces_its_handle(view):
    seen = []
    view.handle_changed.connect(lambda handle: seen.append(handle.path if handle else None))
    view.add_action("mark")
    assert seen[-1] == "mark"
    view.settings.set_handle(None)
    assert seen[-1] is None
```

Check `Session.file_path` is a plain attribute (it is set in `Session.new`; confirm with `grep -n "file_path" src/python/tik/trigger/session.py`). If it is a property with a setter, use that; if there is a `save(path)` method, call `view.session.save(tmp_path / "hero_v001.tr")` instead.

- [ ] **Step 2: Run to verify they fail**

Run: `$env:TIK_TESTS_NO_MAYA=1; $env:QT_QPA_PLATFORM="offscreen"; <mayapy> -m pytest tests/ui/test_pipeline_ui.py -q -k "pencil or announces"`
Expected: FAIL with `AttributeError` on `new_script_button` / `handle_changed`.

- [ ] **Step 3: Implement the panel changes**

In `src/python/tik/trigger/ui/settings_panel.py`:

Imports to add:

```python
from pathlib import Path

from tik.shared.io import open_external
from tik.trigger.config import trigger_settings
```

Signals: add `handle_changed = QtCore.Signal(object)` under the existing signals.

`file_extras` in `__init__` becomes:

```python
            file_extras={
                ".trg": ("✎", lambda path: self.open_file_requested.emit(path, ".trg")),
                ".py": ("✎", self.open_externally),
            },
```

Button: after `self.guides_button` is created and added, add:

```python
        self.new_script_button = QtWidgets.QPushButton("New Script…")
        self.new_script_button.setToolTip("Write a versioned stub into the session's scripts folder")
        self.new_script_button.setVisible(False)
        buttons.addWidget(self.new_script_button)
        ...
        self.new_script_button.clicked.connect(lambda: self.new_script())
```

`set_handle`: in the `handle is None` branch add `self.new_script_button.setVisible(False)` and, at the very end of that branch and of the method, `self.handle_changed.emit(handle)`. In the populated branch, after `self.guides_button.setVisible(...)`:

```python
        self.new_script_button.setVisible(self._py_field_name() is not None)
        self._refresh_new_script_state()
```

New methods:

```python
    def _py_field_name(self) -> Optional[str]:
        """Name of the first ``.py`` FileField on the current action, if any."""
        if self._action is None:
            return None
        for name, field in type(self._action).fields().items():
            if ".py" in (getattr(field, "extensions", None) or ()):
                return name
        return None

    def _refresh_new_script_state(self) -> None:
        saved = bool(self._base_dir() if self._base_dir else "")
        self.new_script_button.setEnabled(saved)
        self.new_script_button.setToolTip(
            "Write a versioned stub into the session's scripts folder"
            if saved
            else "Save the session first: scripts live beside the .tr file"
        )

    def open_externally(self, path: str) -> None:
        """Open ``path`` (relative to the session) in the external editor."""
        if not path:
            return
        target = Path(path)
        base = self._base_dir() if self._base_dir else ""
        if not target.is_absolute() and base:
            target = Path(base) / target
        try:
            open_external(target, trigger_settings.get("external_editor") or "")
        except OSError as error:
            Feedback(self).pop_warning("Open script", f"Could not open {target}", str(error))

    def new_script(self, name: Optional[str] = None) -> Optional[Path]:
        """Write a stub into ``scripts/``, point the file field at it, open it."""
        from tik.trigger.actions.script.script import create_script_file

        field_name = self._py_field_name()
        base = self._base_dir() if self._base_dir else ""
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
```

The panel receives `base_dir` in its constructor already; store it: in `__init__` add `self._base_dir = base_dir` before building the form.

- [ ] **Step 4: Wire `SessionView`**

In `src/python/tik/trigger/ui/session_view.py`:

- Add the signal `handle_changed = QtCore.Signal(object)` beside `open_guides_requested`.
- After `self.settings = ActionSettingsPanel(...)` add `self.settings.handle_changed.connect(self.handle_changed)`.
- Replace the `open_file_requested` connection with one that routes by extension:

```python
        self.settings.open_file_requested.connect(self._on_open_file_requested)
```

and the method:

```python
    def _on_open_file_requested(self, path: str, extension: str) -> None:
        if extension == ".trg":
            self.open_guides_requested.emit(path)
        else:
            self.settings.open_externally(path)
```

(The `.py` pencil already calls `open_externally` directly, so this branch is the safety net for any other extension the form may route here later.)

- [ ] **Step 5: Run to verify they pass**

Run: `$env:TIK_TESTS_NO_MAYA=1; $env:QT_QPA_PLATFORM="offscreen"; <mayapy> -m pytest tests/ui/test_pipeline_ui.py -q; <mayapy> -m pytest tests/unit/test_dialog_boundaries.py -q`
Expected: all PASS.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/ui/settings_panel.py src/python/tik/trigger/ui/session_view.py tests/ui/test_pipeline_ui.py
git commit -m "TW-16: New Script button, .py pencil opens externally, handle_changed signal"
```

---

### Task 9: The Script viewer dock

**Files:**
- Create: `src/python/tik/trigger/ui/script_dock.py`
- Modify: `src/python/tik/trigger/ui/main.py` (dock, Tools menu toggle, selection following)
- Test: `tests/ui/test_script_dock.py` (new)

**Interfaces:**
- Consumes: `SessionView.handle_changed` (Task 8), `open_external`.
- Produces: `ScriptViewer(QtWidgets.QWidget)` with `show_handle(handle, base_dir: str)`, `clear()`, attributes `path_label`, `open_button`, `text`; `TriggerWindow.script_dock`, `TriggerWindow.script_action` (menu), `TriggerWindow.toggle_script_viewer()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_script_dock.py`:

```python
"""The read-only Script viewer dock follows the selected script action."""

import pytest
from test_pipeline_ui import _stub_designer

from tik.trigger.core.registry import clear_registries, register_action
from tik.trigger.ui.main import TriggerWindow
from tik.trigger.ui.script_dock import ScriptViewer


@pytest.fixture
def window(qapp):
    clear_registries()
    from tik.trigger.actions.script.script import Script

    register_action("script", category="structure", scope="both")(Script)
    win = TriggerWindow(designer_factory=_stub_designer)
    win.show()
    yield win
    win.close()
    clear_registries()


def test_viewer_shows_file_then_code_and_a_placeholder_otherwise(qapp, tmp_path):
    from tik.trigger.core import ActionNode, Document
    from tik.trigger.session import Session

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "lib_v001.py").write_text("def f():\n    pass\n", encoding="utf-8")
    session = Session()
    session.file_path = tmp_path / "hero_v001.tr"
    session.add("script", "lib", file_path="scripts/lib_v001.py", code="lib.f()")
    viewer = ScriptViewer()
    viewer.show_handle(session["lib"], session.directory)
    text = viewer.text.toPlainText()
    assert "def f():" in text and "lib.f()" in text
    assert text.index("def f()") < text.index("lib.f()")
    assert "lib_v001.py" in viewer.path_label.text()
    assert viewer.open_button.isEnabled()
    viewer.show_handle(None, "")
    assert "Select a script action" in viewer.text.toPlainText()
    assert not viewer.open_button.isEnabled()


def test_viewer_reloads_when_the_file_changes(qapp, tmp_path):
    from tik.trigger.session import Session

    (tmp_path / "scripts").mkdir()
    target = tmp_path / "scripts" / "lib_v001.py"
    target.write_text("A = 1\n", encoding="utf-8")
    session = Session()
    session.file_path = tmp_path / "hero_v001.tr"
    session.add("script", "lib", file_path="scripts/lib_v001.py")
    viewer = ScriptViewer()
    viewer.show_handle(session["lib"], session.directory)
    target.write_text("A = 2\n", encoding="utf-8")
    viewer._reload()  # what the QFileSystemWatcher slot calls
    assert "A = 2" in viewer.text.toPlainText()


def test_the_window_hosts_the_dock_and_follows_the_selection(window):
    view = window.current_view
    assert window.script_dock.isHidden()
    window.script_action.trigger()
    assert window.script_dock.isVisible()
    view.add_action("script")
    assert "Select a script action" not in window.script_viewer.text.toPlainText()
    view.settings.set_handle(None)
    assert "Select a script action" in window.script_viewer.text.toPlainText()
```

`Session.add(type, name, **settings)` is the signature used by `tests/integration/trigger/test_publish_phase_trigger.py` (`rig.add("script", "build_a", code=...)`); confirm with `grep -n "def add" src/python/tik/trigger/session.py`.

- [ ] **Step 2: Run to verify they fail**

Run: `$env:TIK_TESTS_NO_MAYA=1; $env:QT_QPA_PLATFORM="offscreen"; <mayapy> -m pytest tests/ui/test_script_dock.py -q`
Expected: FAIL with `ModuleNotFoundError: tik.trigger.ui.script_dock`.

- [ ] **Step 3: Implement the viewer**

Create `src/python/tik/trigger/ui/script_dock.py`:

```python
"""Read-only viewer for the selected script action's file and inline code.

It never edits: editing is external (spec 2026-09-06, decision 4). A
``QFileSystemWatcher`` reloads the view when the file changes on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tik.shared.io import open_external
from tik.shared.ui.feedback import Feedback
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.config import trigger_settings

PLACEHOLDER = "Select a script action."
RULE = "\n\n# " + "-" * 60 + "  inline code\n\n"


class ScriptViewer(QtWidgets.QWidget):
    """Path header, Open button, monospace read-only text."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)
        header = QtWidgets.QHBoxLayout()
        self.path_label = QtWidgets.QLabel("")
        self.path_label.setObjectName("PanelSubtitle")
        self.open_button = QtWidgets.QToolButton()
        self.open_button.setText("Open")
        self.open_button.setToolTip("Open the file in the external editor")
        self.open_button.setEnabled(False)
        header.addWidget(self.path_label, 1)
        header.addWidget(self.open_button)
        layout.addLayout(header)
        self.text = QtWidgets.QPlainTextEdit()
        self.text.setObjectName("ScriptViewerText")
        self.text.setReadOnly(True)
        self.text.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        layout.addWidget(self.text, 1)
        self._watcher = QtCore.QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(lambda _path: self._reload())
        self._path: Optional[Path] = None
        self._code = ""
        self.open_button.clicked.connect(self._open)
        self.clear()

    # ------------------------------------------------------------- binding
    def show_handle(self, handle, base_dir: str) -> None:
        """Show ``handle``'s script file and code, or the placeholder."""
        self._unwatch()
        if handle is None or handle.type != "script":
            self.clear()
            return
        settings = dict(handle.settings)
        raw = settings.get("file_path") or ""
        self._code = settings.get("code") or ""
        self._path = None
        if raw:
            path = Path(raw)
            if not path.is_absolute() and base_dir:
                path = Path(base_dir) / path
            self._path = path
            if path.exists():
                self._watcher.addPath(str(path))
        self.open_button.setEnabled(self._path is not None)
        self._reload()

    def clear(self) -> None:
        """The empty state."""
        self._unwatch()
        self._path = None
        self._code = ""
        self.path_label.setText("")
        self.open_button.setEnabled(False)
        self.text.setPlainText(PLACEHOLDER)

    def _unwatch(self) -> None:
        files = self._watcher.files()
        if files:
            self._watcher.removePaths(files)

    def _reload(self) -> None:
        parts = []
        if self._path is not None:
            if self._path.exists():
                self.path_label.setText(str(self._path))
                parts.append(self._path.read_text(encoding="utf-8", errors="replace"))
                # editors that replace the file drop the watch: re-add it
                if str(self._path) not in self._watcher.files():
                    self._watcher.addPath(str(self._path))
            else:
                self.path_label.setText(f"{self._path}  (missing)")
        else:
            self.path_label.setText("inline code only" if self._code else "")
        if self._code:
            parts.append((RULE if parts else "") + self._code)
        self.text.setPlainText("\n".join(parts) if parts else "")

    def _open(self) -> None:
        if self._path is None:
            return
        try:
            open_external(self._path, trigger_settings.get("external_editor") or "")
        except OSError as error:
            Feedback(self).pop_warning("Open script", f"Could not open {self._path}", str(error))

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt style
        self._unwatch()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._path is not None and self._path.exists():
            self._watcher.addPath(str(self._path))
            self._reload()
```

- [ ] **Step 4: Host it in the window**

In `src/python/tik/trigger/ui/main.py`:

Import: `from .script_dock import ScriptViewer`.

In `_build_shell`, after the log dock block:

```python
        self.script_viewer = ScriptViewer()
        self.script_dock = QtWidgets.QDockWidget("Script", self)
        self.script_dock.setObjectName("TriggerScriptDock")
        self.script_dock.setWidget(self.script_viewer)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.script_dock)
        self.script_dock.hide()
        self.script_dock.visibilityChanged.connect(
            lambda visible: self.script_action.setChecked(visible)
            if hasattr(self, "script_action")
            else None
        )
```

In `_build_tools_menu`, right after `self.log_action = ...`:

```python
        self.script_action = self._action(
            tools_menu, "Show Script Viewer", self.toggle_script_viewer, "Ctrl+Shift+S", checkable=True
        )
```

Check `Ctrl+Shift+S` is not already bound (`grep -n '"Ctrl+Shift+S"' src/python/tik/trigger/ui/main.py`); if it is, use `Ctrl+Alt+S`.

New method beside `toggle_log`:

```python
    def toggle_script_viewer(self) -> None:
        """Show or hide the Script viewer dock."""
        self.script_dock.setVisible(not self.script_dock.isVisible())
        self.script_action.setChecked(self.script_dock.isVisible())
        if self.script_dock.isVisible():
            self._refresh_script_viewer()

    def _refresh_script_viewer(self) -> None:
        view = self.current_view
        if view is None:
            self.script_viewer.clear()
            return
        self.script_viewer.show_handle(view.current_handle(), view.session.directory)

    def _on_handle_changed(self, view, handle) -> None:
        if view is self.current_view:
            self.script_viewer.show_handle(handle, view.session.directory)
```

In `add_session`, after `view.activity.connect(...)`:

```python
        view.handle_changed.connect(
            lambda handle, session_view=view: self._on_handle_changed(session_view, handle)
        )
```

In `_on_tab_changed`, add `self._refresh_script_viewer()` after `self._update_title()`.

- [ ] **Step 5: Run to verify they pass**

Run: `make tests-ui`
Expected: all PASS, including `tests/ui/test_menus.py` (it counts menus, not actions; if a test enumerates Tools entries, add the new one to its expectation).

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/ui/script_dock.py src/python/tik/trigger/ui/main.py tests/ui/test_script_dock.py
git commit -m "TW-16: read-only Script viewer dock that follows the selection"
```

---

### Task 10: Full verification and the project notes

**Files:**
- Modify: `CLAUDE.md` (tik.trigger status paragraph: one clause about the script action; add the spec to the design specs list)
- Modify: `AI/coding_rules.md` only if it lists action fields (check with `grep -n "script" AI/coding_rules.md`); otherwise nothing.

- [ ] **Step 1: Run everything**

```powershell
make lint
make tests-unit
make tests-integration
make tests-ui
```

Expected: all green. Fix anything red before moving on; a red test here is a bug in a previous task, not something to skip.

- [ ] **Step 2: Update `CLAUDE.md`**

In the `tik.trigger (IN DEVELOPMENT)` status paragraph, after the sentence ending `opposite ends of the Designer's bar.`, add:

> Since the 2026-09-06 pass the `script` action loads files as **named modules** (`import_as`, default the file stem) into a per-run `trigger_build` namespace with a `lifetime` of `build` or `maya`; inline code sees every alias and `ctx`. Editing is external; `New Script…` writes a versioned stub into `scripts/`; the Script dock is a read-only viewer.

In the **Design specs** entry, prepend `docs/superpowers/specs/2026-09-06-script-action-libraries-design.md` (script action libraries, lifetime, viewer) to the list.

In the **tik.trigger Tests** section add a line:
`- tests/unit/test_script_space_trigger.py — the per-run module namespace, stubs, open_external; tests/ui/test_script_dock.py — the viewer`

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "TW-16: project notes for the script action libraries pass"
```

- [ ] **Step 4: Report**

Summarise for the user: what landed per task, the full test run output line for each suite, and that the branch is ready for the finishing-a-development-branch step. Do not push.
