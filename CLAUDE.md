# CLAUDE.md — TikWorks Project Context

This file provides project-level context to Claude Code when working in this repository.

## Repository Overview

**TikWorks** is a multi-tool repository centered around Maya automation and rigging.

- **Location:** `D:/dev/tikworks/`
- **Primary DCC:** Autodesk Maya 2024+
- **Python:** 3.10+

## Project Structure

```
tikworks/
├── src/python/
│   ├── tik/
│   │   ├── maya/              # tik.maya - Maya cmds/API wrapper
│   │   ├── core/               # tik.core - Shared utilities
│   │   ├── shared/             # tik.shared - Cross-DCC utilities
│   │   ├── trigger/            # tik.trigger - Rigging framework (NEXT GEN)
│   │   └── vendor/             # Vendored dependencies (Qt shim, etc.)
│   └── tools/                  # Standalone tools
├── tests/                      # pytest test suite
├── docs/                       # Sphinx documentation
└── .github/                    # GitHub config, agents, workflows
```

## Key Projects

### tik.maya
Maya API wrapper that "feels like Python, behaves like Maya."
- **Location:** `src/python/tik/maya/`
- **Architecture:** Types / Roles / Constructs separation
- **Key modules:** `core/`, `types/`, `roles/`, `constructs/`

### tik.trigger (IN DEVELOPMENT)
Next-generation rigging framework built on tik.maya.
- **Location:** `src/python/tik/trigger/`
- **Status (August 2026):** workflow v2 — the `.tr` session is the rig (nested actions, references with overrides, runner), guides are a `.trg` asset (old format kept), `Session`/`Guides` TD handlers, pipeline UI on the official theme, Guide Designer with two-way binding. Modules `base`/`fkchain`/`arm`; actions `import_asset`/`kinematics`/`script`/`reference`.
- **Design specs:** `docs/superpowers/specs/2026-08-29-trigger-ui-v3-and-io-graph-design.md` (UI v3 + module I/O, authoritative), `2026-08-28-trigger-workflow-and-ui-design.md` (session blueprint), `2026-08-28-trigger-rebuild-design.md` (tik.maya constructs, fields); plans A-F in `docs/superpowers/plans/`
- **Layering rule:** `tik/trigger/core` and `session` import no Maya/Qt (enforced by `tests/unit/test_import_boundaries.py`)

## Important Patterns

### tik.maya Architecture
- **Types:** Describe what a node is (Transform, Mesh)
- **Roles:** Describe what a node means (Controller, SpaceSwitcher)
- **Constructs:** Orchestrate multiple nodes/roles

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
- **Declarative modules** — manifest (`Guides`, `plugs`, `sockets`, typed `Field`s) + `draw_guides(ctx)` / `build(ctx)`
- **Python fields are the schema** (`tik.core.fields`); optional `defaults.json` overrides defaults only; UI is generated (`tik.shared.ui.fields.FormBuilder`)
- **Scene is the truth** — guides are joints tagged via `node.meta` (`trg_*` keys); identity is a uuid, never a name
- **Backend boundary** — `tik/trigger/backends/maya` is the only Maya-touching layer besides module/action bodies
- **Folder-per-module/action** with named `.py` files and `@register_module` / `@register_action`
- **One session document** (`.trg`): guide snapshot + ordered actions

## tik.trigger Tests

Tests for tik.trigger follow naming convention `test_<module>_trigger.py`:
- `tests/unit/test_core_trigger.py` — manifest, Module, registry, schemas, Builder (fake backend)
- `tests/unit/test_document_trigger.py`, `test_runner_trigger.py`, `test_handler_trigger.py` — session document, runner/references, Session API (fake backend)
- `tests/unit/test_guides_trigger.py` — .trg format + Guides handler (Maya)
- `tests/unit/test_maya_backend_trigger.py` — Maya backend, contexts, build pipeline
- `tests/integration/trigger/` — end-to-end pipeline and arm module
- `tests/ui/` — Qt UI (run with `TIK_TESTS_NO_MAYA=1`, `QT_QPA_PLATFORM=offscreen`; `make tests-ui`)
- Shared fakes live in `tests/helpers/trigger_fakes.py`

## Getting Help

- Use `/skill` to invoke relevant skills
- Agent definitions are in `.github/agents/`
- Project-specific skills are in `AI/`
