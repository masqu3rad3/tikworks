# Arm Module Revision: Controls, Spaces and Auto-Collar

**Date:** 2026-08-30
**Status:** Approved design, ready for planning
**Builds on:** `2026-08-30-arm-module-and-module-ground-rules-design.md`

## Purpose

Ten findings from the first test build of the arm connected to a base. Seven
are mechanical corrections; three add structure that every future module will
inherit — module-level animation spaces, offset/tweak controls, and auto-collar.

The ground rules from the previous spec are unchanged and still binding. One new
rule is added (§1.1), prompted by the first finding.

---

## Part 1 — Mechanical Corrections

### 1.1 Stray groups, and a new ground rule

`ChainLengths.create` builds its holder with no parent
(`constructs/chain_lengths.py:71`), so `L_arm_arm_ik_lengths_grp` and
`L_arm_arm_fk_lengths_grp` were left at the world root. It gains a `parent=`
argument; the limb passes `ctx.groups.rig`. This is the only unparented DAG node
the limb creates, which is why exactly two appeared.

The class of bug deserves a rule, so the module ground rules gain a ninth:

> **A module parents everything it creates.** After a build, nothing the module
> made sits at the world root.

Asserted by snapshotting world-level DAG nodes either side of a build. It would
have caught this automatically.

### 1.2 Controller size is derived, not declared

The `controller_size` field is removed from the arm. Size comes from the limb
itself:

```
size = total_limb_length * 0.15
```

with the existing relative scaling kept (pole `0.5 x`, tweak `0.6 x`). `base` and
`fkchain` keep their own `controller_size` fields; changing those is out of scope.

### 1.3 Stretch limit field removed

The `stretch_limit` *field* is removed. The `stretchLimit` *attribute* stays on
the IK control with a 50% default. A generic defaults action will set values like
this later, and that action is out of scope here.

### 1.4 Naming

`build_ikfk_limb` defaults to `name=""`. `ctx.name` already prefixes the instance
name and `naming.format_name` already skips empty tokens
(`core/naming.py:51-52`), so `ctx.name("", "ik", suffix="ctrl")` yields
`L_arm_ik_ctrl` rather than `L_arm_arm_ik_ctrl`. The parameter survives only to
disambiguate a module that builds two limbs.

Controller **role** names must be composed the same way, not with an f-string:
`f"{name}_ik"` would become `"_ik"` when `name` is empty and yield
`L_arm__ik_ctrl`. The limb joins non-empty parts:

```python
def _role(*parts):
    """Join non-empty name parts, so an empty limb name adds no token."""
    return "_".join(part for part in parts if part)

ctx.controller(_role(name, "ik"), ...)   # name="" -> role "ik"
```

The role is what `tags.ROLE` records and what `Space.control` refers to, so with
the default empty name the arm's roles are `ik`, `pole`, `fk_upper`, `fk_lower`,
`fk_hand` and `collar`.

### 1.5 Attribute separators

Locked, channel-box-visible enums via `attribute.add_separator`, on the IK
control:

| Separator | Attributes |
|---|---|
| `ikfk_` | `ikFk` |
| `stretch_` | `stretch`, `squash`, `stretchLimit` |
| `segments_` | `sUpper`, `sLower` |
| `pole_` | `poleFollow`, `polePin` |
| `auto_` | `autoCollar` |
| `display_` | `tweakVis` |

### 1.6 Lock and hide

Anything an animator is not meant to touch is locked and hidden, always.

| Control | Locked + hidden | Keeps |
|---|---|---|
| IK main + tweak | `sx sy sz v` | translate, rotate |
| Collar | `sx sy sz v` | translate, rotate |
| Pole main + tweak | `rx ry rz sx sy sz v` | translate |
| FK root / end | `tx ty tz sx sy sz v` | all rotations |
| FK middle | `tx ty tz sx sy sz v` + the two non-hinge rotations | the hinge axis |

### 1.7 The switch control is removed

`ikFk` moves onto the IK control, with an `attribute.add_proxy` mirror on every
FK control.

**This is what makes hiding the IK controls safe.** At `ikFk = 0` the IK set is
hidden; without the proxies the switch would be unreachable and the animator
stranded in FK. The proxies are load-bearing, not a convenience.

---

## Part 2 — Animation Spaces

### 2.1 Declaration

A new frozen dataclass beside `Input` in `core/manifest.py`:

```python
@dataclass(frozen=True)
class Space:
    name: str             # connection name, unique per module
    control: str          # controller role it drives ("ik", "pole")
    mode: str = "parent"  # parent | point | orient
    default: int = 0      # enum index; 0 is always world
    help: str = ""
```

