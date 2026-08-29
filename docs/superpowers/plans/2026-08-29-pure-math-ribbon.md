# Pure-Math Ribbon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the NURBS/follicle `Ribbon` with a geometry-free ribbon: a reusable `MatrixSpline` (B-spline-weighted `parentMatrix` blend + `aimMatrix` swing + float twist) and a thin `Ribbon` whose deformer joints are flat with live TRS channels and unbounded twist.

**Architecture:** `tik.core.bspline` (pure Python de Boor basis) → `tik.maya.constructs.matrix_spline.MatrixSpline` (per-output `parentMatrix` → `pickMatrix` → `aimMatrix` → `offsetParentMatrix`, plus a per-output `twist` float plug) → `tik.maya.constructs.ribbon.Ribbon` (plugs, twist-subtracted up frame, mid controllers riding a 2-driver spline, flat joints wired `decomposeMatrix` + `rotateX = swing + twist`). The arm module wires controller `rotateX` floats into the ribbon twist plugs.

**Tech Stack:** Maya 2024+ nodes (`parentMatrix`, `pickMatrix`, `aimMatrix`, `composeMatrix`, `decomposeMatrix`, `distanceBetween`, `power`), tik.maya `Plug` operators, pytest under `mayapy`.

**Spec:** `docs/superpowers/specs/2026-08-29-pure-math-ribbon-design.md`

## Global Constraints

- Maya 2024+ floor (Python 3.10+). `parentMatrix` needs 2024+; no fallback path.
- Inside `src/python/tik/maya/**` raw `cmds`/OpenMaya is idiomatic (speed first). Public API stays idiomatic tik.maya: `Plug` operators (`>>`, `+`, `*`, `**`), `@undo`, Types/Roles/Constructs.
- Outside tik.maya (`tik/trigger/**`) only the tik.maya API is used — never `cmds`.
- `tik/core` imports no Maya.
- Twist never enters a matrix before reaching a joint's `rotateX`. Final deformer joints are flat (no parent transform, no `offsetParentMatrix`), rotate order `xyz`, live TRS channels.
- No backward compatibility with the old `Ribbon`; names that the arm integration tests rely on are kept: `{name}_ribbon_grp`, `{name}_{index}_jnt`, `{name}_ribbon_distance`.
- Test command (PowerShell, from repo root):
  `$env:PYTHONPATH="D:\dev\tikworks\src\python"; & "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pytest <paths> -q`
- Commit after every green task. Do not push.

## File Structure

| File | Responsibility |
|---|---|
| `src/python/tik/core/bspline.py` (create) | Clamped uniform B-spline knots/basis, `clamp_degree`. Pure Python. |
| `src/python/tik/maya/constructs/matrix_spline.py` (create) | `SplineOutput` dataclass + `MatrixSpline` construct (blend, aim, twist, delete). |
| `src/python/tik/maya/constructs/ribbon.py` (rewrite) | `Ribbon`: group, plugs, up frame, controllers, joints, scaling, pins, delete. |
| `src/python/tik/maya/constructs/__init__.py`, `src/python/tik/maya/__init__.py` (modify) | Export `MatrixSpline`. |
| `src/python/tik/trigger/modules/arm/arm.py` (modify) | Wire IK/FK twist floats into both ribbons. |
| `tests/unit/test_bspline.py` (create), `tests/unit/test_matrix_spline.py` (create), `tests/unit/test_ribbon.py` (rewrite), `tests/integration/trigger/test_arm_trigger.py` (modify) | Tests. |

---

### Task 1: B-spline basis (`tik.core.bspline`)

**Files:**
- Create: `src/python/tik/core/bspline.py`
- Test: `tests/unit/test_bspline.py`

**Interfaces:**
- Produces: `knots(count: int, degree: int) -> list[float]`, `clamp_degree(count: int, degree: int) -> int`, `basis(u: float, count: int, degree: int) -> list[float]` (length `count`, sums to 1, `basis(0)` = first point, `basis(1)` = last point). `basis` raises `ValueError` for `count < 1` or `degree` outside `[0, count-1]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_bspline.py
"""Tests for the pure-Python B-spline basis (no scene needed)."""

import pytest

from tik.core.bspline import basis, clamp_degree, knots


def test_knots_are_clamped_uniform():
    assert knots(4, 3) == [0, 0, 0, 0, 1, 1, 1, 1]
    assert knots(5, 3) == [0, 0, 0, 0, 0.5, 1, 1, 1, 1]
    assert knots(3, 1) == [0, 0, 0.5, 1, 1]


def test_partition_of_unity_and_non_negative():
    for count in range(2, 7):
        for degree in range(0, count):
            for step in range(0, 10):
                weights = basis(step / 10, count, degree)
                assert len(weights) == count
                assert sum(weights) == pytest.approx(1.0)
                assert all(weight >= 0.0 for weight in weights)


def test_endpoints_interpolate():
    assert basis(0.0, 4, 3) == [1.0, 0.0, 0.0, 0.0]
    assert basis(1.0, 4, 3) == [0.0, 0.0, 0.0, 1.0]


def test_degree_one_is_linear():
    assert basis(0.25, 2, 1) == pytest.approx([0.75, 0.25])
    assert basis(0.25, 3, 1) == pytest.approx([0.5, 0.5, 0.0])


def test_degree_two_is_quadratic_bezier_for_three_points():
    assert basis(0.5, 3, 2) == pytest.approx([0.25, 0.5, 0.25])


def test_cubic_symmetry():
    forward = basis(0.3, 5, 3)
    backward = basis(0.7, 5, 3)
    assert forward == pytest.approx(list(reversed(backward)))


def test_clamp_degree():
    assert clamp_degree(2, 3) == 1
    assert clamp_degree(5, 3) == 3
    assert clamp_degree(1, 3) == 0


def test_invalid_arguments():
    with pytest.raises(ValueError):
        basis(0.5, 0, 0)
    with pytest.raises(ValueError):
        basis(0.5, 3, 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="D:\dev\tikworks\src\python"; & "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pytest tests/unit/test_bspline.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tik.core.bspline'`

- [ ] **Step 3: Implement**

