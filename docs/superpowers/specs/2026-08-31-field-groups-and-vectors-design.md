# Field Groups and Vector Fields — Design Spec

Date: 2026-08-31
Status: designed, not implemented.
Builds on `2026-08-28-trigger-rebuild-design.md` (Python fields are the
schema, the UI is generated) and
`2026-08-31-auto-collar-redesign-design.md` (which added the eight
auto-collar fields this spec folds into four).

## 1. The complaint

Module properties are crowded and confusing. The arm declares **sixteen**
fields and renders them as sixteen flat rows, with nothing to say which ones
a rigger touches every day and which ones have good defaults they will never
look at. Eight of those sixteen arrived yesterday with the auto-collar
redesign, and four of them are two `(lower, upper)` pairs that would read
better as one row each.

Two changes:

1. **Collapsible groups**, declared per module or action, with the
   well-defaulted ones collapsed on arrival.
2. **Vector2 / Vector3 fields**, so a pair or a triple occupies one row.

## 2. What already exists

Most of the machinery is here and unused. This spec is mostly about
connecting it.

| Piece | Where | State |
|---|---|---|
| `Field(group="...")` | `core/fields.py:48` | Exists. A run of same-group fields renders under an uppercase caption (`shared/ui/fields.py:307-311`). Flat, never collapsible. **No module or action passes it.** |
| `VectorField(default, size=N)` | `core/fields.py:170` | Exists, with per-component min/max and a `size` in its schema. |
| `_VectorEditor(size)` | `shared/ui/fields.py:15` | Exists. Lays N `QDoubleSpinBox` in a row. |
| `CollapsibleGroup(title, expanded=)` | `shared/ui/collapsible.py:8` | **Exists, themed and tested** (`theme/__init__.py:70-71`, `tests/ui/test_ui_kit.py:53`). A `QToolButton` header over a content area, with `content_layout`, `is_expanded()`, `set_expanded()` and a `toggled` signal. Never used by `FormBuilder`. |

So there is no new widget to write and no new theming. What is missing is
per-group metadata, the vector convenience types, and the wiring.

## 3. `FieldGroup`

New in `tik/core/fields.py` — pure Python, no Qt, no Maya:

```python
@dataclass(frozen=True)
class FieldGroup:
    """A titled, foldable run of fields.

    Declared once at class level and passed to each field's ``group``, so the
    label and the default fold state live in one place and a typo cannot
    silently invent a second group.
    """

    label: str
    collapsed: bool = False
```

`Field.__init__`'s `group` parameter accepts a `FieldGroup`, a plain `str`,
or `None`. A string is wrapped as `FieldGroup(label, collapsed=False)`, so
every existing call site and today's rendering behaviour are unchanged. The
attribute `Field.group` is always a `FieldGroup` or `None` after `__init__`.

**Ordering is declaration order.** Groups appear in the order their first
field is declared, which is the adjacency rule the form already follows. No
`order` argument, no group registry, nothing to keep in sync.

**Non-adjacent fields in the same group are joined, not split.** Today the
caption is emitted whenever `field.group != current_group`, so declaring
`group=A, group=B, group=A` renders the A caption twice. With real groups
that would mean two folds with the same title, so the builder collects
fields by group first and renders each group once, at the position of its
first field.

`to_schema()` keeps `"group"` as the **label string**, so anything reading a
schema today is unaffected, and adds `"group_collapsed": bool`. Both are
`None`/`False` for an ungrouped field.

## 4. `Vector2Field` and `Vector3Field`

Thin subclasses of the existing `VectorField`:

```python
class Vector2Field(VectorField):
    type_name = "vector"

    def __init__(self, default=(0.0, 0.0), **kwargs):
        kwargs.pop("size", None)
        super().__init__(default, size=2, **kwargs)


class Vector3Field(VectorField):
    ...  # size=3, default (0.0, 0.0, 0.0)
```

`VectorField` gains one optional argument, `labels`: a sequence of
per-component captions, or `None` for none. It is presentation metadata and
it goes in `to_schema()` alongside `size`.

