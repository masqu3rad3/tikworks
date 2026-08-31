# Auto-Collar Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the auto-collar's unsigned-angle-plus-aim-blend driver with
a signed, two-axis, saturating driver whose neutral is authored by a guide.

**Architecture:** A static orthonormal frame at the collar pivot, aimed at a
new `neutral` guide, makes both axis neutrals exactly zero by construction.
A probe under that frame gives the collar-root-to-wrist direction (from
`ik_tweak` in IK, from a product of the FK controls' local matrices in FK,
blended by the `ikFk` switch). Two off-plane `atan2` strands turn that
direction into signed elevation and azimuth, and one three-point
`remapValue` per axis maps authored angle limits onto authored output
degrees, clamping past them and staying C1 at the neutral and at both
limits.

**Tech Stack:** Python 3.10+, Maya 2024+ (core `atan2`, `distanceBetween`,
`multMatrix`, `translationFromMatrix`, `blendColors`, `remapValue`),
tik.maya wrappers, pytest under `mayapy`.

**Spec:** `docs/superpowers/specs/2026-08-31-auto-collar-redesign-design.md`

## Global Constraints

- **Never call `maya.cmds`, `OpenMaya` or `pymel` directly** outside
  `src/python/tik/maya/`. Module and system code consumes tik.maya only.
  Inside tik.maya, raw `cmds` is fine.
- **`tik/trigger/core` is pure Python** — no Maya, no Qt. Enforced by
  `tests/unit/test_import_boundaries.py`. Nothing in this plan touches it
  except `core/manifest.py` field declarations, which are already pure.
- **Modules never inherit from other modules.** Shared behaviour lives in
  `tik/trigger/systems/`.
- **The system names no animator-facing attribute.** `reach.py` takes a
  `prefix` from the caller; `arm.py` supplies `"autoCollar"`.
- **No third-party dependencies.** Stdlib and Maya-bundled modules only.
- Run unit tests with `make tests-unit`, integration with
  `make tests-integration`. Both go through `mayapy`.
- Commit after every task. Branch is `TW-6-Trigger-structuring`; do not
  push, reset, or checkout.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/python/tik/maya/constructs/remap.py` | `remapValue` wrapper | Modify: multi-point ramps |
| `src/python/tik/trigger/guides/scene.py` | Guide scene I/O | Modify: fill declared-but-missing roles on import |
| `src/python/tik/trigger/systems/reach.py` | The reach mechanism | Rewrite |
| `src/python/tik/trigger/modules/arm/arm.py` | Arm module | Modify: neutral guide, fields, validate, wiring |
| `tests/unit/test_remap_maya.py` | `Remap` ramp points | Create or extend |
| `tests/unit/test_guides_trigger.py` | Guide import | Modify: missing-role test |
| `tests/unit/test_core_trigger.py` | Field/validate schemas | Modify: new validate rules |
| `tests/integration/trigger/test_reach_system.py` | Reach against a scene | Rewrite |
| `tests/integration/trigger/test_arm_trigger.py` | Arm end to end | Modify: auto-collar tests |

---

### Task 1: `Remap` gains multi-point ramps

**Files:**
- Modify: `src/python/tik/maya/constructs/remap.py:26-72`
- Test: `tests/unit/test_remap_maya.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Remap.create(..., points: Optional[Sequence[tuple[float, float]]] = None)`.
  Each pair is `(position, value)` in normalised 0..1 ramp space. `None`
  keeps today's two-point `[(0.0, 0.0), (1.0, 1.0)]` behaviour. All points
  get the same `interpolation`. Raises `ValueError` for fewer than two
  points or for any coordinate outside `0..1`.

- [ ] **Step 1: Write the failing test**

Find the existing `Remap` unit tests first — `grep -rn "Remap" tests/unit/`
— and add to that file rather than creating a second one. If none exists,
create `tests/unit/test_remap_maya.py` with the imports the neighbouring
unit tests use.

```python
import pytest

import tik.maya as tm
from tik.maya.constructs.remap import INTERPOLATIONS


def _ramp(remap, index):
    node = remap.node
    return (
        node[f"value[{index}].value_Position"].value,
        node[f"value[{index}].value_FloatValue"].value,
        node[f"value[{index}].value_Interp"].value,
    )


def test_default_ramp_is_unchanged(maya_scene):
    remap = tm.Remap.create(0.0, input_min=0.0, input_max=1.0)
    assert _ramp(remap, 0) == (0.0, 0.0, INTERPOLATIONS["smooth"])
    assert _ramp(remap, 1) == (1.0, 1.0, INTERPOLATIONS["smooth"])


def test_three_points_land_on_the_ramp(maya_scene):
    remap = tm.Remap.create(
        0.0,
        input_min=-40.0,
        input_max=60.0,
        output_min=-8.0,
        output_max=22.0,
        interpolation="smooth",
        points=[(0.0, 0.0), (0.4, 8.0 / 30.0), (1.0, 1.0)],
    )
    assert _ramp(remap, 0) == (0.0, 0.0, INTERPOLATIONS["smooth"])
    position, value, interp = _ramp(remap, 1)
    assert abs(position - 0.4) < 1e-6
    assert abs(value - 8.0 / 30.0) < 1e-6
    assert interp == INTERPOLATIONS["smooth"]
    assert _ramp(remap, 2) == (1.0, 1.0, INTERPOLATIONS["smooth"])


def test_the_middle_point_makes_zero_land_on_zero(maya_scene):
    """The whole reason the argument exists."""
    remap = tm.Remap.create(
        0.0,
        input_min=-40.0,
        input_max=60.0,
        output_min=-8.0,
        output_max=22.0,
        points=[(0.0, 0.0), (0.4, 8.0 / 30.0), (1.0, 1.0)],
    )
    assert abs(remap.output.value) < 1e-4


def test_clamps_rather_than_extrapolates(maya_scene):
    remap = tm.Remap.create(
        120.0, input_min=-40.0, input_max=60.0, output_min=-8.0, output_max=22.0
    )
    assert abs(remap.output.value - 22.0) < 1e-4
    remap.node["inputValue"].value = -200.0
    assert abs(remap.output.value + 8.0) < 1e-4


def test_rejects_a_single_point(maya_scene):
    with pytest.raises(ValueError):
        tm.Remap.create(0.0, input_min=0.0, input_max=1.0, points=[(0.0, 0.0)])


def test_rejects_an_out_of_range_point(maya_scene):
    with pytest.raises(ValueError):
        tm.Remap.create(
            0.0, input_min=0.0, input_max=1.0, points=[(0.0, 0.0), (1.5, 1.0)]
        )
