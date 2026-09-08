# Definable Control Shapes

**Date:** 2026-09-08
**Status:** Approved design, ready for planning
**Builds on:** `2026-08-30-trigger-simplification-design.md` (the `rig` object
and the layering rule), `2026-09-05-dynamic-anim-space-controls-design.md` (the
control manifest: `controls` / `control_names`),
`2026-09-07-movable-pivots-and-pivot-presets-design.md` (the `pivot_controls`
declaration and the `pivot_presets` table, whose idiom this follows),
`2026-09-06-settings-and-preferences-design.md` (the guarantee that a user
preference can never change a rig)

## Purpose

Every controller a tik.trigger module builds has a shape chosen in code and
frozen there. `arm.py` says `shape="CurvedCircle"`; `systems/limb.py` says
`shape="Cube"` for the IK control and `shape="Circle"` for each FK control. A
rigger who wants a different silhouette has no way to ask for one.

Controller shape is the clearest case the Animator-Opinion Rule governs: an
animator has a strong opinion about whether the IK hand is a cube or a curved
circle, and no opinion whatsoever about how a NURBS curve's CVs are written
into a JSON file. This design gives the rigger that choice, per controller, per
module instance, stored in the `.tr`, chosen from a visual library.

It also closes a reproducibility hole that exists today: the shape library's
search order lets `~/TikWorks/user_control_shapes/Circle.json` silently shadow
the shipped `Circle`, so two artists building the same `.tr` get different
rigs.

## Scope

In scope: splitting the shape library from its Maya capture utilities and
moving both the resolver and the data down to `tik.core`; the module manifest
declaration; the resolution chain in `rig.controller`; the rigger's sparse
override table and the per-control fold that edits it; the pinned build
library; a shared thumbnail picker widget; rebuilding the polish shape UI on
that widget.

Out of scope: the post-build `shape` action (capturing a hand-edited curve back
onto a built control); per-control colour, which stays `SIDE_COLORS`' single
answer; shapes for tweak controllers, which are excluded from the control
manifest by construction.

---

## Part 0 — What the code proved

Four findings shaped this design; two of them reversed an earlier plan.

### 0.1 The library is already complete, and already shipped

`src/python/tik/maya/data/control_shapes/` and the user's own
`~/TikWorks/user_control_shapes` were identical file-for-file except for three
shapes under `animated/` (`AnimatedDrop`, `FkikSwitch`, `LimitedDirection`),
which have since been committed. The shipped set is **86 shapes in 9
categories, 172 files** — each shape a `<name>.json` beside a `<name>.png`
thumbnail.

So "we are missing a shape library" was not the problem. Nothing about the
catalogue needed building.

### 0.2 The word "library" was bundling four separable things

The apparent dilemma — *move the library into tik.trigger, and accept a
polish to trigger dependency* — dissolved once the pieces were named:

| # | Piece | Nature | Animator opinion? |
|---|-------|--------|-------------------|
| 1 | Curve format and apply (`set_shape`, `add_shape`) | mechanism | no |
| 2 | The resolver: search paths, name to file, category, thumbnail | a file index | no |
| 3 | The catalogue: 86 json/png | a data asset, a vocabulary | no |
| 4 | **The mapping: control role to shape** | **policy** | **yes** |

The Animator-Opinion Rule places 4 in tik.trigger. It says nothing about 1-3.
An animator cares that the IK hand is a `CurvedCircle`; nobody has an opinion
about a file named `CurvedCircle.json` existing, any more than about a font
file existing — the opinion is in which font you pick.

Piece 4 is the one that does not exist anywhere. Moving 1-3 would have been
motion, not progress, and would have inverted the layering
(`tik.tools.polish` depending on `tik.trigger`) that the repository's own rule
forbids.

### 0.3 The import boundaries make one home impossible

`tests/unit/test_import_boundaries.py` sets
`FORBIDDEN["maya"] = ("tik.trigger", "tik.shared") + QT`, and
`src/python/tik/maya/__init__.py` line 5 is `from maya import cmds` — so
importing *anything* under `tik.maya` requires a live Maya interpreter.

