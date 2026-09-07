# Animator Switches Dock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dockable, non-modal Switches tool that follows the selection, driving pivot presets today and reserving tabs for FK/IK and the pole pin.

**Architecture:** A new `tik/trigger/anim` package — animator tools that read a built rig and never the session, enforced by an import boundary. A `@register_switch` registry mirrors `@register_action`; each switch supplies `states` / `current` / `apply` and nothing else touches Maya, so the Qt shell is testable offscreen. Scene work stays in `tik/trigger/maya/pivot.py`.

**Tech Stack:** Python 3.10+, Maya 2024+, tik.maya, Qt via `tik.shared.ui.Qt`, pytest under `mayapy`.

**Spec:** `docs/superpowers/specs/2026-09-07-animator-switches-dock-design.md`

## Global Constraints

- **Never call `maya.cmds` or `maya.api.OpenMaya` directly** outside `src/python/tik/maya/`. Use `import tik.maya as tm`.
- **`tik/trigger/anim` may not import** `trigger.session`, `trigger.core.document`, `trigger.core.guide_document`, `trigger.guides` or `trigger.ui`. Enforced by `tests/unit/test_import_boundaries.py`.
- **`tik/trigger/anim/context.py`, `switch.py`, `registry.py` and `window.py` must import without Maya** — `tests/ui` runs with `TIK_TESTS_NO_MAYA=1`. Maya imports go inside the switch methods or behind `HAS_MAYA`.
- **Every dialog goes through `tik.shared.ui.feedback.Feedback`** (`tests/unit/test_dialog_boundaries.py`). This tool should need none.
- **Qt comes from `tik.shared.ui.Qt`**, never from PySide directly.
- **No third-party dependencies.** Stdlib and Maya-bundled only.
- **House style:** properties for state (noun), methods for actions (verb), no `get_`/`set_` prefixes, type hints and PEP 257 docstrings on public APIs.
- Unit: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/<file> -q`
- Integration: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/integration/trigger/<file> -q`
- UI: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/ui/<file> -q`
- Full suites: `mayapy tests/unit/invoke.py`, `mayapy tests/integration/invoke.py`
- Lint before every commit: `python -m black src/python/tik tests`, `python -m isort src/python/tik tests`, `python -m flake8 src/python/tik tests` (all must exit 0 — do not pipe to `tail`, it masks the exit code).

---

### Task 1: `switch_pivot_preset` over a frame range

**Files:**
- Modify: `src/python/tik/trigger/maya/pivot.py`
- Test: `tests/unit/test_pivot_trigger.py`

**Interfaces:**
- Produces:
  - `switch_pivot_preset(control, preset, key=False, times=None) -> str` — returns a one-line report. `times=None` switches at the current frame (today's behaviour). A sequence of times switches at each, correcting `translate` per time.
  - `key_times(control, start, end) -> tuple[float, ...]` — every keyframe time on any keyable channel of `control` inside `[start, end]`, sorted and de-duplicated.
  - `playback_range() -> tuple[float, float]` — the playback start/end.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_pivot_trigger.py`:

```python
def test_key_times_unions_every_channel():
    from tik.trigger.maya.pivot import key_times

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    cmds.setKeyframe(main.transform.long_name, attribute="translateX", time=1)
    cmds.setKeyframe(main.transform.long_name, attribute="translateX", time=20)
    cmds.setKeyframe(main.transform.long_name, attribute="rotateY", time=10)
    cmds.setKeyframe(main.transform.long_name, attribute="rotateY", time=40)

    assert key_times(main, 1, 30) == (1.0, 10.0, 20.0)


def test_switch_over_a_range_holds_the_pose_at_every_key():
    from tik.trigger.maya.pivot import switch_pivot_preset

    ctx = _build(
        "pivot_toy",
        {"pivot_main_tip": (9.0, 0.0, 0.0), "pivot_main_ball": (7.0, 0.0, 0.0)},
    )
    main = ctx.controller_by_role("main")
    main.transform["pivotPreset"].value = 1
    for time, angle in ((1, 0.0), (12, 35.0), (24, -20.0)):
        cmds.currentTime(time)
        main.transform.rotate = (0.0, angle, 0.0)
        cmds.setKeyframe(main.transform.long_name, attribute=["translate", "rotate"])

    before = {}
    for time in (1, 12, 24):
        cmds.currentTime(time)
        before[time] = [round(value, 4) for value in main.transform.world_matrix]

    switch_pivot_preset(main, "ball", key=True, times=(1.0, 12.0, 24.0))

    for time in (1, 12, 24):
        cmds.currentTime(time)
        assert [round(value, 4) for value in main.transform.world_matrix] == before[time]
    assert main.transform["pivotPreset"].value == 2


def test_the_preset_enum_is_keyed_once_and_stepped():
    from tik.trigger.maya.pivot import switch_pivot_preset

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    path = main.transform.long_name + ".pivotPreset"
    switch_pivot_preset(main, "tip", key=True, times=(3.0, 9.0, 15.0))

    assert cmds.keyframe(path, query=True, timeChange=True) == [3.0]
    assert cmds.keyTangent(path, query=True, outTangentType=True) == ["step"]


def test_switch_without_key_leaves_no_keys():
    from tik.trigger.maya.pivot import switch_pivot_preset

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    switch_pivot_preset(main, "tip", key=False, times=(1.0, 5.0))

    assert cmds.keyframe(main.transform.long_name, query=True, keyframeCount=True) == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_pivot_trigger.py -q -k "key_times or range or stepped or without_key"`
