# Dynamic Anim-Space Controls

**Date:** 2026-09-05
**Status:** Approved design, ready for planning
**Amends:** `2026-08-30-dynamic-spaces-and-reach-design.md` — Part 1.3
(`space_controls`) is replaced by the control manifest described here. The rest
of Part 1 (one row per space, `<control>_<label>` ports, `(control, mode)`
grouping, row order as enum order) stands unchanged.
**Builds on:** `2026-08-30-arm-module-and-module-ground-rules-design.md`,
`2026-08-30-trigger-simplification-design.md`

## Purpose

Animation spaces work on the arm and nowhere else. `Module.space_controls` is a
static class tuple of controller roles, so a module whose controllers depend on
its settings cannot name them: `fkchain` builds `fk0..fk{segments-1}` and
`ribbon` builds `mid0..mid{mid_count-1}`, and neither can be written down at
class-definition time. Both therefore declare nothing, the `control` column of
the anim-space table offers an empty combo box, and a rigger who adds a row
cannot choose anything.

`space_controls` is also opt-in and hand-maintained, so the failure is silent
and repeats for every module written from here on. Nothing checks that a
declared role is one the module actually builds, or that a role the module
builds was declared.

This design replaces `space_controls` with a **control manifest** — modules
declare the controllers they build the same way they already declare outputs —
and makes the declaration settings-aware, UI-live, and enforced by a
ground-rules test.

## Scope

In scope: the core declaration, its resolution in the properties table, stale
rows when settings change, updating all five modules, optional start/end
controllers on the ribbon, and the drift test.

Out of scope: the row shape (`control` / `mode` / `label`), the derived port
name, how a `SpaceSwitch` is built, and the graph's space ports. Those work and
this design does not touch them.

---

## Part 1 — The Control Manifest

### 1.1 Declaration

`Module.space_controls` is removed. In its place:

```python
class Module(Schema):
    controls: tuple[str, ...] = ()

    @classmethod
    def control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles this module builds.

        Override when a setting drives them.
        """
        return tuple(cls.controls)
```

This is deliberately the shape of `outputs` / `output_names(settings)`, which
solved the same problem for dynamic outputs. There is one idiom for "a
manifest entry whose set depends on settings", not two, and a module author who
has met `output_names` already knows this one.

The `anim_spaces` table changes only its resolver:

```python
Column("control", "choice", choices_from="control_names")
```

Everything downstream is untouched: a row still derives the optional
`kind="space"` input `<control>_<label>`, the graph still paints it gold, and
`Builder._connect_spaces` still groups rows by `(control, mode)` into one
`tm.SpaceSwitch` in row order.

### 1.2 The manifest is every controller, minus tweaks

`controls` lists **every controller the module builds**, not a curated subset.
Arm's `space_controls` was `("ik", "pole")` while the module builds `collar`,
`ik`, `fk_upper`, `fk_lower`, `fk_hand` and `pole`; after this change all six
are offered. An FK hand in world space is a normal rig, and the rigger — not
the module author — decides which controls deserve a space.

Tweak controllers are the one exclusion, and they are excluded **by
construction rather than by policy**: `rig.tweak_control(main)` creates the role
`<main_role>_tweak` as a child of its main, so it already follows the main by
parenting. A `SpaceSwitch` on a tweak would fight the parent it hangs from. The
rule is therefore mechanical and needs no per-module judgement: a role ending
in `_tweak` is never in the manifest.

### 1.3 Roles owned by a system are named by that system

`build_ikfk_limb` chooses the limb's controller roles through `_role(name, ...)`.
A module that hardcoded `"fk_upper"` in its manifest would drift the moment the
system renamed it. `systems/limb.py` therefore exposes the names it will build:

```python
def limb_control_names(name: str = "", labels: Sequence[str] = ()) -> tuple[str, ...]:
    """The controller roles ``build_ikfk_limb`` creates for these arguments."""
    return (
        _role(name, "ik"),
        *(_role(name, "fk", label) for label in labels),
        _role(name, "pole"),
    )
```

and `Arm.control_names` calls it with the same `labels` its `build()` passes.
The strings exist in one place. A future leg module gets the same guarantee for
free.

---

## Part 2 — Stale Rows

### 2.1 The row survives; the setting does not destroy it

Lowering `segments` from 6 to 3 leaves a row naming `fk5`. Unticking "End
Controller" leaves a row naming `end`. In both cases **the row and its input
port survive, with whatever wire the rigger drew into it**.

