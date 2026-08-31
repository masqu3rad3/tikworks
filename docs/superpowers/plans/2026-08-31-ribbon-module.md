# Ribbon Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `ribbon` trigger module wrapping the `tik.maya` `Ribbon` construct, and fix the layering violation inside that construct so its mid controllers become module-owned.

**Architecture:** `Ribbon` currently creates `Controller`s itself, which the animator-opinion rule forbids and which leaves those controllers untagged, uncoloured and outside `control_grp`. Mid controllers become *plugs* — the same vocabulary `start_plug` / `end_plug` already use — so the construct exposes `mid_frames` (the swinging frames) and `mid_plugs` (what the joint spline reads) and the module supplies real `rig.controller`s between them. The module keeps the ribbon in `rig_grp` as puppet and drives a separate set of real bind joints, so no world-space non-inheriting island lands in the bind hierarchy.

**Tech Stack:** Python 3.10+, Maya 2026 (`mayapy`), `tik.maya` wrapper, `pytest`. No third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-08-31-twist-ribbon-limblock-design.md` (§3)

## Global Constraints

- Never call `maya.cmds` or `OpenMaya` directly outside `tik/tik.maya`; consume `tik.maya`. Inside `tik.maya` raw `cmds` is fine.
- A `tik.maya` construct never creates a controller, names a user-facing attribute, or encodes a side convention. This plan exists to restore that.
- `tik/trigger/core` stays pure Python (no Maya, no Qt).
- No third-party dependencies.
- Run tests with: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest <path> -q`
- Commit after each task.

**Depends on:** `docs/superpowers/plans/2026-08-31-twist-module.md` Task 1 (`systems/twist.py`), used in Task 3 below.

---

### Task 1: mid controllers become plugs

**Files:**
- Modify: `src/python/tik/maya/constructs/ribbon.py`
- Test: `tests/unit/test_ribbon.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Ribbon.create(..., mid_count: int = 1, ...)`, `ribbon.mid_frames: list[Transform]`, `ribbon.mid_plugs: list[Transform]`, `ribbon.pin_mid(index, node, maintain_offset=True) -> MatrixConstraint`. The `controller_count` parameter and `ribbon.controllers` are gone. Task 2 consumes all of these.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_ribbon.py`, add:

```python
def test_ribbon_creates_no_controllers():
    """A tik.maya construct never creates a controller (animator-opinion rule)."""
    import inspect

    from tik.maya.constructs import ribbon as ribbon_module

    source = inspect.getsource(ribbon_module)
    assert "Controller" not in source
    assert "roles" not in source


def test_mid_plugs_and_frames_are_exposed():
    start, end = _ends()  # existing helper in this file
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=4, mid_count=2)
    assert len(ribbon.mid_plugs) == 2
    assert len(ribbon.mid_frames) == 2
    assert ribbon.mid_plugs[0].parent.long_name == ribbon.mid_frames[0].long_name


def test_pin_mid_drives_the_strip():
    start, end = _ends()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=5, mid_count=1)
    driver = tm.Transform.create(name="mid_driver")
    driver.snap_to(ribbon.mid_plugs[0])
    ribbon.pin_mid(0, driver)
    before = ribbon.deformer_joints[2].world_position
    driver.translate = (driver.translate[0], driver.translate[1] + 5.0, driver.translate[2])
    after = ribbon.deformer_joints[2].world_position
    assert (after - before).length() > 1e-3


def test_zero_mids_still_builds():
    start, end = _ends()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3, mid_count=0)
    assert ribbon.mid_plugs == []
    assert len(ribbon.deformer_joints) == 3
```

If `_ends()` does not exist in the file, add it mirroring the existing per-test setup:

```python
def _ends():
    start = tm.Transform.create(name="start")
    end = tm.Transform.create(name="end")
    end.translate = (10, 0, 0)
    return start, end
```

Then replace every existing `controller_count=` with `mid_count=` throughout the file, and any `ribbon.controllers` reference with `ribbon.mid_plugs`.

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_ribbon.py -q`

Expected: FAIL — `TypeError: create() got an unexpected keyword argument 'mid_count'`

- [ ] **Step 3: Rewrite the controller half of the construct**

In `src/python/tik/maya/constructs/ribbon.py`:

Delete the import `from ..roles.controller import Controller`.

In `__init__`, replace `self.controllers: list[Controller] = []` with:

```python
        self.mid_frames: list[Transform] = []
        self.mid_plugs: list[Transform] = []
```

In `create`, rename the parameter `controller_count: int = 1` to `mid_count: int = 1`, update its docstring line to:

```
            mid_count: Number of mid plugs between the ends. Pin a controller
                to each with ``pin_mid``; its frame is in ``mid_frames``.
```

and change the call `ribbon._create_controllers(controller_count, length)` to `ribbon._create_mids(mid_count)`. The `length` argument is no longer needed because nothing here sizes a control shape any more.

