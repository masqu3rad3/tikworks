# Rig Scaffold and Master Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every Trigger rig one fixed scaffold (`rig_grp` > `trigger_grp` + `geo_grp`) ensured before every build and action, plus a `preferences_ctrl` for rig-wide switches and a `visibilities_ctrl` with one exclusive-tier enum per module.

**Architecture:** A new `tik/trigger/maya/scaffold.py` owns `ensure_rig()` and the `RigScaffold` dataclass. The builder and the runner both call it; `finalize` wires each built module's visibility attributes to the preferences and its tiered controller shapes to the visibilities enum. Tier is a build-time argument on `rig.controller`, tagged as `trg_tier`. Nothing enters the session document.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy` for every test), tik.maya wrappers (`tm.Transform`, `Plug`, `Controller`, meta tags). No third-party deps.

**Spec:** `docs/superpowers/specs/2026-09-05-rig-scaffold-and-master-controls-design.md`

## Global Constraints

- `tik/trigger/core` stays pure Python: no `maya`, no `tik.maya`, no Qt (`tests/unit/test_import_boundaries.py`).
- Code outside `tik.maya` consumes tik.maya; raw `cmds` in tik.trigger only where tik.maya has no wrapper (import/reference of files, `listRelatives` in tests).
- No backwards compatibility: `rig_name`, `ensure_rig_root` and `BuildReport.rig_root` are removed, not deprecated.
- Fixed names: `rig_grp`, `trigger_grp`, `geo_grp`, `preferences_ctrl`, `visibilities_ctrl`.
- Tiers: `TIERS = ("primary", "secondary", "tertiary")`; the enum on `visibilities_ctrl` is `primary / secondary / tertiary / all`, default `all` (index 3), exclusive.
- Tier wiring drives **shape** visibility, never transform visibility. Tweaks (`tier=None`) are neither tagged nor wired.
- Tests run as `mayapy -m pytest <path> -q` with `PYTHONPATH=src/python` (or `make tests-unit` / `make tests-integration`). Run the UI suite with `make tests-ui` where a task touches `guides/scene.py` or the stub.
- Commit after each task with the trailer:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_017gXwnrR9tFeTx3BYzjUhBV
  ```

## File Structure

| File | Responsibility |
|---|---|
| `src/python/tik/maya/core/plug.py` | (modify) `Plug.eq` comparison helper beside `gt` |
| `src/python/tik/trigger/core/manifest.py` | (modify) `TIERS` constant |
| `src/python/tik/trigger/core/__init__.py` | (modify) export `TIERS` |
| `src/python/tik/trigger/core/action.py` | (modify) `ActionContext.rig` |
| `src/python/tik/trigger/maya/tags.py` | (modify) new kinds and `TIER` key |
| `src/python/tik/trigger/maya/scaffold.py` | (create) `RigScaffold`, `ensure_rig`, fixed names, preference attribute table, `geo_grp` wiring |
| `src/python/tik/trigger/maya/build.py` | (modify) drop `ensure_rig_root`/`rig_name`; call `ensure_rig`; wire preferences and tiers in `finalize` |
| `src/python/tik/trigger/maya/rig.py` | (modify) `ModuleRig.scaffold`, `controller(tier=)`, `tweak_control` passes `tier=None` |
| `src/python/tik/trigger/maya/runner.py` | (modify) `ensure_rig()` before each step, `ctx.rig` |
| `src/python/tik/trigger/maya/__init__.py` | (modify) lazy exports |
| `src/python/tik/trigger/guides/scene.py` | (modify) `test_build` drops `rig_name` |
| `src/python/tik/trigger/actions/kinematics/kinematics.py` | (modify) drop `rig_name` |
| `src/python/tik/trigger/actions/import_asset/import_asset.py` | (modify) `parent_to_geo` |
| `tests/helpers/toy_modules.py` | (modify) `ToyTiers` module |
| `tests/unit/test_scaffold_trigger.py` | (create) `ensure_rig` on its own |
| `tests/unit/test_plug_math_helpers.py` | (modify) `eq` test |
| `tests/unit/test_runner_trigger.py` | (modify) `ctx.rig` tests |
| `tests/integration/trigger/test_builder_trigger.py` | (modify) wiring tests |
| `tests/integration/trigger/test_module_ground_rules.py` | (modify) tier enforcement |
| `tests/integration/trigger/test_session_build_trigger.py` | (modify) import-to-geo tests |
| existing tests listed in Task 3 | (modify) drop `rig_name`, assert fixed names |
| `CLAUDE.md`, `AI/coding_rules.md` | (modify) scaffold and tier rules |

---

### Task 1: `Plug.eq` comparison helper

The tier network needs "enum equals N". `Plug` has `gt`, `minimum`, `maximum` on a private `_condition`; add the public equality form next to them.

**Files:**
- Modify: `src/python/tik/maya/core/plug.py` (after `gt`, around line 1302)
- Test: `tests/unit/test_plug_math_helpers.py`

**Interfaces:**
- Produces: `Plug.eq(other, if_true, if_false) -> Plug` — returns a plug carrying `if_true` when `self == other` (condition operation 0), else `if_false`. `other`, `if_true`, `if_false` accept a `Plug` or a number, exactly like `gt`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_plug_math_helpers.py`:

```python
def test_eq_switches_branches():
    _node, plugs = _holder(a=2.0)
    result = plugs["a"].eq(2.0, 1.0, 0.0)
    assert abs(result.value - 1.0) < 1e-6
    plugs["a"].value = 3.0
    assert abs(result.value - 0.0) < 1e-6


def test_eq_result_can_be_nested():
    """The tier network nests: if all -> 1 else (if tier -> 1 else 0)."""
    _node, plugs = _holder(a=3.0)
    inner = plugs["a"].eq(1.0, 1.0, 0.0)
    outer = plugs["a"].eq(3.0, 1.0, inner)
    assert abs(outer.value - 1.0) < 1e-6
    plugs["a"].value = 1.0
    assert abs(outer.value - 1.0) < 1e-6
    plugs["a"].value = 2.0
    assert abs(outer.value - 0.0) < 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mayapy -m pytest tests/unit/test_plug_math_helpers.py -q -k eq`
Expected: FAIL with `AttributeError: 'Plug' object has no attribute 'eq'`

- [ ] **Step 3: Implement `eq`**

In `src/python/tik/maya/core/plug.py`, directly after the `gt` method:

```python
    def eq(self, other, if_true, if_false) -> "Plug":
        """Return ``if_true`` when ``self == other``, else ``if_false``.

        Args:
            other: Value compared against (Plug or numeric value).
            if_true: Result when the values are equal.
            if_false: Result otherwise.

        Returns:
            Plug: The selected value.
        """
        return self._condition(0, other, if_true, if_false)  # 0 = Equal
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mayapy -m pytest tests/unit/test_plug_math_helpers.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/maya/core/plug.py tests/unit/test_plug_math_helpers.py
git commit -m "tik.maya: Plug.eq comparison helper"
```

---

### Task 2: The scaffold module and `ensure_rig`

