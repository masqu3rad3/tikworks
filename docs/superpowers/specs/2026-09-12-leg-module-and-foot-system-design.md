# The Leg: a foot is a second solver, not a longer arm

**Date:** 2026-09-12
**Status:** implemented
**Amends:** `2026-08-30-trigger-simplification-design.md` — `build_ikfk_limb` is no longer the
only way into the limb system. It splits into a controls phase and a solve phase, and the solve
phase takes a `driver`. The single-call entry point survives unchanged and the arm keeps using
it, so nothing in that spec's layering is withdrawn.

---

## 1. Why

The arm ends at the hand. Whatever the hand does afterwards — fingers, a prop, nothing — hangs
off an output and is somebody else's module. That is what let `arm` be 350 lines: the IK chain
runs collar-to-wrist, one `ikRPsolver` handle, and the last joint *is* the end of the story.

A leg is not that. The ankle is the end of the IK chain and the *middle* of the rig. Below it
sit a ball and a toe, two more solver handles, and a stack of pivots that has to be **upstream**
of the leg's own IK handle so that rolling onto the toe drags the ankle — and therefore the
knee, and therefore the hip — with it. The foot is not downstream of the limb. It is wrapped
around it.

That single structural fact is what this spec is about. Everything else — eleven guides instead
of five, six more controllers, nine proxy attributes — follows from it and is comparatively
mechanical.

### 1.1 What we are not doing

The old `trigger` leg was 2,713 lines and 101 KB. It is not a model to port. It contains two
built-in ribbons, a hand-rolled soft-IK network of nineteen `multiplyDivide` nodes, its own
stretch and squash, its own angle extractor, and four IK chains where three sets of joints
would do. Every one of those now exists as a tested construct or system that the arm already
consumes.

What the old module *is* good for is its inventory of decisions: which guides a rigger needs to
place, which pivots a foot roll needs, in what order they nest, and which attributes animators
actually ask for. §2 records that inventory. The rest of this spec builds it out of parts we
already have.

## 2. The old leg, as an inventory

**Guides (9):** `LegRoot`, `Hip`, `Knee`, `Foot`, `Ball`, `HeelPV`, `ToePV`, `BankIN`,
`BankOUT`. Four chain joints, one toe tip, and four position-only markers around the foot.
Note that `Toe` and `ToePV` are distinct: the toe *joint* at `(0,0,4)` and the pivot at the
front of the shoe at `(0,0,4.3)`.

**The reverse-foot stack** (`create_ik_setup`, outermost first):

```
pv_bankIn → pv_bankOut → pv_heel → pv_ballSpin → pv_toe → pv_ballRoll → pv_ballLean → master_ik
                                                        └→ pv_ball  (holds ikBall + ikToe)
```

`master_ik` carries the leg's own SC and RP handles, so everything above it displaces the whole
leg. `pv_ball` carries the ball and toe handles, so it bends the toes without moving the leg.

**Nine attributes on the IK foot control** drive it, each through a `multiplyDivide` whose
second input is the side multiplier:

| attribute | drives | side multiplier |
|---|---|---|
| `bLean` | `pv_ballLean.rotateZ` | `sideMult` |
| `bRoll` | `pv_ballRoll.rotateY` | `sideMult` |
| `bSpin` | `pv_ballSpin.rotateZ` | `sideMult` |
| `hRoll` | `pv_heel.rotateX` | **1** — deliberately un-mirrored |
| `hSpin` | `pv_heel.rotateY` | `sideMult` |
| `tRoll` | `pv_toe.rotateX` | **1** — deliberately un-mirrored |
| `tSpin` | `pv_toe.rotateY` | `sideMult` |
| `tWiggle` | `pv_ball.rotateY` | `sideMult` |
| `bank` | `pv_bankIn.rotateX` / `pv_bankOut.rotateX` | via set-driven keys at ±90 |

The two exceptions are a finding, not a quirk. §6.3 shows why the whole table disappears.

**`autoHip`** is a two-locator angle extractor blended between IK and FK, multiplied by a 0–1
`autoHip` attribute (default 1.0), driving `cont_thigh_auto.rotateZ`. That is the auto-collar,
on one axis, built before `systems/reach.py` existed.

## 3. The shape of the work

Three pieces, and no module inherits from another.

**`systems/limb.py`** splits. `build_limb_controls()` creates the puppet chains and the IK/FK
controllers; `build_limb_solve()` wires the handle, the lengths, soft-IK, stretch, squash, the
pole and the blend onto the bind joints. `build_ikfk_limb()` remains, calling the two in
sequence with its current signature and current behaviour. §4 covers the seam.

**`systems/foot.py`** is new. Given the limb's controls, the foot guides and the switch plug, it
builds the reverse-foot pivot stack, the mirrored controller chain, the ball and toe extensions
on both puppet chains, the blend onto the ball and toe bind joints, and the auto-roll network.
It returns the node the limb solve must follow. It names no attribute the module has not
supplied a prefix for, and it is reusable by a hindleg.

**`modules/leg/leg.py`** composes them, exactly as `arm.build()` composes `build_ikfk_limb`,
`build_reach` and `build_limb_lock`.