Expected: FAIL — `ImportError: cannot import name 'key_times'`.

- [ ] **Step 3: Implement**

In `src/python/tik/trigger/maya/pivot.py`, add after `preset_labels`:

```python
def playback_range() -> tuple[float, float]:
    """The playback start and end, as the timeline shows them."""
    return (
        float(tm.playbackOptions(query=True, minTime=True)),
        float(tm.playbackOptions(query=True, maxTime=True)),
    )


def key_times(control, start: float, end: float) -> tuple[float, ...]:
    """Keyframe times on any keyable channel of ``control`` within the range.

    The union across *all* channels, not just translation: once the pivot
    moves, every later pose depends on it, so a control keyed only on rotation
    still needs its translation corrected at those times.
    """
    node = _transform(control)
    found = tm.keyframe(node.long_name, query=True, timeChange=True) or []
    return tuple(sorted({float(time) for time in found if start <= time <= end}))
```

Then replace `switch_pivot_preset`:

```python
@undo
def switch_pivot_preset(control, preset, key: bool = False, times=None) -> str:
    """Set ``control``'s pivot preset while holding its pose.

    A ``rotatePivot`` change displaces the control by a constant translation in
    its parent's space, so correcting ``translate`` by the parent-space delta
    puts it back exactly. Over several ``times`` the correction is redone at
    each, because every pose after the switch depends on the new pivot.

    Args:
        control: A controller, transform or node name carrying ``pivotPreset``.
        preset: A preset label or its enum index.
        key: Key ``translate`` at each corrected time, and the preset once.
        times: Times to correct at; ``None`` means the current frame only.

    Returns:
        str: One line describing what happened.

    Raises:
        ValueError: If the control has no pivot presets, or ``preset`` names
            one it does not have.
    """
    node = _transform(control)
    labels = preset_labels(node)
    if not labels:
        raise ValueError(f"'{node.name}' has no pivot presets.")
    index = _preset_index(node, preset, labels)
    label = labels[index]

    frames = tuple(times) if times else (float(tm.currentTime(query=True)),)
    restore = float(tm.currentTime(query=True))
    keyed = 0
    try:
        for position, moment in enumerate(frames):
            tm.currentTime(moment)
            before = _local_origin(node)
            node[PRESET_ATTR].value = index
            after = _local_origin(node)
            node.translate = tuple(
                current - (moved - rest)
                for current, rest, moved in zip(node.translate, before, after)
            )
            if key:
                tm.setKeyframe(node.long_name, attribute="translate", time=moment)
                keyed += 1
                if position == 0:
                    tm.setKeyframe(node.long_name, attribute=PRESET_ATTR, time=moment)
                    tm.keyTangent(
                        node.long_name + "." + PRESET_ATTR,
                        time=(moment, moment),
                        inTangentType="step",
                        outTangentType="step",
                    )
    finally:
        tm.currentTime(restore)

    if len(frames) > 1:
        return f"{node.name} to {label} over {len(frames)} keys — pose held"
    return f"{node.name} to {label} — pose held"
```

Note: the enum is set inside the loop so each frame's correction is measured
against the switched pivot, but it is *keyed* only at the first time — a pivot is
a discrete state and interpolating between two enum values is meaningless.

- [ ] **Step 4: Run to verify they pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_pivot_trigger.py -q`
Expected: PASS, whole file.

- [ ] **Step 5: Lint and commit**

```bash
python -m black src/python/tik tests && python -m isort src/python/tik tests && python -m flake8 src/python/tik tests
git add src/python/tik/trigger/maya/pivot.py tests/unit/test_pivot_trigger.py
git commit -m "Switch a pivot preset across a frame range"
```

---

### Task 2: The anim package — context, contract, registry, boundary

**Files:**
- Create: `src/python/tik/trigger/anim/__init__.py`, `context.py`, `switch.py`, `registry.py`
- Create: `src/python/tik/trigger/anim/switches/__init__.py`
- Modify: `tests/unit/test_import_boundaries.py`
- Test: `tests/unit/test_switch_registry.py`

**Interfaces:**
- Consumes: nothing from Task 1 yet.
- Produces:
  - `Control` — frozen dataclass: `node: str`, `role: str = ""`, `side: str = "C"`, `module: str = ""`, `instance: str = ""`.
  - `SwitchContext` — frozen dataclass: `nodes: tuple[str, ...] = ()`, `controls: tuple[Control, ...] = ()`; properties `is_empty: bool`, `keys: tuple[str, ...]` (module keys, de-duplicated, in order), `sides: tuple[str, ...]`.
  - `SwitchContext.from_scene() -> SwitchContext` — reads the Maya selection. **The only Maya-touching thing in the module**, imported lazily inside the method.
  - `Switch` — the contract from the spec: `label`, `help`, `order`, `available`, `switch_type`, `icon`, `states`, `current`, `apply`. `MIXED` sentinel is `None`.
  - `register_switch(name, icon="")`, `get_switch(name)`, `iter_switches()` (sorted by `order` then `label`), `clear_switches()`, `unregister_switch(name)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_switch_registry.py`:

```python
"""The animator switch registry and its contract (no Maya, no Qt)."""

import pytest