Replace `_create_controllers` wholesale:

```python
    def _create_mids(self, count: int) -> None:
        """Mid plugs on the control spline, for the caller to pin controllers to.

        The frame carries the interpolated twist so a controller parented to
        it rides the ribbon; the plug is the transform the joint spline reads,
        so pinning it is what lets the caller drive the strip.
        """
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
            output.transform["rotateOrder"].value = ROTATE_ORDER_XYZ
            output.twist >> output.transform["rotateX"]
            plug = Transform.create(
                name=f"{self.name}_mid{index}_plug", parent=output.transform.long_name
            )
            plug["rotateOrder"].value = ROTATE_ORDER_XYZ
            self.mid_frames.append(output.transform)
            self.mid_plugs.append(plug)
```

In `_mid_twists`, replace `zip(outputs, self.controllers)` with `zip(outputs, self.mid_plugs)` and the body's `controller.transform["rotateX"]` with `plug["rotateX"]`, renaming the loop variable:

```python
        for output, plug in zip(outputs, self.mid_plugs):
            twist = output.twist + plug["rotateX"]
```

In `_create_joints`, replace the drivers line:

```python
        drivers = [self.start_plug, *self.mid_plugs, self.end_plug]
```

Add `pin_mid` beside `pin_start` / `pin_end`:

```python
    @undo
    def pin_mid(self, index: int, node, maintain_offset: bool = True) -> MatrixConstraint:
        """Drive mid plug ``index`` from ``node`` (full TRS)."""
        return MatrixConstraint.create(
            node, self.mid_plugs[index], maintain_offset=maintain_offset,
            name=f"{self.name}_mid{index}Pin",
        )
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_ribbon.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/maya/constructs/ribbon.py tests/unit/test_ribbon.py
git commit -m "refactor(tik.maya): ribbon mid controllers become plugs"
```

---

### Task 2: the `ribbon` module

**Files:**
- Create: `src/python/tik/trigger/modules/ribbon/ribbon.py`
- Test: `tests/unit/test_ribbon_trigger.py`

**Interfaces:**
- Consumes: `Ribbon.create(..., mid_count=...)`, `mid_frames`, `mid_plugs`, `pin_start`, `pin_end` (Task 1); `ModuleRig.controller/bind_joint/socket/output`.
- Produces: a module registered as `"ribbon"` with outputs `joint0 … jointN-1`. Task 3 adds twist feeding.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ribbon_trigger.py`:

```python
"""Tests for the ribbon trigger module."""

import tik.maya as tm
from tik.trigger.core import registry
from tik.trigger.maya import tags
from tik.trigger.modules.ribbon.ribbon import RibbonModule


def test_ribbon_module_is_registered():
    assert registry.get_module("ribbon") is RibbonModule


def test_output_names_follow_the_joint_count():
    assert RibbonModule.output_names({"joint_count": 3}) == (
        "joint0", "joint1", "joint2",
    )
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_ribbon_trigger.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.modules.ribbon'`

- [ ] **Step 3: Write the module**

Create `src/python/tik/trigger/modules/ribbon/ribbon.py`:

```python
"""Ribbon module: a deforming strip between two inputs.

The ``Ribbon`` construct lives in ``rig_grp`` as puppet, because its joints
sit in a non-inheriting group holding world-space channel values -- correct
for the construct, wrong for a bind hierarchy that has to bake and export
under a moving rig root. Real bind joints are created under
``rig.bind_parent`` and constrained from it, the pattern ``_blend_to_bind``
already uses in ``systems/limb.py``.
"""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import (
    BoolField,
    FloatField,
    GuideLayout,
    Input,
    IntField,
    Module,
    register_module,
)


@register_module("ribbon")
class RibbonModule(Module):
    """A ribbon strip pinned between two inputs."""

    label = "Ribbon"
    guides = GuideLayout("start", "end")
    inputs = (
        Input("start", primary=True, help="What the ribbon start pins to"),
        Input("end", help="What the ribbon end pins to"),
        Input("reference", optional=True, help="Frame the start twist is read against"),
    )
    outputs = ("joint0",)

    joint_count = IntField(5, min=1, max=40, label="Joint Count")
    mid_count = IntField(1, min=0, max=10, label="Mid Controllers")
    degree = IntField(3, min=1, max=3)
    scaleable = BoolField(True, help="Stretch-driven scaleX on the deform joints")
    preserve_volume = BoolField(False, help="Counter-scale Y/Z by ratio ** -0.5")
    controller_size = FloatField(2.0, min=0.01, label="Controller Size")
    spacing = FloatField(10.0, min=0.01, help="Default distance between the guides")

    @classmethod
    def output_names(cls, settings=None):
        count = int((settings or {}).get("joint_count", cls.joint_count.default))
        return tuple(f"joint{index}" for index in range(count))

    # --------------------------------------------------------------- guides
    def draw_guides(self, guides) -> None:
        start = guides.joint("start", (0, 0, 0))
        guides.joint("end", (self.spacing * guides.side_mult, 0, 0), parent=start)

    # ---------------------------------------------------------------- build
    def build(self, rig) -> None:
        start_guide, end_guide = rig.guides("start", "end")
        start_socket = rig.socket("start", match=start_guide)
        end_socket = rig.socket("end", match=end_guide)

        ribbon = tm.Ribbon.create(
            start_guide,
            end_guide,
            name=rig.name("ribbon"),
            joint_count=self.joint_count,
            mid_count=self.mid_count,
            degree=self.degree,
            scaleable=self.scaleable,
            preserve_volume=self.preserve_volume,
            parent=rig.groups.rig,
        )
        ribbon.pin_start(start_socket)
        ribbon.pin_end(end_socket)

        # Controllers belong to the module: tagged, side-coloured, in
        # control_grp, with an offset group. The offset rides the swinging
        # frame, so the controller still travels with the ribbon.
        for index, frame in enumerate(ribbon.mid_frames):
            controller = rig.controller(
                f"mid{index}",
                shape="Circle",
                size=self.controller_size,
                match=frame,
                mirror="behaviour",
            )
            tm.MatrixConstraint.create(frame, controller.offset, maintain_offset=False)
            tm.MatrixConstraint.create(
                controller, ribbon.mid_plugs[index], maintain_offset=False
            )

        for index, ribbon_joint in enumerate(ribbon.deformer_joints):
            joint = rig.bind_joint(
                f"joint{index}", parent=rig.bind_parent, match=ribbon_joint
            )
            tm.MatrixConstraint.create(ribbon_joint, joint, maintain_offset=True)
            rig.output(f"joint{index}", joint)

        self._ribbon = ribbon  # kept for Task 3
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_ribbon_trigger.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/modules/ribbon tests/unit/test_ribbon_trigger.py
git commit -m "feat(tik.trigger): the ribbon module"
```

---

### Task 3: feed the ribbon's twist plugs

**Files:**
- Modify: `src/python/tik/trigger/modules/ribbon/ribbon.py`
- Test: `tests/unit/test_ribbon_trigger.py`

**Interfaces:**
- Consumes: `twist_plug(driver, reference, *, name, axis, source)` from the twist plan's Task 1.
- Produces: nothing new; wires `ribbon.start_twist` and `ribbon.end_twist`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_ribbon_trigger.py`:

```python
def test_twist_plugs_are_fed(scene):
    """start_twist and end_twist must have an incoming connection, not sit at 0."""
    from maya import cmds

    from tik.trigger.core import get_module
    from tik.trigger.core.schemas import ParentRef
    from tik.trigger.maya import Builder

    root = scene.create_guides(get_module("base")(name="body"))
    scene.create_guides(
        get_module("ribbon")(name="upper", side="L"),
        parent=ParentRef(root.instance_id, "root"),
    )
    Builder().build(rig_name="rbn", afterlife="keep")

    for suffix in ("start_plug", "end_plug"):
        found = cmds.ls(f"*_{suffix}")
        assert found, f"no {suffix} was built"
        assert cmds.listConnections(
            f"{found[0]}.twist", source=True, destination=False
        ), f"{found[0]}.twist has no driver"
```

This test uses the `scene` fixture and the `create_guides` + `Builder().build()`
pattern from `tests/unit/test_guide_scene_trigger.py`; import the fixture the
same way that file does (it is defined in that module's `conftest`/top matter —
copy the `scene` fixture definition into this file if it is not shared).

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_ribbon_trigger.py -q -k twist_plugs`

Expected: FAIL — no incoming connection.

- [ ] **Step 3: Wire the twist**

Add the import to `ribbon.py`:

```python
from tik.trigger.systems.twist import twist_plug
```

Add these fields beside the others:

```python
    twist = BoolField(True, help="Drive the ribbon twist from the pinned inputs")
```

and in `build`, after `ribbon.pin_end(end_socket)`:

```python
        if self.twist:
            # The construct exposes twist as bare float plugs; nothing feeds
            # them by default. The same extractor the twist module uses fills
            # them, so there is one implementation of swing-twist in the repo.
            reference = rig.attachments.get("reference") or start_socket.parent
            if reference is not None:
                twist_plug(
                    start_socket, reference, name=rig.name("startTwist")
                ) >> ribbon.start_twist
            twist_plug(
                end_socket, start_socket, name=rig.name("endTwist")
            ) >> ribbon.end_twist
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_ribbon_trigger.py tests/unit/test_ribbon.py -q`

Expected: PASS.

- [ ] **Step 5: Run the whole unit suite**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit -q`

Expected: PASS, no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/modules/ribbon tests/unit/test_ribbon_trigger.py
git commit -m "feat(tik.trigger): drive ribbon twist from the shared extractor"
```
