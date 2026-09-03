# Splitting the pipeline into Build and Publish

**Date:** 2026-09-03
**Status:** Design approved, ready for an implementation plan
**Area:** `tik.trigger` — session document, runner, `Session` API, pipeline UI

## 1. The problem

In the previous Trigger, and in the current one, publishing is a single
post-process attached to the whole system: one implicit method that runs after
the rig is built. That has one virtue — you can build freely without producing
stray publishes — and two costs. There can be only one publish methodology per
workflow, and it is implicit: nowhere in the session can a TD read what
publishing will do. Because it is not made of actions, it cannot be composed.
Exporting an FBX, exporting a Maya file and publishing a rig cannot be chained,
reordered, individually disabled, or given settings.

The fix is to keep the guarantee (building never publishes) while making
publishing ordinary, inspectable, composable actions. The session grows a second
action list. `Build` runs the first; `Build & Publish` runs both.

## 2. Decisions

Five decisions were settled during design; the rest of this document follows
from them.

1. **Two commands, not three.** `Build` and `Build & Publish`. There is no
   publish-only command. The publish list is always the tail of a fresh build,
   so a publish action is guaranteed to see a scene the build just produced.
   This removes any need for a "was this scene built from this session?" stamp.
2. **Publish belongs to the top-level session.** A `reference` contributes build
   actions only; the referenced document's publish list is ignored at any depth.
   The hero rig decides what gets exported; the base rig it consumes does not.
3. **Action types declare their scope.** `@register_action(..., scope=...)` with
   `"build"` (the default), `"publish"` or `"both"`. The shelf, the palette, the
   drop handler and `Session.add()` honour it.
4. **Exactly two lists, named `build` and `publish`.** Not a generic N-phase
   registry. Two named things the runner, the UI and the docs can all reason
   about. A third phase later is a schema bump, which is a cheap, honest cost.
5. **Publish actions are never individually runnable.** No double-click-to-run,
   no "Run this step", no `until` in the publish list. The single entry point
   is `Build & Publish`.

Decision 5 gives the system its central invariant:

> **A publish action executes only as the tail of a full, clean build.**
> No partial or hand-edited rig can ever produce a published artifact.

## 3. Data model

`core/document.py` gains one sibling list and a phase vocabulary.

```python
BUILD = "build"
PUBLISH = "publish"
PHASES = (BUILD, PUBLISH)

SCHEMA_VERSION = 6          # was 5

@dataclass
class Document:
    schema: int = SCHEMA_VERSION
    meta: dict = field(default_factory=dict)
    actions: list[ActionNode] = field(default_factory=list)   # the build list
    publish: list[ActionNode] = field(default_factory=list)   # new
    guides: GuideDocument = field(default_factory=GuideDocument)
```

`actions` keeps its name and its meaning. That is deliberate: every existing
`.tr`, every stored reference override keyed by action path, and every action
path in user scripts stays valid. `from_dict` already accepts older schemas and
rejects only newer ones, so a schema-5 file loads with an empty publish list and
needs no migration step.

### Phase-aware tree operations

`ActionNode` is unchanged — the publish list is a tree of the same nodes, so
nesting and grouping come for free.

Every `Document` tree method takes `phase: str = BUILD` and resolves its root
through one new private helper:

```python
def _roots(self, phase: str = BUILD) -> list[ActionNode]:
    if phase == BUILD:
        return self.actions
    if phase == PUBLISH:
        return self.publish
    raise SessionError(f"Unknown phase '{phase}'.")
```

The methods that widen: `walk`, `paths`, `find`, `require`, `parent_of`,
`siblings`, `path_of`, `unique_name`, `add`, `remove`, `move`, `rename`,
`duplicate`. Each replaces its `self.actions` root lookup with
`self._roots(phase)`. One implementation serves two lists; no tree logic is
duplicated.

### Paths are per-phase and unprefixed

`export_fbx` in the publish list and `export_fbx` in the build list are
different actions, and neither collides, because the phase is always an explicit
argument rather than a path segment. This is what preserves compatibility with
stored reference overrides, which are keyed by bare path.

`move()` refuses to cross phases and raises `SessionError`. A cross-phase move
is a remove followed by an add — which is exactly what the UI's drag performs.

## 4. Runner and run semantics

`core/steps.py`: `Step` gains `phase: str = BUILD`, so logs, the UI status map
and error messages can attribute a failing step to its list.

`maya/runner.py`:

```python
def plan(self, document, base_dir="", until=None, only=None, phase=BUILD) -> Plan
def run(self, document, base_dir="", until=None, only=None,
        reset_scene=True, session=None, publish=False) -> list[StepResult]
```

### Order of operations

- **Build** — `new_scene()`, then the build plan. Behaviour is unchanged.
- **Build & Publish** — `new_scene()`, the build plan, then the publish plan
  **in the same scene, with no second reset**. It is one continuous run. The
  progress total is `len(build steps) + len(publish steps)`, so the operation
  reads as one thing to the user, not two.