```

Use whatever scene fixture the neighbouring unit tests use in place of
`maya_scene` — check the file's existing signatures and match them.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `make tests-unit`
Expected: FAIL — `Remap.create() got an unexpected keyword argument 'points'`
on the three-point tests. `test_default_ramp_is_unchanged`,
`test_clamps_rather_than_extrapolates` and `test_the_middle_point...`'s
sibling may already pass; that is fine, they are the regression net.

- [ ] **Step 3: Implement the `points` argument**

In `src/python/tik/maya/constructs/remap.py`, add `Sequence` to the typing
import, add the parameter to the signature after `interpolation`:

```python
        interpolation: str = "smooth",
        points: Optional[Sequence[tuple[float, float]]] = None,
        name: Optional[str] = None,
```

document it in the docstring:

```
            points: Optional ramp shape as ``(position, value)`` pairs in
                normalised 0..1 space. Defaults to a straight two-point
                ramp. Every point takes ``interpolation``.
```

and replace the ramp-writing loop (currently lines 67-71) with:

```python
        ramp = list(points) if points is not None else [(0.0, 0.0), (1.0, 1.0)]
        if len(ramp) < 2:
            raise ValueError("A ramp needs at least two points.")
        for position, value in ramp:
            if not 0.0 <= position <= 1.0 or not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"Ramp point ({position}, {value}) is outside 0..1."
                )
        # The ramp points carry the curve shape.
        for index, (position, value) in enumerate(ramp):
            node[f"value[{index}].value_Position"].value = position
            node[f"value[{index}].value_FloatValue"].value = value
            node[f"value[{index}].value_Interp"].value = INTERPOLATIONS[interpolation]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `make tests-unit`
Expected: PASS, and no other unit test regresses.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/maya/constructs/remap.py tests/unit/test_remap_maya.py
git commit -m "feat(tik.maya): Remap takes an explicit ramp shape

A three-point ramp is what lets one remapValue span a signed input range
and still put zero on zero. Defaults to today's two-point ramp."
```

---

### Task 2: `.trg` import fills declared-but-missing guide roles

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py:266-305`
- Test: `tests/unit/test_guides_trigger.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `GuideScene.import_guide_instances` creates any fixed role in
  `module_cls.guides.roles` that the record omits, at the position
  `draw_guides` would have given it, parented as `draw_guides` parented it.
  No public signature change.

**Why:** without this, adding the `neutral` role in Task 6 makes
`rig.guide("neutral")` raise `GuideError` on every existing `.trg`
(`trigger/maya/rig.py:188-194`). The import path diverging from the
manifest is the underlying defect; `guide_attrs` already degrade correctly
(`guides/scene.py:282-287`), so guides are catching up.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_guides_trigger.py`. Match the file's existing
fixtures and its toy-module imports from `tests/helpers/toy_modules.py`;
add a toy module there with three fixed roles if none has more than two.

```python
def test_import_creates_a_role_the_record_omits(guide_scene):
    """An older .trg predates a role the module now declares."""
    module = ToyThreeGuideModule(name="probe", side=Side.LEFT)
    instance = guide_scene.create_guides(module)
    records = guide_scene.export_guide_instances([instance])
    guide_scene.delete_guides(instance.instance_id)

    dropped = records[0]
    missing_key = [key for key in dropped.joints if key[0] == "tip"][0]
    expected = tuple(dropped.joints[missing_key]["position"])
    del dropped.joints[missing_key]

    rebuilt = guide_scene.import_guide_instances([dropped])[0]
    nodes = guide_scene.guide_nodes(rebuilt.instance_id)
    assert ("tip", 0) in nodes
    actual = tuple(nodes[("tip", 0)].world_position)
    assert all(abs(a - b) < 1e-4 for a, b in zip(actual, expected))
```

Adjust `ToyThreeGuideModule`, `guide_scene`, `export_guide_instances` and
`guide_nodes` to the names the file actually uses — read the file first and
follow it exactly. The assertion that matters is: a role absent from the
record exists after import, at its `draw_guides` position.

- [ ] **Step 2: Run the test to verify it fails**

Run: `make tests-unit`
Expected: FAIL — `KeyError` or an assertion that `("tip", 0)` is absent.

- [ ] **Step 3: Implement the fill**

Add this helper to `GuideScene`, above `import_guide_instances`:

```python
    def _missing_role_layout(self, module, present_roles) -> dict:
        """Where ``draw_guides`` would put roles the record does not carry.

        Drawn into a throwaway group and deleted, because the module owns
        its own layout and nothing else knows those positions.
        """
        missing = [
            role for role in module.guides.roles if role not in present_roles
        ]
        if not missing:
            return {}
        scratch = tm.Transform.create(name="trg_import_scratch_GRP")
        try:
            draft = GuideDraft(module, scratch, None)
            module.draw_guides(draft)
            role_of = {
                joint.long_name: role
                for (role, index), joint in draft.created.items()
                if index == 0
            }
            layout = {}
            for role in missing:
                joint = draft.created.get((role, 0))
                if joint is None:
                    continue
                parent = joint.parent
                layout[role] = {
                    "position": tuple(joint.world_position),
                    "radius": joint["radius"].value,
                    "parent_role": (
                        role_of.get(parent.long_name) if parent is not None else None
                    ),
                }
            return layout
        finally:
            scratch.delete()
```

If `Transform` has no `delete()`, use whatever the neighbouring code in
this file uses to remove a node — check `delete_guides` and copy it.

Then inside `import_guide_instances`, immediately after
`joints: dict = {}`, insert:

```python
                present_roles = {role for (role, _index) in guide_instance.joints}
                extra = self._missing_role_layout(module, present_roles)
```

and after the existing `for (role, index), record in ...` loop that creates
the recorded joints (just before `root = joints[(module_cls.guides.root, 0)]`),
insert:

```python
                for role, layout in extra.items():
                    joint = tm.Joint.create(
                        name=naming.format_name(
                            module.name, role, None,
                            side=module.side.value, suffix="guide",
                        ),
                        radius=layout["radius"],
                    )
                    joint.world_position = layout["position"]
                    for item in module_cls.attrs_for_role(role):
                        tm.attribute.add_float(
                            joint, item.name,
                            default=item.default, keyable=item.keyable,
                        )
                    joint.meta.update({
                        tags.KIND: tags.GUIDE, tags.MODULE: module.module_type,
                        tags.INSTANCE: module.instance_id, tags.ROLE: role,
                        tags.INDEX: 0, tags.SIDE: module.side.value,
                    })
                    joints[(role, 0)] = joint
                    extra[role]["node"] = joint
```

Then carry `extra` alongside the other per-instance state so the second
pass can reach it: change `built.append((guide_instance, module, joints))`
to `built.append((guide_instance, module, joints, extra))`, unpack four
values in the second loop's `for` statement, and at the end of that loop
body add:

```python
                for role, layout in extra.items():
                    joint = joints[(role, 0)]
                    parent_role = layout["parent_role"]
                    joint.parent = (
                        joints[(parent_role, 0)] if parent_role in joints else holder
                    )
                    joint.world_position = layout["position"]
```

