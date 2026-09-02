# Arm Module Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply ten revision findings to the arm — seven mechanical corrections plus offset/tweak controls, module-level animation spaces (including graph-view authoring), and auto-collar.

**Architecture:** Six phases. A fixes mechanical defects in `systems/limb.py` and `ChainLengths`. B adds tweak controls, which become the rig's drivers. C adds a `Space` manifest declaration, its storage, and a post-build connection pass. D adds auto-collar. E adds multi-wire space ports to the node graph. F verifies the whole arm.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), `tik.maya` wrapper, Qt (via `tik.shared.ui`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-arm-module-revision-design.md`

## Global Constraints

- **No third-party dependencies.** Stdlib and Maya-bundled modules only.
- **Maya 2024+.** `NodeNames.uses_native_math_nodes` is `maya_version >= 2025`; anything using a native math node needs a pre-2025 fallback.
- **No raw `cmds` / `OpenMaya` outside `tik.maya`.** `tik/trigger/systems/` and module bodies consume `tik.maya` only.
- **The animator-opinion rule.** A `tik.maya` construct never creates a controller, names a user-facing attribute, or encodes a side convention.
- **Module ground rules** (from the previous spec, all still binding): four groups per module; bind joints carry live TRS; one bind hierarchy; every output is a bind joint; every controller declares a mirror rule; no controller outside `control_grp`; no evaluation cycle. **This plan adds a ninth: a module parents everything it creates.**
- **Test commands:**
  - Unit/integration: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest <path> -v`
  - UI: `set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui -q`
  - Full: `make tests-unit`, `make tests-integration`, `make tests-ui`
- **Commit after every task.** Never `--no-verify`. Never push.

---

## File Structure

| File | Responsibility | Phase |
|---|---|---|
| `src/python/tik/maya/constructs/chain_lengths.py` (modify) | `parent=` argument | A |
| `src/python/tik/trigger/systems/limb.py` (modify) | naming, derived size, lock/hide, hinge, separators, switch, tweaks, auto-collar | A,B,D |
| `src/python/tik/trigger/modules/arm/arm.py` (modify) | fields removed, spaces declared, auto-collar hookup | A,C,D |
| `src/python/tik/trigger/backends/maya/context.py` (modify) | `tweak_control` | B |
| `src/python/tik/trigger/core/context.py` (modify) | `tweak_control` protocol | B |
| `src/python/tik/trigger/core/manifest.py` (modify) | `Space` dataclass | C |
| `src/python/tik/trigger/core/module.py` (modify) | `spaces`, `space_names()`, `get_space()` | C |
| `src/python/tik/trigger/core/schemas.py` (modify) | `ModuleInstance.spaces` | C |
| `src/python/tik/trigger/core/builder.py` (modify) | post-build space pass | C |
| `src/python/tik/trigger/backends/maya/tags.py` (modify) | `SPACES` | C |
| `src/python/tik/trigger/backends/maya/backend.py` (modify) | persist spaces, `connect_space` | C |
| `src/python/tik/trigger/guides/handler.py` (modify) | `spaces` property, `set_space`, mirror | C |
| `src/python/tik/trigger/ui/graph_view.py` (modify) | multi ports, space wires | E |

---

## Phase A — Mechanical Corrections

### Task 1: `ChainLengths` parent, and the ninth ground rule

**Files:**
- Modify: `src/python/tik/maya/constructs/chain_lengths.py:44-80`
- Modify: `src/python/tik/trigger/systems/limb.py` (two `ChainLengths.create` calls in `_build_lengths`)
- Test: `tests/unit/test_chain_lengths.py` (append), `tests/integration/trigger/test_module_ground_rules.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `ChainLengths.create(joints, *, side_sign=1, name=None, parent=None)`. When `parent` is given the holder is created under it.

**Background:** the holder is created with no parent (`chain_lengths.py:71`), leaving `L_arm_arm_ik_lengths_grp` and `L_arm_arm_fk_lengths_grp` at the world root. It is the only unparented DAG node the limb makes, which is why exactly two appeared.

- [ ] **Step 1: Write the failing construct test**

Append to `tests/unit/test_chain_lengths.py`:

```python
def test_holder_is_parented_when_asked():
    joints = _chain("parented")
    holder_parent = tm.Transform.create(name="lengths_home")
    lengths = tm.ChainLengths.create(joints, name="parented", parent=holder_parent)
    assert lengths.holder.parent.name == holder_parent.name


def test_holder_defaults_to_the_world():
    joints = _chain("rootlevel")
    lengths = tm.ChainLengths.create(joints, name="rootlevel")
    assert lengths.holder.parent is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_chain_lengths.py -k parent -v`
Expected: FAIL — `TypeError: create() got an unexpected keyword argument 'parent'`

- [ ] **Step 3: Add the parameter**

In `src/python/tik/maya/constructs/chain_lengths.py`, add `parent=None` to `create`'s keyword-only arguments (after `name`), document it in the docstring's `Args:` block as:

```
            parent: Optional parent for the construct's holder transform.
```

and replace the holder creation line:

```python
        chain.holder = Transform.create(
            name=f"{chain.name}_lengths_grp",
            parent=parent.long_name if hasattr(parent, "long_name") else parent,
        )
```

- [ ] **Step 4: Pass the parent from the limb**

In `src/python/tik/trigger/systems/limb.py`, `_build_lengths`, both calls become:

```python
    result.ik_lengths = tm.ChainLengths.create(
        result.ik_joints,
        side_sign=side_sign,
        name=ctx.name(name, "ik"),
        parent=ctx.groups.rig,
    )
    result.fk_lengths = tm.ChainLengths.create(
        result.fk_joints,
        side_sign=side_sign,
        name=ctx.name(name, "fk"),
        parent=ctx.groups.rig,
    )
```

- [ ] **Step 5: Write the ground-rule test**

Append to `tests/integration/trigger/test_module_ground_rules.py`:

```python
@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_module_parents_everything_it_creates(module_type):
    """Rule 1.7: nothing a module builds is left at the world root."""
    cmds.file(new=True, force=True)
    backend = trigger.maya_backend()
    before = set(cmds.ls(assemblies=True, long=True))

    module = get_module(module_type)(name=module_type)
    instance = backend.create_guides(module)
    if get_module(module_type).primary_input() is not None:
        cmds.file(new=True, force=True)
        backend = trigger.maya_backend()
        before = set(cmds.ls(assemblies=True, long=True))
        body = backend.create_guides(get_module("base")(name="body"))
        instance = backend.create_guides(
            get_module(module_type)(name=module_type),
            parent=ParentRef(body.instance_id, "root"),
        )
    Builder(backend).build(rig_name="rules", afterlife="delete")

    stray = set(cmds.ls(assemblies=True, long=True)) - before - {"|rules_rig"}
    assert not stray, f"'{module_type}' left {sorted(stray)} at the world root"
```

- [ ] **Step 6: Run both suites**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_chain_lengths.py tests/integration/trigger/test_module_ground_rules.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/maya/constructs/chain_lengths.py src/python/tik/trigger/systems/limb.py tests/unit/test_chain_lengths.py tests/integration/trigger/test_module_ground_rules.py
git commit -m "fix(tik.maya): ChainLengths parents its holder; add the parents-everything ground rule"
```

---

### Task 2: Limb naming and derived controller size

**Files:**
- Modify: `src/python/tik/trigger/systems/limb.py`
- Modify: `src/python/tik/trigger/modules/arm/arm.py`
- Test: `tests/integration/trigger/test_arm_trigger.py` (modify), `tests/integration/trigger/test_limb_system.py` (modify)

**Interfaces:**
- Consumes: `ChainLengths.create(..., parent=)` from Task 1.
- Produces:
  - `build_ikfk_limb(ctx, guides, *, name="", parent=None, bind_joints=None, controller_size=None, soft_ik=True, stretch=True, squash=True, stretch_limit_default=50.0, pole_pin=False, labels=None)`
  - Module-level helper `_role(*parts) -> str` in `limb.py`, joining non-empty parts with `_`.
  - `LimbResult.size: float` — the derived base controller size.
  - Arm loses the `controller_size` and `stretch_limit` fields.

**Background:** `ctx.name` already prefixes the instance name, so passing `name="arm"` produced `L_arm_arm_ik_ctrl`. `f"{name}_ik"` with an empty name would give `"_ik"` and a doubled underscore, hence `_role`.

- [ ] **Step 1: Write the failing tests**

In `tests/integration/trigger/test_arm_trigger.py`, replace the existing
`_ik_control` helper and `test_has_no_ik_solver_ribbon_or_soft_ik_fields` with:

```python
def _ik_control(ctx):
    return next(
        item.transform
        for item in ctx.controllers
        if item.transform.name.endswith("_ik_ctrl")
    )


def test_has_only_the_behaviour_fields():
    names = set(get_module("arm").fields())
    assert names == {"stretch", "squash", "pole_pin"}


def test_control_names_carry_one_module_token(backend):
    """L_arm_ik_ctrl, not L_arm_arm_ik_ctrl."""
    ctx = _arm_ctx(backend)
    names = {item.transform.name for item in ctx.controllers}
    assert "L_arm_ik_ctrl" in names
    assert "L_arm_pole_ctrl" in names
    assert not any("_arm_arm_" in name for name in names)