```python
# src/python/tik/core/bspline.py
"""Clamped uniform B-spline basis functions (pure Python, DCC-agnostic).

Used to turn "sample a strip at parameter u" into fixed blend weights over an
ordered set of control transforms. ``basis`` is the Cox–de Boor recursion.
"""

from __future__ import annotations


def knots(count: int, degree: int) -> list[float]:
    """Clamped uniform knot vector for ``count`` control points."""
    spans = count - degree
    interior = [index / spans for index in range(1, spans)]
    return [0.0] * (degree + 1) + interior + [1.0] * (degree + 1)


def clamp_degree(count: int, degree: int) -> int:
    """Highest usable degree for ``count`` control points, at most ``degree``."""
    return max(0, min(degree, count - 1))


def basis(u: float, count: int, degree: int) -> list[float]:
    """Return the ``count`` basis weights at parameter ``u`` in [0, 1].

    The weights sum to 1 and interpolate the end points (u=0 -> first control
    point, u=1 -> last). ``u`` is clamped to [0, 1].
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    if not 0 <= degree <= count - 1:
        raise ValueError(f"degree must be within [0, {count - 1}], got {degree}")
    u = min(max(float(u), 0.0), 1.0)
    if u >= 1.0:
        weights = [0.0] * count
        weights[-1] = 1.0
        return weights
    knot = knots(count, degree)
    weights = [1.0 if knot[i] <= u < knot[i + 1] else 0.0 for i in range(len(knot) - 1)]
    for p in range(1, degree + 1):
        next_weights = []
        for i in range(len(knot) - 1 - p):
            left = 0.0
            if knot[i + p] != knot[i]:
                left = (u - knot[i]) / (knot[i + p] - knot[i]) * weights[i]
            right = 0.0
            if knot[i + p + 1] != knot[i + 1]:
                right = (knot[i + p + 1] - u) / (knot[i + p + 1] - knot[i + 1]) * weights[i + 1]
            next_weights.append(left + right)
        weights = next_weights
    return weights
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same command as Step 2. Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/core/bspline.py tests/unit/test_bspline.py
git commit -m "feat(tik.core): clamped uniform B-spline basis (de Boor)"
```

---

### Task 2: `MatrixSpline` geometry (blend, aim, outputs)

**Files:**
- Create: `src/python/tik/maya/constructs/matrix_spline.py`
- Test: `tests/unit/test_matrix_spline.py`

**Interfaces:**
- Consumes: `tik.core.bspline.basis`, `clamp_degree`.
- Produces: `SplineOutput(parameter: float, weights: list[float], transform: Transform, twist: Plug, nodes: list)`; `MatrixSpline.create(drivers, parameters, *, name, degree=3, twists=None, up_matrix=None, aim_axis=(1,0,0), up_axis=(0,1,0), parent=None) -> MatrixSpline` with attributes `name`, `group` (Transform `{name}_spline_grp`, `inheritsTransform` off), `drivers`, `degree` (clamped), `outputs: list[SplineOutput]`. Output transforms are named `{name}_{index}_out`, driven through `offsetParentMatrix`, swing-only. Raises `ValueError` for fewer than 2 drivers, parameters outside `[0, 1)`, non-ascending parameters, or `len(twists) != len(drivers)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_matrix_spline.py
"""Tests for the MatrixSpline construct."""

import pytest
from maya import cmds
from maya.api import OpenMaya

import tik.maya as tm
from tik.core.bspline import basis
from tik.maya.constructs.matrix_spline import MatrixSpline


def _drivers(positions):
    drivers = []
    for index, position in enumerate(positions):
        driver = tm.Transform.create(name=f"driver{index}")
        driver.translate = position
        drivers.append(driver)
    return drivers


def _axes(transform):
    matrix = transform.world_matrix
    return (
        OpenMaya.MVector(matrix[0], matrix[1], matrix[2]),
        OpenMaya.MVector(matrix[4], matrix[5], matrix[6]),
    )


def _close(vector, expected, tolerance=1e-4):
    return all(abs(a - b) < tolerance for a, b in zip(vector, expected))


def test_outputs_match_basis_weighted_positions():
    positions = [(0, 0, 0), (5, 3, 0), (10, 0, 2)]
    drivers = _drivers(positions)
    parameters = [0.2, 0.5, 0.8]
    spline = MatrixSpline.create(drivers, parameters, name="spl", degree=2)
    assert spline.degree == 2
    assert [output.transform.name for output in spline.outputs] == ["spl_0_out", "spl_1_out", "spl_2_out"]
    for output, u in zip(spline.outputs, parameters):
        weights = basis(u, 3, 2)
        expected = [sum(w * p[axis] for w, p in zip(weights, positions)) for axis in range(3)]
        assert _close(output.transform.world_translation, expected)
        assert output.weights == pytest.approx(weights)


def test_outputs_live_update_when_driver_moves():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.5], name="spl")
    drivers[1].translate = (10, 8, 0)
    assert _close(spline.outputs[0].transform.world_translation, (5, 4, 0))


def test_outputs_aim_along_strip_with_up_from_first_driver():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.25, 0.75], name="spl")
    for output in spline.outputs:
        x_axis, y_axis = _axes(output.transform)
        assert _close(x_axis, (1, 0, 0))
        assert _close(y_axis, (0, 1, 0))
    drivers[0].rotate = (90, 0, 0)  # default up frame rolls with the first driver
    _, y_axis = _axes(spline.outputs[0].transform)
    assert _close(y_axis, (0, 0, 1))


def test_explicit_up_matrix():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    frame = tm.Transform.create(name="frame")
    frame.rotate = (-90, 0, 0)
    spline = MatrixSpline.create(drivers, [0.5], name="spl", up_matrix=frame["worldMatrix[0]"])
    _, y_axis = _axes(spline.outputs[0].transform)
    assert _close(y_axis, (0, 0, -1))


def test_driver_rotation_does_not_leak_into_position_blend():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.5], name="spl")
    drivers[1].rotate = (0, 0, 90)
    assert _close(spline.outputs[0].transform.world_translation, (5, 0, 0))


def test_scale_blends():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.5], name="spl")
    drivers[1].scale = (3, 3, 3)
    matrix = OpenMaya.MTransformationMatrix(spline.outputs[0].transform.world_matrix)
    assert _close(matrix.scale(OpenMaya.MSpace.kWorld), (2, 2, 2))


def test_degree_is_clamped_to_driver_count():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.5], name="spl", degree=3)
    assert spline.degree == 1


def test_invalid_inputs():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    with pytest.raises(ValueError):
        MatrixSpline.create(drivers[:1], [0.5], name="spl")
    with pytest.raises(ValueError):
        MatrixSpline.create(drivers, [1.0], name="spl")
    with pytest.raises(ValueError):
        MatrixSpline.create(drivers, [0.7, 0.3], name="spl")
    with pytest.raises(ValueError):
        MatrixSpline.create(drivers, [0.5], name="spl", twists=[None])


def test_outputs_are_world_space_regardless_of_parent():
    parent = tm.Transform.create(name="parent")
    parent.translate = (0, 100, 0)
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.5], name="spl", parent=parent)
    assert spline.group.parent.name == "parent"
    assert spline.group["inheritsTransform"].value is False
    assert _close(spline.outputs[0].transform.world_translation, (5, 0, 0))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="D:\dev\tikworks\src\python"; & "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pytest tests/unit/test_matrix_spline.py -q`
Expected: FAIL with `ModuleNotFoundError ... matrix_spline`

- [ ] **Step 3: Implement the construct (twist plug exists but is not wired yet)**

