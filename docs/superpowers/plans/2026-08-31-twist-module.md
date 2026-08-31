# Twist Extractor and Twist Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable twist extractor to `tik/trigger/systems/` and a generic `twist` module that drives N joints from it, with per-guide authored weights that survive a `.trg` round trip.

**Architecture:** `systems/twist.py` exposes one function, `twist_plug()`, with two extraction sources — `matrix` (swing-twist decomposition, robust anywhere, bounded to ±180 by the matrix representation) and `channel` (reads an unbounded rotate channel, valid only when the reference is the driver's parent and the twist axis is innermost). The `twist` module places bind joints along a base→end segment, deriving each joint's position from its guide's projection onto that axis and its weight from an unclamped attribute on the guide. Carrying that attribute through the `.trg` requires a small additive framework change: a `guide_attrs` declaration on `Module` and an optional `attrs` key on the joint record.

**Tech Stack:** Python 3.10+, Maya 2026 (`mayapy`), `tik.maya` wrapper, `pytest`. No third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-08-31-twist-ribbon-limblock-design.md` (§2)

## Global Constraints

- Never call `maya.cmds` or `OpenMaya` directly outside `tik/tik.maya`; consume `tik.maya` (`import tik.maya as tm`). Inside `tik.maya` itself raw `cmds` is fine.
- `tik/trigger/core` is pure Python — no Maya, no Qt. Enforced by `tests/unit/test_import_boundaries.py`. `systems/` and `modules/` may use `tik.maya`.
- Modules never inherit from other modules; shared behaviour lives in `tik/trigger/systems/`.
- No third-party dependencies — stdlib and Maya-bundled modules only.
- Run tests with: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest <path> -q`
- Test naming for tik.trigger: `test_<module>_trigger.py`.
- Docstrings: Google style, as used throughout the repo.
- Commit after each task.

---

### Task 1: `twist_plug` — the matrix source

**Files:**
- Create: `src/python/tik/trigger/systems/twist.py`
- Test: `tests/unit/test_twist_trigger.py`

**Interfaces:**
- Consumes: `tik.maya` (`tm.create_node`, `tm.Transform`, `tm.Joint`).
- Produces: `twist_plug(driver, reference, *, name, axis="auto", source="auto") -> Plug` and `dominant_axis(node_a, node_b) -> tuple[str, int]`. Task 2 adds the `channel`/`auto` sources to the same function; Task 4 and the ribbon plan both call it.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_twist_trigger.py`:

```python
"""Tests for the twist extractor and the twist module."""

import tik.maya as tm
from tik.trigger.systems.twist import dominant_axis, twist_plug


def _pair(rest_rotation=(0.0, 0.0, 0.0)):
    """A reference transform and a child driver, optionally rested off-identity."""
    reference = tm.Transform.create(name="ref")
    driver = tm.Transform.create(name="drv", parent=reference.long_name)
    driver.translate = (5, 0, 0)
    driver.rotate = rest_rotation
    return reference, driver


def test_matrix_source_is_zero_at_rest():
    reference, driver = _pair(rest_rotation=(20.0, 15.0, -10.0))
    plug = twist_plug(driver, reference, name="fore", axis="X", source="matrix")
    assert abs(plug.value) < 1e-4


def test_matrix_source_tracks_the_driver():
    reference, driver = _pair()
    plug = twist_plug(driver, reference, name="fore", axis="X", source="matrix")
    for angle in (30.0, 90.0, 170.0, -170.0):
        driver.rotate = (angle, 0, 0)
        assert abs(plug.value - angle) < 1e-3


def test_matrix_source_ignores_swing():
    reference, driver = _pair()
    plug = twist_plug(driver, reference, name="fore", axis="X", source="matrix")
    driver.rotate = (120.0, 0, 0)
    baseline = plug.value
    for swing in (30.0, 60.0):
        driver.rotate = (120.0, swing, 0)
        assert abs(plug.value - baseline) < 1e-3


def test_matrix_source_wraps_past_180():
    """The documented bound. See spec section 2.1 -- a rotation matrix for 200
    degrees is identical to the matrix for -160, so no quaternion wiring can
    recover the difference. Asserted so nobody re-attempts the slerp trick.
    """
    reference, driver = _pair()
    plug = twist_plug(driver, reference, name="fore", axis="X", source="matrix")
    driver.rotate = (200.0, 0, 0)
    assert abs(plug.value - (-160.0)) < 1e-3


def test_dominant_axis_picks_the_chain_axis():
    start = tm.Transform.create(name="a")
    end = tm.Transform.create(name="b")
    end.translate = (7, 0, 0)
    assert dominant_axis(start, end)[0] == "X"
    end.translate = (0, 0, -7)
    axis, direction = dominant_axis(start, end)
    assert axis == "Z" and direction == -1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_twist_trigger.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.systems.twist'`

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/trigger/systems/twist.py`:

```python
"""Twist extraction: how much a driver rolls about one axis, in degrees.

Two sources, because they have genuinely different reach:

``matrix``
    Swing-twist decomposition of the driver's rotation relative to a
    reference. Works for any driver in any hierarchy, however it is
    constrained, and is **bounded to +/-180 about the rest pose**. That bound
    is a property of the representation, not of the wiring: the rotation
    matrix for 200 degrees is identical to the one for -160, and
    ``decomposeMatrix`` canonicalises the quaternion to the ``w >= 0``
    hemisphere, so the difference is gone before any quaternion node sees it.
    A ``quatSlerp`` half-angle trick was measured against Maya 2026 and does
    not recover it in any ``angleInterpolation`` mode.

``channel``
    Reads the driver's ``rotate<axis>`` channel directly. Genuinely unbounded
    -- a propeller or wheel winds past 360 without a pop -- but only correct
    when that channel *is* the roll relative to the reference.
"""

from __future__ import annotations

import logging
from typing import Optional

import tik.maya as tm

logger = logging.getLogger(__name__)

AXES = ("X", "Y", "Z")
SOURCES = ("auto", "matrix", "channel")
ROTATE_ORDER_XYZ = 0

#: Rotate order whose innermost (first applied) rotation is this axis, which
#: is what makes the matching rotate channel a pure roll about the bone axis.
_INNERMOST_ORDER = {"X": 0, "Y": 2, "Z": 4}  # xyz, yzx, zxy


def dominant_axis(node_a, node_b) -> tuple[str, int]:
    """Which local axis of ``node_a`` points at ``node_b``.

    Args:
        node_a: The node whose local axes are tested.
        node_b: The node it is assumed to aim at.

    Returns:
        ``(axis, direction)`` where axis is ``"X"``/``"Y"``/``"Z"`` and
        direction is ``1`` or ``-1``.
    """
    aim = node_b.world_position - node_a.world_position
    if aim.length() < 1e-6:
        return "X", 1
    aim.normalize()
    best, best_dot, best_sign = "X", -1.0, 1
    for axis in AXES:
        projection = node_a.world_axis(axis.lower()) * aim
        if abs(projection) > best_dot:
            best, best_dot = axis, abs(projection)
            best_sign = 1 if projection > 0 else -1
    return best, best_sign


def _channel_is_valid(driver, reference, axis: str) -> bool:
    """True when ``driver.rotate<axis>`` is the roll relative to ``reference``.

    Both conditions must hold: the reference must be the driver's parent, so
    the local channel is measured against the right frame; and the rotate
    order must apply this axis innermost, so the channel is a roll about the
    bone's own axis rather than one term of a composite rotation.
    """
    parent = driver.parent
    if parent is None or parent.long_name != reference.long_name:
        return False
    return driver["rotateOrder"].value == _INNERMOST_ORDER[axis]


def twist_plug(
    driver,
    reference,
    *,
    name: str,
    axis: str = "auto",
    source: str = "auto",
) -> "tm.core.plug.Plug":
    """A plug carrying ``driver``'s roll about ``axis``, relative to ``reference``.

    Args:
        driver: Transform whose roll is measured.
        reference: Transform the roll is measured against.
        name: Prefix for every created node.
        axis: ``"auto"``, ``"X"``, ``"Y"`` or ``"Z"``. ``"auto"`` picks the
            axis of ``reference`` pointing at ``driver``, resolved once in
            Python at build time.
        source: ``"auto"``, ``"matrix"`` or ``"channel"``. See the module
            docstring. ``"auto"`` uses ``channel`` when it is valid, which
            gives an FK-driven twist its unbounded range, and ``matrix``
            otherwise.

    Returns:
        A float plug in degrees, zero at the pose held when this was built.
    """
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, got {source!r}.")
    if axis == "auto":
        axis = dominant_axis(reference, driver)[0]
    axis = axis.upper()
    if axis not in AXES:
        raise ValueError(f"axis must be one of {AXES} or 'auto', got {axis!r}.")

    if source == "auto":
        source = "channel" if _channel_is_valid(driver, reference, axis) else "matrix"
        logger.debug("twist '%s': auto-selected the %s source", name, source)
    if source == "channel":
        return _channel_plug(driver, reference, axis, name)
    return _matrix_plug(driver, reference, axis, name)


def _channel_plug(driver, reference, axis: str, name: str):
    """The driver's own rotate channel, re-zeroed to the build pose."""
    if not _channel_is_valid(driver, reference, axis):
        raise ValueError(
            f"twist '{name}': the channel source needs '{driver.name}' parented to "
            f"'{reference.name}' with rotate order "
            f"{_INNERMOST_ORDER[axis]} so rotate{axis} is a pure roll."
        )
    channel = driver[f"rotate{axis}"]
    rest = channel.value
    if abs(rest) < 1e-9:
        return channel
    # Subtracting a constant keeps the plug unbounded, which is the whole
    # point of this source; re-referencing through a matrix would not.
    return channel - rest


def _matrix_plug(driver, reference, axis: str, name: str):
    """Swing-twist decomposition of driver-relative-to-reference."""
    mult = tm.create_node("multMatrix", name=f"{name}_twist_multMatrix")
    # matrixIn[0] * matrixIn[1] * matrixIn[2]  ->  rest^-1 * driver * ref^-1,
    # i.e. the delta expressed in the rest-local frame, so the twist axis
    # stays the segment's own axis in every pose.
    rest = driver.world_matrix() * reference.world_matrix().inverse()
    mult["matrixIn[0]"].value = list(rest.inverse())
    driver["worldMatrix[0]"] >> mult["matrixIn[1]"]
    reference["worldInverseMatrix[0]"] >> mult["matrixIn[2]"]

    decompose = tm.create_node("decomposeMatrix", name=f"{name}_twist_decomposeMatrix")
    mult["matrixSum"] >> decompose["inputMatrix"]

    # Feeding quatToEuler only the axis component and W is what isolates
    # twist from swing.
    to_euler = tm.create_node("quatToEuler", name=f"{name}_twist_quatToEuler")
    decompose[f"outputQuat{axis}"] >> to_euler[f"inputQuat{axis}"]
    decompose["outputQuatW"] >> to_euler["inputQuatW"]
    return to_euler[f"outputRotate{axis}"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_twist_trigger.py -q`

Expected: PASS (5 tests)

If `test_matrix_source_is_zero_at_rest` fails with a non-zero value, the `multMatrix` input order is inverted — swap so `matrixIn[0]` holds the baked inverse and the live plugs follow it.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/systems/twist.py tests/unit/test_twist_trigger.py
git commit -m "feat(tik.trigger): twist extraction with a matrix source"
```

---

### Task 2: the channel source and `auto` selection

**Files:**
- Modify: `src/python/tik/trigger/systems/twist.py` (already contains both paths from Task 1)
- Test: `tests/unit/test_twist_trigger.py`

**Interfaces:**
- Consumes: `twist_plug`, `_channel_is_valid` from Task 1.
- Produces: no new symbols; proves the `channel` and `auto` behaviour Task 4 relies on.

Task 1 wrote both code paths so the module reads as one piece. This task is the test coverage that proves the second path, and any fixes it forces.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_twist_trigger.py`:

```python
def test_channel_source_is_unbounded():
    reference, driver = _pair()
    driver["rotateOrder"].value = 0  # xyz -- X applied innermost
    plug = twist_plug(driver, reference, name="prop", axis="X", source="channel")
    previous = None
    for step in range(-80, 81):
        angle = step * 5.0
        driver.rotate = (angle, 0, 0)
        value = plug.value
        assert abs(value - angle) < 1e-3
        if previous is not None:
            assert abs(value - previous) < 10.0  # no wrap anywhere in +/-400
        previous = value


def test_channel_source_is_zero_at_rest():
    reference, driver = _pair(rest_rotation=(35.0, 0.0, 0.0))
    plug = twist_plug(driver, reference, name="prop", axis="X", source="channel")
    assert abs(plug.value) < 1e-4
    driver.rotate = (395.0, 0, 0)
    assert abs(plug.value - 360.0) < 1e-3


def test_auto_prefers_the_channel_when_valid():
    reference, driver = _pair()
    driver["rotateOrder"].value = 0
    plug = twist_plug(driver, reference, name="prop", axis="X", source="auto")
    driver.rotate = (400.0, 0, 0)
    assert abs(plug.value - 400.0) < 1e-3  # unbounded => the channel was used


def test_auto_falls_back_to_matrix_when_not_parented():
    reference = tm.Transform.create(name="ref")
    driver = tm.Transform.create(name="drv")  # not a child of reference
    driver.translate = (5, 0, 0)
    plug = twist_plug(driver, reference, name="fore", axis="X", source="auto")
    driver.rotate = (200.0, 0, 0)
    assert abs(plug.value - (-160.0)) < 1e-3  # bounded => the matrix was used


def test_auto_falls_back_to_matrix_on_a_bad_rotate_order():
    reference, driver = _pair()
    driver["rotateOrder"].value = 1  # yzx -- X is outermost, not a pure roll
    plug = twist_plug(driver, reference, name="fore", axis="X", source="auto")
    driver.rotate = (200.0, 0, 0)
    assert abs(plug.value - (-160.0)) < 1e-3


def test_channel_source_rejects_an_invalid_driver():
    import pytest

    reference = tm.Transform.create(name="ref")
    driver = tm.Transform.create(name="drv")
    with pytest.raises(ValueError, match="channel source"):
        twist_plug(driver, reference, name="bad", axis="X", source="channel")
```

- [ ] **Step 2: Run the tests**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_twist_trigger.py -q`

Expected: PASS (11 tests). If `test_channel_source_is_zero_at_rest` fails, `Plug.__sub__` may not exist — use `channel + (-rest)` instead.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_twist_trigger.py src/python/tik/trigger/systems/twist.py
git commit -m "test(tik.trigger): cover the channel and auto twist sources"
```

---

### Task 3: per-guide attributes (`guide_attrs`)

**Files:**
- Modify: `src/python/tik/trigger/core/manifest.py` (add `GuideAttr`)
- Modify: `src/python/tik/trigger/core/module.py` (add `guide_attrs`)
- Modify: `src/python/tik/trigger/core/__init__.py` (export `GuideAttr`)
- Modify: `src/python/tik/trigger/maya/rig.py` (`GuideDraft.joint` adds them)
- Modify: `src/python/tik/trigger/guides/format.py` (`make_record` gains `attrs`)
- Modify: `src/python/tik/trigger/guides/scene.py` (export and import them)
- Test: `tests/unit/test_guides_trigger.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `GuideAttr(name, default=0.0, keyable=True, help="")` (frozen dataclass in `core/manifest.py`, exported from `tik.trigger.core`) and `Module.guide_attrs: dict[str, tuple[GuideAttr, ...]]`. Task 4 declares `guide_attrs = {"twist": (GuideAttr("twistWeight"),)}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_guides_trigger.py`:

```python
def test_guide_attrs_round_trip(tmp_path):
    """A per-guide authored attribute survives export and import."""
    from tik.trigger.guides.format import GuideFile
    from tik.trigger.guides.scene import GuideScene
    from tik.trigger.core import registry

    scene = GuideScene()
    module_cls = registry.get_module("twist")
    instance = scene.create_guides(module_cls(name="fore"))
    guide = scene.guide_node(instance.instance_id, "twist", 0)
    guide["twistWeight"].value = -0.42

    records = scene.export_guide_records()
    path = tmp_path / "guides.trg"
    GuideFile(records).save(path)

    scene.delete_guides(instance.instance_id)
    reloaded = GuideFile.load(path)
    rebuilt = scene.import_guide_instances(reloaded.instances())[0]
    restored = scene.guide_node(rebuilt.instance_id, "twist", 0)
    assert abs(restored["twistWeight"].value - (-0.42)) < 1e-6


def test_record_without_attrs_still_imports():
    """Old .trg files carry no 'attrs' key and must keep loading."""
    from tik.trigger.guides.format import make_record

    record = make_record(
        name="a_guide", position=(0, 0, 0), rotation=(0, 0, 0),
        joint_orient=(0, 0, 0), parent=None, side="C", module="twist",
        role="twist", index=0, instance="abc123",
    )
    assert "attrs" not in record
    assert record.get("attrs", {}) == {}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_guides_trigger.py -q -k guide_attrs`

Expected: FAIL — the `twist` module is not registered yet (Task 4) and `twistWeight` does not exist. Mark both tests with `@pytest.mark.skip(reason="enabled by Task 4")` if you want a green suite between tasks; unskip in Task 4.

- [ ] **Step 3: Add `GuideAttr` to the manifest**

In `src/python/tik/trigger/core/manifest.py`, after the `Input` dataclass:

```python
@dataclass(frozen=True)
class GuideAttr:
    """A float attribute a module's guide carries, authored by the rigger.

    Guides normally round-trip through the ``.trg`` by world position alone.
    A module that needs per-guide *data* -- a twist weight, a falloff -- can
    declare it here and the guide layer will create, export and restore it.

    Args:
        name: Attribute long name, created on every guide of its role.
        default: Value written at draw time. ``draw_guides`` may overwrite it
            per guide.
        keyable: Whether it shows in the channel box.
        help: Tooltip text.
    """

    name: str
    default: float = 0.0
    keyable: bool = True
    help: str = ""
```

- [ ] **Step 4: Declare it on `Module`**

In `src/python/tik/trigger/core/module.py`, import `GuideAttr` alongside `GuideLayout, Input, instance_key`, and add the class attribute beside `guides`:

```python
    #: Per-guide authored attributes, keyed by guide role. Roles absent from
    #: the mapping carry none, so existing modules are unaffected.
    guide_attrs: dict[str, tuple[GuideAttr, ...]] = {}
```

Add this classmethod beside `output_names`:

```python
    @classmethod
    def attrs_for_role(cls, role: str) -> tuple[GuideAttr, ...]:
        """Declared per-guide attributes for ``role`` (empty when none)."""
        return tuple(cls.guide_attrs.get(role, ()))
```

Export `GuideAttr` from `src/python/tik/trigger/core/__init__.py`: add it to the `from .manifest import ...` line and to `__all__`.

- [ ] **Step 5: Create the attributes when drawing a guide**

In `src/python/tik/trigger/maya/rig.py`, inside `GuideDraft.joint`, after `joint.color = SIDE_COLORS[self.side]` and before `self.created[(role, index)] = joint`:

```python
        for declared in self.module.attrs_for_role(role):
            attribute.add_float(
                joint, declared.name, default=declared.default, keyable=declared.keyable
            )
```

`attribute` is already imported in that module.

- [ ] **Step 6: Carry them through the record**

In `src/python/tik/trigger/guides/format.py`, add a parameter to `make_record` after `color`:

```python
    attrs: Optional[dict] = None,
```

and before the `if settings is not None:` block:

```python
    if attrs:
        record["attrs"] = {key: float(value) for key, value in attrs.items()}
```

In `src/python/tik/trigger/guides/scene.py`, inside `export_guide_records`, build the values just before `records.append(make_record(...))`:

```python
                declared = module_cls.attrs_for_role(role)
                attrs = {item.name: node[item.name].value for item in declared}
```

and pass `attrs=attrs,` into the `make_record(...)` call.

In `import_guide_instances`, after `joint.color = record.get("color") or 17`:

```python
                    for item in module_cls.attrs_for_role(role):
                        plug = tm.attribute.add_float(
                            joint, item.name, default=item.default, keyable=item.keyable
                        )
                        plug.value = record.get("attrs", {}).get(item.name, item.default)
```

- [ ] **Step 7: Run the guide suite**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_guides_trigger.py tests/unit/test_core_trigger.py -q`

Expected: PASS, with the two new tests still skipped pending Task 4.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/core src/python/tik/trigger/maya/rig.py src/python/tik/trigger/guides tests/unit/test_guides_trigger.py
git commit -m "feat(tik.trigger): per-guide authored attributes via guide_attrs"
```

---

### Task 4: the `twist` module

**Files:**
- Create: `src/python/tik/trigger/modules/twist/twist.py`
- Modify: `tests/unit/test_guides_trigger.py` (unskip the two tests from Task 3)
- Test: `tests/unit/test_twist_trigger.py`

**Interfaces:**
- Consumes: `twist_plug` (Task 1/2), `GuideAttr` (Task 3), `rig.bind_joint` / `rig.guide` / `rig.chain` / `rig.socket` / `rig.output` from `ModuleRig`.
- Produces: a module registered as `"twist"` with outputs `twist0 … twistN-1`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_twist_trigger.py`:

```python
from tik.trigger.core import registry
from tik.trigger.modules.twist.twist import Twist


def test_twist_module_is_registered():
    assert registry.get_module("twist") is Twist


def test_output_names_follow_the_count():
    assert Twist.output_names({"count": 3}) == ("twist0", "twist1", "twist2")


def test_projected_position_ignores_sideways_drift():
    """A guide dragged off the axis still reads its along-axis fraction."""
    from tik.trigger.modules.twist.twist import projected_position

    start = tm.Transform.create(name="s")
    end = tm.Transform.create(name="e")
    end.translate = (10, 0, 0)
    probe = tm.Transform.create(name="p")
    probe.translate = (2.5, 6, -3)  # far off the axis
    assert abs(projected_position(start, end, probe) - 0.25) < 1e-6
    probe.translate = (-4, 0, 0)  # behind the start, clamped
    assert projected_position(start, end, probe) == 0.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_twist_trigger.py -q -k twist_module or projected`

Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.modules.twist'`

- [ ] **Step 3: Write the module**

Create `src/python/tik/trigger/modules/twist/twist.py`:

```python
"""Twist module: N joints rolling about one axis, driven by a segment's ends.

Generic, not a limb accessory. ``twist_source`` says *which end drives* the
roll; ``extraction`` says *how the angle is read*. Position and weight are
fully independent: position comes from where the guide sits along the
segment, weight from an unclamped attribute on that guide, so a joint at 0.95
may carry a weight of 0.2, or a negative weight to reverse the twist.
"""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import (
    BoolField,
    ChoiceField,
    GuideAttr,
    GuideLayout,
    Input,
    IntField,
    Module,
    register_module,
)
from tik.trigger.systems.twist import AXES, SOURCES, twist_plug

WEIGHT_ATTR = "twistWeight"


def projected_position(start, end, probe) -> float:
    """Where ``probe`` falls along ``start`` -> ``end``, as a 0-1 fraction.

    Only the component along the axis counts, so a guide dragged sideways for
    visibility still reads correctly.
    """
    axis = end.world_position - start.world_position
    length_squared = axis * axis
    if length_squared < 1e-12:
        return 0.0
    fraction = ((probe.world_position - start.world_position) * axis) / length_squared
    return max(0.0, min(1.0, fraction))


@register_module("twist")
class Twist(Module):
    """A strip of twist joints between two inputs."""

    label = "Twist"
    guides = GuideLayout("base", "end", multi="twist", min=1, max=20)
    inputs = (
        Input("base", primary=True, help="Segment start (upperarm, thigh, shaft)"),
        Input("end", help="Segment end (lowerarm, shin, hub)"),
        Input(
            "reference",
            optional=True,
            help="What a start-sourced twist is measured against; "
                 "defaults to the base joint's parent",
        ),
    )
    outputs = ("twist0",)
    guide_attrs = {
        "twist": (
            GuideAttr(
                WEIGHT_ATTR,
                help="How much of the extracted twist this joint takes. "
                     "Unclamped; negative reverses it.",
            ),
        )
    }

    count = IntField(3, min=1, max=20, help="Number of twist joints")
    twist_source = ChoiceField(
        "end", choices=("start", "end"), label="Twist Source",
        help="'end' follows the child (forearm); 'start' counters the "
             "segment's own roll (upper arm)",
    )
    axis = ChoiceField("auto", choices=("auto", *AXES))
    extraction = ChoiceField(
        "auto", choices=SOURCES,
        help="'channel' is unbounded but needs an FK-style driver; "
             "'matrix' works anywhere and wraps past 180 degrees",
    )
    distribute_translation = BoolField(
        True, help="Slide the joints along when the segment stretches"
    )
    spacing = IntField(10, min=1, help="Default guide distance from base to end")

    @classmethod
    def output_names(cls, settings=None):
        count = int((settings or {}).get("count", cls.count.default))
        return tuple(f"twist{index}" for index in range(count))

    def guide_count(self) -> int:
        return self.count

    # --------------------------------------------------------------- guides
    def draw_guides(self, guides) -> None:
        span = self.spacing * guides.side_mult
        base = guides.joint("base", (0, 0, 0))
        guides.joint("end", (span, 0, 0), parent=base)
        for index in range(self.count):
            fraction = (index + 1) / (self.count + 1)
            joint = guides.joint(
                "twist", (span * fraction, 0, 0), index=index, parent=base, radius=0.5
            )
            # The sensible default, freely overridable afterwards.
            weight = fraction if self.twist_source == "end" else 1.0 - fraction
            joint[WEIGHT_ATTR].value = weight

    # ---------------------------------------------------------------- build
    def build(self, rig) -> None:
        base_guide, end_guide = rig.guides("base", "end")
        twist_guides = rig.chain("twist")

        base_socket = rig.socket("base", match=base_guide)
        rig.socket("end", match=end_guide)  # materialised; read below

        end_socket = rig.socket("end")
        if self.twist_source == "end":
            driver, reference = end_socket, base_socket
        else:
            driver = base_socket
            reference = rig.attachments.get("reference") or base_socket.parent

        angle = twist_plug(
            driver,
            reference,
            name=rig.name("twist"),
            axis=self.axis,
            source=self.extraction,
        )
        resolved_axis = self.axis if self.axis != "auto" else _axis_of(angle)

        end_joint = rig.bind_parent
        for index, guide_node in enumerate(twist_guides):
            position = projected_position(base_guide, end_guide, guide_node)
            weight = guide_node[WEIGHT_ATTR].value
            joint = rig.bind_joint(
                f"twist{index}", parent=rig.bind_parent, match=guide_node, radius=0.5
            )
            joint["rotateOrder"].value = 0  # xyz -- roll innermost
            (angle * weight) >> joint[f"rotate{resolved_axis}"]
            if self.distribute_translation and end_joint is not None:
                for channel in "XYZ":
                    (end_joint[f"translate{channel}"] * position) >> joint[
                        f"translate{channel}"
                    ]
            rig.output(f"twist{index}", joint)


def _axis_of(plug) -> str:
    """Recover the axis letter from the plug the extractor returned."""
    return plug.name[-1].upper()
```

- [ ] **Step 4: Unskip the guide round-trip tests**

Remove the two `@pytest.mark.skip` decorators added in Task 3 Step 2.

- [ ] **Step 5: Run the tests**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_twist_trigger.py tests/unit/test_guides_trigger.py -q`

Expected: PASS. `distribute_translation` depends on `rig.bind_parent` being a real joint; when a module is built unconnected it is the module's `bind_grp`, which has no `translateX` carrying segment length — guard with the `end_joint is not None` check already present, and skip the wiring when `rig.bind_parent` is the bind group.

- [ ] **Step 6: Run the whole unit suite for regressions**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit -q`

Expected: PASS, no new failures. `test_import_boundaries.py` must still pass — `core/manifest.py` gained only a dataclass.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/modules/twist tests/unit
git commit -m "feat(tik.trigger): the twist module"
```