Setting the world position again after parenting matches how the recorded
joints are handled (the existing `cmds.xform(..., worldSpace=True, ...)`
call at the end of that loop), because parenting moves the joint.

Import `GuideDraft` and `naming` at the top of the file if they are not
already imported — check first.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `make tests-unit && make tests-integration`
Expected: PASS. The integration run matters here: every `.trg` round-trip
test exercises this path.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/guides/scene.py tests/unit/test_guides_trigger.py tests/helpers/toy_modules.py
git commit -m "fix(tik.trigger): import fills guide roles a .trg predates

import_guide_instances created only the roles present in the file, so a
module that gained a guide stopped building every existing asset. It now
draws the missing ones where draw_guides would have."
```

---

### Task 3: The reach axis spec and its ramp arithmetic

**Files:**
- Modify: `src/python/tik/trigger/systems/reach.py`
- Test: `tests/unit/test_reach_math_trigger.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ReachAxis(min_angle: float, max_angle: float, min_output: float, max_output: float)`
    — a frozen dataclass in `tik.trigger.systems.reach`.
  - `ReachAxis.ramp_points() -> list[tuple[float, float]]` returning the
    three `(position, value)` pairs for `Remap.create(points=...)`.
  - `ReachAxis.validate(label: str) -> None` raising `ValueError` unless
    `min_angle < 0 < max_angle` and `min_output < max_output`.

Pure arithmetic, no Maya, so it is tested on its own before any node
exists.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_reach_math_trigger.py`:

```python
"""The reach ramp arithmetic, which decides where the neutral lands."""

import pytest

from tik.trigger.systems.reach import ReachAxis


def test_the_middle_point_puts_zero_on_zero():
    axis = ReachAxis(min_angle=-40.0, max_angle=60.0, min_output=-8.0, max_output=22.0)
    points = axis.ramp_points()
    assert len(points) == 3
    assert points[0] == (0.0, 0.0)
    assert points[2] == (1.0, 1.0)
    position, value = points[1]
    assert abs(position - 0.4) < 1e-9
    assert abs(value - 8.0 / 30.0) < 1e-9


def test_the_middle_point_reconstructs_zero_output():
    """position -> value -> output must come back to exactly zero."""
    axis = ReachAxis(min_angle=-45.0, max_angle=120.0, min_output=-6.0, max_output=15.0)
    _position, value = axis.ramp_points()[1]
    output = axis.min_output + value * (axis.max_output - axis.min_output)
    assert abs(output) < 1e-9


def test_a_symmetric_axis_puts_the_neutral_in_the_middle():
    axis = ReachAxis(min_angle=-60.0, max_angle=60.0, min_output=-10.0, max_output=10.0)
    position, value = axis.ramp_points()[1]
    assert abs(position - 0.5) < 1e-9
    assert abs(value - 0.5) < 1e-9


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_angle": 10.0, "max_angle": 60.0},    # neutral outside the range
        {"min_angle": -60.0, "max_angle": -10.0},  # neutral outside the range
        {"min_angle": 0.0, "max_angle": 60.0},     # neutral on the boundary
        {"min_angle": -60.0, "max_angle": 0.0},    # neutral on the boundary
    ],
)
def test_rejects_a_neutral_outside_the_input_range(kwargs):
    axis = ReachAxis(min_output=-5.0, max_output=5.0, **kwargs)
    with pytest.raises(ValueError, match="lift"):
        axis.validate("lift")


def test_rejects_an_inverted_output_range():
    axis = ReachAxis(min_angle=-45.0, max_angle=45.0, min_output=10.0, max_output=-10.0)
    with pytest.raises(ValueError, match="swing"):
        axis.validate("swing")


def test_a_valid_axis_validates_silently():
    ReachAxis(
        min_angle=-45.0, max_angle=120.0, min_output=-6.0, max_output=15.0
    ).validate("lift")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `make tests-unit`
Expected: FAIL — `ImportError: cannot import name 'ReachAxis'`.

- [ ] **Step 3: Implement `ReachAxis`**

Add to the top of `src/python/tik/trigger/systems/reach.py`, below the
existing imports (add `from dataclasses import dataclass`):

```python
@dataclass(frozen=True)
class ReachAxis:
    """One signed falloff: an input angle range onto an output degree range.

    The neutral is always the zero angle, because the driver is measured in
    a frame whose X *is* the neutral direction. ``min_angle`` must be
    negative and ``max_angle`` positive so the neutral lies strictly inside
    the range -- a ramp point at 0.0 or 1.0 would collide with an endpoint.
    """

    min_angle: float
    max_angle: float
    min_output: float
    max_output: float

    def validate(self, label: str) -> None:
        """Raise ``ValueError`` if this axis cannot carry a neutral."""
        if not self.min_angle < 0.0 < self.max_angle:
            raise ValueError(
                f"{label} angle range must straddle zero, so the neutral sits "
                f"inside it ({self.min_angle} .. {self.max_angle})."
            )
        if self.min_output >= self.max_output:
            raise ValueError(
                f"{label} output range must increase "
                f"({self.min_output} >= {self.max_output})."
            )

    def ramp_points(self) -> list:
        """``(position, value)`` pairs placing the neutral on zero output."""
        position = (0.0 - self.min_angle) / (self.max_angle - self.min_angle)
        value = (0.0 - self.min_output) / (self.max_output - self.min_output)
        return [(0.0, 0.0), (position, value), (1.0, 1.0)]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `make tests-unit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/systems/reach.py tests/unit/test_reach_math_trigger.py
git commit -m "feat(tik.trigger): ReachAxis, the signed falloff description

Four authored numbers per axis and the ramp shape that puts the neutral on
zero output for any asymmetric pair of limits."
```

---

### Task 4: Rewrite `build_reach`

**Files:**
- Rewrite: `src/python/tik/trigger/systems/reach.py`
- Rewrite: `tests/integration/trigger/test_reach_system.py`

**Interfaces:**
- Consumes: `ReachAxis` (Task 3), `Remap.create(points=...)` (Task 1).
- Produces:

```python
@dataclass
class Reach:
    frame: "tm.Transform"       # the static neutral frame
    group: "tm.Transform"       # the driven group, aligned to the frame
    align: "tm.Transform"       # static child; parent the controller here
    lift_plug: "Plug"           # the animator's <prefix>Lift
    swing_plug: "Plug"          # the animator's <prefix>Swing


def build_reach(
    rig,
    parent,                     # where the driven group hangs (ctrl.offset)
    origin,                     # transform whose pivot the frame sits at
    rest_from,                  # the module socket; frame parent, up source
    neutral_position,           # world-space point the neutral direction hits
    ik_target,                  # upstream transform standing in for the wrist
    control,                    # carries the animator attributes
    *,
    fk_controls=None,           # optional; enables the FK branch
    switch_plug=None,           # optional; required with fk_controls
    prefix: str = "autoReach",
    lift: ReachAxis = ...,
    swing: ReachAxis = ...,
    interpolation: str = "smooth",
    name: Optional[str] = None,
) -> Reach:
```