def test_controller_size_scales_with_the_limb(backend):
    """No size field: size is derived from the chain length."""
    from tik.trigger.systems.limb import _derive_size

    short = tm.Joint.chain(
        [(0, 0, 0), (4, 0, -1), (8, 0, 0)], name_pattern="short_{index}"
    )
    long_chain = tm.Joint.chain(
        [(0, 0, 0), (40, 0, -1), (80, 0, 0)], name_pattern="long_{index}"
    )
    assert _derive_size(short) > 0
    assert _derive_size(long_chain) > _derive_size(short)
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_arm_trigger.py -q`
Expected: FAIL — `ImportError: cannot import name '_derive_size'`, plus assertion failures on `_arm_arm_`.

- [ ] **Step 3: Add `_role` and `_derive_size` to the limb**

Add near the bottom of `src/python/tik/trigger/systems/limb.py`, beside `_pole_rest_position`:

```python
def _role(*parts) -> str:
    """Join non-empty name parts.

    An empty limb name must add no token: ``f"{name}_ik"`` would yield ``"_ik"``
    and a doubled underscore once ``ctx.name`` prefixes the instance.
    """
    return "_".join(part for part in parts if part)


def _derive_size(joints: Sequence) -> float:
    """Base controller size from the chain's rest length."""
    total = 0.0
    for first, second in zip(joints, joints[1:]):
        total += first.distance_to(second)
    return total * 0.15
```

- [ ] **Step 4: Use them in the limb**

In `build_ikfk_limb`, change the signature defaults `name: str = ""` and
`controller_size: Optional[float] = None`, and after the guard block add:

```python
    if controller_size is None:
        controller_size = _derive_size(guides)
    result.size = controller_size
```

Add `size: float = 0.0` to the `LimbResult` dataclass fields.

In `_build_controls`, replace every controller role f-string with `_role`:

```python
    result.ik_control = ctx.controller(
        _role(name, "ik"), shape="Cube", size=size, ...
    )
    result.switch_control = ctx.controller(
        _role(name, "switch"), shape="Cube", size=size * 0.4, ...
    )
    ...
        fk_control = ctx.controller(
            _role(name, "fk", label), shape="Circle", size=size, ...
        )
```

and in `_build_pole`:

```python
    result.pole_control = ctx.controller(
        _role(name, "pole"), shape="Diamond", size=size * 0.5, ...
    )
```

- [ ] **Step 5: Drop the arm's two fields**

In `src/python/tik/trigger/modules/arm/arm.py`, delete the `stretch_limit` and
`controller_size` field declarations, drop `FloatField` from the import if it
becomes unused, and change `build` to derive the size and stop passing a name:

```python
    def build(self, ctx) -> None:
        collar_guide = ctx.guide("collar")
        limb_guides = [ctx.guide("shoulder"), ctx.guide("elbow"), ctx.guide("hand")]
        size = _derive_size(limb_guides)
```

Import it: `from tik.trigger.systems.limb import _derive_size, build_ikfk_limb`.

Then in the `build_ikfk_limb(...)` call remove `name="arm"`, remove
`controller_size=size` (leave it defaulted) and remove
`stretch_limit_default=self.stretch_limit`.

Keep `size` for the collar controller.

- [ ] **Step 6: Fix the limb tests that passed a name**

In `tests/integration/trigger/test_limb_system.py`, `_limb` currently passes
`name="limb"`. Leave it — the parameter still works — but add:

```python
def test_empty_name_adds_no_token(build_context):
    ctx = build_context()
    guides = tm.Joint.chain(
        [(0, 0, 0), (4, 0, -1), (8, 0, 0)], name_pattern="noname_guide_{index}"
    )
    result = build_ikfk_limb(ctx, guides, labels=("upper", "lower", "end"))
    assert result.ik_control.transform.name == "C_probe_ik_ctrl"
```

- [ ] **Step 7: Run the suites**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/systems/limb.py src/python/tik/trigger/modules/arm tests/integration/trigger
git commit -m "refactor(tik.trigger): single module name token, controller size derived from limb length"
```

---

### Task 3: Lock/hide and the derived hinge axis

**Files:**
- Modify: `src/python/tik/trigger/systems/limb.py`
- Modify: `src/python/tik/trigger/modules/arm/arm.py` (collar locking)
- Test: `tests/integration/trigger/test_limb_system.py` (append)

**Interfaces:**
- Consumes: `_role`, `LimbResult.size` from Task 2.
- Produces:
  - `_hinge_axis(joints) -> Optional[str]` in `limb.py` — returns `"x"`, `"y"`, `"z"`, or `None` for a degenerate (straight) chain.
  - `LimbResult.hinge_axis: Optional[str]`.

**Background:** the middle FK control must keep exactly one rotation axis. Which one is a fact about the guides, not a convention, so it is derived: the bend-plane normal is `axis x bend`, and the hinge is whichever of the middle joint's local axes is most parallel to it. A straight chain has no bend plane; locking the wrong two axes there is worse than locking none.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_limb_system.py`:

```python
def _locked(transform, attr):
    return cmds.getAttr(f"{transform.long_name}.{attr}", lock=True)


def _hidden(transform, attr):
    return not cmds.getAttr(f"{transform.long_name}.{attr}", keyable=True)


def test_ik_control_locks_scale_and_visibility(build_context):
    result, _binds = _limb(build_context())
    control = result.ik_control.transform
    for attr in ("sx", "sy", "sz", "v"):
        assert _locked(control, attr) and _hidden(control, attr)
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
        assert not _locked(control, attr)


def test_fk_controls_lock_translate(build_context):
    result, _binds = _limb(build_context())
    for control in (item.transform for item in result.fk_controls):
        for attr in ("tx", "ty", "tz", "sx", "sy", "sz", "v"):
            assert _locked(control, attr), f"{control.name}.{attr} should be locked"


def test_middle_fk_control_keeps_only_the_hinge(build_context):
    result, _binds = _limb(build_context())
    assert result.hinge_axis == "y"  # elbow bends in the XZ plane
    middle = result.fk_controls[1].transform
    assert not _locked(middle, "ry")
    assert _locked(middle, "rx") and _locked(middle, "rz")


def test_root_and_end_fk_keep_every_rotation(build_context):
    result, _binds = _limb(build_context())
    for control in (result.fk_controls[0].transform, result.fk_controls[-1].transform):
        for attr in ("rx", "ry", "rz"):
            assert not _locked(control, attr)


def test_straight_chain_locks_no_rotation(build_context):
    """No bend plane means no derivable hinge; locking two axes would guess."""
    ctx = build_context()
    guides = tm.Joint.chain(
        [(0, 0, 0), (4, 0, 0), (8, 0, 0)], name_pattern="straight_{index}"
    )
    result = build_ikfk_limb(ctx, guides, labels=("upper", "lower", "end"))
    assert result.hinge_axis is None
    middle = result.fk_controls[1].transform
    for attr in ("rx", "ry", "rz"):
        assert not _locked(middle, attr)
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_limb_system.py -k "lock or hinge or straight" -v`
Expected: FAIL — `AttributeError: 'LimbResult' object has no attribute 'hinge_axis'`

- [ ] **Step 3: Add `_hinge_axis`**

Add beside `_pole_rest_position` in `limb.py`:

```python
def _hinge_axis(joints: Sequence) -> Optional[str]:
    """Which local axis of the middle joint the chain bends about.

    The bend-plane normal is ``chain axis x bend direction``; the hinge is the
    middle joint's local axis most parallel to it. Returns ``None`` for a
    straight chain, which has no bend plane -- guessing two axes to lock would
    be worse than locking none.
    """
    start = joints[0].world_position
    middle = joints[len(joints) // 2]
    mid = middle.world_position
    end = joints[-1].world_position

    axis = end - start
    to_mid = mid - start
    if axis.length() < 1e-6:
        return None
    projection = start + axis * ((to_mid * axis) / (axis * axis))
    bend = mid - projection
    if bend.length() < 1e-4:
        return None

    normal = axis ^ bend
    normal.normalize()
    best, best_dot = None, 0.0
    for name in ("x", "y", "z"):
        dot = abs(middle.world_axis(name) * normal)
        if dot > best_dot:
            best, best_dot = name, dot
    return best
```

Add `hinge_axis: Optional[str] = None` to `LimbResult`.

- [ ] **Step 4: Apply the locking**

In `_build_controls`, replace the FK loop body's locking line and add per-control
locking. The full loop becomes:

```python
    result.hinge_axis = _hinge_axis(result.fk_joints)
    fk_parent = None
    last = len(labels) - 1
    for index, (label, joint) in enumerate(zip(labels, result.fk_joints)):
        fk_control = ctx.controller(
            _role(name, "fk", label),
            shape="Circle",
            size=size,
            parent=fk_parent if fk_parent is not None else ctx.groups.control,
            match=joint,
            mirror="behaviour",
        )
        offset = fk_control.transform.create_offset_group(
            name=ctx.name(name, "fk", label, suffix="offset")
        )
        if fk_parent is None:
            tm.MatrixConstraint.create(parent, offset, maintain_offset=True)
        locked = ["tx", "ty", "tz", "sx", "sy", "sz", "v"]
        if 0 < index < last and result.hinge_axis is not None:
            # An elbow or knee is a hinge: only the derived axis stays.
            locked += [f"r{axis}" for axis in "xyz" if axis != result.hinge_axis]
        attribute.lock_and_hide(fk_control.transform, locked)
        tm.MatrixConstraint.create(
            fk_control.transform, joint, maintain_offset=True, skip_scale="xyz"
        )
        result.fk_controls.append(fk_control)
        fk_parent = fk_control.transform
```

For the IK control, immediately after its offset group is created:

```python
    attribute.lock_and_hide(result.ik_control.transform, ("sx", "sy", "sz", "v"))
```

The pole control already locks `rx ry rz sx sy sz v` in `_build_pole`; leave it.

- [ ] **Step 5: Lock the collar in the arm**

In `src/python/tik/trigger/modules/arm/arm.py`, after the collar offset group is
created:

```python
        attribute.lock_and_hide(collar_ctrl.transform, ("sx", "sy", "sz", "v"))
```

Import it: `from tik.maya import attribute`.

- [ ] **Step 6: Run the suites**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/systems/limb.py src/python/tik/trigger/modules/arm tests/integration/trigger/test_limb_system.py
git commit -m "feat(tik.trigger): lock non-animatable channels, derive the hinge axis from the guides"
```

---

### Task 4: Separators, and the switch moves onto the IK control

**Files:**
- Modify: `src/python/tik/trigger/systems/limb.py`
- Test: `tests/integration/trigger/test_limb_system.py` (append), `tests/integration/trigger/test_arm_trigger.py` (modify)

**Interfaces:**
- Consumes: everything from Tasks 2 and 3.
- Produces: `LimbResult.switch_control` becomes `None`; `LimbResult.switch_plug` is the `ikFk` plug on the IK control.

**Background:** hiding the IK controls at `ikFk = 0` would strand the switch. The FK proxies are what make removal safe — whichever set is visible can always switch back.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_limb_system.py`:

```python
def test_no_separate_switch_control(build_context):
    result, _binds = _limb(build_context())
    assert result.switch_control is None
    assert not [
        item for item in result.fk_controls if "switch" in item.transform.name
    ]
    assert result.switch_plug.node.name.endswith("_ik_ctrl")


def test_every_fk_control_proxies_the_switch(build_context):
    result, _binds = _limb(build_context())
    for control in (item.transform for item in result.fk_controls):
        assert control.has_attr("ikFk")
    result.switch_plug.value = 0.0
    for control in (item.transform for item in result.fk_controls):
        assert abs(control["ikFk"].value) < 1e-6


def test_switch_is_reachable_from_fk_when_ik_is_hidden(build_context):
    """The reason removing the switch control is safe."""
    result, _binds = _limb(build_context())
    result.switch_plug.value = 0.0
    assert not result.ik_control.transform.parent.visibility
    # An animator in FK flips it back through the proxy.
    result.fk_controls[0].transform["ikFk"].value = 1.0
    assert result.ik_control.transform.parent.visibility


def test_ik_control_has_separators(build_context):
    result, _binds = _limb(build_context())
    control = result.ik_control.transform
    for separator in ("ikfk_", "stretch_", "segments_", "pole_"):
        assert control.has_attr(separator)
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_limb_system.py -k "switch or separator" -v`
Expected: FAIL — `assert <Controller ...> is None`

- [ ] **Step 3: Remove the switch control and add separators**

In `_build_controls`, delete the whole `result.switch_control = ctx.controller(...)`
block through `result.switch_plug = attribute.add_float(result.switch_control...)`,
and replace it with, immediately after the IK control's lock line:

```python
    attribute.add_separator(result.ik_control.transform, "ikfk_")
    result.switch_plug = attribute.add_float(
        result.ik_control.transform, "ikFk", default=1.0, min=0.0, max=1.0
    )
```

- [ ] **Step 4: Add the FK proxies**

At the end of the FK loop in `_build_controls`, after `result.fk_controls.append(...)`:

```python
        # The switch must stay reachable from whichever set is visible: at
        # ikFk = 0 the IK controls are hidden, so FK carries the proxy.
        attribute.add_proxy(fk_control.transform, result.switch_plug, name="ikFk")
```

`result.switch_plug` must therefore exist before the FK loop runs — move the FK
loop so it follows the IK control block (it already does).

- [ ] **Step 5: Group the remaining attributes under separators**

In `build_ikfk_limb`, wrap the segment-scale block:

```python
    attribute.add_separator(control, "segments_")
    segment_scales = [
        attribute.add_float(control, f"s{label.capitalize()}", default=1.0, min=0.001)
        for label in labels[:-1]
    ]
```

In `_build_stretch`, before the `if stretch:` block:

```python
    if stretch or squash:
        attribute.add_separator(control, "stretch_")
```

In `_build_pole`, before `pole_follow`:

```python
    attribute.add_separator(control, "pole_")
```

- [ ] **Step 6: Drop the switch from the dataclass docs**

Change `LimbResult.switch_control` to keep the field but document it:

```python
    switch_control: object = None  # retired; ikFk lives on the IK control
```

- [ ] **Step 7: Update the arm test that looked for a switch control**

In `tests/integration/trigger/test_arm_trigger.py`, replace
`test_hand_follows_ik_when_switched` with:

```python
def test_hand_follows_ik_when_switched(backend):
    ctx = _arm_ctx(backend)
    control = _ik_control(ctx)
    control["ikFk"].value = 1.0
    before = ctx.outputs["hand"].world_translation
    control.translate = tuple(
        value + shift for value, shift in zip(control.translate, (0, 3, 0))
    )
    after = ctx.outputs["hand"].world_translation
    assert (after - before).length() > 1.0
```

- [ ] **Step 8: Run the suites**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/python/tik/trigger/systems/limb.py tests/integration/trigger
git commit -m "feat(tik.trigger): ikFk moves to the IK control with FK proxies, plus attribute separators"
```

---

## Phase B — Tweak Controls

### Task 5: `ctx.tweak_control`

**Files:**
- Modify: `src/python/tik/trigger/core/context.py` (`BuildContext` protocol)
- Modify: `src/python/tik/trigger/backends/maya/context.py`
- Modify: `tests/helpers/trigger_fakes.py`
- Test: `tests/unit/test_maya_backend_trigger.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `ctx.tweak_control(main, *, size=None, shape="Circle") -> Controller`.
  Creates `<main role>_tweak` as a child of `main.transform`, adds a non-keyable
  `tweakVis` bool on the main (default `False`) wired to the tweak's
  `visibility`, copies the main's `trg_mirror` tag, mirrors the main's locked
  channels, and appends the tweak to `ctx.controllers`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_maya_backend_trigger.py`:

```python
def test_tweak_control_is_a_child_of_its_main(backend):
    ctx = _built(backend)
    main = ctx.controller("hand", mirror="world")
    tweak = ctx.tweak_control(main)
    assert tweak.transform.parent.name == main.transform.name
    assert tweak.transform.name.endswith("_hand_tweak_ctrl")
    assert tweak in ctx.controllers


def test_tweak_visibility_comes_from_the_main(backend):
    ctx = _built(backend)
    main = ctx.controller("hand", mirror="world")
    tweak = ctx.tweak_control(main)
    assert main.transform.has_attr("tweakVis")
    assert not tweak.transform.visibility
    main.transform["tweakVis"].value = True
    assert tweak.transform.visibility


def test_tweak_copies_the_mirror_rule(backend):
    ctx = _built(backend)
    main = ctx.controller("hand", mirror="world")
    tweak = ctx.tweak_control(main)
    assert tweak.transform.meta[tags.MIRROR] == tags.WORLD


def test_tweak_inherits_locked_channels(backend):
    ctx = _built(backend)
    main = ctx.controller("hand", mirror="world")
    tm.attribute.lock_and_hide(main.transform, ("sx", "sy", "sz", "v"))
    tweak = ctx.tweak_control(main)
    for attr in ("sx", "sy", "sz"):
        assert cmds.getAttr(f"{tweak.transform.long_name}.{attr}", lock=True)
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_maya_backend_trigger.py -k tweak -v`
Expected: FAIL — `AttributeError: 'MayaBuildContext' object has no attribute 'tweak_control'`

- [ ] **Step 3: Add the protocol stub**

In `src/python/tik/trigger/core/context.py`, add to `BuildContext`:

```python
    def tweak_control(
        self, main: Any, *, size: Optional[float] = None, shape: str = "Circle"
    ) -> Any:
        """Create a secondary tweak controller under ``main``.

        The tweak is a child of the main, so it rides along when the animator
        moves the main control instead of being left behind. It is what the rig
        reads downstream.
        """