### 3.1 Two helpers become public

`systems/limb._derive_size` is already imported by `arm.py` with its underscore intact; the leg
makes that two callers. `arm._conventional_frames` is private to the arm and the leg needs it
verbatim. Both move to `systems/limb.py` as `derive_size` and `conventional_frames`. No aliases are
kept: there is no backward compatibility to preserve, so the underscored spellings are deleted
outright and the arm's import is updated with them.

### 3.2 The IK control gets no `pivot_controls` entry

`arm` declares `pivot_controls["ik"] = "hand"` and ships three preset rows. The leg declares
**no pivot for its IK control**. The reverse foot already owns that pivot, and offering both
would give the animator two independent pivots on one node, silently fighting: `rotatePivot`
would move the control while the pivot stack moved the rig, and the two corrections do not
compose. The leg's other controls are offered pivots as usual.

## 4. The limb seam

`build_ikfk_limb` hard-wires `result.ik_tweak` as the thing the solve follows. Every consumer of
that choice is in the second half of the function:

```
_build_chains            chains, puppet group
pole_rest = _pole_rest_position(ik_joints)      <- captured before the solve moves anything
_build_pole_base
_build_controls          ik_control, ik_tweak, switch_plug, fk_controls, hinge_axis
------------------------------------------------------------------ the seam
segment scales
IkHandle.create + MatrixConstraint(driver -> ik_joints[-1], rotation only)
_build_lengths / _build_soft_ik(driver) / _build_stretch(driver) / _build_pole(driver)
_build_visibility / _blend_to_bind
```

The leg cannot pass a driver into the single call, because the driver is built *from* the IK
control, which the call itself creates. Four ways out were considered:

1. **Split into two calls.** Chosen.
2. **A `driver_from` callback** that receives the control and returns the driver. Smallest diff,
   but it hides an entire sub-rig inside a keyword argument and the leg's build order stops
   being readable from `leg.build()`.
3. **Build normally, then re-point the handle constraint.** Requires deleting something just
   built, and leaves `_build_soft_ik` and `_build_pole` measuring the ankle's old position with
   no error — the exact class of bug that is invisible until an animator notices the soft-IK
   kicking in early.
4. **Let the leg build its own IK.** Duplicates stretch, squash, soft-IK, pole and blend-to-bind,
   and guarantees the arm and the leg drift.

### 4.1 The new signatures

```python
def build_limb_controls(rig, guides, *, name="", parent=None,
                        controller_size=None, labels=None) -> LimbResult
def build_limb_solve(rig, result, *, driver=None, bind_joints=None, soft_ik=True,
                     stretch=True, squash=True, stretch_limit_default=50.0,
                     pole_pin=False) -> LimbResult
```

`driver=None` means `result.ik_tweak`, which is what makes the arm's behaviour identical. Two
values that phase one computes and phase two needs move onto `LimbResult`: `pole_rest` and
`parent`. `pole_rest` **must** be captured in phase one — it is read before the solve is wired
precisely because the pole and soft-IK constraints move the chain, and every offset baked
afterwards depends on that untouched pose.

`build_ikfk_limb` keeps its signature and becomes six lines. **The arm is not edited.** The
existing `test_arm_trigger.py`, `test_limb_system.py` and `test_module_ground_rules.py` are the
regression net for the refactor, and they must pass unchanged before the leg is started.

## 5. Guides

Eleven roles. The naming follows the arm's discipline: anatomical, unabbreviated, and the same
word the bind joint will carry.

| role | kind | arm analogue | old name |
|---|---|---|---|
| `hip` | ROOT | `collar` | `LegRoot` |
| `thigh` | JOINT | `shoulder` | `Hip` |
| `knee` | JOINT | `elbow` | `Knee` |
| `ankle` | JOINT | `hand` | `Foot` |
| `ball` | JOINT | — | `Ball` |
| `toe` | JOINT | — | `Toe` |
| `heel` | REFERENCE | — | `HeelPV` |
| `tip` | REFERENCE | — | `ToePV` |
| `bank_in` | REFERENCE | — | `BankIN` |
| `bank_out` | REFERENCE | — | `BankOUT` |
| `neutral` | REFERENCE | `neutral` | — (auto-hip had none) |

```python
guides = GuideLayout(
    "hip", "thigh", "knee", "ankle", "ball", "toe",
    "heel", "tip", "bank_in", "bank_out", "neutral",
    reference=("heel", "tip", "bank_in", "bank_out", "neutral"),
    oriented=("ankle",),
)
```

`reference` is already the right vocabulary: a heel marker is read for its position and nothing
in the rig is shaped like it, which is the 2026-09-12 guide-kinds spec's definition exactly. It
also buys the drawing behaviour for free — a reference guide is a locator *transform*, so it
suppresses its own bone without suppressing its siblings, which is what stops four markers
smearing a blob under the ankle.

### 5.1 The oriented guide has children, and the arm's is the last joint

`oriented=("ankle",)` follows the arm's rule: the chain is oriented by convention at build time
(X to the next joint, Y up, both sides), and exactly one guide's rotation is read — the one that
aligns the extremity to the model.