`fk_controls` and `switch_plug` are optional together: without them the
driver is IK-only, which keeps the system usable by a module with no FK
chain and keeps this task's tests free of a whole limb.

- [ ] **Step 1: Verify the node types exist in this Maya**

Before writing anything, confirm the three node types the design assumes.
Run under `mayapy`:

```bash
mayapy -c "import maya.standalone; maya.standalone.initialize(); from maya import cmds; print([t for t in ('atan2','distanceBetween','multMatrix','translationFromMatrix','blendColors') if not cmds.objExists(cmds.createNode(t))] or 'all present')"
```

Expected: `all present`. If `translationFromMatrix` is absent, substitute
`decomposeMatrix` and take its `outputTranslate` — note the substitution in
the commit message and in `reach.py`'s docstring, and carry on. Everything
else in the plan is unaffected.

- [ ] **Step 2: Write the failing tests**

Replace `tests/integration/trigger/test_reach_system.py` entirely:

```python
"""Integration tests for the reach system.

The driver is a position, so these tests move a target and read the driven
group's world matrix. No limb is built here -- the FK branch is exercised
by the arm tests, which have real FK controls.
"""

import math

import tik.maya as tm
from tik.trigger.systems.reach import ReachAxis, build_reach

LIFT = ReachAxis(min_angle=-45.0, max_angle=120.0, min_output=-6.0, max_output=15.0)
SWING = ReachAxis(min_angle=-45.0, max_angle=90.0, min_output=-6.0, max_output=10.0)


def _setup(ctx, lift=LIFT, swing=SWING, **kwargs):
    """A socket, an origin, a target, and the reach driving a group."""
    socket = tm.Transform.create(name="reach_socket", parent=ctx.groups.socket.long_name)
    origin = tm.Transform.create(name="reach_origin", parent=socket.long_name)
    origin.translate = (2, 0, 0)
    holder = tm.Transform.create(name="reach_holder", parent=ctx.groups.rig.long_name)
    target = tm.Transform.create(name="reach_target", parent=ctx.groups.control.long_name)
    target.translate = (14, 0, 0)
    control = ctx.controller("reach_ctrl", mirror="world")
    reach = build_reach(
        ctx, holder, origin, socket, (16.0, 0.0, 0.0), target, control.transform,
        prefix="autoCollar", lift=lift, swing=swing, name="reach", **kwargs
    )
    return socket, target, control.transform, reach


def _rotation(reach):
    """The driven group's local rotation, in degrees."""
    return tuple(reach.group.rotate)


def _place(target, elevation_deg, azimuth_deg=0.0, distance=12.0):
    """Put the target at an angle off the +X neutral line, about the origin."""
    elevation = math.radians(elevation_deg)
    azimuth = math.radians(azimuth_deg)
    target.translate = (
        2.0 + distance * math.cos(elevation) * math.cos(azimuth),
        distance * math.sin(elevation),
        distance * math.cos(elevation) * math.sin(azimuth),
    )


def test_adds_exactly_two_attributes(build_context):
    _socket, _target, control, _reach = _setup(build_context())
    assert control.has_attr("autoCollarLift")
    assert control.has_attr("autoCollarSwing")
    assert not control.has_attr("autoCollar")
    assert not control.has_attr("autoCollarVertical")
    assert not control.has_attr("autoCollarHorizontal")
    assert abs(control["autoCollarLift"].value) < 1e-6
    assert abs(control["autoCollarSwing"].value) < 1e-6


def test_off_is_inert(build_context):
    _socket, target, _control, reach = _setup(build_context())
    before = _rotation(reach)
    _place(target, 60.0, 40.0)
    assert all(abs(a - b) < 1e-4 for a, b in zip(_rotation(reach), before))


def test_the_neutral_direction_produces_no_rotation(build_context):
    """The regression test for the two-zeros bug."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    control["autoCollarSwing"].value = 1.0
    _place(target, 0.0, 0.0)
    assert all(abs(value) < 1e-4 for value in _rotation(reach))


def test_the_sign_flips_across_the_neutral(build_context):
    """The collar must not dip on its way up."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    _place(target, 20.0)
    above = _rotation(reach)[2]
    _place(target, -20.0)
    below = _rotation(reach)[2]
    assert above > 0.0 > below


def test_lift_is_monotonic_from_the_neutral_to_the_limit(build_context):
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    samples = []
    for elevation in range(0, 121, 10):
        _place(target, float(elevation))
        samples.append(_rotation(reach)[2])
    assert all(b >= a - 1e-6 for a, b in zip(samples, samples[1:]))
    assert abs(samples[-1] - LIFT.max_output) < 1e-3


def test_saturates_past_the_limit(build_context):
    """Today's mechanism reaches +139 degrees at +120. This one stops."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    _place(target, 120.0)
    at_limit = _rotation(reach)[2]
    _place(target, 160.0)
    assert abs(_rotation(reach)[2] - at_limit) < 1e-3
    assert abs(at_limit - LIFT.max_output) < 1e-3


def test_saturates_below_the_lower_limit(build_context):
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    _place(target, -45.0)
    at_limit = _rotation(reach)[2]
    _place(target, -80.0)
    assert abs(_rotation(reach)[2] - at_limit) < 1e-3
    assert abs(at_limit - LIFT.min_output) < 1e-3


def test_no_hard_corner_at_the_limit(build_context):
    """Finite differences either side of the limit must both be near zero."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    readings = {}
    for elevation in (118.0, 119.0, 121.0, 122.0):
        _place(target, elevation)
        readings[elevation] = _rotation(reach)[2]
    inside = readings[119.0] - readings[118.0]
    outside = readings[122.0] - readings[121.0]
    assert abs(inside) < 0.05
    assert abs(outside) < 1e-6


def test_no_hard_corner_at_the_neutral(build_context):
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    readings = {}
    for elevation in (-2.0, -1.0, 1.0, 2.0):
        _place(target, elevation)
        readings[elevation] = _rotation(reach)[2]
    below = readings[-1.0] - readings[-2.0]
    above = readings[2.0] - readings[1.0]
    assert abs(below - above) < 0.05


def test_the_axes_are_independent(build_context):
    """The per-axis test that proves each strand reached its own remap."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    control["autoCollarSwing"].value = 0.0
    _place(target, 0.0, 60.0)
    assert all(abs(value) < 1e-3 for value in _rotation(reach))
    control["autoCollarSwing"].value = 1.0
    assert abs(_rotation(reach)[1]) > 1.0


def test_the_scalars_scale_the_output(build_context):
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    _place(target, 60.0)
    full = _rotation(reach)[2]
    control["autoCollarLift"].value = 0.5
    assert abs(_rotation(reach)[2] - full * 0.5) < 1e-3


def test_the_scalar_never_moves_the_neutral(build_context):
    """The regression test for the old input-side multipliers."""
    _socket, target, control, reach = _setup(build_context())
    _place(target, 0.0)
    for scalar in (0.0, 0.25, 0.5, 1.0):
        control["autoCollarLift"].value = scalar
        control["autoCollarSwing"].value = scalar
        assert all(abs(value) < 1e-4 for value in _rotation(reach))


def test_the_folded_arm_does_not_wrap(build_context):
    """atan2(y, hypot(x, z)) has no branch cut; atan2(y, x) does."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    _place(target, 10.0, 170.0)
    across = _rotation(reach)[2]
    _place(target, 10.0, 190.0)
    assert abs(_rotation(reach)[2] - across) < 1.0
```

