# Script action: libraries, lifetime and the viewer

**Date:** 2026-09-06
**Status:** Design approved, ready for an implementation plan
**Area:** `tik.trigger` — the `script` action, the Maya runner, `tik.core.fields`,
`FormBuilder`, the pipeline UI
**Ticket:** TW-16

## 1. The problem

The `script` action is two single-line strings: a file path and a line of
code. Each run gets a throwaway namespace with only `ctx` in it. That serves
"run one snippet" and nothing else.

What riggers actually do is build a small library per asset and call into it
from many places in the pipeline:

```
scripts/general_rig_utils_v001.py   -> generic, rig-agnostic         as gen_rig
scripts/cfx_utils_v001.py           -> imports gen_rig, adds cfx     as cfx_utils
scripts/hero_build_v001.py          -> asset-specific build steps    as hero_build
```

The modules are loaded once near the top of the build; later script actions
are one-line calls such as `hero_build.finalize(ctx)`. Today's action cannot
express this: everything execs into one flat dict, so two files with a
`build_ctrl` collide, and `cfx_utils.py` cannot `import gen_rig` because
nothing by that name exists in `sys.modules`. The legacy session format already
had this shape (`script_file_path`, `import_as`, `commands`); the rebuild lost
it.

Three smaller costs ride along. The file path is a bare `StringField`, so there
is no browse button, no version badge, and no missing-file check before the
run. The inline code is a one-line edit. And there is no way to read a script
without leaving Trigger.

## 2. Decisions

Settled during design; the rest of the document follows from them.

1. **A script file is a named module, not a body to exec.** The runner loads it
   with `importlib` under an alias and registers it in `sys.modules`. Files can
   import each other by alias. Inline code runs in a shared build namespace
   where every alias loaded so far is a global.
2. **Lifetime has two tiers, `build` (default) and `maya`.** Lifetime covers
   both the module names and the import path, because they are linked: a
   module that survives the run needs its imports to keep resolving.
   There is no per-step isolation tier; a function does that job.
3. **Every run reloads.** Modules are re-executed from disk on each build.
   Edits in an external editor are picked up without restarting Maya.
4. **Editing is external.** Trigger opens the file in the OS editor (or a
   user-configured command) and shows a read-only viewer. Trigger never writes
   a `.py` file except the one case below.
5. **`New…` writes a versioned stub** into `<session dir>/scripts/`, fills the
   path field, and opens the file. The one time Trigger creates a `.py`.
6. **The word "scope" is taken.** `@register_action(scope=)` already means
   build-list / publish-list placement. The new field is called `lifetime`.

## 3. The action

```python
@register_action("script", category="structure", icon="script", scope="both")
class Script(Action):
    """Load a Python file as a named module, then run inline code."""

    file_path = FileField("", extensions=[".py"], label="Script File")
    import_as = StringField("", label="Import As",
                            help="Module name for the file; defaults to its stem")
    code = TextField("", label="Code",
                     help="Runs after the file, with every loaded module in scope")
    lifetime = ChoiceField("build", choices=["build", "maya"],
                           help="build: names vanish when the run ends. "
                                "maya: they stay importable until the next run")
```

Either half is optional. A file with no code is a library load; code with no
file is a snippet. Both empty is a no-op that validates clean.

`summary()` (inherited) already shows the file name. When `import_as` is set
and differs from the stem the summary is `"<name> as <alias>"`.

### 3.1 `run(ctx)`

1. If `file_path` is set: resolve it against the session directory, build a
   spec with `importlib.util.spec_from_file_location(alias, path)`, create the
   module, register it in `sys.modules[alias]` **before** executing it (so
   self-referential and circular imports behave like normal Python), then
   `exec_module`. A failure removes the half-registered name and re-raises;
   the runner wraps it into the usual step failure with the alias and path in
   the message.
2. Register the alias in the build namespace (section 4): `namespace[alias] = module`.
3. If `code` is set: `exec(compile(code, f"<{ctx.path}>", "exec"), namespace)`.
   The filename in the compile call is the action path, so tracebacks name
   the action.
