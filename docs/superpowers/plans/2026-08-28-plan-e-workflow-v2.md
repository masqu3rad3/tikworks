# Plan E — Trigger Workflow v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the session the rig: nested action documents, a runner with reference expansion and overrides, the TD `Session` handler, `.trg`-compatible guides, a pipeline-centric Qt UI on the official theme, and a Guide Designer with two-way Maya binding.

**Architecture:** `tik.trigger.core.document` (tree of `ActionNode`), `core.runner` (plan → steps → run with events), `core.versioning`, `tik.trigger.handler.Session/ActionHandle` (public API), `tik.trigger.guides` (`.trg` I/O + live-scene handler), `tik.trigger.ui` rebuilt (theme, pipeline window, shelf, palette, reference rows, Guide Designer), `tik.shared.ui.binding` ported from creature_kit.

**Spec:** `docs/superpowers/specs/2026-08-28-trigger-workflow-and-ui-design.md`

## Global Constraints

- core/handler import no Maya/Qt (boundary test); UI imports no Maya directly (backend hooks only).
- `.trg` stays the old joint-list format (real sample in `tests/data/crabMonster_guides_v001.trg`); old flat `.tr` converts on load (`tests/data/crabMonster_main_session_v002.tr`).
- Paths stored relative to the session file when possible.
- Tests: mayapy 2026 for `tests/unit` + `tests/integration/trigger`; `TIK_TESTS_NO_MAYA=1` for `tests/ui`.

---

### Task 1 ✅: Document, versioning, runner, reference, Session handler (core, no UI)

**Files:** `tik/core/fields.py` (+`FileField`, `DictField`), `tik/trigger/core/document.py`, `core/versioning.py`, `core/runner.py`, `core/action.py` (category/icon/validate/save_from_scene, `ActionContext.resolve`), `core/registry.py` (`register_action(name, category, icon)`), `tik/trigger/actions/reference/reference.py`, `tik/trigger/handler.py`, `tik/trigger/__init__.py`.

**Produces:**
```python
ActionNode(name, type, enabled=True, settings={}, children=[]); .to_dict()/.from_dict()
Document(schema=4, meta={}, actions=[]); .load(path)/.save(path); .walk() -> (path, node, parent); .find(path); .add(node, parent=None, index=None); .remove(path); .move(path, parent=None, index=None); .rename(path, new); .unique_name(parent_path, base)
versioning.parse(path)->(stem, version|None, suffix); next_version(path); latest_version(path); with_version(path, n)
Runner(backend, events).plan(document, base_dir, until=None, only=None) -> list[Step(path, node, base_dir, chain)]
Runner.run(document, base_dir, until=None, only=None, reset_scene=True) -> list[StepResult(path, status, seconds, error)]
Reference: type "reference", settings file/version/include/overrides; Reference.expand(node, base_dir, loader, chain) -> (Document, base_dir)
Session(backend=None, file_path=None): open(), add(), __getitem__, actions, remove/move/rename/duplicate, build(), run(), save(), increment(), is_modified, directory, validate()
ActionHandle: name/type/path/enabled/settings/children, add(), __getitem__, field attrs, is_linked, reset(field)
```
Tests: `tests/unit/test_document_trigger.py`, `test_runner_trigger.py`, `test_handler_trigger.py` (fake backend + toy actions).

### Task 2 ✅: Guides (`.trg` compatible) + kinematics on files

**Files:** `tik/trigger/guides/format.py` (`GuideFile`), `guides/handler.py` (`Guides`), `backends/maya` (guide joints carry old attrs `moduleName`, `upAxis*`, `useRefOri`, side/type + our meta), `actions/kinematics/kinematics.py` (guides_file/guide_roots/after_build/auto_switchers/selection_sets; master setup), `actions/import_asset` label "Import Model".
Tests: `.trg` roundtrip against the sample; guides handler add/mirror/export/import; kinematics builds from a file in a fresh scene.

### Task 3 ✅: UI — theme, pipeline window, shelf, palette, reference rows

**Files:** `tik/shared/ui/theme/` (theme.qss copy + `apply(widget)`), `tik/trigger/ui/model.py` (`PipelineModel` QAbstractItemModel over `Session`, DnD), `ui/pipeline_view.py`, `ui/shelf.py`, `ui/palette.py`, `ui/settings_panel.py`, `ui/main.py` (tabs = sessions), `ui/icons/` (category glyphs).
Tests (`tests/ui`): model tree/DnD/nesting, palette filter/insert, linked rows + override edit, run status colouring from events.

### Task 4 ✅: Guide Designer + binding

**Files:** `tik/shared/ui/binding.py`, `tik/trigger/ui/guide_designer.py` (module tiles + palette, side control, tree with drag-parenting, bound properties, Import/Export/Test build), backend `SceneObserver`.
Tests: designer with fake guides handler; binding with fake plugs.

### Task 5 ✅: Remove v1 pieces, docs, verification

Remove `session/` package (RigSession), scene-scope kinematics, old panels; update docs, CLAUDE.md, memory; full suites green; commit.