```

- [ ] **Step 4: Implement it**

In `src/python/tik/trigger/backends/maya/context.py`, add after `controller`.
`size` defaults to `1.0` and every caller passes it explicitly — a controller's
built size is not readable back off the node, so inferring it would mean storing
a bookkeeping attribute for no gain:

```python
    def tweak_control(
        self, main: Controller, *, size: Optional[float] = None, shape: str = "Circle"
    ) -> Controller:
        """Create a secondary tweak controller under ``main``.

        The tweak is a child of the main, so it rides along when the animator
        moves the main control instead of being left behind. Downstream rig
        connections read the tweak, not the main.
        """
        role = main.transform.meta.get(tags.ROLE, main.transform.name)
        tweak = self.controller(
            f"{role}_tweak",
            shape=shape,
            size=size if size is not None else 1.0,
            parent=main.transform,
            match=main.transform,
            mirror=main.transform.meta.get(tags.MIRROR, tags.WORLD),
        )
        visible = attribute.add_bool(
            main.transform, "tweakVis", default=False, keyable=False
        )
        cmds.setAttr(visible.path, channelBox=True)
        visible >> tweak.transform["visibility"]
        locked = [
            attr
            for attr in attribute.ALL_CHANNELS
            if cmds.getAttr(f"{main.transform.long_name}.{attr}", lock=True)
        ]
        if locked:
            attribute.lock_and_hide(tweak.transform, locked)
        return tweak
```

- [ ] **Step 5: Add it to the fake context**

In `tests/helpers/trigger_fakes.py`, add to `FakeBuildContext`:

```python
    def tweak_control(self, main, *, size=None, shape="Circle"):
        name = f"{main}_tweak"
        self.controllers.append(name)
        return name
```

- [ ] **Step 6: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/core/context.py src/python/tik/trigger/backends/maya/context.py tests/helpers/trigger_fakes.py tests/unit/test_maya_backend_trigger.py
git commit -m "feat(tik.trigger): ctx.tweak_control for secondary tweak controllers"
```

---

### Task 6: The limb drives from its tweak controls

**Files:**
- Modify: `src/python/tik/trigger/systems/limb.py`
- Test: `tests/integration/trigger/test_limb_system.py` (append)

**Interfaces:**
- Consumes: `ctx.tweak_control` from Task 5.
- Produces: `LimbResult.ik_tweak` and `LimbResult.pole_tweak` (`Controller`).
  The IK handle constraint, the tip rotation constraint, the soft-IK goal, the
  aim frame and the pole vector constraint all read the tweak transforms.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_limb_system.py`:

```python
def test_ik_and_pole_have_tweak_controls(build_context):
    result, _binds = _limb(build_context())
    assert result.ik_tweak.transform.parent.name == result.ik_control.transform.name
    assert result.pole_tweak.transform.parent.name == result.pole_control.transform.name


def test_the_tweak_drives_the_rig(build_context):
    result, binds = _limb(build_context())
    result.switch_plug.value = 1.0
    before = binds[-1].world_translation
    result.ik_tweak.transform.translate = (0, 3, 0)
    assert (binds[-1].world_translation - before).length() > 1.0


def test_the_tweak_rides_along_with_the_main(build_context):
    result, _binds = _limb(build_context())
    tweak = result.ik_tweak.transform
    before = tweak.world_translation
    result.ik_control.transform.translate = (0, 5, 0)
    assert (tweak.world_translation - before).length() > 4.9


def test_fk_and_collar_have_no_tweak(build_context):
    result, _binds = _limb(build_context())
    names = {item.transform.name for item in result.fk_controls}
    assert not any("tweak" in name for name in names)
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_limb_system.py -k tweak -v`
Expected: FAIL — `AttributeError: 'LimbResult' object has no attribute 'ik_tweak'`

- [ ] **Step 3: Add the fields**

Add to `LimbResult`:

```python
    ik_tweak: object = None
    pole_tweak: object = None
```

- [ ] **Step 4: Create the IK tweak and route the rig through it**

At the end of `_build_controls`, after the IK control's offset group and lock:

```python
    result.ik_tweak = ctx.tweak_control(result.ik_control, size=size * 0.6)
```

In `build_ikfk_limb`, everything that reads `control` for *rig* purposes now reads
the tweak. Introduce a local right after `control` is taken:

```python
    control = result.ik_control.transform          # animator-facing attributes
    driver = result.ik_tweak.transform             # what the rig follows
```

Change the tip rotation constraint to use `driver`:

```python
    tm.MatrixConstraint.create(
        driver,
        result.ik_joints[-1],
        maintain_offset=True,
        skip_translate="xyz",
        skip_scale="xyz",
    )
```

Pass `driver` into `_build_soft_ik`, `_build_stretch` and `_build_pole` as a new
argument, keeping `control` for attribute creation:

```python
    _build_soft_ik(ctx, name, soft_ik, control, driver, result)
    _build_stretch(ctx, name, stretch, squash, stretch_limit_default, control, driver, result)
    _build_pole(ctx, name, controller_size, pole_pin, control, driver, pole_rest, result)
```

Inside those three functions rename the second transform parameter accordingly and
replace every *geometric* use of `control` with `driver`: `SoftIk.create(...,
driver, ...)`, the fallback `MatrixConstraint.create(driver, result.ik_handle,
...)`, both `Measure.create(..., driver["worldMatrix[0]"], ...)` calls, and
`AimFrame.create(result.pole_base, driver, driver, twist_axis="X", ...)`.
`attribute.add_float(control, ...)` calls stay on `control`.

- [ ] **Step 5: Create the pole tweak and use it as the pole target**

In `_build_pole`, after the pole control's offset group and world position:

```python
    result.pole_tweak = ctx.tweak_control(result.pole_control, size=size * 0.3)
    attribute.lock_and_hide(
        result.pole_tweak.transform, ("rx", "ry", "rz", "sx", "sy", "sz", "v")
    )
    result.ik_handle.pole_vector(result.pole_tweak.transform)
```

and delete the old `result.ik_handle.pole_vector(result.pole_control.transform)`.

- [ ] **Step 6: Run the suites**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/systems/limb.py tests/integration/trigger/test_limb_system.py
git commit -m "feat(tik.trigger): tweak controls drive the limb rig"
```

---

## Phase C — Animation Spaces

### Task 7: `Space` manifest and schema

**Files:**
- Modify: `src/python/tik/trigger/core/manifest.py`
- Modify: `src/python/tik/trigger/core/module.py`
- Modify: `src/python/tik/trigger/core/schemas.py`
- Modify: `src/python/tik/trigger/core/__init__.py`
- Test: `tests/unit/test_core_trigger.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Space(name, control, mode="parent", default=0, help="")` frozen dataclass in `manifest.py`.
  - `Module.spaces: tuple[Space, ...] = ()`, `Module.space_names() -> list[str]`, `Module.get_space(name) -> Optional[Space]`.
  - `ModuleInstance.spaces: dict[str, list[str]]`, round-tripped by `to_dict`/`from_dict`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_core_trigger.py`:

```python
def test_space_declaration_defaults():
    from tik.trigger.core import Space

    space = Space("ik_hand", control="ik")
    assert space.mode == "parent" and space.default == 0


def test_module_space_lookup():
    from tik.trigger.core import Module, Space

    class Spaced(Module):
        spaces = (Space("ik_hand", control="ik", mode="point"),)

    assert Spaced.space_names() == ["ik_hand"]
    assert Spaced.get_space("ik_hand").mode == "point"
    assert Spaced.get_space("nope") is None


def test_module_has_no_spaces_by_default():
    assert ToyRoot.spaces == ()
    assert ToyRoot.space_names() == []


def test_instance_spaces_round_trip():
    instance = ToyChain(name="arm").to_instance()
    instance.spaces = {"ik_hand": ["spine.chest", "head.head"]}
    restored = ModuleInstance.from_dict(instance.to_dict())
    assert restored.spaces == {"ik_hand": ["spine.chest", "head.head"]}


def test_instance_spaces_default_to_empty():
    restored = ModuleInstance.from_dict(
        {"module_type": "toychain", "instance_id": "x", "name": "arm"}
    )
    assert restored.spaces == {}
```

Add `ModuleInstance` to that file's imports from `tik.trigger.core.schemas` if it
is not already there.

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_core_trigger.py -k space -v`
Expected: FAIL — `ImportError: cannot import name 'Space'`

- [ ] **Step 3: Add the `Space` dataclass**

In `src/python/tik/trigger/core/manifest.py`, after `Input`:

```python
@dataclass(frozen=True)
class Space:
    """An animation space a controller in this module can follow.

    Unlike an ``Input``, which resolves to exactly one source and drives the
    bind hierarchy, a space takes any number of sources and becomes an enum on
    the controller. ``world`` is always index 0.

    Args:
        name: Connection name (unique per module).
        control: Controller role the switch is built on (e.g. ``"ik"``).
        mode: ``parent`` | ``point`` | ``orient``.
        default: Default enum index; 0 is ``world``.
        help: Tooltip text.
    """

    name: str
    control: str
    mode: str = "parent"
    default: int = 0
    help: str = ""
```

Add `"Space"` to that module's `__all__` if it has one.

- [ ] **Step 4: Add the module hooks**

