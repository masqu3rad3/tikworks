# Dynamic Animation Spaces and the Reach System

**Date:** 2026-08-30
**Status:** Approved design, ready for planning
**Supersedes:** Part 2 of `2026-08-30-arm-module-revision-design.md` (fixed `Space` declarations)
**Builds on:** `2026-08-30-arm-module-and-module-ground-rules-design.md`

> **Part 4 (The Reach System) is superseded** by
> `2026-08-31-auto-collar-redesign-design.md`. The mechanism described there
> had two unrelated zeros — the ramp measured from the arm's bind direction
> while the blend aimed the base at the target — so an A-posed collar dipped
> before it lifted, and past the end angle it tracked the target 1:1 without
> bound. The rest of this document still stands.

## Purpose

Two changes from testing the revised arm.

The animation spaces shipped last round are declared in the module manifest, so
a module offers a fixed set and each accepts one connection. Riggers need an
arbitrary number of spaces per controller, added in the properties panel, each
separable as parent, point or orient.

Auto-collar needs remapping — the angle at which it starts and stops taking
effect, an interpolation curve, and independent vertical and horizontal
weighting — and the rigger must be able to opt out of it entirely.

---

## Part 1 — Spaces Become Dynamic Inputs

### 1.1 One row is one space target

A space is defined by a row in a table on the module's properties:

| control | mode | label |
|---|---|---|
| `ik` | `parent` | `chest` |
| `ik` | `parent` | `head` |
| `pole` | `point` | `chest` |

Each row derives one **single-connection input port** named
`<control>_<label>` — `ik_chest`, `ik_head`, `pole_chest`. Rows sharing a
`(control, mode)` pair are grouped at build time into one enum switch, **in row
order**, so the row order is the enum order.

### 1.2 Spaces are inputs, so the parallel storage goes away

Because every space is now an input, space connections live in
`instance.inputs` alongside every other wire. Everything added last round to
carry them separately is removed:

- `Space` from `core/manifest.py`
- `Module.spaces`
- `ModuleInstance.spaces`
- `tags.SPACES` and its read/write in the Maya backend
- `GuideHandle.spaces`, `GuideHandle.set_space`, `Guides.set_spaces`
- `spaces_for()` and the `kind: "space"` tag in `guides/format.py`

Space connections then serialise into `.trg` for free, through the
`connections` list that already carries inputs.

### 1.3 Declaration

```python
class Module(Schema):
    space_controls: tuple[str, ...] = ()   # controller roles that accept spaces
    anim_spaces = TableField([], columns=(
        Column("control", "choice", choices_from="space_controls"),
        Column("mode",    "choice", choices=("parent", "point", "orient")),
        Column("label",   "string"),
    ))


class Arm(Module):
    space_controls = ("ik", "pole")
```

`anim_spaces` lives on the base `Module` so any module can host spaces; the
properties panel hides it when `space_controls` is empty.

**Row validation**, enforced in `Module.validate()` so a bad table is caught
before a build rather than producing a confusing rig:

- `label` must be non-empty — an empty one yields the port name `ik_`.
- `control` must name a role in `space_controls`.
- `(control, label)` must be unique, since it is the derived port name. Two
  rows colliding would silently drop one connection.

A row whose derived input has no connection is skipped at build time, with a
warning. That is normal while a rigger is still wiring, not an error.

### 1.4 `input_names` becomes settings-aware

`output_names(settings)` is already settings-aware — it is how `fkchain`
publishes one output per segment. Inputs follow the same precedent:

```python
@classmethod
def input_names(cls, settings=None) -> list[str]

@classmethod
def space_inputs(cls, settings=None) -> list[Input]
    # one Input(f"{control}_{label}", kind="space") per row
```

`Input.kind` already exists (`transform` | `joint` | `attribute`); `space`
joins it.

### 1.5 Three places must skip space inputs

Each for its own reason, and each is a real defect if missed:

| Site | Why |
|---|---|
| `Builder._connect_one` | A space input has no `ctx.attach()` target, so it would raise "module did not call ctx.attach()". |
| `order_by_connections` | **The one that matters.** Space connections are legitimately mutually referential — an arm in head space while the head sits in arm space is a normal rig. Leaving them in the topological sort resurrects exactly the false-cycle problem the post-build pass exists to avoid. |
| `Builder._bind_parent_for` | Spaces are never primary, so it is already safe; an explicit guard keeps it that way. |