The `build_context` fixture and `ctx.controller` / `ctx.groups` usage are
copied from the file being replaced — keep whatever the old file used.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `make tests-integration`
Expected: FAIL — `TypeError` on `build_reach`, which still has the old
signature.

- [ ] **Step 4: Rewrite `reach.py`**

Replace everything below the `ReachAxis` dataclass. The module docstring
becomes:

```python
"""Reach: a base rotates as an end-effector swings away from a neutral.

Auto-clavicle is shoulder reach; the same system serves a hip. It is named
for the behaviour rather than the anatomy, and it names no animator-facing
attribute itself -- the module supplies a prefix, because wording is policy.

    frame       static transform at `origin`, X aimed at the neutral point,
                up from `rest_from`  ->  both neutrals are zero by construction
    probe       transform under the frame, point-constrained to `ik_target`
                -> probe.translate IS the direction, already in frame space
    fk_ref      static transform under the frame at the FK root's rest pose
                -> its `matrix` is the constant that opens the FK product
    driver      blendColors(fk_product, probe.translate, ikFk)
    elevation   atan2(y, hypot(x, z))        signed, +/-90, never wraps
    azimuth     atan2(z, hypot(x, y))        signed, +/-90, never wraps
    lift        remap(elevation) * <prefix>Lift   -> group.rotateZ
    swing       remap(azimuth)   * <prefix>Swing  -> group.rotateY

The frame is built with `aim_at`, which bakes plain rotation values, so it
is static once parented under `rest_from` -- and aimConstraint's
orthogonalisation IS the Gram-Schmidt step the design calls for.

`atan2(y, hypot(x, z))` rather than `atan2(y, x)`: the latter has a branch
cut on -X, the arm folded across the chest, where the clamped output would
jump from one limit to the other.
"""
```

Then the builder. Write it in these pieces, in this order:

```python
def _hypot(rig, vector_plug, first: str, second: str, name: str):
    """Length of two of a vector's three components."""
    node = tm.create_node("distanceBetween", name=rig.name(name))
    vector_plug.child(first) >> node[f"point1{first.upper()}"]
    vector_plug.child(second) >> node[f"point1{second.upper()}"]
    return node["distance"]
```

Use whatever tik.maya offers for reaching a compound plug's child — if
`.child()` does not exist, index it the way the rest of the codebase does
(`plug["X"]` or `node["outputX"]`); read `systems/limb.py` for the idiom and
follow it.

```python
def _signed_angle(rig, vector_plug, numerator: str, others, name: str):
    """atan2(numerator, hypot(others)) in degrees -- signed, +/-90, no wrap."""
    hypot = _hypot(rig, vector_plug, others[0], others[1], f"{name}Hypot")
    node = tm.create_node("atan2", name=rig.name(name))
    vector_plug.child(numerator) >> node["input1"]
    hypot >> node["input2"]
    return node["output"]
```

```python
def _fk_direction(rig, frame, fk_controls, name: str):
    """Wrist position in frame space, from the FK controls' LOCAL matrices.

    The FK controllers are parented controller-to-controller, each with its
    own offset group (`systems/limb.py:219,244`), so the hierarchy is
    o_0 -> c0 -> o_1 -> c1 -> o_2 -> c2. Only o_0 is animated -- it carries
    the constraint to the limb parent -- so `fk_ref`, a static child of the
    frame snapped to o_0's rest pose, supplies that term instead. Every
    other matrix in the product is either a controller's own local matrix
    (an animator input, upstream of us) or static parenting.

    Reading local matrices is what keeps this acyclic: the FK controls'
    WORLD matrices are downstream of the collar, their local ones are not.
    """
    fk_ref = tm.Transform.create(name=rig.name(name, "fkRef"), parent=frame.long_name)
    fk_ref.align_to(fk_controls[0].offset)
    product = tm.create_node("multMatrix", name=rig.name(name, "fkProduct"))
    index = 0
    for control in reversed(fk_controls):
        control.transform["matrix"] >> product[f"matrixIn[{index}]"]
        index += 1
        if control is not fk_controls[0]:
            control.offset["matrix"] >> product[f"matrixIn[{index}]"]
            index += 1
    fk_ref["matrix"] >> product[f"matrixIn[{index}]"]
    translation = tm.create_node(
        "translationFromMatrix", name=rig.name(name, "fkPoint")
    )
    product["matrixSum"] >> translation["input"]
    return translation["output"]
```

Confirm `translationFromMatrix`'s input and output attribute names against
`cmds.attributeInfo` before trusting `input` / `output`; correct them if
they differ. Same for `atan2`'s `input1` / `input2` / `output`.

Then the public builder:

```python
def build_reach(
    rig,
    parent,
    origin,
    rest_from,
    neutral_position,
    ik_target,
    control,
    *,
    fk_controls=None,
    switch_plug=None,
    prefix: str = "autoReach",
    lift: ReachAxis,
    swing: ReachAxis,
    interpolation: str = "smooth",
    name: Optional[str] = None,
) -> Reach:
    """Rotate a group as ``ik_target`` swings away from the neutral direction.

    Args:
        rig: The module's ``ModuleRig``.
        parent: Where the driven group hangs, usually a controller's offset.
        origin: Transform whose pivot the rotation happens about.
        rest_from: The module's socket. Parents the frame and supplies the
            up vector, so it must be upstream of everything read here.
        neutral_position: World point the neutral direction passes through.
        ik_target: What the base reaches toward. MUST be upstream of any IK
            solve it feeds, or the graph cycles.
        control: Transform carrying the animator-facing attributes.
        fk_controls: Optional FK controllers, root first. With them the
            driver is exact in FK as well as IK.
        switch_plug: The ikFk switch. Required when ``fk_controls`` is given.
        prefix: Attribute prefix, e.g. ``autoCollar``.
        lift: Falloff for elevation, driving the group's Z.
        swing: Falloff for azimuth, driving the group's Y.
        interpolation: ``linear``, ``smooth`` or ``spline``. Only ``smooth``
            is free of a slope discontinuity at the neutral and the limits.
        name: Prefix for created nodes.

    Returns:
        The ``Reach``. Parent the driven controller under ``reach.align``.
    """
    if fk_controls and switch_plug is None:
        raise ValueError("fk_controls needs switch_plug to blend against.")
    lift.validate(f"{prefix} lift")
    swing.validate(f"{prefix} swing")
    name = name or prefix
```

