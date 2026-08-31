# Twist, Ribbon and Limb Lock — Design Spec

Date: 2026-08-31
Status: brainstormed with Arda Kutlu; awaiting spec review.
Builds on `2026-08-30-trigger-simplification-design.md` (the `rig` object and
layering), `2026-08-30-arm-module-and-module-ground-rules-design.md` (module
ground rules) and `2026-08-29-pure-math-ribbon-design.md` (the `Ribbon`
construct this spec refactors).

## 1. Goal

Three additions to tik.trigger, specced together because the first is the
foundation of the second:

1. **`systems/twist.py`** — a shared, robust twist extractor, and a generic
   `twist` module built on it.
2. **A `ribbon` module** wrapping the existing `tik.maya` `Ribbon` construct,
   which requires fixing a layering violation inside that construct.
3. **`systems/limb_lock.py`** — limb lock as a system, opt-out at module level,
   wired into `arm`.

Two prior implementations are the starting point, not the target:
`dump/twist_dump.py` and `dump/limb_lock_dump.py`. Both are ported to tik.maya
idiom and both are simplified; the specific departures are called out below,
each with its reason.

Ordering matters: the twist extractor lands first because both the `twist`
module and the `ribbon` module consume it.

## 2. Section 1 — the twist extractor and the `twist` module

### 2.1 Why the dump's method is limited, and what actually fixes it

`dump/twist_dump.py` extracts twist with `composeMatrix` → `multMatrix`
(negating the build pose) → `decomposeMatrix` → `quatToEuler` on one axis.
That is a correct swing-twist decomposition, and it wraps at ±180.

**An earlier draft of this spec proposed a `quatSlerp` half-angle trick to
push that to ±360. It was measured against Maya 2026 and it does not work.**
Sweeping a driver from -400° to +400° through
`quatSlerp(identity, twist, 0.5) → quatToEuler → x2`:

| driver rx | direct | Shortest | Positive | Negative |
|---|---|---|---|---|
| 181 | -179.0 | -179.0 | -179.0 | 181.0 |
| 200 | -160.0 | -160.0 | -160.0 | 200.0 |
| 361 | 1.0 | 1.0 | 1.0 | -359.0 |

Largest step between adjacent samples across the sweep: 355° for Shortest and
Positive, 365° for Negative. Every mode wraps.

The cause is upstream of the slerp and is not fixable by any quaternion
wiring: **a rotation matrix for 200° is identical to the matrix for -160°**,
and `decomposeMatrix` canonicalises the quaternion to the `w >= 0`
hemisphere. The information is gone before a quaternion node sees it. Any
matrix-derived twist is therefore bounded to a 360°-wide window, i.e. ±180
about the reference pose. This is a property of the representation.

What does carry unbounded twist is a **rotate channel**. With rotate order
XYZ the X rotation is applied innermost, so `rotateX` is exactly the roll
about the bone's own axis and it is a plain unbounded float. This is already
why `Ribbon` sets `ROTATE_ORDER_XYZ` and adds twist onto `rotateX` rather
than through a matrix (`constructs/ribbon.py`).

So the extractor offers both sources and picks honestly between them.

### 2.2 `systems/twist.py`

One public function:

```python
def twist_plug(driver, reference, *, name, axis="auto", source="auto") -> Plug:
    """Degrees of ``driver``'s roll about ``axis``, relative to ``reference``."""
```

**`source="matrix"`** — swing-twist decomposition. Works for any driver in any
hierarchy, however it is constrained. Bounded to ±180 about the rest pose.
Four nodes, created once per call and shared by every consumer:

| node | role |
|---|---|
| `multMatrix` (3 inputs: static `rest_inverse`, `driver.worldMatrix`, `reference.worldInverseMatrix`) | relative rotation expressed in the **rest-local** frame, so the twist axis stays the segment's own axis in any pose |
| `decomposeMatrix` | swing-twist decomposition, giving `outputQuat<axis>` + `outputQuatW` |
| `quatToEuler` | the angle, in `outputRotate<axis>` |

`multMatrix` multiplies in input order, so a single node with three inputs
yields `rest_inverse * driver.worldMatrix * reference.worldInverseMatrix` —
the delta expressed in the rest frame. `rest_inverse` is baked as a static
matrix value at build time. Feeding `quatToEuler` only the axis component and
`W` is what isolates twist from swing.

**`source="channel"`** — reads `driver["rotate<axis>"]` directly. Zero nodes,
and genuinely unbounded: a propeller, wheel, drill or FK roll control winds
past 360° without a pop. Valid only when the driver's rotation *is* the twist
relative to the reference, which requires both:

- `reference` is the driver's parent transform, and
- the driver's `rotateOrder` applies the twist axis innermost (XYZ for an
  X twist), so the channel is roll about the bone's own axis rather than a
  component of a composite rotation.

**`source="auto"`** (the default) checks those two conditions at build time
and picks `channel` when they hold, `matrix` otherwise, logging which it
chose at debug level. This gives an FK-driven twist its unbounded range and a
matrix- or IK-driven one the robust bounded extraction, with no user decision
required.

**The bound is real and is documented, not hidden.** A wrist or ankle driven
through `MatrixBlend` (every IK/FK limb in this repo) resolves to rotate
channels derived from a matrix, so it is bounded whichever source is chosen —
which is correct, because anatomical twist never approaches 180° from rest.
Unbounded rotation is a mechanical case, and mechanical drivers are FK, where
`channel` applies.

Per consumer joint the cost is one `multDoubleLinear` for its weight.

`axis="auto"` runs the dominant-axis dot product from `twist_dump.py`
(`get_dominant_axis`) **once in Python at build time**, never in the DG.
`axis` may also be given explicitly as `"X"`, `"Y"` or `"Z"`.

The `multMatrix` input order (`rest_inverse` first vs last) is asserted by a
test that twists a driver in a non-identity rest pose.

### 2.3 The `twist` module

`src/python/tik/trigger/modules/twist/twist.py`:

```python
guides  = GuideLayout("base", "end", multi="twist", min=1, max=20)
inputs  = (Input("base", primary=True), Input("end"), Input("reference", optional=True))
outputs = twist0 ... twistN-1        # via output_names(settings)
```

Fields: `count` (drives `guide_count()`), `twist_source` (`"start"` | `"end"`),
`axis` (`"auto"` | `"X"` | `"Y"` | `"Z"`), `extraction` (`"auto"` | `"matrix"`
| `"channel"`, passed to `twist_plug(source=...)`), `distribute_translation`
(bool).

`twist_source` and `extraction` are deliberately distinct: the first says
*which end drives* the twist, the second says *how the angle is read*.

This is a **generic** module, not a limb accessory. It covers both directions
of the common case through `twist_source`:

- `twist_source="end"` — follow-twist. Driver is the `end` input, reference is
  `base`. The forearm/wrist case.
- `twist_source="start"` — counter-twist. Driver is the `base` input,
  reference is the `reference` input (falling back to the base joint's parent
  when unconnected). The upper-arm/thigh case.

**Position and weight are fully decoupled.**

*Position* is the guide's **projection onto the base-to-end axis**, clamped to
0–1, computed at build. A rigger may drag a twist guide sideways for
visibility and it still reads correctly. Guides are plain draggable joints, so
they round-trip through the `.trg` by world position like every other guide in
the repo.

*Weight* is an **unclamped float attribute on the guide joint** (`twistWeight`).
Negatives are legal and reverse the twist. A joint at position 0.95 may carry
weight 0.2 while one at 0.5 carries 0.8; nothing derives one from the other.
The value written at draw time is the projected position (or `1 - position`
for `twist_source="start"`), so the common case is correct untouched, and
every joint is independently overridable afterwards.