4. If `lifetime == "maya"`: mark the alias as persistent for this run
   (section 4.2).

The alias is `import_as` or the file stem with its version suffix stripped
(`general_rig_utils_v001.py` becomes `general_rig_utils`), passed through
`versioning.parse`. An alias must be a valid identifier; `validate()` reports
it otherwise, before the run starts.

### 3.2 What a loaded file sees

- `__name__ == alias`, so `if __name__ == "__main__":` never fires. Correct
  for a library.
- `__file__` is the resolved path, so relative resources work.
- `ctx` is **not** injected into the module. A library that needs the context
  takes it as an argument: `def finalize(ctx): ...`. Inline code is where
  `ctx` lives, and it passes it on. This keeps files importable outside a
  build and testable in plain `mayapy`.
- The session's `scripts/` folder is on `sys.path` for the run, so
  `import general_rig_utils` by file name also works, alias or not.

### 3.3 Order is the dependency order

`cfx_utils.py` writing `import gen_rig` requires the `gen_rig` action to sit
earlier in the pipeline. Trigger does not analyse imports ahead of time. The
failure is an ordinary `ImportError` on the later step, and the message adds
one line: *"gen_rig is not loaded yet; a script action that loads it must run
before this one."* The runner knows this because the missing name is not in
the build namespace and is not importable from `scripts/` either.

## 4. The build namespace

### 4.1 During a run

The runner owns one `ScriptSpace` per `Runner.run()` call, created in
`run()` and torn down in a `finally` around the step loop:

```python
class ScriptSpace:
    """The modules and globals script actions share for one run."""
    name = "trigger_build"

    def __enter__(self)      # tear down the previous run's leftovers; register self.module
    def __exit__(self, ...)  # remove added paths; drop every alias not marked persistent
    def add_path(self, scripts_dir: Path) -> None   # once per distinct dir, idempotent
    def load(self, path: Path, alias: str) -> ModuleType
    def globals(self, ctx) -> dict   # the exec namespace: aliases + ctx + __name__
    def keep(self, alias: str) -> None
```

It lives in `tik/trigger/maya/runner.py`'s neighbourhood, as
`tik/trigger/maya/scripts.py`. It touches `sys.modules` and `sys.path`, which
is process state, not Maya state, so it could sit in `core`; it goes in `maya`
because the runner is its only client and the layering test does not need to
know about it.

`trigger_build` itself is a real module registered in `sys.modules` for the
run. Its `__dict__` is the exec namespace. So inline code, a loaded file and
the Maya Script Editor all agree on what `trigger_build.hero_build` means.
`ctx` is set on it at the start of each step and removed at the end of the run.

`ActionContext` gains one field, `scripts: Any = None`, that the Maya runner
sets to the `ScriptSpace`. `core` never reads it, as with `rig`.

Before each step the runner calls `add_path(<step.base_dir>/scripts)`; the
call is a no-op when the folder does not exist or was already added. For a
referenced session (`Reference.expand`), `step.base_dir` is the referenced
file's directory, so a reference's scripts resolve against its own folder.
Paths are added as steps are reached and removed only at the end of the run,
never per step: a module loaded from the reference must still find its
siblings when a later top-level step calls it.

### 4.2 After a run

- **`build`** aliases are removed from `sys.modules` and from `trigger_build`
  when the run ends, success or failure. `trigger_build` itself is removed.
- **`maya`** aliases survive, and so does `trigger_build`, holding those
  aliases only. The `scripts/` path entries survive with them. The next run,
  from any session tab, replaces them: `__enter__` first tears down whatever
  the previous run left. **Last run wins**, stated in the action help and the
  user docs. Two sessions open in tabs share one Maya, so they share one
  `trigger_build`.

A rigger in the Script Editor after a `maya`-lifetime build writes:

```python
import trigger_build
trigger_build.hero_build.finalize(trigger_build.ctx)   # ctx is None after the run
```

