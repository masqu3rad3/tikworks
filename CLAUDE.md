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
- **Status:** Phase 4 Session Management complete (April 2026)
- **Key influences:** tik_manager4 UI patterns, labelmatic config/core separation
- **Current implementation:** Core foundation + actions + modules + session management

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

## tik.trigger Structure Plan

The tik.trigger structural organization plan is stored in:
- `AI/tik_trigger_plan.md` — Full architectural plan

Key decisions:
- **Folder-per-action/module** with named `.py` files (e.g., `bipedArm/bipedArm.py`)
- **Registry decorators** for explicit plugin registration
- **Folder-based discovery** scanning subdirectories
- **JSON configs** for UI definitions and defaults
- **Dataclasses** for typed session data (`core/schemas.py`)
- **DCC-agnostic core** — `core/` imports no Maya modules
- **Session management** — GuideSession and ActionSession for save/load workflows

## tik.trigger Tests

Tests for tik.trigger follow naming convention `test_<module>_trigger.py`:
- `tests/unit/test_exceptions_trigger.py` — Exception hierarchy tests
- `tests/unit/test_registry_trigger.py` — Registry and decorator tests
- `tests/unit/test_schemas_trigger.py` — Dataclass tests
- `tests/unit/test_action_core_trigger.py` — ActionCore base class tests
- `tests/unit/test_module_core_trigger.py` — ModuleCore/GuidesCore tests
- `tests/unit/test_session_trigger.py` — Session management tests

## Getting Help

- Use `/skill` to invoke relevant skills
- Agent definitions are in `.github/agents/`
- Project-specific skills are in `AI/`