```python
# src/python/tik/maya/constructs/matrix_spline.py
"""MatrixSpline: geometry-free spline of transforms built from matrix nodes.

Each output is a swing-only transform driven through ``offsetParentMatrix``:
a B-spline-weighted ``parentMatrix`` blend of the driver world matrices
(translate and scale only, rotation stripped by ``pickMatrix``), oriented by
an ``aimMatrix`` that aims at the next output and aligns its up axis to a
caller-supplied, twist-free frame. Twist is interpolated with the same
weights as plain float math and exposed per output as a ``twist`` plug; it
never enters a matrix, so it is unbounded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from maya import cmds

from tik.core.bspline import basis, clamp_degree

from ..core import attribute
from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import resolve
from ..core.scene import create_node
from ..types.transform import Transform

AIM = 1  # aimMatrix.primaryMode "Aim"
ALIGN = 2  # aimMatrix.secondaryMode "Align"


def _node(item):
    return resolve(item) if isinstance(item, str) else item


@dataclass
class SplineOutput:
    """One sample along the spline."""

    parameter: float
    weights: list[float]
    transform: Transform
    twist: Plug
    nodes: list = field(default_factory=list)


class MatrixSpline:
    """Wrapper holding the drivers, outputs and network of a matrix spline."""

    def __init__(self, name: str, group: Transform, drivers: list, degree: int) -> None:
        self.name = name
        self.group = group
        self.drivers = drivers
        self.degree = degree
        self.outputs: list[SplineOutput] = []

    @classmethod
    @undo
    def create(
        cls,
        drivers: Sequence,
        parameters: Sequence[float],
        *,
        name: str,
        degree: int = 3,
        twists: Optional[Sequence[Optional[Plug]]] = None,
        up_matrix: Optional[Plug] = None,
        aim_axis: Sequence[float] = (1, 0, 0),
        up_axis: Sequence[float] = (0, 1, 0),
        parent=None,
    ) -> "MatrixSpline":
        """Sample ``drivers`` at ``parameters``.

        Args:
            drivers: Ordered transforms (or names) acting as control points.
            parameters: Ascending values in ``[0, 1)``; one output per value.
            name: Prefix for all created nodes.
            degree: Requested B-spline degree, clamped to ``len(drivers) - 1``.
            twists: Optional float plug per driver (``None`` contributes no
                twist), interpolated with the position weights.
            up_matrix: World matrix plug whose ``up_axis`` orients every
                output's secondary axis. Defaults to the first driver.
            aim_axis: Output axis pointing along the strip.
            up_axis: Output axis aligned to ``up_matrix``.
            parent: Optional parent for the spline group.
        """
        drivers = [_node(driver) for driver in drivers]
        if len(drivers) < 2:
            raise ValueError("MatrixSpline needs at least two drivers.")
        parameters = [float(value) for value in parameters]
        if any(value < 0.0 or value >= 1.0 for value in parameters):
            raise ValueError("MatrixSpline parameters must satisfy 0 <= u < 1.")
        if parameters != sorted(parameters):
            raise ValueError("MatrixSpline parameters must be ascending.")
        twists = list(twists) if twists is not None else [None] * len(drivers)
        if len(twists) != len(drivers):
            raise ValueError("One twist plug (or None) per driver is required.")
        degree = clamp_degree(len(drivers), degree)
        if up_matrix is None:
            up_matrix = drivers[0]["worldMatrix[0]"]

        group = Transform.create(name=f"{name}_spline_grp")
        if parent is not None:
            group.parent = _node(parent)
        # outputs carry world-space matrices; the group must not transform them again
        group["inheritsTransform"].value = False

        spline = cls(name, group, drivers, degree)
        blends = [spline._create_blend(index, u) for index, u in enumerate(parameters)]
        for index, (u, (pick, weights, nodes)) in enumerate(zip(parameters, blends)):
            if index + 1 < len(blends):
                target = blends[index + 1][0]["outputMatrix"]
            else:
                target = drivers[-1]["worldMatrix[0]"]
            aim = spline._create_aim(index, pick, target, up_matrix, aim_axis, up_axis)
            output = Transform.create(name=f"{name}_{index}_out", parent=group.long_name)
            aim["outputMatrix"] >> output["offsetParentMatrix"]
            twist = attribute.add_float(output, "twist", default=0.0)
            spline.outputs.append(SplineOutput(u, weights, output, twist, [*nodes, aim]))
        return spline

    def _create_blend(self, index: int, u: float):
        """parentMatrix (weighted drivers) -> pickMatrix (translate + scale only)."""
        weights = basis(u, len(self.drivers), self.degree)
        blend = create_node("parentMatrix", name=f"{self.name}_{index}_parentMatrix")
        for slot, (driver, weight) in enumerate(zip(self.drivers, weights)):
            driver["worldMatrix[0]"] >> blend[f"target[{slot}].targetMatrix"]
            blend[f"target[{slot}].weight"].value = weight
        pick = create_node("pickMatrix", name=f"{self.name}_{index}_pickMatrix")
        pick["useRotate"].value = False
        pick["useShear"].value = False
        blend["outputMatrix"] >> pick["inputMatrix"]
        return pick, weights, [blend, pick]

    def _create_aim(self, index: int, pick, target: Plug, up_matrix: Plug, aim_axis, up_axis):
        aim = create_node("aimMatrix", name=f"{self.name}_{index}_aimMatrix")
        pick["outputMatrix"] >> aim["inputMatrix"]
        aim["primaryMode"].value = AIM
        aim["primaryInputAxis"].value = tuple(aim_axis)
        target >> aim["primaryTargetMatrix"]
        aim["secondaryMode"].value = ALIGN
        aim["secondaryInputAxis"].value = tuple(up_axis)
        aim["secondaryTargetVector"].value = tuple(up_axis)
        up_matrix >> aim["secondaryTargetMatrix"]
        return aim
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same command as Step 2. Expected: `9 passed`. If `aim["primaryInputAxis"].value = (1, 0, 0)` fails, set the children instead: `for axis, value in zip("XYZ", aim_axis): aim[f"primaryInputAxis{axis}"].value = value` (same for the secondary attributes).

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/maya/constructs/matrix_spline.py tests/unit/test_matrix_spline.py
git commit -m "feat(tik.maya): MatrixSpline construct — parentMatrix/pickMatrix/aimMatrix strip sampling"
```

---

### Task 3: `MatrixSpline` twist, delete and exports

**Files:**
- Modify: `src/python/tik/maya/constructs/matrix_spline.py`
- Modify: `src/python/tik/maya/constructs/__init__.py`, `src/python/tik/maya/__init__.py`
- Test: `tests/unit/test_matrix_spline.py`

**Interfaces:**
- Produces: `SplineOutput.twist` is driven by `Σ weights[j] * twists[j]` (float math; `None` entries skipped); `MatrixSpline.nodes -> list` (all DG nodes); `MatrixSpline.delete()`; `tm.MatrixSpline` export.

- [ ] **Step 1: Append the failing tests**

