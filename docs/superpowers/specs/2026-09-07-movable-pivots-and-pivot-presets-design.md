# Movable Pivots and Pivot Presets

**Date:** 2026-09-07
**Status:** Approved design, ready for planning
**Builds on:** `2026-09-05-dynamic-anim-space-controls-design.md` (the control
manifest and the `warnings()` seam), `2026-09-05-draw-and-sync-separation-design.md`
(Draw vs Sync, the reconcile states), `2026-08-31-guide-ownership-and-lockstep-design.md`
(the guide document), `2026-08-30-trigger-simplification-design.md` (the `rig`
object and the layering rule)

## Purpose

A rigger cannot move a controller's pivot. Every controller rotates about its
own origin, which is wrong for the cases that matter most: a hand planted on
the ground wants to roll about the fingertips, then the knuckles, then the
wrist; a prop wants to tip about whichever corner is touching the floor.

This design gives a module the ability to declare that a controller has a
**movable pivot**, and to ship **named preset positions** for it that the
rigger places in the viewport as guides and the animator picks from an enum.

Pivot presets are not a foot roll. A leg's ball / ankle / heel / tip are
permanent pivot points that rotate the rig through a chain of groups; they all
exist at once and each has its own channel. A pivot preset moves *one
controller's rotate pivot* and nothing else.

## Scope

In scope: the module declaration and its default rows, the preset guides and
how they draw, sync and reconcile, the tik.maya mechanism, the trigger rig
helper, validation and warnings, the arm module's presets, and the
pose-preserving switch tool.

Out of scope: foot roll and any other permanent-pivot system; mirroring pivot
presets across sides beyond what guide mirroring already does; pivot presets on
tweak controllers.

---

## Part 0 — What the scene proved

Three claims were measured in a live Maya session before this design was
written, because two of them are not obvious.

### 0.1 A live `rotatePivotTranslate` compensation cancels the pivot entirely

The tempting design is to preserve the pose when the pivot moves by driving
`rotatePivotTranslate` from `rp·R - rp`. It does preserve the pose — by
deleting the pivot:

```
p' = (p - rp)·R + rp + rpt         with rpt = rp·R - rp
   = p·R - rp·R + rp + rp·R - rp
   = p·R                           <- rp has vanished
```

Measured: with the compensation network connected, a probe at 90° landed on
`[5.09808, 2.0, -4.36603]` with the pivot at `z=5`, and on exactly the same
point with the pivot at `0`. Maya's own "preserve" pivot edit works because a
*tool* freezes `rotatePivotTranslate` to a value at edit time. The DG cannot
hold it live. **The rig therefore uses a raw pivot**, and pose preservation is
Part 6's tool.

### 0.2 A raw pivot pops, and that is inherent

Moving the pivot on a control already rotated 45° moved the probe from
`[5.9568, 2.0, -3.70711]` to `[3.62717, 2.0, -0.67107]`. Rotating about a
different point *is* a different transform; no network makes it not so. The
workflow is pick-pivot-then-rotate, and Part 6 covers the rest.

### 0.3 The pivot marker parented under the control sits exactly on the pivot

A transform parented under the controller at local position equal to
`rotatePivot` is the rotation's fixed point: measured
`[7.23205, 1.0, 1.33013]` at rest and unchanged through a 90° rotation, and
`[7.1651, 1.0, 0.2141]` unchanged through 60° with a preset plus a manual
offset applied. So the pivot controller can be a plain child of the controller
it drives, follow it around, and still mark the true pivot. No counter-group,
no space maths.

### 0.4 A `choice` node's input type is fixed by its first connection

`setAttr choice.input[0] type="double3"` fails on a fresh node. Connecting a
`double3` plug into `input[0]` first sets the type, after which the node
switches vectors correctly. Part 4 therefore stores each preset as a locked
hidden `double3` attribute on the pivot controller and connects it in — no
extra nodes, and the preset data is readable on the control that uses it.

---

## Part 1 — The Declaration

### 1.1 A module declares which controls have a movable pivot

```python
class Module(Schema):
    #: Controller roles that get a movable pivot, mapped to the guide their
    #: preset guides hang under. Declaring one is what makes it movable.
    pivot_controls: dict[str, str] = {}
```

