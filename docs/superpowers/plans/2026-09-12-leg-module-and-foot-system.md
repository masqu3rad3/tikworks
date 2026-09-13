# Leg Module and Foot System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `leg` module for tik.trigger with a full reverse foot — roll, bank, heel/ball/toe pivots, and a new one-channel auto foot roll — reusing the arm's limb, reach and limb-lock systems rather than duplicating them.

**Architecture:** `systems/limb.py` splits into a controls phase and a solve phase so a driver can be injected between them; a new `systems/foot.py` builds the reverse-foot pivot stack plus a mirrored controller chain and returns the node the limb solve follows; `modules/leg/leg.py` composes limb + foot + reach + limb_lock. Every foot behaviour gets both a secondary controller and a proxy attribute on the IK control, which Maya keys onto the same curve.

**Tech Stack:** Python 3.10+, Autodesk Maya 2024+, `tik.maya` wrapper (never raw `maya.cmds` in tool code), `pytest` under `mayapy`.

**Spec:** `docs/superpowers/specs/2026-09-12-leg-module-and-foot-system-design.md` — read it before Task 1. Every task references its sections.

## Global Constraints

- **Maya 2024+, Python 3.10+.** No third-party dependencies — stdlib and Maya-bundled modules only.
- **Never call `maya.cmds` or `OpenMaya` directly** in `src/python/tik/trigger/`. Go through `tik.maya` (`import tik.maya as tm`). Tests may use `cmds` directly.
- **`tik/trigger/core` is pure Python** — no Maya, no Qt. `tests/unit/test_import_boundaries.py` enforces it. Scene code lives in `tik/trigger/maya/`, `tik/trigger/guides/` and `tik/trigger/systems/`.
- **Modules never inherit from other modules.** Shared behaviour goes in `tik/trigger/systems/`.
- **Preferences never change the rig.** Nothing under `trigger/core`, `modules`, `systems`, `maya`, `actions`, `guides` may import `tik.trigger.config.prefs`.
- **The control manifest must equal what `build()` creates, minus tweaks and pivots.** `tests/integration/trigger/test_module_ground_rules.py` enforces it.
- **Four groups per module** (`socket` / `control` / `rig` / `bind`). `control_grp` holds nothing but controllers and their offset groups. IK handles live in `rig_grp`.
- **Every dialog goes through `tik.shared.ui.feedback.Feedback`.** Not relevant to this plan — no UI is added — but do not add one.
- Run tests with `make tests-unit` and `make tests-integration` (both use `mayapy`). Single file: `mayapy -m pytest tests/integration/trigger/test_foo.py -v` with `PYTHONPATH` including `src/python`.
- Lint with `make lint` (black, isort profile=black, flake8) before every commit.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `src/python/tik/trigger/systems/foot.py` | Reverse-foot pivot stack, controller chain, ball/toe puppet extensions, proxies, auto-roll. Knows nothing about the leg module. |
| `src/python/tik/trigger/modules/leg/leg.py` | The `leg` module: manifest, `draw_guides`, `build` composing limb + foot + reach + limb_lock. |
| `src/python/tik/trigger/modules/leg/leg.svg` | Module icon, per `AI/icon_rules.md`. |
| `tests/integration/trigger/test_foot_system.py` | The foot system driven directly. |
| `tests/integration/trigger/test_leg_trigger.py` | The leg module end to end. |

**Modified:**

| File | Change |
|---|---|
| `src/python/tik/trigger/systems/limb.py` | Split into `build_limb_controls` / `build_limb_solve`; `derive_size` and `conventional_frames` made public; `LimbResult` gains `pole_rest` and `parent`. |
| `src/python/tik/trigger/modules/arm/arm.py` | Import the renamed helpers; delete its private `_conventional_frames`. No behaviour change. |
| `src/python/tik/trigger/maya/rig.py` | `controller()` conjugates a shape orient only for `mirror="behaviour"` controls. |
| `tests/integration/trigger/conftest.py` | Add the `mirrored_pair` fixture. |
| `tests/integration/trigger/test_module_ground_rules.py` | Delete the stale `MODULE_TYPES` tuple. |

---

## Task 1: Close the ground-rules coverage hole

Spec §10.2. `test_module_ground_rules.py` holds two module lists. `MODULE_TYPES = ("base", "fkchain", "arm")` drives ten tests; `_shipped_module_types()` drives the rest. `control`, `twist` and `ribbon` were added later and are silently exempt from those ten. This must be closed *before* `leg` exists, or `leg` inherits the same exemption.

**Files:**
- Modify: `tests/integration/trigger/test_module_ground_rules.py:21` and the ten `@pytest.mark.parametrize("module_type", MODULE_TYPES)` decorators
- Possibly modify: `src/python/tik/trigger/modules/control/control.py`, `.../twist/twist.py`, `.../ribbon/ribbon.py` — only if a newly-covered test fails

**Interfaces:**
- Consumes: nothing
- Produces: every shipped module covered by every ground-rule test. Later tasks rely on `leg` being auto-covered the moment it registers.

- [ ] **Step 1: See the hole**

```bash
cd D:/dev/tikworks
grep -n "MODULE_TYPES\|_shipped_module_types" tests/integration/trigger/test_module_ground_rules.py
```

Expected: line 21 defines the tuple, ten `@pytest.mark.parametrize` lines use it, and `_shipped_module_types()` is used by the others.

- [ ] **Step 2: Delete the tuple and repoint the ten tests**

Delete line 21 entirely. Then replace every occurrence:

```python
@pytest.mark.parametrize("module_type", MODULE_TYPES)
```

with:

```python
@pytest.mark.parametrize("module_type", _shipped_module_types())
```

Do all ten. `_shipped_module_types()` is already defined above them in the same file and already calls `trigger.load_plugins()`, so no import changes are needed.

- [ ] **Step 3: Run and read the failures**

```bash
mayapy -m pytest tests/integration/trigger/test_module_ground_rules.py -v
```

Expected: `base`, `fkchain`, `arm` pass as before. `control`, `twist`, `ribbon` may fail. **Each failure is a finding about that module, not a test to relax** — that file's own docstring says so. The likely shape is a manifest/build disagreement in `test_every_module_declares_exactly_the_controllers_it_builds`: a controller the module creates but does not declare in `controls`, or vice versa.

- [ ] **Step 4: Fix each failing module at its manifest**

For a module whose build creates a control it did not declare, add the role to `controls` (or to `controls_for_copy` when the set depends on a setting). For a module that declares one it does not build, remove it. Do **not** change `_built_control_roles` or add exemptions. Re-run after each fix.

If a failure is not a manifest disagreement, stop and report it before changing anything — an unexpected ground-rule failure in a shipped module is worth a human decision.

- [ ] **Step 5: Run the whole integration suite**

```bash
make tests-integration
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/trigger/test_module_ground_rules.py src/python/tik/trigger/modules
git commit -m "Cover every shipped module with every ground rule

MODULE_TYPES was a hand-maintained tuple driving ten of the ground-rule
tests while the rest used _shipped_module_types(). control, twist and
ribbon were added after it was written and were silently exempt."
```

---

## Task 2: Make the two limb helpers public

Spec §3.1. `_derive_size` is already imported by `arm.py` with its underscore; `_conventional_frames` is private to the arm and the leg needs it verbatim. No aliases are kept — there is no backward compatibility to preserve.

**Files:**
- Modify: `src/python/tik/trigger/systems/limb.py`
- Modify: `src/python/tik/trigger/modules/arm/arm.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `tik.trigger.systems.limb.derive_size(joints: Sequence) -> float`
  - `tik.trigger.systems.limb.conventional_frames(rig, positions: Sequence[Sequence[float]]) -> list[tm.Joint]` — a throwaway chain on the convention (X to the next joint, Y up) at `positions`, parented under `rig.groups.rig`. **The caller deletes it** with `tm.delete(frames[0].long_name)`.

- [ ] **Step 1: Rename in `limb.py`**

In `src/python/tik/trigger/systems/limb.py`, rename `_derive_size` to `derive_size` (the `def` and all four internal call sites — `build_ikfk_limb` and any other).

Then move `_conventional_frames` out of `arm.py` and into `limb.py` as `conventional_frames`, keeping its docstring verbatim — it records two measured Maya behaviours (`cmds.joint -orientJoint` silently skipping a joint with non-zero rotations, and why the chain is read off a throwaway rather than oriented in place) that must not be lost. Place it next to `derive_size` at the bottom of the module.

- [ ] **Step 2: Update the arm**

In `src/python/tik/trigger/modules/arm/arm.py`:

```python
from tik.trigger.systems.limb import (
    build_ikfk_limb,
    conventional_frames,
    derive_size,
    limb_control_names,
    limb_control_orients,
    limb_control_shapes,
    limb_pivot_controls,
)
```

Delete the module-level `_conventional_frames` function from `arm.py`. Replace its two call sites: `_derive_size(limb_guides)` becomes `derive_size(limb_guides)`, and `_conventional_frames(rig, [...])` becomes `conventional_frames(rig, [...])`.

- [ ] **Step 3: Confirm nothing else referenced the old names**

```bash
cd D:/dev/tikworks
grep -rn "_derive_size\|_conventional_frames" src/python tests --include=*.py
```

Expected: no output. If anything is found, update it.

- [ ] **Step 4: Run the arm and limb tests**

```bash
mayapy -m pytest tests/integration/trigger/test_arm_trigger.py tests/integration/trigger/test_limb_system.py -v
```

Expected: PASS, with exactly the same test count as before. This is a pure rename; any behaviour change here is a mistake.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/systems/limb.py src/python/tik/trigger/modules/arm/arm.py
git commit -m "Make derive_size and conventional_frames public limb helpers

Both are needed by a second limb module. _derive_size was already
imported across module boundaries with its underscore intact."
```

---

## Task 3: Split the limb into a controls phase and a solve phase

Spec §4. The leg's IK solve must follow a node built *from* the IK control, which the single call creates — so the call has to open in the middle.

**Files:**
- Modify: `src/python/tik/trigger/systems/limb.py`
- Test: `tests/integration/trigger/test_limb_system.py`

**Interfaces:**
- Consumes: `derive_size` (Task 2)
- Produces:
  - `build_limb_controls(rig, guides, *, name="", parent=None, controller_size=None, labels=None) -> LimbResult` — fills `ik_joints`, `fk_joints`, `puppet_group`, `pole_base`, `ik_control`, `ik_tweak`, `switch_plug`, `fk_controls`, `hinge_axis`, `size`, `pole_rest`, `parent`, `labels`, `name`.
  - `build_limb_solve(rig, result, *, driver=None, bind_joints=None, soft_ik=True, stretch=True, squash=True, stretch_limit_default=50.0, pole_pin=False) -> LimbResult` — `driver=None` means `result.ik_tweak`.
  - `build_ikfk_limb(...)` unchanged in signature and behaviour.
  - `LimbResult` gains `pole_rest`, `parent`, `labels`, `name`.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_limb_system.py` (add `from tik.trigger.systems import limb` and `import tik.maya as tm` at the top if absent):

```python
def test_a_custom_driver_is_what_the_solve_follows(build_context):
    """The seam the leg needs: something built between the two phases."""
    ctx = build_context("base", name="probe")
    guides = [
        tm.Joint.create(name="g%d" % index, position=position)
        for index, position in enumerate([(0, 10, 0), (0, 5, 1), (0, 0, 0)])
    ]
    result = limb.build_limb_controls(ctx, guides, labels=("upper", "lower", "end"))

    # Stand-in for the leg's reverse foot: a node under the IK tweak.
    relay = tm.Transform.create(
        name="relay", parent=result.ik_tweak.transform.long_name
    )
    limb.build_limb_solve(ctx, result, driver=relay)

    # The soft-IK network measures to the relay, not to the tweak.
    assert result.soft_ik is not None
    upstream = tm.listConnections(
        result.soft_ik.node.long_name, source=True, destination=False
    ) or []
    names = [tm.resolve(node).name for node in upstream]
    assert "relay" in names


def test_the_default_driver_is_still_the_ik_tweak(build_context):
    """Phase two with no driver must behave exactly as the single call does."""
    ctx = build_context("base", name="probe")
    guides = [
        tm.Joint.create(name="h%d" % index, position=position)
        for index, position in enumerate([(0, 10, 0), (0, 5, 1), (0, 0, 0)])
    ]
    result = limb.build_limb_controls(ctx, guides, labels=("upper", "lower", "end"))
    limb.build_limb_solve(ctx, result)
    assert result.ik_handle is not None
    assert result.pole_control is not None
```

- [ ] **Step 2: Run it and watch it fail**

```bash
mayapy -m pytest tests/integration/trigger/test_limb_system.py::test_a_custom_driver_is_what_the_solve_follows -v
```

Expected: FAIL with `AttributeError: module 'tik.trigger.systems.limb' has no attribute 'build_limb_controls'`.

- [ ] **Step 3: Add four fields to `LimbResult`**

```python
    #: Pole rest position, captured in the controls phase. It MUST be read
    #: before the solve is wired: the pole and soft-IK constraints move the
    #: chain, and every offset baked afterwards depends on this pose.
    pole_rest: object = None
    #: What the limb hangs from, carried so the solve phase need not be told.
    parent: object = None
    #: Segment labels, resolved. The solve phase names attributes from them.
    labels: list = field(default_factory=list)
    #: The extra name token, carried for the same reason.
    name: str = ""
