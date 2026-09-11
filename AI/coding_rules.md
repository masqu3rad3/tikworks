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

### Preferences never reach the rig

A user preference is a quality-of-life choice. It may change what you *see*
and what you *author*, never what a build makes from an already-saved session.
The rule is build determinism: **given the same `.tr`, two artists build an
identical rig, whatever their settings say.**

This is enforced structurally rather than by review. `tik/trigger/core`,
`modules`, `systems`, `maya`, `actions` and `guides` may not import
`tik.trigger.config` or `tik.shared.prefs` *at all* --
`tests/unit/test_import_boundaries.py` fails if they do. Only
`tik/trigger/ui` reads preferences, and the build API takes no settings
argument.

So a value that changes the rig is not a preference. It belongs in the `.tr`
session document, where it is visible, reviewable and version-controlled. If
you find yourself wanting a preference read from inside a module or an action,
that is the signal you are reaching for the wrong home.

Adding a preference is one `Field` line on a page in
`tik/trigger/config/pages/`; the dialog is generated. Every field must declare
`help=` -- it is both the tooltip and the text the settings search matches on.

---

## Module Ground Rules (all tik.trigger modules)

Full rationale: `docs/superpowers/specs/2026-08-30-arm-module-and-module-ground-rules-design.md`

### Group Taxonomy

Every module hangs under the rig's scaffold, which `ensure_rig()` creates or
heals before any build or action (`tik/trigger/maya/scaffold.py`; spec
`docs/superpowers/specs/2026-09-05-rig-scaffold-and-master-controls-design.md`).
One rig per scene, no name:

```
rig_grp
├── trigger_grp            every <side>_<name>_grp
│   ├── preferences_ctrl   rig-wide switches: cacheMode, controls, rig/rigDisplay,
│   │                      joints/jointsDisplay, geo/geoDisplay
│   └── visibilities_ctrl  one enum per module: primary / secondary / tertiary / all
└── geo_grp                what Import Model brings in
```

Modules never add attributes to `preferences_ctrl`; scripts and actions reach
it as `ctx.rig.preferences`. The one thing a module says about visibility is
the **tier** of each controller: `rig.controller(name, tier="secondary")`,
default `primary`, one of `tik.trigger.core.TIERS`. Tiers are exclusive in the
enum; `all` shows the three. Tweaks have no tier and stay on `tweakVis`. Tier
wiring drives shape visibility, never transforms. Once built into the rig, the
module's own `controlVisibility` / `rigVisibility` / `bindVisibility` are
driven by the preferences and locked.

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
    guides   = GuideLayout("collar", "shoulder", "elbow", "hand")
    inputs   = (Input("root", primary=True),)
    outputs  = ("collar", "upperarm", "lowerarm", "hand")
    controls = ("collar", "ik", "fk_upper", "fk_lower", "fk_hand", "pole")
    stretch  = BoolField(True)

    def draw_guides(self, guides): ...
    def build(self, rig): ...
```

The four groups, the naming, the tagging, **a socket per declared input**, and
**an offset group per controller** are created for it. `rig.socket("root")`
fetches the socket the declaration made; `ctrl.offset` is the controller's
offset group.

### The Control Manifest

`controls` lists **every controller the module builds** — not a curated subset.
What each rigger-facing section then *offers* is named separately, so a module
states it rather than the table assuming it:

| Attribute | Question it answers | Default |
|---|---|---|
| `controls` | What controllers do I build? | `()` |
| `space_controls` | Which may host an animation space? | **all of `controls`** |
| `pivot_controls` | Which get a movable pivot, anchored where? | `{}` |
| `control_shapes` | Which have a definable shape, defaulting to what? | `{}` |

`space_controls` is the one whose default is "all", and the asymmetry is the
point: hosting a space is something any controller *can* do, so a module
narrows rather than opts in. A pivot and a shape are offers a module makes.
`control_shapes`' **keys are the Shapes section's candidate set** — there is no
`shape_controls` list, because it would repeat `controls` line for line and then
drift from it.

A pivot anchor is a guide *reference*: `"hand"` means that role at index 0, and
`("segment", 2)` addresses the third guide of a multi — which is what lets a
module whose controls depend on a setting declare a pivot for each of them.

**Declaring a pivot offers it; a preset row builds it.** The builder makes the
pivot controller after `build()` returns, for every declared role that has rows,
the same way a socket is made per declared input — so no module contains pivot
code. It skips a role that already has one, so a module still calling
`rig.pivot_control` itself gets one pivot rather than a second that fails.
Every control a module builds must be offered a pivot: offering is free, so
leaving one out is an oversight, not a decision. When it *is* a decision, say so
in `pivot_exempt_for_copy` and give the reason in its docstring — the ribbon's
mids are exempt because a mid rides the surface and a moved pivot does not
behave there. A control may not be both offered and exempt.

**A section with no candidates and no rows does not render.** A fold the rigger
cannot use is worse than a missing one — it claims an offer the module does not
make.

When a setting drives any of these sets, override the matching `*_for_copy`
hook — `controls_for_copy`, `space_controls_for_copy`, `pivot_controls_for_copy`,
`control_shape_defaults_for_copy` — exactly as `outputs_for_copy` does for
outputs:

```python
@classmethod
def controls_for_copy(cls, settings=None):
    count = int((settings or {}).get("segments", cls.segments.default))
    return tuple(f"fk{index}" for index in range(count))