In `src/python/tik/trigger/core/module.py`, import `Space` alongside `Input`, add
the class attribute beside `inputs`:

```python
    spaces: tuple[Space, ...] = ()
```

and add beside `input_names`:

```python
    @classmethod
    def space_names(cls) -> list[str]:
        return [item.name for item in cls.spaces]

    @classmethod
    def get_space(cls, name: str) -> Optional[Space]:
        return next((item for item in cls.spaces if item.name == name), None)
```

- [ ] **Step 5: Add the instance field**

In `src/python/tik/trigger/core/schemas.py`, add to `ModuleInstance` after
`inputs`:

```python
    spaces: dict = field(default_factory=dict)  # space name -> list of sources
```

and in `from_dict`:

```python
            spaces={
                key: list(value)
                for key, value in dict(data.get("spaces", {}) or {}).items()
            },
```

`to_dict` uses `asdict`, so the field serialises automatically.

- [ ] **Step 6: Export `Space`**

In `src/python/tik/trigger/core/__init__.py`, add `Space` to the `from .manifest
import ...` line and to `__all__`.

- [ ] **Step 7: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/core tests/unit/test_core_trigger.py
git commit -m "feat(tik.trigger): Space manifest declaration and instance storage"
```

---

### Task 8: Persist spaces and expose them on the handler

**Files:**
- Modify: `src/python/tik/trigger/backends/maya/tags.py`
- Modify: `src/python/tik/trigger/backends/maya/backend.py`
- Modify: `src/python/tik/trigger/guides/handler.py`
- Test: `tests/unit/test_guides_trigger.py` (append)

**Interfaces:**
- Consumes: `ModuleInstance.spaces`, `Module.get_space` from Task 7.
- Produces:
  - `tags.SPACES = "trg_spaces"`.
  - `MayaBackend.set_spaces(instance_id, spaces: dict)`.
  - `GuideHandle.spaces -> dict[str, list[str]]`, `GuideHandle.set_space(name, sources)`.
  - `Guides.set_spaces(handle, spaces)`; `Guides.mirror` maps space sources across sides.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_guides_trigger.py`:

```python
def test_spaces_round_trip_through_the_scene(guides):
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    arm.set_space("ik_hand", ["body.root"])
    assert guides.find("arm", "L").spaces == {"ik_hand": ["body.root"]}


def test_setting_an_unknown_space_raises(guides):
    arm = guides.add("arm", side="L", name="arm")
    with pytest.raises(GuideError):
        arm.set_space("nope", ["body.root"])


def test_clearing_a_space_removes_it(guides):
    arm = guides.add("arm", side="L", name="arm")
    arm.set_space("ik_hand", ["body.root"])
    arm.set_space("ik_hand", [])
    assert guides.find("arm", "L").spaces == {}


def test_mirror_maps_space_sources_across_sides(guides):
    body = guides.add("base", name="body")
    left = guides.add("arm", side="L", name="arm", parent=body)
    other = guides.add("arm", side="L", name="other", parent=body)
    left.set_space("ik_hand", ["L_other.hand", "body.root"])
    mirrored = guides.mirror(left)
    assert mirrored.spaces["ik_hand"] == ["R_other.hand", "body.root"]
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_guides_trigger.py -k space -v`
Expected: FAIL — `AttributeError: 'GuideHandle' object has no attribute 'set_space'`

- [ ] **Step 3: Add the tag and backend persistence**

In `src/python/tik/trigger/backends/maya/tags.py`, beside the other meta keys:

```python
SPACES = "trg_spaces"  # {space name: [sources]} (root guide only)
```

In `src/python/tik/trigger/backends/maya/backend.py`, add `SPACES = "trg_spaces"`
next to the existing `INPUTS = "trg_inputs"` constant (line 22), read it in
`find_instances` beside `inputs=` (line 144):

```python
            spaces={
                key: list(value)
                for key, value in dict(root_meta.get(SPACES, {}) or {}).items()
            },
```

and add the writer beside `set_inputs` (line 217):

```python
    def set_spaces(self, instance_id: str, spaces: dict) -> None:
        """Store ``{space name: [sources]}`` on the instance's root guide."""
        root = self.guide_node(instance_id, self.root_role(instance_id))
        root.meta[SPACES] = {
            key: list(value) for key, value in dict(spaces).items() if value
        }
```

If `set_inputs` resolves its root differently, copy that resolution verbatim —
read lines 217-222 and mirror them.

Also persist spaces in `create_guides` beside `root.meta[INPUTS] = resolved_inputs`
(line 213):

```python
        if getattr(module, "space_sources", None):
            ctx.root.meta[SPACES] = dict(module.space_sources)
```

and in the `.trg` import path beside `root.meta[INPUTS] = dict(guide_instance.inputs)`
(line 391):

```python
                root.meta[SPACES] = dict(guide_instance.spaces)
```

- [ ] **Step 4: Add the handler API**

In `src/python/tik/trigger/guides/handler.py`, add to `GuideHandle` beside
`inputs`:

```python
    @property
    def spaces(self) -> dict:
        """``{space name: [sources]}``."""
        return {key: list(value) for key, value in self._refresh().spaces.items()}

    def set_space(self, name: str, sources) -> None:
        """Replace the source list for one declared space."""
        if self.module_class.get_space(name) is None:
            raise GuideError(f"'{self.module_type}' has no space '{name}'.")
        spaces = self.spaces
        sources = [item for item in (sources or []) if item]
        if sources:
            spaces[name] = sources
        else:
            spaces.pop(name, None)
        self._guides.backend.set_spaces(self.instance_id, spaces)
```

- [ ] **Step 5: Mirror space sources**

In `Guides.mirror`, after the mirrored inputs are computed, add the same mapping
for spaces and pass them along. In the "existing" branch, after
`self.backend.set_inputs(...)`:

```python
            self.backend.set_spaces(
                existing.instance_id,
                {
                    name: [
                        _mirror_source(source, handle.side.value, target_side.value)
                        for source in sources
                    ]
                    for name, sources in instance.spaces.items()
                },
            )
```

and for the newly created branch, after `created = self.backend.create_guides(...)`:

```python
        if instance.spaces:
            self.backend.set_spaces(
                created.instance_id,
                {
                    name: [
                        _mirror_source(source, handle.side.value, target_side.value)
                        for source in sources
                    ]
                    for name, sources in instance.spaces.items()
                },
            )
```

- [ ] **Step 6: Add the convenience wrapper**

Add to `Guides`, beside `connect`:

```python
    def set_spaces(self, handle, spaces: dict) -> None:
        """Replace every space source list on ``handle``."""
        for name, sources in spaces.items():
            handle.set_space(name, sources)
```

- [ ] **Step 7: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/backends/maya src/python/tik/trigger/guides/handler.py tests/unit/test_guides_trigger.py
git commit -m "feat(tik.trigger): persist animation spaces and expose them on the guide handler"
```

---

### Task 9: The builder's post-build space pass

**Files:**
- Modify: `src/python/tik/trigger/core/builder.py`
- Modify: `src/python/tik/trigger/backends/maya/backend.py`
- Modify: `src/python/tik/trigger/backends/maya/context.py`
- Modify: `tests/helpers/trigger_fakes.py`
- Test: `tests/unit/test_core_trigger.py` (append)

**Interfaces:**
- Consumes: `Module.spaces`, `ModuleInstance.spaces`, `GuideHandle.spaces`.
- Produces:
  - `ctx.controller_by_role(role) -> Optional[Controller]` on the build context.
  - `Backend.connect_space(ctx, space, source_nodes)` — the Maya implementation builds a `SpaceSwitch`.
  - `Builder.build` runs `_connect_spaces(instances, report)` after every module is built and connected.
  - `BuildReport.spaces: list[tuple[str, str]]` — `("L_arm.ik_hand", "body.root")` pairs, like `connections`.

**Background:** spaces connect in a final pass rather than joining
`order_by_connections`. A space switch does not affect the bind hierarchy, and
spaces are legitimately mutually referential (an arm in head space while the head
sits in arm space), which would raise a false cycle in the topological sort.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_core_trigger.py`:

```python
def test_builder_connects_spaces_after_every_module():
    backend, root, chain = _scene()
    chain_instance = backend.instances[chain.instance_id]
    chain_instance.spaces = {"follow": [f"{root.key}.root"]}
    report = Builder(backend).build(rig_name="rig", afterlife="keep")
    assert (f"{chain.key}.follow", f"{root.key}.root") in report.spaces


def test_space_sources_may_be_mutually_referential():
    """An arm in head space while the head is in arm space is a normal rig."""
    backend = FakeBackend()
    first = backend.create_guides(ToyRoot(name="a"))
    second = backend.create_guides(ToyRoot(name="b"))
    backend.instances[first.instance_id].spaces = {"follow": ["b.root"]}
    backend.instances[second.instance_id].spaces = {"follow": ["a.root"]}
    report = Builder(backend).build(rig_name="rig", afterlife="keep")
    assert len(report.spaces) == 2


def test_unknown_space_source_is_skipped_with_a_warning():
    backend, root, chain = _scene()
    backend.instances[chain.instance_id].spaces = {"follow": ["ghost.root"]}
    events = EventBus()
    messages = []
    events.subscribe("log", lambda **kw: messages.append(kw["message"]))
    report = Builder(backend, events).build(rig_name="rig", afterlife="keep")
    assert not report.spaces
    assert any("ghost.root" in message for message in messages)
```

