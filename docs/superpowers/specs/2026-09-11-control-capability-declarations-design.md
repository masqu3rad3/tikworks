# Control Capability Declarations: a module says what each section may offer

**Date:** 2026-09-11
**Status:** implemented
**Amended by:** `2026-09-12-movable-pivots-without-presets-design.md` — §4's closing rule
becomes "declaring is what makes it available; a **tick** is what builds it, and a preset row
implies a tick". §4.1's claimed escape hatch ("adds a row and clears its label") is withdrawn:
`_validate_pivots` has always refused a blank label. The seam and its idempotence guard stand.
**Amends:** `2026-09-07-movable-pivots-and-pivot-presets-design.md` — `pivot_controls` becomes a
settings-aware hook whose values address a guide by role *and index*, and the pivot controller
is built by the framework rather than by a call in the module's `build()`. The declaration's
meaning, the preset guides and the switch compensation all stand.
`2026-09-08-definable-control-shapes-design.md` — the Shapes section's candidate set becomes the
keys of `control_shapes` rather than every declared control. The resolution chain, the sparse
override table and the pinned library stand.

---

## 1. Why

Open a `twist` module in the Guide Designer and three folds greet you — **Spaces**, **Pivots**,
**Control Shapes** — and not one of them can be used. `twist` builds no controllers at all
(`controls = ()`; the joints ride an aimed frame), so every table in all three is unfillable.
Open a `base` or an `fkchain` and the Pivots fold is dead for a different reason: `arm` is the
only module in the repo that declares `pivot_controls`.

That is the visible half. The invisible half is why the declarations are the way they are.

**Spaces and Shapes read the wrong set.** The `anim_spaces` table's `control` column and the
`control_shape_overrides` table's `rows_from` both name `control_names` — *every* control the
module builds. Neither is wrong today, because every module that builds a control happens to
want both for all of them, but neither is a statement the module made. A module cannot say
"this control has a shape you may change but no space to switch", because nothing reads such a
statement.

**Pivots cannot be declared by a settings-driven module at all.** `pivot_controls_for_copy`
exists and returns `tuple(cls.pivot_controls)` — the keys, with the anchors dropped on the
floor. Both places that need an anchor read past the hook to the raw class attribute:

```python
anchor_role = self.pivot_controls.get(control)      # core/module.py:677
if role not in self.module.pivot_controls:          # maya/rig.py:544
```

So an `fkchain` whose control set depends on `segments` has no way to express "each `fk{i}`
anchors to `segment{i-1}`" — the hook that would compute it is not consulted, and the anchor is
a bare role string that `draft.made(role)` resolves at index 0 regardless. A pivot on `fk2`
would stack its preset markers on `segment0`.

**Declaring is only half of a pivot.** `arm` declares `pivot_controls = {"ik": "hand"}` *and*
calls `rig.pivot_control(limb.ik_control)` in `build`. The declaration makes the rigger's preset
rows appear and draws the marker guides; the call is what wires them. Miss the call and the
rigger fills in rows that build nothing. Every module that wanted pivots would repeat that
pairing by hand.

## 2. Decision

**A module names the candidate set for each section, and the framework does the rest.**

Four attributes, each answering exactly one question, each with a `*_for_copy` hook for the
settings-driven case — the same idiom `outputs_for_copy` established:

| Attribute | Question | Default on `Module` |
|---|---|---|
| `controls` | What controllers do I build? | `()` |
| `space_controls` | Which of them may host an anim space? | **all of `controls`** |
| `pivot_controls` | Which get a movable pivot, anchored where? | `{}` |
| `control_shapes` | Which have a definable shape, defaulting to what? | `{}` |

`space_controls` is the one whose default is "all", and the asymmetry is the point: hosting a
space is something any controller *can* do, so a module narrows rather than opts in. A pivot and
a shape are things a module chooses to offer.

`control_shapes` picks up a second job. **Its keys are the Shapes section's candidate set.** A
control with a declared default shape is shape-editable; one without is not offered. There is no
`shape_controls` list, because it would duplicate `controls` line for line in every module and
then drift from it — the exact maintenance burden this document exists to remove.

### 2.1 Why that second job is safe