`ctx` is None after the run on purpose. The scaffold is reachable through
`tik.trigger.maya.scaffold.ensure_rig()`, which is what a post-build helper
should call; the run context is a run-time object and pretending it outlives
the run would hand out a stale event bus.

### 4.3 Reloading

`__enter__` tears down before `load` runs, so a file is always executed
fresh. Nothing in Trigger calls `importlib.reload`; a plain re-exec into a new
module object is simpler and has no stale-attribute problem. A `maya` module
that the rigger has monkey-patched from the Script Editor loses the patch on
the next build, which is the expected reload behaviour.

## 5. Fields and the form

### 5.1 `TextField`

A new field in `tik.core.fields`:

```python
class TextField(Field):
    """Multi-line text. Stored as one string with ``\n`` line breaks."""
    type_name = "text"
    def __init__(self, default="", *, language="", **kwargs)
```

`coerce` accepts `None` as `""`, rejects non-strings, and normalises `\r\n`
to `\n`. `language` is advisory for the editor (`"python"` gives a monospace
font and a tab-inserts-four-spaces filter; anything else is plain).
`to_schema` adds `language`.

`FormBuilder` renders `text` as a `_TextEditor`: a `QPlainTextEdit` with a
fixed minimum of six lines, growing with content to a cap of twenty, a
monospace font when `language == "python"`, and `Tab` inserting spaces. It
emits on focus-out and on `Ctrl+Enter`, not per keystroke, matching how the
line edits commit. Override marks (the linked-reference amber) work as for
any other widget since the form treats it as one value.

The text field takes the full form row: label above, editor spanning both
columns, so code is not squeezed into the value column.

### 5.2 The `.py` file field

`file_path` becomes a `FileField(extensions=[".py"])`. It inherits browse,
the Nuke-style version badge, Alt+Up / Alt+Down stepping and the base
`validate()` missing-file check. `FormBuilder.file_extras` gains a `.py`
entry alongside `.trg`, rendered as the same pencil button, whose callback
emits `open_file_requested(path, ".py")`.

`ActionSettingsPanel` grows one button next to `Open Guide Designer`, visible
only for actions with a `.py` file field: **New Script…**. It asks
`Feedback.ask_text` for a name, writes the stub (section 6) to
`<session dir>/scripts/<name>_v001.py`, sets the field, and opens the file.
If the session is unsaved (no directory yet) the button is disabled with a
tooltip saying to save first, the same rule the versioned badge already
applies.

### 5.3 Legacy settings

`Action.__init__` applies settings with `strict=False`, so unknown keys are
ignored. `Script` adds a `migrate(settings)` classmethod the loader calls for
`type == "script"` nodes: `script_file_path` maps to `file_path`,
`import_as` stays, and a non-empty `commands` list joins with `\n` into
`code`. No schema bump; the document version stays at 6 because the change
is confined to one action's settings, and the migration is idempotent.

## 6. Files on disk

### 6.1 The stub

```python
"""<name> -- session scripts.

Loaded by the Trigger script action as ``<alias>``. Functions here receive the
build context explicitly; nothing is injected.
"""

from tik.trigger.maya import scaffold


def build(ctx):
    """Called from an inline snippet: ``<alias>.build(ctx)``."""
    rig = ctx.rig
    ctx.log(f"<alias>.build running on {rig.root.long_name}")
```

`<name>` and `<alias>` are filled in. The template lives beside the action as
`script/stub.py.tmpl` so it is data, not code with `.format` hazards.

### 6.2 Opening a file

`tik.shared.io.open_external(path)`: on Windows `os.startfile`, on macOS
`open`, elsewhere `xdg-open`, via `subprocess.Popen` with no shell. If the
user settings hold `external_editor` (a command string, `{path}`
substituted, or the path appended when absent), that wins. No picker UI in
this pass; the key is documented in the user settings reference.

## 7. The viewer

A `QDockWidget` on `TriggerWindow`, titled **Script**, object name
`TriggerScriptDock`, hidden by default, toggled from the same View menu as
Log. It holds a read-only `QPlainTextEdit` in the monospace font with a
one-line header above it: the resolved path, the badge state, and an
**Open** button that calls `open_external`.