from tik.trigger.anim.context import Control, SwitchContext
from tik.trigger.anim.registry import (
    clear_switches,
    get_switch,
    iter_switches,
    register_switch,
)
from tik.trigger.anim.switch import Switch
from tik.trigger.core.exceptions import DuplicateRegistrationError, NotFoundError


@pytest.fixture(autouse=True)
def _clean():
    clear_switches()
    yield
    clear_switches()


def _toy(name, order=100, available=True, states=("a", "b")):
    @register_switch(name)
    class Toy(Switch):
        label = name.title()
        pass

    Toy.order = order
    Toy.available = available
    Toy.states = lambda self, context: list(states)
    return Toy


def test_register_stamps_type_and_icon():
    toy = _toy("pivot")
    assert toy.switch_type == "pivot"
    assert toy.icon == "pivot"
    assert get_switch("pivot") is toy


def test_registering_a_name_twice_is_refused():
    _toy("pivot")
    with pytest.raises(DuplicateRegistrationError):

        @register_switch("pivot")
        class Other(Switch):
            label = "Other"


def test_unknown_switch_raises():
    with pytest.raises(NotFoundError):
        get_switch("nope")


def test_switches_iterate_in_order_then_label():
    _toy("zed", order=10)
    _toy("alpha", order=10)
    _toy("last", order=90)
    assert [item.switch_type for item in iter_switches()] == ["alpha", "zed", "last"]


def test_the_base_contract_offers_nothing():
    class Bare(Switch):
        label = "Bare"

    context = SwitchContext()
    assert Bare().states(context) == []
    assert Bare().current(context) is None


def test_context_reports_keys_and_sides_without_repeats():
    context = SwitchContext(
        nodes=("|a", "|b", "|c"),
        controls=(
            Control(node="|a", role="ik", side="L", module="arm", instance="1"),
            Control(node="|b", role="pole", side="L", module="arm", instance="1"),
            Control(node="|c", role="ik", side="R", module="arm", instance="2"),
        ),
    )
    assert context.is_empty is False
    assert context.keys == ("L_arm", "R_arm")
    assert context.sides == ("L", "R")


def test_an_empty_context_is_empty():
    assert SwitchContext().is_empty is True
    assert SwitchContext().keys == ()
```

Add to `tests/unit/test_import_boundaries.py`'s `FORBIDDEN` mapping:

```python
    #: An animator tool reads the rig, never the session. Everything a switch
    #: needs is on the built nodes (the pivotPreset enum, the trg_* tags), so
    #: this costs nothing and keeps the rigger's app and the animator's tools
    #: from entangling.
    "trigger/anim": (
        "tik.trigger.session",
        "tik.trigger.core.document",
        "tik.trigger.core.guide_document",
        "tik.trigger.guides",
        "tik.trigger.ui",
    ) + PREFS,
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_switch_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.anim'`.

- [ ] **Step 3: Write `context.py`**

```python
"""What is selected, as plain data.

The shell renders a context; a switch reads one. Neither needs Maya to exist,
which is what lets ``tests/ui`` drive the whole window offscreen against a
fabricated selection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Control:
    """One selected rig controller, as its tags describe it."""

    node: str
    role: str = ""
    side: str = "C"
    module: str = ""
    instance: str = ""

    @property
    def key(self) -> str:
        """Display key: ``L_arm`` / ``spine``."""
        if not self.module:
            return ""
        return self.module if self.side in ("C", "") else f"{self.side}_{self.module}"


@dataclass(frozen=True)
class SwitchContext:
    """The selection a switch acts on."""

    nodes: tuple[str, ...] = ()
    controls: tuple[Control, ...] = ()

    @property
    def is_empty(self) -> bool:
        """True when nothing usable is selected."""
        return not self.controls

    @property
    def keys(self) -> tuple[str, ...]:
        """Module display keys, in selection order, without repeats."""
        found: list[str] = []
        for control in self.controls:
            if control.key and control.key not in found:
                found.append(control.key)
        return tuple(found)

    @property
    def sides(self) -> tuple[str, ...]:
        """Sides present, in selection order, without repeats."""
        found: list[str] = []
        for control in self.controls:
            if control.side not in found:
                found.append(control.side)
        return tuple(found)

    @classmethod
    def from_scene(cls) -> "SwitchContext":
        """Read the current Maya selection. The one Maya-touching call here."""
        import tik.maya as tm

        from tik.trigger.maya import tags

        nodes, controls = [], []
        for node in tm.ls(selection=True, type="transform") or []:
            nodes.append(node.long_name)
            meta = node.meta.as_dict()
            if meta.get(tags.KIND) != tags.CONTROLLER:
                continue
            controls.append(
                Control(
                    node=node.long_name,
                    role=meta.get(tags.ROLE, ""),
                    side=meta.get(tags.SIDE, "C"),
                    module=meta.get(tags.NAME, "") or meta.get(tags.MODULE, ""),
                    instance=meta.get(tags.INSTANCE, ""),
                )
            )
        return cls(nodes=tuple(nodes), controls=tuple(controls))
```

Note: a controller is tagged with `KIND`, `INSTANCE`, `ROLE` and `MIRROR` by
`rig.controller`, but **not** with `SIDE`, `NAME` or `MODULE` — those live on the
module's top group. Verify this against `tik/trigger/maya/rig.py` before relying
on it; if the tags are absent, resolve them by walking up to the nearest ancestor
carrying `tags.KIND == tags.RIG` and reading `tags.SIDE` / `tags.NAME` there, and
put that walk in `from_scene`. The dataclass shape does not change either way.