```

- [ ] **Step 4: Split the function**

Replace `build_ikfk_limb` with three functions. The split point is immediately after `_build_controls`.

```python
def build_limb_controls(
    rig,
    guides: Sequence,
    *,
    name: str = "",
    parent=None,
    controller_size: Optional[float] = None,
    labels: Optional[Sequence[str]] = None,
) -> LimbResult:
    """Build the puppet chains and the IK/FK controllers.

    The first half of :func:`build_ikfk_limb`. It is its own entry point so a
    module can build something *from* the IK control and feed it back in as
    the solve's driver -- which is what a reverse foot is.

    Returns:
        A partially filled :class:`LimbResult`, for :func:`build_limb_solve`.
    """
    guides = list(guides)
    if len(guides) < 3:
        raise ValueError("build_limb_controls needs at least three guides.")
    labels = list(labels) if labels else [str(index) for index in range(len(guides))]
    parent = parent if parent is not None else rig.groups.socket
    if controller_size is None:
        controller_size = derive_size(guides)
    result = LimbResult()
    result.size = controller_size
    result.parent = parent
    result.labels = list(labels)
    result.name = name
    side_sign = rig.side_mult

    _build_chains(rig, guides, name, parent, side_sign, result)
    # Captured before the solve is wired: the pole and soft-IK constraints
    # move the chain, and every offset baked afterwards depends on this pose.
    result.pole_rest = _pole_rest_position(result.ik_joints)
    _build_pole_base(rig, name, parent, result)
    _build_controls(rig, name, parent, controller_size, labels, guides, result)
    return result


def build_limb_solve(
    rig,
    result: LimbResult,
    *,
    driver=None,
    bind_joints: Optional[Sequence] = None,
    soft_ik: bool = True,
    stretch: bool = True,
    squash: bool = True,
    stretch_limit_default: float = 50.0,
    pole_pin: bool = False,
) -> LimbResult:
    """Wire the solve onto controls that :func:`build_limb_controls` made.

    Args:
        rig: The module's ``ModuleRig``.
        result: What ``build_limb_controls`` returned.
        driver: What the solve follows. ``None`` means ``result.ik_tweak``,
            which is what keeps the single-call entry point unchanged. A
            module with a rig between its IK control and its IK handle -- a
            leg's reverse foot -- passes the bottom of that stack here.
        bind_joints: Bind joints to drive, one per guide.
        soft_ik: Build the soft-IK network.
        stretch: Build the extend-side factor and its limit clamp.
        squash: Build the compress-side factor.
        stretch_limit_default: Default percentage for ``stretchLimit``.
        pole_pin: Build the mid-joint pin override.

    Returns:
        The same :class:`LimbResult`, fully filled.
    """
    name = result.name
    labels = result.labels
    side_sign = rig.side_mult
    control = result.ik_control  # animator-facing attributes
    driver = node_of(driver) if driver is not None else result.ik_tweak

    rig.separator(control, "segments_")
    segment_scales = [
        control["s" + label.capitalize()].create("float", default=1.0, min=0.001)
        for label in labels[:-1]
    ]

    result.ik_handle = tm.IkHandle.create(
        result.ik_joints[0],
        result.ik_joints[-1],
        solver="ikRPsolver",
        name=rig.name(name, suffix="ikHandle"),
    )
    result.ik_handle.parent = rig.groups.rig
    tm.MatrixConstraint.create(
        driver,
        result.ik_joints[-1],
        maintain_offset=True,
        skip_translate="xyz",
        skip_scale="xyz",
    )

    _build_lengths(rig, name, side_sign, segment_scales, result)
    _build_soft_ik(rig, name, soft_ik, control, driver, result)
    _build_stretch(
        rig, name, stretch, squash, stretch_limit_default, control, driver, result
    )
    _build_pole(
        rig, name, result.size, pole_pin, control, driver, result.pole_rest, result
    )
    _build_visibility(rig, name, result)
    _blend_to_bind(rig, name, bind_joints, result)
    return result


def build_ikfk_limb(
    rig,
    guides: Sequence,
    *,
    name: str = "",
    parent=None,
    bind_joints: Optional[Sequence] = None,
    controller_size: Optional[float] = None,
    soft_ik: bool = True,
    stretch: bool = True,
    squash: bool = True,
    stretch_limit_default: float = 50.0,
    pole_pin: bool = False,
    labels: Optional[Sequence[str]] = None,
) -> LimbResult:
    """Build an IK/FK limb driving ``bind_joints``.

    The two phases back to back, for a module with nothing to insert between
    them. Arguments and behaviour are unchanged; see
    :func:`build_limb_controls` and :func:`build_limb_solve`.
    """
    result = build_limb_controls(
        rig,
        guides,
        name=name,
        parent=parent,
        controller_size=controller_size,
        labels=labels,
    )
    return build_limb_solve(
        rig,
        result,
        bind_joints=bind_joints,
        soft_ik=soft_ik,
        stretch=stretch,
        squash=squash,
        stretch_limit_default=stretch_limit_default,
        pole_pin=pole_pin,
    )
```

`node_of` is defined in `tik/trigger/maya/rig.py`. `limb.py` currently does not import it. **Do not add that import** — `rig.py` imports from `systems` indirectly and the cycle risk is not worth it. Instead add a two-line local helper at the top of `limb.py`:

```python
def node_of(value):
    """The Transform behind a role, or ``value`` unchanged.

    A local copy of ``rig.node_of``: importing it would point this system at
    the Maya rig layer for two lines.
    """
    return getattr(value, "transform", value)
```

- [ ] **Step 5: Run the new tests**

```bash
mayapy -m pytest tests/integration/trigger/test_limb_system.py -v
```

Expected: PASS, including the two new ones.

- [ ] **Step 6: Prove the arm is untouched**

```bash
mayapy -m pytest tests/integration/trigger/test_arm_trigger.py tests/integration/trigger/test_module_ground_rules.py tests/integration/trigger/test_twist_ribbon_limblock.py -v
```

Expected: PASS, same counts as before Task 3. **This is the safety argument for the whole refactor.** If anything fails here, the split is wrong — fix the split, do not adjust the arm.

- [ ] **Step 7: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/systems/limb.py tests/integration/trigger/test_limb_system.py
git commit -m "Split build_ikfk_limb into a controls phase and a solve phase

A leg's reverse foot sits between the IK control and the IK handle, and
the control is created by the call itself. build_limb_solve takes a
driver defaulting to the IK tweak, so build_ikfk_limb and the arm are
unchanged."
```

---

## Task 4: Fix the shape-orient mirror for world-aligned controls

Discovered while planning; a fifth entry for spec §11.2. `rig.controller()` conjugates a shape's orientation whenever the side is RIGHT, ignoring the `mirror=` argument. `mirror_orient`'s own docstring explains why that is right for a behaviour-mirrored control — *"its joints carry a 180 degree roll about X"* — and it is wrong for a world-aligned one. The arm never hit it because `limb_control_orients` deliberately omits every world-aligned role. The leg's six foot controls are `mirror="world"` **and** carry orientations, so they are the first to hit it.

**Files:**
- Modify: `src/python/tik/trigger/maya/rig.py` (in `ModuleRig.controller`)
- Test: `tests/integration/trigger/test_module_ground_rules.py`

**Interfaces:**
- Consumes: nothing
- Produces: `rig.controller(..., mirror="world")` leaves a declared `control_orients` entry alone on both sides.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_module_ground_rules.py`:

```python
def test_a_world_mirrored_control_keeps_its_shape_orientation(build_context):
    """mirror_orient undoes a 180 roll about X that a world control has not got.

    A behaviour-mirrored control's joints carry that roll, so a shape
    authored for the left arrives rolled and the conjugation puts it back. A
    world-aligned control is identical on both sides, so conjugating it flips
    a shape that was already correct.
    """
    from tik.trigger.maya.rig import mirror_orient

    turn = (0.0, 0.0, -90.0)
    # The conjugation itself is unchanged and still correct where it applies.
    assert mirror_orient(turn) == (0.0, 0.0, 90.0)

    ctx = build_context("base", name="probe", side="R")
    # control_orient_defaults is a classmethod reading cls.control_orients,
    # so an instance attribute here would be invisible to rig.controller.
    module_cls = type(ctx.module)
    previous = module_cls.control_orients
    module_cls.control_orients = {"worldish": turn, "boney": turn}
    try:
        world = ctx.controller("worldish", mirror="world")
        boney = ctx.controller("boney", mirror="behaviour")
    finally:
        module_cls.control_orients = previous

    assert world.shape_orient == turn, "a world control must not be conjugated"
    assert boney.shape_orient == mirror_orient(turn), "a bone control must be"
```

- [ ] **Step 2: Run it and watch it fail**

```bash
mayapy -m pytest tests/integration/trigger/test_module_ground_rules.py::test_a_world_mirrored_control_keeps_its_shape_orientation -v
```

Expected: FAIL — `world.shape_orient` is `(0.0, 0.0, 90.0)`, the conjugated value.

- [ ] **Step 3: Make the conjugation conditional**

In `ModuleRig.controller` in `src/python/tik/trigger/maya/rig.py`, replace:

```python
        orient = self.module.control_orient_defaults(self.module.values()).get(name)
        if orient and self.side is Side.RIGHT:
            orient = mirror_orient(orient)
```

with:

```python
        orient = self.module.control_orient_defaults(self.module.values()).get(name)
        # Only a behaviour-mirrored control needs the conjugation. It undoes
        # the 180 degree roll about X that the right side's *joints* carry --
        # a world-aligned control is identical on both sides and has no roll
        # to undo, so conjugating it flips a shape that was already right.
        if orient and self.side is Side.RIGHT and mirror == tags.BEHAVIOUR:
            orient = mirror_orient(orient)
```

If `tags.BEHAVIOUR` does not exist, use the literal `"behaviour"` and add the constant to `tik/trigger/maya/tags.py` alongside `WORLD`:

```python
BEHAVIOUR = "behaviour"
```

- [ ] **Step 4: Run the test**

```bash
mayapy -m pytest tests/integration/trigger/test_module_ground_rules.py -v
```

Expected: PASS.

- [ ] **Step 5: Prove nothing that shipped changes**

```bash
mayapy -m pytest tests/integration/trigger/test_arm_trigger.py tests/unit/test_shape_resolution_trigger.py tests/ui/test_shape_fold.py -v
```

Expected: PASS. No shipped module declares an orient for a world-aligned control — `limb_control_orients` returns FK roles only — so this fix is inert for every rig that exists today. If something here fails, a module *was* relying on the old behaviour and that needs a human decision before proceeding.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/maya/rig.py src/python/tik/trigger/maya/tags.py tests/integration/trigger/test_module_ground_rules.py
git commit -m "Conjugate a shape orient only for behaviour-mirrored controls

mirror_orient undoes the 180 degree roll about X that a right-side
joint carries. A world-aligned control has no such roll, so conjugating
it flipped a shape that was already correct. Inert for every shipped
module; the leg's foot controls are the first world-aligned controls
with declared orientations."
```

---

## Task 5: A mirrored-pair test fixture

Spec §10.4. Both new test files need "build a left and a right and compare", and mirroring is the most common source of limb bugs. Written before the leg so Tasks 10 and 15 can use it.

**Files:**
- Modify: `tests/integration/trigger/conftest.py`

**Interfaces:**
- Consumes: the existing `scene` fixture
- Produces: fixture `mirrored_pair(module_type, poses, **settings) -> tuple[ctx_L, ctx_R]`, where `poses` is `{role: (x, y, z)}` for the **left** side; the right is built from the same poses with `x` negated. Both are built in one scene, in one `Builder().build()` pass.

- [ ] **Step 1: Write the fixture**

Append to `tests/integration/trigger/conftest.py`:

```python
@pytest.fixture
def mirrored_pair(scene):
    """Build the same module on both sides and hand back both contexts.

    Mirroring is the most common source of limb bugs and every test has been
    asserting it ad hoc. ``poses`` are the LEFT side's world positions; the
    right gets the same triples with X negated, which is what "mirrored" has
    to mean for a comparison to say anything.

    Both sides are built in one pass so the comparison cannot be poisoned by
    two different scene states.
    """
    from tik.trigger.core import ParentRef, get_module
    from tik.trigger.maya import Builder

    def _make(module_type: str, poses: dict, **settings):
        body = scene.create_guides(get_module("base")(name="body"))
        cmds.xform(
            scene.guide_node(body.instance_id, "root").long_name,
            ws=True,
            t=(0, 0, 0),
        )
        instances = {}
        for side in ("L", "R"):
            instance = scene.create_guides(
                get_module(module_type)(
                    name=module_type, side=side, settings=settings
                ),
                parent=ParentRef(body.instance_id, "root"),
            )
            mult = -1 if side == "R" else 1
            for role, (x, y, z) in poses.items():
                cmds.xform(
                    scene.guide_node(instance.instance_id, role).long_name,
                    ws=True,
                    t=(x * mult, y, z),
                )
            instances[side] = instance
        report = Builder().build(document=scene.document, afterlife="keep")
        return (
            report.rigs[instances["L"].instance_id],
            report.rigs[instances["R"].instance_id],
        )

    return _make
```

- [ ] **Step 2: Prove the fixture works against a module that already exists**

Append to `tests/integration/trigger/test_arm_trigger.py`:

```python
def test_mirrored_pair_builds_both_arms(mirrored_pair):
    """Smoke test for the fixture itself, on a module known to be correct."""
    left, right = mirrored_pair(
        "arm",
        {
            "collar": (2, 15, 0),
            "shoulder": (5, 15, 0),
            "elbow": (9, 15, -1),
            "hand": (14, 15, 0),
            "neutral": (2 + 12 * NEUTRAL_REACH, 15, 0),
        },
    )
    left_hand = left.outputs["hand"].world_position
    right_hand = right.outputs["hand"].world_position
    assert left_hand[0] == pytest.approx(-right_hand[0], abs=1e-4)
    assert left_hand[1] == pytest.approx(right_hand[1], abs=1e-4)
```

