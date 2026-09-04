# AGENTS.md — TikWorks Agent System

This file documents the agent definitions and behavior guidelines for the TikWorks project.

## Overview

TikWorks uses specialized agents for different tasks. Agents are defined in `.github/agents/` and are invoked via the `Skill` tool or subagent mechanism.

## Available Agents

| Agent | File | Purpose |
|-------|------|---------|
| **tikmaya_api_agent** | `.github/agents/tikmaya-api-agent.agent.md` | Low-level tik.maya API proposals and OpenMaya optimizations |
| **tikmaya_tools_agent** | `.github/agents/tikmaya-tools-agent.agent.md` | Maya tool development consuming tik.maya |
| **tikworks_docs** | `.github/agents/docs-agent.agent.md` | Technical writing and Sphinx documentation |
| **tikworks_linter** | `.github/agents/lint-agent.agent.md` | PEP 8 / Black / Flake8 enforcement |
| **tikworks_tester** | `.github/agents/tests-agent.agent.md` | Test authoring, execution, and coverage |

## Agent Invocation

```bash
# Via Skill tool
/skill tikmaya-api

# Via subagent in conversation
Use the Agent tool with subagent_type="general-purpose" and pass the agent name in the prompt
```

## Agent Specialization

### tikmaya_api_agent
- Proposes and validates low-level tik.maya API additions
- OpenMaya-based optimizations
- Performance benchmarking
- Does NOT modify core without approval

### tikmaya_tools_agent
- Builds production-grade Maya tools consuming tik.maya
- Follows Types / Roles / Constructs architecture
- Delegates to other agents for docs, linting, testing

### tikworks_docs
- Sphinx ReST documentation
- Conditional: only documents existing source files
- Skips `trigger` docs if source not yet implemented

### tikworks_linter
- Style fixes only — never changes functionality
- Handles Python and MEL
- Ignores C++ source in `src/plugins/`

### tikworks_tester
- Author and run pytest tests under Maya standalone
- Per-test coverage analysis (with user consent)
- Test deduplication and archival policy

## Delegation Rules

When working on a complex task, delegate to specialized agents:

1. **Tool implementation** → `tikmaya_tools_agent`
2. **New API behavior** → `tikmaya_api_agent` (propose first)
3. **Documentation** → `tikworks_docs`
4. **Style fixes** → `tikworks_linter`
5. **Tests** → `tikworks_tester`

## Safety Constraints

- **Never modify core tik.maya** without explicit user approval
- **Never create branches/commits/PRs** without authorization
- **Never run full per-test coverage** without explicit confirmation
- **Never introduce third-party packages** without approval

## Agent Definition Files

Agent definitions are Markdown files with YAML frontmatter:

```markdown
---
name: agent_name
description: What this agent does
---

# Agent content...
```

## Related Files

- `CLAUDE.md` — Project-level context
- `AI/coding_rules.md` — Detailed coding standards
- `AI/system_prompt.md` — System instructions
- `AI/icon_rules.md` — Icon drawing rules for tik.trigger actions and modules