Two consumers therefore cannot share a library that lives in `tik.maya`:

- The picker widget must run headless. `tests/ui` runs under
  `TIK_TESTS_NO_MAYA=1` with `QT_QPA_PLATFORM=offscreen`, so it cannot import
  `tik.maya.utils.control_shapes`.
- `Controller.set_shape("Circle")` lives in `tik.maya`, which may not import
  `tik.shared`.

There is no position in the current layout that both can reach. The resolver
has to move down to `tik.core`, which every layer may import. This is the one
structural change the design is forced into, and it is a clean one — the
current file is two unrelated things sharing a module.

### 0.4 The polish prototype is real, and worth keeping

`tik/tools/polish/ui/mcv/controller_shapes_mcv.py` is 464 working lines: a
category tree that toggles to an 80px icon grid, thumbnails read from the
`.png` siblings, a floating hover overlay, search, and drill-down navigation.
It is spike-grade — a hardcoded `D:/dev/tikworks/src` appended to `sys.path`, a
loop that purges `tik.maya` out of `sys.modules`, a direct `PySide6` import
instead of `tik.shared.ui.Qt`, and a private stylesheet instead of the official
theme — but it is the right answer to "how do we show 86 shapes", and it should
graduate rather than be abandoned.

`tik/shared/ui/tile_grid.py` already provides most of it: `TileGrid` groups
tiles by category, reflows to the available width, and takes an injected icon
provider. It is already used by the Designer shelf and the session view, and
already tested.

---

## Part 1 — Where the library lives

`tik/maya/utils/control_shapes.py` splits along the line Part 0.3 forced.

**`tik/core/control_shapes.py`** (new, pure — paths and JSON, no Maya, no Qt):

- `ControlShapeLibrary` — search paths, the name to file index, categories, the
  thumbnail sibling, `list_shapes`, `get_shape_data`, `get_path`, `load`,
  `add_path`, `remove_path`, `refresh`.
- `save_to_disk`, `_resolve_folder_path`, `_normalize_ratio`, `_scale_data` —
  all of which are arithmetic and file writes, with nothing Maya about them.

**`tik/maya/utils/control_shapes.py`** (keeps only what needs a scene):

- `capture`, `capture_to_disk`, `capture_thumbnail`, `_guess_camera_view`,
  `CAMERA_POSITIONS` — OpenMaya curve reads, `Panel`, `Camera`, `playblast`.
- Re-exports `ControlShapeLibrary` so existing call sites
  (`tik/maya/roles/controller.py`, `tik/tools/polish/core.py`,
  `tik/__init__.py`) keep working unchanged.

**The data moves to `tik/core/data/control_shapes/`** — all 172 files, by
`git mv`. Curve data is points, knots and a degree: DCC-agnostic by nature, and
core is where it honestly belongs. The alternative considered was leaving the
files under `tik/maya/data/` and having the core index compute that path as a
string. That was rejected: it satisfies the import-boundary test while
violating what the test is for, and it makes `tik.core` know where `tik.maya`
keeps its files.

Two behavioural changes to `ControlShapeLibrary` fall out of this part:

1. **The user path becomes opt-in.** `ControlShapeLibrary(include_user_path=True)`
   is the default, preserving today's behaviour for polish and for
   `Controller.set_shape`. Part 5 passes `False`.
2. **`__init__` stops creating directories.** It currently runs
   `self._user_path.mkdir(parents=True, exist_ok=True)` on construction, so
   merely importing the module creates `~/TikWorks/user_control_shapes`.
   Creating a directory as an import side effect is wrong independently of this
   design; the directory is created on first write instead, in
   `_resolve_folder_path`, which already does it.

---

## Part 2 — The declaration

A module declares its default shape per controller role, beside `controls`,
`outputs` and `pivot_controls`:

```python
class Module(Schema):
    #: Default shape per controller role, keyed by the names ``control_names``
    #: returns. The manifest is the only place a default lives.
    control_shapes: dict[str, str] = {}

    @classmethod
    def control_shape_defaults(cls, settings: Optional[dict] = None) -> dict[str, str]:
        """Default shape per control role.

        Override when a setting drives them -- exactly as ``control_names``
        and ``output_names`` are overridden.
        """
        return dict(cls.control_shapes)
```

Control roles are not literals: `_role(name, "fk", label)` computes them inside
`systems/limb.py`, and a module that hardcoded those names would drift the
moment a role was renamed. `limb_control_names` already exists to prevent
exactly that, so the system gains its mirror:

```python
def limb_control_shapes(name: str = "", labels: Sequence[str] = ()) -> dict[str, str]:
    """The default shape per role ``build_ikfk_limb`` creates for these arguments."""
    return {
        _role(name, "ik"): "Cube",
        **{_role(name, "fk", label): "Circle" for label in labels},
        _role(name, "pole"): "Diamond",
    }
```

and `arm` spreads it in, the same way it already spreads the names:

```python
controls = ("collar", *limb_control_names(labels=LIMB_LABELS))
control_shapes = {
    "collar": "CurvedCircle",
    **limb_control_shapes(labels=LIMB_LABELS),
}
```

`fkchain` and `ribbon` build one control per segment, so they override
`control_shape_defaults(settings)` the way they already override
`control_names(settings)`.

---

## Part 3 — Resolution

**`rig.controller` loses its `shape` parameter entirely.** Not merely its call
sites: keeping the parameter would preserve a second place a default could
hide, and the module ground rules already require the manifest to equal what
`build()` creates. Removing it makes the manifest the single source by
construction rather than by convention.

`rig.controller(name, ...)` already receives the role — `name` is what gets
stamped as `tags.ROLE` — so it resolves without new arguments:

1. the rigger's override row for this role, if one exists (Part 4);
2. `type(self.instance).control_shape_defaults(self.instance.values()).get(role)`;
3. `"Circle"`.

Size keeps its existing three mechanisms untouched. The module still computes
the base — `_derive_size(guides)` in the limb, the `controller_size` field in
`base` / `fkchain` / `ribbon` — and the override supplies a **multiplier**, so
the default of `1.0` is a no-op and nothing collides. Swapping a `Cube` for a
`Diamond` usually wants a nudge, which is why shape and size travel together
rather than the size living somewhere else.

`rig.tweak_control` keeps its own `shape="Circle"` parameter. Tweaks are
excluded from the control manifest by construction — `rig.tweak_control`
parents them under their main — so they have no role to key an override on.

A shape change is an ordinary settings change: it flags a built module in the
test rig for rebuild, exactly as any other setting does, and it does not touch
guides.

---

## Part 4 — The rigger's override

### 4.1 Storage

A sparse `TableField` on the `Module` base, in its own fold:

```python
SHAPES = FieldGroup("Shapes", collapsed=True)
"""Every module's control shapes fold away; declared here, not per module."""

control_shape_overrides = TableField(
    [],
    label="Control Shapes",
    group=SHAPES,
    help="Override the shape and relative size of one controller.",
    last=True,
    rows_from="control_names",
    columns=(
        Column("control", "choice", choices_from="control_names"),
        Column("shape", "shape"),
        Column("size", "float"),
    ),
)
```

This is the `anim_spaces` / `pivot_presets` idiom, so it serialises into the
`.tr` with the module's settings, diffs correctly against a referenced source
(making an override self-cleaning), and undoes on the session stack — all for
free.

**The table is sparse: a row exists only for a control the rigger actually
changed.** That is what keeps module defaults live — a module that improves its
default propagates to every rig that never overrode it — and it makes "revert
to default" a row deletion rather than a second null state.

**No `.tr` schema bump.** This is an ordinary module setting, and module
settings are already free-form per module type.

### 4.2 Editor