Declaring the entry is what creates the behaviour, the same way declaring an
input is what creates its socket. The value is the **anchor guide**: the guide
role the control is built at, and the one this control's preset guides are
drawn under. It is the module author's business, never the rigger's, so it is a
class attribute and not a table column.

`Arm` declares:

```python
pivot_controls = {"ik": "hand"}
```

A settings-driven variant follows the established idiom:

```python
@classmethod
def pivot_control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
    """Controller roles with a movable pivot. Override when a setting drives them."""
    return tuple(cls.pivot_controls)
```

This is deliberately the shape of `outputs` / `output_names` and
`controls` / `control_names`. There is one idiom for "a manifest entry whose
set depends on settings", and a module author who has met the other two already
knows this one.

Every role in `pivot_controls` must also be in `control_names(settings)` — a
control that is not built cannot have a pivot. A ground-rules test asserts it
(Part 7).

### 1.2 The rigger owns the preset rows

```python
PIVOTS = FieldGroup("Pivots", collapsed=True)
"""Every module's pivot presets fold away; declared on the base, not per module."""

pivot_presets = TableField(
    [],
    label="Pivot Presets",
    group=PIVOTS,
    help="Each row adds one named pivot position and one guide to place it with.",
    last=True,
    columns=(
        Column("control", "choice", choices_from="pivot_control_names"),
        Column("label", "string"),
    ),
)
```

Presets are not fixed by the module. A module ships sensible defaults and the
rigger adds and removes rows exactly as they do with anim spaces — that is
where a rigger already expects to find this shape of thing, and the properties
table, the `choices_from` resolver and the row editor all exist.

Two derived readers sit beside `space_rows` / `space_inputs`:

```python
@classmethod
def pivot_rows(cls, settings=None) -> list[dict]:
    """The pivot-preset rows from ``settings`` (or the field default)."""

@classmethod
def pivot_guide_roles(cls, settings=None) -> tuple[str, ...]:
    """``pivot_<control>_<label>`` per well-formed row, in row order."""
```

### 1.3 A module's default rows: `Field.with_default`

`Module.fields()` walks the MRO, so a subclass overrides a base field by
redeclaring the name. Restating the whole `TableField` — columns, group, help,
`last` — just to change its default rows would duplicate the declaration in
every module and drift the moment a column changes. `tik.core.fields.Field`
therefore gains:

```python
def with_default(self, default):
    """A copy of this field with a different default.

    For a subclass that keeps a base field's shape and changes only what it
    starts out holding.
    """
```

so a module reads:

```python
class Arm(Module):
    pivot_controls = {"ik": "hand"}
    pivot_presets = Module.pivot_presets.with_default(
        [{"control": "ik", "label": label} for label in ("tip", "ball", "wrist")]
    )
```

`with_default` is a general `Field` method, not a `TableField` one: `anim_spaces`
and any future base-declared field get it for the same reason.

---

## Part 2 — The Preset Guides

### 2.1 One guide per row, keyed by label

Each well-formed row draws one guide, role `pivot_<control>_<label>`, index 0.

The role carries the **label**, never the row index. A guide document stores
poses by `(role, index)`; index-keyed roles would shuffle every preset's
position between presets the moment a rigger reorders or deletes a row. With a
label key, deleting a row orphans exactly one guide and re-adding the row
restores its authored pose from the document.

### 2.2 They stay joints, and look like locators

`guide_nodes`, `scan`, `snapshot` and the guide selection sync all filter
`type="joint"`. Introducing a second node species into the guide layer means
touching every one of them, plus `.trg` exchange and regenerate, and buys
nothing the eye cannot get more cheaply.

A preset guide is therefore a `tm.Joint` created by `create_guide_joint` like
any other, then styled:

- `drawStyle = 2` (None), so the bone is not drawn at all;
- a locator shape parented under the joint, so it reads as a cross-hair marker;
- a distinct colour, so it is never mistaken for a chain guide.

It is a locator to look at and a joint to every line of code.

### 2.3 They hang under the anchor guide

A preset guide is created as a child of `pivot_controls[control]`'s guide, at
that guide's position. Moving the hand guide carries its presets with it; the
rigger then drags each preset to where it belongs. A fresh module therefore
draws with all its presets stacked on the anchor, which is visibly "not placed
yet" and is exactly how an unposed guide already behaves.

