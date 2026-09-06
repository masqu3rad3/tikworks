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
- **Status (August 2026):** workflow v3 — the `.tr` session is the rig *and its guides* (nested actions, references with overrides, runner), `Session`/`GuideScene` TD handlers, pipeline UI on the official theme, one menu bar over the session tabs, each session holding Session and Guide Designer sub-tabs, with two-way binding. `.trg` is an import/export format for guide libraries, not the master. Modules `base`/`fkchain`/`arm`/`twist`/`ribbon`; systems `limb`/`limb_lock`/`reach`/`twist`; actions `import_asset`/`kinematics`/`script`/`reference`. A `kinematics` action builds **only the modules it explicitly names** (instance uuids); an empty list is an error, and its draw and afterlife are scoped to that list, so a rig can be split across several passes with other actions between them. The pipeline is split in two: a **build** list and a **publish** list. `Build` runs the first; `Build & Publish` runs both in one continuous run with a single scene reset. Publish actions are never individually runnable, and a `reference` contributes build actions only. Maya-only since the 2026-08-30 simplification pass. Modules may declare `guide_attrs` for per-guide authored data, authored on the joint and captured into the document. Since the 2026-09-05 pass the guides move in two explicitly named directions — **Draw** (session into the scene, manual) and **Sync** (scene into the session, `Auto` or on demand) — sitting at opposite ends of the Designer's bar. Since the 2026-09-06 pass the `script` action loads files as **named modules** (`import_as`, default the file stem) into a per-run `trigger_build` namespace with a `lifetime` of `build` or `maya`; inline code sees every alias and `ctx`. Editing is external; `New Script…` writes a versioned stub into `scripts/`; the Script dock is a read-only viewer. Since the 2026-09-06 preferences pass, user settings live in `tik/shared/prefs` (a JSON store under `~/TikWorks`, declarative pages built on `tik.core.fields.Schema`, a page registry) and are edited from **File > Settings…** (`Ctrl+,`). Adding a setting is one field line in `tik/trigger/config/pages/`. **A preference can never change a rig**: the build path may not import the preferences packages at all, enforced by `tests/unit/test_import_boundaries.py`. Opaque Qt geometry blobs stay in `QSettings`; everything a human might edit is in the JSON.
- **Design specs:** `docs/superpowers/specs/2026-09-06-settings-and-preferences-design.md` (the preferences system: the shared spine, the guarantee and its enforcement, the dialog and its cross-page search), `2026-09-06-script-action-libraries-design.md` (the script action as a library loader: `ScriptSpace`, the `lifetime` tiers, external editing, stubs, the viewer dock), `2026-09-05-rig-scaffold-and-master-controls-design.md` (the fixed rig scaffold, the preferences and visibilities controls, control tiers), `2026-09-05-draw-and-sync-separation-design.md` (**authoritative for anything touching guides**: Draw vs Sync, the state model, the action bar, the tree and graph markers), `2026-09-03-build-publish-split-design.md` (the build/publish split — the second action list, action `scope`, and the run semantics), `2026-09-01-optional-sync-and-snapshot-design.md` (optional sync, the scope-split action bar, the `trg_entry` breadcrumb and Snapshot From Scene — **amends the guide-ownership spec's sections 5 and 6**), `2026-08-31-guide-ownership-and-lockstep-design.md` (the guide document, capture/regenerate/reconcile, guides in the session — superseded on Draw/Sync by the 2026-09-05 spec), `2026-08-31-field-groups-and-vectors-design.md` (FieldGroup folds, Vector2/Vector3 fields), `2026-08-31-auto-collar-redesign-design.md` (the signed two-axis auto-collar: a neutral guide, off-plane `atan2`, three-point `remapValue`; supersedes the reach spec's Part 4, and note the measured +/-90 ceiling on off-plane angles), `2026-08-31-twist-ribbon-limblock-design.md` (twist extraction, ribbon module, limb lock; note the measured +/-180 bound on matrix-derived twist), `2026-08-30-trigger-simplification-design.md` (layering and the `rig` object, authoritative), `2026-08-29-trigger-ui-v3-and-io-graph-design.md` (module I/O model), `2026-08-28-trigger-workflow-and-ui-design.md` (session blueprint), `2026-08-28-trigger-rebuild-design.md` (tik.maya constructs, fields); plans in `docs/superpowers/plans/`
- **Layering rule:** `tik/trigger/core` is pure Python — no Maya, no Qt (enforced by `tests/unit/test_import_boundaries.py`). Everything else in tik.trigger may use tik.maya.
- **Icons:** every action and module ships `<name>.svg` beside its `.py` (a same-named `.png` wins over it); rules and templates in `AI/icon_rules.md`.

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
with their offset group (`ctrl.offset`) and a **tier**
(`rig.controller(..., tier=)`, default `primary`, tweaks excluded) that the
rig's `visibilities_ctrl` shows or hides per module; rig-wide switches live on
`preferences_ctrl`; both sit in the fixed `rig_grp` > `trigger_grp` scaffold
that `ensure_rig()` guarantees before any build or action (one rig per scene,
no name). A module also declares the
**controllers it builds** — `controls`, or `control_names(settings)` when a
setting drives them, the same shape as `outputs` / `output_names(settings)`.
Every declared control can host an animation space; tweak controllers are
excluded by construction. The manifest must equal what `build()` actually
creates, minus tweaks — `tests/integration/trigger/test_module_ground_rules.py`
enforces it. Full text in `AI/coding_rules.md`.

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
5. **One dialog surface** — Every user dialog goes through
   `tik.shared.ui.feedback.Feedback` (message boxes, file browsers, text
   prompts). Raw `QMessageBox` / `QFileDialog` / `QInputDialog` outside
   `shared/ui/feedback.py` fails `tests/unit/test_dialog_boundaries.py`.
   `feedback.set_browser` lets a pipeline replace file picking repo-wide;
   `feedback.set_handler` lets a headless test answer a message box