`ToyRoot` needs a declared space for these to resolve. In
`tests/helpers/trigger_fakes.py`, add to `ToyRoot`:

```python
    spaces = (Space("follow", control="root", mode="parent"),)
```

importing `Space` from `tik.trigger.core`.

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_core_trigger.py -k space -v`
Expected: FAIL — `AttributeError: 'BuildReport' object has no attribute 'spaces'`

- [ ] **Step 3: Extend the report and add the pass**

In `src/python/tik/trigger/core/builder.py`, add to `BuildReport`:

```python
    spaces: list[tuple[str, str]] = field(default_factory=list)  # ("L_arm.ik_hand", "body.root")
```

Add the call inside the `undo_chunk` block, after the build loop and before
`self.backend.afterlife(...)`:

```python
            self._connect_spaces(instances, report, by_key)
```

and the method itself, after `_connect_one`:

```python
    def _connect_spaces(self, instances, report: BuildReport, by_key: dict) -> None:
        """Build every declared space switch, after all modules exist.

        Deliberately not part of ``order_by_connections``: a space switch does
        not affect the bind hierarchy, and spaces are legitimately mutually
        referential (an arm in head space while the head sits in arm space),
        which would raise a false cycle in the topological sort.
        """
        for instance in instances:
            module_cls = registry.get_module(instance.module_type)
            ctx = report.contexts[instance.instance_id]
            for space in module_cls.spaces:
                sources = list(instance.spaces.get(space.name, []))
                if not sources:
                    continue
                nodes, resolved = [], []
                for source in sources:
                    node = self._resolve_space_source(source, by_key, report)
                    if node is None:
                        self.events.log(
                            f"{instance.key}.{space.name}: source '{source}' was not "
                            f"found; skipped.",
                            level="warning",
                        )
                        continue
                    nodes.append(node)
                    resolved.append(source)
                if not nodes:
                    continue
                self.backend.connect_space(ctx, space, nodes, resolved)
                for source in resolved:
                    report.spaces.append((f"{instance.key}.{space.name}", source))

    def _resolve_space_source(self, source: str, by_key: dict, report: BuildReport):
        """Return the node for a space source, or None when it cannot be found."""
        key, output = split_source(source)
        if key is not None and key in by_key:
            producer_ctx = report.contexts.get(by_key[key].instance_id)
            if producer_ctx is None:
                return None
            return producer_ctx.outputs.get(output)
        return self.backend.scene_node(source)
```

- [ ] **Step 4: Add `controller_by_role` to the context**

In `src/python/tik/trigger/backends/maya/context.py`, add after `tweak_control`:

```python
    def controller_by_role(self, role: str) -> Optional[Controller]:
        """Return the controller registered under ``role``, if any."""
        for controller in self.controllers:
            if controller.transform.meta.get(tags.ROLE) == role:
                return controller
        return None
```

Add the matching stub to `BuildContext` in `core/context.py`:

```python
    def controller_by_role(self, role: str) -> Any:
        """Return the controller registered under ``role``, or None."""
```

and to the fake in `tests/helpers/trigger_fakes.py`:

```python
    def controller_by_role(self, role):
        return next((item for item in self.controllers if item.endswith(role)), None)
```

- [ ] **Step 5: Implement `connect_space` on the backends**

In `src/python/tik/trigger/backends/maya/backend.py`, beside `connect`:

```python
    def connect_space(self, ctx: MayaBuildContext, space, source_nodes, labels) -> None:
        """Build a SpaceSwitch on the controller the space names."""
        controller = ctx.controller_by_role(space.control)
        if controller is None:
            raise AttachError(
                f"{ctx.instance.key}.{space.name}: no controller with role "
                f"'{space.control}'.",
                instance_id=ctx.instance.instance_id,
                module_type=ctx.module.module_type,
            )
        tm.SpaceSwitch.create(
            controller.transform,
            source_nodes,
            attr_name=f"{space.name}Space",
            mode=space.mode,
            labels=[label.split(".")[0] for label in labels],
            default=space.default,
            name=ctx.name(space.name),
        )
```

Import `AttachError` from `tik.trigger.core.exceptions` if it is not already
imported in that file.

In `tests/helpers/trigger_fakes.py`, add to `FakeBackend`:

```python
    def connect_space(self, ctx, space, source_nodes, labels):
        self.space_connections.append((ctx.instance.key, space.name, list(labels)))
```

and initialise `self.space_connections: list = []` in `FakeBackend.__init__`.

- [ ] **Step 6: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger tests/helpers/trigger_fakes.py tests/unit/test_core_trigger.py
git commit -m "feat(tik.trigger): post-build space connection pass"
```

---

### Task 10: The arm declares its spaces

**Files:**
- Modify: `src/python/tik/trigger/modules/arm/arm.py`
- Test: `tests/integration/trigger/test_arm_trigger.py` (append)

**Interfaces:**
- Consumes: `Space`, `Guides.set_spaces`, the builder pass.
- Produces: the arm's `spaces` manifest — `ik_hand` on the `ik` control in
  `parent` mode, `pole` on the `pole` control in `point` mode.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_arm_trigger.py`:

```python
def test_arm_declares_two_spaces():
    module_cls = get_module("arm")
    assert module_cls.space_names() == ["ik_hand", "pole"]
    assert module_cls.get_space("ik_hand").mode == "parent"
    assert module_cls.get_space("pole").mode == "point"


def test_ik_space_switch_is_built(backend):
    body = backend.create_guides(get_module("base")(name="body"))
    arm = backend.create_guides(
        get_module("arm")(name="arm", side="L"),
        parent=ParentRef(body.instance_id, "root"),
    )
    backend.set_spaces(arm.instance_id, {"ik_hand": ["body.root"]})
    report = Builder(backend).build(rig_name="hero", afterlife="keep")
    ctx = report.contexts[arm.instance_id]
    control = _ik_control(ctx)
    assert control.has_attr("ik_handSpace")
    assert report.spaces == [("L_arm.ik_hand", "body.root")]


def test_point_space_moves_without_rotating(backend):
    body = backend.create_guides(get_module("base")(name="body"))
    arm = backend.create_guides(
        get_module("arm")(name="arm", side="L"),
        parent=ParentRef(body.instance_id, "root"),
    )
    backend.set_spaces(arm.instance_id, {"pole": ["body.root"]})
    report = Builder(backend).build(rig_name="hero", afterlife="keep")
    ctx = report.contexts[arm.instance_id]
    pole = next(
        item.transform
        for item in ctx.controllers
        if item.transform.name.endswith("_pole_ctrl")
    )
    pole["poleSpace"].value = 1
    body_ctrl = tm.Transform("C_body_root_ctrl")
    before_rotation = tuple(pole.world_axis("x"))
    body_ctrl.rotate = (0, 45, 0)
    after_rotation = tuple(pole.world_axis("x"))
    for first, second in zip(before_rotation, after_rotation):
        assert abs(first - second) < 1e-3
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_arm_trigger.py -k space -v`
Expected: FAIL — `assert [] == ['ik_hand', 'pole']`

- [ ] **Step 3: Declare the spaces**

In `src/python/tik/trigger/modules/arm/arm.py`, add `Space` to the
`tik.trigger.core` import and, beside `inputs`:

```python
    spaces = (
        Space("ik_hand", control="ik", mode="parent",
              help="What the IK hand follows"),
        Space("pole", control="pole", mode="point",
              help="What the pole vector follows"),
    )
```

- [ ] **Step 4: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/modules/arm tests/integration/trigger/test_arm_trigger.py
git commit -m "feat(tik.trigger): arm declares ik_hand and pole animation spaces"
```

---

## Phase D — Auto-Collar

### Task 11: Auto-collar

**Files:**
- Modify: `src/python/tik/trigger/modules/arm/arm.py`
- Test: `tests/integration/trigger/test_arm_trigger.py` (append)

**Interfaces:**
- Consumes: `LimbResult.ik_control`, `LimbResult.ik_tweak`, `tm.AimFrame`, `tm.MatrixBlend`.
- Produces: an `autoCollar` 0–1 float on the arm's IK control, default `0`, and a
  `<name>_collar_auto_grp` between the collar offset group and the collar control.

**Background:** the collar aims at the IK hand, blended in by one dial. The up
vector comes from the **socket**, not the hand — aiming and rolling from the same
target would make a wrist roll spin the clavicle.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_arm_trigger.py`:

```python
def _collar_control(ctx):
    return next(
        item.transform
        for item in ctx.controllers
        if item.transform.name.endswith("_collar_ctrl")
    )


def test_auto_collar_defaults_to_off(backend):
    control = _ik_control(_arm_ctx(backend))
    assert control.has_attr("autoCollar")
    assert abs(control["autoCollar"].value) < 1e-6


