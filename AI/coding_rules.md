# Coding Rules — TikWorks

## Context
- `tikworks` is a repository containing the `tikmaya` core library and various tools (e.g., `trigger`).
- `tikmaya` lives under `src/tik/maya`.
- Tools live under `src/tik/` and should consume `tikmaya`.

---

## Global Guidelines (All Code)

### Dependencies
- Stick to vanilla Python stdlib and modules that ship with Maya: `cmds`, `OpenMaya` (API 2.0), `PySide2`/`PySide6`, etc.
- No third‑party dependencies unless explicitly approved.

### Compatibility
- Target Autodesk Maya 2024 and onwards.
- Assume Python 3.10+ and `PySide2` or `PySide6` availability.
- No support for Python versions before 3.10.

### Code Style
- Follow PEP 8.
- Enforce `black` formatting and `flake8` linting.
- Write clear type hints and docstrings complying with PEP257 rules.
- Never use single-letter variable names even in small scopes (e.g., loops, comprehensions).
- Use `black` line length (default 88 chars).

### Imports
- Group imports: stdlib → third-party → local
- Use `isort` for automatic sorting

### Testing
- Use `pytest` for all tests.
- All tests must run in a headless Maya standalone session initialized via `tests/conftest.py`.
- Follow `pytest` naming conventions: `test_*.py`, `Test*`, `test_*`.
- Prefer exercising real Maya behavior; mocking is a last resort.

### Test Execution Template
```powershell
$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/<testfile> --cov=<module> --cov-report=term-missing
```

---

## Tikmaya Library Guidelines (`src/tik/maya`)

These rules apply **strictly** when developing or extending the core `tik.maya` library.

### Core Philosophy
- **"Feel like Python, behave like Maya":** APIs should be expressive and explicit.
- **Source of Truth:** The Maya scene state is the ultimate authority.
- **Opinionated:** Favor clarity and correctness over cleverness.

### Architecture
Tikmaya is organized around three distinct concepts. Do not conflate them:

1.  **Types (`tikmaya/core/types`)**:
    - Describes what a node *is* (e.g., `Transform`, `Mesh`).
    - Maps 1:1 to Maya node types.
    - **Rule:** Never encodes semantic meaning.

2.  **Roles (`tikmaya/core/roles`)**:
    - Describes what a node *means* (e.g., `Controller`, `SpaceSwitcher`).
    - Wraps an existing type instance to add semantic logic.
    - **Rule:** Never creates new Maya node kinds.

3.  **Constructs (`tikmaya/core/constructs`)**:
    - Orchestrates multiple nodes/roles to represent a pattern or setup.

### API Style & Naming
- **Properties vs. Methods:**
    - Use `@property` for state/data (noun-like: `visible`, `locked`).
    - Use **Methods** for actions/side-effects (verb-like: `lock()`, `freeze()`).
    - **No** `get_` / `set_` prefixes.
- **Class Structure:**
    - Order members: Docstrings → `__init__` → Properties → Public Methods → Private Helpers.
    - Group related properties together.

### Undoability
- All scene-modifying operations MUST be undoable.
- Prefer the vendored `tik.core.apicommon.undocommit` pattern for API-level operations.
- For cmds-based sequences, use `cmds.undoInfo(openChunk=True/closeChunk=True)`.

---

## Tool Development Guidelines (`src/tik/trigger`)

These rules apply when writing tools that use tik.maya.

### Implementation Rules
- **Consume tik.maya:** Tools should consume `tik.maya` objects and wrappers.
- **Avoid Direct Calls:** Avoid calling `cmds` or `OpenMaya` directly in tools.
- **Gap Handling:** If `tik.maya` lacks functionality:
    1. Propose and implement the feature in `tik.maya` first.
    2. Only add ad-hoc logic in the tool if strictly domain-specific.

### tik.trigger Specific
- **Registry Decorators:** Use `@register_action` / `@register_module` for plugin registration
- **Folder Discovery:** Each action/module is a folder with named `.py` file
- **JSON Configs:** Use JSON files for UI definitions and defaults
- **DCC-Agnostic Core:** `core/` imports no Maya modules

#### tik.trigger Core Development
When implementing `core/` modules:
- All modules must have full type hints and docstrings
- Use dataclasses for typed data structures (see `core/schemas.py`)
- Custom exceptions must inherit from appropriate `TriggerError` subclasses
- Registry-based code must use `setup_method`/`teardown_method` for isolation
- Test files follow naming: `test_<module_name>_trigger.py`

---

## Error Handling
- Fail fast with clear custom exception types.
- Avoid silent catches that hide Maya errors.
- Use proper exception chaining: `raise NewException(...) from e`

## Documentation
- All public APIs need docstrings.
- Use Sphinx-friendly formats (RST, Markdown where supported).

---

## Related Files
- `AGENTS.md` — Agent definitions
- `AI/testing_rules.md` — Test-specific guidelines
- `AI/documentation_rules.md` — Doc conventions
