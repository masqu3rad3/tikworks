# Plan F — UI v3 and Module I/O Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Trigger UI to the approved mockup quality (dockable tool windows, menus, status bars, refined rows, reflowing shelf, Nuke-style versioned fields) and replace attachment with explicit module inputs/outputs stored in the guides file, edited through tree and node-graph views.

**Spec:** `docs/superpowers/specs/2026-08-29-trigger-ui-v3-and-io-graph-design.md`

## Tasks

- [ ] **Task 1 — UI kit + Trigger window.** `tik/shared/ui/{maya_window,scene_watcher,collapsible,versioned_field,tile_grid,status}.py`, theme additions; `FormBuilder` uses `VersionedFileField` and `FieldCaption` group headers; `tik/trigger/ui/main.py` (MayaToolWindow, File/Edit/Session/Tools/Help, status bar, single instance), `session_view.py` (splitter: tile pane | pipeline | properties), `delegates.py` (earlier row treatment + gutter status dot, muted-tint selection), session undo/redo. Tests: `tests/ui/test_ui_kit.py`, updated `test_pipeline_ui.py`.
- [ ] **Task 2 — I/O model.** `core/manifest.py` `Input`; `Module.inputs/outputs`; `ModuleInstance.inputs`; `.trg` wrapped format with `connections` (+ list form accepted); Maya backend: `trg_inputs` meta, `ctx.output()/ctx.attach()`, connect pass (module outputs or scene nodes; errors), legacy derivation from guide DAG; `Guides.connect/disconnect`, `GuideHandle.inputs/outputs`. Modules base/fkchain/arm updated. Tests: unit (fake) + Maya + integration.
- [ ] **Task 3 — Guide Designer v3.** MayaToolWindow with menus; panes [modules | tree | graph | properties] (tree/graph collapsible); `graph_view.py` (QGraphicsView nodes/ports/wires, external nodes, drag-connect, delete wire); Inputs group in properties; SceneWatcher; pre-fill primary input on create; drag-parent writes primary input. Tests offscreen with the fake backend.
- [ ] **Task 4 — API, docs, screenshots.** `Guides.connect`, docs page, CLAUDE.md/memory, offscreen renders, artifact.