Joints are created with `rig.bind_joint(parent=rig.bind_parent)` — siblings of
the next segment's joint, which is how engine twist bones are structured and
what `arm.py`'s docstring already promises. With `distribute_translation` on,
each joint's `translate` is the end input's `translate x position`, so joints
redistribute when the limb stretches (kept from the dump's `multiplyDivide`).

Rotation per joint: `twist_plug(...) x twistWeight -> joint.rotate<axis>`.

### 2.4 Framework change: per-guide attributes

Storing weight on the guide requires per-guide authorable data to survive a
save/load, which the `.trg` format does not currently support:
`export_guide_records` writes `settings` for the **root** guide only
(`guides/scene.py`), and `import_guide_instances` restores a guide purely by
world position, rotation, joint orient, radius and colour.

`format.py` has **no schema version and no migration machinery** —
`core/versioning.py` is filename `_v###` handling only, and a joint record is
a plain dict. So this is purely additive; old `.trg` files simply lack the key
and `record.get("attrs", {})` covers them.

The change, generic rather than twist-specific:

1. `Module` gains a `guide_attrs` declaration mapping a guide role to the
   float attributes its guides carry, alongside the existing `guides` /
   `inputs` / `outputs` class attributes:

   ```python
   guide_attrs = {"twist": (GuideAttr("twistWeight", default=0.0),)}
   ```

   `GuideAttr` is a frozen dataclass beside `Input` in `core/manifest.py`
   (`name`, `default`, `keyable=True`, `help=""`). Roles absent from the
   mapping carry no extra attributes, so every existing module is unaffected.
   The default written at draw time may be overridden per guide by
   `draw_guides` — the twist module writes the projected position there.
2. `GuideDraft.joint` adds the declared attributes when drawing a guide.
3. `make_record` gains an optional `attrs: dict | None` parameter writing an
   `"attrs"` key when present.
4. `export_guide_records` reads the declared attributes off each guide node.
5. `import_guide_instances` re-adds and sets them after creating the joint.

The build path needs nothing: `rig.guide("twist", i)` already returns a
`tm.Joint`, so a module reads `joint["twistWeight"].value` directly.

**Dropped from the dump:** the guide *rail* (twist guide translate driven by a
`multiplyDivide` from the end guide, with a `position` attribute). Driven
translate channels cannot be restored by `import_guide_instances`, which sets
world position with `cmds.xform`. Projection replaces it and is strictly more
permissive.

## 3. Section 2 — the `ribbon` module and the `Ribbon` refactor

### 3.1 The layering violation

`Ribbon._create_controllers` calls `Controller.create` directly
(`constructs/ribbon.py`). This breaks the rule stated in
`systems/__init__.py` and `CLAUDE.md` — *a tik.maya construct never creates a
controller, names a user-facing attribute, or encodes a side convention* —
and it has concrete consequences for a trigger module: those controllers get
no side colour, no `tags.CONTROLLER` tag, no offset group, no entry in
`rig.controllers`, and they sit under a spline output inside `rig_grp` rather
than `control_grp`. The pose-mirror tool and the space-switch system cannot
see them.

`Ribbon`'s only callers are its own tests (`tests/unit/test_ribbon.py`), so
fixing it at the source is cheap.

### 3.2 The refactor

`Ribbon` already has the right vocabulary: `start_plug` / `end_plug` are
transforms the caller pins to its own controllers via `pin_start` / `pin_end`.
Mids become plugs like the ends:

```python
Ribbon.create(start, end, *, name, joint_count, mid_count=1, ...)
ribbon.mid_frames[i]    # swing+twist frame from the control spline
ribbon.mid_plugs[i]     # transform the joint spline reads
ribbon.pin_mid(i, node) # drive that plug from a caller-owned node
```

`Controller` and the `..roles.controller` import leave
`constructs/ribbon.py` entirely. `_mid_twists` reads `mid_plugs[i]["rotateX"]`
instead of the controller's, so twist behaviour is unchanged.
`tests/unit/test_ribbon.py` is updated for the new attribute names.

### 3.3 The module

`src/python/tik/trigger/modules/ribbon/ribbon.py`:

```python
guides  = GuideLayout("start", "end")
inputs  = (Input("start", primary=True), Input("end"), Input("reference", optional=True))
outputs = joint0 ... jointN-1        # via output_names(settings), the fkchain pattern
```

Fields: `joint_count`, `mid_count`, `degree`, `scaleable`, `preserve_volume`,
`controller_size`.

Controllers are created by the module, in `control_grp`, and still ride the
ribbon because their *offset* is driven by the swinging frame:

```python
ctrl = rig.controller(f"mid{i}", shape="Circle", size=..., mirror="behaviour")
tm.MatrixConstraint.create(ribbon.mid_frames[i], ctrl.offset, maintain_offset=False)
tm.MatrixConstraint.create(ctrl, ribbon.mid_plugs[i], maintain_offset=False)
```

**Deform joints.** The `Ribbon` (its joints included) is built under
`rig.groups.rig` as puppet, and `pin_start` / `pin_end` attach it to the two
input sockets. The module then creates real bind joints under
`rig.bind_parent` — siblings, engine-twist-bone shaped — each
`MatrixConstraint`ed from its ribbon joint, the pattern `_blend_to_bind`
already uses in `systems/limb.py`.

The reason: `Ribbon` puts its joints in a group with `inheritsTransform =
False` because each joint's local channels hold *world* values decomposed
from the spline. That is correct for the construct, but a non-inheriting
island inside `bind_grp` bakes and exports wrong the moment the rig root
moves. Keeping it in `rig_grp` makes it harmless, at the cost of one
constraint per joint.

**Twist.** `Ribbon.start_twist` and `end_twist` are bare float plugs that
nothing feeds. `twist_plug()` from §2.2 fills them: `start_twist` is the start
input's roll against `reference`, `end_twist` is the end input's roll against
start. Same extractor, no second implementation.

## 4. Section 3 — `systems/limb_lock.py`

### 4.1 What limb lock is

While locked, the distance from the limb root to the IK control is held at
`lockLength`. The hand or foot is the animator's anchor, so the **root** is
what moves. A single lock, not the dump's pre/post pair — that split existed
only to serve multiple knee and ankle pivots with an auxiliary IK chain, and
none of that is wanted here.

### 4.2 Signature

Deliberately takes nodes rather than reaching for them:

```python
def build_limb_lock(
    rig, *, socket, chain_root, driver, control, target=None, name=""
) -> LimbLock
```

- `socket` — the module's input socket. Two jobs: it *drives* `lock_root`
  (pre-push, §4.5) and it is the rest side of the blend.
- `chain_root` — where `lock_root` is *positioned*, i.e. the first joint of
  the limb chain. Distinct from `socket`, which for the arm sits at the collar.
- `driver` — what the rig follows at the far end.
- `control` — where the three animator attributes are added.
- `target` — the transform the blend drives. `None` selects output mode: the
  push is published rather than consumed locally (§4.8).

For the arm: `socket = rig.socket("root")`, `chain_root = limb.ik_joints[0]`,
`driver = limb.ik_tweak`, `control = limb.ik_control`.

### 4.3 Attributes

Three, on the IK control, created in this order — Maya orders the channel box
by creation order:

| attribute | type | behaviour |
|---|---|---|
| `limbLock` | float 0–1, keyable | the blend |
| `currentLength` | float, keyable **and locked** | live `Measure` distance; display and copy source |
| `lockLength` | double, keyable | absolute length to lock to; default = the bind-pose distance measured at build |

`currentLength` is connected first and locked afterwards, so it shows greyed
in the channel box and remains copyable.

This set exists to serve one workflow: at any arbitrary pose the animator
reads `currentLength`, pastes it into `lockLength`, and raises `limbLock`.
Nothing moves at that instant, and the limb is locked exactly where it stands.
A normalised multiplier cannot express that, which is why `lockLength` is in
absolute scene units.

### 4.4 Graph

```
lock_root   transform placed at chain_root, MatrixConstraint from socket (pre-push)
measure     Measure(lock_root, driver).distance  ->  currentLength   (then lock)
aim_grp     point-constrained to driver; aimConstraint at lock_root, +X, worldUpType=none
push        child of aim_grp,  translateX  <-  lockLength      # a direct connection
blend       MatrixBlend(socket, [push], [limbLock])            # socket is the rest side
            -> MatrixConstraint(blend.output, target, skip_rotate="xyz", skip_scale="xyz")
```

`push` is a point at distance `lockLength` from the hand, along the direction
toward the unpushed root. Blending the root toward it holds the limb at that
length while the hand stays on its control. The blend is translation only.

### 4.5 The cycle, and how it is avoided

`limb_lock_dump.py` aims at `lock_start` and pushes the pelvis — but
`lock_start` hangs off the pelvis, so root -> measure -> push -> root is a DG
cycle that Maya resolves with a frame of lag.

Here, `lock_root` is `MatrixConstraint`ed from the module's **socket**, which
is *pre-push*, while the push is applied strictly downstream of it. The
measurement can never see its own output.

It is also the semantically correct quantity: "how far is the control from
where the root *would* be", which is precisely the deficit to close.

`lock_root` is created **at the chain root** (the shoulder), not at the
socket, and constrained from the socket with a maintained offset. For the arm
the socket sits at the *collar*, so measuring from it would lock collar-to-hand
rather than shoulder-to-hand, and `lockLength` would be seeded with the wrong
number.

**Known approximation:** `lock_root` therefore rides the socket rather than
the collar controller, so it does not see collar rotation, including
auto-collar. Under a locked limb the shoulder is treated as rigidly following
the chest. Breaking the cycle requires *some* pre-push reference and this is
the closest one available.

### 4.6 What was dropped from the dump, and why

- **The pre/post lock pair** — needed only for multiple ankle pivots and a
  helper IK chain. One lock replaces both.
- **`restLength`, `normLength`, the two `floatMath` divides, and the
  `scaleX`-on-the-aim-group trick** — with `lockLength` in absolute units,
  `push.translateX <- lockLength` is a plain connection. Roughly three nodes
  instead of ten.
- **Every `rig.rigScale` division** — no global rig-scale concept exists
  anywhere in tik.maya or tik.trigger, so there is nothing to divide by.
  Absolute units are correct today. If a global scale is added later, this
  becomes `lockLength * globalScale` on that one connection.
- **`hipPush`** — a second feature bolted onto the same controller, out of
  scope here.

### 4.7 Interaction with soft-IK and stretch

None is wired, and none is needed. Holding the root at exactly `lockLength`
removes the very deficit soft-IK and stretch react to, so when `lockLength`
equals the rest length they idle on their own. When `lockLength` is
appreciably shorter the limb is genuinely compressed and `squash` engages,
which is the desired behaviour.

### 4.8 `lock_target` and the arm

- `"socket"` — the module inserts a `lockPush` buffer in `socket_grp`, and the
  arm's `collar_ctrl.offset` is constrained to that instead of the raw socket.
  `lock_root` still reads the raw socket, so no cycle. Self-contained and
  useful today.
- `"output"` — no local push; `rig.output("lock", push)` publishes it for a
  future body/COG module to absorb. `Arm.output_names()` grows `"lock"` in
  this mode.

The push transform and the attributes are built identically either way; only
the consumer differs.

On `Arm`: `limb_lock = BoolField(True)` — an *opt-out*, so it defaults on; at
`limbLock = 0` the network is inert. `lock_target = ChoiceField("socket",
("socket", "output"))`.

## 5. Testing

Following the repo's conventions — `pytest` under `mayapy`, no third-party
deps, `test_<module>_trigger.py` naming.

**`tests/unit/test_twist_trigger.py`** (Maya)
- `twist_plug` returns 0 at rest in a non-identity rest pose, for both sources.
- `source="matrix"` tracks the driver exactly across ±170°.
- `source="matrix"` wraps beyond ±180 — asserted deliberately, so the
  documented bound is a tested property rather than a latent surprise, and so
  a future reader does not re-attempt the quaternion trick. A comment cites
  the measurement in §2.1.
- `source="channel"` is monotonic across a -400° to +400° sweep with no step
  larger than the sample interval — the unbounded case.
- `source="auto"` picks `channel` for an XYZ-order driver parented to the
  reference, and `matrix` when the driver is constrained or the rotate order
  puts the twist axis outermost.
- Swing contamination: rotating the driver off-axis leaves the extracted twist
  unchanged under `source="matrix"`.
- `axis="auto"` picks the chain axis for X-, Y- and Z-oriented chains.
- Module: guide projection yields expected positions for guides dragged off
  the axis; a negative `twistWeight` reverses the joint's rotation; joints land
  under `rig.bind_parent` as siblings.

**`tests/unit/test_guides_trigger.py`** (extended)
- `guide_attrs` round-trip: draw, export, import preserves `twistWeight`.
- A `.trg` record with no `"attrs"` key still imports (backwards compatibility).

**`tests/unit/test_ribbon.py`** (updated)
- Existing coverage retargeted to `mid_plugs` / `mid_frames`.
- `Ribbon` creates no `Controller` and imports nothing from `..roles`.

**`tests/unit/test_ribbon_trigger.py`** (Maya)
- Mid controllers are tagged, side-coloured, have offset groups and live in
  `control_grp`; moving one deforms the strip.
- Bind joints exist under `rig.bind_parent`, and the non-inheriting joint
  group stays in `rig_grp`.

**`tests/unit/test_limb_lock_trigger.py`** (Maya)
- The three attributes exist in the stated order; `currentLength` is locked
  and connected; `lockLength` defaults to the bind-pose root-to-driver
  distance.
- The copy-paste workflow: at an arbitrary pose, setting `lockLength` to the
  current `currentLength` and raising `limbLock` to 1 moves nothing.
- With the lock engaged, moving the IK control away holds root-to-driver at
  `lockLength`.
- `cmds.cycleCheck` reports no cycle on the built rig — the regression guard
  for §4.5.
- `lock_target="output"` publishes `"lock"` and pushes nothing locally.

**`tests/integration/trigger/`**
- An arm with `limb_lock=True` plus a twist module on `upperarm` and a ribbon
  module on `lowerarm` builds end to end and is cycle-free.

**`tests/unit/test_import_boundaries.py`** already guards that `core` stays
pure; the new systems and modules live outside it and may use tik.maya.

## 6. Build order

1. `systems/twist.py` + its tests.
2. `guide_attrs` framework change + guide round-trip tests.
3. The `twist` module + tests.
4. The `Ribbon` refactor + updated `test_ribbon.py`.
5. The `ribbon` module + tests.
6. `systems/limb_lock.py` + tests.
7. `Arm` wiring (`limb_lock`, `lock_target`, `output_names`) + integration test.

Steps 1–3 and 4–5 are independent of 6–7 and may proceed in parallel.
