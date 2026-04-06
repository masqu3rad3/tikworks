# Documentation Rules — TikWorks

## Overview
Documentation in TikWorks follows Sphinx/ReStructuredText conventions and is authored by the `tikworks_docs` agent.

---

## Documentation Architecture

```
docs/
├── index.rst              # Main landing page
├── usage/                 # User guides
├── reference/             # API references (autodocs)
├── development/           # Developer guides
└── _static/              # Static assets
```

---

## Sphinx & ReST Standards

### Formatting
- Use standard Sphinx reST
- Code blocks: `.. code-block:: python`
- Links: Use `:class:`, `:func:`, `:attr:` for code references

### Directives
- `.. note::` — Important information
- `.. warning::` — Side effects, undo impact
- `.. seealso::` — Related topics
- `.. automodule::` — Autodoc for modules
- `.. autoclass::` — Autodoc for classes

---

## Docstring Standards

### PEP 257
- All public APIs need docstrings
- First line: concise summary (ends with period)
- Blank line after summary
- Additional paragraphs for detailed description
- Args/Returns/Raises sections for functions

### Example
```python
def create_joint(name: str, parent: Optional[str] = None) -> str:
    """Create a Maya joint with optional parent.

    Args:
        name: The joint name.
        parent: Optional parent joint name.

    Returns:
        The created joint name.

    Raises:
        ValueError: If name is empty.
    """
```

---

## tik.maya Documentation Guidelines

### Value Add Focus
- Don't just list functions — explain the abstraction
- Example: "Unlike `cmds.xform`, `tik.maya.Transform.set_matrix()` handles decomposition automatically"

### API Documentation
- Document public methods and properties
- Include usage examples
- Note Maya version requirements
- Document undo behavior

---

## tik.trigger Documentation (when implemented)

### Trigger-Specific
- Document Rig Logic flow
- Document module and action patterns
- Include setup and usage guides

### Architecture Docs
- Document separation of concerns (core/, actions/, modules/, etc.)
- Document plugin discovery mechanism
- Document session management

---

## Conditional Documentation

### Source File Check
- If source files don't exist, do not generate placeholder docs
- Clearly state: "Module not yet implemented"

### Trigger Docs
- Only generate when `src/tik/trigger/` has valid source files
- If asked about unimplemented features, state clearly

---

## Related Files
- `AGENTS.md` — Agent definitions (tikworks_docs agent)
- `AI/coding_rules.md` — Code style
- `AI/system_prompt.md` — System instructions