```python
# append to tests/unit/test_matrix_spline.py


def test_twist_interpolates_with_position_weights():
    drivers = _drivers([(0, 0, 0), (5, 0, 0), (10, 0, 0)])
    twists = [tm.attribute.add_float(driver, "twist") for driver in drivers]
    spline = MatrixSpline.create(drivers, [0.5], name="spl", degree=2, twists=twists)
    twists[0].value = 100.0
    twists[1].value = 20.0
    twists[2].value = 300.0
    assert spline.outputs[0].twist.value == pytest.approx(0.25 * 100 + 0.5 * 20 + 0.25 * 300)


def test_twist_is_unbounded_and_stays_out_of_the_matrix():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    twists = [tm.attribute.add_float(driver, "twist") for driver in drivers]
    spline = MatrixSpline.create(drivers, [0.5], name="spl", twists=twists)
    twists[1].value = 900.0
    assert spline.outputs[0].twist.value == pytest.approx(450.0)
    _, y_axis = _axes(spline.outputs[0].transform)
    assert _close(y_axis, (0, 1, 0))


def test_missing_twists_leave_plug_at_zero():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.5], name="spl", twists=[None, None])
    assert spline.outputs[0].twist.value == 0.0
    assert not cmds.listConnections(spline.outputs[0].twist.path, source=True, destination=False)


def test_delete_removes_network():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    twists = [tm.attribute.add_float(driver, "twist") for driver in drivers]
    spline = MatrixSpline.create(drivers, [0.25, 0.75], name="spl", twists=twists)
    spline.delete()
    assert not cmds.objExists("spl_spline_grp")
    assert not cmds.ls(type=["parentMatrix", "pickMatrix", "aimMatrix"])
    assert not cmds.ls("multDL*")


def test_exported_from_tik_maya():
    assert tm.MatrixSpline is MatrixSpline
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="D:\dev\tikworks\src\python"; & "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pytest tests/unit/test_matrix_spline.py -q`
Expected: the first two twist tests, `test_delete_removes_network` and `test_exported_from_tik_maya` FAIL (`twist.value == 0`, `AttributeError: delete`, `AttributeError: MatrixSpline`).

- [ ] **Step 3: Wire the twist sum, add `nodes` and `delete`**

In `create`, replace the two lines

```python
            twist = attribute.add_float(output, "twist", default=0.0)
            spline.outputs.append(SplineOutput(u, weights, output, twist, [*nodes, aim]))
```

with

```python
            twist = attribute.add_float(output, "twist", default=0.0)
            twist_source, math_nodes = spline._weighted_sum(twists, weights)
            if twist_source is not None:
                twist_source >> twist
            spline.outputs.append(SplineOutput(u, weights, output, twist, [*nodes, aim, *math_nodes]))
```

and add to the class:

```python
    @staticmethod
    def _weighted_sum(plugs: Sequence[Optional[Plug]], weights: Sequence[float]):
        """Return ``(plug, nodes)`` for ``sum(w * plug)``; ``(None, [])`` if nothing contributes."""
        total = None
        nodes: list = []
        for plug, weight in zip(plugs, weights):
            if plug is None or abs(weight) < 1e-9:
                continue
            term = plug
            if abs(weight - 1.0) > 1e-9:
                term = plug * weight
                nodes.append(term.node)
            if total is None:
                total = term
            else:
                total = total + term
                nodes.append(total.node)
        return total, nodes

    @property
    def nodes(self) -> list:
        """Every DG node created for the spline (output transforms excluded)."""
        return [node for output in self.outputs for node in output.nodes]

    @undo
    def delete(self) -> None:
        """Delete the spline group, its outputs and the whole network."""
        cmds.delete([node.long_name for node in self.nodes if node.exists()])
        if self.group.exists():
            cmds.delete(self.group.long_name)
```

Exports — `src/python/tik/maya/constructs/__init__.py`:

```python
from .matrix_spline import MatrixSpline
```
and add `"MatrixSpline"` to `__all__` (keep alphabetical: after `"MatrixConstraint"`).

`src/python/tik/maya/__init__.py`: add `MatrixSpline,` to the `from .constructs import (...)` block and `"MatrixSpline",` to `__all__` next to `"MatrixConstraint"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: same command. Expected: `14 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/maya/constructs/matrix_spline.py src/python/tik/maya/constructs/__init__.py src/python/tik/maya/__init__.py tests/unit/test_matrix_spline.py
git commit -m "feat(tik.maya): MatrixSpline float twist interpolation, delete, export"
```

---

### Task 4: `Ribbon` rewrite — structure, up frame, controllers, flat joints

**Files:**
- Rewrite: `src/python/tik/maya/constructs/ribbon.py`
- Rewrite: `tests/unit/test_ribbon.py`

**Interfaces:**
- Consumes: `MatrixSpline.create(...)`, `SplineOutput.twist/.transform`, `Measure` (Task 5), `MatrixConstraint` (Task 5).
- Produces: `Ribbon.create(start, end, *, name, joint_count=5, controller_count=1, degree=3, up_vector=(0,1,0), scaleable=True, preserve_volume=False, parent=None) -> Ribbon` with `group` (`{name}_ribbon_grp`), `start_plug`/`end_plug` (`{name}_start_plug`/`{name}_end_plug`, children of `group`), `start_twist`/`end_twist` (float Plugs `twist` on the plugs), `up_frame` (matrix Plug), `control_spline` (`MatrixSpline` or `None`), `spline` (`MatrixSpline`), `joint_group` (`{name}_joints_grp`, non-inheriting), `controllers: list[Controller]` (`{name}_mid{i}_ctrl`), `deformer_joints: list[Joint]` (`{name}_{i}_jnt`, flat under `joint_group`, rotate order xyz), `scale_switch` (Plug `scaleSwitch` on `start_plug` when scaleable, else `None`), `measure` (`None` until Task 5). Scaling, pins and `delete` come in Task 5.

- [ ] **Step 1: Replace `tests/unit/test_ribbon.py` with the failing tests**

```python
# tests/unit/test_ribbon.py
"""Tests for the pure-math Ribbon construct."""

import math

import pytest
from maya import cmds
from maya.api import OpenMaya

import tik.maya as tm
from tik.core.bspline import basis
from tik.maya.constructs.ribbon import Ribbon


def _endpoints():
    start = tm.Transform.create(name="start")
    end = tm.Transform.create(name="end")
    end.translate = (10, 0, 0)
    return start, end


def _close(vector, expected, tolerance=1e-4):
    return all(abs(a - b) < tolerance for a, b in zip(vector, expected))


def _axes(transform):
    matrix = transform.world_matrix
    return (
        OpenMaya.MVector(matrix[0], matrix[1], matrix[2]),
        OpenMaya.MVector(matrix[4], matrix[5], matrix[6]),
    )