The obvious objection is that a module author who adds a control and forgets its shape default
silently loses that control's override row. That failure is already impossible:
`test_every_declared_control_has_a_resolvable_default_shape` asserts that every declared control
has a default the pinned library can resolve, for every module and every settings variation. A
forgotten default is a CI failure today and stays one.

So for a well-formed module the shape candidate set *equals* its control set, and this change
narrows nothing in practice. That is the point rather than a weakness: the module now says so
rather than the table assuming it, and a module with no controls — `twist` — yields an empty set
from the same rule that gives `arm` six, instead of from a special case.

§5's test guards the reverse direction: every key must name a control the module actually builds.

## 3. The pivot anchor becomes addressable

`pivot_controls` values become a guide *reference* rather than a role:

```python
pivot_controls = {"ik": "hand"}                 # role, index 0
pivot_controls = {"fk2": ("segment", 1)}        # role and index
```

A bare string means index 0, so every existing declaration reads unchanged.

`pivot_controls_for_copy` returns the **whole dict**, computed from settings:

```python
@classmethod
def pivot_controls_for_copy(cls, settings=None) -> dict[str, object]:
    """Controller roles of one copy with a movable pivot, mapped to their anchor."""
    return dict(cls.pivot_controls)
```

`pivot_control_names` is unchanged — iterating a dict yields its keys, which is what it already
does.

Both readers stop reaching past the hook. `Module._draw_pivot_guides` resolves the anchor
through `pivot_controls_for_copy(self.values())` and unpacks `(role, index)` before calling
`draft.made(role, index)`; `rig.pivot_control`'s membership check goes through the same hook.
That single change is what makes a settings-driven module able to declare a pivot at all.

## 4. The framework builds the pivot

`rig.controllers` and `rig.controller_by_role` already exist. Directly after `view.build(ctx)` in
the per-copy loop (`maya/build.py:744`), for every declared role that has preset rows:

```python
for role in view.pivot_controls_for_copy(view.values()):
    main = ctx.controller_by_role(role)
    if main is None or not view.pivot_labels(role):
        continue
    if ctx.controller_by_role(f"{role}_pivot") is None:
        ctx.pivot_control(main)
```

**The seam is idempotent, and has to be.** Every module called `rig.pivot_control` itself before
this existed, and a studio module outside this repo may still. Without the guard it gets a second
pivot, which fails outright when `showPivot` is created twice on the same control. Skipping a role
that already has one means the old style keeps working and the new style is simply less code.

**Declaring is what makes it available; a preset row is what builds it.** That is the sentence
the ground rules already use for sockets — "a socket per declared input is created for you;
declaring the input is what makes it" — and a pivot now reads the same way. No module contains
pivot code; `arm` **loses** its `rig.pivot_control(limb.ik_control)` line.

`pivot_labels(role)` moves from `ModuleRig._pivot_labels` to `Module`, since the builder needs it
and `core` is where the rows live. `ModuleRig._pivot_labels` delegates.

### 4.1 What this changes for an existing arm

An `arm` today gets its hand pivot unconditionally. Under this rule an arm whose rigger deleted
every preset row loses it. `arm` ships three default rows (`tip`, `ball`, `wrist`), so a fresh
arm is byte-identical; a deliberately emptied one now means "no pivot", which is the reading that
makes the rule uniform. A movable-by-hand pivot with no presets is still available — the rigger
adds a row and clears its label, or simply keeps one preset.

## 5. Validation, in two layers

**Test-time**, in `tests/integration/trigger/test_module_ground_rules.py`, for every registered
module across a spread of settings: every name in `space_controls`, `pivot_controls` and
`control_shapes` must be a control that module actually builds, and every pivot anchor must name
a guide role the module's layout declares. A typo fails CI rather than a rigger's build.

**Runtime** — and here the obvious design is wrong, so it is worth writing down why.

The tempting move is to filter `Module.space_rows()`: it feeds both `space_inputs()` (the ports)
and the builder's space loop, so dropping an ineligible row there would stop it growing a phantom
port *and* stop it building, in one place. **That filter must not exist.** The port is what
carries the wire. A rigger who lowers `segments` from 6 to 2 and raises it again has to get the
setup back intact, and the connection is keyed by port name — remove the port and the wire is
gone for good. The existing guarantee is pinned by
`test_a_stale_control_keeps_its_row_and_its_port`: *"ports come from rows, not from controls, so
the wire survives."*

