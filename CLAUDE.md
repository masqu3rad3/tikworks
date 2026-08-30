# CLAUDE.md — TikWorks Project Context

This file provides project-level context to Claude Code when working in this repository.

## Repository Overview

**TikWorks** is a multi-tool repository centered around Maya automation and rigging.

- **Primary DCC:** Autodesk Maya 2024+
- **Python:** 3.10+

## Key Projects

### tik.maya
Maya API wrapper that "feels like Python, behaves like Maya."
- **Location:** `src/python/tik/maya/`
- **Architecture:** Types / Roles / Constructs separation

### tik.trigger (IN DEVELOPMENT)
Next-generation rigging framework built on tik.maya.
- **Location:** `src/python/tik/trigger/`
- **Status (August 2026):** workflow v2 — the `.tr` session is the rig (nested actions, references with overrides, runner), guides are a `.trg` asset, `Session`/`GuideScene` TD handlers, pipeline UI on the official theme, Guide Designer as a mode tab of that UI (tear-off supported) with two-way binding. Modules `base`/`fkchain`/`arm`; actions `import_asset`/`kinematics`/`script`/`reference`. Maya-only since the 2026-08-30 simplification pass.
- **Design specs:** `docs/superpowers/specs/2026-08-30-trigger-simplification-design.md` (layering and the `rig` object, authoritative), `2026-08-30-designer-as-mode-tab-design.md` (the UI shell: modes, menus, tear-off), `2026-08-29-trigger-ui-v3-and-io-graph-design.md` (module I/O model), `2026-08-28-trigger-workflow-and-ui-design.md` (session blueprint), `2026-08-28-trigger-rebuild-design.md` (tik.maya constructs, fields); plans in `docs/superpowers/plans/`
- **Layering rule:** `tik/trigger/core` is pure Python — no Maya, no Qt (enforced by `tests/unit/test_import_boundaries.py`). Everything else in tik.trigger may use tik.maya.

## Important Patterns

### tik.maya Architecture
- **Types:** Describe what a node is (Transform, Mesh)
- **Roles:** Describe what a node means (Controller, SpaceSwitcher)
- **Constructs:** Orchestrate multiple nodes/roles

### The Animator-Opinion Rule (governs the tik.maya / tik.trigger split)
If an average animator can understand it and might have an opinion about it, it
belongs to **tik.trigger**, not tik.maya. tik.maya owns *mechanism* (which nodes,
wired how); tik.trigger owns *policy* (what the rig is). A tik.maya construct
never creates a controller, names a user-facing attribute, or encodes a side
convention. Layers: `nodes → types → roles → constructs → systems → modules`.
**Modules never inherit from other modules** — shared behaviour goes in
`tik/trigger/systems/`.

### Module Ground Rules
Four groups per module (`socket` / `control` / `rig` / `bind`); two skeletons
(puppet in `rig_grp`, engine-neutral deform skeleton in `bind_grp` with **live
TRS** for baking/export); one bind hierarchy per rig, built in final position via
`rig.bind_parent`, never reparented. A **socket per declared input** is created
for you in `socket_grp` — declaring the input is what makes it. Controllers come
with their offset group (`ctrl.offset`). Full text in `AI/coding_rules.md`.

### The `rig` object
`rig` owns naming, tagging, group placement and registration; tik.maya owns the
mechanism. A helper belongs on `rig` only when it removes naming, tagging,
placement or registration boilerplate — which is why module code still says
`tm.MatrixConstraint.create(...)` outright. Note `Controller` proxies attribute
and plug *reads* to its transform, but not writes: assignments and type-checked
tik.maya APIs take `ctrl.transform`.

### Decorators for Maya Context
Maya-specific decorators (`@undo`, `@keepselection`, `@keepframe`) live in tik.maya, not in tik.trigger.

### Registry Pattern
Actions and modules in tik.trigger use explicit `@register_action` / `@register_module` decorators for discovery.

## Development Guidelines

See `AGENTS.md` for detailed agent and developer guidance.

### Quick Rules
1. **Consume tik.maya** — Don't call `cmds` or `OpenMaya` directly in tools
2. **Source of Truth** — Maya scene state is always authoritative
3. **Testing** — All tests run via `pytest` under Maya standalone (`mayapy`)
4. **No third-party deps** — Stick to stdlib and Maya-bundled modules

## Key Files

| File | Purpose |
|------|---------|
| `AGENTS.md` | Agent definitions and behavior guidelines |
| `AI/coding_rules.md` | Python/Maya coding standards |
| `AI/system_prompt.md` | System-level instructions |
| `.github/copilot-instructions.md` | Legacy Copilot instructions |

## tik.trigger Structure

Authoritative design: `docs/superpowers/specs/2026-08-28-trigger-rebuild-design.md`
(`AI/tik_trigger_plan.md` is the superseded first draft).

Key decisions:
- **Declarative modules** — manifest (`GuideLayout`, `Input`s, `outputs`, typed `Field`s) + `draw_guides(guides)` / `build(rig)`
- **Python fields are the schema** (`tik.core.fields`); optional `defaults.json` overrides defaults only; UI is generated (`tik.shared.ui.fields.FormBuilder`)
- **Scene is the truth** — guides are joints tagged via `node.meta` (`trg_*` keys); identity is a uuid, never a name
- **Maya-only** — there is no backend protocol. `tik/trigger/maya` (rig, build, runner, tags) and `tik/trigger/guides` (scene, nodes) hold the scene code; `core` stays pure
- **Folder-per-module/action** with named `.py` files and `@register_module` / `@register_action`
- **One session document** (`.trg`): guide snapshot + ordered actions

## tik.trigger Tests

Tests for tik.trigger follow naming convention `test_<module>_trigger.py`:
- `tests/unit/test_core_trigger.py` — manifest, Module, registry, schemas
- `tests/unit/test_document_trigger.py`, `test_runner_trigger.py`, `test_session_trigger.py` — session document, runner/references, Session API
- `tests/unit/test_guides_trigger.py` — .trg format + GuideScene (Maya)
- `tests/unit/test_guide_scene_trigger.py` — GuideScene, ModuleRig, build pipeline
- `tests/integration/trigger/test_builder_trigger.py` — the builder against a real scene
- `tests/integration/trigger/` — end-to-end pipeline and arm module
- `tests/ui/` — Qt UI (run with `TIK_TESTS_NO_MAYA=1`, `QT_QPA_PLATFORM=offscreen`; `make tests-ui`)
- There are no fake backends: build tests run against Maya. `tests/helpers/toy_modules.py` holds throwaway modules; `tests/ui/stub.py` is a Qt-only `GuideScene` stand-in (Maya standalone cannot host a QApplication)

## Getting Help

- Use `/skill` to invoke relevant skills
- Agent definitions are in `.github/agents/`
- Project-specific skills are in `AI/`