`Module.spaces: tuple[Space, ...] = ()`. The arm declares:

```python
spaces = (
    Space("ik_hand", control="ik",   mode="parent"),
    Space("pole",    control="pole", mode="point"),
)
```

`Space` is a separate concept rather than a multi-valued `Input` because an
`Input` means "one attach point, one source" — an invariant `_bind_parent_for`
and `_connect_one` both rely on. Overloading it would force a `str | list` union
at every read site and make `primary` interact strangely with multiplicity.

### 2.2 Storage

`ModuleInstance.spaces: dict[str, list[str]]`, sources in the same
`"module.output"` form as inputs so the graph authors both the same way.
Persisted on the guide root as `tags.SPACES = "trg_spaces"`, exactly as
`trg_inputs` already is (`backends/maya/backend.py:22,144,217-222`).

Defaults to `{}`, so existing `.trg` files load unchanged.

### 2.3 Connection is a final pass

Spaces are connected **after every module is built**, not woven into
`order_by_connections`.

Two reasons. A space switch does not affect the bind hierarchy, so nothing needs
it early. And spaces are legitimately mutually referential — an arm in head
space while the head sits in arm space is a normal rig, and feeding that into the
topological sort would raise a false cycle. Inputs keep sole ownership of build
order.

Each space resolves to `SpaceSwitch.create(control, targets, mode=...,
attr_name=f"{name}Space")`. The construct already prepends `world` at index 0 and
already supports all three modes (`constructs/space_switch.py:39-83`), so no new
mechanism is needed — only a way to declare and resolve.

`SpaceSwitch` inserts its own group above the control, giving
`control_grp > <space grp> > offset > main ctrl > tweak ctrl`.

### 2.4 Mirroring

`Guides.mirror` maps space sources across sides with the existing
`_mirror_source` helper (`guides/handler.py:19`), the same way it already maps
inputs. A new `Guides.set_spaces(handle, {name: [sources]})` writes them.

### 2.5 Graph view

Spaces are authorable in the node graph in this pass.

- **`Port` gains `multi: bool`.** Space ports live in `NodeItem.inputs` alongside
  input ports so wire routing needs no special case, but carry `multi=True`.
- **`wire_for_input` becomes `wires_for_input`**, returning a list. A
  single-connection port keeps today's behaviour — clicking picks the wire up and
  unplugs it (`graph_view.py:74-79`). A multi port instead starts a *new* wire on
  click; an existing space wire is removed by selecting the wire itself, not the
  port, since a port with five wires has no single one to pick up.
- **Visual distinction:** space ports draw as diamonds against input circles, in
  a distinct colour, so a glance separates "what drives this module" from "what
  this control can follow".
- **`connect_requested` / `disconnect_requested` carry the port kind**, so
  `connect_input` appends to `handle.spaces[name]` rather than assigning
  `handle.inputs[name]`.
- `NodeItem.relayout` counts space ports in its row total; collapse modes
  (`MODE_CONNECTED`, `MODE_MINIMAL`) treat them like inputs.

---

## Part 3 — Control Rig

### 3.1 Hierarchy

```
L_arm_control_grp
├── L_arm_collar_offset            <- constrained from the socket
│   └── L_arm_collar_auto_grp      <- auto-collar blend (Part 4)
│       └── L_arm_collar_ctrl
├── L_arm_ik_hand_space_grp        <- inserted by SpaceSwitch
│   └── L_arm_ik_offset
│       └── L_arm_ik_ctrl          <- animator's main
│           └── L_arm_ik_tweak_ctrl    <- drives ikHandle + tip rotation
├── L_arm_pole_space_grp
│   └── L_arm_pole_offset
│       └── L_arm_pole_ctrl
│           └── L_arm_pole_tweak_ctrl  <- pole vector target
└── L_arm_fk_upper_offset          <- constrained from the collar ctrl
    └── L_arm_fk_upper_ctrl
        └── L_arm_fk_lower_offset
            └── L_arm_fk_lower_ctrl
                └── L_arm_fk_hand_offset
                    └── L_arm_fk_hand_ctrl
```

### 3.2 Tweak controls

The IK hand and the pole each get one. FK controls and the collar do not: they
are rotation-only and already nest, so a tweak layer adds clutter without buying
anything.

```python
ctx.tweak_control(main, size=None, shape="Circle") -> Controller
```