**Files:**
- Create: `src/python/tik/trigger/maya/scaffold.py`
- Modify: `src/python/tik/trigger/maya/tags.py`
- Modify: `src/python/tik/trigger/maya/__init__.py`
- Test: `tests/unit/test_scaffold_trigger.py`

**Interfaces:**
- Produces:
  - `tags.RIG_TRIGGER = "rig_trigger"`, `tags.RIG_GEO = "rig_geo"`, `tags.PREFERENCES = "preferences"`, `tags.VISIBILITIES = "visibilities"`, `tags.TIER = "trg_tier"`.
  - `scaffold.RIG_GRP = "rig_grp"`, `TRIGGER_GRP = "trigger_grp"`, `GEO_GRP = "geo_grp"`, `PREFERENCES_CTRL = "preferences_ctrl"`, `VISIBILITIES_CTRL = "visibilities_ctrl"`.
  - `scaffold.DISPLAY_MODES = ("normal", "template", "reference")`.
  - `scaffold.RigScaffold` dataclass with `root`, `trigger`, `geo` (`tm.Transform`) and `preferences`, `visibilities` (`Controller`).
  - `scaffold.ensure_rig(events=None) -> RigScaffold`, idempotent. `events` is an optional `EventBus`; adoption of an untagged node logs a warning through it.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_scaffold_trigger.py`:

```python
"""The rig scaffold: one fixed structure per scene, ensured and healed."""

import pytest
from maya import cmds

import tik.maya as tm
from tik.maya.roles.controller import Controller
from tik.trigger.core import EventBus
from tik.trigger.maya import scaffold, tags


@pytest.fixture(autouse=True)
def _fresh_scene():
    cmds.file(new=True, force=True)


PREFERENCE_DEFAULTS = {
    "cacheMode": 0,
    "controls": 1,
    "rig": 0,
    "rigDisplay": 0,
    "joints": 1,
    "jointsDisplay": 0,
    "geometry": 1,
    "geometryDisplay": 0,
}


def test_fresh_scene_gets_the_whole_scaffold():
    rig = scaffold.ensure_rig()
    assert rig.root.long_name == "|rig_grp"
    assert rig.trigger.long_name == "|rig_grp|trigger_grp"
    assert rig.geo.long_name == "|rig_grp|geo_grp"
    assert rig.preferences.transform.long_name == "|rig_grp|trigger_grp|preferences_ctrl"
    assert rig.visibilities.transform.long_name == "|rig_grp|trigger_grp|visibilities_ctrl"
    assert rig.root.meta[tags.KIND] == tags.RIG_ROOT
    assert rig.trigger.meta[tags.KIND] == tags.RIG_TRIGGER
    assert rig.geo.meta[tags.KIND] == tags.RIG_GEO
    assert rig.preferences.transform.meta[tags.KIND] == tags.PREFERENCES
    assert rig.visibilities.transform.meta[tags.KIND] == tags.VISIBILITIES
    assert Controller.is_controller(rig.preferences.transform)
    assert Controller.is_controller(rig.visibilities.transform)
    assert rig.preferences.shapes and rig.visibilities.shapes


def test_preference_attributes_exist_with_defaults():
    rig = scaffold.ensure_rig()
    node = rig.preferences.transform
    for name, default in PREFERENCE_DEFAULTS.items():
        plug = node[name]
        assert plug.exists(), name
        assert plug.value == default, name
        assert not plug.keyable, name
        assert plug.visible, name
    assert cmds.attributeQuery("rigDisplay", node=node.long_name, listEnum=True) == [
        "normal:template:reference"
    ]


def test_second_call_creates_nothing_and_keeps_values():
    first = scaffold.ensure_rig()
    first.preferences.transform["rig"].value = True
    first.preferences.transform["geometryDisplay"].value = 2
    before = set(cmds.ls(long=True))
    second = scaffold.ensure_rig()
    assert set(cmds.ls(long=True)) == before
    assert second.root.long_name == first.root.long_name
    assert second.preferences.transform["rig"].value is True
    assert second.preferences.transform["geometryDisplay"].value == 2


def test_untagged_rig_grp_is_adopted_with_a_warning():
    tm.Transform.create(name="rig_grp")
    logged = []
    events = EventBus()
    events.subscribe("log", lambda level="", message="", **_kw: logged.append((level, message)))
    rig = scaffold.ensure_rig(events)
    assert rig.root.long_name == "|rig_grp"
    assert len(cmds.ls("rig_grp")) == 1
    assert rig.root.meta[tags.KIND] == tags.RIG_ROOT
    assert any(level == "warning" and "rig_grp" in message for level, message in logged)


def test_missing_pieces_are_healed():
    rig = scaffold.ensure_rig()
    rig.geo.delete()
    rig.preferences.transform["joints"].delete()
    healed = scaffold.ensure_rig()
    assert healed.geo.long_name == "|rig_grp|geo_grp"
    assert healed.preferences.transform["joints"].value == 1


def test_group_channels_are_locked_and_hidden():
    rig = scaffold.ensure_rig()
    for group in (rig.root, rig.trigger, rig.geo):
        for channel in tm.TRANSFORM_CHANNELS:
            assert group[channel].locked, f"{group.name}.{channel}"
            assert not group[channel].visible, f"{group.name}.{channel}"


def test_geometry_preferences_drive_geo_grp():
    rig = scaffold.ensure_rig()
    prefs = rig.preferences.transform
    assert rig.geo.visibility
    prefs["geometry"].value = False
    assert not rig.geo.visibility
    assert rig.geo["overrideEnabled"].value
    prefs["geometryDisplay"].value = 2
    assert rig.geo["overrideDisplayType"].value == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mayapy -m pytest tests/unit/test_scaffold_trigger.py -q`
Expected: FAIL with `ImportError: cannot import name 'scaffold'` (or `AttributeError` on `tags.RIG_TRIGGER`).

- [ ] **Step 3: Add the tags**

In `src/python/tik/trigger/maya/tags.py`, update the kind comment and add after `OUTPUT_NAME`:

```python
TIER = "trg_tier"  # "primary" | "secondary" | "tertiary" - controllers only, never tweaks
```

and after `INPUT = "input"`:

```python
RIG_TRIGGER = "rig_trigger"  # trigger_grp: every module's top group hangs here
RIG_GEO = "rig_geo"  # geo_grp: imported geometry
PREFERENCES = "preferences"  # preferences_ctrl
VISIBILITIES = "visibilities"  # visibilities_ctrl
```

Update the comment on line 5 to list them: `# "guide" | "rig" | "deform" | "controller" | "output" | "input" | "rig_root" | "rig_trigger" | "rig_geo" | "preferences" | "visibilities"`.

- [ ] **Step 4: Write `scaffold.py`**

Create `src/python/tik/trigger/maya/scaffold.py`:

```python
"""The one scaffold every rig is built into, ensured before any build or action.

Spec: docs/superpowers/specs/2026-09-05-rig-scaffold-and-master-controls-design.md

A scene holds one rig and it has no name: the scaffold is addressed by fixed
names and confirmed by tags. ``ensure_rig`` is idempotent and heals -- a node
found by name but untagged is adopted, a missing node or attribute is created,
and the values of attributes already present are left alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from maya import cmds

import tik.maya as tm
from tik.maya.roles.controller import Controller

from . import tags

RIG_GRP = "rig_grp"
TRIGGER_GRP = "trigger_grp"
GEO_GRP = "geo_grp"
PREFERENCES_CTRL = "preferences_ctrl"
VISIBILITIES_CTRL = "visibilities_ctrl"

DISPLAY_MODES = ("normal", "template", "reference")  # == overrideDisplayType 0/1/2

#: (name, attr_type, default, kwargs) in channel-box order. A separator row
#: is inserted before "rig" so the three display pairs read as one block.
PREFERENCE_ATTRS = (
    ("cacheMode", "bool", False, {}),
    ("controls", "bool", True, {}),
    ("rig", "bool", False, {}),
    ("rigDisplay", "enum", 0, {"items": list(DISPLAY_MODES)}),
    ("joints", "bool", True, {}),
    ("jointsDisplay", "enum", 0, {"items": list(DISPLAY_MODES)}),
    ("geometry", "bool", True, {}),
    ("geometryDisplay", "enum", 0, {"items": list(DISPLAY_MODES)}),
)
DISPLAY_SEPARATOR = "display_"


@dataclass
class RigScaffold:
    """The fixed nodes of the one rig in the scene."""

    root: Any  # rig_grp
    trigger: Any  # trigger_grp
    geo: Any  # geo_grp
    preferences: Controller
    visibilities: Controller


def _log(events, message: str, level: str = "warning") -> None:
    if events is not None:
        events.log(message, level=level)


def _ensure_group(name: str, parent, kind: str, events) -> tm.Transform:
    """The transform ``name`` under ``parent`` (None = world), tagged ``kind``."""
    path = f"{parent.long_name}|{name}" if parent is not None else f"|{name}"
    if cmds.objExists(path):
        node = tm.Transform(path)
        if node.meta.get(tags.KIND) != kind:
            _log(events, f"Adopted existing '{name}' as the rig's {kind}.")
            node.meta[tags.KIND] = kind
    else:
        node = tm.Transform.create(
            name=name, parent=parent.long_name if parent is not None else None
        )
        node.meta[tags.KIND] = kind
    for channel in tm.TRANSFORM_CHANNELS:
        plug = node[channel]
        plug.locked = True
        plug.visible = False
    return node


def _ensure_control(name: str, parent, kind: str, shape: str, events) -> Controller:
    """The controller ``name`` under ``parent``, tagged ``kind``."""
    path = f"{parent.long_name}|{name}"
    if cmds.objExists(path):
        node = tm.Transform(path)
        if not Controller.is_controller(node):
            _log(events, f"Adopted existing '{name}' as the rig's {kind} control.")
            control = Controller(node)
            control._tag_as_controller()
            control.set_shape(shape, size=1.0)
        else:
            control = Controller(node)
        if node.meta.get(tags.KIND) != kind:
            node.meta[tags.KIND] = kind
        return control
    control = Controller.create(name=name, shape=shape, size=1.0, parent=parent.long_name)
    control.transform.meta[tags.KIND] = kind
    for channel in tm.TRANSFORM_CHANNELS:
        plug = control.transform[channel]
        plug.locked = True
        plug.visible = False
    return control


def _ensure_preference_attrs(control: Controller) -> None:
    """Add any preference attribute that is missing; leave present ones alone."""
    node = control.transform
    for name, attr_type, default, kwargs in PREFERENCE_ATTRS:
        if name == "rig" and not node[DISPLAY_SEPARATOR].exists():
            row = node[DISPLAY_SEPARATOR].create(
                "enum", items=["----------"], keyable=False
            )
            row.visible = True
            row.locked = True
        plug = node[name]
        if plug.exists():
            continue
        plug.create(attr_type, default=default, keyable=False, **kwargs)
        plug.visible = True


def _wire_geo(control: Controller, geo) -> None:
    """geometry -> geo_grp.visibility, geometryDisplay -> its override type."""
    prefs = control.transform
    if not geo["visibility"].get_input():
        prefs["geometry"] >> geo["visibility"]
    geo["overrideEnabled"].value = True
    if not geo["overrideDisplayType"].get_input():
        prefs["geometryDisplay"] >> geo["overrideDisplayType"]


def ensure_rig(events: Optional[Any] = None) -> RigScaffold:
    """The scaffold, created or healed. Safe to call before every step."""
    root = _ensure_group(RIG_GRP, None, tags.RIG_ROOT, events)
    trigger = _ensure_group(TRIGGER_GRP, root, tags.RIG_TRIGGER, events)
    geo = _ensure_group(GEO_GRP, root, tags.RIG_GEO, events)
    preferences = _ensure_control(
        PREFERENCES_CTRL, trigger, tags.PREFERENCES, "Settings", events
    )
    visibilities = _ensure_control(
        VISIBILITIES_CTRL, trigger, tags.VISIBILITIES, "Cog", events
    )
    _ensure_preference_attrs(preferences)
    _wire_geo(preferences, geo)
    return RigScaffold(
        root=root,
        trigger=trigger,
        geo=geo,
        preferences=preferences,
        visibilities=visibilities,
    )


def find_rig() -> Optional[RigScaffold]:
    """The scaffold if the scene has one, without creating anything."""
    if not cmds.objExists(f"|{RIG_GRP}|{TRIGGER_GRP}|{PREFERENCES_CTRL}"):
        return None
    return ensure_rig()
```

Notes for the implementer:
- `Plug.get_input()` returns the incoming plug or `None`; check `src/python/tik/maya/core/plug.py:396` for the exact signature before relying on the truthiness test, and adjust if it returns a list.
- `Controller.create(parent=...)` forwards to `Transform.create` which accepts a parent path.
- If the `Settings` / `Cog` shapes fail to load in the test scene (the shape library reads `src/python/tik/maya/data/control_shapes`), the test `assert rig.preferences.shapes` will fail; fall back to `"Circle"` only if the library really lacks them.

- [ ] **Step 5: Export from the package**

In `src/python/tik/trigger/maya/__init__.py`, add to `_LAZY`:

```python
    "RigScaffold": ".scaffold",
    "ensure_rig": ".scaffold",
    "find_rig": ".scaffold",
```

and in `__getattr__`, allow the submodule name like `tags`:

```python
    if name in ("tags", "scaffold"):
        return importlib.import_module(f".{name}", __name__)
```