### Failure

A failing publish step aborts the run exactly as a build step does: the same
`ActionExecutionError`, the same per-step undo chunk, the same pre-flight
`validate()`. The error text names the phase, so "which list did this come
from?" is never a guess.

### `until` is build-only

`until` is a debugging tool for the build list. When it is set, **publish never
runs** — a partial build is not a rig anyone should be exporting.
`Session.build(until=..., publish=True)` raises `SessionError` rather than
silently dropping the publish half.

### References contribute build actions only

`_collect_reference` expands the referenced document's `actions` and ignores its
`publish` entirely, at any depth of nesting. The `reference` action itself stays
`scope="build"`, so it cannot be placed in a publish list where its meaning
would be ambiguous — a reference in the publish list would expand another
session's *build* actions into a publish run, which is nonsense.

### No build stamp

Because publish is always the tail of a fresh build, the scene a publish action
sees was, by construction, produced by the build that just ran. There is nothing
to verify and no stamp to write.

## 5. Action scope

The phase constants (`BUILD`, `PUBLISH`, `PHASES`) live in `core/document.py`
and are re-exported from `core/__init__.py`. `core/registry.py` imports them
from there; `document.py` does not import `registry`, so there is no cycle.

`core/registry.py`:

```python
def register_action(name, category="utility", icon="", scope=BUILD): ...
```

`scope` is one of `"build"`, `"publish"`, `"both"`. It is stamped onto the class
alongside `category` and `icon`, and `Action` declares `scope: str = "build"` as
a class attribute so an unregistered subclass still answers the question.

The default of `"build"` means the four existing actions — `import_asset`,
`kinematics`, `reference`, `script` — keep working with no edit. `script` moves
to `scope="both"` (see section 8).

Two registry additions:

```python
def iter_actions(scope: Optional[str] = None) -> list[type]
def allows(action_type: str, phase: str) -> bool
```

`iter_actions("publish")` returns actions declaring `"publish"` or `"both"`.
`allows()` is the single place the rule lives, and has exactly three callers:

- the tile shelf and Tab palette, building their entry lists for the focused
  phase;
- `PipelineModel.dropMimeData`, rejecting a cross-phase drag of an incompatible
  action;
- `Session.add()`, raising `SessionError` rather than letting the Python API
  write an invalid document.

**Scope is a placement rule, not a runtime one.** The runner never checks it. A
`.tr` hand-edited into an odd state still runs and reports what it did;
`validate()` surfaces the mismatch as a problem row.

## 6. Session API

`Session` keeps its entire current surface pointing at the build list.
`session.actions`, `session[path]`, `session.add(...)`, `session.walk()` and
`session.build()` all mean exactly what they mean today.

The publish list arrives as a namespace object rather than a parallel set of
methods:

```python
rig = trigger.Session.open("hero.tr")

rig.add("kinematics")                              # build list, unchanged
rig.publish.add("script", file="export_fbx.py")
rig.publish["script"].enabled = False

rig.build()                                        # build only
rig.build(publish=True)                            # build, then publish
```

`session.publish` is a thin `PhaseView` holding `(session, phase)` and exposing
the same tree verbs — `.actions`, `[path]`, `.add`, `.remove`, `.move`,
`.rename`, `.duplicate`, `.walk`, `.paths`. It delegates to `Document`'s
phase-aware methods and calls `session.touch()`, so undo, the dirty flag and the
reference cache behave identically in both lists. `ActionHandle` gains a `phase`
attribute so a handle knows which list it came from.

`session.publish` reads as a noun, which is safe precisely because decision 1
means there is no `publish()` verb to collide with.

### Changed signatures

| Method | Change |
|---|---|
| `build(until=None, reset_scene=True, publish=False)` | `publish=True` appends the publish phase; combined with `until` it raises |
| `validate()` | Checks both lists; publish problems are prefixed with their phase |
| `steps(until=None, phase=BUILD)` | Reports one list at a time |
| `add(...)` | Raises `SessionError` when the action's scope forbids the target phase |
| `run(path)` | Unchanged, and **build-only**: raises `SessionError` on a publish path |

`capture_guides()` is called once at the start of `build()`, as today. Publish
adds no guide handling of its own.

## 7. UI

`ui/session_view.py` — the pipeline pane becomes a vertical `QSplitter` holding
two `PipelineTree`s, each backed by its own `PipelineModel(session, phase=...)`:
build on top under a `BUILD` header, publish below under a collapsible `PUBLISH`
one, sized roughly 3:1.

