# Arm Module Rebuild and Module Ground Rules — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder arm module with a single-IK-chain arm built on new `tik.maya` constructs, and land the repo-wide module ground rules (four groups, two skeletons, one bind hierarchy) it depends on.

**Architecture:** Three phases. Phase A adds mechanism to `tik.maya` (`MatrixBlend`, `ChainLengths`, `SoftIk`, `AimFrame`, plus plug/joint/constraint extensions) and retires `IkFkChain`. Phase B reworks the trigger group taxonomy, adds `ctx.bind_parent`, and makes the builder order build-and-connect topologically by input connections. Phase C adds `tik/trigger/systems/limb.py` (policy: controllers and attribute names) and rewrites the arm module on top of it.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), `tik.maya` wrapper, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-arm-module-and-module-ground-rules-design.md`

## Global Constraints

- **No third-party dependencies.** Stdlib and Maya-bundled modules only.
- **Maya 2024+.** `NodeNames.uses_native_math_nodes` is `maya_version >= 2025` (`src/python/tik/maya/core/constants.py:205`). Anything using a native math node needs a pre-2025 fallback.
- **No raw `cmds` / `OpenMaya` outside `tik.maya`.** `tik/trigger/systems/` and module bodies consume `tik.maya` only. Inside `tik.maya` itself raw `cmds` is fine and idiomatic.
- **The animator-opinion rule.** A `tik.maya` construct never creates a controller, never names a user-facing attribute, never encodes a side convention. All of that lives in `tik/trigger/`.
- **Bind joints carry live TRS.** Never drive a bind joint through `offsetParentMatrix`. `MatrixConstraint` already decomposes to `translate`/`rotate`/`scale`.
- **`math.e`**, never a truncated literal.
- **Test command:** `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/<file> -v`
  Full suites: `make tests-unit`, `make tests-integration`.
- **Commit after every task.** Never use `--no-verify`. Never push.

---

## File Structure

**Phase A — `tik.maya` mechanism**

| File | Responsibility |
|---|---|
| `src/python/tik/maya/core/plug.py` (modify) | Add `minimum`/`maximum`/`clamped`/`lerp`/`gt` helpers; version-guard `**` |
| `src/python/tik/maya/types/joint.py` (modify) | `preferred_angle` property, `duplicate_chain`, `reverse_aim`/`reverse_up` |
| `src/python/tik/maya/constructs/matrix_constraint.py` (modify) | `cutoff=` parameter |
| `src/python/tik/maya/constructs/measure.py` (modify) | Accept matrix `Plug`s |
| `src/python/tik/maya/constructs/matrix_blend.py` (create) | Continuous N-target `blendMatrix` |
| `src/python/tik/maya/constructs/chain_lengths.py` (create) | Per-segment length drivers, factors, overrides |
| `src/python/tik/maya/constructs/soft_ik.py` (create) | Exponential approach curve + goal matrix |
| `src/python/tik/maya/constructs/aim_frame.py` (create) | Twist-aware aim frame |
| `src/python/tik/maya/constructs/ikfk_chain.py` (delete) | Retired |

**Phase B — trigger ground rules**

| File | Responsibility |
|---|---|
| `src/python/tik/trigger/core/context.py` (modify) | `RigGroups` four-group dataclass; `BuildContext` protocol gains `bind_parent`/`bind_joint` |
| `src/python/tik/trigger/backends/maya/context.py` (modify) | Build the four groups; `bind_joint`, `bind_parent`, `trg_mirror` |
| `src/python/tik/trigger/backends/maya/tags.py` (modify) | `MIRROR`, `BEHAVIOUR`, `WORLD`, `BIND` keys |
| `src/python/tik/trigger/core/schemas.py` (modify) | `order_by_connections` |
| `src/python/tik/trigger/core/builder.py` (modify) | Ordered build-and-connect; resolve `bind_parent` before build |
| `src/python/tik/trigger/backends/maya/backend.py` (modify) | `build_context` takes `bind_parent`; validate outputs are bind joints |
| `src/python/tik/trigger/modules/base/base.py` (modify) | Use `ctx.bind_joint` |
| `src/python/tik/trigger/modules/fkchain/fkchain.py` (modify) | Use `ctx.bind_joint`, `socket_grp`, `control_grp` |
| `tests/helpers/trigger_fakes.py` (modify) | Fake ctx gains `bind_parent`/`bind_joint` |

**Phase C — systems and arm**

| File | Responsibility |
|---|---|
| `src/python/tik/trigger/systems/__init__.py` (create) | Package marker |
| `src/python/tik/trigger/systems/limb.py` (create) | `build_ikfk_limb` — the policy layer |
| `src/python/tik/trigger/modules/arm/arm.py` (rewrite) | Guides, bind joints, fields, controllers |

---

## Phase A — `tik.maya` Mechanism

### Task 1: Plug math helpers and the `**` version guard

**Files:**
- Modify: `src/python/tik/maya/core/plug.py:618-642` (the power node), and add methods to the `Plug` class
- Test: `tests/unit/test_plug_math_helpers.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Plug.minimum(other) -> Plug` — `min(self, other)`; `other` is `Plug | float`
  - `Plug.maximum(other) -> Plug` — `max(self, other)`
  - `Plug.clamped(low, high) -> Plug` — `min(max(self, low), high)`
  - `Plug.lerp(other, weight) -> Plug` — `self + (other - self) * weight`
  - `Plug.gt(threshold, if_true, if_false) -> Plug` — `condition` node, operation 2 (Greater Than)

  All accept `Plug | int | float` for every operand and return a scalar `Plug`.

**Background:** `condition` is a legacy node available on every Maya. Native `min`/`max`/`clampRange` are 2025+, so these helpers use `condition` for `minimum`/`maximum` too — one node either way, and no version branch to maintain. `lerp` is expressed with existing guarded operators, so it needs no node of its own.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_plug_math_helpers.py`:

```python
"""Tests for the scalar comparison/blend helpers on Plug."""

import tik.maya as tm
from tik.maya.core.constants import NodeNames


def _holder(**attrs):
    node = tm.Transform.create(name="holder")
    plugs = {}
    for name, value in attrs.items():
        plugs[name] = tm.attribute.add_float(node, name, default=value)
    return node, plugs


def test_minimum_picks_the_smaller():
    _node, plugs = _holder(a=5.0)
    result = plugs["a"].minimum(3.0)
    assert abs(result.value - 3.0) < 1e-6
    plugs["a"].value = 1.0
    assert abs(result.value - 1.0) < 1e-6


def test_maximum_picks_the_larger():
    _node, plugs = _holder(a=5.0)
    result = plugs["a"].maximum(8.0)
    assert abs(result.value - 8.0) < 1e-6
    plugs["a"].value = 12.0
    assert abs(result.value - 12.0) < 1e-6


def test_minimum_accepts_a_plug():
    _node, plugs = _holder(a=5.0, b=2.0)
    result = plugs["a"].minimum(plugs["b"])
    assert abs(result.value - 2.0) < 1e-6


def test_clamped_bounds_both_sides():
    _node, plugs = _holder(a=5.0)
    result = plugs["a"].clamped(1.0, 3.0)
    assert abs(result.value - 3.0) < 1e-6
    plugs["a"].value = 0.0
    assert abs(result.value - 1.0) < 1e-6
    plugs["a"].value = 2.0
    assert abs(result.value - 2.0) < 1e-6


def test_lerp_interpolates():
    _node, plugs = _holder(a=0.0, b=10.0, w=0.25)
    result = plugs["a"].lerp(plugs["b"], plugs["w"])
    assert abs(result.value - 2.5) < 1e-6
    plugs["w"].value = 1.0
    assert abs(result.value - 10.0) < 1e-6


def test_gt_switches_branches():
    _node, plugs = _holder(a=5.0)
    result = plugs["a"].gt(10.0, 100.0, -100.0)
    assert abs(result.value - (-100.0)) < 1e-6
    plugs["a"].value = 20.0
    assert abs(result.value - 100.0) < 1e-6


def test_power_uses_a_supported_node():
    _node, plugs = _holder(a=2.0)
    result = plugs["a"] ** 3.0
    assert abs(result.value - 8.0) < 1e-6
    expected = "power" if NodeNames.uses_native_math_nodes else "multiplyDivide"
    assert result.node.type == expected
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_plug_math_helpers.py -v`
Expected: FAIL — `AttributeError: 'Plug' object has no attribute 'minimum'`

- [ ] **Step 3: Add the helper methods to `Plug`**

Add these as public methods on the `Plug` class in `src/python/tik/maya/core/plug.py`, placed after the arithmetic dunder methods:

```python
    # ------------------------------------------------- comparison helpers
    def _condition(self, operation: int, other, if_true, if_false) -> "Plug":
        """Build a ``condition`` node comparing ``self`` against ``other``.

        ``condition`` exists on every supported Maya, so these helpers need no
        version branch (native ``min``/``max``/``clampRange`` are 2025+).
        """
        node = cmds.createNode("condition", name="condition#")
        cmds.setAttr(f"{node}.operation", operation)
        cmds.connectAttr(self.path, f"{node}.firstTerm", force=True)
        for attr, value in (
            ("secondTerm", other),
            ("colorIfTrueR", if_true),
            ("colorIfFalseR", if_false),
        ):
            if isinstance(value, Plug):
                cmds.connectAttr(value.path, f"{node}.{attr}", force=True)
            elif isinstance(value, (int, float)):
                cmds.setAttr(f"{node}.{attr}", float(value))
            else:
                raise TypeError(
                    f"'{attr}' must be a Plug or numeric value, got {type(value)}"
                )
        return self._create_plug(node, "outColorR")

    def minimum(self, other) -> "Plug":
        """Return a plug carrying ``min(self, other)``."""
        return self._condition(4, other, self, other)  # 4 = Less Than

    def maximum(self, other) -> "Plug":
        """Return a plug carrying ``max(self, other)``."""
        return self._condition(2, other, self, other)  # 2 = Greater Than

    def clamped(self, low, high) -> "Plug":
        """Return a plug carrying ``min(max(self, low), high)``."""
        return self.maximum(low).minimum(high)

    def lerp(self, other, weight) -> "Plug":
        """Return a plug carrying ``self + (other - self) * weight``."""
        return self + (other - self) * weight

    def gt(self, threshold, if_true, if_false) -> "Plug":
        """Return ``if_true`` when ``self > threshold``, else ``if_false``."""
        return self._condition(2, threshold, if_true, if_false)  # 2 = Greater Than
```

- [ ] **Step 4: Version-guard the power node**

Replace the body of `_create_power_node_single` (`src/python/tik/maya/core/plug.py:618-642`) with:

```python
    def _create_power_node_single(self, other) -> "Plug":
        """Create a power node for single-value power operation.

        For Maya 2025+, uses the native 'power' node.
        For Maya 2024 and older, uses 'multiplyDivide' with operation=3 (power),
        which computes ``input1 ^ input2`` per component.

        Args:
            other: The right-hand operand (Plug or numeric value) for the exponent.

        Returns:
            Plug: The output plug of the power node.
        """
        if NodeNames.uses_native_math_nodes:
            node = cmds.createNode("power", name="power#")
            input_attr = "input"
            exponent_attr = "exponent"
            output_attr = "output"
        else:
            node = cmds.createNode("multiplyDivide", name="multiplyDivide_power#")
            cmds.setAttr(f"{node}.operation", 3)  # 3 = Power
            input_attr = "input1X"
            exponent_attr = "input2X"
            output_attr = "outputX"

        # Connect input (left operand - self / base)
        cmds.connectAttr(self.path, f"{node}.{input_attr}", force=True)

        # Connect or set exponent (right operand - other)
        if isinstance(other, Plug):
            cmds.connectAttr(other.path, f"{node}.{exponent_attr}", force=True)
        elif isinstance(other, (int, float)):
            cmds.setAttr(f"{node}.{exponent_attr}", float(other))
        else:
            raise TypeError(
                f"Right operand must be a Plug or numeric value, got {type(other)}"
            )

        return self._create_plug(node, output_attr)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_plug_math_helpers.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 6: Run the existing plug suites for regressions**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_plug.py tests/unit/test_plug_operators.py tests/unit/test_plug_ambiguous.py -q`
Expected: PASS, no new failures.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/maya/core/plug.py tests/unit/test_plug_math_helpers.py
git commit -m "feat(tik.maya): plug comparison helpers and version-guarded power node"
```

---

### Task 2: `Joint` extensions — preferred angle, chain duplication, mirrored orientation

**Files:**
- Modify: `src/python/tik/maya/types/joint.py:85-108` (`orient_chain`), plus new members
- Test: `tests/unit/test_joint_chain_ops.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Joint.preferred_angle` — property, get/set `tuple[float, float, float]` in degrees
  - `Joint.duplicate_chain(joints, prefix, parent=None) -> list[Joint]` — classmethod. Copies `jointOrient`, `translate`, `rotate`, `scale`, `preferredAngle`, `radius`. Names are `f"{prefix}_{index}_jnt"`. Returns the copies, root first.
  - `Joint.orient_chain(joints, aim_axis="x", up_axis="y", world_up=(0,1,0), reverse_aim=False, reverse_up=False)` — two new keyword args.

**Background:** `IkFkChain._copy_chain` (being deleted in Task 9) rebuilt joints by hand and silently dropped `preferredAngle` and `scale`. A zero preferred angle lets an `ikRPsolver` chain solve to a degenerate plane. `reverse_aim`/`reverse_up` are what mirrored-behaviour right sides need: Maya's `orientJoint` flag takes a sign through the axis string, so reversing means negating the resulting `jointOrient` about the relevant axes by 180 degrees.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_joint_chain_ops.py`:

```python
"""Tests for Joint.preferred_angle, duplicate_chain and mirrored orientation."""

import tik.maya as tm


def _chain(name="arm"):
    return tm.Joint.chain(
        [(0, 0, 0), (4, 0, -1), (8, 0, 0)], name_pattern=name + "_{index}"
    )


def test_preferred_angle_round_trips():
    joint = tm.Joint.create(name="single")
    joint.preferred_angle = (0.0, 0.0, -15.0)
    values = joint.preferred_angle
    assert abs(values[2] - (-15.0)) < 1e-4


def test_duplicate_chain_matches_positions():
    joints = _chain()
    copies = tm.Joint.duplicate_chain(joints, prefix="arm_ik")
    assert len(copies) == 3
    assert copies[0].name == "arm_ik_0_jnt"
    for source, copy in zip(joints, copies):
        assert (source.world_translation - copy.world_translation).length() < 1e-5


def test_duplicate_chain_is_parented_as_a_chain():
    joints = _chain()
    parent = tm.Transform.create(name="chain_parent")
    copies = tm.Joint.duplicate_chain(joints, prefix="arm_fk", parent=parent)
    assert copies[0].parent.name == parent.name
    assert copies[1].parent.name == copies[0].name
    assert copies[2].parent.name == copies[1].name


def test_duplicate_chain_carries_preferred_angle_and_scale():
    joints = _chain()
    joints[1].preferred_angle = (0.0, 0.0, -20.0)
    joints[1].scale = (2.0, 2.0, 2.0)
    copies = tm.Joint.duplicate_chain(joints, prefix="arm_pa")
    assert abs(copies[1].preferred_angle[2] - (-20.0)) < 1e-4
    assert abs(copies[1].scale.x - 2.0) < 1e-5


def test_orient_chain_aims_x_down_the_chain():
    joints = _chain("plain")
    tm.Joint.orient_chain(joints)
    axis = joints[0].world_matrix_axis_x()
    to_child = joints[1].world_translation - joints[0].world_translation
    to_child.normalize()
    assert axis * to_child > 0.99


def test_reverse_aim_points_x_back_up_the_chain():
    joints = _chain("mirrored")
    tm.Joint.orient_chain(joints, reverse_aim=True, reverse_up=True)
    axis = joints[0].world_matrix_axis_x()
    to_child = joints[1].world_translation - joints[0].world_translation
    to_child.normalize()
    assert axis * to_child < -0.99
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_joint_chain_ops.py -v`
Expected: FAIL — `AttributeError: 'Joint' object has no attribute 'preferred_angle'`

- [ ] **Step 3: Add `preferred_angle` and `world_matrix_axis_x` helpers**

Add to `Joint` in `src/python/tik/maya/types/joint.py`, next to the `joint_orient` property:

```python
    @property
    def preferred_angle(self):
        """Get or set the preferred angle values (degrees).

        An ``ikRPsolver`` chain with a zero preferred angle can solve to a
        degenerate plane, so this must survive chain duplication.
        """
        return tuple(self["preferredAngle"].get()[0])

    @preferred_angle.setter
    def preferred_angle(self, value):
        self["preferredAngle"].set((value[0], value[1], value[2]))

    def world_matrix_axis_x(self):
        """Return the normalized world X axis of this joint."""
        matrix = self["worldMatrix[0]"].value
        axis = OpenMaya.MVector(matrix[0], matrix[1], matrix[2])
        axis.normalize()
        return axis
```