Add `"scaffold"` to `__all__`: `__all__ = ["tags", "scaffold", *sorted(_LAZY)]`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `mayapy -m pytest tests/unit/test_scaffold_trigger.py -q`
Expected: 7 PASS. If `test_preference_attributes_exist_with_defaults` fails on `plug.value == default` for the bool attributes (Maya returns `False`/`True`), compare with `==` as written; `0 == False` holds.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/maya/scaffold.py src/python/tik/trigger/maya/tags.py src/python/tik/trigger/maya/__init__.py tests/unit/test_scaffold_trigger.py
git commit -m "trigger: rig scaffold with preferences and visibilities controls"
```

---

### Task 3: Builder builds into the scaffold; `rig_name` is gone

Mechanical but wide: replace `ensure_rig_root` with `ensure_rig`, drop `rig_name` everywhere, and point every test at the fixed names.

**Files:**
- Modify: `src/python/tik/trigger/maya/build.py`
- Modify: `src/python/tik/trigger/maya/rig.py` (`ModuleRig.__init__`)
- Modify: `src/python/tik/trigger/maya/__init__.py` (drop `ensure_rig_root` export)
- Modify: `src/python/tik/trigger/guides/scene.py:712-728` (`test_build`)
- Modify: `src/python/tik/trigger/actions/kinematics/kinematics.py`
- Modify: `tests/ui/stub.py:592`
- Modify tests: `tests/integration/trigger/conftest.py`, `test_arm_trigger.py`, `test_builder_trigger.py`, `test_draw_sync_trigger.py`, `test_module_ground_rules.py`, `test_session_build_trigger.py`, `test_session_guides_build_trigger.py`, `test_twist_ribbon_limblock.py`, `tests/unit/test_connections_trigger.py`, `tests/unit/test_guide_scene_trigger.py`

**Interfaces:**
- Consumes: `scaffold.ensure_rig(events)`, `RigScaffold`.
- Produces:
  - `Builder.build(scope="scene", afterlife="delete", document=None) -> BuildReport` (no `rig_name`).
  - `BuildReport.scaffold: RigScaffold` (replaces `rig_root`).
  - `build_context(module, instance, scaffold, bind_parent=None) -> ModuleRig`.
  - `ModuleRig(module, instance, scaffold, guide_nodes, bind_parent=None)`; `rig.scaffold` is the `RigScaffold`, `rig.rig_root` is `scaffold.trigger`.
  - `GuideScene.test_build(*handles)`.

- [ ] **Step 1: Write the failing test**

In `tests/integration/trigger/test_builder_trigger.py`, add after `test_builds_in_order_and_connects`:

```python
def test_modules_build_under_the_scaffold(pair):
    scene, body, tail = pair
    report = Builder().build(document=scene.document, afterlife="keep")
    assert report.scaffold.trigger.long_name == "|rig_grp|trigger_grp"
    for ctx in report.rigs.values():
        assert ctx.groups.limb.parent.long_name == "|rig_grp|trigger_grp"
        assert ctx.rig_root.long_name == "|rig_grp|trigger_grp"
        assert ctx.scaffold is report.scaffold
    # a second build reuses the same scaffold rather than making another
    Builder().build(document=scene.document, afterlife="keep")
    assert len(cmds.ls("rig_grp")) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mayapy -m pytest tests/integration/trigger/test_builder_trigger.py -q -k scaffold`
Expected: FAIL with `AttributeError: 'BuildReport' object has no attribute 'scaffold'`

- [ ] **Step 3: Update `build.py`**

Replace `ensure_rig_root` and the `rig_root` field:

```python
from .scaffold import RigScaffold, ensure_rig
```

In `BuildReport`, replace `rig_root: Any = None` with `scaffold: Any = None  # RigScaffold`.

Replace `build_context`:

```python
def build_context(module, instance, scaffold: RigScaffold, bind_parent=None) -> ModuleRig:
    """The object a module builds through, wired to its guides."""
    return ModuleRig(
        module,
        instance,
        scaffold,
        guide_nodes.guide_nodes(instance.instance_id),
        bind_parent,
    )
```

Delete `ensure_rig_root` entirely.

In `Builder.build`, change the signature to `def build(self, scope: Any = "scene", afterlife: str = "delete", document=None) -> BuildReport:` and the docstring to `"""Build every guide instance in ``scope`` into the scene's one rig."""`. Replace the undo chunk label and the root line:

```python
        with guide_nodes.undo_chunk("Trigger build"):
            report.scaffold = ensure_rig(self.events)
```

Replace `ctx = self._build_one(instance, report.rig_root, bind_parent)` with `ctx = self._build_one(instance, report.scaffold, bind_parent)`, and `_build_one(self, instance, rig_root, bind_parent=None)` with `_build_one(self, instance, scaffold, bind_parent=None)` whose body calls `build_context(module, instance, scaffold, bind_parent)`. The final log line becomes `self.events.log(f"Built {total} module(s).")`.

- [ ] **Step 4: Update `ModuleRig.__init__`**

In `src/python/tik/trigger/maya/rig.py`:

```python
    def __init__(
        self,
        module,
        instance: ModuleInstance,
        scaffold,
        guide_nodes: dict,
        bind_parent=None,
    ) -> None:
        self.module = module
        self.instance = instance
        self.side = module.side
        self.side_mult = module.side.multiplier
        self.scaffold = scaffold
        # trigger_grp: the world-space anchor every module hangs under
        self.rig_root = scaffold.trigger
```

(keep the rest of the body unchanged). Update the `_LAZY` table in `maya/__init__.py`: remove `"ensure_rig_root": ".build"`.

- [ ] **Step 5: Drop `rig_name` from Kinematics and `test_build`**

`kinematics.py`: delete the `rig_name = StringField("trigger", label="Rig name")` line and the `rig_name=self.rig_name,` argument. Remove `StringField` from the import if nothing else uses it. Change the final log to `ctx.log(f"Kinematics built {report.count} module(s) from {source}.")` (unchanged text, no name).

`guides/scene.py`: `def test_build(self, *handles: GuideHandle) -> Any:` and `return Builder(self.events).build(scope=scope, document=self.document, afterlife="keep")`.

`tests/ui/stub.py:592`: `def test_build(self, *handles):`.

- [ ] **Step 6: Update the tests**

Apply these edits:

- `tests/integration/trigger/conftest.py`: replace `from tik.trigger.maya import build` with `from tik.trigger.maya import build, scaffold as scaffold_module`; in `_make`, replace `rig_root = build.ensure_rig_root("test")` with `rig = scaffold_module.ensure_rig()` and `return build.build_context(built, instance, rig)`.
- Every `Builder().build(... rig_name="...", ...)` and `Builder(events).build(...)` call in `test_arm_trigger.py`, `test_builder_trigger.py`, `test_draw_sync_trigger.py`, `test_module_ground_rules.py`, `test_twist_ribbon_limblock.py`, `tests/unit/test_connections_trigger.py`, `tests/unit/test_guide_scene_trigger.py`: delete the `rig_name=...` argument.
- Every `session.add("kinematics", rig_name="...")` / `rig.add("kinematics", ..., rig_name="...")` in `test_session_build_trigger.py` and `test_session_guides_build_trigger.py`: delete the `rig_name` keyword.
- Assertions on names:
  - `test_session_build_trigger.py`: `cmds.objExists("hero_rig")` → `cmds.objExists("rig_grp")`; `len(cmds.ls("hero_rig")) == 1` → `len(cmds.ls("rig_grp")) == 1`; `cmds.objExists("fromsession_rig")` → `cmds.objExists("rig_grp")`.
  - `test_session_guides_build_trigger.py`: every `cmds.objExists("hero_rig")` → `cmds.objExists("rig_grp")`; `any("hero_rig" in name for name in built)` → `any("|rig_grp|trigger_grp|" in name for name in built)`.
  - `tests/unit/test_guide_scene_trigger.py:119`: `cmds.objExists("hero_rig")` → `cmds.objExists("rig_grp")`; line 151: `assert cmds.objExists("a_rig") and cmds.objExists("b_rig")` → `assert len(cmds.ls("rig_grp")) == 1`.
  - `test_module_ground_rules.py::test_module_parents_everything_it_creates`: `{"|rules_rig", "|trigger_modules_grp"}` → `{"|rig_grp", "|trigger_modules_grp"}`.