```
┌─ PIPELINE ─────────────────┐
│ BUILD                      │
│  ▸ import_asset            │
│  ▸ reference  baseRig.tr   │
│  ▸ kinematics              │
│  ▸ script  fixes.py        │
├────────────────────────────┤
│ PUBLISH                    │
│  ▸ export_fbx              │
│  ▸ export_maya             │
└────────────────────────────┘
```

Two models rather than one keeps the existing per-row status map, drag-and-drop
and rebuild logic untouched; each simply resolves its root through the phase it
was given.

**Focus drives context.** `SessionView` tracks which tree last had focus. The
properties panel edits that tree's current row, and the tile shelf and Tab
palette rebuild their entries from `registry.iter_actions(scope=...)` for that
phase — standing in the publish list, you are only offered actions that belong
there. `current_path()` returns a `(phase, path)` pair.

**Dragging** between the trees is a remove-and-add across phases.
`dropMimeData` calls `registry.allows()` and refuses an incompatible action in
either direction.

**Publish rows carry no run affordance.** No double-click-to-run, no "Run this
step" or "Build until here" in the context menu, and the settings panel hides
its run buttons when the current row is a publish row. `save_from_scene` is
untouched and naturally inert for publish actions, whose base implementation
returns no side files.

**The build bar** keeps `Build rig` and `Build until here` — the latter disabled
while the publish tree has focus, since `until` is build-only — and finally
wires `Build && Publish` to `session.build(publish=True)`, dropping the
`setEnabled(False)` and the "Publishing is not wired yet" tooltip at
`ui/session_view.py:194-196`. One progress bar spans both phases.

`ui/main.py` — the Session menu gains **Build & Publish** (`Ctrl+Shift+P`)
beside Build Rig (`Ctrl+B`) and Build Until Here (`Ctrl+Shift+B`).

### Event plumbing

`STEP_STARTED` / `STEP_FINISHED` / `STEP_FAILED` currently carry only `path`,
which is ambiguous across two lists. They gain a `phase` field, and
`SessionView._step` routes each status to the matching model.

## 8. Scope of this spec

This spec delivers the **mechanism**: the split lists, the scope rule, the run
semantics, the API and the UI. It ships no new exporters.

What makes the publish list usable and testable on day one is widening `script`
to `scope="both"`, so a post-build Python step works immediately. Concrete
`export_fbx`, `export_maya` and `publish_rig` actions are a follow-up spec —
each a small, independent piece once this exists.

## 9. Testing

Following the `test_<module>_trigger.py` convention:

- **`tests/unit/test_document_trigger.py`** — phase-aware tree operations;
  schema-6 round-trip; an existing schema-5 file loading with an empty publish
  list; `move()` refusing to cross phases; same-named actions coexisting in both
  lists without collision.
- **`tests/unit/test_runner_trigger.py`** — a plan per phase; a reference
  contributing build actions only and never its publish list, including at
  depth; build steps preceding publish steps in one run with a single
  `new_scene()`; `until` combined with `publish=True` raising; a failing publish
  step aborting with the phase in its message.
- **`tests/unit/test_session_trigger.py`** — the `session.publish` namespace;
  undo and the dirty flag spanning both lists; `add()` rejecting an
  out-of-scope action; `run()` raising on a publish path.
- **`tests/unit/test_core_trigger.py`** — `register_action(scope=...)` stamping;
  `iter_actions(scope=)` filtering; `allows()`.
- **`tests/ui/`** — both trees present; shelf refilter on focus change;
  cross-phase drop rejected; publish rows offering no run action;
  `Build && Publish` enabled and calling `build(publish=True)`.
- **`tests/integration/trigger/`** — one case running a real build-and-publish
  against Maya and asserting order and single-reset.

`tests/helpers/` gains a toy publish-scoped action, so the pure tests never need
a real exporter.

## 10. Files touched

| File | Change |
|---|---|
| `core/document.py` | `publish` list, phase constants, `_roots()`, phase-aware tree methods, schema 6 |
| `core/steps.py` | `Step.phase` |
| `core/registry.py` | `scope` on `register_action`, `iter_actions(scope=)`, `allows()` |
| `core/action.py` | `Action.scope` class attribute |
| `maya/runner.py` | `phase` on `plan`, `publish` on `run`, phase on step events |
| `session.py` | `PhaseView`, `session.publish`, widened `build`/`validate`/`steps`/`add`/`run`, `ActionHandle.phase` |
| `actions/script/script.py` | `scope="both"` |
| `ui/session_view.py` | Split pipeline pane, two models, focus tracking, wired Build && Publish |
| `ui/model.py` | `phase` on `PipelineModel`, scope check in `dropMimeData` |
| `ui/settings_panel.py` | Hide run buttons for publish rows |
| `ui/shelf.py` | Refilter entries by focused phase |
| `ui/main.py` | Build & Publish menu entry and shortcut |
| `CLAUDE.md` | `.tr` schema 5 → 6; the two-list pipeline in the tik.trigger section |