A separate method rather than a flag on `ctx.controller`, because the caller
needs both objects and returning one that carries the other would mean stuffing
an attribute onto a `tik.maya` role. `size=None` means 60% of the main control's
size, so a tweak reads as secondary without the caller doing arithmetic. It
creates the child, adds a non-keyable
`tweakVis` bool on the main (default off) wired to the tweak's `visibility`,
copies the parent's `trg_mirror` tag, applies the parent's lock/hide set, and
returns the tweak.

**The tweak control is the driver.** Every downstream consumer — the IK handle
constraint, the tip rotation constraint, the pole vector constraint — reads the
tweak, not the main. Because the tweak is a *child* of the main, tweaks ride
along when the animator moves the main control and are never left behind.

### 3.3 Hinge derivation

The middle FK control keeps exactly one rotation axis, derived from the guides
rather than assumed:

```
axis       = end - start
to_mid     = mid - start
projection = start + axis * ((to_mid . axis) / (axis . axis))
bend       = mid - projection
normal     = axis ^ bend                    # bend-plane normal, world space
hinge      = the middle joint's local axis with the largest |dot| with normal
```

For a conventionally placed arm this yields `Y`. A leg, or an elbow a rigger
places unusually, yields whatever its guides actually describe — one rule that
travels.

**Degenerate fallback:** when `|bend| < 1e-4` the chain is straight and has no
bend plane. All three rotations are then left **unlocked**, with a warning.
Locking the wrong two axes is far worse than locking none.

---

## Part 4 — Auto-Collar

```
collar_rest        transform under rig_grp, snapped to the collar joint,
                   constrained from the socket = "no automation"
        |
AimFrame(base = collar_rest, aim_target = ik_tweak_ctrl, up_target = socket)
        |
MatrixBlend(collar_rest, aim_frame, weight = ik_ctrl.autoCollar)
        |
MatrixConstraint -> L_arm_collar_auto_grp
```

`autoCollar` is a 0–1 float on the IK control, default `0`, so a rig is
predictable until the animator opts in — the same reasoning as `stretch`.

**Up comes from the socket, not the hand.** Aiming and rolling from the same
target would make a wrist roll spin the clavicle. Taking the aim from the IK
control and the up vector from the chest keeps the collar following the hand in
every direction while its roll stays stable. Same node count.

The collar's own control sits *below* the automation group, so manual collar
animation layers on top of the automation rather than fighting it.

**Cycle safety.** The IK control's world position depends on its space targets
and on nothing inside this arm; the collar drives the puppet chains, which drive
the bind joints. There is no return path. The existing
`test_module_builds_without_a_cycle` covers it, extended with an
`autoCollar = 1` case.

---

## Part 5 — Testing

### 5.1 New ground-rule test

`test_module_parents_everything_it_creates` — world-level DAG nodes are
identical before and after a build, across `base`, `fkchain` and `arm`.

### 5.2 Behaviour tests that could otherwise pass while wrong

- **Auto-collar off is inert.** With `autoCollar = 0`, moving the IK hand
  anywhere leaves the collar's world matrix unchanged. A failure means the blend
  captured the wrong rest matrix.
- **Wrist roll does not spin the collar.** Roll the IK control about its bone
  axis with `autoCollar = 1`; the collar's orientation must not change. This is
  the property the socket-as-up-target buys.
- **Auto-collar on does move the collar.** The complement of the first test, so
  neither can pass by the network being dead.
- **The hinge is derived.** The arm's elbow keeps `ry` and locks `rx`/`rz`; a
  deliberately straight guide chain leaves all three unlocked.
- **The switch stays reachable.** At `ikFk = 0` the IK controls are hidden;
  setting `ikFk` back to `1` through an FK control's proxy restores them.
- **Tweak controls drive the rig.** Moving only the tweak moves the hand; moving
  the main carries the tweak with it.
- **`.trg` round-trip with spaces** — declared, saved, reloaded, rebuilt, spaces
  still connected with the right modes.
- **Space modes differ observably** — a `point` space moves its control without
  rotating it; a `parent` space does both.

### 5.3 UI tests

`tests/ui` (offscreen, `TIK_TESTS_NO_MAYA=1`): a space port accepts several
wires; clicking a connected space port starts a new wire rather than unplugging
the existing one; a single-connection input port keeps today's unplug behaviour.

---

## Out of Scope

- The generic defaults action referenced in §1.3.
- `controller_size` on `base` and `fkchain`.
- Pose mirroring and the `trg_mirror` consumer.
- Twist and ribbon modules.