Use `rg -n "rig_name|_rig\"|ensure_rig_root|rig_root" tests src` afterwards; only `limb_lock.py` (`rig.rig_root`) and the builder test above may still mention `rig_root`.

- [ ] **Step 7: Run the suites**

Run: `mayapy -m pytest tests/unit -q` then `mayapy -m pytest tests/integration -q`, then `make tests-ui`.
Expected: all PASS. A failure mentioning `rig_name` is a missed call site from Step 6.

- [ ] **Step 8: Commit**

```bash
git add -A src/python/tik/trigger tests
git commit -m "trigger: build into the fixed scaffold; drop rig_name"
```

---

### Task 4: Preferences drive every module's groups

**Files:**
- Modify: `src/python/tik/trigger/maya/build.py` (`finalize`)
- Test: `tests/integration/trigger/test_builder_trigger.py`

**Interfaces:**
- Consumes: `rig.scaffold.preferences` (Task 3), `rig.groups` (`RigGroups`).
- Produces: `build.wire_preferences(rig) -> None`, called from `finalize`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_builder_trigger.py`:

```python
def test_preferences_drive_module_visibility(pair):
    scene, body, tail = pair
    report = Builder().build(document=scene.document, afterlife="keep")
    prefs = report.scaffold.preferences.transform
    groups = [ctx.groups for ctx in report.rigs.values()]
    assert all(group.control.visibility for group in groups)
    prefs["controls"].value = False
    assert not any(group.control.visibility for group in groups)
    assert not any(group.rig.visibility for group in groups)  # default off
    prefs["rig"].value = True
    assert all(group.rig.visibility for group in groups)
    prefs["joints"].value = False
    assert not any(group.bind.visibility for group in groups)
    # the module-level switches are now owned by the preferences
    for group in groups:
        for attr in ("controlVisibility", "rigVisibility", "bindVisibility"):
            assert group.limb[attr].locked, f"{group.limb.name}.{attr}"


def test_preferences_drive_module_display_mode(pair):
    scene, body, tail = pair
    report = Builder().build(document=scene.document, afterlife="keep")
    prefs = report.scaffold.preferences.transform
    for ctx in report.rigs.values():
        assert ctx.groups.rig["overrideEnabled"].value
        assert ctx.groups.bind["overrideEnabled"].value
    prefs["rigDisplay"].value = 1
    prefs["jointsDisplay"].value = 2
    for ctx in report.rigs.values():
        assert ctx.groups.rig["overrideDisplayType"].value == 1
        assert ctx.groups.bind["overrideDisplayType"].value == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mayapy -m pytest tests/integration/trigger/test_builder_trigger.py -q -k preferences`
Expected: FAIL at `prefs["controls"].value = False` → `assert not any(...)` (groups still visible).

- [ ] **Step 3: Implement `wire_preferences`**

In `src/python/tik/trigger/maya/build.py`, add above `finalize`:

```python
def wire_preferences(rig) -> None:
    """Hand the module's visibility switches to the rig-wide preferences.

    The limb group keeps its three attributes so a module stays testable on
    its own; once built into a rig, the preferences drive them and they lock.
    """
    prefs = rig.scaffold.preferences.transform
    limb = rig.groups.limb
    for pref, attr in (
        ("controls", "controlVisibility"),
        ("rig", "rigVisibility"),
        ("joints", "bindVisibility"),
    ):
        plug = limb[attr]
        prefs[pref] >> plug
        plug.locked = True
    for pref, group in (("rigDisplay", rig.groups.rig), ("jointsDisplay", rig.groups.bind)):
        group["overrideEnabled"].value = True
        prefs[pref] >> group["overrideDisplayType"]
