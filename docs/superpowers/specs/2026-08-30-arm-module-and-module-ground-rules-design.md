# Arm Module Rebuild and Module Ground Rules

**Date:** 2026-08-30
**Status:** Approved design, ready for planning
**Supersedes:** the placeholder `src/python/tik/trigger/modules/arm/arm.py`

## Purpose

Replace the placeholder arm module with a from-scratch design, and settle the
repo-wide conventions it depends on. The conventions bind every module written
after this document, not just the arm.

The legacy arm at `D:\dev\trigger\python\trigger\modules\arm.py` is a reference
for its stretch/squash, soft IK, per-segment scaling and matrix-based wiring. It
is not a template: its chain proliferation, its embedded ribbons and its
mandatory stretch network are the things this design removes.

---

## Part 1 — Ground Rules

These are repo-wide. The governing text lives in `AI/coding_rules.md`; this
section is the rationale.

### 1.1 The animator-opinion rule

If an average animator can understand it and might have an opinion about it, it
belongs to `tik.trigger`, not `tik.maya`.

- `tik.maya` owns **mechanism**: which nodes exist and how they are wired. A
  `blendMatrix` between two matrices. An exponential falloff on a distance.
  Nobody has an opinion about `multMatrix` operand order.
- `tik.trigger` owns **policy**: what the rig *is*. "The wrist control carries
  the `ikFk` attribute." "The pole vector follows the shoulder by default."
  "Stretch is limited to +50%."
- Practical test: could you name the thing in a note to an animator without
  explaining it first? Then it is trigger's.
- Corollary: a `tik.maya` construct never creates a controller, never names a
  user-facing attribute, and never encodes a side convention.

### 1.2 Layer escalation

```
nodes -> types -> roles -> constructs -> systems -> modules
         \____________ tik.maya ______/   \____ tik.trigger ____/
```

A new package `src/python/tik/trigger/systems/` holds policy-bearing sub-rigs
that compose `tik.maya` constructs *and* create controllers. Modules compose
systems.

**Modules never inherit from each other.** Modules are declarative: `guides`,
`inputs`, `outputs` and the `Field`s are class attributes read by the registry
and the UI `FormBuilder`. Subclassing makes a module silently inherit fields it
may not want and makes `output_names()` / `guide_count()` overrides interact.
Shared behaviour goes in `systems/`, not in a base class.

### 1.3 Module group taxonomy

Exactly four children per module, created by the backend, never by the module:

```
<side>_<name>_grp
├── ..._socket_grp    input attach transforms, driven by parent module outputs
├── ..._control_grp   controllers and their offset/space groups — nothing else
├── ..._rig_grp       the puppet: IK/FK chains, handles, math, helpers
└── ..._bind_grp      deform/export joints only — empty when connected
```

`scale_grp`, `nonScale_grp` and `scaleHook_grp` are dropped. Nothing depends on
them: `MatrixSpline` sets its own `inheritsTransform = False`
(`constructs/matrix_spline.py:105-106`) and `Ribbon` parents its group wherever
asked (`constructs/ribbon.py:111-115`).

Visibility bools stay on the module group, renamed to match:
`controlVisibility`, `rigVisibility` (default off), `bindVisibility`.

### 1.4 Two skeletons

| | Puppet (`rig_grp`) | Deform skeleton (`bind_grp`) |
|---|---|---|
| Orientation | mirrored behaviour — reversed aim/up on the right, negative `tx` | engine-neutral — identical orients both sides |
| Negative scale | never needed | never permitted |
| Exported | no | yes |
| Driven by | controls and solvers | the puppet, via `MatrixConstraint` |

The orientation the *solve* wants and the orientation an *export pipeline* wants
are different. Separating the two skeletons lets both be right.

Bind joints must carry **live TRS values** — `translate`, `rotate` and `scale`
channels actually driven, never a transform parked in `offsetParentMatrix`. This
is required for baking and for export to game engines and mocap workflows.
`MatrixConstraint` already satisfies this: it decomposes to the three channels
(`constructs/matrix_constraint.py:117-119`).