The arm gets away with this cheaply because `hand` is the **last** joint, so re-aligning it
disturbs nothing below. The leg's `ankle` has `ball` and `toe` under it. Re-orienting a joint
rotates everything beneath it, so the build order is load-bearing:

1. Build the whole bind chain `hip → thigh → knee → ankle → ball → toe` at guide positions.
2. Align every joint to its conventional frame, **root first** — each child is put back after
   its parent moves, which is the arm's existing documented rule.
3. Align `ankle` to its guide's rotation only.
4. **Re-align `ball` and `toe` to their conventional frames**, because step 3 just rotated them.

Step 4 has no counterpart in the arm and is the single easiest thing to omit. It gets a test that
rolls the `ankle` guide and asserts the ball's X axis still points at the toe.

### 5.2 The A-pose question does not arise

The arm draws an A-pose because it gives better shoulder deformation and because its auto-collar
neutral must be exactly collinear with the hand. A leg is drawn in its rest stance: the chain
hangs down with the knee pushed forward in +Z so the bend plane is unambiguous, which is what the
old module's `knee_vec = (5·side, 5, 1)` was doing. `neutral` is derived from `hip` and `ankle`
by the same `NEUTRAL_REACH` extrapolation the arm uses, and for the same reason — a hand-written
triple is only approximately collinear, and the arm measured that rounding to one decimal put it
0.006 out, sixty times the tolerance the bind-pose test allows.

## 6. The foot: two chains that stay in lockstep

### 6.1 Why two

The ground rules say `control_grp` holds nothing but controllers and their offset groups, and
`rig_grp` holds the puppet. The old module parents the ball and toe IK handles directly under a
pivot group; if that pivot were a controller, handles would live in `control_grp`.

So the foot builds **two parallel hierarchies**:

```
rig_grp                                        control_grp
  foot_root      <- MatrixConstraint(ik_tweak)   bank_ctrl.offset <- MatrixConstraint(ik_tweak)
    bank_in      rx <- min(bank_ctrl.rx, 0)         bank_ctrl        rx bank
      bank_out   rx <- max(bank_ctrl.rx, 0)           heel_ctrl      rx heelRoll  ry heelSpin
        heel     rx ry                                  ball_spin_ctrl  rz ballSpin
          ball_spin  rz                                   toe_ctrl      rx toeRoll  ry toeSpin
            toe      rx ry                                  ball_ctrl   ry ballRoll rz ballLean
              ball_roll  ry rz                                toe_wiggle_ctrl  ry toeWiggle
                ankle_driver  ---> build_limb_solve(driver=)
              toe_wiggle   ry  ---> constrains ikBall + ikToe handles
```

The nesting on the left is the old module's, unchanged. `ball_roll` merges the old `pv_ballRoll`
and `pv_ballLean`: they pivot at the same point and are adjacent in the chain, so two nodes were
tidiness, not mechanism. `ballSpin` stays where it is — above the toe pivot — because that is
what makes spinning the foot on the ball independent of rolling over the tip.

### 6.2 Lockstep is by construction, not by constraint

Each controller sits at its pivot's position with the same ancestor chain, so it inherits its
ancestors' rotation exactly as its pivot does. No constraints run between the two hierarchies and
no cycle is possible. The only wiring is one channel connection per driven axis:

```
pivot.<chan>  =  ctrl.offset.<chan> + ctrl.<chan>
```

The sum is what §8 needs: the auto-roll drives the **offset group**, the animator drives the
**controller**, and the pivot takes both. Without it, an auto-roll offset would move the rig and
leave the animator's control behind, visually detached from the foot it is driving.

**Two exceptions, not one.** §6.4 carves out `bank`: one control channel feeds two mutually
exclusive pivots, so there is no single pivot node for `bank_ctrl` to be the twin of. The second
is structural rather than semantic: the control chain is strictly linear (`toe_wiggle_ctrl` under
`ball_ctrl`), while §6.1's own diagram has the pivots branch (`toe_wiggle` is a **sibling** of
`ball_roll` under `toe`, not a child of it). Rotating `ball_ctrl` therefore moves the
`toe_wiggle` gizmo even though the `toe_wiggle` pivot it is nominally the twin of does not move.
It is harmless — the channel sum in each pivot's own local space is unaffected by where its
controller's gizmo happens to be drawn, so the delivered value is correct — but it is a second
place lockstep does not hold, and 6.2 should say so rather than let 6.4 read as the only one.

The IK handles are *constrained* to `toe_wiggle`, not parented under it — the same pattern
`_build_soft_ik` already uses to drive the leg's own handle from `soft_ik.goal_matrix`.

### 6.3 The frame is behaviour-mirrored, and no sign rule is needed

**Twice corrected. The original claim -- that a frame built from each foot's own geometry
retires the legacy's side handling -- was withdrawn on measurement, replaced with a sign rule,
and the sign rule is now withdrawn too. What follows is the third and final answer, and unlike
the first two it rests on a uniqueness proof rather than on a reading of the legacy.**

#### What was measured

Build the frame by aiming local Z heel->tip with local Y up, on each foot, from that foot's own
geometry. On both a straight and a 25-degree toed-out foot, the right frame comes back as the
naive mirror **with its X column negated**: `z_R = M z_L`, `y_R = M y_L`, `x_R = -M x_L`, where
`M = diag(-1, 1, 1)`.