```

and call it as the first line of `finalize(rig)`:

```python
def finalize(rig) -> None:
    """Tag a built module's outputs and sockets, and wire it to the scaffold."""
    wire_preferences(rig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mayapy -m pytest tests/integration/trigger/test_builder_trigger.py tests/integration/trigger/test_module_ground_rules.py -q`
Expected: PASS. If `test_module_builds_without_a_cycle` or the limb-lock tests regress, the override connection is the suspect: confirm `prefs[pref] >> group["overrideDisplayType"]` connects enum to enum (Maya allows it) and nothing else changed.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/maya/build.py tests/integration/trigger/test_builder_trigger.py
git commit -m "trigger: preferences control drives module visibility and display"
```

---

### Task 5: Control tiers and the visibilities control

**Files:**
- Modify: `src/python/tik/trigger/core/manifest.py` (`TIERS`)
- Modify: `src/python/tik/trigger/core/__init__.py` (export)
- Modify: `src/python/tik/trigger/maya/rig.py` (`controller(tier=)`, `tweak_control`)
- Modify: `src/python/tik/trigger/maya/build.py` (`wire_tiers`, `finalize`)
- Modify: `tests/helpers/toy_modules.py` (`ToyTiers`)
- Test: `tests/integration/trigger/test_builder_trigger.py`, `tests/unit/test_guide_scene_trigger.py`, `tests/integration/trigger/test_module_ground_rules.py`

**Interfaces:**
- Consumes: `Plug.eq` (Task 1), `rig.scaffold.visibilities` (Task 3).
- Produces:
  - `tik.trigger.core.TIERS == ("primary", "secondary", "tertiary")`.
  - `ModuleRig.controller(name, *, ..., tier: Optional[str] = "primary")`; `tier=None` means untiered (tweaks). Raises `GuideError` for an unknown tier. Tags `tags.TIER` on tiered controllers.
  - `build.wire_tiers(rig) -> None`: adds/reuses the enum `<instance key>` on `visibilities_ctrl` (items `primary:secondary:tertiary:all`, default 3) when the module built at least one tiered controller, and drives every shape of every tiered controller.
  - `build.tier_attr_name(key) -> str`: the enum name (`re.sub(r"\W", "_", key)`).

- [ ] **Step 1: Write the failing tests**

In `tests/helpers/toy_modules.py`, add:

```python
class ToyTiers(Module):
    """One controller per tier, plus a tweak, for the visibility tests."""

    label = "Toy Tiers"
    sided = False
    guides = GuideLayout("root")
    inputs = ()
    outputs = ("root",)
    controls = ("primary", "secondary", "tertiary")

    def draw_guides(self, guides):
        guides.joint("root", (0, 0, 0))

    def build(self, rig):
        main = rig.controller("primary", tier="primary")
        rig.controller("secondary", tier="secondary")
        rig.controller("tertiary", tier="tertiary")
        rig.tweak_control(main)
        joint = rig.bind_joint("root", match=rig.guide("root"))
        rig.output("root", joint)
```

In `tests/unit/test_guide_scene_trigger.py`, after the tweak tests:

```python
# ---------------------------------------------------------------- tiers
def test_controller_defaults_to_primary_tier(scene):
    ctx = _built(scene)
    control = ctx.controller("hand", mirror="world")
    assert control.transform.meta[tags.TIER] == "primary"


def test_controller_accepts_a_tier_and_rejects_unknown_ones(scene):
    ctx = _built(scene)
    control = ctx.controller("hand", mirror="world", tier="secondary")
    assert control.transform.meta[tags.TIER] == "secondary"
    with pytest.raises(trigger.TriggerError):
        ctx.controller("other", mirror="world", tier="quaternary")


def test_tweaks_carry_no_tier(scene):
    ctx = _built(scene)
    main = ctx.controller("hand", mirror="world")
    tweak = ctx.tweak_control(main)
    assert tags.TIER not in tweak.transform.meta
```

In `tests/integration/trigger/test_builder_trigger.py`, add the registration of `ToyTiers` next to the other toys (mirror how `ToyRoot`/`ToyChain` are registered in the module's fixture: `register_module("toy_tiers")(ToyTiers)` and `unregister_module("toy_tiers")` on teardown; import it as `from tests.helpers.toy_modules import ToyTiers` or copy the class into the test file if the helpers package is not importable there — check how `tests/ui` imports it) and append:

```python
def _shape_visible(controller):
    return [shape.visibility for shape in controller.transform.shapes]


def test_visibilities_control_has_one_enum_per_module_with_controls(scene):
    scene.add("toy_tiers", side="C", name="tiers")
    body = scene.add("toy_root", side="C", name="body")
    report = Builder().build(document=scene.document, afterlife="keep")
    vis = report.scaffold.visibilities.transform
    assert vis["tiers"].exists() and vis["body"].exists()
    assert cmds.attributeQuery("tiers", node=vis.long_name, listEnum=True) == [
        "primary:secondary:tertiary:all"
    ]
    assert vis["tiers"].value == 3
    assert not vis["tiers"].keyable and vis["tiers"].visible


def test_tiers_are_exclusive_and_all_shows_everything(scene):
    handle = scene.add("toy_tiers", side="C", name="tiers")
    report = Builder().build(document=scene.document, afterlife="keep")
    ctx = report.rigs[handle.instance_id]
    vis = report.scaffold.visibilities.transform["tiers"]
    by_tier = {
        controller.transform.meta[tags.TIER]: controller
        for controller in ctx.controllers
        if tags.TIER in controller.transform.meta
    }
    assert set(by_tier) == {"primary", "secondary", "tertiary"}
    for index, tier in enumerate(("primary", "secondary", "tertiary")):
        vis.value = index
        for other, controller in by_tier.items():
            expected = other == tier
            assert all(state == expected for state in _shape_visible(controller)), (
                f"{other} at enum={tier}"
            )
    vis.value = 3
    for controller in by_tier.values():
        assert all(_shape_visible(controller))


def test_tier_enum_hides_shapes_not_transforms(scene):
    handle = scene.add("toy_tiers", side="C", name="tiers")
    report = Builder().build(document=scene.document, afterlife="keep")
    ctx = report.rigs[handle.instance_id]
    report.scaffold.visibilities.transform["tiers"].value = 1  # secondary only
    primary = ctx.controller_by_role("primary")
    assert primary.transform.visibility
    assert not any(_shape_visible(primary))


def test_tweak_shapes_ignore_the_tier_enum(scene):
    handle = scene.add("toy_tiers", side="C", name="tiers")
    report = Builder().build(document=scene.document, afterlife="keep")
    ctx = report.rigs[handle.instance_id]
    tweak = ctx.controller_by_role("primary_tweak")
    report.scaffold.visibilities.transform["tiers"].value = 1
    assert all(_shape_visible(tweak))
    # the tweak's own switch is untouched
    ctx.controller_by_role("primary").transform["tweakVis"].value = True
    assert tweak.transform.visibility


def test_module_without_controls_adds_no_enum(scene):
    body = scene.add("base", side="C", name="body")
    scene.add("twist", side="L", name="twist", parent=body)
    report = Builder().build(document=scene.document, afterlife="keep")
    vis = report.scaffold.visibilities.transform
    assert vis["body"].exists()
    assert not vis["L_twist"].exists()
```

(The last test needs the real `twist` module wired; if its required inputs make the setup heavy, replace it with a second toy that declares `controls = ()` and builds none, registered as `toy_still`.)

In `tests/integration/trigger/test_module_ground_rules.py`, append:

```python
@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_every_controller_carries_a_valid_tier(module_type):
    """Rule: a tweak has no tier; everything else declares one of TIERS."""
    from tik.trigger.core import TIERS

    ctx = _solo(module_type)
    for controller in ctx.controllers:
        role = controller.transform.meta.get(tags.ROLE, "")
        tier = controller.transform.meta.get(tags.TIER)
        if role.endswith("_tweak"):
            assert tier is None, f"{controller.transform.name} is a tiered tweak"
        else:
            assert tier in TIERS, f"{controller.transform.name} has tier {tier!r}"


@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_visibilities_enum_matches_the_control_manifest(module_type):
    """One enum on visibilities_ctrl iff the module declares controls."""
    module_cls = get_module(module_type)
    ctx = _built_with(module_type, {})
    vis = ctx.scaffold.visibilities.transform
    key = ctx.instance.key
    expected = bool(module_cls.control_names(ctx.instance.settings))
    assert vis[key].exists() is expected, f"{module_type}: enum present={not expected}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mayapy -m pytest tests/unit/test_guide_scene_trigger.py -q -k tier` and `mayapy -m pytest tests/integration/trigger/test_builder_trigger.py -q -k "tier or visibilities or enum"`
Expected: FAIL with `TypeError: controller() got an unexpected keyword argument 'tier'` / `KeyError: 'trg_tier'`.

- [ ] **Step 3: `TIERS` in core**

In `src/python/tik/trigger/core/manifest.py`, after the imports:

```python
#: Control tiers, in the order the visibilities enum lists them. ``all`` is
#: the enum's fourth item, not a tier a control can be given.
TIERS = ("primary", "secondary", "tertiary")
```

In `core/__init__.py`: `from .manifest import TIERS, GuideAttr, GuideLayout, Input, instance_key` and add `"TIERS"` to `__all__`.

- [ ] **Step 4: `controller(tier=)` and `tweak_control`**

In `src/python/tik/trigger/maya/rig.py`, import `TIERS`:

```python
from tik.trigger.core.manifest import TIERS
```

Change the `controller` signature to add `tier: Optional[str] = "primary",` after `offset: bool = True,`, extend the docstring with `` ``tier`` places the control in the visibilities enum (one of ``TIERS``); ``None`` leaves it untiered, which is what a tweak wants. `` and, before `Controller.create(...)`:

```python
        if tier is not None and tier not in TIERS:
            raise GuideError(
                f"'{name}': tier must be one of {TIERS} or None, got {tier!r}."
            )
```

After the existing `tags.tag(controller.transform, ...)` call:

```python
        if tier is not None:
            controller.transform.meta[tags.TIER] = tier
```

In `tweak_control`, add `tier=None,` to the `self.controller(...)` call.

- [ ] **Step 5: `wire_tiers` in the builder**

In `src/python/tik/trigger/maya/build.py`:

```python
import re

from tik.trigger.core.manifest import TIERS

TIER_ITEMS = (*TIERS, "all")
ALL_INDEX = len(TIERS)


def tier_attr_name(key: str) -> str:
    """The visibilities enum for a module: its display key, made attribute-safe."""
    return re.sub(r"\W", "_", key)


def wire_tiers(rig) -> None:
    """One exclusive-tier enum per module on visibilities_ctrl, driving shapes.

    Tiers are exclusive: ``secondary`` shows secondary controls only, ``all``
    shows the three tiers. Shapes are driven, not transforms, so an FK chain
    whose next control hangs under the previous one keeps its hierarchy.
    Tweaks carry no tier and are left to ``tweakVis`` on their main.
    """
    by_tier: dict[str, list] = {}
    for controller in rig.controllers:
        tier = controller.transform.meta.get(tags.TIER)
        if tier is not None:
            by_tier.setdefault(tier, []).append(controller)
    if not by_tier:
        return
    vis = rig.scaffold.visibilities.transform
    attr = tier_attr_name(rig.instance.key)
    enum = vis[attr]
    if not enum.exists():
        enum.create("enum", items=list(TIER_ITEMS), default=ALL_INDEX, keyable=False)
        enum.visible = True
    is_all = enum.eq(ALL_INDEX, 1, 0)
    cmds.rename(is_all.node.long_name, rig.name("vis", "all", suffix="cond"))
    for tier, controllers in by_tier.items():
        shown = enum.eq(TIERS.index(tier), 1, is_all)
        cmds.rename(shown.node.long_name, rig.name("vis", tier, suffix="cond"))
        for controller in controllers:
            for shape in controller.transform.shapes:
                shown >> shape["visibility"]
```

`cmds.rename` on a renamed node invalidates the wrapper's cached name only if the wrapper caches by name; `Plug.node` returns the wrapper that resolved the `condition#` name. Since `shown` is used after the rename, resolve the plug fresh if the connection fails: `shown = tm.Plug(tm.resolve(new_name), "outColorR")`. Verify once in the test run and keep whichever form works.

Call it from `finalize`, after `wire_preferences(rig)`:

```python
    wire_preferences(rig)
    wire_tiers(rig)
```

- [ ] **Step 6: Run the tests**

Run: `mayapy -m pytest tests/unit/test_guide_scene_trigger.py tests/integration/trigger/test_builder_trigger.py tests/integration/trigger/test_module_ground_rules.py -q`
Expected: PASS. `test_every_module_declares_exactly_the_controllers_it_builds` must still pass: the tier tag does not change roles.

- [ ] **Step 7: Run the full suites**

Run: `mayapy -m pytest tests/unit -q` and `mayapy -m pytest tests/integration -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/core/manifest.py src/python/tik/trigger/core/__init__.py src/python/tik/trigger/maya/rig.py src/python/tik/trigger/maya/build.py tests/helpers/toy_modules.py tests/unit/test_guide_scene_trigger.py tests/integration/trigger/test_builder_trigger.py tests/integration/trigger/test_module_ground_rules.py
git commit -m "trigger: control tiers on the visibilities control"
```

---

### Task 6: The runner ensures the scaffold and hands it to actions

**Files:**
- Modify: `src/python/tik/trigger/core/action.py` (`ActionContext.rig`)
- Modify: `src/python/tik/trigger/maya/runner.py` (`_run_step`)
- Test: `tests/unit/test_runner_trigger.py`

**Interfaces:**
- Consumes: `scaffold.ensure_rig(events)`.
- Produces: `ActionContext.rig: Any = None`, set to the `RigScaffold` for every step the runner executes.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_runner_trigger.py`, add a recording action and two tests:

```python
class SeesRig(Action):
    def run(self, ctx):
        CALLS.append(("rig", ctx.rig))
```

Register it in `_registered`: `register_action("sees_rig")(SeesRig)`.

```python
def test_every_step_receives_the_scaffold():
    from maya import cmds

    from tik.trigger.maya.scaffold import RigScaffold

    doc = Document()
    doc.add(ActionNode("first", "sees_rig"))
    doc.add(ActionNode("second", "sees_rig"))
    Runner().run(doc, "D:/x")
    rigs = [call[1] for call in CALLS if call[0] == "rig"]
    assert len(rigs) == 2 and all(isinstance(rig, RigScaffold) for rig in rigs)
    assert rigs[0].root.long_name == rigs[1].root.long_name == "|rig_grp"
    assert len(cmds.ls("rig_grp")) == 1


def test_a_script_can_extend_the_preferences_control():
    from maya import cmds

    from tik.trigger.actions.script.script import Script

    register_action("script", category="structure", scope="both")(Script)
    doc = Document()
    doc.add(
        ActionNode(
            "extend",
            "script",
            settings={
                "code": (
                    "plug = ctx.rig.preferences.transform['exportLod']\n"
                    "plug.create('int', default=0, keyable=False)\n"
                    "plug.visible = True\n"
                )
            },
        )
    )
    Runner().run(doc, "D:/x")
    assert cmds.attributeQuery("exportLod", node="preferences_ctrl", exists=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mayapy -m pytest tests/unit/test_runner_trigger.py -q -k "scaffold or preferences"`
Expected: FAIL with `AttributeError: 'ActionContext' object has no attribute 'rig'`

- [ ] **Step 3: Add `rig` to `ActionContext`**

In `src/python/tik/trigger/core/action.py`, after `depth: int = 0`:

```python
    rig: Any = None  # the RigScaffold, set by the Maya runner; core never reads it
```

- [ ] **Step 4: Ensure in `_run_step`**

In `src/python/tik/trigger/maya/runner.py`, import at top: `from .scaffold import ensure_rig`. In `_run_step`, replace the run block:

```python
        try:
            with undo_chunk(f"Trigger: {step.display_chain}"):
                ctx.rig = ensure_rig(self.events)
                action.run(ctx)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `mayapy -m pytest tests/unit/test_runner_trigger.py tests/integration/trigger/test_publish_phase_trigger.py tests/integration/trigger/test_session_build_trigger.py -q`
Expected: PASS. `test_build_and_publish_resets_the_scene_exactly_once` still counts one reset: `ensure_rig` never resets.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/core/action.py src/python/tik/trigger/maya/runner.py tests/unit/test_runner_trigger.py
git commit -m "trigger: runner ensures the scaffold and passes it as ctx.rig"
```

---

### Task 7: Import Model parents into `geo_grp`

**Files:**
- Modify: `src/python/tik/trigger/actions/import_asset/import_asset.py`
- Test: `tests/integration/trigger/test_session_build_trigger.py`

**Interfaces:**
- Consumes: `ctx.rig.geo` (Task 6).
- Produces: `ImportAsset.parent_to_geo: BoolField(True)`; after a run with it on, every top-level transform the import created sits under `|rig_grp|geo_grp`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_session_build_trigger.py`:

```python
def _model_file(tmp_path):
    model = tmp_path / "geo" / "hero_model.ma"
    cmds.file(new=True, force=True)
    cmds.polySphere(name="hero_geo")
    cmds.polyCube(name="prop_geo")
    model.parent.mkdir(exist_ok=True)
    cmds.file(rename=str(model))
    cmds.file(save=True, type="mayaAscii", force=True)
    return model


def test_import_model_parents_under_geo_grp(tmp_path):
    model = _model_file(tmp_path)
    rig = trigger.Session()
    rig.save(tmp_path / "hero.tr")
    rig.add("import_asset", "import_model", file_path="geo/hero_model.ma")
    rig.build()
    assert cmds.ls("hero_geo", long=True) == ["|rig_grp|geo_grp|hero_geo"]
    assert cmds.ls("prop_geo", long=True) == ["|rig_grp|geo_grp|prop_geo"]


def test_import_model_can_leave_geometry_at_world(tmp_path):
    _model_file(tmp_path)
    rig = trigger.Session()
    rig.save(tmp_path / "hero.tr")
    rig.add(
        "import_asset", "import_model", file_path="geo/hero_model.ma", parent_to_geo=False
    )
    rig.build()
    assert cmds.ls("hero_geo", long=True) == ["|hero_geo"]


def test_referenced_model_is_parented_too(tmp_path):
    _model_file(tmp_path)
    rig = trigger.Session()
    rig.save(tmp_path / "hero.tr")
    rig.add(
        "import_asset",
        "import_model",
        file_path="geo/hero_model.ma",
        reference=True,
        namespace="model",
    )
    rig.build()
    assert cmds.ls("model:hero_geo", long=True) == ["|rig_grp|geo_grp|model:hero_geo"]
```

Also update the first assertion block of `test_session_builds_from_files_and_rebuilds` so it keeps passing: `cmds.objExists("hero_geo")` still holds by short name.

- [ ] **Step 2: Run tests to verify they fail**

Run: `mayapy -m pytest tests/integration/trigger/test_session_build_trigger.py -q -k "geo_grp or world or referenced"`
Expected: `test_import_model_parents_under_geo_grp` FAILS (`["|hero_geo"]`), `test_import_model_can_leave_geometry_at_world` FAILS on the unknown `parent_to_geo` setting.

- [ ] **Step 3: Implement**

Replace `run` in `import_asset.py`:

```python
    parent_to_geo = BoolField(
        True,
        label="Parent to geo_grp",
        help="Move what the file brings in under the rig's geo_grp.",
    )

    def run(self, ctx) -> None:
        """Import or reference the file into the scene."""
        from maya import cmds

        path = self.resolve_path(ctx)
        if not path.exists():
            raise ActionExecutionError(f"File not found: {path}")
        kwargs = {"force": True, "returnNewNodes": True}
        if self.namespace:
            kwargs["namespace"] = self.namespace
        if self.reference:
            new_nodes = cmds.file(str(path), reference=True, **kwargs) or []
        else:
            new_nodes = cmds.file(str(path), i=True, **kwargs) or []
        if self.parent_to_geo and ctx.rig is not None:
            self._parent_top_nodes(new_nodes, ctx.rig.geo)
        ctx.log(f"Imported {path}")

    @staticmethod
    def _parent_top_nodes(new_nodes, geo) -> None:
        """Every world-level DAG node the file brought in goes under geo_grp."""
        from maya import cmds

        top = [
            node
            for node in cmds.ls(new_nodes, long=True, dag=True, type="transform") or []
            if node.count("|") == 1
        ]
        if top:
            cmds.parent(top, geo.long_name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mayapy -m pytest tests/integration/trigger/test_session_build_trigger.py -q`
Expected: PASS. If the reference test fails on parenting, Maya may report the referenced root as `|model:hero_geo` only after `cmds.file` returns; parenting a referenced top node is legal and becomes a reference edit.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/actions/import_asset/import_asset.py tests/integration/trigger/test_session_build_trigger.py
git commit -m "trigger: Import Model parents geometry under geo_grp"
```

---

### Task 8: Ground rules and project docs

**Files:**
- Modify: `AI/coding_rules.md` (Group Taxonomy section, ~line 120)
- Modify: `CLAUDE.md` (Module Ground Rules paragraph and the tik.trigger status line)

- [ ] **Step 1: Update `AI/coding_rules.md`**

Above the existing `<side>_<name>_grp` tree in "Group Taxonomy", insert:

```markdown
Every module hangs under the rig's scaffold, which `ensure_rig()` creates or
heals before any build or action (`tik/trigger/maya/scaffold.py`). One rig per
scene, no name:

```
rig_grp
├── trigger_grp            every <side>_<name>_grp
│   ├── preferences_ctrl   rig-wide switches: cacheMode, controls, rig/rigDisplay,
│   │                      joints/jointsDisplay, geometry/geometryDisplay
│   └── visibilities_ctrl  one enum per module: primary / secondary / tertiary / all
└── geo_grp                what Import Model brings in
```

Modules never add attributes to `preferences_ctrl`. The one thing a module
says about visibility is the **tier** of each controller:
`rig.controller(name, tier="secondary")`, default `primary`, one of
`tik.trigger.core.TIERS`. Tiers are exclusive in the enum; `all` shows the
three. Tweaks have no tier and stay on `tweakVis`. Tier wiring drives shape
visibility, never transforms.
```

- [ ] **Step 2: Update `CLAUDE.md`**

In the "Module Ground Rules" paragraph, after "Controllers come with their offset group (`ctrl.offset`).", add: "Every controller has a **tier** (`rig.controller(..., tier=)`, default `primary`, tweaks excluded) that the rig's `visibilities_ctrl` shows or hides per module; rig-wide switches live on `preferences_ctrl`; both sit in the fixed `rig_grp` > `trigger_grp` scaffold that `ensure_rig()` guarantees before any build or action." In the tik.trigger status line, add the spec to the list: "`2026-09-05-rig-scaffold-and-master-controls-design.md` (the fixed rig scaffold, the preferences and visibilities controls, control tiers)".

- [ ] **Step 3: Run everything once more**

Run: `make tests-unit`, `make tests-integration`, `make tests-ui`, `make lint`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add AI/coding_rules.md CLAUDE.md
git commit -m "docs: rig scaffold and control tiers in the ground rules"
```