then, in order:

1. **The frame.** Create a transform under `rest_from`, `snap_to(origin,
   rotation=False)`, then aim it. Build a temporary locator at
   `neutral_position` to aim at, and delete it afterwards:

   ```python
    frame = tm.Transform.create(
        name=rig.name(name, "neutralFrame"), parent=rest_from.long_name
    )
    frame.snap_to(origin, rotation=False)
    marker = tm.Transform.create(name=rig.name(name, "neutralMarker"))
    marker.world_position = neutral_position
    frame.aim_at(
        marker, aim_vector=(1, 0, 0), up_vector=(0, 1, 0), world_up_object=rest_from
    )
    marker.delete()
   ```

   `aim_at` bakes rotation values, so the frame is static. Use whatever
   node-removal call the rest of tik.trigger uses in place of `.delete()`.

2. **The IK probe**, under the frame, translate-only constrained:

   ```python
    probe = tm.Transform.create(name=rig.name(name, "probe"), parent=frame.long_name)
    tm.MatrixConstraint.create(
        ik_target, probe, maintain_offset=False, skip_rotate="xyz", skip_scale="xyz"
    )
    direction = probe["translate"]
   ```

3. **The FK branch and blend**, when asked for:

   ```python
    if fk_controls:
        fk_point = _fk_direction(rig, frame, fk_controls, name)
        blend = tm.create_node("blendColors", name=rig.name(name, "ikFkBlend"))
        probe["translate"] >> blend["color1"]
        fk_point >> blend["color2"]
        switch_plug >> blend["blender"]
        direction = blend["output"]
   ```

   `blendColors` outputs `color1` at `blender = 1`, and `ikFk = 1` is IK
   (`limb.py:209` defaults it to 1.0; `limb.py:404` drives the IK control's
   visibility straight off it), so the probe belongs on `color1` as written.
   `test_ik_and_fk_agree_across_the_switch` in Task 6 is what proves it.

4. **The attributes**, then a remap and a multiply per axis:

   ```python
    attribute.add_separator(control, "auto_")
    plugs = {}
    for label, axis, channel, numerator, others in (
        ("Lift", lift, "rotateZ", "Y", ("X", "Z")),
        ("Swing", swing, "rotateY", "Z", ("X", "Y")),
    ):
        scalar = attribute.add_float(
            control, f"{prefix}{label}", default=0.0, min=0.0, max=1.0
        )
        angle = _signed_angle(
            rig, direction, numerator, others, f"{name}{label}Angle"
        )
        ramp = tm.Remap.create(
            angle,
            input_min=axis.min_angle,
            input_max=axis.max_angle,
            output_min=axis.min_output,
            output_max=axis.max_output,
            interpolation=interpolation,
            points=axis.ramp_points(),
            name=rig.name(name, label.lower()),
        )
        (ramp.output * scalar) >> group[channel]
        plugs[label] = scalar
   ```

   `ramp.output * scalar` follows the operator idiom already used at
   `reach.py`'s `weight = ramp.output * amount`. Keep it.

5. **The driven group and its static align child**, created before step 4
   so `group[channel]` exists:

   ```python
    group = tm.Transform.create(name=rig.name(name, "auto"), parent=parent.long_name)
    group.snap_to(origin, rotation=False)
    group.snap_to(frame, position=False)
    group["rotateOrder"].value = 0  # xyz -> Rz * Ry * Rx, lift outermost
    align = tm.Transform.create(name=rig.name(name, "align"), parent=group.long_name)
    align.align_to(origin)
   ```

6. **Return** `Reach(frame=frame, group=group, align=align,
   lift_plug=plugs["Lift"], swing_plug=plugs["Swing"])`.

Delete `AngleBetween`, `AimFrame` and `MatrixBlend` usage entirely. If the
azimuth sign comes out inverted — the design derives that a positive
azimuth needs a *negative* rotation about the frame's Y — negate it by
swapping `swing`'s output signs at the wiring site with a `multDoubleLinear`
of -1, and say so in a comment. `test_the_axes_are_independent` and
`test_the_sign_flips_across_the_neutral` are what catch it.

- [ ] **Step 5: Run the tests until they pass**

Run: `make tests-integration`
Expected: PASS, all sixteen. Expect to iterate on attribute names for
`atan2` and `translationFromMatrix` and on the azimuth sign. Do not weaken
a tolerance to make a test pass — if `test_no_hard_corner_at_the_neutral`
fails, the ramp points are wrong, not the tolerance.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/systems/reach.py tests/integration/trigger/test_reach_system.py
git commit -m "feat(tik.trigger): reach gets a signed, saturating driver

The old mechanism had two unrelated zeros -- the ramp measured from the
arm's bind direction while the blend aimed the base at the target -- so an
A-posed collar dipped before it lifted, and past the end angle it tracked
the target 1:1 without bound.

Now: a static frame aimed at an authored neutral, an off-plane atan2 per
axis, and one three-point remapValue mapping angle limits onto authored
degrees. Clamps at the limits, keeps zero on zero, and the animator's
scalars multiply the output so they cannot move the neutral."
```

---

### Task 5: The `neutral` guide and the new `Arm` fields

**Files:**
- Modify: `src/python/tik/trigger/modules/arm/arm.py:36-85`
- Test: `tests/unit/test_core_trigger.py`

**Interfaces:**
- Consumes: `ReachAxis.validate` (Task 3).
- Produces: `Arm.guides` gains a `neutral` role; the nine fields listed in
  the spec's section 4.1; `Arm.validate()` rejects a neutral outside either
  input range. `Arm.build` is *not* touched in this task — the guide is
  drawn and the fields exist, but nothing consumes them yet, so the module
  still builds exactly as before.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_core_trigger.py`, matching the file's existing
import and construction idiom for `Arm`:

```python
def test_arm_declares_a_neutral_guide():
    assert "neutral" in Arm.guides.roles


def test_arm_auto_collar_defaults_straddle_zero():
    arm = Arm(name="arm", side=Side.LEFT)
    assert arm.auto_collar_lift_min_angle < 0 < arm.auto_collar_lift_max_angle
    assert arm.auto_collar_swing_min_angle < 0 < arm.auto_collar_swing_max_angle
    arm.validate()


def test_arm_rejects_a_neutral_outside_the_lift_range():
    arm = Arm(name="arm", side=Side.LEFT, settings={"auto_collar_lift_min_angle": 10.0})
    with pytest.raises(ValueError, match="lift"):
        arm.validate()


def test_arm_rejects_a_neutral_outside_the_swing_range():
    arm = Arm(name="arm", side=Side.LEFT, settings={"auto_collar_swing_max_angle": -5.0})
    with pytest.raises(ValueError, match="swing"):
        arm.validate()


def test_arm_no_longer_has_the_old_angle_fields():
    arm = Arm(name="arm", side=Side.LEFT)
    assert not hasattr(arm, "auto_collar_start")
    assert not hasattr(arm, "auto_collar_end")
```

