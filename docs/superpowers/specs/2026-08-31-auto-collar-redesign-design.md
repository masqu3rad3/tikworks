# Auto-Collar Redesign — Design Spec

Date: 2026-08-31
Status: designed, not implemented.
Supersedes Part 4 ("The Reach System") of
`2026-08-30-dynamic-spaces-and-reach-design.md`. The file
`systems/reach.py` survives; its mechanism does not.
Builds on `2026-08-30-trigger-simplification-design.md` (the `rig` object
and layering) and `2026-08-30-arm-module-and-module-ground-rules-design.md`
(module ground rules).

## 1. The complaint

Pose the character in an A-pose, switch the auto-collar on, and start
raising the arm. The collar first bends *down*, keeps sinking as the arm
rises, and only then swings up. Past the end angle it never stops — it
tracks the arm one-for-one forever. Neither behaviour is adjustable by any
field the module exposes.

What the rigger actually wants to author:

- the **neutral direction** where the clavicle changes sign,
- an **upper and a lower falloff limit** either side of it,
- how many **degrees** of collar motion each limit corresponds to,
- **saturation** past the limits — "after that it stays like that",
- a **smooth** approach to the limits, with no hard corner.

None of that is expressible in the current mechanism, and section 2
explains why it is not a tuning problem.

## 2. Why the current system misbehaves