If `ctx.outputs` is not a mapping of name to node, read the joint through whatever accessor `test_arm_trigger.py` already uses for outputs and keep the same two assertions.

- [ ] **Step 3: Run it**

```bash
mayapy -m pytest tests/integration/trigger/test_arm_trigger.py -v
```

Expected: PASS.

- [ ] **Step 4: Lint and commit**

```bash
make lint
git add tests/integration/trigger/conftest.py tests/integration/trigger/test_arm_trigger.py
git commit -m "Add a mirrored_pair fixture for integration tests

Build the same module on both sides in one pass and hand back both
contexts. Mirroring is where limbs break and every test was asserting
it ad hoc."
```

---

## Task 6: The leg module's manifest and guides

Spec §5 and §9.1. Eleven guides, drawn in a rest stance. No build yet — `build()` is a stub, so the module registers, draws and round-trips through the document before anything rigs.

**Files:**
- Create: `src/python/tik/trigger/modules/leg/leg.py`
- Test: `tests/integration/trigger/test_leg_trigger.py`

**Interfaces:**
- Consumes: `GuideLayout`, `Input`, `Module`, `register_module` from `tik.trigger.core`
- Produces: module type `"leg"`, class `Leg`, module constants `LIMB_LABELS = ("upper", "lower", "foot")`, `LIMB_GUIDES = ("thigh", "knee", "ankle")`, `FOOT_CONTROLS = ("heel", "ball_spin", "toe", "ball", "toe_wiggle", "bank")`, `NEUTRAL_REACH = 1.4`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/trigger/test_leg_trigger.py`:

```python
"""Leg module: eleven guides, a reverse foot, one IK chain."""

import pytest
from maya import cmds

import tik.maya as tm
from tik.trigger.core import ParentRef, get_module
from tik.trigger.core.manifest import GuideKind
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder


@pytest.fixture
def scene():
    cmds.file(new=True, force=True)
    return GuideScene()


def test_the_leg_declares_eleven_guides():
    leg = get_module("leg")
    assert leg.guides.all_roles == (
        "hip", "thigh", "knee", "ankle", "ball", "toe",
        "heel", "tip", "bank_in", "bank_out", "neutral",
    )


def test_the_foot_markers_are_reference_guides():
    """A marker is read for its position and nothing is shaped like it.

    Reference is also what stops them drawing bones: a reference guide is a
    locator transform, so it suppresses its own bone without suppressing its
    siblings -- four markers under the ankle would otherwise smear a blob.
    """
    layout = get_module("leg").guides
    for role in ("heel", "tip", "bank_in", "bank_out", "neutral"):
        assert layout.kind_for(role) is GuideKind.REFERENCE, role
    for role in ("thigh", "knee", "ankle", "ball", "toe"):
        assert layout.kind_for(role) is GuideKind.JOINT, role
    assert layout.kind_for("hip", is_root=True) is GuideKind.ROOT


def test_only_the_ankle_is_read_for_its_orientation():
    """The chain is oriented by convention; the ankle aligns the foot."""
    assert get_module("leg").guides.oriented == ("ankle",)


def test_drawing_a_leg_creates_all_eleven(scene):
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    for role in get_module("leg").guides.all_roles:
        assert scene.guide_node(leg.instance_id, role) is not None, role


def test_the_neutral_guide_is_collinear_with_hip_and_ankle(scene):
    """Exactly collinear, not approximately.

    The reach network measures the angle between this direction and the
    ankle's; at the guide pose that angle must be exactly zero or no scalar
    value leaves the bind pose alone. The arm measured a hand-written triple
    rounded to one decimal landing 0.006 out -- sixty times the tolerance.
    """
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    hip = scene.guide_node(leg.instance_id, "hip").world_position
    ankle = scene.guide_node(leg.instance_id, "ankle").world_position
    neutral = scene.guide_node(leg.instance_id, "neutral").world_position

    to_ankle = (ankle - hip)
    to_neutral = (neutral - hip)
    to_ankle.normalize()
    to_neutral.normalize()
    assert (to_ankle * to_neutral) == pytest.approx(1.0, abs=1e-6)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
mayapy -m pytest tests/integration/trigger/test_leg_trigger.py -v
```

Expected: FAIL — `get_module("leg")` raises, the module does not exist.

- [ ] **Step 3: Create the module**

Create the folder `src/python/tik/trigger/modules/leg/` and the file `src/python/tik/trigger/modules/leg/leg.py`:

```python
"""Leg module: hip plus a single-IK-chain IK/FK leg with a reverse foot.

The arm's recipe down to the ankle, and then a second solver hierarchy
wrapped *around* it: the reverse foot's pivots sit upstream of the leg's own
IK handle, so rolling onto the toe drags the ankle, the knee and the hip with
it. The foot is not downstream of the limb.

Ribbons and twist live in their own modules. A twist attached to the
``upperleg`` output creates its joints as siblings of the shin, which is
exactly how engine twist bones are structured, so nothing here anticipates
them.
"""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import (
    BoolField,
    ChoiceField,
    FieldGroup,
    FloatField,
    GuideLayout,
    Input,
    Module,
    Vector2Field,
    register_module,
)
from tik.trigger.systems.limb import (
    limb_control_names,
    limb_control_orients,
    limb_control_shapes,
    limb_pivot_controls,
)

LIMB_LOCK = FieldGroup("Limb Lock")
AUTO_HIP = FieldGroup("Auto Hip", collapsed=True)
FOOT = FieldGroup("Foot", collapsed=True)

#: The FK labels ``build()`` passes to the limb. Named once so the manifest
#: and the build cannot disagree.
LIMB_LABELS = ("upper", "lower", "foot")

#: The limb's own three guides, in chain order. The limb system never names a
#: guide, so the anchors for its pivot presets come from here.
LIMB_GUIDES = ("thigh", "knee", "ankle")

#: The reverse foot's controllers, ground up. ``systems/foot.py`` builds them
#: and the module declares them; the two must not drift.
FOOT_CONTROLS = ("heel", "ball_spin", "toe", "ball", "toe_wiggle", "bank")

#: How far past the ankle the ``neutral`` guide sits, as a multiple of the
#: hip-to-ankle distance. Only the direction matters to the reach network;
#: sitting beyond the ankle keeps the guide selectable rather than buried.
NEUTRAL_REACH = 1.4


@register_module("leg", category="limbs")
class Leg(Module):
    """Biped leg: hip, thigh, knee, ankle, ball, toe, and a reverse foot."""

    label = "Leg"
    #: Only the ankle's rotation reaches the rig: the chain is oriented by
    #: convention at build time, so rolling the hip, thigh or knee guide
    #: changes nothing. The ankle's is what aligns the foot to the model.
    guides = GuideLayout(
        "hip",
        "thigh",
        "knee",
        "ankle",
        "ball",
        "toe",
        "heel",
        "tip",
        "bank_in",
        "bank_out",
        "neutral",
        reference=("heel", "tip", "bank_in", "bank_out", "neutral"),
        oriented=("ankle",),
    )
    inputs = (Input("root", primary=True, help="Where the hip hangs (pelvis/body)"),)
    outputs = ("hip", "upperleg", "lowerleg", "foot", "ball", "toe")
    controls = (
        "thigh",
        *limb_control_names(labels=LIMB_LABELS),
        "fk_ball",
        *FOOT_CONTROLS,
    )
    control_shapes = {
        "thigh": "CurvedCircle",
        **limb_control_shapes(labels=LIMB_LABELS),
        # The IK control is a foot, not a cube. Overrides the limb default.
        "ik": "FootPrint",
        "fk_ball": "Circle",
        "heel": "CurvedArrow",
        "ball_spin": "Rotator",
        "toe": "CurvedArrow",
        "ball": "CurvedArrow",
        "toe_wiggle": "Arrow",
        "bank": "DualCurvedArrow",
    }
    control_orients = {
        **limb_control_orients(labels=LIMB_LABELS),
        "fk_ball": (0.0, 0.0, -90.0),
        # Shapes are authored flat in XZ with the normal on +Y. A roll pivot
        # turns about the foot frame's X, so its arrow wants the normal on X:
        # Rz(-90) maps +Y to +X. A spin turns about Z: Rx(90) maps +Y to +Z.
        # A wiggle turns about Y and needs no turn at all.
        #
        # These survive on the right side unconjugated, because every foot
        # control is `mirror="world"` and both feet share one frame.
        "heel": (0.0, 0.0, -90.0),
        "toe": (0.0, 0.0, -90.0),
        "ball": (0.0, 0.0, -90.0),
        "bank": (0.0, 0.0, -90.0),
        "ball_spin": (90.0, 0.0, 0.0),
    }
    #: No entry for ``ik``: the reverse foot already owns that control's
    #: pivot, and offering both would give the animator two pivots on one
    #: node whose corrections do not compose. The foot controls are pivots
    #: themselves, so a movable pivot on one is meaningless.
    pivot_controls = {
        "thigh": "hip",
        **{
            role: guide
            for role, guide in limb_pivot_controls(
                labels=LIMB_LABELS, guides=LIMB_GUIDES
            ).items()
            if role != "ik"
        },
        "fk_ball": "ball",
    }

    stretch = BoolField(True, help="Build the stretch network")
    squash = BoolField(True, help="Build the compress-side network")
    pole_pin = BoolField(False, help="Lock the knee to the pole control")
    lock_from = ChoiceField(
        "thigh",
        choices=("thigh", "hip"),
        label="Lock From",
        group=LIMB_LOCK,
        help="'thigh' displaces the leg chain and leaves the hip on the "
        "pelvis; 'hip' carries the hip joint along too",
    )
    limb_lock = BoolField(
        True,
        label="Limb Lock",
        group=LIMB_LOCK,
        help="Hold the thigh-to-foot distance while the foot anchors. "
        "Inert until the animator raises limbLock.",
    )
    roll_overlap = FloatField(
        10.0,
        min=0.0,
        label="Roll Overlap",
        group=FOOT,
        help="Degrees either side of rollBreak over which the ball hands off "
        "to the toe. 0 is a hard switch.",
    )

    def draw_guides(self, guides) -> None:
        """A rest stance: the chain hangs down, knee pushed forward in +Z.

        The knee's +Z is what makes the bend plane unambiguous -- the same job
        the arm's elbow does with -1 in Z. The four foot markers are siblings
        of the ankle rather than links in a chain, and are reference guides,
        so none of them draws a bone.
        """
        mult = guides.side_mult
        hip_at = (1.0 * mult, 10.4, 0.0)
        ankle_at = (2.0 * mult, 1.0, 0.0)
        hip = guides.joint("hip", hip_at)
        thigh = guides.joint("thigh", (2.0 * mult, 9.6, 0.0), parent=hip)
        knee = guides.joint("knee", (2.0 * mult, 5.3, 0.45), parent=thigh)
        ankle = guides.joint("ankle", ankle_at, parent=knee)
        ball = guides.joint("ball", (2.0 * mult, 0.25, 1.3), parent=ankle)
        guides.joint("toe", (2.0 * mult, 0.05, 2.4), parent=ball)

        # Position-only markers around the shoe. Siblings of the ankle: they
        # describe the foot's footprint, not a chain through it.
        guides.joint("heel", (2.0 * mult, 0.05, -0.6), parent=ankle)
        guides.joint("tip", (2.0 * mult, 0.05, 2.8), parent=ankle)
        guides.joint("bank_in", (1.2 * mult, 0.05, 1.3), parent=ankle)
        guides.joint("bank_out", (2.8 * mult, 0.05, 1.3), parent=ankle)

        # Where the ankle sits when the hip is at rest -- the auto-hip's zero.
        # Derived from the ankle rather than typed as a triple: the reach
        # network measures the angle between this direction and the ankle's,
        # and at the guide pose that angle must be exactly zero.
        neutral_at = tuple(
            start + (end - start) * NEUTRAL_REACH
            for start, end in zip(hip_at, ankle_at)
        )
        guides.joint("neutral", neutral_at, parent=hip)

    def build(self, rig) -> None:
        """Not yet built -- see Tasks 7 and 15."""
        raise NotImplementedError("leg.build lands in Task 7")
```

Note `guides.joint(...)` is used for the reference roles too: `GuideDraft.joint` looks the kind up from the layout, and `reference=(...)` there is what makes them reference guides. `guides.reference()` is for roles no layout declares (framework-made pivot preset guides) and module authors never call it.

- [ ] **Step 4: Run the tests**

```bash
mayapy -m pytest tests/integration/trigger/test_leg_trigger.py -v
```

Expected: PASS for all five. If `test_the_neutral_guide_is_collinear_with_hip_and_ankle` fails, the extrapolation is being rounded somewhere — do not adjust the tolerance, find the rounding.

- [ ] **Step 5: Draw it in Maya and look at it**

The guide pose is a judgement call that a test cannot make. Open Maya, run the Guide Designer, create a leg and check: the chain reads as a leg, the knee bends forward, the four markers sit around the shoe and none of them draws a bone. Adjust the triples in `draw_guides` until it does. Re-run Step 4 afterwards.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/modules/leg tests/integration/trigger/test_leg_trigger.py
git commit -m "Add the leg module's manifest and guides

Eleven roles: six chain joints and five reference markers. Only the
ankle is read for its orientation; the rest of the chain is oriented by
convention at build time. build() is still a stub."
```

---

## Task 7: The bind chain and its orientation

Spec §5.1. The chain is convention-oriented (X to the next joint, Y up, both sides) and the ankle then takes its guide's rotation. **The ankle has children**, which the arm's hand does not — so `ball` and `toe` must be put back after the ankle moves. That is the step this task exists to get right.

