# Movable Pivots Without Presets: a tick is what builds a pivot

**Date:** 2026-09-12
**Status:** proposed
**Amends:** `2026-09-11-control-capability-declarations-design.md` — §4's closing rule becomes
"declaring is what makes it available; a **tick** is what builds it, and a preset row implies a
tick", and §4.1's claimed escape hatch is withdrawn as untrue of the code. The seam, its
idempotence guard, and the four declarations all stand.
`2026-09-07-movable-pivots-and-pivot-presets-design.md` — a movable pivot no longer requires a
named preset to exist. The pivot controller, `showPivot`, the preset guides and the switch
compensation are unchanged.

---

## 1. Why

A movable pivot and a set of named pivot positions are two different features that today share
one switch. The rigger who wants the first must buy the second.

`rig.pivot_control` has always known they were separable — "With no rows there is no enum at
all, only a pivot the animator moves by hand" — and the 2026-09-11 pass wrote down where the
bare pivot was supposed to come from:

> A movable-by-hand pivot with no presets is still available — the rigger adds a row and clears
> its label, or simply keeps one preset.

**That is not true of the code, and never was.** `Module._validate_pivots` rejects a blank label,
and the builder treats every validation problem as fatal:

```
>>> module.apply({"pivot_presets": [{"control": "fk0", "label": ""}]})
>>> module.validate()
['pivot preset row 1: label is required']
>>> module.pivot_labels("fk0")
[]
```

Both halves fail independently: the row cannot be saved, and `pivot_labels` filters unlabelled
rows out, so even a row that survived validation would build nothing. The second half of the
sentence — "keeps one preset" — is not an escape hatch at all; it is the thing the rigger was
trying to avoid. It also costs a guide joint and an enum entry the animator did not ask for.

So a control can be offered a movable pivot and have no way to receive one. The gap is
framework-wide: it is not about any module, and no module can work around it, because since
2026-09-11 no module contains pivot code at all.

## 2. Decision

**A rigger-facing tick list decides which offered controls get a pivot; a preset row implies a
tick.**

The Pivots fold grows a second widget above the existing table:

```
Pivots
  Movable Pivots
    [x] ik
    [ ] fk0
    [ ] fk1
  Pivot Presets
    ik  | tip
    ik  | ball
```

Three properties make this the right shape:

**The two widgets describe two features, in dependency order.** "Does this control have a
movable pivot" is answered above "and what named positions does it have", which is the order a
rigger thinks in and the order the build reads them.

**A preset row implies a tick, so nothing migrates.** Every `.tr` in existence, and `arm`'s
three shipped default rows, build exactly what they build today. The implication runs one way
only — a tick does not invent rows — which is what makes the bare pivot reachable.

**Nothing is ticked by default.** A module that offers pivots on fifty FK controls still builds
none until asked, which is the property that let `pivot_controls` become a declaration every
module makes.

### 2.1 What was rejected

**Building a pivot for every declared role, unconditionally.** Uniform, no new field, and it
reads well until you count nodes: `fkchain` declares a pivot for every FK control, so a
50-segment chain builds 50 extra controllers nobody asked for. Worse, it makes `pivot_controls`
an expensive declaration, which pushes a module author to declare fewer — directly against the
ground rule that every control a module builds must be *offered* a pivot.

**A row with a blank label meaning "just the pivot".** Ten lines and no UI work: delete the
`label is required` rule and gate on any row rather than any labelled row. Rejected because the
table stops describing what it holds, two blank rows mean nothing distinct from one, and
`_validate_pivots` loses its only way to catch a genuinely forgotten label. A feature reached by
leaving a field empty is not a feature a rigger finds.

**Letting the module author mark a pivot "always built".** A movable pivot is something an
average animator has an opinion about, which the animator-opinion rule places in `tik.trigger`'s
policy layer and, within that, on the rigger's side of the panel rather than the author's.

**A single module-wide "movable pivots on" switch.** Cheaper than a list and strictly worse: the
rigger who wants a pivot on the hand does not want one on every finger, and the switch gives no
way to say so.

## 3. The field

One addition to `Module`, declared immediately before `pivot_presets`:

```python
movable_pivots = ListField(
    [],
    item_type=str,
    label="Movable Pivots",
    group=PIVOTS,
    last=True,
    choices_from="pivot_control_names",
    help="Controls that get a pivot the animator moves by hand.",
)
```

`last=True` keeps its relative declaration order (`core/fields.py:613`), so it renders above
`pivot_presets` inside the Pivots fold without any ordering machinery.

It is **per copy**, like every field but `copies` itself. The copy form's target is the per-copy
view, so `choices_from="pivot_control_names"` resolves to that copy's bare roles (`ik`) rather
than the module's qualified set (`ik`, `c1_ik`, `c2_ik`) — the same arrangement `pivot_presets`
already relies on, and the same scope leak it already avoids.