A stale row is already safe at both ends without any filter:

- `warnings()` tells the rigger, which is §5's advisory layer below.
- The builder skips it: `connect_space` returns falsy when no controller carries the role, and
  `maya/build.py:592` logs *"no controller with role 'X'; its space was skipped"*.

So `space_rows` stays deliberately unfiltered, and its docstring says so. `rig.pivot_control`
already raises `GuideError` on an undeclared role, so pivots need nothing new beyond routing that
check through the hook.

**The advisory layer already exists** and needs only to read the right sets. `Module.warnings()`
reports a stale row in all three tables, and two of its three checks are written against
`control_names`:

```python
known = type(self).control_names(self.values())   # -> space_control_names for anim_spaces
                                                  # -> shape_control_names for shape overrides
```

Its pivot check already reads `pivot_control_names`, which is correct. These are the warnings a
rigger sees in the panel; §5's `space_rows` filter is the separate, silent guarantee that a stale
row cannot grow a port or build a space.

## 6. The UI: a table nobody can fill renders nothing

Generic, in `tik/shared/ui/fields.py`, stated as a property of the *table* rather than of
Trigger:

```python
def _table_is_dead(self, name, field) -> bool:
    """A table nobody could add a row to, that holds no rows to remove."""
    if getattr(self._target, name, None):
        return False                       # has rows -- show them
    source = getattr(field, "rows_from", "")
    if source and not self._resolve_choices(source):
        return True
    return any(
        column.choices_from and not self._resolve_choices(column.choices_from)
        for column in getattr(field, "columns", ())
    )
```

`set_target` skips such a field entirely — no widget, no label — and a pass over the folds closes
any group left with nothing in it.

**`set_visible_fields` has to agree, and did not.** It decided a fold's visibility from every
*declared* field rather than the ones that got a widget, so it put back every fold `set_target` had
just closed. The designer calls it after every `set_target` — that is what splits the MODULE and
COPY halves — so in the running app the empty folds came back every time, which is exactly what was
reported. Both now count only fields present in `self._widgets`.

The test is **per column**, not per table: a column whose options are fixed and empty is what
makes a row unfillable. `anim_spaces` has a static `mode` column beside its `control` column, and
only the latter can empty out.

The `or bool(current rows)` clause is the stale-row escape. A rigger who adds a mid controller to
a ribbon, gives it an anim space, then sets Mid Controllers back to 0 still sees the Spaces fold
holding that one row, and can delete it. Put the mid back and nothing was lost either way.

Re-rendering is covered by extending `_topology` in `ui/designer/properties.py` with
`space_control_names` and `shape_control_names`, so changing a setting that empties or refills a
candidate set rebuilds the panel.

## 7. What each module declares

Spaces and shapes need no module changes at all: every module's existing declarations already say
the right thing, and the dead folds were never a declaration problem. Reading them against §2:

| Module | Spaces | Shapes | `pivot_controls` |
|---|---|---|---|
| `base` | `root` | `root` | `{"root": "root"}` |
| `fkchain` | per segment | per segment | computed: `fk0 → ("root", 0)`, `fk{i} → ("segment", i-1)` |
| `ribbon` | as configured | as configured | computed: `start → "start"`, `mid{i} → "start"`, `end → "end"` |
| `arm` | all six | all six | `collar → "collar"`, `fk_upper → "shoulder"`, `fk_lower → "elbow"`, `fk_hand → "hand"`, `ik → "hand"`, `pole → "elbow"` |
| `twist` | — hidden | — hidden | `{}` — it builds no controls |

`fkchain` and `ribbon` get a `pivot_controls_for_copy` override, the same shape as their existing
`control_shape_defaults_for_copy`.

`arm`'s anchors come from a new `limb_pivot_controls` in `systems/limb.py` — the third mirror of
`limb_control_names`, for the reason the other two exist: a module that hardcoded the roles this
system chose would drift the moment one was renamed. The *guide* roles are passed in, because the
limb system never names a guide; `arm` holds them in a `LIMB_GUIDES` constant beside `LIMB_LABELS`.