`offsetParentMatrix` remains fine for rig helpers inside `rig_grp`, which are
never exported.

Per-engine retargeting (UE5, Unity, mocap skeletons) is explicitly **out of
scope** here and gets its own spec. The deform skeleton this design produces is
engine-neutral and is the input to that later layer.

### 1.5 Single bind hierarchy

Every rig has exactly one deform-joint hierarchy. Each module's bind joints sit
in their correct place within it when the module is connected.

`ctx.bind_parent` resolves the connected input's bind joint **before** `build()`
runs, so bind joints are *created* in their final position and never reparented.
This is not a stylistic preference: `MatrixConstraint` wires a live connection to
`driven.parent.worldInverseMatrix[0]` captured at build time
(`constructs/matrix_constraint.py:105-106`). A joint reparented after being
constrained keeps compensating for its old parent and goes wrong.

Consequence for the builder: `Builder.build()` currently builds every instance
and then runs `_connect_all` (`core/builder.py:67-127`). It becomes a
topologically ordered build-and-connect pass over the input-connection graph,
with cycle detection.

Consequence for outputs: **every module output resolves to a bind joint**, since
that is what `ctx.bind_parent` reads. Today `ctx.output()` accepts whatever node
the module hands it (`backends/maya/context.py:175-178`); the backend now
validates it.

### 1.6 Control mirror metadata

Each controller is tagged `trg_mirror`:

- `behaviour` — FK-like controls (clavicle, fingers, spine) that follow their
  joint, so equal rotation values on both sides give a symmetric pose.
- `world` — IK and world controls (wrist, foot, pole, COG) that are
  world-aligned, so dragging left and right together moves them the same
  direction.

The rig does not read this tag. It exists for a future pose-mirror tool, which
needs the rule per control rather than per side.

---

## Part 2 — `tik.maya` Changes (mechanism only)

### 2.1 Chain count: four sets become three

Retiring `IkFkChain` removes its redundant blend-result chain, because the blend
now lands directly on the deform skeleton that has to exist anyway:

```
ik_*  joints   (rig_grp)   ONE ikRPsolver handle. No second IK chain, ever.
fk_*  joints   (rig_grp)   driven by FK controls
bind  joints   (bind_grp)  <- MatrixBlend(fk[i].worldMatrix, ik[i].worldMatrix,
                              weight = ikFk) constrained per joint
```

The bind joints *are* the blend result.

Two existing mechanisms make the orientation mismatch between puppet and deform
skeleton a non-issue: `MatrixConstraint`'s joint-orient compensation strand
(`matrix_constraint.py:123-143`) and its parent-inverse multiply
(`matrix_constraint.py:105-106`).

### 2.2 New constructs

**`MatrixBlend`** — continuous N-target `blendMatrix` with float weights.

```
MatrixBlend.create(driven, targets, weights=None, *, name=None)
```

`MatrixSwitch` cannot serve this: it is discrete, driven by an integer through
`condition` nodes (`constructs/matrix_switch.py:135-141`), and `SpaceSwitch`
builds on it. The continuous pattern already exists inlined in
`IkFkChain._blend` (`constructs/ikfk_chain.py:105-118`); this extracts it.
Consumers: the IK/FK blend, the pole auto-space, float-weighted space switching.

**`ChainLengths`** — owns the per-segment length drivers of a joint chain.

```
ChainLengths.create(joints, *, side_sign=1, name=None)
    .rest_plugs[i]     live, writable — the per-segment scale hooks
    .total_length      sum plug
    .add_factor(plug)  multiplied into every segment
    .add_override(lengths, weight)   final blend on tx (used by pole pin)

    tx_i = side_sign * rest_i * PRODUCT(factors)
```

Always built, because per-segment scale is always on. Stretch and squash are
merely factors added from outside. An unbuilt factor is `1.0`, so flags do not
interact.

**`SoftIk`** — the exponential approach curve.

```
SoftIk.create(root, goal, chain_length_plug, *, name=None, parent=None)
    .soft_plug     the softness distance (0 = off)
    .gap_plug      the shortfall the stretch network consumes
    .goal_matrix   world matrix plug for the ikHandle
```