Check how `Arm` is constructed elsewhere in that file — if settings go
through a different argument, follow it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `make tests-unit`
Expected: FAIL — `neutral` missing from roles, and the new fields absent.

- [ ] **Step 3: Add the guide, the fields and the validation**

In `arm.py`, extend the layout:

```python
    guides = GuideLayout("collar", "shoulder", "elbow", "hand", "neutral")
```

Replace `auto_collar_start` and `auto_collar_end` with:

```python
    auto_collar = BoolField(True, help="Build the auto-collar network")
    auto_collar_lift_min_angle = FloatField(
        -45.0, min=-180.0, max=0.0, label="Lift Lower Angle",
        help="Arm elevation, relative to the neutral guide, at full "
             "downward falloff. Must be below zero.",
    )
    auto_collar_lift_max_angle = FloatField(
        120.0, min=0.0, max=180.0, label="Lift Upper Angle",
        help="Arm elevation at full upward falloff. Must be above zero.",
    )
    auto_collar_lift_min_output = FloatField(
        -6.0, min=-90.0, max=90.0, label="Lift Lower Degrees",
        help="Collar rotation at the lower angle.",
    )
    auto_collar_lift_max_output = FloatField(
        15.0, min=-90.0, max=90.0, label="Lift Upper Degrees",
        help="Collar rotation at the upper angle.",
    )
    auto_collar_swing_min_angle = FloatField(
        -45.0, min=-180.0, max=0.0, label="Swing Back Angle",
        help="Arm azimuth, relative to the neutral guide, at full backward "
             "falloff. Must be below zero.",
    )
    auto_collar_swing_max_angle = FloatField(
        90.0, min=0.0, max=180.0, label="Swing Forward Angle",
        help="Arm azimuth at full forward falloff. Must be above zero.",
    )
    auto_collar_swing_min_output = FloatField(
        -6.0, min=-90.0, max=90.0, label="Swing Back Degrees",
        help="Collar rotation at the back angle.",
    )
    auto_collar_swing_max_output = FloatField(
        10.0, min=-90.0, max=90.0, label="Swing Forward Degrees",
        help="Collar rotation at the forward angle.",
    )
    auto_collar_interpolation = ChoiceField(
        "smooth",
        choices=("linear", "smooth", "spline"),
        label="Auto Collar Interpolation",
        help="Only 'smooth' is free of a slope discontinuity: 'linear' kinks "
             "at the neutral and both limits, 'spline' kinks at both limits.",
    )
```

Add two helpers and rewrite `validate`:

```python
    def _lift_axis(self) -> ReachAxis:
        return ReachAxis(
            min_angle=self.auto_collar_lift_min_angle,
            max_angle=self.auto_collar_lift_max_angle,
            min_output=self.auto_collar_lift_min_output,
            max_output=self.auto_collar_lift_max_output,
        )

    def _swing_axis(self) -> ReachAxis:
        return ReachAxis(
            min_angle=self.auto_collar_swing_min_angle,
            max_angle=self.auto_collar_swing_max_angle,
            min_output=self.auto_collar_swing_min_output,
            max_output=self.auto_collar_swing_max_output,
        )

    def validate(self) -> None:
        if self.auto_collar:
            self._lift_axis().validate("auto collar lift")
            self._swing_axis().validate("auto collar swing")
```

Keep any other checks `validate` already performs — read it first and add
to it rather than replacing wholesale.

Extend `draw_guides` with the neutral guide. Guide positions are absolute,
not parent-relative (`collar (2,0,0)`, `hand (14,0,0)`), so the default
neutral sits just past the hand on the same T-pose line:

```python
        guides.joint("hand", (14 * mult, 0, 0), parent=elbow)
        # Only the direction matters; past the hand keeps it selectable.
        guides.joint("neutral", (16 * mult, 0, 0), parent=collar, radius=0.8)
```

Import `ReachAxis` alongside the existing `build_reach` import.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `make tests-unit && make tests-integration`
Expected: unit PASS. Integration will show arm failures where the old
`start_angle` / `end_angle` arguments are still passed in `Arm.build` —
that is Task 6. If `make tests-integration` blocks the commit, note the
failing test names and proceed; Task 6 fixes them.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/modules/arm/arm.py tests/unit/test_core_trigger.py
git commit -m "feat(tik.trigger): the arm's neutral guide and per-axis limits

The neutral is a guide the rigger drags, not a number they guess: it
mirrors for free and it is the only form in which the zero is visible. The
angle limits and the output degrees become independent knobs per axis."
```

---

### Task 6: Wire the new reach into the arm

**Files:**
- Modify: `src/python/tik/trigger/modules/arm/arm.py:148-165`
- Test: `tests/integration/trigger/test_arm_trigger.py`

**Interfaces:**
- Consumes: `build_reach`, `Reach`, `ReachAxis` (Tasks 3-5).
- Produces: an arm whose collar carries `autoCollarLift` and
  `autoCollarSwing` on the IK control, driven by the new mechanism.

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/trigger/test_arm_trigger.py`, following its
existing build fixture:

```python
def _collar_matrix(arm_rig):
    return list(arm_rig.collar_ctrl.transform["worldMatrix[0]"].value)


def test_the_arm_ships_two_auto_collar_attributes(built_arm):
    control = built_arm.ik_control.transform
    assert control.has_attr("autoCollarLift")
    assert control.has_attr("autoCollarSwing")
    assert not control.has_attr("autoCollar")


def test_bind_pose_is_exact_with_the_automation_full_on(built_arm):
    """The regression test for the rest-direction bug: today this fails."""
    control = built_arm.ik_control.transform
    before = _collar_matrix(built_arm)
    control["autoCollarLift"].value = 1.0
    control["autoCollarSwing"].value = 1.0
    after = _collar_matrix(built_arm)
    assert all(abs(a - b) < 1e-4 for a, b in zip(before, after))


def test_raising_the_arm_never_dips_the_collar(built_arm):
    """The complaint, as a test."""
    control = built_arm.ik_control.transform
    control["autoCollarLift"].value = 1.0
    rest = built_arm.collar_ctrl.transform.rotate[2]
    readings = []
    for height in range(0, 13):
        built_arm.ik_control.transform.translate = (14.0, float(height), 0.0)
        readings.append(built_arm.collar_ctrl.transform.rotate[2] - rest)
    assert min(readings) > -1e-3, f"collar dipped: {readings}"
    assert all(b >= a - 1e-6 for a, b in zip(readings, readings[1:]))


def test_ik_and_fk_agree_across_the_switch(built_arm):
    """The reason the driver is a position and not the solved humerus."""
    control = built_arm.ik_control.transform
    control["autoCollarLift"].value = 1.0
    control.translate = (12.0, 8.0, 2.0)
    built_arm.switch_plug.value = 1.0  # ikFk: 1 is IK (limb.py:209, 404)
    in_ik = built_arm.collar_ctrl.transform.rotate[2]
    # match FK to the IK pose before switching
    for fk, ik in zip(built_arm.fk_controls, built_arm.ik_joints):
        fk.transform.rotate = tuple(ik.rotate)
    built_arm.switch_plug.value = 0.0  # 0 is FK
    assert abs(built_arm.collar_ctrl.transform.rotate[2] - in_ik) < 0.5


def test_the_graph_has_no_cycle(built_arm):
    """The FK branch reads local matrices precisely so this holds."""
    assert not built_arm.rig.evaluation_cycles()
```