- [ ] **Step 4: Write `switch.py`**

```python
"""The tab contract: a named set of states you pick between."""

from __future__ import annotations

from typing import Optional, Sequence

from .context import SwitchContext


class Switch:
    """One tab in the Switches dock.

    A switch changes what a control *does* and the pose survives it. Anything
    that cannot name what it promises not to disturb is not a switch.

    Subclasses override three methods and declare a label; the shell owns the
    chips, the keying, the frame scope and the status line.
    """

    label: str = ""
    help: str = ""
    order: int = 100
    #: False marks a switch that is declared but not built. The shell shows
    #: ``help`` under a "not built yet" line instead of an empty picker, so a
    #: placeholder never reads as broken.
    available: bool = True

    switch_type: str = ""  # stamped by @register_switch
    icon: str = ""  # stamped by @register_switch

    @classmethod
    def display_label(cls) -> str:
        """The tab text (falls back to the type)."""
        return cls.label or cls.switch_type

    def states(self, context: SwitchContext) -> list[str]:
        """The states offered for ``context``. Empty means nothing to offer."""
        return []

    def current(self, context: SwitchContext) -> Optional[str]:
        """The state ``context`` is in; None when it has none or they disagree."""
        return None

    def apply(
        self, context: SwitchContext, state: str, *, key: bool, times: Sequence[float]
    ) -> str:
        """Switch ``context`` to ``state``; return one line for the status bar."""
        raise NotImplementedError
```

- [ ] **Step 5: Write `registry.py`**

```python
"""Switch discovery: ``@register_switch``, mirroring the action registry."""

from __future__ import annotations

import logging
from typing import Callable

from tik.trigger.core.exceptions import DuplicateRegistrationError, NotFoundError

from .switch import Switch

logger = logging.getLogger(__name__)

_SWITCHES: dict[str, type[Switch]] = {}


def register_switch(name: str, icon: str = "") -> Callable[[type], type]:
    """Register a ``Switch`` subclass under ``name``.

    Args:
        name: Unique switch type name.
        icon: Icon name (defaults to ``name``).
    """

    def inner(cls: type) -> type:
        existing = _SWITCHES.get(name)
        if existing is not None and existing is not cls:
            raise DuplicateRegistrationError(name, kind="switch")
        cls.switch_type = name
        cls.icon = icon or name
        _SWITCHES[name] = cls
        logger.debug("Registered switch: %s", name)
        return cls

    return inner


def get_switch(name: str) -> type[Switch]:
    """The switch class registered under ``name``."""
    try:
        return _SWITCHES[name]
    except KeyError:
        raise NotFoundError(f"No switch registered as '{name}'.") from None


def iter_switches() -> list[type[Switch]]:
    """Every registered switch, by ``order`` then label."""
    return sorted(_SWITCHES.values(), key=lambda cls: (cls.order, cls.display_label()))


def unregister_switch(name: str) -> None:
    """Drop one registration (tests)."""
    _SWITCHES.pop(name, None)


def clear_switches() -> None:
    """Drop every registration (tests)."""
    _SWITCHES.clear()
```

Check `DuplicateRegistrationError`'s signature in
`src/python/tik/trigger/core/exceptions.py` and match it — if it does not take a
`kind` keyword, pass whatever it does. Same for `NotFoundError`.

- [ ] **Step 6: Write the two `__init__.py` files**

`src/python/tik/trigger/anim/switches/__init__.py`:

```python
"""Built-in switches. Importing this package is what registers them."""

from . import ikfk, pivot, polepin  # noqa: F401 - imported for registration
```

Leave this importing nothing until Tasks 3 and 4 create those modules — for now
write it as an empty docstring-only module and fill it in at Task 4.

`src/python/tik/trigger/anim/__init__.py`:

```python
"""Animator tools for a built trigger rig.

An animator tool reads the rig, never the session: everything a switch needs is
already on the built nodes, so this package is forbidden from importing
``trigger.session``, the documents, the guides or ``trigger.ui``
(``tests/unit/test_import_boundaries.py``).
"""

from .context import Control, SwitchContext
from .registry import get_switch, iter_switches, register_switch
from .switch import Switch

__all__ = [
    "Control",
    "SwitchContext",
    "Switch",
    "get_switch",
    "iter_switches",
    "register_switch",
]
```

`show()` is added in Task 6 — adding it now would make this module import Qt,
and `test_switch_registry.py` must run without a QApplication.

- [ ] **Step 7: Run the tests**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_switch_registry.py tests/unit/test_import_boundaries.py -q`
Expected: PASS.

- [ ] **Step 8: Lint and commit**

```bash
python -m black src/python/tik tests && python -m isort src/python/tik tests && python -m flake8 src/python/tik tests
git add src/python/tik/trigger/anim tests/unit/test_switch_registry.py tests/unit/test_import_boundaries.py
git commit -m "Add the animator switch registry, contract and selection context"
```

---

### Task 3: The pivot switch

**Files:**
- Create: `src/python/tik/trigger/anim/switches/pivot/__init__.py`, `pivot.py`, `pivot.svg`
- Test: `tests/unit/test_pivot_trigger.py` (append)

**Interfaces:**
- Consumes: `Switch`, `SwitchContext`, `register_switch` (Task 2); `pivot.preset_labels`, `switch_pivot_preset`, `key_times` (Task 1).
- Produces: `PivotSwitch` registered as `"pivot"`, `label="Pivot"`, `order=10`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_pivot_trigger.py`:

```python
# ------------------------------------------------------------- the switch tab
def _context_for(*controls):
    from tik.trigger.anim.context import Control, SwitchContext

    return SwitchContext(
        nodes=tuple(item.transform.long_name for item in controls),
        controls=tuple(
            Control(node=item.transform.long_name, role="main", side="C", module="toy")
            for item in controls
        ),
    )


def test_pivot_switch_offers_the_controls_presets():
    from tik.trigger.anim.switches.pivot.pivot import PivotSwitch

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    switch = PivotSwitch()
    context = _context_for(main)

    assert switch.states(context) == ["default", "tip", "ball"]
    assert switch.current(context) == "default"


def test_pivot_switch_offers_nothing_for_a_control_without_presets():
    from tik.trigger.anim.switches.pivot.pivot import PivotSwitch

    ctx = _build("bare_pivot_toy")
    main = ctx.controller_by_role("main")
    assert PivotSwitch().states(_context_for(main)) == []


def test_pivot_switch_reports_mixed_when_controls_disagree():
    from tik.trigger.anim.switches.pivot.pivot import PivotSwitch

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    other = ctx.controller_by_role("main")  # same control, two entries
    main.transform["pivotPreset"].value = 1
    switch = PivotSwitch()
    assert switch.current(_context_for(main, other)) == "tip"

    main.transform["pivotPreset"].value = 2
    # a genuinely mixed selection needs two different controls; fabricate one by
    # building a second instance in the same scene if the toy allows it,
    # otherwise assert the single-control answer and cover mixed in the UI test.


def test_pivot_switch_applies_and_reports():
    from tik.trigger.anim.switches.pivot.pivot import PivotSwitch

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    context = _context_for(main)
    report = PivotSwitch().apply(context, "tip", key=False, times=(1.0,))

    assert main.transform["pivotPreset"].value == 1
    assert "tip" in report
```

Drop the incomplete `test_pivot_switch_reports_mixed_when_controls_disagree` and
write it only if the toy scene can hold two independent pivot controls; the
mixed rendering is covered offscreen in Task 5 either way.

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_pivot_trigger.py -q -k "pivot_switch"`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/python/tik/trigger/anim/switches/pivot/__init__.py`:

```python
"""The pivot-preset switch."""

from .pivot import PivotSwitch  # noqa: F401
```

`src/python/tik/trigger/anim/switches/pivot/pivot.py`:

```python
"""Which point a control turns about."""

from __future__ import annotations

from typing import Optional, Sequence

from tik.trigger.anim.registry import register_switch
from tik.trigger.anim.switch import Switch
from tik.trigger.maya import pivot as ops


@register_switch("pivot")
class PivotSwitch(Switch):
    """Snap a control's rotate pivot to one of its rigger-placed presets."""

    label = "Pivot"
    help = "Which point the control turns about."
    order = 10

    def states(self, context) -> list[str]:
        """Presets every selected control has, in the first one's order."""
        shared: Optional[list[str]] = None
        for control in context.controls:
            labels = ops.preset_labels(control.node)
            if not labels:
                return []
            if shared is None:
                shared = list(labels)
            else:
                shared = [item for item in shared if item in labels]
        return shared or []

    def current(self, context) -> Optional[str]:
        """The preset every selected control is on, else None."""
        seen = set()
        answer = None
        for control in context.controls:
            labels = ops.preset_labels(control.node)
            if not labels:
                return None
            answer = ops.current_preset(control.node)
            seen.add(answer)
        return answer if len(seen) == 1 else None

    def apply(self, context, state: str, *, key: bool, times: Sequence[float]) -> str:
        """Switch every selected control, holding each one's pose."""
        done = 0
        for control in context.controls:
            if state not in ops.preset_labels(control.node):
                continue
            ops.switch_pivot_preset(control.node, state, key=key, times=times)
            done += 1
        if done == 1:
            return f"Snapped to {state} — pose held"
        return f"Snapped {done} controls to {state} — pose held"
```

This needs one more reader in `tik/trigger/maya/pivot.py`:

```python
def current_preset(control) -> Optional[str]:
    """The preset label ``control`` is currently on, or None."""
    node = _transform(control)
    labels = preset_labels(node)
    if not labels:
        return None
    index = int(node[PRESET_ATTR].value)
    return labels[index] if 0 <= index < len(labels) else None
```

- [ ] **Step 4: Draw `pivot.svg`**

Follow `AI/icon_rules.md`. A pivot is a point something turns about: a small
filled dot with an arc and an arrowhead sweeping round it, stroke-based, on the
same grid the action icons use. Read that file and match the family before
drawing.

- [ ] **Step 5: Run the tests**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_pivot_trigger.py -q`
Expected: PASS.

- [ ] **Step 6: Lint and commit**

```bash
python -m black src/python/tik tests && python -m isort src/python/tik tests && python -m flake8 src/python/tik tests
git add src/python/tik/trigger/anim/switches/pivot src/python/tik/trigger/maya/pivot.py tests/unit/test_pivot_trigger.py
git commit -m "Add the pivot switch tab"
```

---

### Task 4: The two placeholders

**Files:**
- Create: `src/python/tik/trigger/anim/switches/ikfk/__init__.py`, `ikfk.py`, `ikfk.svg`
- Create: `src/python/tik/trigger/anim/switches/polepin/__init__.py`, `polepin.py`, `polepin.svg`
- Modify: `src/python/tik/trigger/anim/switches/__init__.py`
- Test: `tests/unit/test_switch_registry.py` (append)

**Interfaces:**
- Produces: `IkFkSwitch` (`"ikfk"`, order 20), `PolePinSwitch` (`"polepin"`, order 30), both `available = False`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_switch_registry.py`:

```python
def test_the_shipped_switches_register_in_order():
    from tik.trigger.anim import switches  # noqa: F401 - registers them

    listed = [(item.switch_type, item.available) for item in iter_switches()]
    assert listed == [("pivot", True), ("ikfk", False), ("polepin", False)]


def test_a_placeholder_offers_no_states_and_says_why():
    from tik.trigger.anim import switches  # noqa: F401

    for name in ("ikfk", "polepin"):
        switch = get_switch(name)()
        assert switch.available is False
        assert switch.states(SwitchContext()) == []
        assert switch.help, f"{name} must say what it will do"
```

That test needs the autouse `clear_switches` fixture not to wipe the shipped
registrations — import the `switches` package inside the test *after* the
fixture has cleared, which re-runs the decorators only if the module has not
been imported yet. Make the fixture restore instead: capture the registry dict
before clearing and put it back afterwards.

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_switch_registry.py -q -k shipped`
Expected: FAIL — `ModuleNotFoundError: ...switches.ikfk`.

- [ ] **Step 3: Implement**

`src/python/tik/trigger/anim/switches/ikfk/ikfk.py`:

```python
"""Match and switch a limb between IK and FK. Declared, not built."""

from __future__ import annotations

from tik.trigger.anim.registry import register_switch
from tik.trigger.anim.switch import Switch


@register_switch("ikfk")
class IkFkSwitch(Switch):
    """Reserved: matches the other chain to the pose on screen, then flips."""

    label = "IK / FK"
    help = (
        "Will match the other chain to the pose on screen and flip the blend, "
        "holding the limb's silhouette."
    )
    order = 20
    available = False
```

`polepin/polepin.py`, the same shape:

```python
@register_switch("polepin")
class PolePinSwitch(Switch):
    """Reserved: locks the elbow to the pole control where it already is."""

    label = "Pin"
    help = (
        "Will lock the elbow to the pole control at its current position, "
        "holding the elbow's world position."
    )
    order = 30
    available = False
```

Each package's `__init__.py` re-exports its class. Then
`src/python/tik/trigger/anim/switches/__init__.py`:

```python
"""Built-in switches. Importing this package is what registers them."""

from . import ikfk, pivot, polepin  # noqa: F401 - imported for registration
```

- [ ] **Step 4: Draw the two icons**

`ikfk.svg` — two chains meeting at a joint with a swap arrow. `polepin.svg` — a
pin through a point. Read `AI/icon_rules.md` first and match the family; both
must read at 22px.

- [ ] **Step 5: Run the tests**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_switch_registry.py tests/unit/test_icon_assets.py -q`
Expected: PASS. `test_icon_assets.py` may assert every registered thing ships an
icon — read it and satisfy whatever it checks.

- [ ] **Step 6: Lint and commit**

```bash
python -m black src/python/tik tests && python -m isort src/python/tik tests && python -m flake8 src/python/tik tests
git add src/python/tik/trigger/anim/switches tests/unit/test_switch_registry.py
git commit -m "Declare the IK/FK and pole-pin switches as placeholders"
```

---

### Task 5: The shell

**Files:**
- Create: `src/python/tik/trigger/anim/window.py`
- Create: `tests/ui/test_switches_window.py`
- Modify: `src/python/tik/shared/ui/theme/__init__.py` (a few `TOOL_QSS` rules)

**Interfaces:**
- Consumes: `Switch`, `SwitchContext`, `iter_switches` (Tasks 2–4).
- Produces:
  - `SwitchesWindow(MayaToolWindow)` — `WINDOW_NAME = "TikSwitchesWindow"`.
  - `SwitchesWindow.set_context(context)` — render a context; **the seam the UI tests drive**, with no Maya anywhere near it.
  - `SwitchesWindow.pending`, `.current_switch`, `.can_apply` — read by tests.
  - `SwitchesWindow.apply()` — runs the pending switch.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_switches_window.py`:

```python
"""The Switches shell, offscreen, against a fabricated context."""

import pytest

from tik.trigger.anim.context import Control, SwitchContext
from tik.trigger.anim.registry import clear_switches, register_switch
from tik.trigger.anim.switch import Switch
from tik.trigger.anim.window import SwitchesWindow


@pytest.fixture(autouse=True)
def _switches():
    clear_switches()

    @register_switch("toy")
    class Toy(Switch):
        label = "Toy"
        help = "A toy switch."
        order = 10

        def states(self, context):
            return ["a", "b", "c"] if context.controls else []

        def current(self, context):
            return {1: "a", 2: None}.get(len(context.controls))

        def apply(self, context, state, *, key, times):
            self.applied = (state, key, tuple(times))
            return f"Switched to {state}"

    @register_switch("later")
    class Later(Switch):
        label = "Later"
        help = "Not built yet."
        order = 20
        available = False

    yield
    clear_switches()


def _one():
    return SwitchContext(
        nodes=("|a",),
        controls=(Control(node="|a", role="ik", side="L", module="arm"),),
    )