def test_ribbon_creates_expected_nodes():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="upArm", joint_count=4, controller_count=1)
    assert len(ribbon.deformer_joints) == 4
    assert len(ribbon.controllers) == 1
    assert ribbon.group.name == "upArm_ribbon_grp"
    assert ribbon.start_plug.parent.name == ribbon.group.name
    assert ribbon.deformer_joints[0].name == "upArm_0_jnt"
    assert ribbon.controllers[0].transform.name == "upArm_mid0_ctrl"
    assert not cmds.ls(type=["nurbsSurface", "follicle", "skinCluster"])
    assert ribbon.spline.degree == 2  # start + mid + end clamps cubic to quadratic
    assert ribbon.control_spline.degree == 1


def test_joints_are_distributed_between_endpoints():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3, controller_count=0)
    assert ribbon.control_spline is None
    for index, joint in enumerate(ribbon.deformer_joints):
        assert _close(joint.world_translation, (10 * (index + 0.5) / 3, 0, 0))


def test_joints_match_basis_weighted_positions_after_bending():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=5, controller_count=1)
    ribbon.controllers[0].transform.translate = (0, 3, 0)
    positions = [(0, 0, 0), (5, 3, 0), (10, 0, 0)]
    for index, joint in enumerate(ribbon.deformer_joints):
        weights = basis((index + 0.5) / 5, 3, 2)
        expected = [sum(w * p[axis] for w, p in zip(weights, positions)) for axis in range(3)]
        assert _close(joint.world_translation, expected)


def test_plugs_sit_on_endpoints_and_joints_aim_along_strip():
    start, end = _endpoints()
    end.translate = (0, 10, 0)
    ribbon = Ribbon.create(start, end, name="rbn", up_vector=(0, 0, 1))
    assert _close(ribbon.start_plug.world_translation, start.world_translation)
    assert _close(ribbon.end_plug.world_translation, end.world_translation)
    x_axis, y_axis = _axes(ribbon.deformer_joints[0])
    assert _close(x_axis, (0, 1, 0))
    assert _close(y_axis, (0, 0, 1))


def test_deformer_joints_are_flat_with_live_channels():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=2, controller_count=0)
    for joint in ribbon.deformer_joints:
        assert joint.parent.name == ribbon.joint_group.name
        assert joint["rotateOrder"].value == 0
        assert not cmds.listConnections(f"{joint.long_name}.offsetParentMatrix", source=True, destination=False)
        assert _close(joint.translate, joint.world_translation)
    ribbon.end_plug.translate = (5, 4, 0)
    assert ribbon.deformer_joints[1]["translateY"].value == pytest.approx(3.0, abs=1e-4)
    assert ribbon.deformer_joints[1]["translateX"].value == pytest.approx(7.5, abs=1e-4)


def test_mid_controller_follows_ends():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", controller_count=1)
    ribbon.start_plug.translate = (-5, 4, 0)
    ribbon.end_plug.translate = (5, 4, 0)
    assert ribbon.controllers[0].transform.world_translation.y == pytest.approx(4, abs=1e-3)


def test_twist_interpolates_as_unbounded_floats():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3, controller_count=0)
    ribbon.end_twist.value = 270.0
    for index, joint in enumerate(ribbon.deformer_joints):
        angle = 270 * (index + 0.5) / 3  # 45, 135, 225
        assert joint["rotateX"].value == pytest.approx(angle, abs=1e-3)
        x_axis, y_axis = _axes(joint)
        assert _close(x_axis, (1, 0, 0))
        assert _close(y_axis, (0, math.cos(math.radians(angle)), math.sin(math.radians(angle))))


def test_mid_controller_roll_adds_local_twist():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3, controller_count=1)
    ribbon.controllers[0].transform.rotate = (90, 0, 0)
    weights = basis(0.5, 3, 2)
    assert ribbon.deformer_joints[1]["rotateX"].value == pytest.approx(weights[1] * 90, abs=1e-3)
    assert _close(ribbon.deformer_joints[1].world_translation, (5, 0, 0))


def test_start_roll_beyond_180_with_twist_wired_does_not_flip():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3, controller_count=0)
    ribbon.start_plug["rotateX"] >> ribbon.start_twist
    ribbon.end_plug["rotateX"] >> ribbon.end_twist
    ribbon.start_plug.rotate = (270, 0, 0)
    ribbon.end_plug.rotate = (270, 0, 0)
    for joint in ribbon.deformer_joints:
        assert joint["rotateX"].value == pytest.approx(270, abs=1e-3)
        x_axis, y_axis = _axes(joint)
        assert _close(x_axis, (1, 0, 0))
        assert _close(y_axis, (0, 0, -1))


def test_invalid_arguments():
    start, end = _endpoints()
    with pytest.raises(ValueError):
        Ribbon.create(start, end, name="rbn", joint_count=0)
    end.translate = (0, 0, 0)
    with pytest.raises(ValueError):
        Ribbon.create(start, end, name="rbn")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="D:\dev\tikworks\src\python"; & "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pytest tests/unit/test_ribbon.py -q`
Expected: FAIL (`TypeError` on unknown keyword `degree`/`controller_count` behaviours, `AttributeError: spline`, etc.).

- [ ] **Step 3: Replace `src/python/tik/maya/constructs/ribbon.py`**