No schema bump. A field defaulting to `[]` fills in through `per_copy_defaults` on read, exactly
as `copies` did: a `.tr` written before this exists holds no `movable_pivots` key and gets one.

## 4. The builder seam

The gate, and nothing else (`maya/build.py:759`):

```python
for role in view.pivot_controls_for_copy(view.values()):
    main = ctx.controller_by_role(role)
    if main is None or not view.pivot_wanted(role):
        continue
    if ctx.controller_by_role(f"{role}_pivot") is None:
        ctx.pivot_control(main)
```

with the rule itself on `Module`, beside `pivot_labels`:

```python
def pivot_wanted(self, role: str) -> bool:
    """Whether ``role`` gets a movable pivot: ticked, or carrying presets.

    A preset row implies the tick rather than requiring it -- a row that
    built no pivot would be a row that does nothing, and every session
    written before the tick existed has rows and no ticks.
    """
    return role in (self.movable_pivots or ()) or bool(self.pivot_labels(role))
```

On `Module` rather than in the builder for the reason `pivot_labels` is there: it is a question
about settings, not about a scene, and `core` is where the rows live.

`rig.pivot_control` is unchanged. It already builds `showPivot`, the pivot controller and
`drive_pivot` first and wires presets only `if labels:`, so a ticked control with no rows gets
the pivot and no `pivotPreset` enum — which is precisely the feature.

## 5. Two FormBuilder fixes

Both are generalizations. Neither adds a case for this field.

**A `ListField` picker must resolve its own choices.** `FormBuilder` builds the tick-list editor
only when a `list_choices` callback is injected (`shared/ui/fields.py:748`), and the only place
that injects one is `session_view.py`, the pipeline's action panel. A `TableField` column has
never needed that: `_resolve_choices` reads `choices_from` off the current target and calls it
with the target's values. The `ListField` branch falls back to the same helper when no callback
is supplied, so `choices_from` means one thing on both field kinds and the Designer's module
form gets a real picker instead of the comma-separated `QLineEdit` fallback.

**`_table_is_dead` becomes `_field_is_dead`.** The empty-section rule the 2026-09-11 pass
installed counts widgets: a fold whose every field was skipped hides itself
(`shared/ui/fields.py:640`). A `ListField` nobody can tick — `choices_from` resolving to nothing,
no stored value — has to be skipped for the same reason a table nobody can fill is, or the
Pivots fold returns to `twist`, which builds no controllers at all. The rule is unchanged, only
its domain: *a widget nobody could add to, holding nothing to remove.* A list holding a value
always renders, whatever its options say, for the reason a table holding rows does — a setting
that narrows the candidates must never strand a value where the rigger cannot reach it.

## 6. Validation and warnings

`_validate_pivots` keeps `label is required`. With a tick list there is no reason to overload a
blank row, and the rule is the only thing that catches a label the rigger meant to type.

A tick naming a control the current settings no longer build is a `warnings()` entry, not a
validation problem, and **the tick is kept**. This is the rule `anim_spaces` already follows for
a space row on a removed control, and for the same reason: lowering `segments` from 6 to 2 and
raising it again must restore the setup, not silently discard it. A build must never fail
because a control the rigger is not currently using is named in a list.

## 7. What does not change

A bare pivot places no preset guides. `pivot_guide_roles` derives from rows only, so Draw, Sync,
reconcile, the `.trg` and the guide document are all untouched — a tick adds a controller to the
built rig and nothing to the scene's guides.

`pivot_controls`' anchor is still required of a module author. It is the guide a preset marker
hangs under, so it is simply unused until a row exists; a module offering a pivot with no anchor
would still be a module whose presets could not be placed.

## 8. Tests

| Test | What it pins |
|---|---|
| `tests/integration/trigger/test_pivot_build_trigger.py` | a tick with no rows builds a pivot and **no** `pivotPreset` attr; a row with no tick still builds one; neither builds nothing; a tick and rows together build one pivot with its enum |
| `tests/unit/test_pivot_trigger.py` | `pivot_wanted` for the four combinations; the tick is per copy and qualifies like the rows |
| `tests/ui/test_empty_sections.py` | `twist` still renders no Pivots fold, now with a live field in it |
| `tests/ui/test_pivot_picker.py` (new, beside `test_kinematics_picker.py`) | the module form renders the picker rather than a line edit, and its choices are the copy's bare roles |
| `tests/integration/trigger/test_control_module_trigger.py` | `test_no_preset_rows_means_no_pivot` becomes "no tick and no rows means no pivot"; a ticked control gets one |