`rows_from` is the opt-in that swaps the widget, the same way `choices_from`
makes a `ListField` render as a `CheckListEditor` and `filterable` adds the
`FilterBar`. When `FormBuilder` sees it, it builds a per-control fold instead
of an add/remove table:

- one row per role returned by `control_names(settings)`, in manifest order;
- each row a thumbnail button (`ShapeButton`, Part 6) and a size spinner;
- a row with no stored override draws the module default greyed, so the rigger
  sees the whole instance's appearance at a glance without adding anything;
- editing a row writes it into the sparse table; clearing it removes the row.

The rigger never picks a control out of a combo box, and never has to add a row
to discover what a control currently looks like.

Two new `Column` kinds are required — `Column.kind` is `"string" | "choice"`
today:

- **`"shape"`** — a `ShapeButton` showing the current thumbnail, opening the
  picker as a popup.
- **`"float"`** — a spin box; the size multiplier, defaulting to `1.0`.

The `control` column is still declared with `choices_from="control_names"` even
though `rows_from` already fixes the row set. It is what the stored row is keyed
by, and keeping it means the table remains a plain, readable table for anything
that does not build the custom editor — `to_dict`, a reference diff, a text
inspection of the `.tr`.

### 4.3 Partial rows, stale rows, unresolvable names

**Resolution is per field, not per row.** A row that sets a shape but leaves
size unset resolves size to `1.0`; a row that sets only a size resolves the
shape from the manifest default. This falls out of the sparse storage and is
what lets the fold's two widgets be cleared independently.

**A stale row is kept and warned about, never dropped.** Lowering `segments`
on an `fkchain` leaves a row naming a control that is no longer built. This
follows `Module.warnings()` exactly as `anim_spaces` and `pivot_presets`
already do, for the reason documented there: the row is kept, so raising the
count restores the setup intact. The message reads
`control shape '<control>': control is not built with the current settings`.

**An unresolvable shape name falls back and warns.** The picker cannot offer a
shape the pinned library lacks (Part 5), but a `.tr` authored on a machine with
a `TRIGGER_SHAPES_PATH` entry that this machine does not have can still carry
one. The build resolves such a row to the manifest default and reports
`control shape '<control>': shape '<name>' is not in the shape library` through
`warnings()` — not `validate()`, because a missing thumbnail must cost the
rigger a warning, not the rig.

---

## Part 5 — The pinned build library

`tik/trigger/core/shapes.py` (pure — it imports `tik.core` only, so both
`trigger/maya/rig.py` and `trigger/ui` may reach it) owns one library whose
search order is:

1. the shipped `tik/core/data/control_shapes`;
2. every entry in `TRIGGER_SHAPES_PATH`.

`~/TikWorks/user_control_shapes` is **not** on it — the library is constructed
with `include_user_path=False`.

This is the preferences guarantee applied to shapes. A per-user home folder is
a preference by any reasonable reading, and *given the same `.tr`, two artists
must build the same rig*. Today they do not: the user path resolves after the
core path, so a personal `Circle.json` silently replaces the shipped one for
that artist alone.

`TRIGGER_SHAPES_PATH` is the escape hatch, and it is the right one: a studio
path is deployed and version-controlled, so it is the same for everyone who
resolves through it. A personal shape must be promoted to such a path before a
rig can use it.

The picker reads its list from this same pinned library, so **it is not
possible to choose a shape the build cannot resolve** — the constraint is
enforced by construction rather than by a validation pass.

---

## Part 6 — The picker, and polish

### 6.1 `tik/shared/ui/shape_picker.py`

- `ShapePicker(QWidget)` — built on `TileGrid`, categories as its groups, an
  icon provider that loads the `.png` sibling of each shape's JSON, a
  `FilterBar` for search, on the official theme.
- `ShapeButton(QToolButton)` — the per-row control used by the Part 4 fold:
  shows the current shape's thumbnail, opens `ShapePicker` as a popup, emits
  the chosen name.