That is forced, not incidental. For any reflection `M`, `(Ma) x (Mb) = det(M) M(a x b) =
-M(a x b)`. The frame takes Z from a point difference and Y from a point difference
(Gram-Schmidt'd, and dot products are reflection-invariant), so both mirror cleanly -- while X
is their cross product and must come back negated. **No guide layout can make it otherwise.**

Consequently, with naive mirrored frames, a local rotation about X produces mirrored world
motion while rotations about Y and Z produce the mirror of the *negated* angle.

#### Why the obvious remedy is wrong

The tempting fix is to negate `rotateY` and `rotateZ` on the mirrored side -- which is, exactly,
what the legacy did, and the legacy's two "unexplained" exemptions turn out to be its `rotateX`
channels. (All three of them: `hRoll`, `tRoll` and `bank` all escaped `sideMult`, and all six
`rotateY`/`rotateZ` drivers took it.) So the legacy was right, and this spec's first version was
wrong to read those exemptions as a smell.

But adopting that rule here breaks something this design promises elsewhere. `rig.controller`
does **not** set orientation from its `mirror=` argument -- that argument is a tag plus a
shape-orient conjugation. A controller's frame comes from `match=` and its ancestor chain, so
under 6.2 the foot controls inherit their *pivots'* frames. Put the sign on the control-to-pivot
connection and, on the right leg, the animator turns a handle one way while the foot turns the
other, on six of the ten driven channels. 6.4 spends a paragraph apologising for **one**
detached handle. Six more, on one side only, is not a footnote -- it is the lockstep claim of
6.2 quietly failing.

#### The frame-level fix, and why it is the only one

Require that the mirrored frame reproduce mirrored motion for *every* rotation:

```
F_R R F_R^T  =  M (F_L R F_L^T) M      for all R in SO(3)
```

Set `C = (M F_L)^T F_R`. The requirement becomes `C R C^T = R` for all `R`, so `C` commutes with
all of SO(3), so `C = +/-I`. And `det C = det(M) det(F_R) det(F_L) = -1`. Therefore **`C = -I`**:

```
F_R  =  -M F_L  =  diag(1, -1, -1) . F_L  =  Rx(180) . F_L
```

The solution is unique, and it is the **behaviour mirror** -- the left frame rolled 180 degrees
about the world mirror normal. Three candidates were considered and two were rejected for the
wrong reason: `Ry(180)` gives `C = diag(-1, 1, -1)` and `Rz(180)` gives `C = diag(-1, -1, 1)`,
neither of which is `-I`. `Rx(180)` is the one that works, and it was initially skipped because
it is the ugliest to look at: on the right foot it points Z backwards *and* Y downwards.

Crucially it is a **proper rotation**: `det(-M F_L) = (-1)^3 . (-1) . (+1) = +1`. There is no
negative scale, no flipped normal, and nothing for `jointOrient` to choke on -- which was the
stated reason for rejecting a "true mirrored frame" and does not apply here.

It is also already this repo's convention. `mirror_orient` in `tik/trigger/maya/rig.py` says it
outright: *"The right side is mirrored by behaviour: its joints carry a 180 degree roll about
X."* Conjugation by `Rx(180) = diag(1,-1,-1)` and by `diag(-1,1,1)` are the same operation, so
this is not a new rule at all -- it is the repo's existing mirror algebra, reappearing.

#### What it costs and what it buys

One line, in `foot_frame`, on the mirrored side only:

```python
aim, up = ((0, 0, -1), (0, -1, 0)) if rig.side_mult < 0 else ((0, 0, 1), (0, 1, 0))
```

Aiming local `-Z` at the tip puts `+Z` behind the heel; upping on `-Y` puts `+Y` down; and
`X = Y x Z` then lands on `-M x_L`, giving exactly `-M F_L`.

In exchange: **no sign anywhere else in the foot.** `CONTROL_CHANNELS` connects straight
through, 6.4's bank clamps take no side term, 8's auto-roll takes none, 6.2's lockstep holds
unconditionally on both legs, and `mirror="behaviour"` on the foot controls becomes literally
true rather than a tag that lies to the pose-mirror tool. The frame still does the job it was
introduced for: a toed-out foot defines its own roll axes instead of inheriting a world
convention.

#### How it was found

Task 8's first pass measured the frame as exact world identity, because the default guide layout
puts heel and tip at the same X and Y. Every frame assertion was satisfied by an identity
matrix, and both feet were trivially equal -- the original claim appeared to hold in the one
case where the mechanism does nothing. Re-testing on a toed-out foot, the ordinary production
pose, is what exposed it. **A claim proven only where its mechanism is inert is not proven.**

### 6.4 Bank is two linear connections

```
bank_out.rx = max(bank, 0)
bank_in.rx  = min(bank, 0)
```

The old module used `setDrivenKeyframe` at ±90 with linear tangents, which is a straight line
expressed as an animation curve. A build should not be laying down animation curves: they are
editable, they serialise into the scene, and a rigger who scrubs onto them cannot tell they were
authored by code. Two clamps do the same job with no keys.

**Bank is one of §6.2's two places lockstep does not hold**, and it cannot: one control channel
feeds two mutually exclusive pivots, so there is no single pivot node for `bank_ctrl` to be the
twin of. It sits at the top of the control chain and is a handle for a value rather than a visual
twin of the rig's motion — rotating it does not tilt it onto the edge the foot banks over.

That position at the top of the chain has a mechanical consequence, and it is the one that
actually drew blood during assembly: `bank_ctrl` is parented directly under the world-aligned IK
control, not under a behaviour-mirrored sibling the way every other foot control is. Its offset
group is therefore not frame-aligned, and its local decomposition of whatever rest rotation sits
between the IK control and the frame is a *real* value, not zero. On the mirrored side that
decomposition lands on exactly `rotateX = -180` (the frame's `Rx(180)`, read through a
non-mirrored parent); on either side, a rolled ankle guide puts a nonzero rest rotation into that
same offset regardless of side. Concretely: **§6.2's `pivot = offset + ctrl` rule does not apply
to bank.** `bank`'s offset must never be summed into its live value — an implementation pass
during this work did sum it, which pushed every pivot from `bank_in` down off its rest pose the
instant the connection was wired (caught by
`test_a_mirrored_foot_rests_and_rolls_exactly_like_the_source` in `test_foot_system.py`) — and a
future auto-roll target must never be `bank` for the same reason: there is no meaningful "offset"
to drive. The formula below has always been written without an offset term; the summed version
was an implementation deviation, and removing it was a return to this spec, not a change to it.

A single pivot node whose `rotatePivot` switches between the two marker positions on the sign of
`bank` would restore the correspondence, and the switch is free because the rotation is zero at
the instant the sign changes. It is rejected here as cleverness bought with a behaviour that the
old module proved over years of production; if the handle's detachment turns out to bother
animators, that is the fix to reach for, and this paragraph is the note saying so.

### 6.5 Ball and toe on the puppet chains

`build_limb_controls` builds three-joint IK and FK chains for `thigh → knee → ankle`. The foot
extends both with `ball` and `toe`:

- **FK side:** an `fk_ball` controller drives the FK ball joint, exactly as the limb's own FK
  controls drive theirs. The FK toe follows its parent and has no control.
- **IK side:** the `ikBall` handle (ankle → ball) and the `ikToe` handle (ball → toe), both
  `ikSCsolver`, constrained to `toe_wiggle`.
- **Blend:** the ball and toe bind joints take `MatrixBlend(fk, ik, switch_plug)` — the same
  switch plug the limb already created, so a single `ikFk` value covers the whole leg.

## 7. The animator interface

Every foot behaviour has **both** a controller and an attribute, and they are the same thing.

### 7.1 Measured

```
addAttr foot -longName heelRoll -proxy heel.rotateX    ->  created
set foot.heelRoll = 37.5                               ->  heel.rotateX == 37.5
set heel.rotateX = -12.25                              ->  foot.heelRoll == -12.25
setKeyframe foot.heelRoll                              ->  curve lands on heelTest_rotateX
```

Run in a live Maya session on 2026-09-12. Three facts matter. Maya will proxy a **single compound
child** (`rotateX`) under a different long name; the proxy is two-way; and **keying the proxy
creates the animation curve on the source**, not on the proxy.

That last one is why this design works at all. An animator in the channel box and an animator
grabbing the controller write to the same curve. There is no additive offset to reconcile, no
double transform, and no possibility of the two interfaces disagreeing — they are one interface
with two front ends.

### 7.2 The six controllers

`heel`, `ball_spin`, `toe`, `ball`, `toe_wiggle`, `bank`, all at `tier="secondary"`, so the rig's
existing `visibilities_ctrl` hides them by default and an animator who wants them turns them on
per module. Uniform coverage was chosen over a smaller set: the rule "every foot behaviour has a
control and an attribute" is worth more than removing two rarely-grabbed handles, because a rule
with two exceptions is a rule nobody can predict.

### 7.3 The nine proxies

On the IK foot control, under a `foot_` separator, in pivot order from the ground up:

```
heelRoll  heelSpin  ballSpin  toeRoll  toeSpin  ballRoll  ballLean  toeWiggle  bank
```

Names are the old module's long names shortened to the house style. They are the names riggers
and animators already have muscle memory for, and there is no reason to spend that goodwill.

## 8. Auto foot roll

New — the old module had nothing like it. One keyable value walks the foot through heel strike,
flat, ball peel and toe-off, which is what a walk or run cycle wants on a single curve.

### 8.1 Two attributes and one field

| name | where | why |
|---|---|---|
| `footRoll` | IK control, keyable | the animator's single roll channel |
| `rollBreak` | IK control, keyable | where the roll hands over from ball to toe |
| `roll_overlap` | module `FloatField`, degrees, default 10.0, min 0.0 | how *softly* it hands over |

The split is deliberate. Animators asked for fewer channels, so the feel of the handover is tuned
once by the rigger and does not appear in the channel box. `rollBreak` stays keyable because
where the foot breaks genuinely changes shot to shot — a tip-toe and a heavy stomp break at
different angles.

`rollBreak` is named for what it is. `footRollStart` was the working name and was withdrawn: at
the break the ball *stops* and the toe *starts*, so a name claiming to be the start of one of
them describes half the event.

### 8.2 The maths

Let `r = footRoll`, `b = rollBreak`, `w = roll_overlap`.

```
h    = clamp((b - r) / (2w) + 0.5, 0, 1)
ball = max( lerp(b, r, h) - w*h*(1 - h), 0 )
heel = min(r, 0)
toe  = r - ball - heel
```

This is a quadratic smooth-minimum. Properties, all checked:

- Outside `[b-w, b+w]` it is **exactly** `min(r, b)`, so the hard behaviour is not approximated
  anywhere it matters.
- At `w = 0` it collapses to the hard break, so `roll_overlap = 0` is a real setting and not a
  division by zero waiting to happen (the implementation short-circuits the network entirely at
  zero rather than dividing).
- At `r = b` the ball sits `0.25w` short of the break and the toe has already taken up that
  `0.25w`. **The overlap is a genuine overlap**, not a rounded corner: the toe begins to move
  before the ball has finished.
- `toe >= 0` everywhere, and C1 at both band edges — both fall out of the same closed form.
  Inside the band, write `x = r - b`. Then:

  ```
  toe = (x + w)^2 / (4w)
  ```

  This is a perfect square over a positive denominator, so `toe >= 0` is immediate — no
  inequality argument needed, unlike the property-list version this replaces. Differentiating,
  `d(toe)/dr = (x + w) / (2w)`, which is `0` at `x = -w` (i.e. `r = b - w`) and `1` at `x = +w`
  (i.e. `r = b + w`) — exactly the slopes `toe` has outside the band (`0` below the break, `1`
  above it, from `toe = max(r - b, 0)`), which **is** the C1 claim, proven rather than asserted.

A naive blend *toward* the break point was tried first and is wrong: it overshoots, and at
`r = 25, b = 30, w = 10` it yields `toe = -0.78`, rolling the toe backwards before the break. The
smooth-min undershoots, which is what turns the artefact into the feature.

Cost: `clamp`, `lerp`, and three multiplies. All exist on `Plug` (`minimum`, `maximum`,
`clamped`, `lerp`). No `Remap` node, nothing new in tik.maya.

### 8.3 Where it connects

`footRoll` drives the **offset groups** of `heel_ctrl`, `ball_ctrl` and `toe_ctrl`, never the
pivots directly. §6.2's sum is what makes that work: the pivot reads `offset + control`, so the
auto roll and the animator's manual value add, and the controller visually rides on top of the
automation instead of drifting away from the foot it drives.

Axis mapping: `heel -> heel_ctrl.offset.rx`, `ball -> ball_ctrl.offset.ry`,
`toe -> toe_ctrl.offset.rx`.

### 8.4 The handover at zero stays hard

The overlap applies to the ball→toe break only. At `footRoll = 0` the heel hands over to the ball
with a corner, and that is intended: the foot is flat at zero, the pivot genuinely changes from
the heel to the ball, and softening it would blend two pivots at foot-plant — which reads as the
foot sliding at exactly the moment it must not. Recorded here so it is not "fixed" later.

## 9. The module

### 9.1 Manifest

```python
inputs  = (Input("root", primary=True, help="Where the hip hangs (pelvis/body)"),)
outputs = ("hip", "upperleg", "lowerleg", "foot", "ball", "toe")
controls = ("thigh", *limb_control_names(labels=LIMB_LABELS), "fk_ball", *FOOT_CONTROLS)
```

`LIMB_LABELS = ("upper", "lower", "foot")`. `upperleg` and `lowerleg` are what a twist module
attaches to, mirroring the arm's `upperarm` / `lowerarm`, so a leg twist needs no new module.

`pivot_controls` covers every control except the IK one (§3.2) and the six foot controls — a
movable pivot on a pivot node is meaningless. `control_shapes` and `control_orients` extend the
limb's helpers with `thigh`, `fk_ball` and the six foot shapes. Per the ground rules, the
manifest must equal what `build()` creates minus tweaks, and
`test_module_ground_rules.py` enforces it.

### 9.2 Fields

Arm parity, plus one:

- `stretch` (True), `squash` (True), `pole_pin` (False)
- **Limb Lock** group: `limb_lock` (True), `lock_from` — `"thigh"` displaces the leg and leaves
  the pelvis alone; `"hip"` carries the hip joint along, the mirror of the arm's
  `shoulder`/`collar` choice
- **Auto Hip** group: `auto_hip` (True), lift angles/degrees, swing angles/degrees,
  interpolation — the arm's auto-collar field set, renamed
- **Foot** group: `roll_overlap` (10.0)

Nothing else. The old module's `Volume_Preserve`, `interpType`, `Pole_Vector` visibility toggle
and mid-lock have no place: volume preservation is the ribbon module's, the pole is always
built, and the mid-lock was a ribbon pin.

### 9.3 Auto hip is `build_reach`

`systems/reach.py` already says so in its own docstring — *"Auto-clavicle is shoulder reach; the
same system serves a hip."* The leg passes its `thigh` control's offset, the `hip` socket, the
`neutral` guide position and the limb's IK tweak, with the prefix `autoHip`.

The old module drove one axis (`rotateZ`) from a blended IK/FK angle. `build_reach` drives two
signed axes from off-plane `atan2`, blends IK against FK the same way, and has no branch cut. The
leg gets the better behaviour for free.

**No cycle:** `build_reach` requires `ik_target` to be upstream of any IK solve it feeds. The
leg's solve is fed by `ankle_driver` at the bottom of the foot stack, and `ik_tweak` is upstream
of that stack, so reading `ik_tweak` is safe — the same relationship the arm has.

### 9.4 Limb lock

Reused unchanged. `lock_from="hip"` targets the hip pass-through group and lets the hip travel;
`lock_from="thigh"` targets the limb group and leaves the hip on the pelvis. Built last, because
it needs the limb's IK tweak, and the lock root still reads the raw socket — which is what keeps
the graph acyclic.

## 10. Testing

### 10.1 The refactor comes first

`test_arm_trigger.py`, `test_limb_system.py` and `test_module_ground_rules.py` must pass
unchanged after the §4 split and before any leg code exists. That ordering is the whole safety
argument for touching a 587-line system the arm depends on.

### 10.2 Two module lists, one of them stale

`test_module_ground_rules.py` currently holds both:

```python
MODULE_TYPES = ("base", "fkchain", "arm")        # drives 10 tests
def _shipped_module_types(): ...                 # drives the rest
```

`control`, `twist` and `ribbon` were added after the tuple was written and are **silently exempt
from those ten ground-rule tests**. Adding `leg` to the tuple would repeat the mistake, so the
tuple is deleted and every test parametrises on `_shipped_module_types()`. Expect the three
exempt modules to fail something when they are first covered; those failures are findings about
the modules, as that file's own docstring says, not tests to relax.

### 10.3 New tests

`tests/integration/trigger/test_foot_system.py`

- the pivot stack nests in the documented order, and `ankle_driver` is what the leg's IK handle
  follows
- each controller's channel reaches its pivot, summed with the offset group
- every one of the nine proxies resolves to its controller's channel, and keying a proxy puts the
  curve on the controller
- `bank` at +45 rotates `bank_out` and leaves `bank_in` at zero, and the reverse at −45
- **both sides roll identically** (§6.3) — the claim this design rests on
- `footRoll` sweep: at `roll_overlap = 0` the ball is exactly `min(r, b)` and the toe exactly
  `max(r - b, 0)`; at `roll_overlap = 10` the toe is non-zero before the break and never negative
  anywhere in a −90…+90 sweep
- negative `footRoll` drives the heel and leaves ball and toe at zero

`tests/integration/trigger/test_leg_trigger.py`, mirroring `test_arm_trigger.py`

- builds standalone and under a `base`
- the bind chain is convention-oriented, **and rolling the `ankle` guide leaves the ball's X axis
  still pointing at the toe** (§5.1 step 4 — the omission this test exists to catch)
- bind pose is exact with every automation full on, the arm's tolerance
- `ikFk` at 0 and 1 puts the ball and toe bind joints where FK and IK respectively say
- auto-hip produces zero rotation at the guide pose

### 10.4 A helper worth extracting

Both new files need "build a left and a right, and compare". Mirroring is the most common source
of limb bugs and every test currently asserts it ad hoc. A shared `build_mirrored_pair()` helper
in `tests/integration/trigger/conftest.py` is in scope for this work.

## 11. Framework readiness

Asked for as a report, and separated from the plan deliberately: only §11.2 is in scope.

### 11.1 Ready, and used as-is

Guide kinds — `REFERENCE` is exactly the heel/tip/bank markers, including the measured
transform-not-joint behaviour that stops them drawing bones. Control tiers and `visibilities_ctrl`
— precisely what "secondary foot controls" needs, already shipped. The manifest declarations and
their `*_for_copy` hooks. Copies. Draw/Sync. The test-rig sandbox. Definable shapes. Pivot
presets. Proxy attributes, measured today.

The systems layer is the real result here: `reach`, `limb_lock` and `twist` are consumed by the
leg with **no changes at all**, and `reach`'s docstring anticipated the hip before the hip
existed. That is the layering working.

### 11.2 Forced by this module — in scope

1. The limb controls/solve split and `driver=` (§4).
2. `derive_size` and `conventional_frames` made public (§3.1).
3. The stale `MODULE_TYPES` tuple (§10.2).
4. The mirrored-pair test helper (§10.4).
5. `rig.controller` conjugated a shape orient for **every** right-side control, ignoring
   `mirror=`. Correct for a behaviour-mirrored control (whose joints carry a 180-degree roll
   about X), wrong for a world-aligned one. The arm never hit it because `limb_control_orients`
   omits every world-aligned role.
6. `systems/limb.py`'s `_build_pole` had a Gram-Schmidt singularity: for any limb whose end guide
   is unrotated and hangs straight down — exactly the leg's default pose with `limb_lock` and
   `auto_hip` on, both defaults — the twist-aware pole frame degenerated and threw the knee a full
   segment off its guide. The arm never hit it because an A-pose arm hangs sideways. Fixed with
   `_safe_twist_axis`, which picks whichever of the target's orthonormal X/Y is less parallel to
   the aim; because they are orthonormal, `min(x_dot, y_dot) <= 1/sqrt(2)` always, so the chosen
   reference is guaranteed at least 45 degrees off the aim for any input. This is shared code the
   arm depends on, and the arm's choice is now pinned by a unit test.
7. `tik.maya`'s `Node` gained a `__contains__` that **raises** `TypeError`. It previously had
   `__getitem__` and no `__iter__`, so `"x" in node` fell back to Python's legacy iteration
   protocol — `node[0]`, `node[1]`, ... — each building a `Plug` from an integer, which
   **segfaults Maya** with an access violation and leaves the process spinning rather than dying.
   Refusing beats implementing: a working `__contains__` would make the broken expression
   silently mean something.

### 11.3 Gaps this surfaces — report only, not in scope

1. **No shared limb-module recipe.** `arm.build()` and `leg.build()` will open with roughly sixty
   near-identical lines: socket, two lock pass-throughs, conventional frames, bind chain, the
   collar/thigh control and its reach. Two is a coincidence; a hindleg makes it three and a
   pattern. Extract it **after** the leg exists and the duplication is real and measured — not as
   part of this work, where it would be a guess about what a third limb needs.
2. **Proxy attributes have no framework affordance.** Two hand-rolled call sites today; the foot
   alone adds nine. A `rig.proxy(control, name, plug)` owning naming, the separator and channel-box
   ordering would pay for itself immediately and would have prevented this spec from having to
   specify proxy ordering by hand in §7.3.
3. **Tiers are author-fixed.** A module author writes `secondary` in code; a rigger who disagrees
   for their show cannot retier from the UI. The leg ships six secondary controls, which is the
   first time that will actually be felt.
4. **The oriented-guide-with-children trap (§5.1) has no framework guard.** It is a convention
   plus a test, and the third module to hit it will hit it cold. A `rig.align_chain(joints,
   oriented={...})` helper that owns the four-step order would close it permanently.
5. **No quadruped consideration.** `systems/foot.py` is deliberately reusable, but its guide roles
   are biped-shaped. A hindleg's extra segment is not designed for here and should not be
   speculatively accommodated.
6. **`tm.listConnections` re-resolves every string result through the node registry even with
   `plugs=True`**, silently dropping the `.attribute` suffix and returning a fresh identity-only
   `Node` each call. Any before/after equality check written through that wrapper can therefore
   never pass, even when nothing changed. Not fixed here: it is shared code used across the whole
   repo, changing its return type mid-plan risks callers this branch never touches, and the leg
   does not need it — the tests that need a real before/after comparison call
   `cmds.listConnections` directly instead. The same unguarded
   `__getitem__`-without-`__iter__` shape §11.2 item 7 fixed on `Node` still exists on `Plug`.

## 12. Out of scope

Ribbons — the leg builds none, and a rigger who wants smooth deformation attaches the existing
`ribbon` and `twist` modules to `upperleg` and `lowerleg`. Volume preservation, the mid-lock
control, `interpType`, the pole-vector visibility attribute, IK/FK matching or snapping tools, and
any animator-facing switch tab for the foot. A `foot` switch tab in the Switches dock is a natural
follow-up and is explicitly deferred.

## 13. Decisions

| # | Decision | Alternative rejected |
|---|---|---|
| 1 | Split `build_ikfk_limb` into controls + solve | A `driver_from` callback — hides a sub-rig in a keyword; re-pointing after the fact — leaves soft-IK and the pole measuring the wrong node, silently |
| 2 | The foot is a system, the leg is a module | Extending `limb.py` with foot knowledge — a limb has no feet |
| 3 | Two parallel hierarchies, channel-connected | Controllers *as* the pivots — puts IK handles in `control_grp` |
| 4 | The foot frame is **behaviour-mirrored** (`Rx(180)`) on the mirrored side, so no sign appears anywhere | A per-axis sign rule -- correct, and what the legacy did, but it desynchronises six handles from their pivots on the right leg (6.2); and a naive mirrored frame, **withdrawn twice, see 6.3** |
| 5 | Every foot channel gets a control **and** a proxy | A smaller control set — a rule with exceptions is unpredictable |
| 6 | Auto-roll drives controller offset groups | Driving pivots directly — the controls would drift off the foot |
| 7 | Quadratic smooth-min for the break | Blend toward the break — overshoots, drives the toe backwards |
| 8 | `roll_overlap` is a rigger field, `rollBreak` an animator attribute | Both keyable — animators asked for fewer channels |
| 9 | Heel→ball handover at zero stays hard | Symmetric softening — blends two pivots at foot-plant |
| 10 | No `pivot_controls` entry for the IK control | Offering both — two pivots on one node that do not compose |
| 11 | `bank` as two clamps | `setDrivenKeyframe` — a build should not author animation curves |
| 12 | `bank_ctrl` is a handle, not a lockstep twin | A sign-switched `rotatePivot` — restores the correspondence, but trades a production-proven structure for cleverness (§6.4) |