def test_auto_collar_off_is_inert(backend):
    """At 0 the collar must not move, however far the hand goes."""
    ctx = _arm_ctx(backend)
    collar = _collar_control(ctx)
    control = _ik_control(ctx)
    before = list(collar["worldMatrix[0]"].value)
    control.translate = (0, 20, 10)
    after = list(collar["worldMatrix[0]"].value)
    for first, second in zip(before, after):
        assert abs(first - second) < 1e-4


def test_auto_collar_on_follows_the_hand(backend):
    ctx = _arm_ctx(backend)
    collar = _collar_control(ctx)
    control = _ik_control(ctx)
    control["autoCollar"].value = 1.0
    before = tuple(collar.world_axis("x"))
    control.translate = (0, 20, 0)
    after = tuple(collar.world_axis("x"))
    assert max(abs(a - b) for a, b in zip(before, after)) > 0.05


def test_wrist_roll_does_not_spin_the_collar(backend):
    """Up comes from the socket, so rolling the wrist leaves the collar alone."""
    ctx = _arm_ctx(backend)
    collar = _collar_control(ctx)
    control = _ik_control(ctx)
    control["autoCollar"].value = 1.0
    before = list(collar["worldMatrix[0]"].value)
    control.rotate = (90, 0, 0)
    after = list(collar["worldMatrix[0]"].value)
    for first, second in zip(before, after):
        assert abs(first - second) < 1e-3


def test_auto_collar_does_not_cycle(backend):
    ctx = _arm_ctx(backend)
    _ik_control(ctx)["autoCollar"].value = 1.0
    cmds.dgdirty(allPlugs=True)
    assert not (cmds.cycleCheck(all=True) or [])
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_arm_trigger.py -k collar -v`
Expected: FAIL — `assert False` on `has_attr("autoCollar")`

- [ ] **Step 3: Build the automation group**

In `src/python/tik/trigger/modules/arm/arm.py`, capture the limb result and add
the automation after the limb is built (the collar control and its offset already
exist by then):

```python
        limb = build_ikfk_limb(...)
        self._build_auto_collar(ctx, socket, collar_ctrl, limb)
```

and add the method:

```python
    @staticmethod
    def _build_auto_collar(ctx, socket, collar_ctrl, limb) -> None:
        """Aim the collar at the IK hand, weighted by one dial.

        The up vector comes from the socket rather than the hand: aiming and
        rolling from the same target would make a wrist roll spin the clavicle.
        """
        control = limb.ik_control.transform
        attribute.add_separator(control, "auto_")
        amount = attribute.add_float(
            control, "autoCollar", default=0.0, min=0.0, max=1.0
        )

        auto_grp = tm.Transform.create(
            name=ctx.name("collar", "auto", suffix="grp"), parent=ctx.groups.control
        )
        auto_grp.snap_to(collar_ctrl.transform)
        offset = collar_ctrl.transform.parent
        auto_grp.parent = offset
        collar_ctrl.transform.set_parent(auto_grp, relative=True)

        rest = tm.Transform.create(
            name=ctx.name("collar", "rest"), parent=ctx.groups.rig.long_name
        )
        rest.snap_to(collar_ctrl.transform)
        tm.MatrixConstraint.create(socket, rest, maintain_offset=True)

        frame = tm.AimFrame.create(
            rest,
            limb.ik_tweak.transform,
            socket,
            parent=ctx.groups.rig,
            name=ctx.name("collar", "auto"),
        )
        blend = tm.MatrixBlend.create(
            rest, [frame.transform], [amount], name=ctx.name("collar", "autoBlend")
        )
        tm.MatrixConstraint.create(blend.output, auto_grp, maintain_offset=True)
```

Note the parenting order: `auto_grp` is created under `control_grp`, snapped to
the collar control, moved under the collar's existing offset group, and the collar
control is then re-parented into it **relatively**, so the snap is preserved and
no compensation is written into its channels.

- [ ] **Step 4: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger -q`
Expected: PASS.

If `test_auto_collar_off_is_inert` fails, the blend captured the wrong rest
matrix — check that `rest` is snapped *before* the `MatrixConstraint` from the
socket is applied, and that `MatrixConstraint.create(blend.output, auto_grp)` uses
`maintain_offset=True`.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/modules/arm tests/integration/trigger/test_arm_trigger.py
git commit -m "feat(tik.trigger): auto-collar aims at the IK hand with up from the socket"
```

---

## Phase E — Graph View

### Task 12: Multi-connection ports

**Files:**
- Modify: `src/python/tik/trigger/ui/graph_view.py`
- Test: `tests/ui/test_pipeline_ui.py` (append)

**Interfaces:**
- Consumes: `Module.space_names()`, `GuideHandle.spaces`.
- Produces:
  - `Port(node, name, is_output, primary=False, multi=False)`; `Port.multi` is True for space ports.
  - `NodeItem(..., spaces: list[str] = ())` — space ports go into `NodeItem.inputs` alongside inputs, flagged `multi`.
  - `GraphScene.wires_for_input(port) -> list[WireItem]` replaces `wire_for_input`.

**Background:** a single-connection input port unplugs its wire when clicked
(`graph_view.py:74-79`). A port with five wires has no single wire to pick up, so
clicking a space port starts a *new* wire instead; an existing space wire is
removed by selecting the wire itself.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_pipeline_ui.py`:

```python
def test_space_port_is_multi():
    from tik.trigger.ui.graph_view import NodeItem

    node = NodeItem("L_arm", "L_arm", "Arm", ["root"], ["hand"], "#888888",
                    spaces=["ik_hand"])
    assert node.inputs["root"].multi is False
    assert node.inputs["ik_hand"].multi is True


def test_space_port_accepts_several_wires():
    from tik.trigger.ui.graph_view import GraphScene

    scene = GraphScene()
    scene.add_node("body", "body", "Base", [], ["root"], "#888888")
    scene.add_node("head", "head", "Base", [], ["root"], "#888888")
    scene.add_node("L_arm", "L_arm", "Arm", ["root"], ["hand"], "#888888",
                   spaces=["ik_hand"])
    assert scene.add_wire("body.root", "L_arm.ik_hand", False) is not None
    assert scene.add_wire("head.root", "L_arm.ik_hand", False) is not None
    port = scene.nodes["L_arm"].inputs["ik_hand"]
    assert len(scene.wires_for_input(port)) == 2


def test_single_input_port_keeps_one_wire():
    from tik.trigger.ui.graph_view import GraphScene

    scene = GraphScene()
    scene.add_node("body", "body", "Base", [], ["root"], "#888888")
    scene.add_node("L_arm", "L_arm", "Arm", ["root"], ["hand"], "#888888",
                   spaces=["ik_hand"])
    scene.add_wire("body.root", "L_arm.root", True)
    port = scene.nodes["L_arm"].inputs["root"]
    assert len(scene.wires_for_input(port)) == 1
```

If `GraphScene` and `add_node` have different names in that module, read
`graph_view.py:260-300` and use the real ones; do not change the assertions'
meaning.

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_pipeline_ui.py -k "space or single_input" -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'spaces'`

- [ ] **Step 3: Add `multi` to `Port`**

In `graph_view.py`, change `Port.__init__`:

```python
class Port(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, node: "NodeItem", name: str, is_output: bool,
                 primary: bool = False, multi: bool = False) -> None:
        super().__init__(-PORT_RADIUS, -PORT_RADIUS, PORT_RADIUS * 2, PORT_RADIUS * 2, node)
        self.node = node
        self.name = name
        self.is_output = is_output
        self.primary = primary
        self.multi = multi
        self.connected = False
        self.setBrush(QtGui.QColor(PORT_SPACE if multi else "#7b7b7b"))
        self.setPen(QtGui.QPen(QtGui.QColor("#111111"), 1))
        self.setZValue(3)
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"{node.key}.{name}" + (" (space)" if multi else ""))
```

Add the colour constant beside the others near the top:

```python
PORT_SPACE = "#c9a227"  # space ports read apart from input ports at a glance
```

Change `set_connected` to keep a space port's own colour:

```python
    def set_connected(self, connected: bool) -> None:
        self.connected = connected
        if self.multi:
            self.setBrush(QtGui.QColor(PORT_SPACE))
            return
        self.setBrush(QtGui.QColor(theme.ACCENT if connected else "#7b7b7b"))
```

- [ ] **Step 4: Change the click behaviour**

Replace `Port.mousePressEvent`'s body:

```python
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != QtCore.Qt.LeftButton or event.modifiers() & QtCore.Qt.ControlModifier:
            event.ignore()
            return
        scene = self.scene()
        # A multi port has no single wire to pick up, so clicking starts a new
        # one; its existing wires are removed by selecting the wire itself.
        wire = None
        if not self.is_output and not self.multi:
            wires = scene.wires_for_input(self)
            wire = wires[0] if wires else None
        if wire is not None:
            scene.pick_up_wire(wire, event.scenePos())
        else:
            scene.start_wire(self, event.scenePos())
        event.accept()