Pure-math, following the `matrix_spline.py` precedent (`aimMatrix` for the root
frame, plug arithmetic for the scalar, one `condition`). No locators, no
`aimConstraint`.

Taking `chain_length_plug` from `ChainLengths.total_length` is what preserves the
legacy's best idea: one multiply on `rest_i` rescales that bone through the soft
threshold, the stretch share, the limit and the squash together.

**`AimFrame`** — a frame that aims at one target and takes its up direction from
a live axis of another. Generic; it does not know what a pole vector is.

```
AimFrame.create(base, aim_target, up_target=None, *, aim_axis=(1,0,0),
                up_axis=(0,1,0), twist_axis="Y", parent=None, name=None)
    .matrix     output frame plug
    .transform  optional node carrying the frame in offsetParentMatrix,
                local TRS left free for offsetting along the frame
```

`aimMatrix` with `primaryMode = Aim` and a zero `primaryTargetVector` (so it aims
at the target's position), `secondaryMode = Align` (so the up direction comes
from the up-target's chosen axis), and a `multMatrix` against the parent's
`worldInverseMatrix[0]` when parented.

The `secondaryMode = Align` behaviour is the point: rolling the wrist control
rolls the frame. A rest-captured static offset cannot do this.

### 2.3 The soft-IK curve

With `L` = total rest length, `ds = softIk + 0.001` (the divide-by-zero guard),
`da = L - ds`, and `d` = the root-to-goal distance divided by global scale:

```
f(d) = d                          if d <= da
     = L - ds * e^(-(d-da)/ds)    if d >  da
```

Three properties make this correct rather than merely curved, and they are what
the tests assert:

- **C0 at the seam:** `f(da) = L - ds * e^0 = L - ds = da`.
- **C1 at the seam:** `f'(d>da) = e^(-(d-da)/ds)`, which is `1` at `d = da` —
  the identity branch's slope. No velocity discontinuity, which is the entire
  point of soft IK.
- **Asymptote:** `f(d) -> L` as `d -> inf`, so the chain never fully straightens
  and the elbow never pops.

**Do not attempt a branchless form.** `min(d, L - ds*e^...)` picks the wrong
branch below `da` (at `d=0, ds=1, L=10` the exponential term evaluates to
`-8093`) and `max` picks the wrong branch above. One `condition` node stays.

### 2.4 Stretch and squash as factors

The legacy chains `blendTwoAttr` into `blendColors` because it treats stretch and
squash as two drivers competing for the same `tx`. They are not: they are two
factors on opposite sides of 1.0 that never overlap.

```
gap            = ||end_point - soft_blend_point|| / global_scale
                 (equals stretch * (d - f(d)), so the stretch amount is
                  already folded in by the soft blend — no extra blend node)
stretch_factor = min(1 + gap/L,  1 + limit_pct/100)     >= 1, extending only
squash_factor  = lerp(1.0, min(d/L, 1.0), squash_amount) <= 1, compressing only

tx_i = side_sign * rest_i * stretch_factor * squash_factor
```

Consequences:

- **Stretch off** → the gap/limit branch is never built. **Squash off** → that
  branch is never built. **Both off** → `tx_i = side_sign * rest_i`, and since
  `rest_i` is a live plug, per-segment scale still works with zero stretch
  nodes. This is the "simpler rig" requirement.
- The stretch limit becomes a percentage naturally, because it clamps a *factor*
  rather than adding scene units. The legacy exposed `stretchLimit` with
  `default 100, max 1000` — reading as a percentage — while adding it in scene
  units. That bug cannot be reintroduced here.
- The legacy squash ratio was not divided by global scale
  (`library/tools.py:707`) while the stretch branch was (`:702`), breaking under
  a scaled rig. Both are divided here.

### 2.5 Extensions to existing code

| Change | Why |
|---|---|
| `Joint.duplicate_chain(joints, prefix, parent)` | Replaces `IkFkChain._copy_chain` (`ikfk_chain.py:89-103`), which silently drops `preferredAngle` and `scale`. A zero preferred angle lets an `ikRPsolver` chain solve to a degenerate plane. |
| `Joint.preferred_angle` accessor | Not present in `types/joint.py`. Required by the above. |
| `reverse_aim` / `reverse_up` on `Joint.orient_chain` | `types/joint.py:85-108` always aims `+X` with a fixed world up. Mirrored-behaviour right sides need both. |
| `MatrixConstraint(..., cutoff=)` | Compensates only the immediate parent today (`:105-106`). With controllers mandated under `control_grp` while driving joints under `rig_grp`/`bind_grp`, the driver sits beneath groups that would otherwise double-transform. The legacy needed `source_parent_cutoff` on nearly every controller-to-joint connection for this reason. |
| `Measure.create` accepts matrix `Plug`s | Takes nodes only today (`constructs/measure.py:33-37`); the stretch and pin networks measure between computed positions. |
| `Plug.minimum`, `.maximum`, `.clamped`, `.lerp`, `.gt` | `core/plug.py` offers only `+ - * / ** %`. Without these, `systems/limb.py` must call `create_node("condition")` directly and break the no-raw-cmds rule. |
| Version-guard `**` | `_create_power_node_single` (`core/plug.py:618-642`) creates a `power` node unconditionally while `-` and `/` are guarded by `uses_native_math_nodes` (`core/constants.py:159-212`, native only from 2025). Soft IK depends on `**` for `e^x`. Fall back to `multiplyDivide` op=3, which computes `input1 ^ input2` on every supported Maya. |

Use `math.e` (`2.718281828459045`), not the legacy's truncated `2.71828`.

### 2.6 Deletions

- `src/python/tik/maya/constructs/ikfk_chain.py`
- its exports at `constructs/__init__.py:3,13` and `maya/__init__.py:16,61`
- `tests/unit/test_ikfk_chain.py`

Its only other consumer is the arm module being replaced.

---

## Part 3 — `tik/trigger/systems/limb.py`

```python
build_ikfk_limb(ctx, joints, *, soft_ik=True, stretch=True, squash=True,
                stretch_limit_default=50.0, pole_pin=False)
```

This is where policy lives: it creates controllers, names the animator-facing
attributes, and applies `ctx.side_mult`.

The stretch limit is **not** a separate flag: when `stretch` is on, the clamp is
always built, and `stretch_limit_default` only seeds the attribute's default
percentage.

```
1. duplicate  ->  ik_* and fk_* chains in rig_grp   (Joint.duplicate_chain)

2. ChainLengths on BOTH chains, SHARING rest plugs
       rest_i = initial_i * segmentScale_i          <- always built

3. SoftIk(pole_base, goal_ctrl, ChainLengths.total_length)   <- always, if IK
       .goal_matrix -> MatrixConstraint -> ikHandle
       (pole_base doubles as the soft-IK root: same position as the IK
        chain root, but upstream of the solve — see 3.2)

4. if stretch:  ChainLengths.add_factor(
                    min(1 + gap/L, 1 + limitPct/100))        <- IK chain only
   if squash:   ChainLengths.add_factor(
                    lerp(1.0, min(d/L, 1.0), squashAmount))  <- IK chain only

5. AimFrame(pole_base, soft_goal, hand_ctrl)
       -> MatrixBlend against a rest-captured static matrix,
          weight = poleFollow
       -> pole controller's offset group
       poleVectorConstraint(pole_ctrl, ikHandle)

6. MatrixBlend(fk[i].worldMatrix, ik[i].worldMatrix, weight = ikFk)
       -> MatrixConstraint -> bind joint[i]
```

### 3.1 Shared rest plugs fix a legacy limitation

Per-segment scale worked in IK only in the legacy module, because
`initialDistance` lived on the IK chains (`arm.py:1110-1121`). Here both chains
read the same plugs, so `sUpper`/`sLower` work in FK too. Stretch and squash
factors stay IK-only, matching legacy behaviour.

### 3.2 `pole_base` and cycle safety

The `AimFrame` base **must be upstream of the IK solve**. `ikRPsolver` rotates
the chain's root joint, so feeding `ik_joints[0].worldMatrix` into the frame
creates a cycle — Maya's DG will not notice that only the translation is
actually used.

`pole_base` is therefore a dedicated transform under `rig_grp`,
matrix-constrained to the IK chain's parent with an offset placing it at the
shoulder. The aim target (the soft-IK goal) and the up target (the IK hand
control) are both already upstream.

`SoftIk` takes the same transform as its root, for the same reason and with the
same position. One transform serves both.

This is the single most likely thing to be got wrong and to pass a unit test
anyway. It is verified interactively in a live Maya session before the mayapy
tests are written.

### 3.3 Pole spaces

Step 5 blends the live `AimFrame` against a matrix captured at build time, so
`poleFollow = 0` is a fixed space and `poleFollow = 1` is the twist-aware auto
space. Switching mid-shot pops, as any space switch does. That is the animator's
call and is not hidden.

This replaces the legacy's second IK chain outright. The legacy blended an
`ikSCsolver` chain against an `ikRPsolver` chain through `wtAddMatrix`
(`library/connection.py:362-455`), which is a naive component-wise matrix lerp:
at intermediate weights the basis is non-orthonormal, so the arm visibly shrinks
and shears mid-blend. Blending the pole *target* has no such failure mode.

### 3.4 Attribute policy

| Control | `trg_mirror` | Attributes |
|---|---|---|
| IK hand | `world` | `stretch`, `squash`, `softIk`, `stretchLimit` (%), `sUpper`, `sLower`, `poleFollow`, `polePin` |
| Switch | `world` | `ikFk`, plus proxies of the above |
| FK controls | `behaviour` | none — rotation only |
| Pole | `world` | translate only; rotate and scale locked |

### 3.5 Pole pin

Pin overrides per-segment *lengths* rather than scaling them, so it cannot be a
factor. It uses `ChainLengths.add_override(lengths, weight)` — a final blend on
`tx` — fed with `distance(pole_base, pole)` and `distance(pole, goal)`.
Default off.

---

## Part 4 — The Arm Module

### 4.1 Guides

Four: `collar`, `shoulder`, `elbow`, `hand`.

### 4.2 Deform skeleton

```
collar_jnt          driven by the collar control (FK only, no blend)
  upperarm_jnt      \
    lowerarm_jnt     >  driven by MatrixBlend(fk[i], ik[i], weight = ikFk)
      hand_jnt      /
```

Unconnected, `collar_jnt` sits under `bind_grp`. Connected to a spine's `chest`
output, `ctx.bind_parent` resolves to `chest_jnt` and `collar_jnt` is *created*
there, leaving `bind_grp` empty.

### 4.3 Future twist and ribbon modules need no special support

A twist module attached to the arm's `upperarm` output creates its bind joints
under `upperarm_jnt`, as siblings of `lowerarm_jnt`. That is exactly how engine
twist bones are structured, so the single-hierarchy rule does not fight it and
nothing needs inserting mid-chain. A ribbon segment behaves the same way.

This is why keeping ribbons out of the arm costs nothing later. When the twist
and ribbon modules exist and are proven as attached modules, an optional
inherit-into-the-arm checkbox can be reconsidered as a separate change.

### 4.4 Outputs

`collar`, `upperarm`, `lowerarm`, `hand` — each resolving to a bind joint, per
rule 1.5.

### 4.5 Fields

```python
stretch         = BoolField(True,  help="Build the stretch network")
squash          = BoolField(True,  help="Build the compress-side network")
stretch_limit   = FloatField(50.0, min=0, max=500, label="Stretch Limit %")
pole_pin        = BoolField(False, help="Lock the elbow to the pole control")
controller_size = FloatField(3.0, min=0.01)
```

Deliberately absent:

- **`soft_ik`** — always on. Soft IK is not optional for an IK solution.
- **`segment_scale`** — always on.
- **`ribbon_joints` / `ribbon_controllers`** — no ribbon in the arm.
- **`ik_solver`** — the placeholder offered `ikRPsolver` / `ikSCsolver`
  (`modules/arm/arm.py:36`). Once the pole has a twist-aware auto space, the SC
  solver has nothing left to do. This field disappearing *is* the fix to "too
  many chains."

### 4.6 Controllers

`collar`, `fk_upArm`, `fk_lowArm`, `fk_hand` tagged `behaviour`; `ik_hand`,
`pole`, `switch` tagged `world`. All under `control_grp`; the collar's offset
group hangs off the `root` socket in `socket_grp`.

### 4.7 Inputs

One: `root` (primary) — where the collar hangs, typically a spine's chest.

---

## Part 5 — The FKIK Module

A more granular, pluggable-anywhere sibling of the arm, sharing
`build_ikfk_limb` with no inheritance between the two modules.

Differences from the arm:

- **`soft_ik` is a `BoolField`**, not always-on, so a plain IK chain is
  buildable.
- No collar.
- Variable joint count rather than the arm's fixed shoulder/elbow/hand.

Specified here only to prove the `systems/` boundary carries its weight. It is
built after the arm, under its own plan.

---

## Part 6 — Migration and Testing

### 6.1 Blast radius

The group change touches `RigGroups` (`trigger/core/context.py:13-22`),
`_create_groups` (`trigger/backends/maya/context.py:92-117`) and every existing
module — `modules/base/base.py:31`, `modules/fkchain/fkchain.py:41,45` — plus
`tests/helpers/trigger_fakes.py`. `base` and `fkchain` also move from
`ctx.groups.joints` to `ctx.bind_parent`. Both are small (36 and 64 lines) and
are updated in the same pass, not left broken.

### 6.2 Tests

Per-construct Maya unit tests: `test_soft_ik.py`, `test_chain_lengths.py`,
`test_matrix_blend.py`, `test_aim_frame.py`.

`test_soft_ik.py` asserts the three curve properties of §2.3 numerically, not
just node counts — `f(da) == da`, `f'(da) == 1`, and `f(d) -> L`. Those
properties are what make the solve soft rather than merely curved.

`test_chain_lengths.py` asserts the multiply-by-1 property: with no factors,
`tx_i == side_sign * rest_i`; with stretch alone, never below rest; with squash
alone, never above.

Three ground-rule tests that bind every future module, not only the arm:

1. exactly one bind-hierarchy root per rig;
2. `bind_grp` is empty for any connected module;
3. no controller is parented outside a `control_grp`.

`tests/integration/trigger/test_arm_trigger.py` is rewritten.
`tests/unit/test_ikfk_chain.py` is deleted.

### 6.3 Prototype first

Maya is reachable live in this session. The soft-IK and `AimFrame` graphs are
built and verified interactively before the mayapy tests are written —
particularly the `pole_base` cycle check of §3.2.

### 6.4 Maya version floor

The repo states Maya 2024+; `core/constants.py:205` assumes native math nodes
only from 2025; `**` is unguarded (`core/plug.py:618-642`). Soft IK depends on
`**`.

**Decision:** implement the `multiplyDivide` op=3 fallback behind the
`uses_native_math_nodes` guard. It is correct on every supported version and
costs one node. If 2024 support is later dropped, the fallback can be removed as
a cleanup.

---

## Explicitly Out of Scope

- Ribbon and twist inside the arm. They become separate modules and may later be
  offered as an optional checkbox, after they are proven as attached modules.
- Per-engine retarget skeletons (UE5, Unity, mocap). Own spec.
- The pose-mirror tool that consumes `trg_mirror`. Own spec.
- Volume preservation. The legacy tied it to the ribbon
  (`arm.py:1404-1600`); without a ribbon in the arm there is nothing for it to
  drive. It belongs with the ribbon module.

---

## Related

- `docs/superpowers/specs/2026-08-28-trigger-rebuild-design.md` — module
  contract, fields, constructs. Its group list (`:179`) is superseded by §1.3.
- `docs/superpowers/specs/2026-08-29-pure-math-ribbon-design.md` — the
  pure-math precedent `SoftIk` and `AimFrame` follow.
- `AI/coding_rules.md` — governing text for §1.1, §1.2, §1.3.
