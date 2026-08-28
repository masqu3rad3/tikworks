# Plan D — Minimal Trigger UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A functional Qt window for Trigger: guides tab (module palette, instance tree, generated property editor, build) and actions tab (pipeline list, generated editor, run/run-until/run-all), file menu, progress + log driven by the core event bus.

**Architecture:** `tik.shared.ui.fields.FormBuilder` generates editors from `tik.core.fields` schemas (reusable by any tool). `tik.trigger.ui` composes it with `RigSession`/`Builder`; no Qt in core, no Maya in the UI (backend hooks `selected_guide`, `select_guides`, `selected_node_name`).

**Spec:** `docs/superpowers/specs/2026-08-28-trigger-rebuild-design.md` §8

## Tasks

- [x] **Task 1:** `tik/shared/ui/Qt.py` shim (fixes `feedback.py`/`qtmaya.py` imports), `tik/shared/ui/fields.py` `FormBuilder` (int/float/bool/string/choice/vector/list/node widgets, groups, hidden, validation error → revert + `error` signal, `changed` signal, `node_picker`).
- [x] **Task 2:** `tik/trigger/ui/`: `widgets.py` (LogWidget, NameEdit), `guides_panel.py`, `actions_panel.py`, `main.py` (`TriggerWindow`), `__init__.py` (`show()` for Maya).
- [x] **Task 3:** Maya backend UI hooks: `selected_guide()`, `select_guides()`, `selected_node_name()`.
- [x] **Task 4:** Tests: `tests/ui/` (no Maya, offscreen Qt): `test_form_builder.py`, `test_trigger_window.py`; `tests/helpers/trigger_fakes.py` shared fakes; `make tests-ui` target; conftest `TIK_TESTS_NO_MAYA`.
- [x] **Task 5:** All suites green; commit `feat(tik.trigger): minimal Qt UI`.

Later (UI polish spec): node-graph view of module attachments, live validation, guide mirroring tools, recent files, icons.