### 1.6 The build pass

The post-build pass stays, and stays post-build for the reason in 1.5. It now
reads space-kind inputs, groups them by `(control, mode)` in row order, and
builds one switch per group:

```
ik.parentSwitch  = chest:head
pole.pointSwitch = chest
```

**`tm.SpaceSwitch` gains `world: bool = True`.** With `world=False` the enum
contains only the defined targets. It currently hard-codes `world` at index 0
(`constructs/space_switch.py:74`, `[WORLD, *spaces]`); trigger passes
`world=False`, because nothing should appear that the rigger did not define.

---

## Part 2 — `TableField`

```python
@dataclass(frozen=True)
class Column:
    name: str
    kind: str = "string"        # "string" | "choice"
    choices: tuple = ()
    choices_from: str = ""      # attribute on the target supplying choices
    label: str = ""


class TableField(Field):
    """A list of records, rendered as a table with add/remove rows."""

    type_name = "table"

    def __init__(self, default=None, *, columns: tuple = (), **kwargs) -> None
```

The value is a list of plain dicts, so it serialises into `.trg` with no
special handling. `coerce` rejects unknown keys and choice values outside their
column's range.

`choices_from` is what lets the `control` column offer `("ik", "pole")` on an
arm and something else on a leg. The field is a class attribute and cannot know
the subclass at definition time, so **the widget resolves choices from the
target object at render time**.

`FormBuilder._make_widget` gains a `kind == "table"` branch rendering a
`QTableWidget` with add and remove buttons.

---

## Part 3 — Graph View

Ports become per-instance: `rebuild` calls `module_cls.input_names(handle.settings)`
rather than the no-argument classmethod, so adding a row in properties makes a
port appear.

Last round's multi-wire behaviour is removed — every space is a
single-connection input again. Two pieces survive on merit:

- **`Port.multi` becomes `Port.space`**, colour only, no behavioural change. A
  space port should still read apart from a structural input at a glance.
- **`wires_for_input` stays plural.** It is strictly more robust than the
  singular form and the callers are already converted.

`connect_requested` and `disconnect_requested` **revert** to `(str, str)` and
`(str)`. `connect_input` routes everything through `guides.connect` again;
there is no second code path left to select.

---

## Part 4 — The Reach System

### 4.1 Named for the behaviour, not the anatomy

Auto-collar moves out of `arm.py` into `trigger/systems/reach.py`. *Reach* is
the rigging term for a base rotating toward an end-effector as it reaches away:
auto-clavicle is shoulder reach, and the same system serves a hip.

The system is generic, so it names no animator-facing attribute itself — it
takes a prefix and the module supplies it. That is the animator-opinion rule:
mechanism is shared, wording is policy.

```python
build_reach(
    ctx, base_group, rest_from, target, control, *,
    prefix="autoReach",
    start_angle=0.0,
    end_angle=90.0,
    interpolation="smooth",
) -> None
```

The arm passes `prefix="autoCollar"`, giving `autoCollar`,
`autoCollarVertical`, `autoCollarHorizontal`. A hip would pass `"autoHip"`.

### 4.2 Network

```
probe        transform under the socket, point-constrained to the target
             -> probe.translate IS the target offset in socket space
scaled       (t.x, t.y * <prefix>Vertical, t.z * <prefix>Horizontal)
aim_point    transform under the socket at `scaled`
angle        AngleBetween(rest direction, scaled)
factor       Remap(angle, start_angle, end_angle, 0..1, interpolation)
             * <prefix>
             |
MatrixBlend(rest, AimFrame(rest -> aim_point, up = socket), weight = factor)
             -> base_group
```

Reading the offset off a transform parented under the socket, rather than
multiplying matrices, avoids `pointMatrixMult` — which is plugin-gated and
absent from a stock Maya. The probe is point-constrained to the IK tweak, which
is upstream of the IK solve, so no cycle.