**Files:**
- Modify: `src/python/tik/trigger/modules/leg/leg.py`
- Test: `tests/integration/trigger/test_leg_trigger.py`

**Interfaces:**
- Consumes: `conventional_frames`, `derive_size` (Task 2)
- Produces: `Leg.build` creating the six bind joints and the socket. `rig.output(...)` for all six. Later tasks add the limb, the foot and the automation on top.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_leg_trigger.py`:

```python
def _build_leg(scene, side="L", ankle_roll=0.0, **settings):
    """A rigger-authored pose, deliberately not the module's default."""
    body = scene.create_guides(get_module("base")(name="body"))
    leg = scene.create_guides(
        get_module("leg")(name="leg", side=side, settings=settings),
        parent=ParentRef(body.instance_id, "root"),
    )
    mult = -1 if side == "R" else 1
    for role, (x, y, z) in {
        "hip": (1, 10.4, 0),
        "thigh": (2, 9.6, 0),
        "knee": (2, 5.3, 0.45),
        "ankle": (2, 1.0, 0),
        "ball": (2, 0.25, 1.3),
        "toe": (2, 0.05, 2.4),
        "heel": (2, 0.05, -0.6),
        "tip": (2, 0.05, 2.8),
        "bank_in": (1.2, 0.05, 1.3),
        "bank_out": (2.8, 0.05, 1.3),
        "neutral": (1 + 1 * 1.4, 10.4 - 9.4 * 1.4, 0),
    }.items():
        cmds.xform(
            scene.guide_node(leg.instance_id, role).long_name,
            ws=True,
            t=(x * mult, y, z),
        )
    if ankle_roll:
        cmds.xform(
            scene.guide_node(leg.instance_id, "ankle").long_name,
            ws=True,
            ro=(0, 0, ankle_roll),
        )
    report = Builder().build(document=scene.document, afterlife="keep")
    return report.rigs[leg.instance_id]


def test_the_bind_chain_runs_hip_to_toe(scene):
    ctx = _build_leg(scene)
    for name in ("hip", "upperleg", "lowerleg", "foot", "ball", "toe"):
        assert ctx.outputs[name] is not None, name


def test_rolling_the_ankle_guide_leaves_the_ball_aimed_at_the_toe(scene):
    """The step the arm never needed.

    The arm's oriented guide is its LAST joint, so re-aligning it disturbs
    nothing. The ankle has the ball and the toe under it: re-orienting a
    joint rotates everything beneath it, so both have to be put back.
    """
    ctx = _build_leg(scene, ankle_roll=30.0)
    ball = ctx.outputs["ball"]
    toe = ctx.outputs["toe"]

    to_toe = toe.world_position - ball.world_position
    to_toe.normalize()
    ball_x = ball.world_axis("x")
    assert (ball_x * to_toe) == pytest.approx(1.0, abs=1e-4)


def test_the_ankle_takes_the_guide_rotation_the_chain_does_not(scene):
    """The one guide whose rotation is read, and only it."""
    rolled = _build_leg(scene, ankle_roll=30.0)
    foot_z = rolled.outputs["foot"].world_axis("z")

    cmds.file(new=True, force=True)
    flat_scene = GuideScene()
    flat = _build_leg(flat_scene, ankle_roll=0.0)
    flat_z = flat.outputs["foot"].world_axis("z")

    assert (foot_z * flat_z) < 0.99, "the ankle must follow its guide's roll"
    # ...while the knee above it must not have moved.
    assert (
        rolled.outputs["lowerleg"].world_axis("x")
        * flat.outputs["lowerleg"].world_axis("x")
    ) == pytest.approx(1.0, abs=1e-4)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
mayapy -m pytest tests/integration/trigger/test_leg_trigger.py -k bind_chain -v
```

Expected: FAIL with `NotImplementedError: leg.build lands in Task 7`.

- [ ] **Step 3: Implement the chain**

Replace `Leg.build`'s stub. Add `conventional_frames` and `derive_size` to the `systems.limb` import.

```python
    def build(self, rig) -> None:
        """The deform skeleton. Limb, foot and automation land in Task 15."""
        hip_guide = rig.guide("hip")
        limb_guides = rig.guides(*LIMB_GUIDES)
        foot_guides = rig.guides("ball", "toe")

        rig.socket("root", match=hip_guide)

        # deform skeleton -- created in final position, never reparented -----
        hip_jnt = rig.bind_joint("hip", match=hip_guide)
        chain = [hip_jnt]
        parent_joint = hip_jnt
        for label, guide_node in zip(
            ("upperleg", "lowerleg", "foot", "ball", "toe"),
            [*limb_guides, *foot_guides],
        ):
            joint = rig.bind_joint(label, parent=parent_joint, match=guide_node)
            chain.append(joint)
            parent_joint = joint

        # The deform skeleton takes the convention, not the guides' rotations:
        # X to the next joint, Y up. The guides stay world-aligned, which is
        # load-bearing: `build_reach` derives its mirror correction by
        # comparing its own frame's Z against the socket's, and the socket is
        # matched to the hip guide, so orienting that guide would make both
        # terms flip together and silently cancel the correction.
        frames = conventional_frames(
            rig, [joint.world_position for joint in chain]
        )
        # Position *and* rotation, root first: re-orienting a joint rotates
        # everything under it, so each child has to be put back after its
        # parent moves.
        for joint, frame in zip(chain, frames):
            joint.align_to(frame)

        # The ankle is the exception, and the only guide whose rotation is
        # read: it is what aligns the foot to the model.
        chain[3].align_to(limb_guides[-1], position=False)
        # ...and it has children, which the arm's hand does not. Step 3 just
        # rotated the ball and the toe with it, so both go back onto their
        # conventional frames. Omitting this is the single easiest mistake
        # here and it is invisible until a rigger rolls the ankle guide.
        chain[4].align_to(frames[4])
        chain[5].align_to(frames[5])

        tm.delete(frames[0].long_name)

        for name, joint in zip(
            ("hip", "upperleg", "lowerleg", "foot", "ball", "toe"), chain
        ):
            rig.output(name, joint)

        self._bind_chain = chain
        self._size = derive_size(limb_guides)
```

- [ ] **Step 4: Run the tests**

```bash
mayapy -m pytest tests/integration/trigger/test_leg_trigger.py -v
```

Expected: PASS. If `test_rolling_the_ankle_guide_leaves_the_ball_aimed_at_the_toe` fails, the two re-align lines are missing or in the wrong order — the fix is there, not in the tolerance.

- [ ] **Step 5: Delete one re-align line and watch the test catch it**

Temporarily comment out `chain[5].align_to(frames[5])` and re-run. Expected: FAIL. Restore it. A test that cannot fail is not protecting anything.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/modules/leg/leg.py tests/integration/trigger/test_leg_trigger.py
git commit -m "Build the leg's deform skeleton

Convention-oriented hip to toe, with the ankle taking its guide's
rotation. Unlike the arm's hand the ankle has children, so the ball and
the toe are put back onto their conventional frames afterwards."
```

---

## Task 8: The foot frame and the pivot stack

Spec §6.1 and §6.3. The pivot groups only — no controllers, no IK handles, no attributes. The frame is the part that makes the side-multiplier table disappear, so it comes first and alone.

**Files:**
- Create: `src/python/tik/trigger/systems/foot.py`
- Test: `tests/integration/trigger/test_foot_system.py`

**Interfaces:**
- Consumes: `ModuleRig` (`rig.name`, `rig.group`, `rig.groups`, `rig.guide`)
- Produces:
  - `PIVOTS = ("bank_in", "bank_out", "heel", "ball_spin", "toe", "ball_roll", "toe_wiggle")` — creation order is nesting order except `toe_wiggle`, which is a second child of `toe`.
  - `@dataclass FootResult` with fields `frame`, `root`, `pivots: dict[str, tm.Transform]`, `ankle_driver`, `controls: dict[str, object] = {}`, `ball_joints: list = []`, `toe_joints: list = []`.
  - `build_foot_pivots(rig, *, parent, guides: dict) -> FootResult` — `guides` maps `"heel" | "tip" | "ball" | "bank_in" | "bank_out" | "ankle"` to guide nodes. Returns a `FootResult` with `ankle_driver` set.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/trigger/test_foot_system.py`:

```python
"""The reverse foot, driven directly rather than through the leg module."""

import pytest
from maya import cmds

import tik.maya as tm
from tik.trigger.systems import foot as foot_system


def _foot_guides():
    """Left-foot marker positions, matching the leg module's defaults."""
    return {
        role: tm.Joint.create(name="guide_" + role, position=position)
        for role, position in {
            "ankle": (2.0, 1.0, 0.0),
            "ball": (2.0, 0.25, 1.3),
            "heel": (2.0, 0.05, -0.6),
            "tip": (2.0, 0.05, 2.8),
            "bank_in": (1.2, 0.05, 1.3),
            "bank_out": (2.8, 0.05, 1.3),
        }.items()
    }


def test_the_pivots_nest_in_the_documented_order(build_context):
    ctx = build_context("base", name="probe")
    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=_foot_guides())

    expected = [
        ("bank_in", result.root),
        ("bank_out", result.pivots["bank_in"]),
        ("heel", result.pivots["bank_out"]),
        ("ball_spin", result.pivots["heel"]),
        ("toe", result.pivots["ball_spin"]),
        ("ball_roll", result.pivots["toe"]),
        ("toe_wiggle", result.pivots["toe"]),
    ]
    for role, parent in expected:
        assert result.pivots[role].parent.long_name == parent.long_name, role


def test_the_ankle_driver_sits_under_ball_roll(build_context):
    """What build_limb_solve will follow."""
    ctx = build_context("base", name="probe")
    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=_foot_guides())
    assert (
        result.ankle_driver.parent.long_name
        == result.pivots["ball_roll"].long_name
    )


def test_each_pivot_sits_on_its_marker(build_context):
    ctx = build_context("base", name="probe")
    guides = _foot_guides()
    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=guides)

    for pivot_role, guide_role in (
        ("bank_in", "bank_in"),
        ("bank_out", "bank_out"),
        ("heel", "heel"),
        ("ball_spin", "ball"),
        ("toe", "tip"),
        ("ball_roll", "ball"),
        ("toe_wiggle", "ball"),
    ):
        expected = guides[guide_role].world_position
        actual = result.pivots[pivot_role].world_position
        assert actual.distance_to(expected) == pytest.approx(0.0, abs=1e-5), pivot_role


def test_every_pivot_shares_one_frame_aimed_heel_to_tip(build_context):
    """The claim the whole side-multiplier simplification rests on.

    The old module multiplied eight of nine attributes by the side sign and
    then had to exempt two. The cause was the frame: build them all on one
    frame aimed heel-to-tip with the ankle as up, and rx/ry/rz mean the same
    thing on both feet with no multiplier anywhere.
    """
    ctx = build_context("base", name="probe")
    guides = _foot_guides()
    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=guides)

    to_tip = guides["tip"].world_position - guides["heel"].world_position
    to_tip.normalize()
    assert (result.frame.world_axis("z") * to_tip) == pytest.approx(1.0, abs=1e-4)

    reference = result.frame.world_axis("x")
    for role, pivot in result.pivots.items():
        assert (pivot.world_axis("x") * reference) == pytest.approx(
            1.0, abs=1e-4
        ), role
```

- [ ] **Step 2: Run it and watch it fail**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.systems.foot'`.

- [ ] **Step 3: Write the system**

Create `src/python/tik/trigger/systems/foot.py`:

```python
"""Reverse foot: a pivot stack upstream of the leg's own IK handle.

The foot is not downstream of the limb, it is wrapped around it. Rolling onto
the toe has to drag the ankle -- and therefore the knee, and therefore the hip
-- with it, which means these pivots sit between the IK control and the IK
handle. ``systems/limb.py`` opens in the middle for exactly this.

Two parallel hierarchies, and they stay in lockstep by construction::

    rig_grp                          control_grp
      root      <- ik_tweak            bank_ctrl.offset  <- ik_tweak
        bank_in                          bank_ctrl
          bank_out                         heel_ctrl
            heel                             ball_spin_ctrl
              ball_spin                        toe_ctrl
                toe                              ball_ctrl
                  ball_roll                      toe_wiggle_ctrl
                    ankle_driver
                  toe_wiggle

Each controller sits at its pivot's position with the same ancestor chain, so
it inherits its ancestors' rotation exactly as its pivot does. No constraint
runs between the two and no cycle is possible. ``bank`` is the one exception
and §6.4 of the spec says why.

**No side multipliers anywhere.** Every pivot is built on one frame aimed
heel-to-tip with the ankle as up, which points the same way on both feet, so
``rx`` is roll, ``ry`` is spin and ``rz`` is lean on the left and the right
alike. The legacy module's per-attribute multiplier table -- with its two
exemptions for heel roll and toe roll -- was paying for a frame problem one
attribute at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import tik.maya as tm

#: Pivot roles, in creation order. Nesting is each on the one before it,
#: except ``toe_wiggle``, which is a second child of ``toe``.
PIVOTS = (
    "bank_in",
    "bank_out",
    "heel",
    "ball_spin",
    "toe",
    "ball_roll",
    "toe_wiggle",
)

#: Which marker each pivot sits on.
PIVOT_GUIDES = {
    "bank_in": "bank_in",
    "bank_out": "bank_out",
    "heel": "heel",
    "ball_spin": "ball",
    "toe": "tip",
    "ball_roll": "ball",
    "toe_wiggle": "ball",
}


@dataclass
class FootResult:
    """Everything the leg needs after the foot is built."""

    frame: object = None
    root: object = None
    pivots: dict = field(default_factory=dict)
    ankle_driver: object = None
    controls: dict = field(default_factory=dict)
    ball_joints: list = field(default_factory=list)
    toe_joints: list = field(default_factory=list)


def foot_frame(rig, guides: dict, *, parent=None, name: str = "foot"):
    """A static frame aimed heel to tip, with the ankle as up.

    Built from the foot's own geometry rather than from a side convention,
    which is what makes both feet agree. ``aim_at`` bakes plain rotation
    values, so the frame is static once created.
    """
    frame = tm.Transform.create(
        name=rig.name(name, "frame"),
        parent=parent.long_name if parent is not None else rig.groups.rig.long_name,
    )
    frame.snap_to(guides["heel"], rotation=False)
    frame.aim_at(
        guides["tip"],
        aim_vector=(0, 0, 1),
        up_vector=(0, 1, 0),
        world_up_object=guides["ankle"],
    )
    return frame


def build_foot_pivots(rig, *, parent, guides: dict, name: str = "foot") -> FootResult:
    """Build the reverse-foot pivot stack under ``parent``.

    Args:
        rig: The module's ``ModuleRig``.
        parent: What the stack rides -- the limb's IK tweak, or a group
            constrained to it.
        guides: Guide nodes keyed by role. Needs ``ankle``, ``ball``,
            ``heel``, ``tip``, ``bank_in`` and ``bank_out``.
        name: Extra name token.

    Returns:
        A :class:`FootResult` with ``frame``, ``root``, ``pivots`` and
        ``ankle_driver`` filled. Pass ``ankle_driver`` to
        ``build_limb_solve(driver=)``.
    """
    result = FootResult()
    result.frame = foot_frame(rig, guides, name=name)

    result.root = tm.Transform.create(
        name=rig.name(name, "root", suffix="grp"), parent=rig.groups.rig.long_name
    )
    result.root.snap_to(parent)
    tm.MatrixConstraint.create(parent, result.root, maintain_offset=True)

    branch = result.root
    for role in PIVOTS:
        # toe_wiggle is a second child of toe, not a link below ball_roll:
        # it carries the ball and toe handles, so it must bend the toes
        # without moving the leg.
        under = result.pivots["toe"] if role == "toe_wiggle" else branch
        pivot = tm.Transform.create(
            name=rig.name(name, role, suffix="grp"), parent=under.long_name
        )
        pivot.snap_to(guides[PIVOT_GUIDES[role]], rotation=False)
        # Position from the marker, rotation from the shared frame. This is
        # the whole of §6.3.
        pivot.align_to(result.frame, position=False)
        result.pivots[role] = pivot
        if role != "toe_wiggle":
            branch = pivot

    # What the limb solve follows.
    result.ankle_driver = tm.Transform.create(
        name=rig.name(name, "ankleDriver", suffix="grp"),
        parent=result.pivots["ball_roll"].long_name,
    )
    result.ankle_driver.snap_to(guides["ankle"], rotation=False)
    result.ankle_driver.align_to(parent, position=False)
    return result
```

If `Transform.aim_at` does not accept `world_up_object`, check its signature in `src/python/tik/maya/types/transform.py` and use whatever the arm's `draw_guides` uses (it calls `hand.aim_at(beyond, aim_vector=..., up_vector=...)`); build a temporary up locator at the ankle if an up *object* is not supported, and delete it.

- [ ] **Step 4: Run the tests**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py -v
```

Expected: PASS for all four.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/systems/foot.py tests/integration/trigger/test_foot_system.py
git commit -m "Add the reverse-foot pivot stack

Position from each marker, rotation from one frame aimed heel-to-tip
with the ankle as up. That frame points the same way on both feet,
which is what retires the legacy per-attribute side-multiplier table
and its two exemptions."
```

---

## Task 9: The controller chain and the channel sums

Spec §6.2. Six controllers mirroring the pivot stack, each channel summed with its offset group so Task 13's auto-roll has somewhere to land.

**Files:**
- Modify: `src/python/tik/trigger/systems/foot.py`
- Test: `tests/integration/trigger/test_foot_system.py`

**Interfaces:**
- Consumes: `build_foot_pivots` (Task 8), `rig.controller`
- Produces:
  - `CONTROL_CHANNELS: dict[str, dict[str, str]]` — `{control_role: {channel: pivot_role}}`, the single table saying which controller channel drives which pivot channel.
  - `build_foot_controls(rig, result, *, size, guides=None, parent=None, name="foot") -> FootResult` — fills `result.controls`. Each control is `mirror="world"`, `tier="secondary"`. `parent` defaults to `rig.groups.control`; the leg passes its IK control so the chain hangs under it.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_foot_system.py`:

```python
def _built_foot(ctx, size=1.0):
    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    guides = _foot_guides()
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=guides)
    foot_system.build_foot_controls(ctx, result, size=size)
    return result


def test_the_controls_nest_like_the_pivots(build_context):
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    chain = ("bank", "heel", "ball_spin", "toe", "ball", "toe_wiggle")
    for child, parent in zip(chain[1:], chain[:-1]):
        control = result.controls[child]
        assert control.offset.parent.long_name == (
            result.controls[parent].transform.long_name
        ), child


def test_every_foot_control_is_secondary(build_context):
    from tik.trigger.maya import tags

    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    for role, control in result.controls.items():
        assert control.transform.meta.get(tags.TIER) == "secondary", role


def test_a_control_channel_and_its_offset_sum_onto_the_pivot(build_context):
    """The sum is what lets automation and the animator both drive a pivot."""
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)

    result.controls["heel"].transform["rotateX"].value = 20.0
    result.controls["heel"].offset["rotateX"].value = 5.0
    assert result.pivots["heel"]["rotateX"].value == pytest.approx(25.0, abs=1e-4)


def test_every_declared_channel_reaches_its_pivot(build_context):
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    for control_role, channels in foot_system.CONTROL_CHANNELS.items():
        for channel, pivot_role in channels.items():
            if control_role == "bank":
                continue  # two clamps, not a direct sum -- see Task 10
            result.controls[control_role].transform[channel].value = 7.0
            assert result.pivots[pivot_role][channel].value == pytest.approx(
                7.0, abs=1e-4
            ), (control_role, channel)
            result.controls[control_role].transform[channel].value = 0.0
```

- [ ] **Step 2: Run it and watch it fail**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py -k controls -v
```

Expected: FAIL — `AttributeError: module ... has no attribute 'build_foot_controls'`.

- [ ] **Step 3: Add the table and the builder**

Add to `src/python/tik/trigger/systems/foot.py`:

```python
#: Which controller channel drives which pivot channel. The single place the
#: mapping lives -- the proxy names in ``PROXIES`` key off it, so a channel
#: cannot be wired one way and proxied another.
CONTROL_CHANNELS = {
    "bank": {"rotateX": "bank_in"},  # special-cased: two clamped pivots
    "heel": {"rotateX": "heel", "rotateY": "heel"},
    "ball_spin": {"rotateZ": "ball_spin"},
    "toe": {"rotateX": "toe", "rotateY": "toe"},
    "ball": {"rotateY": "ball_roll", "rotateZ": "ball_roll"},
    "toe_wiggle": {"rotateY": "toe_wiggle"},
}

#: Controller nesting, outermost first. Matches the pivot stack so the two
#: hierarchies inherit the same rotation without a constraint between them.
CONTROL_CHAIN = ("bank", "heel", "ball_spin", "toe", "ball", "toe_wiggle")

#: Which PIVOT each controller co-locates with. Pivot roles, not guide
#: roles: the controller has to land exactly where its twin is, and the
#: pivots have already resolved every marker.
CONTROL_GUIDES = {
    "bank": "ball_roll",
    "heel": "heel",
    "ball_spin": "ball_spin",
    "toe": "toe",
    "ball": "ball_roll",
    "toe_wiggle": "toe_wiggle",
}


def build_foot_controls(
    rig, result: FootResult, *, size: float, guides: Optional[dict] = None,
    parent=None, name: str = "foot",
) -> FootResult:
    """Build the controller chain that mirrors the pivot stack.

    Every control is ``mirror="world"``: both feet share one frame, so there
    is nothing to mirror and a behaviour mirror would invert the right foot's
    channels -- which is exactly the bug the legacy multiplier table was
    compensating for.

    ``tier="secondary"`` puts all six behind the rig's ``visibilities_ctrl``,
    so an animator who prefers the proxy attributes never sees them.
    """
    guides = guides if guides is not None else {}
    under = parent if parent is not None else rig.groups.control
    for role in CONTROL_CHAIN:
        control = rig.controller(
            role,
            size=size,
            parent=under,
            mirror="world",
            tier="secondary",
        )
        control.transform.snap_to(result.pivots[CONTROL_GUIDES[role]], rotation=False)
        control.transform.align_to(result.frame, position=False)
        control.offset.snap_to(control.transform)
        control.transform.translate = (0.0, 0.0, 0.0)
        for channel in ("tx", "ty", "tz", "sx", "sy", "sz", "v"):
            plug = control[channel]
            plug.locked = True
            plug.visible = False
        result.controls[role] = control
        under = control

    # The outermost control rides what the pivot stack rides.
    tm.MatrixConstraint.create(
        result.root, result.controls[CONTROL_CHAIN[0]].offset, maintain_offset=True
    )

    for role, channels in CONTROL_CHANNELS.items():
        if role == "bank":
            continue  # two clamped pivots, wired in build_foot_bank
        control = result.controls[role]
        for channel, pivot_role in channels.items():
            summed = control.offset[channel] + control.transform[channel]
            summed >> result.pivots[pivot_role][channel]
    return result
```

Locking translate on each control means the offset group carries the placement — which is correct, and is also what makes `control.offset[channel] + control.transform[channel]` a pure rotation sum.

- [ ] **Step 4: Run the tests**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py -v
```

Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/systems/foot.py tests/integration/trigger/test_foot_system.py
git commit -m "Add the foot's controller chain

Six secondary controls mirroring the pivot stack. Each pivot channel is
the sum of its control's offset group and the control itself, which is
what lets automation and the animator drive the same pivot without the
control drifting off the foot."
```

---

## Task 10: Bank

Spec §6.4. One control channel, two mutually exclusive pivots, two clamps — and no animation curves.

**Files:**
- Modify: `src/python/tik/trigger/systems/foot.py`
- Test: `tests/integration/trigger/test_foot_system.py`

**Interfaces:**
- Consumes: `build_foot_controls` (Task 9)
- Produces: `build_foot_bank(rig, result, *, name="foot") -> FootResult` — wires `bank` control `rotateX` to `bank_out.rotateX = max(v, 0)` and `bank_in.rotateX = min(v, 0)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_foot_system.py`:

```python
def test_positive_bank_rolls_one_edge_and_leaves_the_other(build_context):
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    foot_system.build_foot_bank(ctx, result)

    result.controls["bank"].transform["rotateX"].value = 45.0
    assert result.pivots["bank_out"]["rotateX"].value == pytest.approx(45.0, abs=1e-4)
    assert result.pivots["bank_in"]["rotateX"].value == pytest.approx(0.0, abs=1e-4)

    result.controls["bank"].transform["rotateX"].value = -45.0
    assert result.pivots["bank_out"]["rotateX"].value == pytest.approx(0.0, abs=1e-4)
    assert result.pivots["bank_in"]["rotateX"].value == pytest.approx(-45.0, abs=1e-4)


def test_bank_lays_down_no_animation_curves(build_context):
    """The legacy used setDrivenKeyframe for what is a straight line.

    A build should not author animation curves: they are editable, they
    serialise into the scene, and a rigger who scrubs onto them cannot tell
    they were made by code.
    """
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    foot_system.build_foot_bank(ctx, result)

    for role in ("bank_in", "bank_out"):
        curves = tm.listConnections(
            result.pivots[role]["rotateX"].path, type="animCurve"
        )
        assert not curves, role


def test_bank_is_mirrored_by_the_frame_not_by_a_multiplier(mirrored_pair):
    """Same value, same magnitude, opposite world direction -- no side term."""
    left, right = mirrored_pair("leg", LEG_POSES)
    for ctx in (left, right):
        ctx.controller_by_role("bank").transform["rotateX"].value = 30.0

    left_up = left.outputs["foot"].world_axis("y")
    right_up = right.outputs["foot"].world_axis("y")
    assert left_up[0] == pytest.approx(-right_up[0], abs=1e-3)
    assert left_up[1] == pytest.approx(right_up[1], abs=1e-3)
```

Add near the top of the file:

```python
#: The leg guide pose the mirrored tests build from (left side; the fixture
#: negates X for the right).
LEG_POSES = {
    "hip": (1, 10.4, 0),
    "thigh": (2, 9.6, 0),
    "knee": (2, 5.3, 0.45),
    "ankle": (2, 1.0, 0),
    "ball": (2, 0.25, 1.3),
    "toe": (2, 0.05, 2.4),
    "heel": (2, 0.05, -0.6),
    "tip": (2, 0.05, 2.8),
    "bank_in": (1.2, 0.05, 1.3),
    "bank_out": (2.8, 0.05, 1.3),
    "neutral": (1 + 1 * 1.4, 10.4 - 9.4 * 1.4, 0),
}
```

`test_bank_is_mirrored_by_the_frame_not_by_a_multiplier` needs the full leg build and will not pass until Task 15. Mark it `@pytest.mark.xfail(reason="needs leg.build -- Task 15", strict=True)` now and delete the marker in Task 15's Step 1.