Add the import at the top of the file, beside the existing imports:

```python
from maya.api import OpenMaya
```

- [ ] **Step 4: Add `duplicate_chain`**

Add as a classmethod on `Joint`, directly after `chain`:

```python
    @classmethod
    def duplicate_chain(
        cls,
        joints: Sequence["Joint"],
        prefix: str,
        parent=None,
    ) -> list["Joint"]:
        """Duplicate ``joints`` as a fresh parented chain named ``<prefix>_<i>_jnt``.

        Copies ``jointOrient``, ``translate``, ``rotate``, ``scale``,
        ``preferredAngle`` and ``radius``. Dropping ``preferredAngle`` would let
        an ``ikRPsolver`` chain solve to a degenerate plane.

        Args:
            joints: Source chain, root first.
            prefix: Name prefix for the copies.
            parent: Optional parent for the first copy.

        Returns:
            The copies, root first.
        """
        copies: list[Joint] = []
        current_parent = parent
        for index, source in enumerate(joints):
            joint = cls.create(
                name=f"{prefix}_{index}_jnt",
                parent=current_parent.long_name
                if hasattr(current_parent, "long_name")
                else current_parent,
                radius=source.radius,
            )
            joint.joint_orient = source.joint_orient
            joint.translate = tuple(source.translate)
            joint.rotate = tuple(source.rotate)
            joint.scale = tuple(source.scale)
            joint.preferred_angle = source.preferred_angle
            copies.append(joint)
            current_parent = joint
        return copies
```

- [ ] **Step 5: Add `reverse_aim` / `reverse_up` to `orient_chain`**

Replace `orient_chain` (`src/python/tik/maya/types/joint.py:85-108`) with:

```python
    @staticmethod
    def orient_chain(
        joints: Iterable["Joint"],
        aim_axis: str = "x",
        up_axis: str = "y",
        world_up: Sequence[float] = (0, 1, 0),
        reverse_aim: bool = False,
        reverse_up: bool = False,
    ) -> None:
        """Orient ``joints`` so ``aim_axis`` points down the chain.

        The last joint inherits its parent orientation (zero joint orient).

        Args:
            joints: The chain, root first.
            aim_axis: Axis aimed down the chain.
            up_axis: Secondary axis.
            world_up: World up reference.
            reverse_aim: Flip the aim axis 180 degrees about ``up_axis`` — a
                mirrored-behaviour side, where the aim axis points back up the
                chain and ``translateX`` is therefore negative.
            reverse_up: Flip the up axis 180 degrees about ``aim_axis``.
        """
        joints = list(joints)
        orient_flag = f"{aim_axis}{up_axis}{''.join(sorted(set('xyz') - {aim_axis, up_axis}))}"
        secondary = f"{up_axis}up"
        for joint in joints[:-1]:
            cmds.joint(
                joint.long_name,
                edit=True,
                orientJoint=orient_flag,
                secondaryAxisOrient=secondary,
                zeroScaleOrient=True,
            )
        if joints:
            cmds.joint(joints[-1].long_name, edit=True, orientation=(0, 0, 0))
        if not (reverse_aim or reverse_up):
            return
        index = "xyz".index
        for joint in joints:
            values = list(joint.joint_orient)
            if reverse_aim:
                values[index(up_axis)] += 180.0
            if reverse_up:
                values[index(aim_axis)] += 180.0
            joint.joint_orient = tuple(
                ((value + 180.0) % 360.0) - 180.0 for value in values
            )
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_joint_chain_ops.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 7: Run the existing joint suites for regressions**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_joint.py tests/unit/test_joint_helpers.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/maya/types/joint.py tests/unit/test_joint_chain_ops.py
git commit -m "feat(tik.maya): Joint.preferred_angle, duplicate_chain, mirrored orient_chain"
```

---

### Task 3: `MatrixConstraint` cutoff parameter

**Files:**
- Modify: `src/python/tik/maya/constructs/matrix_constraint.py:48-121`
- Test: `tests/unit/test_matrix_constraint.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `MatrixConstraint.create(..., cutoff=None)`. When `cutoff` is given, the driver's world matrix is multiplied by `cutoff.worldInverseMatrix[0]` before the driven's parent inverse, so transforms at or above `cutoff` do not reach the driven.

**Background:** the constraint compensates only the driven's immediate parent (`matrix_constraint.py:105-106`). With controllers under `control_grp` driving joints under `rig_grp`/`bind_grp`, the driver sits beneath groups that would otherwise double-transform. The legacy trigger needed `source_parent_cutoff` on nearly every controller-to-joint connection for this reason.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_matrix_constraint.py`:

```python
def test_cutoff_ignores_transforms_at_or_above_it():
    """A driver under a moved group should not drag the driven when cut off."""
    cutoff_grp = tm.Transform.create(name="cutoff_grp")
    driver = tm.Transform.create(name="cut_driver", parent=cutoff_grp.long_name)
    driven = tm.Transform.create(name="cut_driven")

    tm.MatrixConstraint.create(driver, driven, maintain_offset=True, cutoff=cutoff_grp)

    cutoff_grp.translate = (0, 10, 0)
    assert driven.world_translation.length() < 1e-4

    driver.translate = (3, 0, 0)
    assert abs(driven.world_translation.x - 3.0) < 1e-4


def test_without_cutoff_the_group_still_drives():
    parent_grp = tm.Transform.create(name="plain_grp")
    driver = tm.Transform.create(name="plain_driver", parent=parent_grp.long_name)
    driven = tm.Transform.create(name="plain_driven")

    tm.MatrixConstraint.create(driver, driven, maintain_offset=True)

    parent_grp.translate = (0, 10, 0)
    assert abs(driven.world_translation.y - 10.0) < 1e-4
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_matrix_constraint.py -k cutoff -v`
Expected: FAIL — `TypeError: create() got an unexpected keyword argument 'cutoff'`

- [ ] **Step 3: Add the parameter**

In `src/python/tik/maya/constructs/matrix_constraint.py`, add `cutoff` to the `create` signature after `skip_scale`:

```python
        cutoff=None,
```

Add to the docstring's `Args:` block:

```
            cutoff: Node whose world transform (and everything above it) is
                removed from the driver's contribution. Use when the driver
                lives under groups that would otherwise double-transform the
                driven.
```

Then, immediately after the `source_plug` is chosen (the line `source_plug = driver_plugs[0]` and its `else` branch, before `mult_matrix` is created), insert:

```python
        if cutoff is not None:
            cutoff = resolve(cutoff) if isinstance(cutoff, str) else cutoff
            cutoff_mult = create_node("multMatrix", name=f"{name}_cutoffMultMatrix")
            source_plug >> cutoff_mult["matrixIn[0]"]
            cutoff["worldInverseMatrix[0]"] >> cutoff_mult["matrixIn[1]"]
            source_plug = cutoff_mult["matrixSum"]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_matrix_constraint.py -v`
Expected: PASS, including both new tests.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/maya/constructs/matrix_constraint.py tests/unit/test_matrix_constraint.py
git commit -m "feat(tik.maya): MatrixConstraint cutoff parameter"
```

---

### Task 4: `Measure` accepts matrix plugs

**Files:**
- Modify: `src/python/tik/maya/constructs/measure.py:29-38`
- Test: `tests/unit/test_measure.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `Measure.create(start, end, name=None)` where `start` and `end` may each be a node, a node name, **or a matrix `Plug`**. `.start` / `.end` hold whatever was passed.

**Background:** the stretch and pole-pin networks measure between computed positions, not only between nodes (`measure.py:33-37` wires `worldMatrix[0]` of two nodes).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_measure.py`:

```python
def test_create_accepts_matrix_plugs():
    a = tm.Transform.create(name="plug_measure_a")
    b = tm.Transform.create(name="plug_measure_b")
    b.translate = (0, 0, 5)

    measure = tm.Measure.create(
        a["worldMatrix[0]"], b["worldMatrix[0]"], name="plug_measure"
    )
    assert abs(measure.distance.value - 5.0) < 1e-4

    b.translate = (0, 0, 9)
    assert abs(measure.distance.value - 9.0) < 1e-4


def test_create_mixes_a_node_and_a_plug():
    a = tm.Transform.create(name="mixed_measure_a")
    b = tm.Transform.create(name="mixed_measure_b")
    b.translate = (4, 0, 0)

    measure = tm.Measure.create(a, b["worldMatrix[0]"], name="mixed_measure")
    assert abs(measure.distance.value - 4.0) < 1e-4
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_measure.py -k plug -v`
Expected: FAIL — the `Plug` has no `name` / `__getitem__("worldMatrix[0]")` behaviour the current code assumes.

- [ ] **Step 3: Accept plugs**

In `src/python/tik/maya/constructs/measure.py`, add a helper below `_node`:

```python
def _matrix_plug(item):
    """Return a world-matrix plug for a node, a node name, or a matrix plug."""
    if isinstance(item, Plug):
        return item
    return _node(item)["worldMatrix[0]"]


def _label(item) -> str:
    """Short name for an item that may be a node or a plug."""
    return item.node.name if isinstance(item, Plug) else _node(item).name
```

Replace `create` with:

```python
    @classmethod
    @undo
    def create(cls, start, end, name: Optional[str] = None) -> "Measure":
        """Measure the distance between ``start`` and ``end``.

        Args:
            start: Node, node name, or matrix plug.
            end: Node, node name, or matrix plug.
            name: Prefix for the created node.
        """
        name = name or f"{_label(start)}_{_label(end)}"
        node = create_node("distanceBetween", name=f"{name}_distance")
        _matrix_plug(start) >> node["inMatrix1"]
        _matrix_plug(end) >> node["inMatrix2"]
        return cls(node, start, end, node["distance"].value)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_measure.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/maya/constructs/measure.py tests/unit/test_measure.py
git commit -m "feat(tik.maya): Measure accepts matrix plugs"
```

---

### Task 5: `MatrixBlend` construct

**Files:**
- Create: `src/python/tik/maya/constructs/matrix_blend.py`
- Modify: `src/python/tik/maya/constructs/__init__.py`, `src/python/tik/maya/__init__.py`
- Test: `tests/unit/test_matrix_blend.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `MatrixBlend.create(base, targets, weights=None, *, name=None) -> MatrixBlend`
    - `base`: node, name, or matrix plug — the `inputMatrix` (weight-zero end).
    - `targets`: sequence of nodes, names, or matrix plugs.
    - `weights`: optional sequence of `Plug | float`, one per target. Defaults to `1.0`.
  - `.output` → matrix `Plug` (`blendMatrix.outputMatrix`)
  - `.node` → the `blendMatrix` node
  - `.weight_plug(index)` → the `target[i].weight` `Plug`
  - `.delete()`

**Background:** `MatrixSwitch` is discrete — a `condition` per target driven by an integer (`matrix_switch.py:135-141`) — so it cannot serve a continuous 0..1 blend. The pattern is currently inlined in `IkFkChain._blend` (`ikfk_chain.py:105-118`); this extracts it before that file is deleted in Task 9.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_matrix_blend.py`:

```python
"""Tests for the MatrixBlend construct."""

from maya import cmds

import tik.maya as tm


def _pair():
    a = tm.Transform.create(name="blend_a")
    b = tm.Transform.create(name="blend_b")
    b.translate = (10, 0, 0)
    return a, b


def test_weight_zero_is_the_base():
    a, b = _pair()
    driven = tm.Transform.create(name="blend_driven")
    blend = tm.MatrixBlend.create(a, [b], name="pair")
    blend.weight_plug(0).value = 0.0
    tm.MatrixConstraint.create(blend.output, driven, maintain_offset=False)
    assert driven.world_translation.length() < 1e-4


def test_weight_one_is_the_target():
    a, b = _pair()
    driven = tm.Transform.create(name="blend_driven_one")
    blend = tm.MatrixBlend.create(a, [b], name="pair_one")
    blend.weight_plug(0).value = 1.0
    tm.MatrixConstraint.create(blend.output, driven, maintain_offset=False)
    assert abs(driven.world_translation.x - 10.0) < 1e-4


def test_weight_is_continuous():
    a, b = _pair()
    driven = tm.Transform.create(name="blend_driven_half")
    blend = tm.MatrixBlend.create(a, [b], name="pair_half")
    blend.weight_plug(0).value = 0.25
    tm.MatrixConstraint.create(blend.output, driven, maintain_offset=False)
    assert abs(driven.world_translation.x - 2.5) < 1e-4


def test_weights_accept_plugs():
    a, b = _pair()
    holder = tm.Transform.create(name="blend_holder")
    switch = tm.attribute.add_float(holder, "ikFk", default=1.0, min=0.0, max=1.0)
    blend = tm.MatrixBlend.create(a, [b], [switch], name="pair_plug")
    assert cmds.listConnections(
        blend.weight_plug(0).path, source=True, destination=False
    )


def test_accepts_matrix_plugs_for_base_and_targets():
    a, b = _pair()
    blend = tm.MatrixBlend.create(
        a["worldMatrix[0]"], [b["worldMatrix[0]"]], name="pair_plugs"
    )
    blend.weight_plug(0).value = 1.0
    assert blend.output.value[12] - 10.0 < 1e-4


def test_delete_removes_the_node():
    a, b = _pair()
    blend = tm.MatrixBlend.create(a, [b], name="pair_delete")
    node_name = blend.node.long_name
    blend.delete()
    assert not cmds.objExists(node_name)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_matrix_blend.py -v`
Expected: FAIL — `AttributeError: module 'tik.maya' has no attribute 'MatrixBlend'`

- [ ] **Step 3: Write the construct**

Create `src/python/tik/maya/constructs/matrix_blend.py`:

```python
"""Continuous N-target matrix blend.

A ``blendMatrix`` whose targets carry float weights, unlike ``MatrixSwitch``
which selects one target discretely through ``condition`` nodes.
"""

from __future__ import annotations

from typing import Optional, Sequence

from maya import cmds

from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import resolve
from ..core.scene import create_node


def _matrix_plug(item) -> Plug:
    """Return a world-matrix plug for a node, a node name, or a matrix plug."""
    if isinstance(item, Plug):
        return item
    node = resolve(item) if isinstance(item, str) else item
    return node["worldMatrix[0]"]


class MatrixBlend:
    """Wrapper for a ``blendMatrix`` with float-weighted targets."""

    def __init__(self, node) -> None:
        self.node = node

    @classmethod
    @undo
    def create(
        cls,
        base,
        targets: Sequence,
        weights: Optional[Sequence] = None,
        *,
        name: Optional[str] = None,
    ) -> "MatrixBlend":
        """Blend ``targets`` over ``base``.

        Args:
            base: Node, name, or matrix plug used at weight zero.
            targets: Nodes, names, or matrix plugs.
            weights: One ``Plug`` or float per target; defaults to ``1.0``.
            name: Prefix for the created node.

        Returns:
            The construct wrapping the new ``blendMatrix``.
        """
        targets = list(targets)
        if not targets:
            raise ValueError("MatrixBlend needs at least one target.")
        if weights is not None and len(weights) != len(targets):
            raise ValueError("weights must have one entry per target.")
        name = name or "matrixBlend"
        node = create_node("blendMatrix", name=f"{name}_blendMatrix")
        _matrix_plug(base) >> node["inputMatrix"]
        for index, target in enumerate(targets):
            _matrix_plug(target) >> node[f"target[{index}].targetMatrix"]
            weight = 1.0 if weights is None else weights[index]
            if isinstance(weight, Plug):
                weight >> node[f"target[{index}].weight"]
            else:
                node[f"target[{index}].weight"].value = float(weight)
        return cls(node)

    @property
    def output(self) -> Plug:
        """Return the blended world-matrix plug."""
        return self.node["outputMatrix"]

    def weight_plug(self, index: int = 0) -> Plug:
        """Return the weight plug for target ``index``."""
        return self.node[f"target[{index}].weight"]

    @undo
    def delete(self) -> None:
        """Delete the blend node."""
        if self.node.exists():
            cmds.delete(self.node.long_name)
```

- [ ] **Step 4: Export it**

In `src/python/tik/maya/constructs/__init__.py`, add the import alongside the others and add `"MatrixBlend"` to `__all__`:

```python
from .matrix_blend import MatrixBlend
```

In `src/python/tik/maya/__init__.py`, add `MatrixBlend` to the constructs import block and to `__all__`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_matrix_blend.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/maya/constructs/matrix_blend.py src/python/tik/maya/constructs/__init__.py src/python/tik/maya/__init__.py tests/unit/test_matrix_blend.py
git commit -m "feat(tik.maya): MatrixBlend construct for continuous matrix blending"
```