```python
"""Ribbon: a pure-math strip of deformer joints between two ends.

No geometry. Start/end "plug" transforms are what callers pin to their
controllers; ``MatrixSpline`` blends the plugs and the mid controllers into
swing-only frames, and every deformer joint is a flat joint with live TRS
channels: translate/scale/swing decomposed from its spline output and the
interpolated twist added as a float onto ``rotateX`` — never through a
matrix, so twist is unbounded.

The aim up frame is the pinned start matrix with the wired ``start_twist``
removed (``Rx(-twist) * start_plug.worldMatrix``): it swings with the limb
but carries no twist.
"""

from __future__ import annotations

from typing import Optional, Sequence

from maya import cmds

from ..core import attribute
from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import resolve
from ..core.scene import create_node, ensure_plugin
from ..roles.controller import Controller
from ..types.joint import Joint
from ..types.transform import Transform
from .matrix_constraint import MatrixConstraint
from .matrix_spline import MatrixSpline
from .measure import Measure

ROTATE_ORDER_XYZ = 0


def _node(item):
    return resolve(item) if isinstance(item, str) else item


class Ribbon:
    """Wrapper holding every node of a ribbon setup."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.group: Transform = None
        self.start_plug: Transform = None
        self.end_plug: Transform = None
        self.start_twist: Plug = None
        self.end_twist: Plug = None
        self.up_frame: Plug = None
        self.control_spline: Optional[MatrixSpline] = None
        self.spline: MatrixSpline = None
        self.joint_group: Transform = None
        self.controllers: list[Controller] = []
        self.deformer_joints: list[Joint] = []
        self.scale_switch: Optional[Plug] = None
        self.measure: Optional[Measure] = None
        self._decomposes: list = []
        self._nodes: list = []

    # ------------------------------------------------------------------ build
    @classmethod
    @undo
    def create(
        cls,
        start,
        end,
        *,
        name: str,
        joint_count: int = 5,
        controller_count: int = 1,
        degree: int = 3,
        up_vector: Sequence[float] = (0, 1, 0),
        scaleable: bool = True,
        preserve_volume: bool = False,
        parent=None,
    ) -> "Ribbon":
        """Build a ribbon between ``start`` and ``end``.

        Args:
            start: Transform at the ribbon start.
            end: Transform at the ribbon end.
            name: Prefix for all created nodes.
            joint_count: Number of deformer joints.
            controller_count: Number of mid controllers between the ends.
            degree: B-spline degree of the joint strip (clamped to the number
                of drivers minus one; 0 mid controllers is always linear).
            up_vector: World up used for the initial placement of the group.
            scaleable: Add stretch driven ``scaleX`` on the deformer joints.
            preserve_volume: With ``scaleable``, counter-scale Y/Z by
                ``ratio ** -0.5``.
            parent: Optional parent for the ribbon group.
        """
        start, end = _node(start), _node(end)
        if joint_count < 1:
            raise ValueError("Ribbon needs at least one deformer joint.")
        length = start.distance_to(end)
        if length <= 0:
            raise ValueError("Ribbon start and end must not overlap.")
        ribbon = cls(name)
        ribbon._create_group(parent)
        ribbon._create_plugs(length, scaleable)
        ribbon._create_up_frame()
        ribbon._create_controllers(controller_count, length)
        ribbon._create_joints(joint_count, degree)
        ribbon._place(start, end, up_vector)
        if scaleable:
            ribbon._create_scaling(preserve_volume)
        return ribbon

    def _create_group(self, parent) -> None:
        self.group = Transform.create(name=f"{self.name}_ribbon_grp")
        if parent is not None:
            self.group.parent = _node(parent)

    def _create_plugs(self, length: float, scaleable: bool) -> None:
        half = length * 0.5
        self.start_plug = Transform.create(name=f"{self.name}_start_plug", parent=self.group.long_name)
        self.end_plug = Transform.create(name=f"{self.name}_end_plug", parent=self.group.long_name)
        self.start_plug.translate = (-half, 0, 0)
        self.end_plug.translate = (half, 0, 0)
        self.start_twist = attribute.add_float(self.start_plug, "twist")
        self.end_twist = attribute.add_float(self.end_plug, "twist")
        if scaleable:
            self.scale_switch = attribute.add_float(
                self.start_plug, "scaleSwitch", default=1.0, min=0.0, max=1.0
            )

    def _create_up_frame(self) -> None:
        """``Rx(-start_twist) * start_plug.worldMatrix``: swings with the pin, no twist."""
        ensure_plugin("matrixNodes")
        compose = create_node("composeMatrix", name=f"{self.name}_upFrame_composeMatrix")
        negated = self.start_twist * -1.0
        negated >> compose["inputRotateX"]
        mult = create_node("multMatrix", name=f"{self.name}_upFrame_multMatrix")
        compose["outputMatrix"] >> mult["matrixIn[0]"]
        self.start_plug["worldMatrix[0]"] >> mult["matrixIn[1]"]
        self.up_frame = mult["matrixSum"]
        self._nodes.extend([negated.node, compose, mult])

    def _create_controllers(self, count: int, length: float) -> None:
        if count < 1:
            return
        parameters = [(index + 1) / (count + 1) for index in range(count)]
        self.control_spline = MatrixSpline.create(
            [self.start_plug, self.end_plug],
            parameters,
            name=f"{self.name}_ctrl",
            degree=1,
            twists=[self.start_twist, self.end_twist],
            up_matrix=self.up_frame,
            parent=self.group,
        )
        for index, output in enumerate(self.control_spline.outputs):
            # the output frame carries the interpolated twist so the controller rides it
            output.transform["rotateOrder"].value = ROTATE_ORDER_XYZ
            output.twist >> output.transform["rotateX"]
            controller = Controller.create(
                name=f"{self.name}_mid{index}_ctrl",
                shape="Circle",
                size=length * 0.15,
                parent=output.transform.long_name,
            )
            controller.transform["rotateOrder"].value = ROTATE_ORDER_XYZ
            self.controllers.append(controller)

    def _mid_twists(self) -> list[Plug]:
        """Per mid controller: interpolated end twist plus the controller's own roll."""
        twists = []
        outputs = self.control_spline.outputs if self.control_spline is not None else []
        for output, controller in zip(outputs, self.controllers):
            twist = output.twist + controller.transform["rotateX"]
            self._nodes.append(twist.node)
            twists.append(twist)
        return twists

    def _create_joints(self, count: int, degree: int) -> None:
        drivers = [self.start_plug, *[ctrl.transform for ctrl in self.controllers], self.end_plug]
        twists = [self.start_twist, *self._mid_twists(), self.end_twist]
        parameters = [(index + 0.5) / count for index in range(count)]
        self.spline = MatrixSpline.create(
            drivers,
            parameters,
            name=self.name,
            degree=degree,
            twists=twists,
            up_matrix=self.up_frame,
            parent=self.group,
        )
        self.joint_group = Transform.create(name=f"{self.name}_joints_grp", parent=self.group.long_name)
        # joints hold world-space channel values; the group must not transform them again
        self.joint_group["inheritsTransform"].value = False
        for index, output in enumerate(self.spline.outputs):
            joint = Joint.create(name=f"{self.name}_{index}_jnt", parent=self.joint_group.long_name)
            joint["rotateOrder"].value = ROTATE_ORDER_XYZ
            decompose = create_node("decomposeMatrix", name=f"{self.name}_{index}_decomposeMatrix")
            output.transform["worldMatrix[0]"] >> decompose["inputMatrix"]
            decompose["outputTranslate"] >> joint["translate"]
            decompose["outputRotateY"] >> joint["rotateY"]
            decompose["outputRotateZ"] >> joint["rotateZ"]
            # twist is added after decomposition so rotateX stays an unbounded float
            rotate_x = decompose["outputRotateX"] + output.twist
            rotate_x >> joint["rotateX"]
            for axis in "XYZ":
                decompose[f"outputScale{axis}"] >> joint[f"scale{axis}"]
            self.deformer_joints.append(joint)
            self._decomposes.append(decompose)
            self._nodes.extend([decompose, rotate_x.node])

    def _place(self, start, end, up_vector) -> None:
        self.group.world_position = Transform.between(start, end)
        self.group.aim_at(
            end, aim_vector=(1, 0, 0), up_vector=(0, 1, 0), world_up=tuple(up_vector)
        )

    def _create_scaling(self, preserve_volume: bool) -> None:
        raise NotImplementedError  # Task 5
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same command. Expected: `10 passed`. (`test_ribbon_creates_expected_nodes` and the two tests using the default `scaleable=True` need Task 5 — if they raise `NotImplementedError`, pass `scaleable=False` locally only to check the others, then restore; Task 5 closes the gap.) If `decompose["outputRotateX"] + output.twist` raises `TypeError` on the angle plug, build the add explicitly: `add = create_node(NodeNames.ADD_DOUBLE_LINEAR, name=f"{self.name}_{index}_twist_add")` (import `NodeNames` from `..core.constants`), connect `outputRotateX >> add["input1"]`, `output.twist >> add["input2"]`, `add["output"] >> joint["rotateX"]`.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/maya/constructs/ribbon.py tests/unit/test_ribbon.py
git commit -m "feat(tik.maya): pure-math Ribbon — MatrixSpline strip, twist-free up frame, flat live joints"
```