- [ ] **Step 2: Run it and watch it fail**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py -k bank -v
```

Expected: FAIL — no `build_foot_bank`; the mirrored one xfails.

- [ ] **Step 3: Implement it**

Add to `src/python/tik/trigger/systems/foot.py`:

```python
def build_foot_bank(rig, result: FootResult, *, name: str = "foot") -> FootResult:
    """Split the bank control's roll across the two edge pivots.

    Two clamps, not the legacy's pair of set-driven keys: the relationship is
    a straight line, and expressing a straight line as an animation curve
    puts editable, serialising keyframes into a rig nobody keyed.

    **Bank is the one place the two hierarchies are not twins.** One channel
    feeds two mutually exclusive pivots, so there is no single pivot for the
    control to correspond to: it is a handle for a value, and rotating it
    does not tilt it onto the edge the foot banks over. A single pivot whose
    ``rotatePivot`` switched on the sign would restore the correspondence --
    and the switch would be free, because the rotation is zero at the instant
    the sign changes. Rejected for now as cleverness bought against a
    structure the legacy proved in production; this is the note saying where
    to look if the detachment turns out to bother animators.
    """
    channel = result.controls["bank"].transform["rotateX"]
    total = result.controls["bank"].offset["rotateX"] + channel
    total.maximum(0.0) >> result.pivots["bank_out"]["rotateX"]
    total.minimum(0.0) >> result.pivots["bank_in"]["rotateX"]
    return result
```

- [ ] **Step 4: Run the tests**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py -v
```

Expected: PASS, with one xfail.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/systems/foot.py tests/integration/trigger/test_foot_system.py
git commit -m "Split bank across the two edge pivots with clamps

The legacy expressed a straight line as set-driven keyframes. Two
clamps do the same with no curves in the rig."
```

---

## Task 11: The ball and toe puppet chains

Spec §6.5. The limb blends three joints; the foot adds the other two.

**Files:**
- Modify: `src/python/tik/trigger/systems/foot.py`
- Test: `tests/integration/trigger/test_foot_system.py`

**Interfaces:**
- Consumes: `FootResult` (Tasks 8-10), the limb's `LimbResult`
- Produces: `build_foot_chains(rig, result, limb_result, *, guides, bind_joints, size, name="foot") -> FootResult` where `bind_joints` is `[ball_bind, toe_bind]`. Creates the `fk_ball` controller, the IK ball/toe joints and their two `ikSCsolver` handles, and blends both onto the bind joints with `limb_result.switch_plug`. Fills `result.ball_joints` and `result.toe_joints` as `[fk, ik]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_foot_system.py`:

```python
def test_the_ball_and_toe_blend_on_the_limb_switch(scene):
    """One ikFk value covers the whole leg, ankle and foot alike."""
    from tik.trigger.core import ParentRef, get_module
    from tik.trigger.maya import Builder

    body = scene.create_guides(get_module("base")(name="body"))
    leg = scene.create_guides(
        get_module("leg")(name="leg", side="L"),
        parent=ParentRef(body.instance_id, "root"),
    )
    for role, (x, y, z) in LEG_POSES.items():
        cmds.xform(
            scene.guide_node(leg.instance_id, role).long_name, ws=True, t=(x, y, z)
        )
    ctx = Builder().build(document=scene.document, afterlife="keep").rigs[
        leg.instance_id
    ]

    switch = ctx.controller_by_role("ik").transform["ikFk"]
    fk_ball = ctx.controller_by_role("fk_ball")

    switch.value = 0.0
    fk_ball.transform["rotateZ"].value = 25.0
    fk_driven = ctx.outputs["ball"].world_axis("x")

    switch.value = 1.0
    ik_driven = ctx.outputs["ball"].world_axis("x")

    assert (fk_driven * ik_driven) < 0.999, (
        "at ikFk 0 the ball must follow the FK control, at 1 it must not"
    )


def test_ikfk_is_one_switch_for_the_whole_leg(scene):
    """There is no second switch on the foot."""
    from tik.trigger.core import get_module

    assert "ikFk" not in [
        control for control in get_module("leg").controls if control.endswith("Fk")
    ]
```

Both need the full leg build; mark them `@pytest.mark.xfail(reason="needs leg.build -- Task 15", strict=True)` and clear the markers in Task 15.

Also add a direct unit of the system itself, which does not need the module:

```python
def test_the_foot_chains_make_two_sc_handles(build_context):
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    guides = _foot_guides()
    guides["toe"] = tm.Joint.create(name="guide_toe", position=(2.0, 0.05, 2.4))

    from tik.trigger.systems import limb as limb_system

    limb_result = limb_system.build_limb_controls(
        ctx,
        [
            tm.Joint.create(name="lg%d" % index, position=position)
            for index, position in enumerate([(2, 9.6, 0), (2, 5.3, 0.45), (2, 1, 0)])
        ],
        labels=("upper", "lower", "foot"),
    )
    bind = [
        tm.Joint.create(name="bind_ball", position=(2, 0.25, 1.3)),
        tm.Joint.create(name="bind_toe", position=(2, 0.05, 2.4)),
    ]
    foot_system.build_foot_chains(
        ctx, result, limb_result, guides=guides, bind_joints=bind, size=1.0
    )
    assert len(result.ball_joints) == 2
    assert len(result.toe_joints) == 2
    handles = [
        node
        for node in tm.ls(type="ikHandle")
        if "ball" in node or "toe" in node
    ]
    assert len(handles) == 2
```

- [ ] **Step 2: Run it and watch it fail**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py -k chains -v
```

Expected: FAIL — no `build_foot_chains`.

- [ ] **Step 3: Implement it**

Add to `src/python/tik/trigger/systems/foot.py`:

```python
def build_foot_chains(
    rig,
    result: FootResult,
    limb_result,
    *,
    guides: dict,
    bind_joints,
    size: float,
    name: str = "foot",
) -> FootResult:
    """Extend both puppet chains with a ball and a toe, and blend them.

    The limb solves three joints; a foot has five. The two extra joints take
    the same ``ikFk`` switch the limb made, so one value covers the whole leg
    and there is no second switch for an animator to find.

    Args:
        rig: The module's ``ModuleRig``.
        result: The foot, after ``build_foot_controls``.
        limb_result: What ``build_limb_controls`` returned.
        guides: Guide nodes; needs ``ball`` and ``toe``.
        bind_joints: ``[ball_bind, toe_bind]``.
        size: Controller size for ``fk_ball``.
        name: Extra name token.
    """
    ball_at = guides["ball"].world_position
    toe_at = guides["toe"].world_position

    # --- IK side: two SC handles inside the reverse foot -------------------
    ik_ball = tm.Joint.create(
        name=rig.name(name, "ikBall", suffix="jnt"),
        position=ball_at,
        parent=limb_result.ik_joints[-1],
    )
    ik_toe = tm.Joint.create(
        name=rig.name(name, "ikToe", suffix="jnt"), position=toe_at, parent=ik_ball
    )
    tm.Joint.orient_chain([ik_ball, ik_toe], aim_axis="x", up_axis="y")

    ball_handle = tm.IkHandle.create(
        limb_result.ik_joints[-1],
        ik_ball,
        solver="ikSCsolver",
        name=rig.name(name, "ball", suffix="ikHandle"),
    )
    toe_handle = tm.IkHandle.create(
        ik_ball,
        ik_toe,
        solver="ikSCsolver",
        name=rig.name(name, "toe", suffix="ikHandle"),
    )
    for handle in (ball_handle, toe_handle):
        handle.parent = rig.groups.rig
        # Constrained, never parented: toe_wiggle is a controller's twin in
        # rig_grp, and an IK handle under control_grp would break the ground
        # rules. This is the pattern _build_soft_ik already uses.
        tm.MatrixConstraint.create(
            result.pivots["toe_wiggle"],
            handle,
            maintain_offset=True,
            skip_rotate="xyz",
            skip_scale="xyz",
        )

    # --- FK side ----------------------------------------------------------
    fk_ball = tm.Joint.create(
        name=rig.name(name, "fkBall", suffix="jnt"),
        position=ball_at,
        parent=limb_result.fk_joints[-1],
    )
    fk_toe = tm.Joint.create(
        name=rig.name(name, "fkToe", suffix="jnt"), position=toe_at, parent=fk_ball
    )
    tm.Joint.orient_chain([fk_ball, fk_toe], aim_axis="x", up_axis="y")

    fk_control = rig.controller(
        "fk_ball",
        size=size,
        parent=limb_result.fk_controls[-1],
        match=fk_ball,
        mirror="behaviour",
    )
    for channel in ("tx", "ty", "tz", "sx", "sy", "sz", "v"):
        plug = fk_control[channel]
        plug.locked = True
        plug.visible = False
    fk_control["ikFk"].create(proxy=limb_result.switch_plug)
    tm.MatrixConstraint.create(
        fk_control, fk_ball, maintain_offset=True, skip_scale="xyz"
    )

    # --- blend onto the deform skeleton -----------------------------------
    result.ball_joints = [fk_ball, ik_ball]
    result.toe_joints = [fk_toe, ik_toe]
    for index, (fk_joint, ik_joint) in enumerate(
        ((fk_ball, ik_ball), (fk_toe, ik_toe))
    ):
        blend = tm.MatrixBlend.create(
            fk_joint,
            [ik_joint],
            [limb_result.switch_plug],
            name=rig.name(name, "blend%d" % index),
        )
        tm.MatrixConstraint.create(
            blend.output, bind_joints[index], maintain_offset=True
        )
    return result
```

- [ ] **Step 4: Run the direct test**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py::test_the_foot_chains_make_two_sc_handles -v
```

Expected: PASS. The two xfail-marked tests stay xfailed until Task 15.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/systems/foot.py tests/integration/trigger/test_foot_system.py
git commit -m "Extend both puppet chains with a ball and a toe

Two SC handles constrained to the toe_wiggle pivot, an fk_ball control,
and both blended onto the bind joints with the limb's own ikFk switch -
so one value covers the whole leg."
```

---

## Task 12: The nine proxies

Spec §7. The measured behaviour — keying a proxy lands the curve on the source — is what makes the two interfaces one interface.

**Files:**
- Modify: `src/python/tik/trigger/systems/foot.py`
- Test: `tests/integration/trigger/test_foot_system.py`

**Interfaces:**
- Consumes: `result.controls` (Task 9)
- Produces:
  - `PROXIES: tuple[tuple[str, str, str], ...]` — `(attribute_name, control_role, channel)`, ground up.
  - `build_foot_proxies(rig, result, control) -> None` — adds a `foot_` separator on `control` and the nine proxies under it.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_foot_system.py`:

```python
def test_every_proxy_writes_through_to_its_control(build_context):
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    host = ctx.controller("ik", size=1.0, mirror="world")
    foot_system.build_foot_proxies(ctx, result, host)

    for attribute, role, channel in foot_system.PROXIES:
        host.transform[attribute].value = 11.0
        assert result.controls[role].transform[channel].value == pytest.approx(
            11.0, abs=1e-4
        ), attribute
        host.transform[attribute].value = 0.0


def test_a_proxy_reads_back_what_its_control_was_set_to(build_context):
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    host = ctx.controller("ik", size=1.0, mirror="world")
    foot_system.build_foot_proxies(ctx, result, host)

    result.controls["heel"].transform["rotateX"].value = -17.5
    assert host.transform["heelRoll"].value == pytest.approx(-17.5, abs=1e-4)


def test_keying_a_proxy_lands_the_curve_on_the_control(build_context):
    """Measured in Maya on 2026-09-12, and the reason this design works.

    An animator in the channel box and an animator on the controller write
    the same curve. There is nothing to reconcile because there are not two
    of anything.
    """
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    host = ctx.controller("ik", size=1.0, mirror="world")
    foot_system.build_foot_proxies(ctx, result, host)

    cmds.setKeyframe(host.transform.long_name, attribute="heelRoll", time=1)

    on_control = cmds.listConnections(
        result.controls["heel"].transform["rotateX"].path, type="animCurve"
    )
    on_proxy = cmds.listConnections(host.transform["heelRoll"].path, type="animCurve")
    assert on_control, "the curve must land on the control"
    assert not on_proxy, "and not on the proxy"


def test_the_proxy_names_match_the_channel_table():
    """A channel cannot be wired one way and proxied another."""
    wired = {
        (role, channel)
        for role, channels in foot_system.CONTROL_CHANNELS.items()
        for channel in channels
    }
    proxied = {(role, channel) for _name, role, channel in foot_system.PROXIES}
    assert wired == proxied
```

- [ ] **Step 2: Run it and watch it fail**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py -k proxy -v
```

Expected: FAIL — no `build_foot_proxies`.

- [ ] **Step 3: Implement it**

Add to `src/python/tik/trigger/systems/foot.py`:

```python
#: ``(attribute, control role, channel)``, ground up. The names are the
#: legacy module's, shortened to the house style: riggers and animators have
#: the muscle memory and there is no reason to spend it.
PROXIES = (
    ("heelRoll", "heel", "rotateX"),
    ("heelSpin", "heel", "rotateY"),
    ("ballSpin", "ball_spin", "rotateZ"),
    ("toeRoll", "toe", "rotateX"),
    ("toeSpin", "toe", "rotateY"),
    ("ballRoll", "ball", "rotateY"),
    ("ballLean", "ball", "rotateZ"),
    ("toeWiggle", "toe_wiggle", "rotateY"),
    ("bank", "bank", "rotateX"),
)


def build_foot_proxies(rig, result: FootResult, control) -> None:
    """Proxy every foot channel onto ``control``.

    Measured: Maya will proxy a single compound child (``rotateX``) under a
    different long name, the proxy is two-way, and **keying the proxy creates
    the animation curve on the source**. So the channel box and the
    controller are two front ends on one interface, not two interfaces that
    can disagree -- which is why there is no additive offset attribute here.

    Args:
        rig: The module's ``ModuleRig``.
        result: The foot, after ``build_foot_controls``.
        control: The controller the attributes appear on (the leg's IK foot).
    """
    rig.separator(control, "foot_")
    for attribute, role, channel in PROXIES:
        control.transform[attribute].create(
            proxy=result.controls[role].transform[channel]
        )
```

