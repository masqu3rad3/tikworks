# Tikworks Coding Guidelines

## Context
- `tikworks` is a repository containing the `tikmaya` core library and various tools (e.g., `trigger`, `etc`).
- `tikmaya` lives under `tikworks/src/tikmaya`.
- Tools live under `tikworks/src/` (e.g., `src/trigger`) and should consume `tikmaya`.

---

## Global Guidelines (All Code)

### Dependencies
- Stick to vanilla Python stdlib and modules that ship with Maya: `cmds`, `OpenMaya` (API 2.0), `PySide6`, etc.
- No third‑party dependencies unless explicitly approved.

### Compatibility
- Target Autodesk Maya 2026 and onwards.
- Assume Python 3.11+ and `PySide6` availability.
- No support for pre‑`PySide6` or Python versions before 3.11.

### Code Style
- Follow PEP 8.
- Enforce `black` formatting and `flake8` linting.
- Write clear type hints and docstrings complying with PEP257 rules.
- Never use single-letter variable names even in small scopes (e.g., loops, comprehensions).

### Testing
- Use `pytest` for all tests.
- All tests must run in a headless Maya standalone session initialized via `tests/conftest.py`.
- Follow `pytest` naming conventions: `test_*.py`, `Test*`, `test_*`.
- Prefer exercising real Maya behavior; mocking is a last resort.
- Following template should be used for running tests: $env:PYTHONPATH="src"; mayapy -m pytest tests/unit/<testfile> --cov=<module for coverage> --cov-report=term-missing
- If mayapy is not recognized as a command, that probably means its not defined in user PATH. Warn the user to set up their environment correctly in that case.

---

## Tikmaya Library Guidelines (`src/tikmaya`)

These rules apply **strictly** when developing or extending the core `tikmaya` library.

### Core Philosophy
- **"Feel like Python, behave like Maya":** APIs should be expressive and explicit.
- **Source of Truth:** The Maya scene state is the ultimate authority.
- **Opinionated:** Favor clarity and correctness over cleverness.

### Architecture
Tikmaya is organized around three distinct concepts. Do not conflate them:

1.  **Types (`tikmaya/core/types`)**:
    - Describes what a node *is* (e.g., `Transform`, `Mesh`).
    - Maps 1:1 to Maya node types.
    - **Rule:** Never encodes semantic meaning (don't ask "what role does this play?").

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
    - Order members: Docstrings -> `__init__` -> Properties -> Public Methods -> Private Helpers.
    - Group related properties together.
    - Use section headers (e.g., `# === Properties ===`) for large classes.

---

## Tool Development Guidelines (`src/trigger`, `src/etc`)

These rules apply when writing tools that use Tikmaya.

### Implementation Rules
- **Consume Tikmaya:** Tools should consume `tikmaya` objects and wrappers.
- **Avoid Direct Calls:** Avoid calling `cmds` or `OpenMaya` directly in tools.
- **Gap Handling:** If `tikmaya` lacks functionality required by a tool:
    1.  Propose and implement the feature in `tikmaya` first.
    2.  Only add ad-hoc logic in the tool if it is strictly domain-specific and not reusable.