def _two():
    return SwitchContext(
        nodes=("|a", "|b"),
        controls=(
            Control(node="|a", role="ik", side="L", module="arm"),
            Control(node="|b", role="ik", side="R", module="arm"),
        ),
    )


def test_a_tab_per_switch_in_order(qapp):
    window = SwitchesWindow()
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
        "Toy",
        "Later",
    ]


def test_empty_selection_disables_apply_and_says_so(qapp):
    window = SwitchesWindow()
    window.set_context(SwitchContext())
    assert window.can_apply is False
    assert "Select" in window.context_label.text()


def test_one_control_shows_its_current_state_filled(qapp):
    window = SwitchesWindow()
    window.set_context(_one())
    assert window.states == ["a", "b", "c"]
    assert window.current == "a"
    assert window.pending is None
    assert window.can_apply is False


def test_choosing_a_state_arms_apply(qapp):
    window = SwitchesWindow()
    window.set_context(_one())
    window.choose("b")
    assert window.pending == "b"
    assert window.can_apply is True


def test_choosing_the_current_state_does_not_arm_apply(qapp):
    window = SwitchesWindow()
    window.set_context(_one())
    window.choose("a")
    assert window.can_apply is False


def test_a_mixed_selection_arms_apply_for_any_state(qapp):
    window = SwitchesWindow()
    window.set_context(_two())
    assert window.current is None
    window.choose("a")
    assert window.can_apply is True


def test_apply_runs_the_switch_and_reports(qapp):
    window = SwitchesWindow()
    window.set_context(_one())
    window.choose("c")
    window.apply()
    assert window.status_label.text() == "Switched to c"
    assert window.pending is None


def test_a_placeholder_tab_shows_its_help_and_never_applies(qapp):
    window = SwitchesWindow()
    window.set_context(_one())
    window.tabs.setCurrentIndex(1)
    assert window.states == []
    assert window.can_apply is False
    assert "Not built yet" in window.body_note.text()
    assert "Not built yet" not in window.status_label.text()


def test_the_range_button_names_the_range(qapp):
    window = SwitchesWindow()
    window.set_playback_range(1.0, 120.0)
    assert window.range_button.text() == "Range 1–120"
```

`qapp` comes from `tests/ui/conftest.py` — check its name there and use it.

- [ ] **Step 2: Run to verify they fail**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/ui/test_switches_window.py -q`
Expected: FAIL — `ModuleNotFoundError: ...anim.window`.

- [ ] **Step 3: Implement `window.py`**

The four zones from the spec, built with `tik.shared.ui.Qt` widgets:

- `self.tabs` — a `QTabBar` (not a `QTabWidget`; the body is a plain widget the
  window swaps, which keeps the context strip and action bar outside the tab
  pane where the design puts them). Each tab's icon is a dot pixmap: accent when
  the switch offers states, `theme.STATUS[""]` when it does not. Write a module
  helper `_dot(color, size=8) -> QtGui.QIcon` that paints a filled circle on a
  transparent pixmap.
- `self.context_label` / side swatches — a `QFrame` styled `#SwitchContext`.
- The picker — a `QWidget` with a `QHBoxLayout` of checkable `QPushButton`s,
  object name `SwitchChip`, rebuilt on every `set_context`. `setProperty("state",
  "current" | "pending" | "mixed")` and re-polish, so the look lives in the
  stylesheet rather than in Python.
- `self.body_note` — a `QLabel` for the help line, the placeholder line, or the
  "nothing selected" line.
- The action bar — `self.key_box` (`QCheckBox`), `self.frame_button` /
  `self.range_button` (checkable, exclusive via a `QButtonGroup`),
  `self.apply_button` (`objectName("PrimaryButton")`), `self.status_dot`,
  `self.status_label`.

Key methods:

```python
    def set_context(self, context) -> None:
        """Render ``context``: tab availability, chips, current state."""

    def choose(self, state: str) -> None:
        """Mark ``state`` pending (clears when it equals the current state)."""

    def apply(self) -> None:
        """Run the pending switch on the current context."""

    @property
    def can_apply(self) -> bool:
        """True when there is a pending state that differs from the current."""
```

`apply()` collects `times` from the frame/range choice: `Frame` gives
`(current_time,)`, `Range` gives the union of key times. Both need Maya, so guard
them behind `HAS_MAYA` and let the tests inject: give the window a
`times_provider` attribute defaulting to a function that reads Maya, which the
UI tests replace. Keep the Maya import inside that default function.

Refresh on selection: in `__init__`, when `HAS_MAYA`, install a `SceneWatcher`
on `("SelectionChanged", "Undo", "Redo")` whose callback is
`lambda _event: self.set_context(SwitchContext.from_scene())`, and register its
job ids through `MayaToolWindow.register_script_job` so teardown kills them.

Add to `theme.TOOL_QSS`:

```
#SwitchContext { background-color: #2a2a2a; border-bottom: 1px solid #303030; }
#SwitchChip { background-color: #282828; border: 1px solid #353535; border-radius: 3px; color: #c8c8c8; min-height: 20px; width: auto; min-width: 0; padding: 3px 12px; }
#SwitchChip:hover { border-color: #FE7E00; }
#SwitchChip[state="current"] { background-color: #3a2e1f; border-color: #FE7E00; color: #e0c8a8; }
#SwitchChip[state="pending"] { border-color: #FE7E00; color: #e0c8a8; }
#SwitchChip[state="mixed"] { border-style: dashed; border-color: #6a5a44; color: #a89478; }
#SwitchBar { background-color: #1e1e1e; border-top: 1px solid #353535; }
#SwitchNote { color: #7b7b7b; font-size: 11px; }
```