Replace `<ik value>` / `<fk value>` with the real `ikFk` convention from
`systems/limb.py:209-211`, and `built_arm.*` with whatever the file's
fixture actually exposes — read it first. For the cycle test, use whatever
tik.maya offers for cycle detection; if nothing does, drop that assertion
and instead assert `cmds`-free that evaluating the collar's world matrix in
both IK and FK returns finite numbers, and note the gap in the commit.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `make tests-integration`
Expected: FAIL — `Arm.build` still calls `build_reach` with `start_angle`
and `end_angle`.

- [ ] **Step 3: Rewrite the wiring**

Replace the `if self.auto_collar:` block in `Arm.build`:

```python
        if self.auto_collar:
            reach = build_reach(
                rig,
                collar_ctrl.offset,
                collar_ctrl.transform,
                hang_from,
                tuple(rig.guide("neutral").world_position),
                limb.ik_tweak.transform,
                limb.ik_control.transform,
                fk_controls=limb.fk_controls,
                switch_plug=limb.switch_plug,
                prefix="autoCollar",
                lift=self._lift_axis(),
                swing=self._swing_axis(),
                interpolation=self.auto_collar_interpolation,
                name="collar",
            )
            # Relative, so set_parent writes no compensation into the
            # channels: `align` already carries the collar's own orientation.
            collar_ctrl.transform.set_parent(reach.align, relative=True)
```

Everything downstream — `limb_from.snap_to(collar_ctrl.transform)` and the
limb-lock block — is unchanged, but confirm the ordering still holds: the
reach block currently runs *after* the limb is built (it needs
`limb.ik_tweak`) and *before* limb lock. Keep that order.

- [ ] **Step 4: Run the tests until they pass**

Run: `make tests-integration`
Expected: PASS, including the pre-existing arm tests. If
`test_ik_and_fk_agree_across_the_switch` fails by a large constant, the
`blendColors` polarity is backwards — swap `color1` and `color2` in
`reach.py` and fix the comment there.

- [ ] **Step 5: Run the whole suite**

Run: `make tests`
Expected: PASS. Investigate any failure; do not skip a test.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/modules/arm/arm.py tests/integration/trigger/test_arm_trigger.py
git commit -m "feat(tik.trigger): the arm drives its collar off the new reach

Raising an A-posed arm now lifts the collar monotonically from the first
degree, and the bind pose is reproduced exactly with the automation full
on. The driver blends the IK probe against a product of the FK controls'
local matrices, so it reads the same quantity either side of the switch
without a second solve."
```

---

### Task 7: Documentation

**Files:**
- Modify: `CLAUDE.md` (the tik.trigger status line)
- Modify: `docs/superpowers/specs/2026-08-30-dynamic-spaces-and-reach-design.md`

**Interfaces:** none.

- [ ] **Step 1: Mark the superseded spec**

At the top of `2026-08-30-dynamic-spaces-and-reach-design.md`, under its
existing header, add:

```markdown
> **Part 4 (The Reach System) is superseded** by
> `2026-08-31-auto-collar-redesign-design.md`. The mechanism it describes
> had two unrelated zeros and an unbounded output; the rest of this
> document still stands.
```

- [ ] **Step 2: Update the project status line**

In `CLAUDE.md`, in the tik.trigger **Status** paragraph, add the new spec
to the design-specs list:

```
`docs/superpowers/specs/2026-08-31-auto-collar-redesign-design.md`
(the signed two-axis auto-collar; supersedes the reach spec's Part 4)
```

- [ ] **Step 3: Mark the design spec implemented**

In `2026-08-31-auto-collar-redesign-design.md`, change
`Status: designed, not implemented.` to `Status: implemented.` plus the
date, and add a short "Corrections after implementation" section recording
anything the build proved wrong — the `atan2` and `translationFromMatrix`
attribute names, the `blendColors` polarity, the azimuth sign, and whether
`translationFromMatrix` existed at all. Follow the pattern at the end of
`2026-08-31-twist-ribbon-limblock-design.md`.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/
git commit -m "docs(tik.trigger): record the auto-collar redesign as built"
```

---

## Self-Review

**Spec coverage.** Section 2 (root cause) is covered by the regression
tests in Tasks 4 and 6 rather than by code. 3.1 neutral frame → Task 4
step 4.1. 3.2 driver → Task 4 steps 4.2-4.3. 3.3 angles → Task 4's
`_signed_angle`. 3.4 curve → Tasks 1 and 3, wired in Task 4 step 4.4.
3.5 output → Task 4 step 4.5. 4.1 fields → Task 5. 4.2 neutral guide →
Task 5. 4.3 animator attributes → Task 4 step 4.4, asserted in Tasks 4
and 6. 4.4 interpolation → Task 5's help text. Section 5 migration →
Task 2. Section 6 tik.maya → Task 1 (the optional angles construct is
deliberately skipped; `_signed_angle` in `reach.py` is enough for one
consumer). Section 7 hazard 2 → the docstring in `_fk_direction`. Section
8 testing → Tasks 1-6. Section 9 removals → Tasks 4 and 5.

**Known gap:** spec section 7 hazard 1 — an IK-control space targeting the
arm's own `collar` output — is *not* implemented. It needs the module's
resolved input graph inside `validate()`, which the fields alone do not
carry, and it is a pre-existing hole rather than one this change opens.
Left out deliberately; raise it as its own piece of work.

**Type consistency.** `ReachAxis` field names (`min_angle`, `max_angle`,
`min_output`, `max_output`) are identical in Tasks 3, 4 and 5.
`Reach.align` is what Task 6 parents the controller under, and it is what
Task 4 returns. `Remap.create(points=...)` from Task 1 is called with
`axis.ramp_points()` from Task 3 in Task 4.