---

### Task 5: `Ribbon` scaling, volume, pins, delete

**Files:**
- Modify: `src/python/tik/maya/constructs/ribbon.py`
- Test: `tests/unit/test_ribbon.py`

**Interfaces:**
- Produces: `Ribbon.pin_start(node, maintain_offset=True) -> MatrixConstraint`, `Ribbon.pin_end(node, maintain_offset=True) -> MatrixConstraint` (full TRS onto the plug), `Ribbon.delete()`, `ribbon.measure` (`Measure` named `{name}_ribbon` → node `{name}_ribbon_distance`), `scaleX = blendedScaleX * ((ratio - 1) * scaleSwitch + 1)`, with `preserve_volume`: `scaleY/Z = blendedScale * ((ratio ** -0.5 - 1) * scaleSwitch + 1)`.

- [ ] **Step 1: Append the failing tests**

```python
# append to tests/unit/test_ribbon.py


def test_pinning_end_stretches_ribbon():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3)
    ribbon.pin_start(start)
    ribbon.pin_end(end)
    end.translate = (20, 0, 0)
    xs = sorted(joint.world_translation.x for joint in ribbon.deformer_joints)
    assert xs[-1] > 10


def test_scaleable_switch_drives_joint_scale():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", scaleable=True)
    assert ribbon.scale_switch is not None
    assert ribbon.scale_switch.value == 1.0
    assert ribbon.measure.node.name == "rbn_ribbon_distance"
    ribbon.pin_end(end)
    end.translate = (20, 0, 0)
    assert ribbon.deformer_joints[0]["scaleX"].value == pytest.approx(2.0, abs=1e-4)
    assert ribbon.deformer_joints[0]["scaleY"].value == pytest.approx(1.0, abs=1e-4)
    ribbon.scale_switch.value = 0.0
    assert ribbon.deformer_joints[0]["scaleX"].value == pytest.approx(1.0, abs=1e-4)


def test_preserve_volume():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", scaleable=True, preserve_volume=True)
    ribbon.pin_end(end)
    end.translate = (40, 0, 0)
    assert ribbon.deformer_joints[0]["scaleX"].value == pytest.approx(4.0, abs=1e-4)
    assert ribbon.deformer_joints[0]["scaleY"].value == pytest.approx(0.5, abs=1e-4)
    assert ribbon.deformer_joints[0]["scaleZ"].value == pytest.approx(0.5, abs=1e-4)


def test_not_scaleable():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", scaleable=False)
    assert ribbon.scale_switch is None
    assert ribbon.measure is None
    ribbon.pin_end(end)
    end.translate = (20, 0, 0)
    assert ribbon.deformer_joints[0]["scaleX"].value == pytest.approx(1.0, abs=1e-4)


def test_pinned_start_roll_with_wired_twist_follows_without_flip():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=2, controller_count=0)
    ribbon.pin_start(start)
    ribbon.pin_end(end)
    start["rotateX"] >> ribbon.start_twist
    end["rotateX"] >> ribbon.end_twist
    start.rotate = (450, 0, 0)
    end.rotate = (450, 0, 0)
    for joint in ribbon.deformer_joints:
        assert joint["rotateX"].value == pytest.approx(450, abs=1e-3)
        x_axis, y_axis = _axes(joint)
        assert _close(x_axis, (1, 0, 0))
        assert _close(y_axis, (0, 0, 1))


def test_delete():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn")
    ribbon.delete()
    assert not cmds.objExists("rbn_ribbon_grp")
    assert not cmds.objExists("rbn_ribbon_distance")
    assert not cmds.ls(type=["parentMatrix", "pickMatrix", "aimMatrix", "decomposeMatrix", "composeMatrix"])


def test_create_is_one_undo_step():
    start, end = _endpoints()
    Ribbon.create(start, end, name="rbn")
    cmds.undo()
    assert not cmds.objExists("rbn_ribbon_grp")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="D:\dev\tikworks\src\python"; & "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pytest tests/unit/test_ribbon.py -q`
Expected: new tests FAIL with `NotImplementedError` / `AttributeError: pin_end` / `delete`.

- [ ] **Step 3: Implement scaling, pins, delete**

Replace the `_create_scaling` stub and append the pin/delete methods:

```python
    def _create_scaling(self, preserve_volume: bool) -> None:
        self.measure = Measure.create(self.start_plug, self.end_plug, name=f"{self.name}_ribbon")
        ratio = self.measure.ratio_plug()
        # blend between 1.0 (switch off) and the live ratio (switch on)
        stretch = (ratio - 1.0) * self.scale_switch + 1.0
        volume = None
        if preserve_volume:
            volume = (ratio ** -0.5 - 1.0) * self.scale_switch + 1.0
        for joint, decompose in zip(self.deformer_joints, self._decomposes):
            scale_x = decompose["outputScaleX"] * stretch
            scale_x >> joint["scaleX"]
            self._nodes.append(scale_x.node)
            if volume is not None:
                for axis in "YZ":
                    scaled = decompose[f"outputScale{axis}"] * volume
                    scaled >> joint[f"scale{axis}"]
                    self._nodes.append(scaled.node)

    # -------------------------------------------------------------- pinning
    @undo
    def pin_start(self, node, maintain_offset: bool = True) -> MatrixConstraint:
        """Drive the start plug from ``node`` (full TRS)."""
        return MatrixConstraint.create(
            node, self.start_plug, maintain_offset=maintain_offset,
            name=f"{self.name}_startPin",
        )

    @undo
    def pin_end(self, node, maintain_offset: bool = True) -> MatrixConstraint:
        """Drive the end plug from ``node`` (full TRS)."""
        return MatrixConstraint.create(
            node, self.end_plug, maintain_offset=maintain_offset,
            name=f"{self.name}_endPin",
        )

    @undo
    def delete(self) -> None:
        """Delete the entire ribbon hierarchy and network."""
        if self.measure is not None:
            self.measure.delete()
        for spline in (self.control_spline, self.spline):
            if spline is not None:
                spline.delete()
        cmds.delete([node.long_name for node in self._nodes if node.exists()])
        if self.group is not None and self.group.exists():
            cmds.delete(self.group.long_name)
```

- [ ] **Step 4: Run the ribbon, spline and bspline suites**