Everything in this section was measured by rebuilding the `reach.py`
network verbatim on a bare rig in a live Maya session and sweeping the arm
(A-pose guides, arm 30 degrees below the socket's X, `vertical = horizontal
= 0.5`, `start = 0`, `end = 90`, `interp = smooth`, `autoCollar = 1`).

| arm elevation | measured angle | ramp weight | collar delta |
|---|---|---|---|
| -60 | 10.89 | 0.036 | -1.46 |
| -50 | 0.79 | 0.000 | -0.01 |
| **-30 (bind)** | **13.90** | 0.058 | **-0.93** |
| -20 | 19.69 | 0.114 | **-1.17 (worst)** |
| 0 (T-pose) | 30.00 | 0.250 | 0.00 |
| +45 | 56.57 | 0.696 | +18.50 |
| +75 | 91.81 | 1.000 | +61.81 |
| +120 | 169.11 | 1.000 | **+139.11** |

With a realistically elevated clavicle (rest aim +12 degrees, which is what
a real clavicle guide looks like) the dip reaches **-3.09 degrees** and does
not return to zero until the arm is **+23 degrees above horizontal**.

### 2.1 The dominant cause — there are two unrelated zeros

The ramp's zero is the *arm's* bind direction, captured at `reach.py:84`.
The blend target's zero is the *collar's* rest orientation, because
`AimFrame.create(rest, aim_point, ...)` (`reach.py:112-119`) points the
collar's own +X at the aim point. Those are different directions: one
points at the wrist, the other runs along the clavicle.

`MatrixBlend(rest, frame, w)` (`reach.py:120-122`) therefore interpolates
the collar *from where it rests toward pointing at the hand*. In an A-pose
the hand is below the clavicle, so **any** weight above zero rotates the
collar down. The weight meanwhile grows monotonically as the arm rises.
Weight increasing multiplied by a delta that is still negative means the
dip **deepens** as the arm lifts. It only unwinds when the scaled aim
direction crosses the clavicle's rest aim, at

    atan(vertical * tan phi) == collar_rest_elevation

— T-pose when the clavicle rests horizontal, +23 degrees when it rests at
+12 degrees.

That crossing *is* the neutral the rigger has been hunting for. It is an
emergent function of the clavicle's guide orientation and the vertical
multiplier, and no field touches it.

### 2.2 A plain bug — the rest direction is sampled from the wrong plug

`reach.py:84` samples `rest_direction` from the **raw** probe;
`reach.py:98` feeds the ramp the **scaled** vector. The angle at bind pose
is therefore

    theta_bind = phi_bind - atan(vertical * tan phi_bind)

For a 30 degree A-pose at `vertical = 0.5`: `30 - 16.10 = 13.90`, matching
the measurement to the decimal. Weight 0.058, and the collar sits **0.93
degrees off its bind pose with the automation at 1.0**. Setting both
multipliers to 1.0 drives the error to exactly 0.00 (verified). The rig
does not reproduce its own bind pose, and the error is maximised by the
shipped defaults of 0.5 (`reach.py:62-67`).

The redesign removes this class of bug by construction: the multipliers
scale the *output* degrees, so no multiplier value can move the zero.

### 2.3 The end angle saturates the weight, not the output

Past `end_angle` the weight pins at 1.0 and the collar simply *becomes* the
aim frame — it tracks the arm 1:1 without bound. Measured: 139 degrees of
collar rotation at 120 degrees of arm elevation, still climbing.

"Until it hits the limit angle, after that it will stay like that" is
therefore **structurally unachievable** in a blend-toward-an-aim-frame
model, whatever curve is placed on the weight. It also caps the achievable
gain at saturation at 1.0, against roughly 15 degrees of clavicular
elevation for 180 degrees of humeral elevation in life — a target gain
nearer 0.1.

This alone justifies replacing the mechanism rather than retuning it.

### 2.4 `spline` interpolation always pops

Measured on a two-point `remapValue` ramp, `spline` has slope about 0.5 at
both endpoints, so it meets the clamp with a slope discontinuity. It is
never correct for a saturating driver. Kept as an option (section 4.4), but
documented as such.

### 2.5 What is *not* the cause

`AngleBetween` being unsigned is real but secondary — the aim frame carries
the direction, so the sign is implicit in the blend. What unsignedness
actually costs is the requested feature: the ramp is V-shaped with its
vertex at `atan(tan phi_bind / vertical)` (measured minimum at -50 degrees,
not at the bind pose), so arm-down re-engages the automation on the wrong
side of the vertex, sharing one pair of limits with arm-up. Independent up
and down limits are impossible in that model.

### 2.6 Other findings, carried into the plan

- `rest_direction = tuple(probe.translate)` (`reach.py:84`) works only
  because `MatrixConstraint` drives real `translate` channels
  (`matrix_constraint.py:127`). Were it ever to move to
  `offsetParentMatrix`, `rest_direction` would silently become `(0,0,0)`
  and `angleBetween` would return garbage with no error. The redesign
  reads no such sampled value.
- `Arm.validate` (`arm.py:71-78`) catches `start >= end` but not the
  degenerate case where the arm's bind direction is parallel to the socket
  X, in which case the feature silently does nothing.
- The spec's `AimFrame` parallel-up hazard
  (`2026-08-30-dynamic-spaces-and-reach-design.md` section 4.2, worked
  around at `reach.py:112-119` with `twist_axis="X"`) **disappears** — the
  redesign removes `AimFrame` and `MatrixBlend` from reach entirely.

## 3. The new mechanism

    neutral_frame   static frame under rest_from; X = the neutral direction
    driver          collar root -> wrist position, expressed in that frame
                    IK: a probe constrained to ik_target
                    FK: a product of the FK controls' LOCAL matrices
                    blended by the ikFk switch
    elevation       atan2(t.y, hypot(t.x, t.z))      signed, +/-90
    azimuth         atan2(t.z, hypot(t.x, t.y))      signed, +/-90
    lift            remapValue(elevation) * <prefix>Lift   -> auto_grp.rz
    swing           remapValue(azimuth)   * <prefix>Swing  -> auto_grp.ry

### 3.1 The neutral frame folds the neutral into a matrix

Build a static orthonormal frame at the collar control's pivot, parented
under `rest_from` (the arm's `hang_from`, which is upstream of the reach):

    n = normalize(neutral_guide.world_position - collar_guide.world_position)
    u = normalize(Y_socket - (Y_socket . n) n)          # Gram-Schmidt
    f = n x u
    F = [n, u, f, collar_pivot]

Every quantity is measured from the **collar pivot**, not the shoulder: the
frame's origin, the neutral direction, and the driver position in section
3.2 all share that origin. The clavicle rotates about its own root, so that
is the honest centre — and it keeps the neutral guide's meaning simple:
*where the wrist sits when the collar is at rest.*

`F` is computed in Python at build time and parked on the frame's
`offsetParentMatrix`. The probe then hangs under that frame, so
`probe.translate` is **already expressed in the neutral frame** and both
axis neutrals are exactly zero by construction.

This is the load-bearing simplification. There are no neutral fields, no
subtract nodes, no runtime cost, and the neutral cannot drift out of sync
with the guide that authored it.

The frame also fixes the rotation axes unambiguously and symmetrically
across sides:

- **lift** is rotation about `f` — by the right-hand rule, a positive angle
  about `f = n x u` maps `n -> n cos + u sin`, so positive elevation lifts.
- **swing** is rotation about `u` — a positive angle about `u` maps
  `n -> n cos - f sin`, so a **positive azimuth needs a negative rotation
  about u**. The implementation negates one of the two; verify empirically
  before trusting the derivation.

### 3.2 The driver — collar root to wrist, acyclic in both modes

The collar drives `limb_from` (`arm.py:132-135`), which parents the entire
limb chain. Anything hanging off that parent is downstream of the
auto-collar and cycles if read back. Enumerated as downstream:
`puppet_group` (`limb.py:153-156`), `pole_base` (`limb.py:185-189`),
`soft_ik` (`limb.py:274-280`), the stretch/squash `Measure`s
(`limb.py:320-337`), the stretch *factor* (`limb.py:327,339`), the pole
control's and FK controls' **world** matrices (`limb.py:349-372`,
`228-229`), and every joint chain.

Genuinely upstream and safe to read: `ik_control` and `ik_tweak`, which are
created under `rig.groups.control` and are never constrained to `parent`
(`limb.py:195-206`); `switch_plug` (`limb.py:209-211`); every attribute on
`ik_control`; `ik_lengths.rest_plugs` (`limb.py:264-268`); `hang_from`
itself, including under limb lock, because `build_limb_lock` constrains
`lock_root` to the socket and reads `chain_root` only at build time
(`arm.py:102-105`, `limb_lock.py:129-130`); and — the key one —
**`fk_controls[i]["matrix"]`, a control's own local matrix, which depends
only on its own TRS channels and not on its offset group.**

**IK branch (2 nodes plus 1 transform).** A probe transform parented under
`neutral_frame`, `MatrixConstraint`'d to `ik_target` with rotation and
scale skipped. Its `translate` is the wrist position in the neutral frame.

**FK branch (2 nodes).** Each FK controller is parented under the previous
*controller* and `rig.controller` gives it its own offset group
(`limb.py:219,244`), so the hierarchy is `o_0 -> c0 -> o_1 -> c1 -> o_2 ->
c2`. Only `L(o_0)` is animated — it carries the `MatrixConstraint` to
`parent` (`limb.py:229`). `L(o_1)` and `L(o_2)` are plain static parenting.

The wrist is the origin of `c2`'s own space, and a node's own rotation never
moves its own pivot, so the whole hierarchy product gives the wrist position
directly. In Maya's row-vector convention (child first):

    N = L(c2) * L(o_2) * L(c1) * L(o_1) * L(c0) * B

    B = W_rest(o_0) * inverse(W_rest(neutral_frame))

`B` is one build-time constant mapping `o_0`'s rest space into the neutral
frame, and it absorbs both the rest value of the animated `L(o_0)` and the
offset between `limb_from` and `hang_from` at bind — which is why no
separate `limb_from`-to-`hang_from` term appears. `L(o_1)`, `L(o_2)` and `B`
are constants; `L(c0)`, `L(c1)`, `L(c2)` are the live
`fk_controls[i]["matrix"]` plugs. One `multMatrix` with six inputs into one
`translationFromMatrix`. Exact, no solver, no gimbal, no rotate-order
dependency.

`L(c2)` is included for completeness rather than effect: the FK controls
have `tx/ty/tz` locked (`limb.py:230`), so it contributes nothing today and
would contribute correctly if that ever changed.

**Blend (1 node).** `blendColors` on the two `double3` positions, weighted
by `switch_plug`. Confirm the switch's polarity at the wiring site rather
than assuming it.

**Why not the upper arm.** Driving off the humerus would require a shadow
IK chain under `hang_from` (roughly 12-15 nodes and a second solve per arm)
which cannot inherit the real limb's stretch, soft-IK or pole-pin — all
downstream — so it straightens earlier than the real arm and visibly
disagrees with it. It also makes the clavicle react to elbow bend and
pole-vector position, so an animator swinging the pole around the arm axis
would see the collar move. Production auto-clavicles drive off animator
inputs, not the solved skeleton.

**Known limitation.** The FK branch reads a fixed-length chain: the FK
controls have `tx/ty/tz` locked (`limb.py:230`) and the segment-scale
attributes live on `ik_control`, driving joint translation rather than the
FK controls' offsets. So FK stretch does not reach the driver. Acceptable —
it changes the reach *distance*, and only the *direction* is read.

### 3.3 The angles — an off-plane `atan2` that never wraps

    elevation = atan2(t.y, hypot(t.x, t.z))
    azimuth   = atan2(t.z, hypot(t.x, t.y))

**Not** `atan2(y, x)`, which has a genuine branch cut on the -X axis — the
arm folded across the chest — where the clamped output would jump from the
upper limit to the lower one. The off-plane form is monotone, is exactly
+/-90 at the poles, has no branch cut anywhere, and degrades gracefully.

Each `hypot` is one `distanceBetween` with two of the three components
wired and `point2` left at the origin. `atan2` is a core node from Maya
2024 onward: `input1 = y`, `input2 = x`, output is a `doubleAngle`, and
`atan2(0,0) = 0` with no NaN. Feeding it into `remapValue.inputValue`
auto-inserts a `unitConversion` (57.2958) and the trip back out to a
`rotate` channel inserts the inverse, so the arithmetic stays in degrees
end to end at a cost of two `unitConversion` nodes per strand.

Rejected: swing-twist quaternion decomposition (the `systems/twist.py:134`
pattern). It extracts rotation *about* an axis, which for a combined
elevation-plus-azimuth swing is contaminated by the other swing; it needs a
rotating transform where the driver is a position; and it drags in the
`quatNodes` plugin.

### 3.4 The curve — one three-point `remapValue` per axis

Per axis, with authored `min_angle < 0 < max_angle` and outputs
`min_output`, `max_output`:

    inputMin  = min_angle      outputMin = min_output
    inputMax  = max_angle      outputMax = max_output

    ramp points (position, value), all at the chosen interpolation:
        (0.0, 0.0)
        (p0,  v0)   p0 = (0 - min_angle)  / (max_angle  - min_angle)
                    v0 = (0 - min_output) / (max_output - min_output)
        (1.0, 1.0)

At `input = 0` the normalised position is `p0`, the ramp value is `v0`, and
the output is `min_output + v0 * (max_output - min_output) = 0`. The
neutral is exact for any asymmetric pair of limits and any asymmetric pair
of outputs.

`remapValue` **clamps** outside `[inputMin, inputMax]` — verified out to
twice the range, no extrapolation. Saturation is free.

**Smoothness, measured.** Interpolation shapes on a two-point 0..1 ramp:

| interp | shape | slope at 0 | slope at 1 |
|---|---|---|---|
| linear | `t` | 1 | 1 |
| **smooth** | raised cosine `(1-cos pi t)/2` | **0** | **0** |
| spline | Catmull-Rom-ish | ~0.5 | ~0.5 |

The three-point ramp measured at `inputMin=-40, inputMax=+60,
outputMin=-8, outputMax=+22`, ramp points `0.0->0.0`, `0.4->8/30`,
`1.0->1.0`, all `smooth`:

    input   -90   -41   -40   -39   -20    -5     0    +5   +20   +50   +60   +61  +120
    output -8.00 -8.00 -8.00 -7.99 -4.00 -0.30  0.00 +0.37 +5.50 +20.5 +22.0 +22.0 +22.0

At 0.1 either side of the neutral the output is 0.00012 in magnitude — zero
slope on both sides. Same at -40.1/-39.9 and at +59.9/+60.1.

**The structural result:** because a raised cosine has zero derivative at
*every* ramp point, a single three-point `smooth` ramp is C1 at the neutral
crossing **and** at both saturation limits, for any asymmetric limits and
outputs, with no tangent matching required. Two back-to-back ramps would
have needed `max_output/max_angle == min_output/min_angle` to avoid a kink
at zero. This is why the design uses one ramp per axis rather than two.

**The one cost.** Zero slope at the neutral is a dead zone: at 10 degrees
into a 60 degree range the collar has moved 1.47 of its 22 degrees.
Anatomically this is the scapular setting phase, so it is defensible as a
feature — but it must be documented, because a tight limit will feel
sluggish.

### 3.5 The output

`auto_grp` already exists between `collar_ctrl.offset` and
`collar_ctrl.transform` (`arm.py:149-152`) and is a rig helper, so driving
its `rotate` channels live is permitted — the live-TRS rule binds bind
joints only.

It is rebuilt **aligned to the neutral frame's orientation, positioned at
the collar control's pivot**, so that `rz` is lift and `ry` is swing with no
per-side axis juggling. A static `collar_align` transform is inserted
between `auto_grp` and `collar_ctrl.transform` carrying the constant
rotation back to the collar's own orientation, which keeps the collar
control's channels zeroed at bind. Group order becomes:

    collar_ctrl.offset -> auto_grp -> collar_align -> collar_ctrl.transform

`auto_grp.rotateOrder` is `xyz`, which in Maya composes as `Rz * Ry * Rx` —
lift outermost, matching the anatomical hierarchy. At these magnitudes the
order is worth about a degree either way.

Each remap output is multiplied by its own animator attribute
(section 4.3) before reaching the channel.

### 3.6 Node budget

Roughly 2 transforms plus 2 `distanceBetween`, 2 `atan2`, 2 `remapValue`,
2 multiplies and 4 `unitConversion` for the angle strands, plus 2 nodes and
a transform for the IK branch, 2 for the FK branch and 1 `blendColors` —
about **21 nodes** against the current mechanism's 20 or so (4 transforms,
2 `multiplyDivide`, `angleBetween`, `remapValue`, `aimMatrix`,
`multMatrix`, `blendMatrix` and three `MatrixConstraint` networks).
Comparable cost, and it avoids the second IK solve that the rejected
humerus driver would have required.

## 4. The authoring surface

### 4.1 Rigger fields on `Arm`

Replacing `auto_collar_start` and `auto_collar_end`, keeping `auto_collar`
and `auto_collar_interpolation`:

| field | default | meaning |
|---|---|---|
| `auto_collar` | `True` | build the network at all |
| `auto_collar_lift_min_angle` | `-45.0` | arm elevation at full downward falloff |
| `auto_collar_lift_max_angle` | `120.0` | arm elevation at full upward falloff |
| `auto_collar_lift_min_output` | `-6.0` | collar degrees at `lift_min_angle` |
| `auto_collar_lift_max_output` | `15.0` | collar degrees at `lift_max_angle` |
| `auto_collar_swing_min_angle` | `-45.0` | arm azimuth at full backward falloff |
| `auto_collar_swing_max_angle` | `90.0` | arm azimuth at full forward falloff |
| `auto_collar_swing_min_output` | `-6.0` | collar degrees at `swing_min_angle` |
| `auto_collar_swing_max_output` | `10.0` | collar degrees at `swing_max_angle` |
| `auto_collar_interpolation` | `"smooth"` | shared by both sides of both axes |

Defaults are starting points, not anatomy. Life gives roughly 15 degrees of
clavicular elevation across 180 degrees of humeral elevation; animators
consistently want more than life, so riggers are expected to push these.

`Arm.validate()` gains `min_angle < 0 < max_angle` on each axis. The
neutral must lie strictly inside the input range or the middle ramp point
is degenerate. It also gains the cycle rule in section 7.

### 4.2 The neutral guide

`GuideLayout` gains a `neutral` role, drawn as a child of `collar` and a
sibling of `shoulder`. `GuideDraft.joint` positions are **absolute, not
parent-relative** — the existing arm reads `collar (2,0,0)`,
`shoulder (5,0,0)`, `elbow (9,0,-1)`, `hand (14,0,0)` (`arm.py:81-85`), so
the default guide arm is already a T-pose lying along X. The neutral guide
therefore defaults just beyond the hand on that same line:

    guides.joint("neutral", (16 * mult, 0, 0), parent=collar, radius=0.8)

Only the direction matters, so sitting past the hand rather than on top of
it costs nothing and keeps the guide selectable. The default neutral is
consequently the T-pose, which is what was asked for.

It is excluded from `_derive_size` (`limb.py:466-471`, fed an explicit role
list at `arm.py:91`) and from the chain orient pass, both of which take
their roles explicitly.

The direction is read as
`neutral_guide.world_position - collar_guide.world_position`, not as an
orientation, because `GuideDraft.joint` takes no orientation argument
(`trigger/maya/rig.py:67-75`).

Everything else in the guide layer is role-driven and needs no change:
`instance_from_nodes` exports every tagged guide by `(role, index)`
(`guides/nodes.py:169-176`), `GuidePose` carries position, world rotation
and rotate order (`core/schemas.py:15-25`), and `GuideScene.mirror`
(`guides/scene.py:556-567`) mirrors poses — so **the neutral direction
mirrors for free**, which a float field never would. That is the decisive
argument for a guide over a `guide_attrs` entry, alongside the fact that a
draggable guide is the only option in which the rigger can *see* the
neutral, and invisibility is the original complaint.

`GuideDraft.joint` forces `SIDE_COLORS` (`rig.py:103`), so the small radius
is the only distinguishing mark for now. Per-guide colour is out of scope.

### 4.3 Animator attributes

Two, both on the IK control, both `0..1`, both defaulting to **0.0**:

    <prefix>Lift    scales the elevation axis's output degrees
    <prefix>Swing   scales the azimuth axis's output degrees

For the arm, `prefix = "autoCollar"`, giving `autoCollarLift` and
`autoCollarSwing`. The system names nothing itself — wording is policy, so
the module supplies the prefix, as today.

These replace `autoCollar`, `autoCollarVertical` and `autoCollarHorizontal`.

- **The master `autoCollar` goes.** It is arithmetically redundant once each
  axis has its own scalar; zeroing both is the same off switch. The only
  loss is a single key for a whole-feature fade, which is not worth a third
  attribute.
- **The two per-axis scalars stay, and move to the output side.** They are
  animator-facing and answer a question no build-time field can: "lift the
  shoulder on this reach but do not let it swing forward." Today they scale
  the offset vector *before* the aim, warping both the aim direction and
  the ramp input — which is precisely the bug in section 2.2. Multiplying
  the remap *output* instead is linear, cannot move the neutral, and cannot
  break the bind pose: at any scalar value, an elevation of 0 still yields
  an output of 0.
- **Default 0.0** preserves today's behaviour, where the network is built
  but inert until an animator opts in.

### 4.4 Interpolation

The `linear` / `smooth` / `spline` enum is kept with `smooth` as the
default, but only `smooth` is kink-free. Document alongside the field:

- `smooth` — C1 at the neutral and at both limits.
- `linear` — kinks at the neutral (the slopes differ whenever
  `min_output/min_angle != max_output/max_angle`) and at both limits.
- `spline` — kinks at both limits, always (section 2.4).

## 5. Migration — declared-but-missing guide roles

`.trg` import does **not** run `draw_guides`.
`GuideScene.import_guide_instances` (`guides/scene.py:266-300`) creates one
joint per `(role, index)` **present in the file**. Adding the `neutral`
role therefore means `rig.guide("neutral")` raises `GuideError`
(`trigger/maya/rig.py:188-194`) on every existing asset — a build failure,
not a degraded build. (The authoring path is already tolerant:
`create_guides` -> `draw_guides` -> `apply_poses`, `guides/scene.py:73-95`,
draws all declared roles and applies only the poses present.)

The fix is in the import path, not in the arm module: teach
`import_guide_instances` to create declared-but-missing roles at their
`draw_guides` positions. The import path silently diverging from the
manifest is the real defect, and fixing it there means no future module
that adds a guide hits this. `guide_attrs` already degrade correctly by
this rule — the import loop reads `module_cls.attrs_for_role(role)` and
defaults anything missing to `item.default` (`guides/scene.py:282-287`) —
so guides are simply catching up with attributes.

## 6. tik.maya additions

- **`Remap` gains multi-point ramps.** `Remap.create` currently writes only
  ramp indices 0 and 1 with positions and values hard-coded to 0.0 and 1.0
  (`constructs/remap.py:120-124`). It gains a `points` argument — a
  sequence of `(position, value)` pairs — defaulting to today's two-point
  behaviour. Backward-compatible, pure mechanism, no policy. `value_Interp`
  is per ramp point, so applying one shared enum to every point is correct.
- **Optionally, a small direction-to-angles construct** wrapping the
  `atan2` and `distanceBetween` pair per axis. Pure mechanism: it creates
  no controller and names no user-facing attribute, so it sits inside the
  layer. Judgement call at implementation time — if the wiring reads
  clearly inline in `reach.py`, skip it.

Nothing else in tik.maya changes. `AimFrame` and `MatrixBlend` simply stop
being called from reach.

## 7. Validation and cycle safety

The redesign's inputs are `hang_from`, `ik_tweak`, the FK controls' local
matrices and `switch_plug` — all upstream of the collar. **No cycle.** Two
hazards deserve guarding:

1. `space_controls = ("ik", "pole")` (`arm.py:39`) lets a rigger add a
   space to the IK control. A space targeting this arm's own `collar`
   output — or anything under it — makes `ik_tweak` downstream and cycles
   the reach. **This is already true today and nothing catches it.**
   `Arm.validate()` gains a rule for it.
2. Reading `fk_controls[i]["matrix"]` is safe only while those controls
   stay parented control-to-control with static offset groups. If an
   intermediate FK offset is ever constrained to something downstream, the
   FK branch cycles silently. A comment at the read site, naming
   `limb.py:224` as the invariant.

## 8. Testing

Unit (`tests/unit/`):

- `Remap.create` with three points writes the ramp indices, positions,
  values and per-point interpolation it was given; the two-point default is
  unchanged.
- The ramp-point arithmetic (`p0`, `v0`) is pure Python and gets a direct
  test at the asymmetric limits used in section 3.4.
- `Arm.validate()` rejects `min_angle >= 0`, `max_angle <= 0`, and an IK
  space targeting this module's own `collar` output.
- `import_guide_instances` creates a declared-but-missing role at its
  `draw_guides` position, and an old `.trg` without `neutral` still builds.

Integration, against a real scene (`tests/integration/trigger/`):

- **Bind pose is exact.** With both animator scalars at 1.0 and the arm at
  its guide pose, the collar's world matrix equals its bind matrix. This is
  the regression test for section 2.2, and it fails on today's code.
- **The neutral is where the guide says.** Sweeping the arm through the
  neutral direction, the collar's delta crosses zero at the guide's
  direction and nowhere else, and the *sign* of the delta is opposite
  either side. This is the regression test for section 2.1.
- **Saturation.** Past `max_angle` the collar's rotation stops changing;
  sample well beyond it (today's code reaches +139 degrees at +120).
- **Smoothness.** Finite differences across the neutral and across both
  limits stay below a tolerance — no step, no corner.
- **IK/FK parity.** Match FK to IK at several poses; the collar's rotation
  agrees across the switch to within tolerance.
- **Per-axis isolation.** With `autoCollarSwing` at 0 and `autoCollarLift`
  at 1, moving the hand purely forward leaves the collar unrotated, and
  vice versa. This is the test that proves the two strands reached the
  right `remapValue`.
- **No cycle.** Evaluate the graph in IK and in FK and assert Maya reports
  no cycle, on both a plain and a limb-locked arm.
- **Mirroring.** A mirrored arm's neutral direction mirrors, and its
  measured neutral matches.

## 9. What is removed

- `AngleBetween`, `AimFrame` and `MatrixBlend` from `reach.py`, and with
  them the parallel-up hazard that `twist_axis="X"` worked around.
- The `probe` -> `multiplyDivide` -> `aim_point` scaling chain.
- The `autoCollar` master attribute.
- The input-side `autoCollarVertical` and `autoCollarHorizontal`
  multipliers, replaced by output-side `autoCollarLift` and
  `autoCollarSwing`.
- `auto_collar_start` and `auto_collar_end`.

## 10. Out of scope

- Applying the redesigned reach to a leg or hip module. The system stays
  reusable — it names nothing, and takes its prefix and its axis specs from
  the caller — but no second consumer is built here.
- Per-guide colour, so the neutral guide is distinguished only by radius.
- An interactive "sample the current pose as neutral" tool. The guide is
  the authoring surface; a sampler would write to it, and can be added
  later without touching this design.
- FK segment-scale stretch in the FK driver branch (section 3.2).