### 2.4 The base class draws them

`Module.draw_guides` is the module author's method and must stay so. The draw
path gains one seam on the base class:

```python
def draw_all_guides(self, draft) -> None:
    """Everything a fresh draw creates: the module's guides, then its presets."""
    self.draw_guides(draft)
    self._draw_pivot_guides(draft)
```

`regenerate.py` and `exchange.py` — the only two callers of `draw_guides` —
call `draw_all_guides` instead. Nothing else changes: `draft.created` picks the
preset joints up like any other, so poses, radius, colour, joint orient and
guide attrs all apply to them through the existing loop, and `wire_guides`
still sees the full set.

### 2.5 Everything else falls out

- `expected_guides()` appends the pivot pairs, so **reconcile** reports an
  undrawn preset as `absent` (not drawn, never coloured) and a deleted row's
  leftover guide as an orphan — **reported, never deleted**, per the Draw/Sync
  spec. Re-adding the row picks the pose straight back up.
- **Sync** captures preset positions with every other guide and can never
  create, delete or move one. No new code.
- The **`.trg`** exchange round-trips them as ordinary guides.
- Preset guides are not outputs, are not connectable in the graph, and are not
  counted by `guide_count()` (which governs the multi role only).

`Module.validate` must not hand the pivot pairs to `GuideLayout.validate`,
which rejects roles it does not know:

```python
pairs = self.guide_pairs or self.expected_guides()
pivot_roles = set(self.pivot_guide_roles(self.values()))
problems = list(self.guides.validate([p for p in pairs if p[0] not in pivot_roles]))
```

---

## Part 3 — tik.maya: the Mechanism

`AI/coding_rules.md` is explicit that a tik.maya construct never creates a
controller and never names a user-facing attribute. `showPivot` and
`pivotPreset` are attributes an animator has opinions about, and the pivot
controller is a controller. So tik.maya owns the wiring and nothing else:

```python
# roles/controller.py
def drive_pivot(self, source, *, scale: bool = True) -> None:
    """Drive this controller's rotate (and scale) pivot from a transform or plug.

    Args:
        source: A Transform (its ``translate`` is used) or a double3 plug.
        scale: Also drive ``scalePivot``, so scaling happens about the same
            point (default True).
    """
```

Two connections. It creates no node, names no attribute and encodes no side
convention, so it is mechanism by the letter of the rule. It is **lazy** by
construction — a plain method callable at any time on any controller — which
is what makes the attribute order in Part 4 the module's business rather than
`Controller.create`'s.

---

## Part 4 — tik.trigger: the Policy

`rig.pivot_control` sits beside `rig.tweak_control` in
`tik/trigger/maya/rig.py`, and is the same species of helper: a second
controller hung off a main one, with a bool on the main driving its visibility.

```python
def pivot_control(
    self, main: Controller, *, size: Optional[float] = None, shape: str = "Sphere"
) -> Controller:
    """Give ``main`` a movable pivot, with this module's presets for its role."""
```

`Sphere` is the default shape — a pivot is a point, and a sphere is the one
shape that reads the same from every angle, which is what a marker the animator
orbits around needs.

What it builds, for a main whose role is `ik`:

1. `<name>_ik_pivot_ctrl` with its offset group, parented under `main`,
   `tier=None`. Untiered like a tweak: its visibility is governed by
   `showPivot`, not by the rig's `visibilities_ctrl`.
2. `showPivot` on `main` — bool, `keyable=False`, channel-box visible, driving
   the pivot controller's `visibility`. Exactly `tweakVis`'s shape.
3. The presets, **only when the module has rows for this control**:
   - a locked, hidden `double3` `preset_<label>` per row on the *pivot
     controller*, holding the preset guide's position expressed in `main`'s
     local space at build time;
   - a `choice` node with each of those connected into `input[i]` (the type
     comes from the first connection — Part 0.4);
   - `pivotPreset` on `main` — enum, labels `default` then the row labels in
     order — driving `choice.selector`;
   - the choice output driving the pivot controller's **offset group**.
4. `main.drive_pivot(offset["translate"] + pivot["translate"], scale=True)`.