The module imports `tik.core.control_shapes` and Qt, and never `tik.maya` — so
it runs under `TIK_TESTS_NO_MAYA=1`, which is what Part 0.3 forced.

### 6.2 Polish

`tik/tools/polish/ui/mcv/controller_shapes_mcv.py` is rebuilt on `ShapePicker`.
This deletes the hardcoded `sys.path` append, the `sys.modules` purge loop, the
direct `PySide6` import, the private stylesheet, and the bespoke
`ShapeLibraryModel` / `FlatLeafProxyModel` / `HoverOverlay` stack that
`TileGrid` already covers.

Polish keeps its own library instance with `include_user_path=True` — a
cleanup tool *should* see the artist's personal shapes; only the rig build must
not. Its capture and save flow stays Maya-side and is not otherwise touched.

---

## Part 7 — Tests

| File | Covers |
|------|--------|
| `tests/unit/test_control_shapes.py` | updated for the move; asserts the pure library imports with no Maya available, that `include_user_path=False` excludes it, and that construction creates no directories |
| `tests/unit/test_shape_resolution_trigger.py` | the chain override to manifest to `"Circle"`; the size multiplier; per-field resolution of a partial row; sparse storage round-tripping through the `.tr`; a deleted row reverting to the module default |
| `tests/unit/test_core_trigger.py` | extended: `warnings()` for a stale control-shape row and for an unresolvable shape name, and that neither reaches `validate()` |
| `tests/unit/test_pinned_shapes_trigger.py` | the build library's search order; that a user-path shape of the same name does not shadow a shipped one; that `TRIGGER_SHAPES_PATH` is honoured |
| `tests/integration/trigger/test_module_ground_rules.py` | extended: every declared control has a default that resolves in the pinned library, and no module or system passes `shape=` |
| `tests/ui/test_shape_picker.py` | `ShapePicker` and `ShapeButton` offscreen: categories, search, selection |
| `tests/ui/test_shape_fold.py` | the per-control fold: one row per control, greyed defaults, an edit writing a sparse row, a clear removing it |

---

## Summary of Changes

**New**

- `src/python/tik/core/control_shapes.py` — the pure library and file helpers
- `src/python/tik/core/data/control_shapes/` — 172 files, moved
- `src/python/tik/trigger/core/shapes.py` — the pinned build library
- `src/python/tik/shared/ui/shape_picker.py` — `ShapePicker`, `ShapeButton`
- `tests/unit/test_shape_resolution_trigger.py`,
  `tests/unit/test_pinned_shapes_trigger.py`,
  `tests/ui/test_shape_picker.py`, `tests/ui/test_shape_fold.py`
- `tests/unit/test_core_trigger.py` — extended with the new `warnings()` cases

**Changed**

- `src/python/tik/maya/utils/control_shapes.py` — keeps capture only;
  re-exports `ControlShapeLibrary`
- `src/python/tik/core/fields.py` — `Column` kinds `"shape"` and `"float"`;
  `TableField.rows_from`
- `src/python/tik/shared/ui/fields.py` — the per-control fold editor and the
  two new column editors
- `src/python/tik/trigger/core/module.py` — `control_shapes`,
  `control_shape_defaults`, `SHAPES`, `control_shape_overrides`, and the two
  new `warnings()` checks
- `src/python/tik/trigger/maya/rig.py` — `controller()` loses `shape=` and
  resolves it instead
- `src/python/tik/trigger/systems/limb.py` — `limb_control_shapes`; no
  `shape=` at the call sites
- `src/python/tik/trigger/modules/{arm,base,fkchain,ribbon}` — declare defaults
- `src/python/tik/tools/polish/ui/mcv/controller_shapes_mcv.py` — rebuilt on
  `ShapePicker`
- `tests/unit/test_control_shapes.py`,
  `tests/integration/trigger/test_module_ground_rules.py`

**Unchanged by design**

- `tik/maya/roles/controller.py` — `set_shape` still takes a name or a dict
- `SIDE_COLORS` — still the one answer to a controller's colour
- `.tr` schema — stays at 7