Two controls have no guide of their own. The `arm`'s pole is placed at a computed rest position
and the `ribbon`'s mids are computed along the surface, so they anchor to `elbow` and `start`
respectively. Their presets stack there unplaced until the rigger drags them where they belong,
which is already how an unplaced preset behaves — "an unplaced preset should look unplaced".

A new ground rule, `test_every_control_is_offered_a_movable_pivot`, holds the table above true for
every module and settings variation. Offering costs nothing — §4 builds nothing until a preset row
exists — so a control left out of `pivot_controls` is an oversight rather than a decision.

### 7.1 When it is a decision: `pivot_exempt_for_copy`

The rule as first written assumed a missing pivot is *always* an oversight. It is not. A ribbon's
**mid** controls ride the ribbon surface rather than sitting on a guide of their own, and a pivot
moved away from one does not rotate about where the animator put it — so offering the preset would
be offering something that does not work.

`pivot_exempt_for_copy` is how a module says it meant it: the ground rule reads
`controls - movable - exempt`, and separately refuses a control that is both offered and exempt.
That keeps the rule's whole value — an oversight still fails CI — while turning a silent omission
into a decision on the record, next to the declaration, with the reason in its docstring. `ribbon`
is the only module that declares one.

After this, `twist` renders none of the three folds, `ribbon` at zero controllers renders none,
and every other module renders all three.

## 8. Testing

- `tests/unit/test_core_trigger.py` — `space_control_names` defaults to all and narrows when
  declared; `shape_control_names` comes from `control_shapes` keys; `space_rows` drops an
  ineligible row and warns, so `space_inputs` grows no phantom port.
- `tests/unit/test_module_copies_trigger.py` — both new name sets repeat across copies and
  qualify (`c1_ik`); `pivot_controls_for_copy` returns a dict whose keys qualify the same way.
- `tests/unit/test_pivot_trigger.py` — a tuple anchor resolves to the right multi-guide index;
  an `fkchain` with presets on `fk2` draws its markers on `segment1`, not `segment0`.
- `tests/integration/trigger/test_module_ground_rules.py` — §5's subset and anchor assertions,
  over every registered module.
- `tests/integration/trigger/test_pivot_build_trigger.py` (new) — the post-build hook builds a
  pivot exactly where preset rows exist and nowhere else; `arm` builds the same hand pivot it does
  today with its explicit line removed.
- `tests/ui/test_empty_sections.py` (new) — `twist` renders none of the three folds; `ribbon` at
  zero controllers renders none; a `ribbon` holding a stale space row keeps its Spaces fold;
  `arm` renders all three.

## 9. Out of scope

Nothing about how a space, a pivot or a shape *works* changes. The modes, the ports, the preset
guides, the switch compensation, the resolution chain, the pinned library and the sparse override
table are all untouched. This document is about which controls each section offers and what a
module has to write to say so.

## 10. Two defects the first pass left behind

Recorded here because both were reported against this work and both were one root cause each.

**The folds came back.** §6 skips a dead table in `set_target`, and a pass over the folds closes any
group left with nothing in it. But `set_visible_fields` — which the designer calls after *every*
`set_target`, to split the MODULE and COPY halves — decided a fold's visibility from every
*declared* field rather than the ones that got a widget. So it put back every fold `set_target` had
just closed, and in the running app the three empty folds were still there. Both passes now count
only fields present in `self._widgets`.

**A phantom port on the graph.** Adding an anim space drew a dead input plug in the node's top-left
corner. `input_names` already carries every anim-space port, so a node that *also* walked
`spec.spaces` built a second `Port` for each and overwrote the dict entry; the first stayed a child
item nothing indexed, and since `relayout` walks `inputs` it was never positioned or hidden.
`spaces` now marks a port rather than adding one.

Its root cause reached two more places, because `Module.space_inputs` answers for *one copy* and
returns bare names while every caller matched them against qualified keys:

- `maya/build.py` let a later copy's space connection reach the topological sort, so two multi-copy
  modules in each other's space failed the build outright with a spurious
  `ValueError: Cyclic module connection`.
- `core/build_scope.py` registered such a connection as structural, so rebuilding a producer tore
  down and rebuilt a consumer that only borrowed a space from it — the thing that module's own
  docstring exists to prevent.

`Module.space_input_names` qualifies per copy, and all three read it.