This costs nothing to implement, because ports are derived from *rows*, not
from *controls* — `space_inputs(settings)` reads `anim_spaces` and never
consults the manifest. Raising the segment count back, or re-ticking the
checkbox, makes the setup valid again with the wire intact. Auto-pruning the
row would mean a stray click on a spinner silently destroys authored work.

### 2.2 Fatal problems and warnings are different channels

`Builder._build_one` turns *any* `Module.validate()` problem into a
`BuildError`. A stale control must therefore not be a `validate()` problem, or
a spinner click would make the rig unbuildable.

`Module.validate()` keeps the genuinely fatal cases, unchanged from the
2026-08-30 spec:

- a row with an empty `label` (the derived port would be `ik_`);
- two rows deriving the same port name (one connection would be silently lost).

The check `control not in space_controls` moves out of `validate()` into a new
method:

```python
def warnings(self) -> list[str]:
    """Non-fatal problems: things the rigger should see, that still build."""
```

which reports, per stale row:

```
anim space 'fk5_world': control 'fk5' is not built with the current settings
```

`Module.warnings()` returns an empty list on the base class for anything other
than anim spaces, so it is a general seam rather than a spaces-only hook.

### 2.3 Where a warning is seen

Three surfaces, all of which already exist:

1. **`Session.validate()`** — today it validates actions only. It gains a
   module pass: each module instance is rebuilt from its `ModuleInstance`, its
   `validate()` problems are appended as problems, and its `warnings()` are
   appended prefixed `warning:`. The window's *Validate Session* action already
   logs whatever `Session.validate()` returns, so the rigger can catch a broken
   space before pressing Build.
2. **The build log** — `_build_one` logs `module.warnings()` at `warning` level
   before building, and `connect_space` no longer raises `AttachError` when
   `rig.controller_by_role(control)` is `None`. It logs and skips that target,
   which is how an unresolved *source* is already handled a few lines above. A
   space switch is not load-bearing for the bind hierarchy; losing one must not
   cost the rigger the whole rig.
3. **The properties table** — see 3.2. A stale value stays visible in its combo
   box instead of being silently rewritten.

The guide tree's state dot is **not** a surface for this. It carries the
Draw/Sync state vocabulary owned by
`2026-09-05-draw-and-sync-separation-design.md`, and overloading it with a
second meaning would make both unreadable.

---

## Part 3 — The UI

### 3.1 `choices_from` may name a callable

`Column.choices_from` names an attribute on the target object, resolved by
`FormBuilder` as `getattr(self._target, attr, ())`. `control_names` is a
classmethod taking settings, so the resolver is extended:

```python
def _resolve_choices(self, attr):
    found = getattr(self._target, attr, ())
    return tuple(found(self._target.values()) if callable(found) else found)
```

The contract is documented on `Column`: *`choices_from` may name either a
sequence or a callable taking the target's values and returning one.* This is a
generic improvement to `tik.core.fields` / `tik.shared.ui.fields`, not a
trigger-specific hook, and it is what any future settings-driven choice column
will use.

### 3.2 A stale value must not be silently rewritten

`_TableEditor._make_cell` populates a combo box from the resolved choices and
then calls `findText(value)`. When the value is missing, `findText` returns
`-1`, the combo shows index 0, and the next `_emit()` writes that first item
back into the row — which would quietly rewrite `fk5` to `fk0` and defeat
Part 2.1 entirely.

The cell therefore appends any unresolvable value to its own combo as a marked
entry (`fk5 (missing)`) whose data is the original string, and selects it. The
row round-trips unchanged, the rigger can see which control went away, and
picking a real control from the list clears the marker.

### 3.3 The form repaints when the manifest changes

`designer/properties.py::_topology()` snapshots what a settings change might
alter — input names, output names, guide count — and calls `refresh()` when it
moved. It gains `tuple(module_cls.control_names(settings))`.

Dropping `segments` 6 → 3 then repaints the form, so the combo offers `fk0..fk2`
immediately rather than going stale until the panel is reselected. This reuses
the existing "did the topology move?" seam instead of adding a hand-maintained
list of which fields affect controls.

---

## Part 4 — Modules

| Module | `control_names(settings)` |
|---|---|
| `base` | `("root",)` |
| `arm` | `("collar", *limb_control_names(labels=("upper", "lower", "hand")))` |
| `fkchain` | `tuple(f"fk{i}" for i in range(segments))` |
| `twist` | `()` |
| `ribbon` | `("start"?, *(f"mid{i}" for i in range(mid_count)), "end"?)` |

