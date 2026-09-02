# System Prompt — TikWorks Claude Code Integration

## Context
This file provides system-level instructions for Claude Code when working in the TikWorks repository.

---

## Project Context

**TikWorks** is a Maya automation and rigging framework repository.

- **Primary DCC:** Maya 2024+ (Python 3.10+)
- **Core Library:** tik.maya — Maya API wrapper
- **Emerging Framework:** tik.trigger — Next-gen rigging framework

### Key Directories
- `src/tik/maya/` — Core Maya wrapper
- `src/tik/trigger/` — Rigging framework (planned)
- `tests/` — Test suite
- `AI/` — Agent definitions and rules

---

## Agent System

TikWorks uses specialized agents defined in `.github/agents/`:
- `tikmaya_api_agent` — Low-level API proposals
- `tikmaya_tools_agent` — Maya tool development
- `tikworks_docs` — Documentation
- `tikworks_linter` — Style enforcement
- `tikworks_tester` — Test authoring

**Invocation:** Use the `Skill` tool or subagent mechanism.

---

## Key Rules

### Safety Constraints
1. **Never modify core tik.maya** without explicit user approval
2. **Never create branches/commits/PRs** without authorization
3. **Never run full per-test coverage** without explicit confirmation
4. **Never introduce third-party packages** without approval

### Code Constraints
1. **Consume tik.maya** — Don't call `cmds` or `OpenMaya` directly in tools
2. **Source of Truth** — Maya scene state is always authoritative
3. **Test via pytest** — All tests run under Maya standalone (`mayapy`)
4. **No third-party deps** — Stick to stdlib and Maya-bundled modules

### Architecture Constraints
1. **tik.maya Types/Roles/Constructs** — Don't conflate these
2. **DCC-agnostic core** — `core/` in tik.trigger imports no Maya modules
3. **Undoability** — All scene modifications must be undoable

---

## tik.trigger Architecture (Plan)

### Folder Structure
```
src/tik/trigger/
├── core/               # DCC-agnostic framework
│   ├── action_core.py # ActionCore base
│   ├── module_core.py # ModuleCore + GuidesCore
│   ├── registry.py    # @register_action/@register_module
│   └── schemas.py     # Dataclasses
├── actions/           # Folder per action (e.g., jointify/jointify.py)
├── modules/           # Folder per module (e.g., bipedArm/bipedArm.py)
├── session/           # Session management
├── config/           # User settings (JSON defaults)
└── ui/               # Qt UI (decoupled from core)
```

### Discovery Pattern
- Folder-based discovery scanning subdirectories
- Each folder contains named `.py` file (e.g., `jointify.py` not `__init__.py`)
- Explicit `@register_action` / `@register_module` decorators

### UI Definitions
- JSON files for declarative UI (`ui_definition.json`)
- Uses tik_manager4's `SettingsLayout` pattern for auto-generated Qt UI

---

## Important Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project-level context |
| `AGENTS.md` | Agent behavior guidelines |
| `AI/coding_rules.md` | Python/Maya coding standards |
| `AI/testing_rules.md` | Test-specific guidelines |
| `AI/tik_trigger_plan.md` | Full tik.trigger architectural plan |

---

## Development Workflow

1. **Understand task** — Use skills, explore codebase
2. **Plan approach** — For non-trivial tasks, create a plan
3. **Implement** — Follow coding rules
4. **Test** — Use pytest under mayapy
5. **Review** — Delegate to lint-agent if needed

---

## Getting Help

- `/skill <name>` — Invoke a skill
- `Skill` tool — Access agent definitions
- Read file before modifying
- Check related agent definitions for guidance
