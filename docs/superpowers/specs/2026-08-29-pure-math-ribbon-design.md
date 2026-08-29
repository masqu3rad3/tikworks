# Pure-Math Ribbon — Design Spec

Date: 2026-08-29
Status: approved in brainstorming (Arda Kutlu).

## 1. Goal

Replace `tik.maya.constructs.ribbon.Ribbon` (NURBS plane + follicles +
skinCluster) with a geometry-free ribbon built purely from matrix and float
math nodes, following Roman Karoly's "pure-math ribbon rig" breakdown
(https://www.karolyart.com/works/breakdowns/pure-math-ribbon-rig, and its
predecessor https://www.karolyart.com/works/breakdowns/hybrid-matrix-ribbon-rig).

No backward compatibility is required. The only consumer,
`tik.trigger.modules.arm`, will be rewritten separately; this spec only
preserves the parts of the `Ribbon` API that consumer shape relies on.

Non-goals: the arm module rewrite and its integration tests; spine/tail/neck
modules (they will reuse the new lower layer, but are not specified here).

## 2. Findings that drive the design

**The technique (verified from the source pages).** A ribbon's NURBS surface
only ever *interpolated controller transforms*. Doing that interpolation with
math nodes is stateless and parallel-schedulable — no shape node serialises the
evaluation graph. Karoly's profiling: ~500 µs per ribbon vs ~1400 µs classic;
2700 µs vs 6800 µs at 100 ribbons.

The mechanism splits the transform into three independently handled parts:

1. **Position + scale** — weighted linear blend of driver matrices
   (`parentMatrix`/`blendMatrix` + `pickMatrix` to strip rotation). Linear
   blending is exact for translation (affine combination); it is *wrong* for
   rotation (LBS-style shrinkage/flips), which is why rotation never goes
   through this path.
2. **Orientation** — `aimMatrix` per output aiming along the strip.
3. **Twist** — float interpolation of rotation channels, not quaternions:
   slerp takes the shortest path and flips at 180° under partial weights;
   floats twist past 270°+ freely. Twist *derived from a matrix* through stock
   nodes still flips past ±180° — inherent, acknowledged by the author.

**Cross-check.** Matrix splines on the Maya 2020 matrix nodes and the
follicle-free `uvPin` era are established practice; float-channel twist is the
classic ribbon twist trick. Karoly's contribution is the fully geometry-free
formulation and the profiling evidence.

**Repo fit.** `blendMatrix`, `wtAddMatrix`, `multMatrix`/`decomposeMatrix`,
`distanceBetween` and the `Plug` operator algebra are already used in
`tik.maya`. New to the codebase: `aimMatrix`, `pickMatrix`, `parentMatrix`,
and `offsetParentMatrix` (zero hits in `src/python` today). Infrastructure
needs nothing new (`scene.create_node` takes any node type).

**Deviations from the source, on purpose.** Karoly hand-weights neighbours
(1.0 / 0.3 ≈ a flattened cubic basis) and mixes `blendMatrix` cascades with
`parentMatrix`. We compute the exact B-spline basis in Python at build time and
use one simultaneous blend per output — same mechanism, correct maths, fewer
nodes, valid for any joint/controller count.

## 3. Decisions

| Decision | Choice |
|---|---|
| Joint driving | Final deformer/bind joints: decompose to TRS channels (channel-box visible, export-safe). Everything upstream: `offsetParentMatrix` with zeroed TRS. This is a repo-wide policy, not ribbon-specific. |
| Interpolation | Selectable `degree` (simple API knob), default 3 = exact cubic B-spline basis via de Boor. |
| Twist source | Karoly method: controller rotations *are* the twist interface, wired in as floats. Channel-box attrs only as offsets/multipliers layered on top. Mid controllers twist via their own rotation. |
| Pinning | Pins drive translate/scale only by default; orientation is aim + float twist. Per-end `orient=True` mode takes full rotation from the pinned matrix (±180° twist caveat). |
| Layering | Internals free to use raw `cmds`/OpenMaya (idiomatic inside `tik.maya`); public API idiomatic tik.maya (Types/Roles/Constructs, Plug operators, `@undo`). |

## 4. Architecture

Two units in `src/python/tik/maya/constructs/`:

### 4.1 `MatrixSpline` (new, reusable core)

Input: an ordered list of driver transforms D₀…Dₙ, a list of parameters
u₀…uₘ in [0, 1], a `degree`, and a twist float Plug per driver. For each uᵢ it
creates one internal output transform driven by:

- **Position/scale:** one `parentMatrix` whose targets are the drivers' `worldMatrix` with fixed weights
  Nⱼ(uᵢ) — the clamped B-spline basis of the chosen degree, computed by de
  Boor in pure Python at build time. Output passes through `pickMatrix`
  (translate + scale only) into the output transform's `offsetParentMatrix`;
  TRS stays zero.
- **Orientation:** one `aimMatrix` aiming at the next output along the strip
  (the last output aims backward with a negated aim vector). The up input is
  the twist-interpolated up axis derived from the neighbouring drivers, so the
  node stays well conditioned; the degenerate case (aim ∥ up) has the same
  envelope as the old aimConstraints.
- **Twist:** twistᵢ = Σⱼ Nⱼ(uᵢ)·θⱼ as pure float math through the Plug
  operators (a few multiply/add nodes). θⱼ is driver j's twist Plug. Reusing
  the same basis weights makes twist fall off along the strip exactly like
  position, and generalises Karoly's two-end linear lerp to include mid
  controllers. The result is composed as a rotation about the aim axis after
  the aim.

Node budget per output: 1 `parentMatrix` + 1 `pickMatrix` + 1 `aimMatrix` +
~2–3 float math nodes. No shape nodes.

Public surface (indicative): `MatrixSpline.create(drivers, parameters, *,
name, degree=3, twists=None, parent=None)`, `outputs: list[Transform]`,
`basis_weights(u) -> list[float]` (pure Python, also used by tests).

### 4.2 `Ribbon` (rewritten, thin)

Public API kept close to today so consumer shape survives:

```python
Ribbon.create(start, end, *, name, joint_count=5, controller_count=1,
              degree=3, scaleable=True, parent=None) -> Ribbon
ribbon.pin_start(node, maintain_offset=True, orient=False)
ribbon.pin_end(node, maintain_offset=True, orient=False)
ribbon.start_twist / ribbon.end_twist   # unbounded keyable float Plugs
ribbon.deformer_joints, ribbon.controllers, ribbon.scale_switch, ribbon.measure
ribbon.delete()
```

Internals:

- Builds start/end plug transforms and `controller_count` mid controllers
  (`Controller`, circle shape) between them; these are the spline drivers.
- Mid controllers ride the spline: their offset groups are driven via
  `offsetParentMatrix` from a two-driver (start/end) blend so they inherit
  bend/twist and add local translate/scale/rotation on top. Their rotation
  about the ribbon axis is their twist contribution.
- Hands drivers + parameters uᵢ = (i + 0.5) / joint_count (matching the old
  follicle placement) to `MatrixSpline`.
- Creates `joint_count` deformer joints, each driven from its spline output by
  the existing `MatrixConstraint` decompose-to-TRS path.
- Stretch: `Measure` between the plugs; `scaleX` on each deformer joint =
  `(ratio − 1.0) * scale_switch + 1.0` (carried over verbatim). Optional volume
  preservation: `scaleY = scaleZ = ratio ** -0.5`, gated by the same switch.
- Twist inputs: `start_twist`/`end_twist` are float attrs on the plug
  transforms, fed to `MatrixSpline` as the end drivers' twist plugs.
- `pin_start`/`pin_end`: `MatrixConstraint` onto the plug transform, skipping
  rotation by default; `orient=True` drives rotation too (replaces the old
  `orient_start` delete-the-constraint mutation).
- `_place`: group positioned between start/end and aimed with the caller's
  `up_vector` — initial placement only, as today.

Removed: `surface`, `surface_transform`, `follicles`, `skin_cluster`,
`bind_joints`, `start_up`/`end_up` locators, the two aimConstraints, the
non-scale group and its `inheritsTransform` trick.

## 5. Twist wiring contract (consumer side)

Rotating a controller is twisting the ribbon. A consumer wires controller
rotation floats straight into the twist Plugs with the operator idiom; for an
IK/FK arm:

```python
twist = switch * fk_wrist_ctrl["rotateX"] + (1 - switch) * ik_hand_ctrl["rotateX"]
twist >> ribbon.end_twist
```

The blend is float-pure (never passes through a matrix), so twist stays
unbounded end to end. A `twistOffset` attr on a controller is `+` into the same
wire; the ribbon adds no attrs to consumer controllers.

## 6. Error handling

- `create()`: start/end overlapping → `ValueError` (as today); `joint_count`
  ≥ 1; `degree` clamped to `min(degree, driver_count − 1)` — with 0 mid
  controllers the spline is necessarily linear. Documented, not raised.
- Basis weights partition unity by construction (de Boor); `parentMatrix`
  normalisation is a second safety layer.
- Degenerate aim (adjacent outputs coincident) is undefined orientation —
  documented, no runtime guard, same envelope as the old construct.
- Node availability: `aimMatrix`/`pickMatrix`/`blendMatrix` are built in since
  Maya 2020, `parentMatrix` since 2024 — inside the repo's Maya 2024+ floor. No
  fallback path.
- `@undo` on `create`, `pin_*`, `delete`.

## 7. Testing

- **Pure Python (no Maya):** de Boor basis — partition of unity, endpoint
  interpolation, degree 1 vs 3, symmetry.
- **Construct tests under `mayapy`:** scene must match the maths — place
  drivers at known positions and assert each spline output's world position
  equals `basis_weights(u)` applied to those positions in Python (one source of
  truth for graph and reference). Also: twist values at sample parameters,
  twist past ±180° does not flip, stretch ratio and volume preservation,
  pin translate-only default vs `orient=True`, deformer joint count and
  channel-box-visible TRS, `degree` clamping, undo of `create`.
- **Integration:** arm e2e tests in `tests/integration/trigger/` will break and
  are rewritten with `arm.py` in the follow-up task.
- **Live sandboxing:** a running Maya session is reachable through the Maya
  MCP tools; use it during implementation to prototype the node graph and
  verify behaviour (twist past ±180°, aim conditioning, stretch) interactively
  before and alongside the `mayapy` tests.

## 8. Risks

- `aimMatrix` flip at fully straight/collapsed poses (same as old).
- Silhouette drift vs the old 2-influence skin look — accepted (arm rewrite).
- Slight per-output node growth vs a single surface, outweighed at scale by
  parallel evaluation (source profiling).
- Matrix-derived twist (`orient=True` mode) flips past ±180° — inherent to
  stock nodes; documented.