---

### Task 6: `ChainLengths` construct

**Files:**
- Create: `src/python/tik/maya/constructs/chain_lengths.py`
- Modify: `src/python/tik/maya/constructs/__init__.py`, `src/python/tik/maya/__init__.py`
- Test: `tests/unit/test_chain_lengths.py` (create)

**Interfaces:**
- Consumes: `Plug.minimum`, `Plug.lerp` (Task 1).
- Produces:
  - `ChainLengths.create(joints, *, side_sign=1, name=None) -> ChainLengths`
    `joints` is the chain root-first; segment `i` is the gap between `joints[i]` and `joints[i+1]`, driven onto `joints[i+1].translateX`.
  - `.rest_plugs` → `list[Plug]`, one per segment, writable and connectable. Initialised to the measured rest length.
  - `.total_length` → `Plug` carrying the sum of `rest_plugs`.
  - `.add_factor(plug)` → multiplies every segment's output by `plug`. Returns `None`.
  - `.add_override(lengths, weight)` → final `lerp` per segment towards `lengths[i]` by `weight`. Returns `None`.
  - `.segment_count` → `int`
  - `.delete()`

**Background:** this is always built, because per-segment scale is always on. `tx_i = side_sign * rest_i * PRODUCT(factors)`. An unbuilt factor is `1.0`, so stretch and squash flags cannot interact. `rest_plugs` being live is what lets one multiply rescale a bone through the soft threshold, the stretch share, the limit and the squash together.

The rest plugs live on a dedicated holder transform so they survive independently of the joints.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_chain_lengths.py`:

```python
"""Tests for the ChainLengths construct."""

from maya import cmds

import tik.maya as tm


def _chain(name="cl"):
    return tm.Joint.chain(
        [(0, 0, 0), (4, 0, 0), (10, 0, 0)], name_pattern=name + "_{index}"
    )


def test_rest_plugs_hold_measured_lengths():
    joints = _chain()
    lengths = tm.ChainLengths.create(joints, name="cl")
    assert lengths.segment_count == 2
    assert abs(lengths.rest_plugs[0].value - 4.0) < 1e-4
    assert abs(lengths.rest_plugs[1].value - 6.0) < 1e-4


def test_total_length_sums_the_rest_plugs():
    joints = _chain("total")
    lengths = tm.ChainLengths.create(joints, name="total")
    assert abs(lengths.total_length.value - 10.0) < 1e-4
    lengths.rest_plugs[0].value = 6.0
    assert abs(lengths.total_length.value - 12.0) < 1e-4


def test_no_factors_drives_tx_to_rest():
    joints = _chain("plain")
    lengths = tm.ChainLengths.create(joints, name="plain")
    assert abs(joints[1].translate.x - 4.0) < 1e-4
    assert abs(joints[2].translate.x - 6.0) < 1e-4


def test_side_sign_negates_tx():
    joints = _chain("right")
    lengths = tm.ChainLengths.create(joints, side_sign=-1, name="right")
    assert abs(joints[1].translate.x - (-4.0)) < 1e-4
    assert abs(joints[2].translate.x - (-6.0)) < 1e-4


def test_rest_plug_drives_tx_live():
    joints = _chain("live")
    lengths = tm.ChainLengths.create(joints, name="live")
    lengths.rest_plugs[0].value = 8.0
    assert abs(joints[1].translate.x - 8.0) < 1e-4


def test_a_factor_scales_every_segment():
    joints = _chain("factor")
    holder = tm.Transform.create(name="factor_holder")
    factor = tm.attribute.add_float(holder, "factor", default=1.0)
    lengths = tm.ChainLengths.create(joints, name="factor")
    lengths.add_factor(factor)
    assert abs(joints[1].translate.x - 4.0) < 1e-4
    factor.value = 2.0
    assert abs(joints[1].translate.x - 8.0) < 1e-4
    assert abs(joints[2].translate.x - 12.0) < 1e-4


def test_factors_multiply_together():
    joints = _chain("two")
    holder = tm.Transform.create(name="two_holder")
    first = tm.attribute.add_float(holder, "first", default=2.0)
    second = tm.attribute.add_float(holder, "second", default=3.0)
    lengths = tm.ChainLengths.create(joints, name="two")
    lengths.add_factor(first)
    lengths.add_factor(second)
    assert abs(joints[1].translate.x - 24.0) < 1e-4


def test_override_blends_towards_explicit_lengths():
    joints = _chain("pin")
    holder = tm.Transform.create(name="pin_holder")
    weight = tm.attribute.add_float(holder, "pin", default=0.0, min=0.0, max=1.0)
    upper = tm.attribute.add_float(holder, "upper", default=9.0)
    lower = tm.attribute.add_float(holder, "lower", default=1.0)
    lengths = tm.ChainLengths.create(joints, name="pin")
    lengths.add_override([upper, lower], weight)
    assert abs(joints[1].translate.x - 4.0) < 1e-4
    weight.value = 1.0
    assert abs(joints[1].translate.x - 9.0) < 1e-4
    assert abs(joints[2].translate.x - 1.0) < 1e-4