Bounds stay **shared across components** — `min`/`max` apply to every
component, as `VectorField.validate` already does. A rule that differs per
component (the auto-collar's "lower must be negative, upper positive")
stays where it already lives, in the owning object's `validate()`; for the
arm that is `ReachAxis.validate`, which enforces exactly this today.

### The arm's eight scalars become four

```python
auto_collar_lift_angles = Vector2Field(
    (-60.0, 75.0), min=-89.0, max=89.0, labels=("Lower", "Upper"),
    label="Lift Angles", group=AUTO_COLLAR,
    help="Arm elevation either side of the neutral guide at full falloff. "
         "Both stay inside +/-89: the driver's angles saturate at 90.",
)
auto_collar_lift_degrees = Vector2Field(
    (-6.0, 15.0), min=-90.0, max=90.0, labels=("Lower", "Upper"),
    label="Lift Degrees", group=AUTO_COLLAR,
    help="Collar rotation at each of those angles.",
)
auto_collar_swing_angles = Vector2Field(
    (-45.0, 60.0), min=-89.0, max=89.0, labels=("Back", "Front"), ...
)
auto_collar_swing_degrees = Vector2Field(
    (-6.0, 10.0), min=-90.0, max=90.0, labels=("Back", "Front"), ...
)
```

The component order is `(min, max)`, which matches `ReachAxis`'s first two
and last two arguments, so the accessors become:

```python
    def _lift_axis(self) -> ReachAxis:
        return ReachAxis(*self.auto_collar_lift_angles, *self.auto_collar_lift_degrees)
```

Arm goes from 16 fields to 12, and the auto-collar block from 9 rows to 5.

### `_VectorEditor` gains bounds and captions

Today it hardcodes `setRange(-1e9, 1e9)` (`shared/ui/fields.py:27`) and
ignores the field's `min`/`max`, so a spinbox will happily offer a value
`validate()` then rejects. It takes `minimum`, `maximum` and `labels`, sets
the spinbox range from them, and puts a small caption above each spinbox
when labels are given. The captions use the existing `FieldCaption` object
name, so they inherit the theme with no new styling.

## 5. `FormBuilder`

`FormBuilder.__init__` currently sets a `QFormLayout` directly on the widget
(`shared/ui/fields.py:267`). It becomes a `QVBoxLayout` holding:

1. one `QFormLayout` for the **ungrouped** fields, first and header-less, so
   a module that declares no groups renders exactly as it does today;
2. one `CollapsibleGroup` per group, in declaration order, each holding a
   `QWidget` with its own `QFormLayout` inside `content_layout`.

`self._widgets` and `self._labels` stay **flat, keyed by field name**, so
`widget(name)`, `mark_overrides()`, `refresh()` and `_on_change()` need no
changes at all. `clear()` walks the group widgets as well as the top form.

### Remembering the fold state

A dict on the builder, `self._collapsed: dict[str, bool]`, keyed
`f"{type(target).__name__}.{group.label}"`. On `set_target`, a group opens
according to that dict if the key is present and `group.collapsed`
otherwise; each `CollapsibleGroup.toggled` writes back into it.

`FormBuilder` is constructed once and re-targeted — `designer/window.py:187`
and `settings_panel.py:50` both build it in their own `__init__` — so
instance state is exactly the requested scope: expanding a group survives
clicking between modules, and everything returns to the declared defaults on
restart. Nothing is written to disk, so there is no preferences schema to
version and no stale entry when a group is renamed.

Keying by class name rather than instance means two arms share fold state,
which is the wanted behaviour: the rigger is tuning *auto-collar*, not
tuning one particular arm.

## 6. The grouping applied

Groups are declared as module-level constants next to the class, so a group
shared between modules can be imported.

| Module / action | Ungrouped (always visible) | Groups |
|---|---|---|
| **arm** | `stretch`, `squash`, `pole_pin` | **Limb Lock** (open): `limb_lock`, `lock_from` · **Auto Collar** (collapsed): `auto_collar`, the four vectors, `auto_collar_interpolation` · **Spaces** (collapsed): `anim_spaces` |
| **ribbon** | `joint_count`, `mid_count`, `twist` | **Deformation** (collapsed): `scaleable`, `preserve_volume`, `degree` · **Guides** (collapsed): `controller_size`, `spacing` |
| **twist** | `count`, `axis` | **Extraction** (collapsed): `twist_source`, `extraction` · **Guides** (collapsed): `spacing` |
| **kinematics** | `guides_file`, `rig_name` | **Build Options** (collapsed): `guide_roots`, `after_build`, `auto_switchers` |
| **reference** | `file`, `version` | **Scope** (collapsed): `include` (`overrides` is already `hidden`) |
| **base**, **fkchain**, **import_asset**, **script** | everything | none — grouping two or three fields is worse than not |

The rule behind the split: a field stays ungrouped if a rigger changes it
while shaping the rig; it goes in a collapsed group if the default is good
and they will only visit it to tune.

**One accepted consequence.** A feature's on/off bool is simply the first
field of its group, with no checkbox in the header and no special case in
the widget. So `auto_collar` sits inside a collapsed **Auto Collar** group,
and whether the feature is on is not visible until the group is expanded.
That trade was made deliberately in favour of having no special cases; if it
grates in use, moving the bool out of the group is a one-line change.

## 7. Migration

None. `Module.__init__` calls `self.apply(settings, strict=False)`
(`trigger/core/module.py:71-72`), so a `.trg` carrying the eight old scalar
keys loads without error and falls back to the new defaults. Those fields
were added on 2026-08-31 and never released, so nothing in the wild carries
tuned values worth preserving. No alias map, no warning change — both were
considered and rejected as machinery that would sit unused.

## 8. Testing

**Unit** (`tests/unit/test_fields.py`, or wherever the field tests live):

- `FieldGroup` is carried through: a field declared with one exposes it as a
  `FieldGroup`; a plain string is wrapped with `collapsed=False`; `None`
  stays `None`.
- `to_schema()` emits `"group"` as the label string and `"group_collapsed"`,
  and an ungrouped field emits `None`/`False`. This is the back-compat test.
- `Vector2Field` and `Vector3Field` coerce, reject the wrong arity, apply
  shared min/max per component, and put `size` and `labels` in the schema.
- A `Vector2Field` round-trips through `values()` and `apply()`.

**UI** (`tests/ui/`, `TIK_TESTS_NO_MAYA=1`, `QT_QPA_PLATFORM=offscreen`):

- Ungrouped fields render before any group, with no header.
- One `CollapsibleGroup` per declared group, in declaration order, titled
  from the label, with `collapsed` honoured on first target.
- Fields declared with the same group but not adjacent land in **one**
  group, not two.
- `widget(name)` and `mark_overrides(names)` reach a field inside a
  collapsed group — the regression test for the flat-dict decision.
- Expanding a group, re-targeting to another module and back leaves it
  expanded; a fresh `FormBuilder` starts from the declared default.
- `_VectorEditor` clamps its spinboxes to the field's `min`/`max` and shows
  a caption per component when `labels` are given.
- A module with no groups renders exactly the rows it did before.

**Integration** (`tests/integration/trigger/`):

- The arm builds with the vector fields, and `_lift_axis()` /
  `_swing_axis()` produce the same `ReachAxis` the scalar fields did — the
  existing auto-collar behaviour tests are the real proof and must keep
  passing untouched.
- A `.trg` round-trip preserves a non-default `Vector2Field` value.

## 9. Out of scope

- Nested groups. One level is enough for the field counts here, and nesting
  invites hiding things two folds deep.
- A checkbox or state indicator in the group header (section 6).
- Persisting fold state to disk across restarts.
- Per-component bounds on a vector field. Shared bounds plus a rule in the
  owner's `validate()` covers the cases here.
- Reordering fields for presentation. Declaration order is the order.