```

- [ ] **Step 5: Accept space ports on `NodeItem`**

Change `NodeItem.__init__`'s signature to take `spaces: list = ()` after
`outputs`, and add after the input loop:

```python
        for name in spaces:
            self.inputs[name] = Port(self, name, False, multi=True)
```

- [ ] **Step 6: Make `wires_for_input` plural**

Replace `wire_for_input` in the scene class:

```python
    def wires_for_input(self, port: Port) -> list[WireItem]:
        """Every wire landing on ``port``; a multi port may have several."""
        return [wire for wire in self.wires if wire.target is port]
```

Update every call site. `git grep -n "wire_for_input" -- src` and change each to
use the list form.

- [ ] **Step 7: Pass spaces through `add_node`**

Add a `spaces: list = ()` parameter to the scene's `add_node` and forward it to
`NodeItem`.

- [ ] **Step 8: Run the UI suite**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/python/tik/trigger/ui/graph_view.py tests/ui/test_pipeline_ui.py
git commit -m "feat(tik.trigger): multi-connection space ports in the graph view"
```

---

### Task 13: Authoring spaces from the graph

**Files:**
- Modify: `src/python/tik/trigger/ui/graph_view.py`
- Test: `tests/ui/test_pipeline_ui.py` (append)

**Interfaces:**
- Consumes: `Port.multi` from Task 12, `GuideHandle.set_space` from Task 8.
- Produces: `connect_requested` and `disconnect_requested` carry a third `bool`
  argument, `is_space`; the view routes space connections to `set_space` instead
  of `guides.connect`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_pipeline_ui.py`:

```python
def test_connect_signal_reports_whether_the_port_is_a_space():
    from tik.trigger.ui.graph_view import GraphScene

    scene = GraphScene()
    scene.add_node("body", "body", "Base", [], ["root"], "#888888")
    scene.add_node("L_arm", "L_arm", "Arm", ["root"], ["hand"], "#888888",
                   spaces=["ik_hand"])
    seen = []
    scene.connect_requested.connect(lambda *args: seen.append(args))

    scene.start_wire(scene.nodes["body"].outputs["root"], QtCore.QPointF(0, 0))
    scene.finish_wire(scene.nodes["L_arm"].inputs["ik_hand"])
    assert seen and seen[-1][2] is True

    scene.start_wire(scene.nodes["body"].outputs["root"], QtCore.QPointF(0, 0))
    scene.finish_wire(scene.nodes["L_arm"].inputs["root"])
    assert seen[-1][2] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_pipeline_ui.py -k reports_whether -v`
Expected: FAIL — `IndexError: tuple index out of range`

- [ ] **Step 3: Widen the signals**

In `graph_view.py`:

```python
    connect_requested = QtCore.Signal(str, str, bool)  # input key, source key, is_space
    disconnect_requested = QtCore.Signal(str, bool)  # input key, is_space
```

Update every `emit` to pass the port's `multi` flag. In `finish_wire` the target
port is in hand; in `slice_wires` and `delete_selected` take it from
`wire.target.multi`.

- [ ] **Step 4: Route space connections in the view**

Replace `connect_input` / `disconnect_input`:

```python
    def connect_input(self, input_key: str, source_key: str, is_space: bool = False) -> None:
        source = self.resolve_source(source_key)
        if not is_space:
            self._apply(lambda: self.guides.connect(input_key, source))
            return
        key, _dot, space_name = input_key.rpartition(".")
        handle = self.guides.by_key(key)
        if handle is None:
            return
        sources = handle.spaces.get(space_name, [])
        if source in sources:
            return
        self._apply(lambda: handle.set_space(space_name, [*sources, source]))

    def disconnect_input(self, input_key: str, is_space: bool = False, source: str = "") -> None:
        if not is_space:
            self._apply(lambda: self.guides.disconnect(input_key))
            return
        key, _dot, space_name = input_key.rpartition(".")
        handle = self.guides.by_key(key)
        if handle is None:
            return
        remaining = [item for item in handle.spaces.get(space_name, []) if item != source]
        self._apply(lambda: handle.set_space(space_name, remaining))
```

For `disconnect_requested` to remove the right wire, widen it to carry the source
too:

```python
    disconnect_requested = QtCore.Signal(str, bool, str)  # input key, is_space, source key
```

and emit `wire.source.key` alongside. Update `connect`/`disconnect` wiring in
`__init__` accordingly (`graph_view.py:500-501`).

- [ ] **Step 5: Draw space wires when rebuilding**

In `rebuild`, after the existing input-wire loop, add:

```python
            for space_name, sources in handle.spaces.items():
                for source in sources:
                    key, output = split_source(source)
                    if key is not None and key in by_key:
                        source_key = f"{key}.{output}"
                    else:
                        source_key = f"{node_group.get(source, 'scene')}.{source}"
                    self.graph.add_wire(
                        source_key, f"{handle.key}.{space_name}", False
                    )
```

and pass the space names when the node is created:

```python
            self.graph.add_node(
                handle.key, handle.key, module_cls.display_label(),
                module_cls.input_names(), list(handle.outputs),
                theme.SIDE.get(handle.side.value, theme.SIDE["C"]),
                primary_input=primary.name if primary else None, pos=pos,
                mode=collapse.get(handle.key, MODE_FULL),
                spaces=module_cls.space_names(),
            )
```

Update the two `rows = max(...)` height calculations to include spaces:

```python
            rows = max(
                len(module_cls.inputs) + len(module_cls.spaces),
                len(handle.outputs),
                1,
            )
```

- [ ] **Step 6: Run the UI suite**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/ui/graph_view.py tests/ui/test_pipeline_ui.py
git commit -m "feat(tik.trigger): author animation spaces from the node graph"
```

---

## Phase F — Verification

### Task 14: Full-arm sweep

**Files:**
- Test: `tests/integration/trigger/test_arm_trigger.py` (append)

**Interfaces:**
- Consumes: everything above.
- Produces: no source changes; the end-to-end guarantees.

- [ ] **Step 1: Write the round-trip and ground-rule tests**

Append to `tests/integration/trigger/test_arm_trigger.py`:

```python
def test_trg_round_trip_keeps_spaces(backend, tmp_path):
    from tik.trigger.guides import Guides

    guides = Guides(backend)
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    arm.set_space("ik_hand", ["body.root"])

    path = tmp_path / "spaces.trg"
    guides.export(str(path))
    cmds.file(new=True, force=True)
    fresh = Guides(trigger.maya_backend())
    fresh.import_file(str(path))

    assert fresh.find("arm", "L").spaces == {"ik_hand": ["body.root"]}
```

If `Guides` exposes different export/import method names, read
`src/python/tik/trigger/guides/handler.py` and use the real ones; keep the
assertion.

```python
def test_arm_still_satisfies_every_ground_rule(backend):
    ctx = _arm_ctx(backend)
    control_group = ctx.groups.control.long_name
    for controller in ctx.controllers:
        assert control_group in controller.transform.long_name
        assert controller.transform.meta[tags.MIRROR] in (tags.BEHAVIOUR, tags.WORLD)
    for _name, node in ctx.outputs.items():
        assert node.type == "joint" and node in ctx.deform_joints
    for joint in ctx.deform_joints:
        assert not cmds.listConnections(
            f"{joint.long_name}.offsetParentMatrix", source=True, destination=False
        )
```

- [ ] **Step 2: Run the whole test surface**

Run each and record the counts:

```
set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit -q
set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration -q
set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui -q
```

Expected: all pass. Report any failure with its output rather than moving on.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/trigger/test_arm_trigger.py
git commit -m "test(tik.trigger): arm round-trip with spaces and a full ground-rule sweep"
```

---

## Self-Review Notes

**Spec coverage.** §1.1 → Task 1. §1.2 → Task 2. §1.3 → Task 2. §1.4 → Task 2.
§1.5 → Task 4. §1.6 → Task 3. §1.7 → Task 4. §2.1-2.2 → Task 7. §2.3 → Task 9.
§2.4 → Task 8. §2.5 → Tasks 12-13. §3.1-3.2 → Tasks 5-6. §3.3 → Task 3.
Part 4 → Task 11. §5.1 → Task 1. §5.2 → Tasks 3, 4, 6, 10, 11, 14. §5.3 → Task 12.

**Known risks, stated rather than hidden.**

1. **Task 6 rewires every geometric consumer in the limb** from the main control
   to the tweak. If a single one is missed, the rig still builds and most tests
   still pass — `test_the_tweak_drives_the_rig` is the one that catches it, so do
   not weaken it.
2. **Task 13 widens two Qt signals**, and every emit site must be updated
   together or connections silently stop firing. `git grep -n
   "connect_requested\|disconnect_requested"` before and after.
3. **API guesses.** `GraphScene`/`add_node` names in Task 12, `Guides.export` /
   `import_file` in Task 14, and `MayaBackend.root_role` in Task 8 are used as
   written from surrounding code but not verified line by line. Each of those
   steps says to read the real names and adjust the call, never the assertion.
4. **Task 11's re-parenting** of the collar control into the automation group
   must be relative — `set_parent(..., relative=True)` — or Maya writes
   compensation into the control's channels, which is exactly the bug that bit
   `AimFrame` in the previous plan.