It follows the selection: `TriggerWindow` connects each `SessionView`'s
selection change and tab change to `ScriptDock.show_handle(handle)`. For a
script action it shows the file's contents, then a rule, then the inline code
when both are set. For any other action, or no selection, it shows a single
muted line: *"Select a script action."* It never edits: no Save, no key
handling beyond copy.

A `QFileSystemWatcher` on the current file reloads the view when the file
changes on disk, which is how edits made in the external editor appear. The
watcher is re-pointed on every `show_handle` and cleared when the dock hides,
so it never holds a handle on a file the rigger is trying to rename.

Being a real dock, it floats and tabs with the Log. The window does not
persist dock layout today, and this pass does not add that.

## 8. Error handling

| Case | Where | What the rigger sees |
|---|---|---|
| File missing | `validate()` before the run | step fails pre-flight: `file_path: file not found (…)` |
| Alias not an identifier | `validate()` | `import_as: 'my alias' is not a valid module name` |
| Exception inside the file | `run()` | step fails; traceback names the file and line; alias unregistered |
| Exception in inline code | `run()` | step fails; traceback names `<actions/finalize>` |
| `ImportError` for an alias loaded later | `run()` | the `ImportError`, plus the ordering hint from 3.3 |
| Alias clashes with a real module (`import_as = "maya"`) | `validate()` | rejected: names already in `sys.modules` before the run are reserved |
| Session unsaved, `New Script…` pressed | panel | button disabled, tooltip says to save first |
| External editor command fails | `open_external` | `Feedback.pop_warning` with the command and the OS error |

Failure teardown is the same as success teardown: `ScriptSpace.__exit__`
runs from the runner's `finally`, so a failed build never leaves `build`
aliases behind and never leaves the `scripts/` path in `sys.path`.

## 9. Testing

- `tests/unit/test_fields.py` (existing): `TextField` coercion, `\r\n`
  normalisation, schema output.
- `tests/unit/test_script_space_trigger.py` (pure Python, no Maya): enter and
  exit restore `sys.path` and `sys.modules`; `build` aliases vanish; `maya`
  aliases survive and are replaced by the next space; a second file can
  `import` the first by alias; a failure inside a file unregisters it; an
  alias colliding with a pre-existing module is refused; the stub renders with
  name and alias substituted.
- `tests/unit/test_runner_trigger.py` (Maya): rewrite
  `test_a_script_can_extend_the_preferences_control` for the new fields, and
  add: a three-action pipeline mirroring the `gen_rig` / `cfx_utils` /
  `hero_build` example where the last action's inline code calls through both;
  a `maya`-lifetime run leaves `trigger_build.hero_build` importable and the
  next run replaces it; a referenced session's script resolves against the
  referenced folder.
- `tests/unit/test_document_trigger.py`: loading a legacy node with
  `script_file_path` / `import_as` / `commands` produces the new settings and
  round-trips unchanged after that.
- `tests/ui/test_form_builder.py` (existing): the text editor commits on focus
  out and `Ctrl+Enter`, and renders across the full row.
- `tests/ui/test_pipeline_ui.py` (existing): `.py` file gets the pencil; `New Script…`
  is disabled for an unsaved session and, for a saved one, writes
  `scripts/<name>_v001.py` into a temp session dir and sets the field.
- `tests/ui/test_script_dock.py` (new): shows the file and the code for a script
  action, the placeholder for others, and reloads when the file changes.
- `tests/unit/test_dialog_boundaries.py` (existing) keeps `New Script…` and
  the editor failure inside `Feedback`.

## 10. Out of scope

- An in-Trigger code editor. Editing is external by decision 4.
- Static import analysis to reorder actions. Order is the rigger's statement
  of dependency.
- An entry-point convention (`def main(ctx)`). A file may define one and the
  inline code may call it; nothing requires it.
- A per-step isolation lifetime.
- An editor-picker dialog. `external_editor` is a settings key.