def test_delete_releases_the_joints():
    joints = _chain("gone")
    lengths = tm.ChainLengths.create(joints, name="gone")
    lengths.delete()
    assert not cmds.listConnections(
        f"{joints[1].name}.translateX", source=True, destination=False
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_chain_lengths.py -v`
Expected: FAIL — `AttributeError: module 'tik.maya' has no attribute 'ChainLengths'`

- [ ] **Step 3: Write the construct**

Create `src/python/tik/maya/constructs/chain_lengths.py`:

```python
"""Per-segment length drivers for a joint chain.

Owns nothing but segment lengths::

    tx_i = side_sign * rest_i * PRODUCT(factors)

``rest_plugs`` are live and writable, so one multiply on a rest plug rescales
that bone consistently through anything downstream that reads
``total_length``. Stretch and squash are merely factors added from outside; an
unbuilt factor is ``1.0``, so flags never interact.
"""

from __future__ import annotations

from typing import Optional, Sequence

from maya import cmds

from ..core import attribute
from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import resolve
from ..core.scene import create_node
from ..types.transform import Transform


def _node(item):
    return resolve(item) if isinstance(item, str) else item


class ChainLengths:
    """Drives ``translateX`` of every joint after the root."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.holder: Optional[Transform] = None
        self.joints: list = []
        self.rest_plugs: list[Plug] = []
        self._outputs: list[Plug] = []
        self._factors: list[Plug] = []
        self._side_sign = 1
        self._total: Optional[Plug] = None

    @classmethod
    @undo
    def create(
        cls,
        joints: Sequence,
        *,
        side_sign: int = 1,
        name: Optional[str] = None,
    ) -> "ChainLengths":
        """Build the length network for ``joints``.

        Args:
            joints: The chain, root first. At least two joints.
            side_sign: ``-1`` on a mirrored-behaviour side, where the aim axis
                points back up the chain and ``translateX`` is negative.
            name: Prefix for created nodes.

        Returns:
            The construct.
        """
        joints = [_node(joint) for joint in joints]
        if len(joints) < 2:
            raise ValueError("ChainLengths needs at least two joints.")
        chain = cls(name or "chainLengths")
        chain.joints = joints
        chain._side_sign = -1 if side_sign < 0 else 1

        chain.holder = Transform.create(name=f"{chain.name}_lengths_grp")
        attribute.lock_and_hide(chain.holder, attribute.TRANSFORM_ATTRS)

        for index in range(len(joints) - 1):
            rest = abs(joints[index + 1].translate.x)
            plug = attribute.add_float(
                chain.holder, f"restLength{index}", default=rest
            )
            chain.rest_plugs.append(plug)
            chain._outputs.append(plug)
        chain._connect()
        return chain

    # ----------------------------------------------------------- internals
    def _connect(self) -> None:
        """Drive each joint's ``translateX`` from its current output plug."""
        for index, plug in enumerate(self._outputs):
            driver = plug if self._side_sign > 0 else plug * -1.0
            driver >> self.joints[index + 1]["translateX"]

    def _rebuild(self, outputs: list[Plug]) -> None:
        """Swap the output plugs and rewire the joints."""
        self._outputs = outputs
        self._connect()

    # ----------------------------------------------------------- accessors
    @property
    def segment_count(self) -> int:
        """Number of segments (one fewer than the joint count)."""
        return len(self.rest_plugs)

    @property
    def total_length(self) -> Plug:
        """Plug carrying the sum of every rest length."""
        if self._total is None:
            total = self.rest_plugs[0]
            for plug in self.rest_plugs[1:]:
                total = total + plug
            self._total = total
        return self._total

    @undo
    def add_factor(self, plug: Plug) -> None:
        """Multiply every segment's output by ``plug``."""
        self._factors.append(plug)
        self._rebuild([output * plug for output in self._outputs])

    @undo
    def add_override(self, lengths: Sequence, weight) -> None:
        """Blend every segment towards an explicit length by ``weight``."""
        lengths = list(lengths)
        if len(lengths) != self.segment_count:
            raise ValueError("add_override needs one length per segment.")
        self._rebuild(
            [
                output.lerp(target, weight)
                for output, target in zip(self._outputs, lengths)
            ]
        )

    @undo
    def delete(self) -> None:
        """Delete the network, leaving the joints unconnected."""
        for joint in self.joints[1:]:
            plug = f"{joint.long_name}.translateX"
            for source in cmds.listConnections(
                plug, source=True, destination=False, plugs=True
            ) or []:
                cmds.disconnectAttr(source, plug)
        if self.holder is not None and self.holder.exists():
            cmds.delete(self.holder.long_name)
```

- [ ] **Step 4: Export it**

Add `from .chain_lengths import ChainLengths` to `src/python/tik/maya/constructs/__init__.py` with `"ChainLengths"` in `__all__`, and add `ChainLengths` to `src/python/tik/maya/__init__.py`'s import block and `__all__`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_chain_lengths.py -v`
Expected: PASS, 9 tests.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/maya/constructs/chain_lengths.py src/python/tik/maya/constructs/__init__.py src/python/tik/maya/__init__.py tests/unit/test_chain_lengths.py
git commit -m "feat(tik.maya): ChainLengths construct for per-segment length drivers"
```

---

### Task 7: `SoftIk` construct

**Files:**
- Create: `src/python/tik/maya/constructs/soft_ik.py`
- Modify: `src/python/tik/maya/constructs/__init__.py`, `src/python/tik/maya/__init__.py`
- Test: `tests/unit/test_soft_ik.py` (create)

**Interfaces:**
- Consumes: `Plug.gt` (Task 1), `Measure.create` with plugs (Task 4).
- Produces:
  - `SoftIk.create(root, goal, chain_length, *, name=None, parent=None, scale_plug=None) -> SoftIk`
    - `root`: transform at the chain root, **upstream of the IK solve**.
    - `goal`: transform the chain reaches for (the IK control).
    - `chain_length`: `Plug` carrying total rest length — normally `ChainLengths.total_length`.
    - `scale_plug`: optional global-scale `Plug` the raw distance is divided by.
  - `.soft_plug` → the softness distance `Plug` (`softIk` on the construct's group; `0` disables)
  - `.stretch_plug` → 0..1 `Plug`; `0` = the goal is the soft point, `1` = the goal is the control
  - `.distance_plug` → the raw scaled root-to-goal distance
  - `.soft_distance` → `f(d)`
  - `.gap_plug` → `stretch * (d - f(d))`, the shortfall a stretch network consumes
  - `.goal_matrix` → world-matrix `Plug` for the ikHandle
  - `.group` → the construct's `Transform`
  - `.delete()`

**Background — the curve.** With `L` = `chain_length`, `ds = softIk + 0.001` (divide-by-zero guard), `da = L - ds`:

```
f(d) = d                          if d <= da
     = L - ds * e^(-(d-da)/ds)    if d >  da
```

- C0 at the seam: `f(da) = L - ds*e^0 = L - ds = da`.
- C1 at the seam: `f'(d>da) = e^(-(d-da)/ds)`, which is `1` at `d = da`.
- `f(d) -> L` as `d -> inf`, so the chain never fully straightens.

**Do not attempt a branchless form.** `min(d, L - ds*e^...)` picks the wrong branch below `da` (at `d=0, ds=1, L=10` the exponential term evaluates to `-8093`); `max` picks the wrong branch above. One `condition` stays.

**Geometry.** The goal point is `root + normalize(goal - root) * lerp(f(d), d, stretch)`. Built pure-math with `aimMatrix` for the direction frame, following `matrix_spline.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_soft_ik.py`:

```python
"""Tests for the SoftIk construct.

The three curve properties asserted here are what make the solve *soft*
rather than merely curved.
"""

import math

import tik.maya as tm

L = 10.0


def _rig(soft=1.0, stretch=0.0):
    root = tm.Transform.create(name="soft_root")
    goal = tm.Transform.create(name="soft_goal")
    holder = tm.Transform.create(name="soft_holder")
    length = tm.attribute.add_float(holder, "chainLength", default=L)
    soft_ik = tm.SoftIk.create(root, goal, length, name="soft")
    soft_ik.soft_plug.value = soft
    soft_ik.stretch_plug.value = stretch
    return root, goal, soft_ik


def _at(goal, soft_ik, distance):
    goal.translate = (distance, 0, 0)
    return soft_ik.soft_distance.value


def test_identity_below_the_seam():
    """f(d) == d while d <= da."""
    _root, goal, soft_ik = _rig(soft=1.0)
    for distance in (1.0, 4.0, 8.0):
        assert abs(_at(goal, soft_ik, distance) - distance) < 1e-3


def test_c0_continuity_at_the_seam():
    """f(da) == da, with da = L - ds."""
    _root, goal, soft_ik = _rig(soft=1.0)
    da = L - (1.0 + 0.001)
    assert abs(_at(goal, soft_ik, da) - da) < 1e-3


def test_c1_continuity_at_the_seam():
    """f'(da) == 1 — no velocity discontinuity."""
    _root, goal, soft_ik = _rig(soft=1.0)
    ds = 1.0 + 0.001
    da = L - ds
    step = 1e-3
    above = _at(goal, soft_ik, da + step)
    at = _at(goal, soft_ik, da)
    slope = (above - at) / step
    assert abs(slope - 1.0) < 1e-2


def test_asymptotic_to_chain_length():
    """f(d) -> L, so the chain never fully straightens."""
    _root, goal, soft_ik = _rig(soft=1.0)
    assert _at(goal, soft_ik, 50.0) < L
    assert abs(_at(goal, soft_ik, 50.0) - L) < 1e-3


def test_matches_the_closed_form_above_the_seam():
    _root, goal, soft_ik = _rig(soft=2.0)
    ds = 2.0 + 0.001
    da = L - ds
    distance = 12.0
    expected = L - ds * math.exp(-(distance - da) / ds)
    assert abs(_at(goal, soft_ik, distance) - expected) < 1e-3


def test_softness_zero_reaches_almost_the_full_length():
    _root, goal, soft_ik = _rig(soft=0.0)
    assert abs(_at(goal, soft_ik, 20.0) - L) < 1e-2


def test_gap_is_zero_without_stretch():
    _root, goal, soft_ik = _rig(soft=1.0, stretch=0.0)
    goal.translate = (20, 0, 0)
    assert abs(soft_ik.gap_plug.value) < 1e-4


def test_gap_is_the_shortfall_with_stretch():
    _root, goal, soft_ik = _rig(soft=1.0, stretch=1.0)
    goal.translate = (20, 0, 0)
    expected = 20.0 - soft_ik.soft_distance.value
    assert abs(soft_ik.gap_plug.value - expected) < 1e-3


def test_goal_matrix_sits_on_the_root_to_goal_ray():
    root, goal, soft_ik = _rig(soft=1.0, stretch=0.0)
    goal.translate = (0, 20, 0)
    driven = tm.Transform.create(name="soft_probe")
    tm.MatrixConstraint.create(soft_ik.goal_matrix, driven, maintain_offset=False)
    position = driven.world_translation
    assert abs(position.x) < 1e-3 and abs(position.z) < 1e-3
    assert abs(position.y - soft_ik.soft_distance.value) < 1e-3


def test_stretch_one_puts_the_goal_on_the_control():
    root, goal, soft_ik = _rig(soft=1.0, stretch=1.0)
    goal.translate = (20, 0, 0)
    driven = tm.Transform.create(name="soft_probe_stretch")
    tm.MatrixConstraint.create(soft_ik.goal_matrix, driven, maintain_offset=False)
    assert abs(driven.world_translation.x - 20.0) < 1e-3
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_soft_ik.py -v`
Expected: FAIL — `AttributeError: module 'tik.maya' has no attribute 'SoftIk'`

- [ ] **Step 3: Write the construct**

Create `src/python/tik/maya/constructs/soft_ik.py`:

```python
"""Soft IK: an exponential approach curve for an IK goal.

With ``L`` the total rest length, ``ds = softIk + 0.001`` and ``da = L - ds``::

    f(d) = d                          if d <= da
         = L - ds * e^(-(d-da)/ds)    if d >  da

The curve is C0 at the seam (``f(da) = L - ds = da``) and C1 there
(``f'(da) = 1``, matching the identity branch), and asymptotic to ``L`` so the
chain never fully straightens. Those three properties are what make the solve
soft rather than merely curved.

A branchless form does not work: ``min(d, L - ds*e^...)`` picks the wrong
branch below ``da`` and ``max`` picks the wrong branch above, so one
``condition`` node stays.
"""

from __future__ import annotations

import math
from typing import Optional

from maya import cmds

from ..core import attribute
from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import resolve
from ..core.scene import create_node
from ..types.transform import Transform
from .measure import Measure


def _node(item):
    return resolve(item) if isinstance(item, str) else item


class SoftIk:
    """Softened goal position for an IK handle."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.group: Optional[Transform] = None
        self.root = None
        self.goal = None
        self.measure: Optional[Measure] = None
        self._nodes: list = []
        self._distance: Optional[Plug] = None
        self._soft_distance: Optional[Plug] = None
        self._gap: Optional[Plug] = None
        self._goal_matrix: Optional[Plug] = None

    @classmethod
    @undo
    def create(
        cls,
        root,
        goal,
        chain_length: Plug,
        *,
        name: Optional[str] = None,
        parent=None,
        scale_plug: Optional[Plug] = None,
    ) -> "SoftIk":
        """Build the soft-IK network between ``root`` and ``goal``.

        Args:
            root: Transform at the chain root. MUST be upstream of the IK
                solve — an ``ikRPsolver`` rotates the chain's root joint, so
                passing that joint creates a cycle.
            goal: Transform the chain reaches for (the IK control).
            chain_length: Plug carrying the total rest length, normally
                ``ChainLengths.total_length``.
            name: Prefix for created nodes.
            parent: Optional parent for the construct's group.
            scale_plug: Optional global scale the raw distance is divided by.
        """
        soft = cls(name or "softIk")
        soft.root = _node(root)
        soft.goal = _node(goal)

        soft.group = Transform.create(name=f"{soft.name}_softIk_grp")
        if parent is not None:
            soft.group.parent = _node(parent)
        attribute.add_float(soft.group, "softIk", default=0.0, min=0.0)
        attribute.add_float(soft.group, "stretch", default=0.0, min=0.0, max=1.0)
        attribute.lock_and_hide(soft.group, attribute.TRANSFORM_ATTRS)

        soft.measure = Measure.create(
            soft.root["worldMatrix[0]"],
            soft.goal["worldMatrix[0]"],
            name=f"{soft.name}_softIk",
        )
        distance = soft.measure.distance
        if scale_plug is not None:
            distance = distance / scale_plug
        soft._distance = distance

        soft._build_curve(chain_length)
        soft._build_goal()
        return soft

    # ----------------------------------------------------------- internals
    def _build_curve(self, chain_length: Plug) -> None:
        """Wire ``f(d)`` and the stretch gap."""
        distance = self._distance
        ds = self.soft_plug + 0.001  # guards the divide below
        da = chain_length - ds

        # L - ds * e^(-(d-da)/ds)
        exponent = (distance - da) / ds * -1.0
        curve = chain_length - (exponent ** math.e if False else self._exp(exponent)) * ds

        # One condition: identity below the seam, the curve above it.
        self._soft_distance = distance.gt(da, curve, distance)
        self._gap = (distance - self._soft_distance) * self.stretch_plug

    @staticmethod
    def _exp(exponent: Plug) -> Plug:
        """Return ``e ** exponent`` as a plug."""
        base = create_node("floatConstant", name="softIk_e")
        base["inFloat"].value = math.e
        return base["outFloat"] ** exponent

    def _build_goal(self) -> None:
        """Place the goal along the root-to-goal ray at the blended distance."""
        aim = create_node("aimMatrix", name=f"{self.name}_softIk_aimMatrix")
        aim["primaryMode"].value = 1  # Aim
        aim["secondaryMode"].value = 0  # None
        aim["primaryInputAxisX"].value = 1.0
        aim["primaryInputAxisY"].value = 0.0
        aim["primaryInputAxisZ"].value = 0.0
        for axis in "XYZ":
            aim[f"primaryTargetVector{axis}"].value = 0.0
        self.root["worldMatrix[0]"] >> aim["inputMatrix"]
        self.goal["worldMatrix[0]"] >> aim["primaryTargetMatrix"]

        offset = create_node("composeMatrix", name=f"{self.name}_softIk_offset")
        blended = self._soft_distance.lerp(self._distance, self.stretch_plug)
        blended >> offset["inputTranslateX"]

        mult = create_node("multMatrix", name=f"{self.name}_softIk_goalMultMatrix")
        offset["outputMatrix"] >> mult["matrixIn[0]"]
        aim["outputMatrix"] >> mult["matrixIn[1]"]

        self._nodes.extend([aim, offset, mult])
        self._goal_matrix = mult["matrixSum"]

    # ----------------------------------------------------------- accessors
    @property
    def soft_plug(self) -> Plug:
        """Softness distance in scene units; ``0`` disables softening."""
        return self.group["softIk"]

    @property
    def stretch_plug(self) -> Plug:
        """0 = goal is the soft point, 1 = goal is the control."""
        return self.group["stretch"]

    @property
    def distance_plug(self) -> Plug:
        """Raw (scaled) root-to-goal distance."""
        return self._distance

    @property
    def soft_distance(self) -> Plug:
        """``f(d)`` — the softened distance."""
        return self._soft_distance

    @property
    def gap_plug(self) -> Plug:
        """``stretch * (d - f(d))`` — the shortfall a stretch network consumes."""
        return self._gap

    @property
    def goal_matrix(self) -> Plug:
        """World matrix for the ikHandle."""
        return self._goal_matrix

    @undo
    def delete(self) -> None:
        """Delete the network."""
        if self.measure is not None:
            self.measure.delete()
        names = [node.long_name for node in self._nodes if node.exists()]
        if self.group is not None and self.group.exists():
            names.append(self.group.long_name)
        if names:
            cmds.delete(names)
```

- [ ] **Step 4: Simplify the leftover expression in `_build_curve`**

The line

```python
        curve = chain_length - (exponent ** math.e if False else self._exp(exponent)) * ds
```

contains a dead conditional. Replace it with:

```python
        curve = chain_length - self._exp(exponent) * ds
```

- [ ] **Step 5: Export it**

Add `from .soft_ik import SoftIk` to `src/python/tik/maya/constructs/__init__.py` with `"SoftIk"` in `__all__`, and add `SoftIk` to `src/python/tik/maya/__init__.py`'s import block and `__all__`.

- [ ] **Step 6: Run the test to verify it passes**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_soft_ik.py -v`
Expected: PASS, 10 tests.

If `floatConstant` is unavailable, replace `_exp` with a `floatMath`-free alternative: create a `multiplyDivide` with `operation=3`, set `input1X` to `math.e`, connect `exponent` to `input2X`, and return `outputX`. Verify the tests still pass.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/maya/constructs/soft_ik.py src/python/tik/maya/constructs/__init__.py src/python/tik/maya/__init__.py tests/unit/test_soft_ik.py
git commit -m "feat(tik.maya): SoftIk construct with C1-continuous approach curve"
```

---

### Task 8: `AimFrame` construct

**Files:**
- Create: `src/python/tik/maya/constructs/aim_frame.py`
- Modify: `src/python/tik/maya/constructs/__init__.py`, `src/python/tik/maya/__init__.py`
- Test: `tests/unit/test_aim_frame.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `AimFrame.create(base, aim_target, up_target=None, *, twist_axis="Y", parent=None, name=None, create_transform=True) -> AimFrame`
  - `.matrix` → world-matrix `Plug` (`aimMatrix.outputMatrix`)
  - `.transform` → `Transform` carrying the frame in `offsetParentMatrix`, local TRS free — or `None` when `create_transform=False`
  - `.node` → the `aimMatrix`
  - `.delete()`

**Background:** the frame sits at `base`'s position with `+X` aimed at `aim_target`'s position and `+Y` aligned to an axis of `up_target`. Because `secondaryMode` is *Align* (2), rolling `up_target` about its twist axis rolls the frame — that twist-awareness is the whole point, and a rest-captured static offset cannot reproduce it.

`offsetParentMatrix` is correct here: this is a rig helper that is never exported, and parking the frame there leaves local TRS free to express an offset along the frame (a plain `ty`). The live-TRS rule binds bind joints only.

The twist-axis map picks a target vector perpendicular to the twist axis:
`X -> (0,1,0)`, `Y -> (1,0,0)`, `Z -> (1,0,0)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_aim_frame.py`:

```python
"""Tests for the AimFrame construct."""

from maya import cmds

import tik.maya as tm


def _setup():
    base = tm.Transform.create(name="af_base")
    target = tm.Transform.create(name="af_target")
    target.translate = (10, 0, 0)
    up = tm.Transform.create(name="af_up")
    up.translate = (10, 0, 0)
    return base, target, up


def test_transform_sits_at_the_base():
    base, target, up = _setup()
    base.translate = (0, 3, 0)
    frame = tm.AimFrame.create(base, target, up, name="af")
    assert (frame.transform.world_translation - base.world_translation).length() < 1e-4


def test_x_axis_aims_at_the_target():
    base, target, up = _setup()
    target.translate = (0, 0, 12)
    frame = tm.AimFrame.create(base, target, up, name="af_aim")
    axis = frame.transform.world_matrix_axis_x()
    assert abs(axis.z - 1.0) < 1e-3


def test_local_translate_offsets_along_the_frame():
    base, target, up = _setup()
    frame = tm.AimFrame.create(base, target, up, name="af_offset")
    frame.transform.translate = (0, 5, 0)
    assert abs(frame.transform.world_translation.y - 5.0) < 1e-3


def test_rolling_the_up_target_rolls_the_frame():
    """The twist-awareness that a static captured offset cannot reproduce."""
    base, target, up = _setup()
    frame = tm.AimFrame.create(base, target, up, twist_axis="X", name="af_twist")
    frame.transform.translate = (0, 5, 0)
    before = frame.transform.world_translation
    up.rotate = (90, 0, 0)
    after = frame.transform.world_translation
    assert (after - before).length() > 1.0


def test_parented_frame_keeps_its_world_position():
    base, target, up = _setup()
    base.translate = (0, 4, 0)
    holder = tm.Transform.create(name="af_holder")
    holder.translate = (0, 0, 20)
    frame = tm.AimFrame.create(base, target, up, parent=holder, name="af_parent")
    assert (frame.transform.world_translation - base.world_translation).length() < 1e-3


def test_matrix_only_mode_creates_no_transform():
    base, target, up = _setup()
    frame = tm.AimFrame.create(
        base, target, up, name="af_plug", create_transform=False
    )
    assert frame.transform is None
    assert frame.matrix.node.type == "aimMatrix"


def test_delete_removes_the_nodes():
    base, target, up = _setup()
    frame = tm.AimFrame.create(base, target, up, name="af_delete")
    node_name = frame.node.long_name
    frame.delete()
    assert not cmds.objExists(node_name)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_aim_frame.py -v`
Expected: FAIL — `AttributeError: module 'tik.maya' has no attribute 'AimFrame'`

- [ ] **Step 3: Write the construct**

Create `src/python/tik/maya/constructs/aim_frame.py`:

```python
"""A frame that aims at one target and takes its up direction from another.

The frame sits at ``base``'s position with ``aim_axis`` pointed at
``aim_target``'s position and ``up_axis`` aligned to an axis of ``up_target``.

Because the secondary mode is *Align* rather than *Aim*, rolling ``up_target``
about its twist axis rolls the frame. That twist-awareness is the point: a
rest-captured static offset cannot reproduce it.

``offsetParentMatrix`` is used deliberately. This is a rig helper that is never
exported, and parking the frame there leaves local TRS free to express an
offset along the frame. The live-TRS rule binds bind joints only.
"""

from __future__ import annotations

from typing import Optional, Sequence

from maya import cmds

from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import resolve
from ..core.scene import create_node
from ..types.transform import Transform

# A target vector perpendicular to the twist axis.
TWIST_TARGETS = {
    "X": (0.0, 1.0, 0.0),
    "Y": (1.0, 0.0, 0.0),
    "Z": (1.0, 0.0, 0.0),
}


def _node(item):
    return resolve(item) if isinstance(item, str) else item


class AimFrame:
    """Wrapper for an ``aimMatrix`` frame and its optional transform."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.node = None
        self.transform: Optional[Transform] = None
        self._nodes: list = []

    @classmethod
    @undo
    def create(
        cls,
        base,
        aim_target,
        up_target=None,
        *,
        aim_axis: Sequence[float] = (1.0, 0.0, 0.0),
        up_axis: Sequence[float] = (0.0, 1.0, 0.0),
        twist_axis: str = "Y",
        parent=None,
        name: Optional[str] = None,
        create_transform: bool = True,
    ) -> "AimFrame":
        """Build the frame.

        Args:
            base: Transform supplying the frame's position.
            aim_target: Transform the primary axis points at.
            up_target: Transform supplying the up direction; defaults to
                ``aim_target``.
            aim_axis: Primary input axis.
            up_axis: Secondary input axis.
            twist_axis: Which axis of ``up_target`` the frame tracks around;
                one of ``"X"``, ``"Y"``, ``"Z"``.
            parent: Optional parent for the created transform.
            name: Prefix for created nodes.
            create_transform: Create a transform carrying the frame. When
                False only ``.matrix`` is produced.
        """
        base = _node(base)
        aim_target = _node(aim_target)
        up_target = _node(up_target) if up_target is not None else aim_target
        twist = twist_axis.upper()
        if twist not in TWIST_TARGETS:
            raise ValueError(f"twist_axis must be X, Y or Z, got {twist_axis!r}.")

        frame = cls(name or "aimFrame")
        node = create_node("aimMatrix", name=f"{frame.name}_aimMatrix")
        node["primaryMode"].value = 1  # Aim
        node["secondaryMode"].value = 2  # Align

        secondary_target = TWIST_TARGETS[twist]
        for index, axis in enumerate("XYZ"):
            node[f"primaryInputAxis{axis}"].value = aim_axis[index]
            node[f"primaryTargetVector{axis}"].value = 0.0  # aim at the position
            node[f"secondaryInputAxis{axis}"].value = up_axis[index]
            node[f"secondaryTargetVector{axis}"].value = secondary_target[index]

        base["worldMatrix[0]"] >> node["inputMatrix"]
        aim_target["worldMatrix[0]"] >> node["primaryTargetMatrix"]
        up_target["worldMatrix[0]"] >> node["secondaryTargetMatrix"]
        frame.node = node

        if create_transform:
            frame._build_transform(parent)
        return frame

    def _build_transform(self, parent) -> None:
        """Create the transform carrying the frame in ``offsetParentMatrix``."""
        transform = Transform.create(name=f"{self.name}_frame")
        if parent is not None:
            parent = _node(parent)
            transform.parent = parent
            mult = create_node("multMatrix", name=f"{self.name}_frameMultMatrix")
            self.node["outputMatrix"] >> mult["matrixIn[0]"]
            parent["worldInverseMatrix[0]"] >> mult["matrixIn[1]"]
            mult["matrixSum"] >> transform["offsetParentMatrix"]
            self._nodes.append(mult)
        else:
            self.node["outputMatrix"] >> transform["offsetParentMatrix"]
        self.transform = transform

    @property
    def matrix(self) -> Plug:
        """The output frame as a world-matrix plug."""
        return self.node["outputMatrix"]

    @undo
    def delete(self) -> None:
        """Delete the frame network and its transform."""
        names = [node.long_name for node in [self.node, *self._nodes] if node.exists()]
        if self.transform is not None and self.transform.exists():
            names.append(self.transform.long_name)
        if names:
            cmds.delete(names)
```

- [ ] **Step 4: Export it**

Add `from .aim_frame import AimFrame` to `src/python/tik/maya/constructs/__init__.py` with `"AimFrame"` in `__all__`, and add `AimFrame` to `src/python/tik/maya/__init__.py`'s import block and `__all__`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_aim_frame.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/maya/constructs/aim_frame.py src/python/tik/maya/constructs/__init__.py src/python/tik/maya/__init__.py tests/unit/test_aim_frame.py
git commit -m "feat(tik.maya): AimFrame construct with twist-aware up direction"
```

---

### Task 9: Retire `IkFkChain`

**Files:**
- Delete: `src/python/tik/maya/constructs/ikfk_chain.py`, `tests/unit/test_ikfk_chain.py`
- Modify: `src/python/tik/maya/constructs/__init__.py:3,13`, `src/python/tik/maya/__init__.py:16,61`

**Interfaces:**
- Consumes: `MatrixBlend` (Task 5) and `Joint.duplicate_chain` (Task 2), which together replace everything `IkFkChain` did.
- Produces: nothing. `tm.IkFkChain` stops existing.

**Background:** the construct produced three chains where two suffice, its useful API was its own internals, and `_copy_chain` dropped `preferredAngle`. Its only consumers are the arm module (rewritten in Task 15) and its own test file. The arm is left temporarily broken by this task and is fixed in Task 15; that is expected and is why the integration suite is not run here.

- [ ] **Step 1: Delete the files**

```bash
git rm src/python/tik/maya/constructs/ikfk_chain.py tests/unit/test_ikfk_chain.py
```

- [ ] **Step 2: Remove the exports**

In `src/python/tik/maya/constructs/__init__.py`, delete the line `from .ikfk_chain import IkFkChain` and the `"IkFkChain",` entry in `__all__`.

In `src/python/tik/maya/__init__.py`, delete `IkFkChain` from the constructs import block and the `"IkFkChain",` entry in `__all__`.

- [ ] **Step 3: Verify nothing else imports it**

Run: `git grep -n "IkFkChain\|ikfk_chain" -- src tests`
Expected: only `src/python/tik/trigger/modules/arm/arm.py` (its docstring at line 3 and the call at line 90), which Task 15 rewrites.

- [ ] **Step 4: Verify tik.maya still imports**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -c "import tik.maya as tm; print(tm.MatrixBlend, tm.ChainLengths, tm.SoftIk, tm.AimFrame)"`
Expected: prints the four classes, no ImportError.

- [ ] **Step 5: Run the full tik.maya unit suite**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit -q --ignore=tests/unit/test_maya_backend_trigger.py`
Expected: PASS. (Trigger backend tests are reworked in Phase B.)

- [ ] **Step 6: Commit**

```bash
git add -A src/python/tik/maya
git commit -m "refactor(tik.maya): retire IkFkChain in favour of MatrixBlend + duplicate_chain"
```

---

## Phase B — Trigger Ground Rules

### Task 10: Four-group taxonomy

**Files:**
- Modify: `src/python/tik/trigger/core/context.py:13-22` (`RigGroups`)
- Modify: `src/python/tik/trigger/backends/maya/context.py:92-117` (`_create_groups`)
- Modify: `tests/helpers/trigger_fakes.py:31`
- Test: `tests/unit/test_maya_backend_trigger.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `RigGroups(limb, socket, control, rig, bind)` — five fields, four of them children of `limb`. The old `scale`, `nonscale`, `controllers` and `joints` fields are gone.

Group names: `<side>_<name>_socket_grp`, `..._control_grp`, `..._rig_grp`, `..._bind_grp`.
Visibility bools on `limb`: `controlVisibility` (default True) → control, `rigVisibility` (default False) → rig, `bindVisibility` (default True) → bind.

**Background:** `scale_grp`, `nonScale_grp` and `scaleHook_grp` are dropped. Nothing depends on them: `MatrixSpline` sets its own `inheritsTransform = False` (`matrix_spline.py:105-106`) and `Ribbon` parents its group wherever asked (`ribbon.py:111-115`).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_maya_backend_trigger.py`:

```python
def test_module_has_exactly_four_groups():
    from maya import cmds

    ctx = _build_context_for("base")  # existing helper in this file
    children = {
        name.split("|")[-1] for name in cmds.listRelatives(
            ctx.groups.limb.long_name, children=True, fullPath=True
        ) or []
    }
    assert len(children) == 4
    assert ctx.groups.socket.name in children
    assert ctx.groups.control.name in children
    assert ctx.groups.rig.name in children
    assert ctx.groups.bind.name in children


def test_group_names_follow_the_convention():
    ctx = _build_context_for("base")
    assert ctx.groups.socket.name.endswith("_socket_grp")
    assert ctx.groups.control.name.endswith("_control_grp")
    assert ctx.groups.rig.name.endswith("_rig_grp")
    assert ctx.groups.bind.name.endswith("_bind_grp")


def test_old_scale_groups_are_gone():
    ctx = _build_context_for("base")
    assert not hasattr(ctx.groups, "scale")
    assert not hasattr(ctx.groups, "nonscale")
    assert not hasattr(ctx.groups, "joints")
    assert not hasattr(ctx.groups, "controllers")


def test_visibility_attributes_drive_the_groups():
    ctx = _build_context_for("base")
    limb = ctx.groups.limb
    limb["rigVisibility"].value = True
    assert ctx.groups.rig["visibility"].value is True
    limb["controlVisibility"].value = False
    assert ctx.groups.control["visibility"].value is False
```

If `_build_context_for` does not already exist in that file, add it near the top:

```python
def _build_context_for(module_type: str):
    """Build a context for a freshly drawn single instance of ``module_type``."""
    from tik.trigger.backends.maya.backend import MayaBackend
    from tik.trigger.core import registry

    backend = MayaBackend()
    module_cls = registry.get_module(module_type)
    instance = backend.draw_guides(module_cls, name=module_type)
    rig_root = backend.ensure_rig_root("test")
    module = module_cls.from_instance(instance)
    return backend.build_context(module, instance, rig_root)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_maya_backend_trigger.py -k group -v`
Expected: FAIL — `AttributeError: 'RigGroups' object has no attribute 'socket'`

- [ ] **Step 3: Rewrite `RigGroups`**

Replace the dataclass in `src/python/tik/trigger/core/context.py:13-22` with:

```python
@dataclass
class RigGroups:
    """The four groups created for every module instance, under ``limb``.

    ``socket`` holds input attach transforms driven by parent module outputs.
    ``control`` holds controllers and their offset/space groups, nothing else.
    ``rig`` holds the puppet: IK/FK chains, handles, math, helpers.
    ``bind`` holds deform/export joints only, and is empty when the module is
    connected to a parent (its joints are created in the parent's hierarchy).
    """

    limb: Any = None  # top group of the module
    socket: Any = None
    control: Any = None
    rig: Any = None
    bind: Any = None
```

- [ ] **Step 4: Rewrite `_create_groups`**

Replace `_create_groups` in `src/python/tik/trigger/backends/maya/context.py:92-117` with:

```python
    def _create_groups(self) -> RigGroups:
        limb = tm.Transform.create(name=self.name(suffix="grp"), parent=self.rig_root.long_name)
        socket = tm.Transform.create(name=self.name("socket", suffix="grp"), parent=limb.long_name)
        control = tm.Transform.create(name=self.name("control", suffix="grp"), parent=limb.long_name)
        rig = tm.Transform.create(name=self.name("rig", suffix="grp"), parent=limb.long_name)
        bind = tm.Transform.create(name=self.name("bind", suffix="grp"), parent=limb.long_name)

        attribute.add_separator(limb, "visibility_")
        attribute.add_bool(limb, "controlVisibility", default=True) >> control["visibility"]
        attribute.add_bool(limb, "rigVisibility", default=False) >> rig["visibility"]
        attribute.add_bool(limb, "bindVisibility", default=True) >> bind["visibility"]
        for group in (limb, socket, control, rig, bind):
            attribute.lock_and_hide(group, attribute.TRANSFORM_ATTRS)
        tags.tag(
            limb,
            **{
                tags.KIND: tags.RIG,
                tags.MODULE: self.module.module_type,
                tags.INSTANCE: self.instance.instance_id,
                tags.NAME: self.instance.name,
                tags.SIDE: self.side.value,
            },
        )
        return RigGroups(limb=limb, socket=socket, control=control, rig=rig, bind=bind)
```

- [ ] **Step 5: Point `ctx.controller` at the new group**

In the same file, in `controller()`, change the default parent line from
`parent = parent if parent is not None else self.groups.controllers`
to:

```python
        parent = parent if parent is not None else self.groups.control
```

- [ ] **Step 6: Update the fake context**

In `tests/helpers/trigger_fakes.py:31`, replace

```python
        self.groups = RigGroups(limb=f"{module.name}_grp")
```

with:

```python
        self.groups = RigGroups(
            limb=f"{module.name}_grp",
            socket=f"{module.name}_socket_grp",
            control=f"{module.name}_control_grp",
            rig=f"{module.name}_rig_grp",
            bind=f"{module.name}_bind_grp",
        )
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_maya_backend_trigger.py -v`
Expected: the four new tests PASS. Other tests in the file may still fail if they reference old group names — fix those references to the new names as part of this step.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/core/context.py src/python/tik/trigger/backends/maya/context.py tests/helpers/trigger_fakes.py tests/unit/test_maya_backend_trigger.py
git commit -m "refactor(tik.trigger): four-group module taxonomy (socket/control/rig/bind)"
```

---

### Task 11: `ctx.bind_joint`, `ctx.bind_parent`, and mirror tags

**Files:**
- Modify: `src/python/tik/trigger/backends/maya/tags.py`
- Modify: `src/python/tik/trigger/core/context.py` (the `BuildContext` protocol)
- Modify: `src/python/tik/trigger/backends/maya/context.py`
- Modify: `tests/helpers/trigger_fakes.py`
- Test: `tests/unit/test_maya_backend_trigger.py` (append)

**Interfaces:**
- Consumes: `RigGroups.bind` (Task 10).
- Produces:
  - `ctx.bind_parent` — attribute. The node new bind joints should hang from: the connected input's bind joint, or `ctx.groups.bind` when unconnected. Set by the backend before `build()` runs.
  - `ctx.bind_joint(name, *, parent=None, match=None, radius=1.0) -> tm.Joint` — creates a joint named `ctx.name(name, suffix="jnt")` under `parent or ctx.bind_parent`, tags it `trg_kind=deform`, appends to `ctx.deform_joints`, aligns to `match` when given, and returns it.
  - `ctx.controller(..., mirror="world")` — new keyword, `"behaviour"` or `"world"`, written to the `trg_mirror` tag.
  - New tag constants: `tags.MIRROR = "trg_mirror"`, `tags.BEHAVIOUR = "behaviour"`, `tags.WORLD = "world"`.

`ctx.deform_joint(node)` stays for nodes created some other way.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_maya_backend_trigger.py`:

```python
def test_bind_parent_defaults_to_the_bind_group():
    ctx = _build_context_for("base")
    assert ctx.bind_parent.name == ctx.groups.bind.name


def test_bind_joint_lands_under_bind_parent():
    ctx = _build_context_for("base")
    joint = ctx.bind_joint("probe")
    assert joint.parent.name == ctx.groups.bind.name
    assert joint.name.endswith("_probe_jnt")
    assert joint in ctx.deform_joints


def test_bind_joint_is_tagged_as_deform():
    from tik.trigger.backends.maya import tags

    ctx = _build_context_for("base")
    joint = ctx.bind_joint("tagged")
    assert joint.meta[tags.KIND] == tags.DEFORM


def test_bind_joint_honours_an_explicit_parent():
    ctx = _build_context_for("base")
    first = ctx.bind_joint("first")
    second = ctx.bind_joint("second", parent=first)
    assert second.parent.name == first.name


def test_bind_joint_matches_a_node():
    import tik.maya as tm

    ctx = _build_context_for("base")
    target = tm.Transform.create(name="bind_match_target")
    target.translate = (2, 5, 0)
    joint = ctx.bind_joint("matched", match=target)
    assert (joint.world_translation - target.world_translation).length() < 1e-4


def test_controller_records_its_mirror_rule():
    from tik.trigger.backends.maya import tags

    ctx = _build_context_for("base")
    fk = ctx.controller("fk_probe", mirror="behaviour")
    ik = ctx.controller("ik_probe", mirror="world")
    assert fk.transform.meta[tags.MIRROR] == tags.BEHAVIOUR
    assert ik.transform.meta[tags.MIRROR] == tags.WORLD


def test_controller_mirror_defaults_to_world():
    from tik.trigger.backends.maya import tags

    ctx = _build_context_for("base")
    controller = ctx.controller("default_probe")
    assert controller.transform.meta[tags.MIRROR] == tags.WORLD
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_maya_backend_trigger.py -k "bind_ or mirror" -v`
Expected: FAIL — `AttributeError: 'MayaBuildContext' object has no attribute 'bind_parent'`

- [ ] **Step 3: Add the tag constants**

In `src/python/tik/trigger/backends/maya/tags.py`, add after the `DESIGNER` line:

```python
MIRROR = "trg_mirror"  # "behaviour" | "world" — how a pose-mirror tool treats it
```

and after the `SOCKET = INPUT` line:

```python
BEHAVIOUR = "behaviour"  # FK-like: follows its joint, equal values mirror
WORLD = "world"  # IK/world: world-aligned, mirroring is tool logic
```

- [ ] **Step 4: Extend the `BuildContext` protocol**

In `src/python/tik/trigger/core/context.py`, add `bind_parent: Any` to the `BuildContext` attribute list, and add these method stubs:

```python
    def bind_joint(
        self,
        name: str,
        *,
        parent: Any = None,
        match: Any = None,
        radius: float = 1.0,
    ) -> Any:
        """Create a tagged bind joint under ``parent`` or ``bind_parent``."""
```

Change the `controller` stub's signature to include `mirror: str = "world"`.

- [ ] **Step 5: Implement in the Maya context**

In `src/python/tik/trigger/backends/maya/context.py`, change `__init__` to accept and store a bind parent:

```python
    def __init__(
        self, module, instance: ModuleInstance, rig_root, guide_nodes: dict, bind_parent=None
    ) -> None:
```

and after `self.groups = self._create_groups()` add:

```python
        self.bind_parent = bind_parent if bind_parent is not None else self.groups.bind
```

Add the `bind_joint` method next to `deform_joint`:

```python
    def bind_joint(
        self,
        name: str,
        *,
        parent: Any = None,
        match: Any = None,
        radius: float = 1.0,
    ) -> tm.Joint:
        """Create a bind/deform joint in the single rig-wide hierarchy.

        Defaults to ``bind_parent``, which the builder resolves to the
        connected input's bind joint before ``build()`` runs. Bind joints are
        created in their final position and never reparented: ``MatrixConstraint``
        wires a live connection to the driven's parent inverse at build time.
        """
        parent = parent if parent is not None else self.bind_parent
        joint = tm.Joint.create(
            name=self.name(name, suffix="jnt"),
            parent=parent.long_name if hasattr(parent, "long_name") else parent,
            radius=radius,
        )
        if match is not None:
            joint.align_to(match)
        return self.deform_joint(joint)
```

Add `mirror: str = "world"` to the `controller` signature (after `match`), and include it in the tag block:

```python
                tags.MIRROR: mirror,
```

- [ ] **Step 6: Update the fake context**

In `tests/helpers/trigger_fakes.py`, add to `FakeBuildContext.__init__` after the groups assignment:

```python
        self.bind_parent = self.groups.bind
```

and add the method:

```python
    def bind_joint(self, name, *, parent=None, match=None, radius=1.0):
        node = f"{self.module.name}_{name}_jnt"
        self.deform_joints.append(node)
        return node
```

Change `controller` to absorb the new keyword (it already takes `**kwargs`, so no change is needed if so — verify).

- [ ] **Step 7: Thread `bind_parent` through the backend**

In `src/python/tik/trigger/backends/maya/backend.py`, change `build_context`:

```python
    def build_context(
        self, module, instance: ModuleInstance, rig_root, bind_parent=None
    ) -> MayaBuildContext:
        guide_nodes = self.guide_nodes(instance.instance_id)
        return MayaBuildContext(module, instance, rig_root, guide_nodes, bind_parent)
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_maya_backend_trigger.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/python/tik/trigger tests/helpers/trigger_fakes.py tests/unit/test_maya_backend_trigger.py
git commit -m "feat(tik.trigger): ctx.bind_joint, ctx.bind_parent and trg_mirror tags"
```

---

### Task 12: Topological build-and-connect

**Files:**
- Modify: `src/python/tik/trigger/core/schemas.py` (add `order_by_connections`)
- Modify: `src/python/tik/trigger/core/builder.py:67-177`
- Test: `tests/unit/test_core_trigger.py` (append)

**Interfaces:**
- Consumes: `ctx.bind_parent` (Task 11).
- Produces:
  - `order_by_connections(instances, inputs_for) -> list[ModuleInstance]` in `schemas.py`. `inputs_for(instance)` returns `{input_name: source}`. Orders producers before consumers; raises `ValueError` naming the instance on a cycle. Falls back to input order for unconnected instances.
  - `Builder.build()` now builds and connects each instance in that order, resolving `bind_parent` from the primary input's already-built producer before calling `module.build(ctx)`.
  - `Builder._bind_parent_for(instance, module_cls, inputs, by_key, report)` → node or `None`.

**Background:** `order_instances` (`schemas.py:145-167`) orders by *guide parent*, not by input connections. Bind joints must be created in final position, so the producer's outputs must exist before the consumer builds.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_core_trigger.py`:

```python
def test_order_by_connections_puts_producers_first():
    from tik.trigger.core.schemas import order_by_connections

    a = _instance("a")  # existing helper in this file
    b = _instance("b")
    c = _instance("c")
    inputs = {"b": {"root": "a.root"}, "c": {"root": "b.root"}, "a": {}}
    ordered = order_by_connections([c, b, a], lambda item: inputs[item.name])
    assert [item.name for item in ordered] == ["a", "b", "c"]


def test_order_by_connections_detects_a_cycle():
    import pytest

    from tik.trigger.core.schemas import order_by_connections

    a = _instance("a")
    b = _instance("b")
    inputs = {"a": {"root": "b.root"}, "b": {"root": "a.root"}}
    with pytest.raises(ValueError, match="Cyclic"):
        order_by_connections([a, b], lambda item: inputs[item.name])


def test_order_by_connections_keeps_unconnected_order():
    from tik.trigger.core.schemas import order_by_connections

    a = _instance("a")
    b = _instance("b")
    ordered = order_by_connections([b, a], lambda item: {})
    assert [item.name for item in ordered] == ["b", "a"]


def test_builder_passes_bind_parent_from_the_producer(fake_backend):
    """A connected module receives the producer's output as bind_parent."""
    report = _build_two_connected_modules(fake_backend)
    consumer_ctx = report.contexts[fake_backend.instances[1].instance_id]
    producer_ctx = report.contexts[fake_backend.instances[0].instance_id]
    assert consumer_ctx.bind_parent == producer_ctx.outputs["root"]
```

Add the helper `_build_two_connected_modules` near the other helpers in that file:

```python
def _build_two_connected_modules(backend):
    """Build a base and a fkchain whose root input is the base's root output."""
    from tik.trigger.core import Builder

    parent = backend.add_instance("base", name="body")
    child = backend.add_instance("fkchain", name="tail")
    child.inputs = {"root": f"{parent.key}.root"}
    return Builder(backend).build()
```

If `backend.add_instance` does not exist under that name in `trigger_fakes.py`, use whatever the file's existing instance-creation helper is and adjust.

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_core_trigger.py -k "order_by_connections or bind_parent" -v`
Expected: FAIL — `ImportError: cannot import name 'order_by_connections'`

- [ ] **Step 3: Add `order_by_connections`**

Add to `src/python/tik/trigger/core/schemas.py`, after `order_instances`:

```python
def order_by_connections(instances: list[ModuleInstance], inputs_for) -> list[ModuleInstance]:
    """Return instances with producers before consumers.

    Bind joints must be created in their final hierarchy position, so a
    module's producer has to be built before the module itself.

    Args:
        instances: The instances to order.
        inputs_for: Callable returning ``{input_name: source}`` for an
            instance. A source is ``"<module key>.<output>"`` or a bare scene
            node name.

    Returns:
        The instances, producers first, input order preserved otherwise.

    Raises:
        ValueError: On a cyclic connection, naming the instance.
    """
    by_key = {instance.key: instance for instance in instances}
    ordered: list[ModuleInstance] = []
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(instance: ModuleInstance) -> None:
        if instance.instance_id in done:
            return
        if instance.instance_id in visiting:
            raise ValueError(f"Cyclic module connection at '{instance.name}'.")
        visiting.add(instance.instance_id)
        for source in (inputs_for(instance) or {}).values():
            if not source or "." not in source:
                continue
            key, _dot, _output = source.rpartition(".")
            producer = by_key.get(key)
            if producer is not None and producer is not instance:
                visit(producer)
        visiting.discard(instance.instance_id)
        done.add(instance.instance_id)
        ordered.append(instance)

    for instance in instances:
        visit(instance)
    return ordered
```

Add `"order_by_connections"` to that module's `__all__`.

- [ ] **Step 4: Rework `Builder.build`**

In `src/python/tik/trigger/core/builder.py`, replace the body of the `with self.backend.undo_chunk(...)` block in `build()` with:

```python
            report.rig_root = self.backend.ensure_rig_root(rig_name)
            by_id = {instance.instance_id: instance for instance in instances}
            by_key: dict = {}
            instances = order_by_connections(
                instances, lambda item: derive_inputs(item, by_id)
            )
            total = len(instances)
            for number, instance in enumerate(instances, start=1):
                self.events.progress(number, total, f"Building {instance.name}")
                module_cls = registry.get_module(instance.module_type)
                inputs = derive_inputs(instance, by_id)
                bind_parent = self._bind_parent_for(
                    instance, module_cls, inputs, by_key, report
                )
                ctx = self._build_one(instance, report.rig_root, bind_parent)
                report.contexts[instance.instance_id] = ctx
                report.built.append(instance.instance_id)
                by_key[instance.key] = instance
                self._connect_one(instance, module_cls, inputs, by_key, report, known_keys)
            self.backend.afterlife(instances, afterlife)
```

Add the import at the top of the file:

```python
from .schemas import ModuleInstance, order_by_connections, order_instances
```

(and drop the now-unused `order_instances` import only if `Builder.order` no longer uses it — it does, so keep both).

- [ ] **Step 5: Add `_bind_parent_for` and `_connect_one`**

Add to `Builder`, replacing `_connect_all`:

```python
    def _bind_parent_for(self, instance, module_cls, inputs, by_key, report):
        """Resolve the bind joint new bind joints should hang from.

        Returns the primary input's producer output, or ``None`` when the
        module is unconnected (the context then falls back to its own
        ``bind_grp``).
        """
        primary = module_cls.primary_input()
        if primary is None:
            return None
        source = inputs.get(primary.name)
        if not source:
            return None
        key, output = split_source(source)
        if key is None or key not in by_key:
            return None
        producer_ctx = report.contexts.get(by_key[key].instance_id)
        if producer_ctx is None:
            return None
        return producer_ctx.outputs.get(output)

    def _connect_one(self, instance, module_cls, inputs, by_key, report, known_keys) -> None:
        """Attach every declared input of one already-built instance."""
        ctx = report.contexts[instance.instance_id]
        for declared in module_cls.inputs:
            source = inputs.get(declared.name)
            if not source:
                if declared.optional:
                    continue
                raise AttachError(
                    f"{instance.key}.{declared.name}: required input has no source.",
                    instance_id=instance.instance_id, module_type=instance.module_type,
                )
            key, _output = split_source(source)
            if key is not None and key in known_keys and key not in by_key:
                self.events.log(
                    f"{instance.key}.{declared.name}: source '{source}' is outside the "
                    f"build scope; left unattached.",
                    level="warning",
                )
                continue
            node = self._resolve_source(instance, declared.name, source, by_key, report)
            target = ctx.attachments.get(declared.name)
            if target is None:
                raise AttachError(
                    f"{instance.key}.{declared.name}: module did not call ctx.attach() "
                    f"for this input.",
                    instance_id=instance.instance_id, module_type=instance.module_type,
                )
            self.backend.connect(ctx, declared.name, node)
            report.connections.append((f"{instance.key}.{declared.name}", source))
```

- [ ] **Step 6: Thread `bind_parent` into `_build_one`**

Change the signature and the `build_context` call:

```python
    def _build_one(self, instance: ModuleInstance, rig_root, bind_parent=None):
```

```python
            ctx = self.backend.build_context(module, instance, rig_root, bind_parent)
```

- [ ] **Step 7: Update the fake backend**

In `tests/helpers/trigger_fakes.py`, change `FakeBackend.build_context` to accept the extra argument and pass it on:

```python
    def build_context(self, module, instance, rig_root, bind_parent=None):
        ctx = FakeBuildContext(module, instance, rig_root)
        if bind_parent is not None:
            ctx.bind_parent = bind_parent
        return ctx
```

- [ ] **Step 8: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_core_trigger.py tests/unit/test_runner_trigger.py tests/unit/test_handler_trigger.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/python/tik/trigger/core tests/helpers/trigger_fakes.py tests/unit/test_core_trigger.py
git commit -m "feat(tik.trigger): topological build-and-connect with resolved bind_parent"
```

---

### Task 13: Update `base` and `fkchain` modules

**Files:**
- Modify: `src/python/tik/trigger/modules/base/base.py`
- Modify: `src/python/tik/trigger/modules/fkchain/fkchain.py`
- Test: `tests/unit/test_maya_backend_trigger.py` (append)

**Interfaces:**
- Consumes: `ctx.bind_joint`, `ctx.bind_parent`, `ctx.groups.socket`, `ctx.groups.control` (Tasks 10-11).
- Produces: both modules build under the new taxonomy. Outputs unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_maya_backend_trigger.py`:

```python
def test_base_puts_its_joint_in_the_bind_group():
    ctx = _build_context_for("base")
    from tik.trigger.core import registry

    registry.get_module("base").from_instance(ctx.instance).build(ctx)
    joint = ctx.outputs["root"]
    assert joint.parent.name == ctx.groups.bind.name
    assert joint in ctx.deform_joints


def test_fkchain_socket_lives_in_the_socket_group():
    ctx = _build_context_for("fkchain")
    from tik.trigger.core import registry

    registry.get_module("fkchain").from_instance(ctx.instance).build(ctx)
    socket = ctx.attachments["root"]
    assert socket.parent.name == ctx.groups.socket.name


def test_fkchain_joints_chain_under_the_bind_parent():
    ctx = _build_context_for("fkchain")
    from tik.trigger.core import registry

    registry.get_module("fkchain").from_instance(ctx.instance).build(ctx)
    root = ctx.outputs["root"]
    assert root.parent.name == ctx.groups.bind.name
    assert ctx.outputs["segment1"].parent.name == root.name
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_maya_backend_trigger.py -k "base_puts or fkchain_" -v`
Expected: FAIL — `AttributeError: 'RigGroups' object has no attribute 'joints'`

- [ ] **Step 3: Update `base`**

Replace the `build` method in `src/python/tik/trigger/modules/base/base.py` with:

```python
    def build(self, ctx) -> None:
        root_guide = ctx.guide("root")
        controller = ctx.controller(
            "root",
            shape="Circle",
            size=self.controller_size,
            match=root_guide,
            mirror="world",
        )
        joint = ctx.bind_joint("root", match=root_guide)
        tm.MatrixConstraint.create(controller.transform, joint, maintain_offset=True)
        ctx.output("root", joint)
```

- [ ] **Step 4: Update `fkchain`**

Replace the `build` method in `src/python/tik/trigger/modules/fkchain/fkchain.py` with:

```python
    def build(self, ctx) -> None:
        guide_nodes = [ctx.guide("root"), *ctx.guides("segment")]

        socket = tm.Transform.create(
            name=ctx.name("root", suffix="socket"), parent=ctx.groups.socket.long_name
        )
        socket.align_to(guide_nodes[0])
        ctx.attach("root", socket)

        joints = []
        parent_joint = None
        for index, guide_node in enumerate(guide_nodes):
            joint = ctx.bind_joint(str(index), parent=parent_joint, match=guide_node)
            joints.append(joint)
            parent_joint = joint

        parent = socket
        for index, joint in enumerate(joints[:-1]):
            controller = ctx.controller(
                f"fk{index}",
                size=self.controller_size,
                parent=parent,
                match=joint,
                mirror="behaviour",
            )
            controller.transform.create_offset_group(name=ctx.name(f"fk{index}", suffix="offset"))
            tm.MatrixConstraint.create(controller.transform, joint, maintain_offset=True)
            parent = controller.transform

        ctx.output("root", joints[0])
        for index, joint in enumerate(joints[1:]):
            ctx.output(f"segment{index + 1}", joint)
        ctx.output("end", joints[-1])
```

Note: `ctx.bind_joint(str(index), parent=None, ...)` for the root falls back to `ctx.bind_parent`, so a connected fkchain builds its root inside the parent module's hierarchy. Joint orientation is no longer done by `Joint.chain`; each joint is created at its guide's position and inherits the default orientation, which is correct for the bind skeleton's engine-neutral convention.

- [ ] **Step 5: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_maya_backend_trigger.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/modules/base src/python/tik/trigger/modules/fkchain tests/unit/test_maya_backend_trigger.py
git commit -m "refactor(tik.trigger): base and fkchain on the new group taxonomy"
```

---

## Phase C — Systems and the Arm

### Task 14: `tik/trigger/systems/limb.py`

**Files:**
- Create: `src/python/tik/trigger/systems/__init__.py`
- Create: `src/python/tik/trigger/systems/limb.py`
- Test: `tests/integration/trigger/test_limb_system.py` (create)

**Interfaces:**
- Consumes: `tm.MatrixBlend`, `tm.ChainLengths`, `tm.SoftIk`, `tm.AimFrame`, `tm.Joint.duplicate_chain`, `tm.MatrixConstraint(cutoff=)`, `ctx.controller(mirror=)`.
- Produces:

```python
@dataclass
class LimbResult:
    ik_joints: list          # puppet IK chain
    fk_joints: list          # puppet FK chain
    ik_handle: object
    ik_lengths: object       # tm.ChainLengths on the IK chain
    fk_lengths: object       # tm.ChainLengths on the FK chain (shared rest plugs)
    soft_ik: object | None
    pole_base: object        # tm.Transform, upstream of the solve
    fk_controls: list        # tm.Controller, root first
    ik_control: object       # tm.Controller
    pole_control: object     # tm.Controller
    switch_control: object   # tm.Controller
    switch_plug: object      # the ikFk Plug


def build_ikfk_limb(
    ctx,
    guides,                  # list of guide nodes, root first (>= 3)
    *,
    name="limb",
    parent=None,             # socket/transform the limb hangs from
    bind_joints=None,        # list of bind joints to drive, one per guide
    controller_size=3.0,
    soft_ik=True,
    stretch=True,
    squash=True,
    stretch_limit_default=50.0,
    pole_pin=False,
    labels=None,             # FK controller labels; defaults to indices
) -> LimbResult
```

**Background — this is the policy layer.** It creates controllers, names animator-facing attributes, and applies `ctx.side_mult`. The stretch limit is not a flag: when `stretch` is on the clamp is always built, and `stretch_limit_default` seeds the attribute's default percentage.

The factor formulation, from the spec:

```
gap            = soft_ik.gap_plug              # = stretch * (d - f(d))
stretch_factor = min(1 + gap/L,  1 + limitPct/100)      >= 1, extending only
squash_factor  = lerp(1.0, min(d/L, 1.0), squashAmount) <= 1, compressing only
tx_i = side_sign * rest_i * stretch_factor * squash_factor
```

An unbuilt factor is `1.0`, so the flags never interact.

**`pole_base` cycle safety is load-bearing.** `ikRPsolver` rotates the chain's root joint, so `AimFrame`'s base and `SoftIk`'s root must be a transform *upstream* of the solve. `pole_base` is created under `rig_grp` and matrix-constrained to the limb's `parent`, offset to the root guide's position.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/trigger/test_limb_system.py`:

```python
"""Integration tests for the IK/FK limb system."""

from maya import cmds

import tik.maya as tm
from tik.trigger.systems.limb import build_ikfk_limb

from tests.helpers.trigger_fakes import *  # noqa: F401,F403 - shared fixtures


def _guides():
    """Shoulder, elbow, hand — a bent chain so the RP solver has a plane."""
    return tm.Joint.chain(
        [(0, 0, 0), (4, 0, -1), (8, 0, 0)], name_pattern="limb_guide_{index}"
    )


def _limb(ctx, **kwargs):
    guides = _guides()
    binds = [
        ctx.bind_joint(f"bind{index}", match=guide)
        for index, guide in enumerate(guides)
    ]
    return build_ikfk_limb(ctx, guides, bind_joints=binds, name="limb", **kwargs), binds


def test_builds_exactly_two_puppet_chains(maya_build_context):
    result, _binds = _limb(maya_build_context)
    assert len(result.ik_joints) == 3
    assert len(result.fk_joints) == 3
    assert len(cmds.ls(type="ikHandle")) == 1


def test_switch_zero_follows_fk(maya_build_context):
    result, binds = _limb(maya_build_context)
    result.switch_plug.value = 0.0
    result.fk_controls[0].transform.rotate = (0, 0, 30)
    assert (
        binds[1].world_translation - result.fk_joints[1].world_translation
    ).length() < 1e-3


def test_switch_one_follows_ik(maya_build_context):
    result, binds = _limb(maya_build_context)
    result.switch_plug.value = 1.0
    assert (
        binds[2].world_translation - result.ik_joints[2].world_translation
    ).length() < 1e-3


def test_no_stretch_leaves_segment_lengths_at_rest(maya_build_context):
    result, _binds = _limb(maya_build_context, stretch=False, squash=False)
    rest = result.ik_lengths.rest_plugs[0].value
    result.ik_control.transform.translate = (40, 0, 0)
    assert abs(abs(result.ik_joints[1].translate.x) - rest) < 1e-3


def test_stretch_extends_beyond_reach(maya_build_context):
    result, _binds = _limb(maya_build_context, stretch=True)
    result.ik_control.transform["stretch"].value = 1.0
    rest = result.ik_lengths.rest_plugs[0].value
    result.ik_control.transform.translate = (40, 0, 0)
    assert abs(result.ik_joints[1].translate.x) > rest


def test_stretch_limit_caps_the_extension(maya_build_context):
    result, _binds = _limb(maya_build_context, stretch=True)
    control = result.ik_control.transform
    control["stretch"].value = 1.0
    control["stretchLimit"].value = 10.0  # percent
    rest = result.ik_lengths.rest_plugs[0].value
    control.translate = (200, 0, 0)
    assert abs(result.ik_joints[1].translate.x) <= rest * 1.1 + 1e-3


def test_squash_only_compresses(maya_build_context):
    result, _binds = _limb(maya_build_context, squash=True)
    control = result.ik_control.transform
    control["squash"].value = 1.0
    rest = result.ik_lengths.rest_plugs[0].value
    control.translate = (2, 0, 0)
    assert abs(result.ik_joints[1].translate.x) < rest


def test_segment_scale_works_without_stretch(maya_build_context):
    """rest_i is a live plug, so per-segment scale needs no stretch network."""
    result, _binds = _limb(maya_build_context, stretch=False, squash=False)
    rest = result.ik_lengths.rest_plugs[0].value
    result.ik_control.transform["sUpper"].value = 2.0
    assert abs(abs(result.ik_joints[1].translate.x) - rest * 2.0) < 1e-3


def test_segment_scale_also_drives_the_fk_chain(maya_build_context):
    """Both ChainLengths share rest plugs — the legacy was IK-only."""
    result, _binds = _limb(maya_build_context, stretch=False)
    rest = result.fk_lengths.rest_plugs[0].value
    result.ik_control.transform["sUpper"].value = 2.0
    assert abs(abs(result.fk_joints[1].translate.x) - rest * 2.0) < 1e-3


def test_pole_base_does_not_cycle(maya_build_context):
    """The one failure a unit test would happily pass through."""
    _result, _binds = _limb(maya_build_context)
    cmds.dgdirty(allPlugs=True)
    cycles = cmds.cycleCheck(all=True) or []
    assert not cycles


def test_pole_follow_rolls_with_the_wrist(maya_build_context):
    result, _binds = _limb(maya_build_context)
    control = result.ik_control.transform
    control["poleFollow"].value = 1.0
    before = result.pole_control.transform.world_translation
    control.rotate = (90, 0, 0)
    after = result.pole_control.transform.world_translation
    assert (after - before).length() > 0.5


def test_controls_carry_mirror_tags(maya_build_context):
    from tik.trigger.backends.maya import tags

    result, _binds = _limb(maya_build_context)
    assert result.fk_controls[0].transform.meta[tags.MIRROR] == tags.BEHAVIOUR
    assert result.ik_control.transform.meta[tags.MIRROR] == tags.WORLD
    assert result.pole_control.transform.meta[tags.MIRROR] == tags.WORLD
```

Add a `maya_build_context` fixture to `tests/integration/trigger/conftest.py` (create the file if absent):

```python
import pytest

from tik.trigger.backends.maya.backend import MayaBackend
from tik.trigger.core import registry


@pytest.fixture
def maya_build_context():
    """A real MayaBuildContext for the 'base' module, for system-level tests."""
    from maya import cmds

    cmds.file(new=True, force=True)
    backend = MayaBackend()
    module_cls = registry.get_module("base")
    instance = backend.draw_guides(module_cls, name="probe")
    rig_root = backend.ensure_rig_root("test")
    module = module_cls.from_instance(instance)
    return backend.build_context(module, instance, rig_root)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_limb_system.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.systems'`

- [ ] **Step 3: Create the package**

Create `src/python/tik/trigger/systems/__init__.py`:

```python
"""Policy-bearing rig sub-assemblies.

A *system* composes ``tik.maya`` constructs **and** creates controllers,
naming the animator-facing attributes. Mechanism belongs one layer down in
``tik.maya``; a construct there never creates a controller, names a
user-facing attribute, or encodes a side convention.

Layer escalation::

    nodes -> types -> roles -> constructs -> systems -> modules
"""
```

- [ ] **Step 4: Write the limb system**

Create `src/python/tik/trigger/systems/limb.py`:

```python
"""IK/FK limb: the shared recipe behind the arm, the leg and the fkik module.

Chain count is three sets, not four::

    ik_*   joints  (rig_grp)   ONE ikRPsolver handle. No second IK chain.
    fk_*   joints  (rig_grp)   driven by FK controls
    bind   joints  (bind_grp)  <- MatrixBlend(fk[i], ik[i], weight = ikFk)

The bind joints *are* the blend result, so no redundant blend chain exists.

Stretch and squash are factors on opposite sides of 1.0 that never overlap::

    gap            = soft_ik.gap_plug                        # stretch * (d - f(d))
    stretch_factor = min(1 + gap/L, 1 + limitPct/100)         >= 1
    squash_factor  = lerp(1.0, min(d/L, 1.0), squashAmount)   <= 1
    tx_i           = side_sign * rest_i * stretch_factor * squash_factor

An unbuilt factor is 1.0, so the flags never interact and ``stretch=False``
really does produce a smaller graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import tik.maya as tm
from tik.maya import attribute


@dataclass
class LimbResult:
    """Everything a module needs after the limb is built."""

    ik_joints: list = field(default_factory=list)
    fk_joints: list = field(default_factory=list)
    ik_handle: object = None
    ik_lengths: object = None
    fk_lengths: object = None
    soft_ik: object = None
    pole_base: object = None
    fk_controls: list = field(default_factory=list)
    ik_control: object = None
    pole_control: object = None
    switch_control: object = None
    switch_plug: object = None


def build_ikfk_limb(
    ctx,
    guides: Sequence,
    *,
    name: str = "limb",
    parent=None,
    bind_joints: Optional[Sequence] = None,
    controller_size: float = 3.0,
    soft_ik: bool = True,
    stretch: bool = True,
    squash: bool = True,
    stretch_limit_default: float = 50.0,
    pole_pin: bool = False,
    labels: Optional[Sequence[str]] = None,
) -> LimbResult:
    """Build an IK/FK limb driving ``bind_joints``.

    Args:
        ctx: The module build context.
        guides: Guide nodes, root first. At least three.
        name: Token used in every created name.
        parent: Transform the limb hangs from; defaults to ``ctx.groups.socket``.
        bind_joints: Bind joints to drive, one per guide. When omitted the
            puppet is built but nothing is blended onto a deform skeleton.
        controller_size: Base controller size.
        soft_ik: Build the soft-IK network. Always True for an arm.
        stretch: Build the extend-side factor (and its limit clamp).
        squash: Build the compress-side factor.
        stretch_limit_default: Default percentage for the ``stretchLimit`` attr.
        pole_pin: Build the elbow pin override.
        labels: FK controller labels; defaults to indices.

    Returns:
        A :class:`LimbResult`.
    """
    guides = list(guides)
    if len(guides) < 3:
        raise ValueError("build_ikfk_limb needs at least three guides.")
    labels = list(labels) if labels else [str(index) for index in range(len(guides))]
    parent = parent if parent is not None else ctx.groups.socket
    result = LimbResult()
    side_sign = ctx.side_mult

    # ---------------------------------------------------------- puppet chains
    source = tm.Joint.chain(
        [tuple(guide.world_position) for guide in guides],
        name_pattern=ctx.name(name, "src{index}", suffix="jnt"),
        parent=ctx.groups.rig,
    )
    result.ik_joints = tm.Joint.duplicate_chain(
        source, prefix=ctx.name(name, "ik"), parent=ctx.groups.rig
    )
    result.fk_joints = tm.Joint.duplicate_chain(
        source, prefix=ctx.name(name, "fk"), parent=ctx.groups.rig
    )
    tm.delete(source[0].long_name)

    for chain in (result.ik_joints, result.fk_joints):
        tm.MatrixConstraint.create(parent, chain[0], maintain_offset=True)

    # ------------------------------------------------------ pole base (no cycle)
    # ikRPsolver rotates the chain's root joint, so anything feeding the solve
    # must be upstream of it. This transform is that upstream anchor.
    result.pole_base = tm.Transform.create(
        name=ctx.name(name, "poleBase"), parent=ctx.groups.rig.long_name
    )
    result.pole_base.align_to(result.ik_joints[0])
    tm.MatrixConstraint.create(parent, result.pole_base, maintain_offset=True)

    # ------------------------------------------------------------- controllers
    result.ik_control = ctx.controller(
        f"{name}_ik",
        shape="Cube",
        size=controller_size,
        parent=ctx.groups.control,
        match=result.ik_joints[-1],
        mirror="world",
    )
    result.ik_control.transform.create_offset_group(
        name=ctx.name(name, "ik", suffix="offset")
    )
    result.switch_control = ctx.controller(
        f"{name}_switch",
        shape="Cube",
        size=controller_size * 0.4,
        parent=ctx.groups.control,
        match=result.ik_joints[-1],
        mirror="world",
    )
    switch_offset = result.switch_control.transform.create_offset_group(
        name=ctx.name(name, "switch", suffix="offset")
    )
    switch_offset.translate = tuple(
        value + shift
        for value, shift in zip(switch_offset.translate, (0, controller_size * 1.5, 0))
    )
    attribute.lock_and_hide(result.switch_control.transform)
    result.switch_plug = attribute.add_float(
        result.switch_control.transform, "ikFk", default=1.0, min=0.0, max=1.0
    )

    control = result.ik_control.transform
    attribute.add_separator(control, "limb_")
    segment_scales = [
        attribute.add_float(control, f"s{label.capitalize()}", default=1.0, min=0.001)
        for label in labels[:-1]
    ]

    fk_parent = parent
    for index, (label, joint) in enumerate(zip(labels, result.fk_joints)):
        fk_control = ctx.controller(
            f"{name}_fk_{label}",
            shape="Circle",
            size=controller_size,
            parent=fk_parent,
            match=joint,
            mirror="behaviour",
        )
        fk_control.transform.create_offset_group(
            name=ctx.name(name, "fk", label, suffix="offset")
        )
        attribute.lock_and_hide(fk_control.transform, ("sx", "sy", "sz", "v"))
        tm.MatrixConstraint.create(
            fk_control.transform, joint, maintain_offset=True, skip_scale="xyz"
        )
        result.fk_controls.append(fk_control)
        fk_parent = fk_control.transform

    # ------------------------------------------------------------ IK and solve
    result.ik_handle = tm.IkHandle.create(
        result.ik_joints[0],
        result.ik_joints[-1],
        solver="ikRPsolver",
        name=ctx.name(name, suffix="ikHandle"),
    )
    result.ik_handle.parent = ctx.groups.rig
    tm.MatrixConstraint.create(
        result.ik_control.transform,
        result.ik_joints[-1],
        maintain_offset=True,
        skip_translate="xyz",
        skip_scale="xyz",
    )

    # --------------------------------------------------------- segment lengths
    result.ik_lengths = tm.ChainLengths.create(
        result.ik_joints, side_sign=side_sign, name=ctx.name(name, "ik")
    )
    result.fk_lengths = tm.ChainLengths.create(
        result.fk_joints, side_sign=side_sign, name=ctx.name(name, "fk")
    )
    # Share the rest plugs so per-segment scale works in FK too — the legacy
    # kept initialDistance on the IK chains and was therefore IK-only.
    for index, scale in enumerate(segment_scales):
        initial = result.ik_lengths.rest_plugs[index].value
        scaled = scale * initial
        scaled >> result.ik_lengths.rest_plugs[index]
        scaled >> result.fk_lengths.rest_plugs[index]

    # ------------------------------------------------------------- soft and IK
    if soft_ik:
        result.soft_ik = tm.SoftIk.create(
            result.pole_base,
            result.ik_control.transform,
            result.ik_lengths.total_length,
            name=ctx.name(name),
            parent=ctx.groups.rig,
        )
        attribute.add_proxy(control, result.soft_ik.soft_plug, name="softIk")
        tm.MatrixConstraint.create(
            result.soft_ik.goal_matrix,
            result.ik_handle,
            maintain_offset=False,
            skip_rotate="xyz",
            skip_scale="xyz",
        )
        goal_transform = result.soft_ik.goal_matrix
    else:
        tm.MatrixConstraint.create(
            result.ik_control.transform,
            result.ik_handle,
            maintain_offset=True,
            skip_rotate="xyz",
            skip_scale="xyz",
        )
        goal_transform = result.ik_control.transform["worldMatrix[0]"]

    total = result.ik_lengths.total_length
    if stretch:
        stretch_plug = attribute.add_float(
            control, "stretch", default=0.0, min=0.0, max=1.0
        )
        limit_plug = attribute.add_float(
            control, "stretchLimit", default=stretch_limit_default, min=0.0
        )
        if result.soft_ik is not None:
            stretch_plug >> result.soft_ik.stretch_plug
            gap = result.soft_ik.gap_plug
        else:
            measure = tm.Measure.create(
                result.pole_base["worldMatrix[0]"],
                result.ik_control.transform["worldMatrix[0]"],
                name=ctx.name(name, "stretch"),
            )
            gap = (measure.distance - total).maximum(0.0) * stretch_plug
        ceiling = limit_plug / 100.0 + 1.0
        result.ik_lengths.add_factor((gap / total + 1.0).minimum(ceiling))

    if squash:
        squash_plug = attribute.add_float(
            control, "squash", default=0.0, min=0.0, max=1.0
        )
        measure = tm.Measure.create(
            result.pole_base["worldMatrix[0]"],
            result.ik_control.transform["worldMatrix[0]"],
            name=ctx.name(name, "squash"),
        )
        compress = (measure.distance / total).minimum(1.0)
        one = attribute.add_float(control, "squashUnit", default=1.0)
        attribute.lock_and_hide(control, ("squashUnit",))
        result.ik_lengths.add_factor(one.lerp(compress, squash_plug))

    # ------------------------------------------------------------------- pole
    pole_follow = attribute.add_float(
        control, "poleFollow", default=1.0, min=0.0, max=1.0
    )
    frame = tm.AimFrame.create(
        result.pole_base,
        result.ik_control.transform,
        result.ik_control.transform,
        parent=ctx.groups.rig,
        name=ctx.name(name, "pole"),
    )
    rest = tm.Transform.create(
        name=ctx.name(name, "poleRest"), parent=ctx.groups.rig.long_name
    )
    rest.snap_to(frame.transform)
    pole_space = tm.MatrixBlend.create(
        rest, [frame.transform], [pole_follow], name=ctx.name(name, "poleSpace")
    )
    result.pole_control = ctx.controller(
        f"{name}_pole",
        shape="Diamond",
        size=controller_size * 0.5,
        parent=ctx.groups.control,
        mirror="world",
    )
    pole_offset = result.pole_control.transform.create_offset_group(
        name=ctx.name(name, "pole", suffix="offset")
    )
    tm.MatrixConstraint.create(pole_space.output, pole_offset, maintain_offset=False)
    result.pole_control.transform.translate = (
        0,
        _pole_distance(result.ik_joints),
        0,
    )
    attribute.lock_and_hide(
        result.pole_control.transform, ("rx", "ry", "rz", "sx", "sy", "sz", "v")
    )
    result.ik_handle.pole_vector(result.pole_control.transform)

    if pole_pin:
        pin_plug = attribute.add_float(control, "polePin", default=0.0, min=0.0, max=1.0)
        upper = tm.Measure.create(
            result.pole_base["worldMatrix[0]"],
            result.pole_control.transform["worldMatrix[0]"],
            name=ctx.name(name, "pinUpper"),
        )
        lower = tm.Measure.create(
            result.pole_control.transform["worldMatrix[0]"],
            goal_transform,
            name=ctx.name(name, "pinLower"),
        )
        result.ik_lengths.add_override([upper.distance, lower.distance], pin_plug)

    # ------------------------------------------------------------ visibility
    result.switch_plug >> result.ik_control.transform.parent["visibility"]
    reverse = tm.create_node("reverse", name=ctx.name(name, "ikFkReverse"))
    result.switch_plug >> reverse["inputX"]
    reverse["outputX"] >> result.fk_controls[0].transform.parent["visibility"]

    # --------------------------------------------------------- blend to bind
    if bind_joints:
        for index, bind_joint in enumerate(bind_joints):
            blend = tm.MatrixBlend.create(
                result.fk_joints[index],
                [result.ik_joints[index]],
                [result.switch_plug],
                name=ctx.name(name, f"blend{index}"),
            )
            tm.MatrixConstraint.create(
                blend.output, bind_joint, maintain_offset=True
            )
    return result


def _pole_distance(joints: Sequence) -> float:
    """A pole offset proportional to the chain's rest length."""
    total = 0.0
    for first, second in zip(joints, joints[1:]):
        total += first.distance_to(second)
    return total * 0.25
```

- [ ] **Step 5: Run the test**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_limb_system.py -v`
Expected: PASS, 12 tests.

Debug notes if a test fails:
- `test_pole_base_does_not_cycle` failing means something downstream of the solve reached `pole_base`, `AimFrame`, or `SoftIk`. Check that no IK joint feeds any of them.
- If `attribute.add_proxy` has a different signature than assumed, replace the proxy with a plain `add_float` on `control` connected into `soft_ik.soft_plug`.
- If `tm.delete` is not exposed, use `cmds.delete` via `tm.cmds` or restructure to build the IK/FK chains directly from guide positions with two `tm.Joint.chain` calls followed by `orient_chain`.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/systems tests/integration/trigger/test_limb_system.py tests/integration/trigger/conftest.py
git commit -m "feat(tik.trigger): systems/limb.py — the IK/FK limb recipe"
```

---

### Task 15: Rewrite the arm module

**Files:**
- Rewrite: `src/python/tik/trigger/modules/arm/arm.py`
- Test: `tests/integration/trigger/test_arm_trigger.py` (rewrite)

**Interfaces:**
- Consumes: `build_ikfk_limb` (Task 14), `ctx.bind_joint` (Task 11).
- Produces: the `arm` module with guides `collar`/`shoulder`/`elbow`/`hand`, outputs `collar`/`upperarm`/`lowerarm`/`hand`, input `root`, and five fields.

- [ ] **Step 1: Write the failing test**

Replace `tests/integration/trigger/test_arm_trigger.py` with:

```python
"""Integration tests for the rebuilt arm module."""

from maya import cmds

from tik.trigger.core import registry


def _built_arm(maya_build_context_for):
    ctx = maya_build_context_for("arm")
    registry.get_module("arm").from_instance(ctx.instance).build(ctx)
    return ctx


def test_declares_four_outputs():
    module_cls = registry.get_module("arm")
    assert module_cls.output_names({}) == (
        "collar",
        "upperarm",
        "lowerarm",
        "hand",
    )


def test_has_no_ik_solver_or_ribbon_fields():
    """The SC solver has nothing left to do once the pole has an auto space."""
    module_cls = registry.get_module("arm")
    names = {field.name for field in module_cls.field_definitions()}
    assert "ik_solver" not in names
    assert "ribbon_joints" not in names
    assert "soft_ik" not in names


def test_bind_skeleton_is_a_single_chain(maya_build_context_for):
    ctx = _built_arm(maya_build_context_for)
    collar = ctx.outputs["collar"]
    upper = ctx.outputs["upperarm"]
    lower = ctx.outputs["lowerarm"]
    hand = ctx.outputs["hand"]
    assert upper.parent.name == collar.name
    assert lower.parent.name == upper.name
    assert hand.parent.name == lower.name


def test_unconnected_arm_roots_in_its_bind_group(maya_build_context_for):
    ctx = _built_arm(maya_build_context_for)
    assert ctx.outputs["collar"].parent.name == ctx.groups.bind.name


def test_builds_exactly_one_ik_handle(maya_build_context_for):
    """The whole point: one IK chain, no SC chain to blend against."""
    _ctx = _built_arm(maya_build_context_for)
    assert len(cmds.ls(type="ikHandle")) == 1


def test_every_controller_lives_in_the_control_group(maya_build_context_for):
    ctx = _built_arm(maya_build_context_for)
    control_group = ctx.groups.control.long_name
    for controller in ctx.controllers:
        assert control_group in controller.transform.long_name


def test_stretch_off_builds_no_stretch_attributes(maya_build_context_for):
    ctx = maya_build_context_for("arm", settings={"stretch": False, "squash": False})
    registry.get_module("arm").from_instance(ctx.instance).build(ctx)
    ik_control = next(
        item for item in ctx.controllers if item.transform.name.endswith("_arm_ik_ctrl")
    )
    assert not ik_control.transform.has_attr("stretch")
    assert not ik_control.transform.has_attr("squash")
    assert ik_control.transform.has_attr("sUpper")  # per-segment scale is always on


def test_stretch_on_builds_the_limit_with_it(maya_build_context_for):
    ctx = _built_arm(maya_build_context_for)
    ik_control = next(
        item for item in ctx.controllers if item.transform.name.endswith("_arm_ik_ctrl")
    )
    assert ik_control.transform.has_attr("stretch")
    assert ik_control.transform.has_attr("stretchLimit")
```

Add to `tests/integration/trigger/conftest.py`:

```python
@pytest.fixture
def maya_build_context_for():
    """Build a context for any module type, optionally overriding settings."""
    from maya import cmds

    def _make(module_type: str, settings: dict | None = None):
        cmds.file(new=True, force=True)
        backend = MayaBackend()
        module_cls = registry.get_module(module_type)
        instance = backend.draw_guides(module_cls, name=module_type)
        if settings:
            instance.settings.update(settings)
        rig_root = backend.ensure_rig_root("test")
        module = module_cls.from_instance(instance)
        return backend.build_context(module, instance, rig_root)

    return _make
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_arm_trigger.py -v`
Expected: FAIL — the module still imports `IkFkChain`, which Task 9 deleted.

- [ ] **Step 3: Rewrite the module**

Replace `src/python/tik/trigger/modules/arm/arm.py` entirely with:

```python
"""Arm module: collar plus a single-IK-chain IK/FK arm.

Three joint sets, not four. The bind joints *are* the IK/FK blend result, so
no redundant blend chain exists, and there is no second IK chain for the pole
— the pole gets a twist-aware auto space instead.

Ribbons and twist live in their own modules. A twist module attached to the
``upperarm`` output creates its joints as siblings of ``lowerarm_jnt``, which
is exactly how engine twist bones are structured, so nothing here needs to
anticipate them.
"""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import (
    BoolField,
    FloatField,
    Guides,
    Input,
    Module,
    register_module,
)
from tik.trigger.systems.limb import build_ikfk_limb


@register_module("arm")
class Arm(Module):
    """Biped arm: collar, shoulder, elbow, hand."""

    label = "Arm"
    guides = Guides("collar", "shoulder", "elbow", "hand")
    inputs = (Input("root", primary=True, help="Where the collar hangs (chest/body)"),)
    outputs = ("collar", "upperarm", "lowerarm", "hand")

    stretch = BoolField(True, help="Build the stretch network")
    squash = BoolField(True, help="Build the compress-side network")
    stretch_limit = FloatField(
        50.0, min=0.0, max=500.0, label="Stretch Limit %",
        help="Default cap on how far a segment may stretch, as a percentage",
    )
    pole_pin = BoolField(False, help="Lock the elbow to the pole control")
    controller_size = FloatField(3.0, min=0.01, label="Controller Size")

    # --------------------------------------------------------------- guides
    def draw_guides(self, ctx) -> None:
        mult = ctx.side_mult
        collar = ctx.joint("collar", (2 * mult, 0, 0), radius=1.5)
        shoulder = ctx.joint("shoulder", (5 * mult, 0, 0), parent=collar)
        elbow = ctx.joint("elbow", (9 * mult, 0, -1), parent=shoulder)
        ctx.joint("hand", (14 * mult, 0, 0), parent=elbow)

    # ---------------------------------------------------------------- build
    def build(self, ctx) -> None:
        size = self.controller_size
        collar_guide = ctx.guide("collar")
        limb_guides = [ctx.guide("shoulder"), ctx.guide("elbow"), ctx.guide("hand")]

        # socket -----------------------------------------------------------
        socket = tm.Transform.create(
            name=ctx.name("root", suffix="socket"), parent=ctx.groups.socket.long_name
        )
        socket.align_to(collar_guide)
        ctx.attach("root", socket)

        # deform skeleton — created in final position, never reparented -----
        collar_jnt = ctx.bind_joint("collar", match=collar_guide)
        bind_joints = []
        parent_joint = collar_jnt
        for label, guide_node in zip(("upperarm", "lowerarm", "hand"), limb_guides):
            joint = ctx.bind_joint(label, parent=parent_joint, match=guide_node)
            bind_joints.append(joint)
            parent_joint = joint

        # collar -----------------------------------------------------------
        collar_ctrl = ctx.controller(
            "collar",
            shape="CurvedCircle",
            size=size,
            parent=socket,
            match=collar_jnt,
            mirror="behaviour",
        )
        collar_ctrl.transform.create_offset_group(name=ctx.name("collar", suffix="offset"))
        tm.MatrixConstraint.create(collar_ctrl.transform, collar_jnt, maintain_offset=True)

        # the limb ----------------------------------------------------------
        build_ikfk_limb(
            ctx,
            limb_guides,
            name="arm",
            parent=collar_ctrl.transform,
            bind_joints=bind_joints,
            controller_size=size,
            soft_ik=True,  # never optional for an IK solution
            stretch=self.stretch,
            squash=self.squash,
            stretch_limit_default=self.stretch_limit,
            pole_pin=self.pole_pin,
            labels=("upper", "lower", "hand"),
        )

        ctx.output("collar", collar_jnt)
        ctx.output("upperarm", bind_joints[0])
        ctx.output("lowerarm", bind_joints[1])
        ctx.output("hand", bind_joints[2])
```

- [ ] **Step 4: Run the test**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_arm_trigger.py -v`
Expected: PASS, 8 tests.

If `field_definitions()` or `has_attr` do not exist with those names, adjust the tests to the real API — check `src/python/tik/trigger/core/module.py` and `src/python/tik/maya/core/node.py` respectively. Do not change the assertions' meaning.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/modules/arm tests/integration/trigger/test_arm_trigger.py tests/integration/trigger/conftest.py
git commit -m "feat(tik.trigger): rewrite the arm module on the limb system"
```

---

### Task 16: Ground-rule tests

**Files:**
- Create: `tests/integration/trigger/test_module_ground_rules.py`

**Interfaces:**
- Consumes: everything above.
- Produces: three tests that bind every future module, not only the arm.

**Background:** these encode §1.3 and §1.5 of the spec. A new module that violates them fails here rather than in a rig review.

- [ ] **Step 1: Write the tests**

Create `tests/integration/trigger/test_module_ground_rules.py`:

```python
"""Ground rules that bind every trigger module, not just the arm.

Spec: docs/superpowers/specs/2026-08-30-arm-module-and-module-ground-rules-design.md
"""

import pytest
from maya import cmds

from tik.trigger.backends.maya import tags
from tik.trigger.backends.maya.backend import MayaBackend
from tik.trigger.core import Builder, registry

MODULE_TYPES = ("base", "fkchain", "arm")


@pytest.fixture
def connected_rig():
    """A base with an arm attached to it — one hierarchy across two modules."""
    cmds.file(new=True, force=True)
    backend = MayaBackend()
    body = backend.draw_guides(registry.get_module("base"), name="body")
    arm = backend.draw_guides(registry.get_module("arm"), name="arm")
    arm.inputs = {"root": f"{body.key}.root"}
    report = Builder(backend).build(rig_name="rules")
    return backend, report


def test_exactly_one_bind_hierarchy_root(connected_rig):
    _backend, report = connected_rig
    deform = [
        node
        for node in cmds.ls(type="joint", long=True)
        if cmds.objExists(f"{node}.{tags.KIND}")
        and cmds.getAttr(f"{node}.{tags.KIND}") == tags.DEFORM
    ]
    assert deform
    roots = [
        node
        for node in deform
        if (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
        not in deform
    ]
    assert len(roots) == 1, f"expected one bind root, got {roots}"


def test_connected_module_leaves_its_bind_group_empty(connected_rig):
    _backend, report = connected_rig
    arm_ctx = next(
        ctx
        for ctx in report.contexts.values()
        if ctx.instance.module_type == "arm"
    )
    children = cmds.listRelatives(arm_ctx.groups.bind.long_name, children=True) or []
    assert children == [], f"bind_grp should be empty when connected, holds {children}"


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_no_controller_outside_the_control_group(module_type):
    cmds.file(new=True, force=True)
    backend = MayaBackend()
    instance = backend.draw_guides(registry.get_module(module_type), name=module_type)
    report = Builder(backend).build(rig_name="ctrls")
    ctx = report.contexts[instance.instance_id]
    control_group = ctx.groups.control.long_name
    for controller in ctx.controllers:
        assert control_group in controller.transform.long_name, (
            f"{controller.transform.name} is outside {control_group}"
        )


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_every_output_is_a_tagged_bind_joint(module_type):
    """ctx.bind_parent reads outputs, so they must be bind joints."""
    cmds.file(new=True, force=True)
    backend = MayaBackend()
    instance = backend.draw_guides(registry.get_module(module_type), name=module_type)
    report = Builder(backend).build(rig_name="outs")
    ctx = report.contexts[instance.instance_id]
    for name, node in ctx.outputs.items():
        assert node.type == "joint", f"output '{name}' is a {node.type}, not a joint"
        assert node in ctx.deform_joints, f"output '{name}' is not a bind joint"


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_every_controller_declares_a_mirror_rule(module_type):
    cmds.file(new=True, force=True)
    backend = MayaBackend()
    instance = backend.draw_guides(registry.get_module(module_type), name=module_type)
    report = Builder(backend).build(rig_name="mirror")
    ctx = report.contexts[instance.instance_id]
    for controller in ctx.controllers:
        rule = controller.transform.meta[tags.MIRROR]
        assert rule in (tags.BEHAVIOUR, tags.WORLD)
```

- [ ] **Step 2: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_module_ground_rules.py -v`
Expected: PASS.

A failure here is a real finding, not a test bug — fix the offending module rather than relaxing the assertion.

- [ ] **Step 3: Run the whole suite**

Run: `make tests-unit && make tests-integration`
Expected: PASS. Report any failure with its output rather than moving on.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/trigger/test_module_ground_rules.py
git commit -m "test(tik.trigger): ground-rule tests binding every module"
```

---

## Self-Review Notes

**Spec coverage.** §1.1-1.2 (animator-opinion rule, layer escalation) are documentation, committed in `d0473c2`, and realised structurally by Task 14's `systems/` package. §1.3 → Task 10. §1.4 two skeletons → Tasks 11, 14, 15. §1.5 single bind hierarchy → Tasks 11, 12, 16. §1.6 mirror metadata → Task 11. §2.1 → Tasks 5, 9, 14. §2.2 → Tasks 5-8. §2.3 → Task 7. §2.4 → Tasks 6, 14. §2.5 → Tasks 1-4. §2.6 → Task 9. §3.1-3.5 → Task 14. §4 → Task 15. §6.1 → Tasks 10, 13. §6.2 → Tasks 5-8, 16. §6.4 → Task 1.

**Deliberately not covered.** §5 (the FKIK module) — the spec defers it to its own plan. §6.3 (live-Maya prototyping) is a working technique, not a deliverable.

**Known risks, flagged rather than hidden.**

1. **Task 14 is the largest task by far** and the only one whose test list runs to twelve. It resisted splitting because the stretch factors, the pole space and the bind blend all read from the same `ChainLengths` and `SoftIk` instances — a partial limb has nothing testable. If it proves unwieldy during execution, the natural seam is to land the puppet chains plus IK/FK blend first, then the soft/stretch factors, then the pole.
2. **`test_pole_base_does_not_cycle`** is the assertion most likely to fail, and the one the spec calls out as passing a naive unit test while the rig cycles. Treat a failure as a design error in the wiring, not a flaky test.
3. **API guesses.** `attribute.add_proxy`'s signature, `Module.field_definitions()`, `Node.has_attr()` and `FakeBackend.add_instance` are used as written from the surrounding code but not verified line-by-line. Task 14 Step 5 and Task 15 Step 4 say what to do if any differs: adjust the call, never the assertion's meaning.