`twist` builds no controllers and declares so explicitly. That is a real
statement, not an omission: the ground-rules test in Part 5 will hold it to it.

`fkchain` builds one controller per joint except the last (`joints[:-1]`), so
the count is `segments`, not `segments + 1`.

### 4.1 Optional start and end controllers on the ribbon

The ribbon pins its ends straight to its sockets, so its only controllers are
the mids. Two new fields:

```python
start_controller = BoolField(False, label="Start Controller")
end_controller = BoolField(False, label="End Controller")
```

Default off, so no existing ribbon changes shape. When on, a controller is
built at that guide, matched to it, `mirror="behaviour"` like the mids, sized
by the existing `controller_size`. The socket drives the controller's **offset
group** — controllers are never parented under a socket, per the ground rules —
and the ribbon pins to the controller's transform instead of the socket:

```python
start_driver = start_socket
if self.start_controller:
    control = rig.controller("start", shape="Circle", size=self.controller_size,
                             match=start_guide, mirror="behaviour")
    tm.MatrixConstraint.create(start_socket, control.offset, maintain_offset=True)
    start_driver = control.transform
ribbon.pin_start(start_driver)
```

**The twist extraction must follow the driver, not the socket.** `twist_plug`
currently reads `start_socket` against the reference and `end_socket` against
`start_socket`. If a controller drives the pin but the twist still reads the
socket, rotating the start controller moves the ribbon end without twisting it
— the ends and the roll would disagree. Both `twist_plug` calls take the
drivers (`start_driver`, `end_driver`), falling back to the sockets when no
controller was requested. The `reference` input and its `start_socket.parent`
fallback are unchanged.

---

## Part 5 — Testing

### 5.1 The drift guard

`tests/integration/trigger/test_module_ground_rules.py` gains the test that
makes this design self-enforcing. For every module in the registry, at a
handful of settings variations, it builds a solo instance, reads the
`tags.ROLE` off every controller in `ctx.controllers`, drops any role ending in
`_tweak`, and asserts the set equals `control_names(settings)` **exactly**.

Variations, chosen so each dynamic axis is exercised at both ends:

| Module | Settings |
|---|---|
| `base`, `twist` | defaults |
| `fkchain` | `segments=1`, `segments=5` |
| `ribbon` | `mid_count=0`, and `mid_count=2` with both controllers ticked |
| `arm` | defaults |

Equality, not subset: a module that builds a controller it did not declare
fails, which is the exact bug `fkchain` and `ribbon` have today.

The test walks the **registry** rather than the file's existing hardcoded
`MODULE_TYPES` tuple, and reads the table above as a `{module_type: [settings,
...]}` mapping that defaults to a single empty-settings run for any type absent
from it. A module registered tomorrow is therefore covered at its defaults the
day it lands, and gains variations only if its author adds a row.

### 5.2 The rest

- `tests/unit/test_core_trigger.py` — `control_names` default and override;
  `warnings()` reports a stale row while `validate()` stays clean; the row and
  its derived port survive a settings change that removes its control; the two
  fatal cases still fail `validate()`.
- `tests/unit/test_fields.py` — `Column.choices_from` naming a callable.
- `tests/ui/test_form_builder.py` — a callable resolver populates the combo; an
  unresolvable value is kept as a marked entry and round-trips unchanged rather
  than collapsing to the first choice.
- `tests/ui/test_guide_designer.py` — changing `segments` repaints the form and
  the control combo offers the new roles.
- `tests/integration/trigger/test_builder_trigger.py` — an fkchain with a space
  on `fk2` builds a real `SpaceSwitch` with the expected enum labels; a space on
  a since-removed `fk5` logs a warning and skips instead of failing the build.
- `tests/unit/test_ribbon_trigger.py` — start/end controllers appear only when
  ticked, the ribbon pins to them rather than to the socket, and the twist
  extraction reads them. (`tests/unit/test_ribbon.py` covers the tik.maya
  construct and is untouched; the construct does not change.)
- `tests/integration/trigger/test_arm_trigger.py`,
  `tests/helpers/toy_modules.py`, `tests/ui/test_pipeline_ui.py` — migrated off
  `space_controls`. The arm assertion becomes the full six-role manifest.

## Migration

`space_controls` has no deprecation shim. It exists in five places in the repo
(one module, four test files), tik.trigger is in development, and a silently
ignored alias would reintroduce exactly the quiet failure this design removes.
Any `.tr` session on disk is unaffected: sessions store `anim_spaces` rows and
input wires, never the manifest.