6. **Preferences never change the rig** — only `tik/trigger/ui` may read
   preferences (`tik.trigger.config.prefs`). Given the same `.tr`, two artists
   build the same result whatever their settings say;
   `tests/unit/test_import_boundaries.py` enforces it by forbidding
   `trigger/core`, `modules`, `systems`, `maya`, `actions` and `guides` from
   importing the preferences packages at all

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
- **Python fields are the schema** (`tik.core.fields`); optional `defaults.json` overrides defaults only; UI is generated (`tik.shared.ui.fields.FormBuilder`). Fields group with `FieldGroup(label, collapsed=)` and render as folds; `Vector2Field`/`Vector3Field` put a pair or triple on one row
- **The session is the truth; the scene only renders it** — a `GuideDocument` (`core/guide_document.py`) owns which modules exist, their settings, connections, layout, guide poses and guide attrs, all keyed by instance uuid. It lives on the session (`Document.guides`, reached through `Session.guides`), never in the scene: deleting groups or opening a new scene cannot touch it. **Guide joints are a rendering** the document owns and can rebuild. Structural edits undo with Trigger's Ctrl+Z (the session stack); moving a guide undoes with Maya's. Display keys (`L_arm`) appear only at read boundaries, translated fresh so they cannot drift
- **Maya-only** — there is no backend protocol. `tik/trigger/maya` (rig, build, runner, tags) and `tik/trigger/guides` (scene, nodes) hold the scene code; `core` stays pure
- **Folder-per-module/action** with named `.py` files and `@register_module` / `@register_action`
- **Modules can be referenced** from another `.tr`. A pipeline `reference` links the referenced session's modules **by default** (`link_modules`, untick for its actions alone), and the link itself is a `ModuleReference` in the guide document rather than a property of the action -- actions are a sequence, modules are a set, so two references to one file share one link. Resolution inserts borrowed entries into the real `modules` list carrying runtime `origin`/`source`, so every guide-layer read and write works on them unchanged; `to_dict` skips them and emits each link's overrides by **diffing** against the source, which makes an override self-cleaning. Structure is upstream's word -- `enabled=False` leaves a module out, `remove` is refused. In the Designer a borrowed row carries a provenance chip and an override diamond, the properties panel offers *Revert to source*, and **File > Reference Modules...** links (unlinking asks whether to bake the modules in or discard the overrides). A `kinematics` scope is picked from a tick list: a `ListField` with `choices_from` renders as a picker showing display keys and storing ids. In the graph a reference draws as a frame around its modules and collapses to a single node carrying only the connections that cross its boundary (frames have their own document section, since `layout_from_keys` replaces `positions`/`collapse` wholesale on every drag).
- **One session document** (`.tr`, schema 7): guides + two ordered action lists (`actions` is the build list, `publish` the post-build one). The scene is a checkout of exactly one session at a time, stamped on the guide holder (`Session.capture_guides` / `checkout_guides`)
- **Draw and Sync are two directions, and neither does the other's job** — `GuideScene.draw()` renders the session into the scene; `GuideScene.sync()` captures poses and guide attrs back and **can never create, delete or move a joint**. Drawing is manual: nothing draws on open, import or checkout, and a drawn module whose settings change is *flagged*, never rebuilt. The one exception is **creating** a module, which draws it when `draw_on_create` is set (default on) — the rigger just asked for it and it has no joints to disturb. `reconcile` reports three states: `absent` is *not drawn* (normal, never coloured), `missing`/`unexpected`/`parent_wrong`/`key_stale` is *out of date*, `drifted` is *moved*. Orphans and duplicates are reported, never deleted, and never built