The multipliers reshape *where it aims* rather than scaling a rotation, so
`0.5` is "half as much vertical influence", not exactly half the angle. That
trade was accepted deliberately: it reuses `AimFrame` and the existing blend
unchanged, and a multiplier of `0` cleanly means "ignore that axis".

The aim frame keeps `twist_axis="X"` so it tracks the socket's Y. **`AimFrame`
fails silently when the up reference is parallel to the aim** — the default
`"Y"` tracks the socket's X, which is the direction the collar aims, leaving
`aimMatrix`'s secondary undefined and the roll drifting.

### 4.3 New `tik.maya` constructs

Both pure mechanism, no controllers, no user-facing names.

```python
Remap.create(input, *, input_min, input_max,
             output_min=0.0, output_max=1.0,
             interpolation="smooth", name=None)   -> .output

AngleBetween.create(first, second, name=None)     -> .angle   # degrees
```

`Remap` wraps `remapValue`, whose ramp interpolation enum is exactly
`none` / `linear` / `smooth` / `spline`. The three options map onto it directly,
with no curve fitting.

### 4.4 Module fields and rig attributes

```python
auto_collar               = BoolField(True,  help="Build the auto-collar network")
auto_collar_start         = FloatField(0.0,  min=0.0, max=180.0, label="Auto Collar Start Angle")
auto_collar_end           = FloatField(90.0, min=0.0, max=180.0, label="Auto Collar End Angle")
auto_collar_interpolation = ChoiceField("smooth", choices=("linear", "smooth", "spline"))
```

`Arm.validate()` rejects `auto_collar_start >= auto_collar_end`: a degenerate
remap range would otherwise build a rig that silently does nothing.

On the IK control, under the `auto_` separator:

| Attribute | Range | Default |
|---|---|---|
| `autoCollar` | 0–1 | **0** |
| `autoCollarVertical` | 0–1 | 0.5 |
| `autoCollarHorizontal` | 0–1 | 0.5 |

---

## Part 5 — Testing

### 5.1 Tests that could pass while being wrong

These are where the effort goes:

- **No automatic world.** The built enum's labels are *exactly* the defined
  rows. A `world` entry sneaking back in at index 0 would still look plausible
  in a viewport.
- **Space inputs do not feed build order.** The mutual-reference case (arm in
  head space, head in arm space) must keep passing now that spaces live in
  `inputs`. If the ordering filter is missed, nothing else catches it.
- **Reach below the start angle is inert.** Move the hand slightly; the collar's
  world matrix must not change at all. Catches an inverted or unclamped remap.
- **`autoCollarVertical = 0` ignores vertical motion** while horizontal still
  works — the per-axis test that proves the multipliers reach the right
  components.
- **The three interpolations differ at the midpoint and agree at both ends.**
  Cheap, and the only thing proving the choice actually reached `remapValue`.
- **Row order is enum order.** Reordering the rows reorders the enum.

### 5.2 Coverage by layer

- **DCC-free unit:** `TableField.coerce` (unknown keys, out-of-range choices),
  `input_names(settings)` deriving ports, `space_inputs` kinds, the builder
  grouping by `(control, mode)`, ordering excluding space inputs.
- **Maya unit:** `SpaceSwitch(world=False)`, `Remap` endpoints and
  interpolation, `AngleBetween`.
- **Maya integration:** the arm with three `ik` rows building one enum;
  `pole` in point mode; reach on/off, angle ramp, per-axis multipliers, no
  cycle; `.trg` round trip carrying both the rows and their connections.
- **UI:** `_TableEditor` add/remove rows and `choices_from` resolution; a space
  port appearing when a row is added; space ports drawn distinctly.

### 5.3 Named risks

1. **`input_names` changing arity ripples** through the graph view, the guide
   designer, validation and the builder. A missed caller fails only when a
   module actually declares spaces, so every call site gets checked explicitly.
2. **`choices_from` resolution** is the genuinely novel part of the field work.
   If the widget cannot reach the target object, the `control` column renders
   empty with no error.

---

## Out of Scope

- Leg or hip modules that would use `build_reach` with a different prefix.
- The generic defaults action.
- Pose mirroring and the `trg_mirror` consumer.
- Twist and ribbon modules.