- [ ] **Step 4: Run the tests**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py -v
```

Expected: PASS (two still xfail).

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/systems/foot.py tests/integration/trigger/test_foot_system.py
git commit -m "Proxy the nine foot channels onto the IK control

Not an additive offset: a Maya proxy of a compound child is two-way and
keys onto the source curve, so the channel box and the controller are
one interface with two front ends."
```

---

## Task 13: Auto foot roll

Spec §8. One keyable value walks heel → flat → ball → toe. The maths is a quadratic smooth-min; the naive version drives the toe backwards.

**Files:**
- Modify: `src/python/tik/trigger/systems/foot.py`
- Test: `tests/integration/trigger/test_foot_system.py`

**Interfaces:**
- Consumes: `result.controls` (Task 9)
- Produces: `build_foot_roll(rig, result, control, *, overlap: float, name="foot") -> None` — adds `footRoll` and `rollBreak` (both keyable floats, `rollBreak` default 35.0) to `control` and drives the offset groups of `heel`, `ball` and `toe`.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_foot_system.py`:

```python
def _roll_rig(ctx, overlap):
    result = _built_foot(ctx)
    host = ctx.controller("ik", size=1.0, mirror="world")
    foot_system.build_foot_roll(ctx, result, host, overlap=overlap)
    return result, host


def _sample(result, host, value):
    host.transform["footRoll"].value = value
    return (
        result.controls["heel"].offset["rotateX"].value,
        result.controls["ball"].offset["rotateY"].value,
        result.controls["toe"].offset["rotateX"].value,
    )


def test_a_hard_break_is_exactly_min_and_max(build_context):
    """overlap 0 must be the hard behaviour, not an approximation of it."""
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=0.0)
    host.transform["rollBreak"].value = 30.0

    for value in (0.0, 10.0, 30.0, 55.0, 90.0):
        heel, ball, toe = _sample(result, host, value)
        assert heel == pytest.approx(min(value, 0.0), abs=1e-3), value
        assert ball == pytest.approx(min(value, 30.0), abs=1e-3), value
        assert toe == pytest.approx(max(value - 30.0, 0.0), abs=1e-3), value


def test_outside_the_band_the_overlap_changes_nothing(build_context):
    """The soft version is exact wherever it matters."""
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=10.0)
    host.transform["rollBreak"].value = 30.0

    for value in (0.0, 12.0, 19.9, 40.1, 75.0):
        heel, ball, toe = _sample(result, host, value)
        assert ball == pytest.approx(min(value, 30.0), abs=1e-3), value
        assert toe == pytest.approx(max(value - 30.0, 0.0), abs=1e-3), value


def test_the_toe_starts_before_the_break(build_context):
    """A genuine overlap, not a rounded corner.

    At r == b the ball sits 0.25w short and the toe has taken up that 0.25w.
    """
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=10.0)
    host.transform["rollBreak"].value = 30.0

    heel, ball, toe = _sample(result, host, 30.0)
    assert ball == pytest.approx(30.0 - 0.25 * 10.0, abs=1e-3)
    assert toe == pytest.approx(0.25 * 10.0, abs=1e-3)


def test_the_toe_never_goes_negative(build_context):
    """The bug the naive blend had: toe == -0.78 at r=25, b=30, w=10."""
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=10.0)
    host.transform["rollBreak"].value = 30.0

    for step in range(-90, 91):
        _heel, _ball, toe = _sample(result, host, float(step))
        assert toe >= -1e-4, "toe went backwards at footRoll=%d" % step


def test_the_three_slices_always_sum_to_the_roll(build_context):
    """heel + ball + toe == footRoll, everywhere. The invariant."""
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=10.0)
    host.transform["rollBreak"].value = 30.0

    for value in (-40.0, -5.0, 0.0, 15.0, 29.0, 30.0, 31.0, 60.0):
        heel, ball, toe = _sample(result, host, value)
        assert (heel + ball + toe) == pytest.approx(value, abs=1e-3), value


def test_negative_roll_drives_the_heel_and_nothing_else(build_context):
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=10.0)
    host.transform["rollBreak"].value = 30.0

    heel, ball, toe = _sample(result, host, -25.0)
    assert heel == pytest.approx(-25.0, abs=1e-3)
    assert ball == pytest.approx(0.0, abs=1e-3)
    assert toe == pytest.approx(0.0, abs=1e-3)


def test_the_roll_adds_to_the_animator_s_own_value(build_context):
    """The offset group carries the automation; the control stays theirs."""
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=0.0)
    host.transform["rollBreak"].value = 30.0
    host.transform["footRoll"].value = 20.0
    result.controls["ball"].transform["rotateY"].value = 7.0

    assert result.pivots["ball_roll"]["rotateY"].value == pytest.approx(27.0, abs=1e-3)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py -k roll -v
```

Expected: FAIL — no `build_foot_roll`.

- [ ] **Step 3: Implement it**

Add to `src/python/tik/trigger/systems/foot.py`:

```python
def build_foot_roll(
    rig, result: FootResult, control, *, overlap: float, name: str = "foot"
) -> None:
    """One value walking the foot through heel, flat, ball peel and toe-off.

    ``footRoll`` is sliced three ways and the slices always sum back to it::

        h    = clamp((b - r) / (2w) + 0.5, 0, 1)
        ball = max( lerp(b, r, h) - w*h*(1 - h), 0 )
        heel = min(r, 0)
        toe  = r - ball - heel

    That is a quadratic smooth-minimum. Outside ``[b-w, b+w]`` it is exactly
    ``min(r, b)``; at ``w == 0`` it is the hard break; at ``r == b`` the ball
    sits ``0.25w`` short and the toe has already taken that up, which is what
    makes the handover an *overlap* rather than a rounded corner. ``toe >= 0``
    everywhere, because inside the band ``ball <= r`` reduces to ``b - r <= w``
    -- the band's own definition.

    A blend *toward* the break was tried first and overshoots: at
    ``r=25, b=30, w=10`` it yields ``toe = -0.78``, rolling the toe backwards
    before the break. The smooth-min undershoots, which turns that artefact
    into the feature.

    **The handover at zero stays hard.** The overlap is the ball-to-toe break
    only. At ``footRoll == 0`` the foot is flat and the pivot genuinely
    changes from the heel to the ball; softening it would blend two pivots at
    foot-plant, which reads as the foot sliding exactly where it must not.

    The three slices drive the controls' *offset groups*, never the pivots:
    ``build_foot_controls`` sums offset and control onto each pivot, so the
    automation and the animator's own value add and the controller rides on
    top of the roll instead of drifting off the foot it drives.

    Args:
        rig: The module's ``ModuleRig``.
        result: The foot, after ``build_foot_controls``.
        control: The controller the two attributes appear on.
        overlap: Degrees either side of ``rollBreak``. 0 is a hard switch.
        name: Extra name token.
    """
    rig.separator(control, "roll_")
    roll = control.transform["footRoll"].create("float", default=0.0)
    brk = control.transform["rollBreak"].create("float", default=35.0)

    if overlap <= 0.0:
        # No band: short-circuit rather than divide by zero. This is the
        # exact behaviour the soft form converges to, not an approximation.
        ball = roll.minimum(brk).maximum(0.0)
    else:
        weight = ((brk - roll) / (2.0 * overlap) + 0.5).clamped(0.0, 1.0)
        # lerp(self, other, w) == self + (other - self) * w, so this is
        # lerp(b, r, h) -- b at h=0, r at h=1.
        eased = brk.lerp(roll, weight)
        ball = (eased - weight * (weight * -1.0 + 1.0) * overlap).maximum(0.0)

    heel = roll.minimum(0.0)
    toe = roll - ball - heel

    heel >> result.controls["heel"].offset["rotateX"]
    ball >> result.controls["ball"].offset["rotateY"]
    toe >> result.controls["toe"].offset["rotateX"]
```

`Plug.lerp` is `self + (other - self) * weight`, so `brk.lerp(roll, weight)` is `b + (r - b) * h`. Confirm in `src/python/tik/maya/core/plug.py:1290` before relying on it; if the argument order differs, write the expression out longhand rather than guessing.

- [ ] **Step 4: Run the tests**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py -v
```

Expected: PASS (two still xfail). `test_the_toe_never_goes_negative` sweeps 181 values and is the one that catches a wrong blend direction.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/systems/foot.py tests/integration/trigger/test_foot_system.py
git commit -m "Add auto foot roll with a soft ball-to-toe handover

One keyable value sliced three ways by a quadratic smooth-min, summing
back to itself everywhere. The rigger sets the overlap width; the
animator gets two channels. A blend toward the break overshoots and
drives the toe backwards, which is why this undershoots instead."
```

---

## Task 14: Auto hip, limb lock, and the module's remaining fields

Spec §9.2-9.4. The arm's auto-collar field set renamed, and `build_reach` consumed unchanged.

**Files:**
- Modify: `src/python/tik/trigger/modules/leg/leg.py`
- Test: `tests/integration/trigger/test_leg_trigger.py`

**Interfaces:**
- Consumes: `build_reach`, `ReachAxis` from `tik.trigger.systems.reach`
- Produces: `Leg.auto_hip`, `Leg.auto_hip_lift_angles`, `Leg.auto_hip_lift_degrees`, `Leg.auto_hip_swing_angles`, `Leg.auto_hip_swing_degrees`, `Leg.auto_hip_interpolation`; `Leg._lift_axis()`, `Leg._swing_axis()`, `Leg.validate()`.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_leg_trigger.py`:

```python
def test_auto_hip_is_inert_at_the_guide_pose(scene):
    """The neutral is where the leg is drawn, so zero must mean zero.

    If this fails the neutral guide is not collinear with hip-to-ankle and
    every auto-hip value starts by moving the rig off its own bind pose.
    """
    ctx = _build_leg(scene, auto_hip=True)
    thigh = ctx.controller_by_role("thigh")
    for channel in ("rotateX", "rotateY", "rotateZ"):
        assert thigh.offset[channel].value == pytest.approx(0.0, abs=1e-3), channel


def test_auto_hip_off_builds_no_reach_network(scene):
    ctx = _build_leg(scene, auto_hip=False)
    assert not [
        node for node in tm.ls(type="remapValue") if "autoHip" in node
    ]


def test_a_bad_auto_hip_range_is_a_validation_problem():
    leg = get_module("leg")(name="leg", settings={"auto_hip_lift_angles": (10.0, 75.0)})
    problems = leg.validate()
    assert any("auto hip lift" in problem for problem in problems)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
mayapy -m pytest tests/integration/trigger/test_leg_trigger.py -k auto_hip -v
```

Expected: FAIL — the settings do not exist.

- [ ] **Step 3: Add the fields, the axes and validation**

Add to `Leg` in `src/python/tik/trigger/modules/leg/leg.py`, after `limb_lock`. These mirror the arm's auto-collar exactly; the angle limits stay inside ±89 because the driver's off-plane angles saturate at 90, so a wider limit is never reached.

```python
    auto_hip = BoolField(True, help="Build the auto-hip network", group=AUTO_HIP)
    auto_hip_lift_angles = Vector2Field(
        (-55.0, 70.0),
        min=-89.0,
        max=89.0,
        labels=("Lower", "Upper"),
        label="Lift Angles",
        group=AUTO_HIP,
        help="Leg elevation either side of the neutral guide at full falloff. "
        "Both stay inside +/-89: the driver's off-plane angles saturate "
        "at 90, so a wider limit is never reached.",
    )
    auto_hip_lift_degrees = Vector2Field(
        (-4.0, 12.0),
        min=-90.0,
        max=90.0,
        labels=("Lower", "Upper"),
        label="Lift Degrees",
        group=AUTO_HIP,
        help="Hip rotation at each of those angles.",
    )
    auto_hip_swing_angles = Vector2Field(
        (-40.0, 55.0),
        min=-89.0,
        max=89.0,
        labels=("Back", "Front"),
        label="Swing Angles",
        group=AUTO_HIP,
        help="Leg azimuth either side of the neutral guide at full falloff.",
    )
    auto_hip_swing_degrees = Vector2Field(
        (-4.0, 8.0),
        min=-90.0,
        max=90.0,
        labels=("Back", "Front"),
        label="Swing Degrees",
        group=AUTO_HIP,
        help="Hip rotation at each of those angles.",
    )
    auto_hip_interpolation = ChoiceField(
        "smooth",
        choices=("linear", "smooth", "spline"),
        label="Auto Hip Interpolation",
        group=AUTO_HIP,
        help="Only 'smooth' is free of a slope discontinuity: 'linear' kinks "
        "at the neutral and both limits, 'spline' kinks at both limits.",
    )

    def _lift_axis(self) -> ReachAxis:
        # Component order is (min, max), matching ReachAxis's first two and
        # last two arguments.
        return ReachAxis(*self.auto_hip_lift_angles, *self.auto_hip_lift_degrees)

    def _swing_axis(self) -> ReachAxis:
        return ReachAxis(*self.auto_hip_swing_angles, *self.auto_hip_swing_degrees)

    def validate(self) -> list[str]:
        """The base checks plus the auto-hip axis ranges."""
        problems = super().validate()
        if self.auto_hip:
            for label, axis in (
                ("lift", self._lift_axis()),
                ("swing", self._swing_axis()),
            ):
                try:
                    axis.validate("auto hip %s" % label)
                except ValueError as error:
                    problems.append(str(error))
        return problems
```

Add to the imports: `from tik.trigger.systems.reach import ReachAxis, build_reach`.