Index 0 of the enum is `default` at `(0, 0, 0)`: the control's own origin,
the way `world` is always index 0 of a space switch. The preset moves the
offset group and the pivot controller translates on top of it, so a manual
adjustment survives a preset change and the marker always sits on the true
pivot.

**No rows means no `pivotPreset` attribute and no choice node** — just
`showPivot` and a pivot the animator moves by hand. A control with a movable
pivot and no presets carries no dead enum.

A role ending in `_pivot` is never in the control manifest, the same mechanical
rule `_tweak` already gets and for the same reason: a `SpaceSwitch` on a pivot
controller would fight the parent it hangs from.

---

## Part 5 — Validation and Warnings

Fatal, in `Module.validate()` — each would silently lose authored work:

- a row with an empty `label` (the guide role would be `pivot_ik_`);
- two rows deriving the same `pivot_<control>_<label>` role.

Non-fatal, in `Module.warnings()` — the seam the anim-space spec introduced:

```
pivot preset 'ik.tip': control 'ik' has no movable pivot with the current settings
```

A settings change that drops a control from `pivot_control_names` must cost the
rigger a warning, not the rig. The row and its guide survive, as in the
anim-space case, so restoring the setting restores the setup with the preset
poses intact.

At build time, `rig.pivot_control(main)` on a role the module has not declared
in `pivot_controls` raises — that is a module-author error, not a rigger one,
and should fail loudly. A declared preset whose guide is missing from the scene
logs and is skipped: a lost preset must not cost the whole rig.

---

## Part 6 — Switch Pivot (Preserve)

Part 0.2 established that switching a preset on an already-rotated control
moves it, and that no live network can prevent this. What can is a tool that
does what Maya's own pivot edit does: compensate once, at the moment of the
switch.

`Trigger > Switch Pivot (Preserve)`, in the trigger UI layer:

1. read the selected control's world matrix;
2. set `pivotPreset` to the chosen entry;
3. write `translate` so the world matrix is unchanged;
4. key both channels when the control is already animated or autokey is on.

The build path never imports it and the rig does not change shape because it
exists. It is implemented last, after the rig side is built and tested.

---

## Part 7 — Tests

- `tests/unit/test_core_trigger.py` — `pivot_controls`, `pivot_control_names`,
  `pivot_rows`, `pivot_guide_roles`, `Field.with_default`, and the
  validate/warnings split.
- `tests/unit/test_regenerate_trigger.py` / `test_reconcile_trigger.py` —
  preset guides draw under their anchor, an undrawn preset reads `absent`, a
  deleted row's guide is reported as an orphan and never deleted, re-adding the
  row restores its pose.
- `tests/unit/test_guides_trigger.py` — preset guides round-trip through `.trg`.
- New `tests/unit/test_pivot_trigger.py` — `Controller.drive_pivot`, and
  `rig.pivot_control` end to end in Maya: the fixed-point property from Part
  0.3, preset switching, preset plus manual offset summing, and that a control
  with no rows gets no `pivotPreset`.
- `tests/integration/trigger/test_module_ground_rules.py` — `_pivot` roles are
  excluded from the control manifest, and every `pivot_controls` key is in
  `control_names`.
- `tests/integration/trigger/test_arm_trigger.py` — the arm builds its three
  presets and the enum reads `default:tip:ball:wrist`.

---

## Summary of Changes

| File | Change |
|------|--------|
| `tik/core/fields.py` | `Field.with_default` |
| `tik/trigger/core/module.py` | `pivot_controls`, `pivot_presets`, `pivot_control_names`, `pivot_rows`, `pivot_guide_roles`, `draw_all_guides`, `_draw_pivot_guides`, `expected_guides`, `validate`, `warnings` |
| `tik/trigger/guides/nodes.py` | preset-guide styling (`drawStyle`, locator shape, colour) |
| `tik/trigger/guides/regenerate.py`, `guides/exchange.py` | call `draw_all_guides` |
| `tik/maya/roles/controller.py` | `drive_pivot` |
| `tik/trigger/maya/rig.py` | `pivot_control` |
| `tik/trigger/modules/arm/arm.py` | `pivot_controls`, default preset rows, `rig.pivot_control(ik)` |
| `tik/trigger/ui/` | Switch Pivot (Preserve) |