`QPushButton` in the base theme sets `width: 100px`; the chip rule must override
it with `width: auto; min-width: 0` or every chip comes out 100px wide.

- [ ] **Step 4: Run the tests**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/ui -q`
Expected: PASS, whole directory.

- [ ] **Step 5: Lint and commit**

```bash
python -m black src/python/tik tests && python -m isort src/python/tik tests && python -m flake8 src/python/tik tests
git add src/python/tik/trigger/anim/window.py src/python/tik/shared/ui/theme/__init__.py tests/ui/test_switches_window.py
git commit -m "Add the Switches dock shell"
```

---

### Task 6: Launch, and remove the modal dialog

**Files:**
- Modify: `src/python/tik/trigger/anim/__init__.py`
- Modify: `src/python/tik/trigger/ui/main.py`
- Test: `tests/ui/test_menus.py`

**Interfaces:**
- Produces: `tik.trigger.anim.show(dockable=True) -> SwitchesWindow`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_menus.py`, matching however that file already inspects
the menu bar:

```python
def test_tools_menu_offers_switches_and_not_the_old_dialog(qapp):
    window = _window()  # whatever the file's existing helper is
    labels = [action.text() for action in window._menus["&Tools"].actions()]
    assert "Switches" in labels
    assert not any("Switch Pivot" in text for text in labels)
```

- [ ] **Step 2: Run to verify it fails**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/ui/test_menus.py -q -k switches`
Expected: FAIL.

- [ ] **Step 3: Add the launcher**

Append to `src/python/tik/trigger/anim/__init__.py`:

```python
def show(dockable: bool = True):
    """Open (or re-open) the single Switches window."""
    from tik.shared.ui.scene_watcher import SceneWatcher

    from . import switches  # noqa: F401 - registers the built-in switches
    from .window import SwitchesWindow

    SceneWatcher.uninstall_all()
    SwitchesWindow.teardown_workspace_control()
    window = SwitchesWindow()
    window.show_tool(dockable=dockable)
    return window
```

The imports are inside the function on purpose: `tests/unit/test_switch_registry.py`
imports this package without a QApplication.

- [ ] **Step 4: Swap the menu entry**

In `src/python/tik/trigger/ui/main.py`:

- in `_build_tools_menu`, replace the `"Switch Pivot (Preserve)…"` action with
  `self._action(tools_menu, "Switches", self.open_switches, "Ctrl+Shift+W")`
  (check no other action already binds that shortcut; drop the shortcut if one
  does);
- delete `switch_pivot_preset` and `_selected_pivot_controls`;
- add:

```python
    def open_switches(self) -> None:
        """Open the animator's Switches dock."""
        from tik.trigger import anim

        anim.show()
```

`Feedback.ask_choice` stays (spec Part 5).

- [ ] **Step 5: Run the tests**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/ui -q`
Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy tests/unit/invoke.py`
Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy tests/integration/invoke.py`
Expected: PASS.

- [ ] **Step 6: Lint and commit**

```bash
python -m black src/python/tik tests && python -m isort src/python/tik tests && python -m flake8 src/python/tik tests
git add src/python/tik/trigger/anim/__init__.py src/python/tik/trigger/ui/main.py tests/ui/test_menus.py
git commit -m "Launch the Switches dock and retire the modal pivot dialog"
```

---

### Task 7: Documentation

**Files:**
- Modify: `CLAUDE.md`, `AI/coding_rules.md`

- [ ] **Step 1: `CLAUDE.md`**

In the tik.trigger **Status** paragraph, after the movable-pivot sentence:

```
Animator-facing tools live in `tik/trigger/anim` and **read the rig, never the
session** — the package may not import `trigger.session`, the documents, the
guides or `trigger.ui` (`tests/unit/test_import_boundaries.py`). The
**Switches** dock (`tik.trigger.anim.show()`, or `Tools > Switches`) is a
non-modal, dockable tool that follows the selection; each tab is a
`@register_switch` class supplying `states` / `current` / `apply`, and nothing
else in the shell touches Maya. Pivot presets ship; IK/FK and the pole pin are
declared placeholders.
```

Add the spec to the **Design specs** list and
`tests/unit/test_switch_registry.py` + `tests/ui/test_switches_window.py` to the
tests list.

- [ ] **Step 2: `AI/coding_rules.md`**

Add a short section after the module ground rules:

```
### Animator switches

A switch changes what a control *does*, and the pose survives it. That is the
whole entry test for a tab in the Switches dock: name what it promises not to
disturb, or it is not a switch. A switch is a `@register_switch` class with
`states` / `current` / `apply`; the scene work is a plain function in
`tik/trigger/maya`, so a shelf button can call it without opening a window.
```

- [ ] **Step 3: Verify and commit**

```bash
python -m black src/python/tik tests && python -m isort src/python/tik tests && python -m flake8 src/python/tik tests
PYTHONPATH="D:/dev/tikworks/src/python" mayapy tests/unit/invoke.py
PYTHONPATH="D:/dev/tikworks/src/python" mayapy tests/integration/invoke.py
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/ui -q
git add CLAUDE.md AI/coding_rules.md
git commit -m "Document the animator switches dock"
```