Run: `$env:PYTHONPATH="D:\dev\tikworks\src\python"; & "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pytest tests/unit/test_ribbon.py tests/unit/test_matrix_spline.py tests/unit/test_bspline.py -q`
Expected: all pass (`17 + 14 + 8`). If `test_delete` finds leftover nodes created by Plug operators inside `Measure.ratio_plug` / the stretch expression, extend `self._nodes` with `stretch.node` and the intermediate `.node`s of the expression (each operator result has `.node`).

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/maya/constructs/ribbon.py tests/unit/test_ribbon.py
git commit -m "feat(tik.maya): Ribbon stretch/volume, full-TRS pins, delete"
```

---

### Task 6: Arm module twist wiring + integration

**Files:**
- Modify: `src/python/tik/trigger/modules/arm/arm.py:94-142`
- Test: `tests/integration/trigger/test_arm_trigger.py`

**Interfaces:**
- Consumes: `tm.Ribbon.create(...)`, `ribbon.start_twist`/`end_twist`, `chain.ik_joints`, `chain.fk_joints`, `switch_plug` (`ikFk`: 1.0 = IK, 0.0 = FK), `ctx.controller(...)` returning a `Controller` with `.transform`.
- Produces: both arm ribbons receive accumulated axial rotation as floats: FK sums of `fk_*_ctrl.rotateX`, IK sums of `ik_joint.rotateX`, blended `fk * (1 - ikFk) + ik * ikFk`.

- [ ] **Step 1: Append the failing integration test**

```python
# append to tests/integration/trigger/test_arm_trigger.py


def test_arm_forearm_twists_with_fk_wrist_beyond_180(backend):
    report, arm = _build_arm(backend, ribbon_joints=3)
    tm.Transform("L_arm_switch_ctrl")["ikFk"].value = 0.0
    tm.Transform("L_arm_fk_hand_ctrl").rotate = (270, 0, 0)
    last = tm.Joint("L_arm_lowArm_2_jnt")
    # drivers start/mid/end -> quadratic weights at u=5/6 are 1/36, 10/36, 25/36;
    # the mid controller carries half the end twist: 10/36*135 + 25/36*270 = 225
    assert last["rotateX"].value == pytest.approx(225.0, abs=1e-2)
    assert tm.Joint("L_arm_lowArm_0_jnt")["rotateX"].value < last["rotateX"].value
    assert tm.Joint("L_arm_upArm_2_jnt")["rotateX"].value == pytest.approx(0.0, abs=1e-2)
```

- [ ] **Step 2: Run the arm integration suite to verify state**

Run: `$env:PYTHONPATH="D:\dev\tikworks\src\python"; & "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pytest tests/integration/trigger/test_arm_trigger.py -q`
Expected: the five existing tests PASS against the new ribbon (names and API preserved); the new test FAILS (`rotateX == 0`).

- [ ] **Step 3: Wire the twists in `arm.py`**

In the FK controller loop (currently lines 94-104) collect the controllers:

```python
        fk_parent = collar_ctrl.transform
        fk_group = None
        fk_controllers = []
        for label, joint in zip(("upArm", "lowArm", "hand"), chain.fk_joints):
            controller = ctx.controller(f"fk_{label}", shape="Circle", size=size, parent=fk_parent, match=joint)
            offset = controller.transform.create_offset_group(name=ctx.name(f"fk_{label}", suffix="offset"))
            attribute.lock_and_hide(controller.transform, ("sx", "sy", "sz", "v"))
            tm.MatrixConstraint.create(controller.transform, joint, maintain_offset=True, skip_scale="xyz")
            fk_group = fk_group or offset
            fk_parent = controller.transform
            fk_controllers.append(controller)
        chain.fk_visibility >> fk_group["visibility"]
```

Replace the ribbons block (currently lines 125-142) with:

```python
        # ribbons ------------------------------------------------------------
        # twist travels as floats only (never through a matrix): accumulate each
        # control's own axial rotation along the chain per IK/FK branch, then
        # blend the two float sums through the switch.
        twists = []
        fk_sum = ik_sum = None
        for fk_ctrl, ik_joint in zip(fk_controllers, chain.ik_joints):
            fk_roll, ik_roll = fk_ctrl.transform["rotateX"], ik_joint["rotateX"]
            fk_sum = fk_roll if fk_sum is None else fk_sum + fk_roll
            ik_sum = ik_roll if ik_sum is None else ik_sum + ik_roll
            twists.append(fk_sum * (1.0 - switch_plug) + ik_sum * switch_plug)
        shoulder_twist, elbow_twist, wrist_twist = twists

        deform = [collar_jnt]
        segments = (
            ("upArm", shoulder_jnt, elbow_jnt, shoulder_twist, elbow_twist),
            ("lowArm", elbow_jnt, hand_rig_jnt, elbow_twist, wrist_twist),
        )
        for label, start, end, start_twist, end_twist in segments:
            ribbon = tm.Ribbon.create(
                start,
                end,
                name=ctx.name(label),
                joint_count=self.ribbon_joints,
                controller_count=self.ribbon_controllers,
                scaleable=self.stretchy,
                parent=ctx.groups.scale,
            )
            ribbon.pin_start(start)
            ribbon.pin_end(end)
            start_twist >> ribbon.start_twist
            end_twist >> ribbon.end_twist
            for controller in ribbon.controllers:
                ctx.controllers.append(controller)
            deform.extend(ribbon.deformer_joints)
        deform.append(hand_jnt)
```

Update the module docstring's second line to: `Composes tik.maya constructs: ``IkFkChain`` for the blend, two pure-math ``Ribbon`` setups for the upper/lower arm (twist wired as floats), ``MatrixConstraint`` for wiring.`

- [ ] **Step 4: Run the integration suite, then everything**

Run: `$env:PYTHONPATH="D:\dev\tikworks\src\python"; & "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pytest tests/integration/trigger/test_arm_trigger.py -q`
Expected: `6 passed`.

Then: `$env:PYTHONPATH="D:\dev\tikworks\src\python"; & "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pytest tests/unit tests/integration -q`
Expected: all pass, no failures related to `Ribbon`, `follicle`, `nurbs` in ribbon context.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/modules/arm/arm.py tests/integration/trigger/test_arm_trigger.py
git commit -m "feat(tik.trigger.arm): wire IK/FK axial rotation floats into the pure-math ribbons"
```

---

## Self-review notes

- Spec coverage: §4.1 → Tasks 2–3; §4.2 → Tasks 4–5; §5 → Task 6; §6 validation → Tasks 1, 2, 4 (`ValueError`s, degree clamp); §7 tests → every task; Maya-2024 floor → Global Constraints.
- Names used consistently: `SplineOutput.twist/.transform/.weights/.nodes`, `MatrixSpline.outputs/.degree/.group/.delete`, `Ribbon.start_twist/.end_twist/.up_frame/.control_spline/.spline/.joint_group/.deformer_joints/.controllers/.scale_switch/.measure`, `pin_start/pin_end(node, maintain_offset=True)`.
- The arm module stays on the tik.maya API only (`Plug` operators, `>>`); no `cmds`.
