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

## The tik.maya / tik.trigger Boundary

### The Animator-Opinion Rule

**If an average animator can understand it and might have an opinion about it,
it belongs to `tik.trigger`, not `tik.maya`.**

- `tik.maya` owns **mechanism** — which nodes exist and how they are wired. A
  `blendMatrix` between two matrices. An exponential falloff on a distance.
  Nobody has an opinion about `multMatrix` operand order.
- `tik.trigger` owns **policy** — what the rig *is*. "The wrist control carries
  the `ikFk` attribute." "The pole vector follows the shoulder by default."
  "Stretch is limited to +50%."
- **Practical test:** could you name the thing in a note to an animator without
  explaining it first? Then it is trigger's.
- **Corollary:** a `tik.maya` construct never creates a controller, never names
  a user-facing attribute, and never encodes a side convention.

### Layer Escalation

```
nodes -> types -> roles -> constructs -> systems -> modules
         \____________ tik.maya ______/   \____ tik.trigger ____/
```

- `tik/trigger/systems/` holds policy-bearing sub-rigs that compose `tik.maya`
  constructs *and* create controllers (e.g. `limb.py`, `twist.py`, `space.py`).
- Modules compose systems.
- **Modules never inherit from other modules.** Modules are declarative:
  `guides`, `inputs`, `outputs` and `Field`s are class attributes read by the
  registry and the UI `FormBuilder`. Shared behaviour goes in `systems/`.

---

## Module Ground Rules (all tik.trigger modules)

Full rationale: `docs/superpowers/specs/2026-08-30-arm-module-and-module-ground-rules-design.md`

### Group Taxonomy

Exactly four children per module, created by the backend, never by the module:

```
<side>_<name>_grp
├── ..._socket_grp    one transform per declared input, driven by the producer
├── ..._control_grp   controllers and their offset/space groups — nothing else
├── ..._rig_grp       the puppet: IK/FK chains, handles, math, helpers
└── ..._bind_grp      deform/export joints only — empty when connected
```

`scale_grp`, `nonScale_grp` and `scaleHook_grp` are **removed**. Do not
reintroduce them.

### Two Skeletons

| | Puppet (`rig_grp`) | Deform skeleton (`bind_grp`) |
|---|---|---|
| Orientation | mirrored behaviour — reversed aim/up on the right, negative `tx` | engine-neutral — identical orients both sides |
| Negative scale | never needed | never permitted |
| Exported | no | yes |
| Driven by | controls and solvers | the puppet, via `MatrixConstraint` |

**Bind joints must carry live TRS values.** `translate`, `rotate` and `scale`
channels must be actually driven — never a transform parked in
`offsetParentMatrix`. This is required for baking and for export to game engines
and mocap workflows. `MatrixConstraint` satisfies this by decomposing to the
three channels.

`offsetParentMatrix` remains fine for rig helpers inside `rig_grp`, which are
never exported.

### Single Bind Hierarchy

- Every rig has **exactly one** deform-joint hierarchy.
- `rig.bind_parent` resolves the connected input's bind joint **before**
  `build()` runs. Bind joints are *created* in their final position and
  **never reparented** — `MatrixConstraint` wires a live connection to
  `driven.parent.worldInverseMatrix[0]` captured at build time, so a joint
  reparented after being constrained keeps compensating for its old parent.
- **Every module output resolves to a bind joint**, because that is what
  `rig.bind_parent` reads.

### What a Module Writes, and What It Gets for Free

A module declares and then builds:

```python
@register_module("arm")
class Arm(Module):
    guides  = GuideLayout("collar", "shoulder", "elbow", "hand")
    inputs  = (Input("root", primary=True),)
    outputs = ("collar", "upperarm", "lowerarm", "hand")
    stretch = BoolField(True)

    def draw_guides(self, guides): ...
    def build(self, rig): ...
```

The four groups, the naming, the tagging, **a socket per declared input**, and
**an offset group per controller** are created for it. `rig.socket("root")`
fetches the socket the declaration made; `ctrl.offset` is the controller's
offset group.

**The boundary rule:** `rig` owns naming, tagging, group placement and
registration. tik.maya owns the mechanism. A helper earns a place on `rig` only
when it removes naming, tagging, placement or registration boilerplate — which
is why module code calls `tm.MatrixConstraint.create(...)` directly instead of
through a wrapper that would only hide it.

`Controller` proxies attribute and plug **reads** to its transform, so
`ctrl["tx"]` and `ctrl.long_name` work. It does not proxy writes: assignments
(`ctrl.transform.world_position = ...`) and type-checked tik.maya APIs
(`snap_to`, `pole_vector`) take `ctrl.transform`.

### Control Mirror Metadata

Tag every controller `trg_mirror`:

- `behaviour` — FK-like (clavicle, fingers, spine): follows its joint, so equal
  rotation values on both sides give a symmetric pose.
- `world` — IK/world (wrist, foot, pole, COG): world-aligned, so dragging left
  and right together moves them the same direction.

The rig does not read this tag; a pose-mirror tool does.

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