- [ ] **Step 4: Run the validation test only**

```bash
mayapy -m pytest tests/integration/trigger/test_leg_trigger.py::test_a_bad_auto_hip_range_is_a_validation_problem -v
```

Expected: PASS. The two build-time auto-hip tests still fail — `build()` does not wire reach yet; Task 15 does.

- [ ] **Step 5: Commit**

```bash
make lint
git add src/python/tik/trigger/modules/leg/leg.py tests/integration/trigger/test_leg_trigger.py
git commit -m "Add the leg's auto-hip fields and validation

The arm's auto-collar field set renamed. build_reach's own docstring
already said the same system serves a hip."
```

---

## Task 15: Assemble the leg

Spec §9. The limb in two phases with the foot between them, then reach and limb lock. This is where every previous task becomes one rig.

**Files:**
- Modify: `src/python/tik/trigger/modules/leg/leg.py`
- Test: `tests/integration/trigger/test_leg_trigger.py`, `tests/integration/trigger/test_foot_system.py`

**Interfaces:**
- Consumes: everything from Tasks 3, 7-14
- Produces: a complete `leg` module. No new public names.

- [ ] **Step 1: Clear the xfail markers**

Delete the `@pytest.mark.xfail(...)` decorators added in Tasks 10 and 11:
`test_bank_is_mirrored_by_the_frame_not_by_a_multiplier`, `test_the_ball_and_toe_blend_on_the_limb_switch`, `test_ikfk_is_one_switch_for_the_whole_leg`. They are `strict=True`, so once `build()` works they fail *as xpass* until the markers go — which is the reminder to remove them.

Then add the whole-rig invariant to `tests/integration/trigger/test_leg_trigger.py`:

```python
def test_the_bind_pose_is_exact_with_every_automation_full_on(scene):
    """Every automation built, every default in place: nothing has moved.

    The arm's own tolerance. A leg that does not reproduce the pose its
    guides describe has an automation whose zero is not zero, and every
    later measurement then reads a pose error rather than the feature.
    """
    ctx = _build_leg(
        scene,
        stretch=True,
        squash=True,
        limb_lock=True,
        auto_hip=True,
        pole_pin=True,
    )
    for name, guide_role in (
        ("upperleg", "thigh"),
        ("lowerleg", "knee"),
        ("foot", "ankle"),
        ("ball", "ball"),
        ("toe", "toe"),
    ):
        expected = scene.guide_node(
            ctx.instance.instance_id, guide_role
        ).world_position
        actual = ctx.outputs[name].world_position
        assert actual.distance_to(expected) == pytest.approx(0.0, abs=1e-4), name
```

- [ ] **Step 2: Run and watch them fail**

```bash
mayapy -m pytest tests/integration/trigger/test_foot_system.py tests/integration/trigger/test_leg_trigger.py -v
```

Expected: FAIL — `build()` stops after the bind chain.

- [ ] **Step 3: Finish `build()`**

Extend `Leg.build` in `src/python/tik/trigger/modules/leg/leg.py`. Replace the trailing `self._bind_chain = chain` / `self._size = derive_size(...)` lines from Task 7 with the full assembly:

```python
        size = derive_size(limb_guides)
        socket = rig.socket("root", match=hip_guide)   # already created above

        # Two places the lock can push, both inert pass-throughs otherwise.
        # `hang_from` carries the hip with it; `limb_from` moves only the leg
        # chain, leaving the pelvis alone. build_limb_lock owns the
        # translation of whichever one it targets, so only the other gets a
        # full constraint here.
        locks_hip = self.limb_lock and self.lock_from == "hip"
        hang_from = rig.group("lock", "hip", under="socket")
        hang_from.snap_to(socket)
        if not locks_hip:
            tm.MatrixConstraint.create(socket, hang_from, maintain_offset=True)

        # hip control ------------------------------------------------------
        thigh_ctrl = rig.controller(
            "thigh", size=size, match=chain[0], mirror="behaviour"
        )
        tm.MatrixConstraint.create(
            hang_from, thigh_ctrl.offset, maintain_offset=True
        )
        tm.MatrixConstraint.create(thigh_ctrl, chain[0], maintain_offset=True)
        for channel in ("sx", "sy", "sz", "v"):
            plug = thigh_ctrl[channel]
            plug.locked = True
            plug.visible = False

        limb_from = rig.group("lock", "limb", under="rig")
        limb_from.snap_to(thigh_ctrl.transform)
        if locks_hip or not self.limb_lock:
            tm.MatrixConstraint.create(
                thigh_ctrl, limb_from, maintain_offset=True
            )

        # the limb, opened in the middle for the foot ----------------------
        limb = build_limb_controls(
            rig,
            limb_guides,
            parent=limb_from,
            controller_size=size,
            labels=LIMB_LABELS,
        )

        foot_guides = {
            role: rig.guide(role)
            for role in ("ankle", "ball", "toe", "heel", "tip", "bank_in", "bank_out")
        }
        foot = build_foot_pivots(
            rig, parent=limb.ik_tweak.transform, guides=foot_guides
        )
        build_foot_controls(
            rig, foot, size=size * 0.35, parent=limb.ik_control
        )
        build_foot_bank(rig, foot)

        # The solve follows the bottom of the pivot stack, not the tweak:
        # that is what makes rolling onto the toe drag the ankle, the knee
        # and the hip with it.
        build_limb_solve(
            rig,
            limb,
            driver=foot.ankle_driver,
            bind_joints=chain[1:4],
            soft_ik=True,  # never optional for an IK solution
            stretch=self.stretch,
            squash=self.squash,
            pole_pin=self.pole_pin,
        )

        build_foot_chains(
            rig,
            foot,
            limb,
            guides=foot_guides,
            bind_joints=chain[4:6],
            size=size * 0.5,
        )
        build_foot_proxies(rig, foot, limb.ik_control)
        build_foot_roll(
            rig, foot, limb.ik_control, overlap=float(self.roll_overlap)
        )

        if self.auto_hip:
            reach = build_reach(
                rig,
                thigh_ctrl.offset,
                thigh_ctrl.transform,
                hang_from,
                tuple(rig.guide("neutral").world_position),
                limb.ik_tweak.transform,
                limb.ik_control.transform,
                lift=self._lift_axis(),
                swing=self._swing_axis(),
                fk_controls=limb.fk_controls,
                switch_plug=limb.switch_plug,
                prefix="autoHip",
                interpolation=self.auto_hip_interpolation,
                name="hip",
            )
            # Relative, so set_parent writes no compensation into the
            # channels: `align` already carries the hip's own orientation.
            thigh_ctrl.transform.set_parent(reach.align, relative=True)

        if self.limb_lock:
            # Built last because it needs the limb's IK tweak; lock_root
            # still reads the raw socket, which keeps the graph acyclic.
            target, follows = (
                (hang_from, socket) if locks_hip else (limb_from, thigh_ctrl)
            )
            build_limb_lock(
                rig,
                socket=socket,
                chain_root=limb.ik_joints[0],
                driver=limb.ik_tweak.transform,
                control=limb.ik_control,
                target=target,
                follows=follows,
            )
```

`build_reach` reads `limb.ik_tweak`, which is **upstream** of the foot stack the solve follows — so there is no cycle, the same relationship the arm has. Add the imports:

```python
from tik.trigger.systems.foot import (
    build_foot_bank,
    build_foot_chains,
    build_foot_controls,
    build_foot_pivots,
    build_foot_proxies,
    build_foot_roll,
)
from tik.trigger.systems.limb import build_limb_controls, build_limb_solve
from tik.trigger.systems.limb_lock import build_limb_lock
```

Keep the single `rig.socket("root", match=hip_guide)` call from Task 7 and assign it to `socket`; do not call it twice.

- [ ] **Step 4: Run both new files**

```bash
mayapy -m pytest tests/integration/trigger/test_leg_trigger.py tests/integration/trigger/test_foot_system.py -v
```

Expected: PASS, no xfail and no xpass.

- [ ] **Step 5: Run the ground rules**

```bash
mayapy -m pytest tests/integration/trigger/test_module_ground_rules.py -v
```

Expected: PASS. `leg` is picked up automatically by `_shipped_module_types()` after Task 1. The likely failure is `test_every_module_declares_exactly_the_controllers_it_builds` — fix the `controls` tuple or the build, not the test. Remember tweaks and `*_pivot` controllers are excluded by construction.

- [ ] **Step 6: Run everything**

```bash
make tests-unit
make tests-integration
make tests-ui
```

Expected: PASS.

- [ ] **Step 7: Drive it in Maya**

Tests cannot tell you a foot feels right. In a live Maya: build a leg, switch `ikFk`, sweep `footRoll` from -40 to 80 and watch the heel, ball and toe hand over; set `rollBreak` to 20 and to 50 and check the peel moves; bank both ways; turn on the secondary controls in `visibilities_ctrl` and confirm the six handles sit on the foot and move with it. Build a right leg and check both roll the same way.

- [ ] **Step 8: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/modules/leg/leg.py tests/integration/trigger
git commit -m "Assemble the leg: limb, reverse foot, auto hip and limb lock

The limb is built in two phases with the foot between them, so the IK
solve follows the bottom of the pivot stack and rolling onto the toe
drags the ankle, the knee and the hip with it."
```

---

## Task 16: The icon and the docs

Spec §12 and `AI/icon_rules.md`. A module without an icon falls back to a generated chip; dropping in a correctly-named file is the entire integration.

**Files:**
- Create: `src/python/tik/trigger/modules/leg/leg.svg`
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-09-12-leg-module-and-foot-system-design.md`

**Interfaces:**
- Consumes: nothing
- Produces: nothing importable

- [ ] **Step 1: Draw the icon**

Module icons are nouns: one flat colour, `stroke-width="1.35"`, no rim, no fill on the bones, filled joint dots, on a `viewBox="0 0 24 24"` grid. The glyph must depict the module's **actual** topology — `arm.svg` is a three-joint bend. A leg is a four-joint bend with a foot: thigh, knee, ankle, then a short forward segment for the toe.

Create `src/python/tik/trigger/modules/leg/leg.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="none" stroke="#93a8c4" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"><path d="M9.4 3.6 L12.4 11.2 L9.2 18.2 L16.4 19.4"/><g fill="#93a8c4" stroke="none"><circle cx="9.4" cy="3.6" r="1.9"/><circle cx="12.4" cy="11.2" r="1.9"/><circle cx="9.2" cy="18.2" r="1.9"/><circle cx="16.4" cy="19.4" r="1.9"/></g></g></svg>
```

No `<filter>`, `<mask>`, `<text>`, `<foreignObject>`, `<use>`, `currentColor` or `@import` — Qt's Tiny 1.2 profile ignores all of them silently, so the file would look right in a browser and render blank in Maya.

- [ ] **Step 2: Run the icon lint**

```bash
mayapy -m pytest tests/unit/test_icon_assets.py -v
```

Expected: PASS, with `leg` now among the parametrised modules.

- [ ] **Step 3: Look at it at 16px**

The pipeline tree renders at 16px. Open the Guide Designer's module palette and confirm the leg reads as a leg next to `arm` and `fkchain`. Adjust the path if it does not.

- [ ] **Step 4: Update `CLAUDE.md`**

In the `### tik.trigger (IN DEVELOPMENT)` block, update the module list from `base`/`control`/`fkchain`/`arm`/`twist`/`ribbon` to include `leg`, and add a sentence after the arm's description:

> The **leg** is the arm's recipe to the ankle and then a reverse foot wrapped *around* it: the pivot stack sits upstream of the leg's own IK handle, which is why `build_ikfk_limb` splits into `build_limb_controls` and `build_limb_solve(driver=)`. Every foot behaviour has both a secondary controller and a proxy attribute on the IK control — measured, a Maya proxy of a compound child keys onto the source curve, so the two are one interface with two front ends. `footRoll` walks heel → ball → toe from one channel, with the ball-to-toe overlap a rigger field rather than an animator attribute.

Add to the **Design specs** list, newest first:

> `docs/superpowers/specs/2026-09-12-leg-module-and-foot-system-design.md` (the leg and the foot system: the limb seam, the two parallel hierarchies, why the legacy side-multiplier table disappears, the proxy interface and the auto-roll smooth-min; **amends the trigger-simplification spec's limb entry point**)

Add to the **tik.trigger Tests** list:

> - `tests/integration/trigger/test_foot_system.py` — the reverse foot: pivot nesting, the shared frame, bank, the proxies and the roll sweep; `tests/integration/trigger/test_leg_trigger.py` — the leg end to end

- [ ] **Step 5: Close the spec out**

In the spec's header change `**Status:** designed` to `**Status:** implemented`, and add under §11.2 a fifth entry:

> 5. `rig.controller` conjugated a shape orient for every right-side control, ignoring `mirror=`. Found while planning; fixed in the same work. The arm never hit it because `limb_control_orients` omits every world-aligned role.

- [ ] **Step 6: Full suite and commit**

```bash
make lint
make tests-unit && make tests-integration && make tests-ui
git add src/python/tik/trigger/modules/leg/leg.svg CLAUDE.md docs/superpowers/specs
git commit -m "Add the leg icon and close out the spec

A four-joint bend with a foot, per the module icon grammar."
```

---

## Done

At this point: `leg` is registered, draws eleven guides, builds standalone and under a base, passes every ground rule, and ships a foot with six secondary controls, nine proxies and a one-channel auto roll. `arm` is unchanged in behaviour and its tests never moved.

Spec §11.3 lists five gaps this work surfaced and deliberately did not close — the shared limb-module recipe, a `rig.proxy` helper, rigger-facing tiers, an `align_chain` helper for the oriented-guide trap, and quadruped support. Each is its own conversation.