@classmethod
def pivot_controls_for_copy(cls, settings=None):
    """Each FK control anchors to the guide it is matched to.

    The anchors carry an index rather than a bare role -- a bare "segment"
    would stack every preset on the first guide.
    """
    found = {"fk0": ("root", 0)}
    for index in range(1, len(cls.controls_for_copy(settings))):
        found[f"fk{index}"] = ("segment", index - 1)
    return found
```

The base class repeats each hook across the module's copies and qualifies the
names, so an author writes single-copy code and never sees a copy.

Two rules keep the manifest honest:

- **Tweaks and pivots are excluded by construction.** `rig.tweak_control(main)`
  creates the role `<main>_tweak` parented under its main, so a space switch on
  one would fight the parent it hangs from; `rig.pivot_control(main)` creates
  `<main>_pivot` the same way. A role ending in `_tweak` or `_pivot` is never
  declared.
- **Roles a system chooses are named by that system.** A module using
  `build_ikfk_limb` calls `limb_control_names(labels=...)` rather than writing
  `"fk_upper"` out; hardcoding would drift the moment the system renamed a role.

A module may also declare **`pivot_controls`** — `{control role: anchor guide
role}` — which gives that control a movable pivot through
`rig.pivot_control(ctrl)`: a `showPivot` bool, a pivot controller under it
driving `rotatePivot`/`scalePivot`, and, when the rigger's `pivot_presets` table
has rows for it, a `pivotPreset` enum switching between named positions placed
as guides. The anchor is the guide those preset guides hang under, so moving it
carries them along. tik.maya owns only the wiring (`Controller.drive_pivot`);
naming `showPivot` and `pivotPreset` is policy, and policy is trigger's.

`tests/integration/trigger/test_module_ground_rules.py` builds every shipped
module and asserts the manifest **equals** the roles tagged on the controllers
it created, minus tweaks and pivots. A control the module forgot to declare is invisible
in the anim-space table — which is exactly how `fkchain` and `ribbon` once
shipped with animation spaces that could not be used at all.

### Animator switches

A switch changes what a control *does*, and the pose survives it. That is the
whole entry test for a tab in the Switches dock (`tik/trigger/anim`): name what
it promises not to disturb, or it is not a switch. A tab is a
`@register_switch` class supplying `states` / `current` / `apply`; the scene
work is a plain function in `tik/trigger/maya`, so a shelf button can call it
without opening a window, and the shell itself never touches Maya.

**An animator tool reads the rig, never the session.** `trigger/anim` may not
import `trigger.session`, the documents, the guides or `trigger.ui` --
everything a switch needs is already on the built nodes.

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
- **JSON Configs:** Python field declarations are the schema (the UI is generated from them by `FormBuilder`); an optional `defaults.json` beside a module/action overrides field default values only
- **DCC-Agnostic Core:** `core/` imports no Maya modules

#### tik.trigger Core Development
When implementing `core/` modules:
- All modules must have full type hints and docstrings
- Use dataclasses for typed data structures (see `core/schemas.py`)
- Custom exceptions must inherit from appropriate `TriggerError` subclasses
- Registry-based code must use `setup_method`/`teardown_method` for isolation
- Test files follow naming: `test_<module_name>_trigger.py`

#### Icons
Every action and guide module ships a hand-drawn `<name>.svg` beside its
`.py` — actions full colour and never tinted, modules monochrome and tinted
by side or category at runtime. `test_icon_assets.py` fails the suite for
any registered plugin with no icon file, so this is not optional for a new
action or module folder. Drawing rules, the Qt SVG Tiny 1.2 subset a file
must stay inside, and copy-paste templates live in `AI/icon_rules.md`.

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
- `AI/icon_rules.md` — Icon drawing rules for tik.trigger actions and modules