## tik.trigger Tests

Tests for tik.trigger follow naming convention `test_<module>_trigger.py`:
- `tests/unit/test_core_trigger.py` — manifest, Module, registry, schemas
- `tests/unit/test_document_trigger.py`, `test_runner_trigger.py`, `test_session_trigger.py` — session document, runner/references, Session API
- `tests/unit/test_guides_trigger.py` — .trg exchange format + GuideScene (Maya)
- `tests/unit/test_guide_document_trigger.py`, `test_reconcile_trigger.py` — the pure document and reconcile (no Maya)
- `tests/unit/test_module_node_trigger.py`, `test_document_store_trigger.py`, `test_snapshot_trigger.py`, `test_capture_trigger.py`, `test_regenerate_trigger.py`
- `tests/unit/test_session_guides_trigger.py` — capture/checkout and the scene stamp
- `tests/unit/test_script_space_trigger.py` — the per-run module namespace, script stubs, `open_external`; `tests/ui/test_script_dock.py` — the Script viewer dock
- `tests/unit/test_prefs_store.py`, `test_prefs_pages.py`, `test_trigger_prefs.py` — the preferences store, pages and registry; `tests/ui/test_prefs_dialog.py` — the dialog and its search; `tests/ui/test_prefs_interface.py`, `test_prefs_files.py`, `test_prefs_guides.py`, `test_autosave.py` — each settings group and the autosave sidecar
- `tests/integration/trigger/test_draw_sync_trigger.py` — the two directions, and that neither crosses into the other
- `tests/unit/test_guide_scene_trigger.py` — GuideScene, ModuleRig, build pipeline
- `tests/integration/trigger/test_builder_trigger.py` — the builder against a real scene
- `tests/integration/trigger/` — end-to-end pipeline and arm module
- `tests/ui/` — Qt UI (run with `TIK_TESTS_NO_MAYA=1`, `QT_QPA_PLATFORM=offscreen`; `make tests-ui`)
- There are no fake backends: build tests run against Maya. `tests/helpers/toy_modules.py` holds throwaway modules; `tests/ui/stub.py` is a Qt-only `GuideScene` stand-in (Maya standalone cannot host a QApplication)

## Getting Help

- Use `/skill` to invoke relevant skills
- Agent definitions are in `.github/agents/`
- Project-specific skills are in `AI/`
