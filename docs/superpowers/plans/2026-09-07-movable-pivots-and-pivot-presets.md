# Movable Pivots and Pivot Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a trigger module declare that a controller has a movable pivot, ship named preset positions for it that the rigger places as guides, and give the animator a `showPivot` toggle and a `pivotPreset` enum.

**Architecture:** `pivot_controls` (a class dict on `Module`, control role -> anchor guide role) declares which controls are movable; `pivot_presets` (a `TableField` the rigger edits) declares the named positions. Each row draws one ordinary guide joint styled as a locator marker, so the whole Draw/Sync/reconcile/`.trg` layer carries it unchanged. tik.maya gains `Controller.drive_pivot`, pure mechanism; `rig.pivot_control` in tik.trigger creates the pivot controller, names the two attributes and builds a `choice` network from the preset guides. A pose-preserving switch tool lands last.

**Tech Stack:** Python 3.10+, Maya 2024+, tik.maya wrapper, pytest under `mayapy`.

**Spec:** `docs/superpowers/specs/2026-09-07-movable-pivots-and-pivot-presets-design.md`

## Global Constraints

- **Never call `maya.cmds` or `maya.api.OpenMaya` directly** outside `src/python/tik/maya/`. Use `import tik.maya as tm`. The one pre-existing exception this plan touches is `tik/trigger/guides/nodes.py`, which already imports `cmds`; do not add new `cmds` calls there — use the `tm` proxy.
- **No third-party dependencies.** Stdlib and Maya-bundled modules only.
- **`tik/trigger/core` is pure Python** — no Maya, no Qt imports. Enforced by `tests/unit/test_import_boundaries.py`.
- **`tik/trigger/core`, `modules`, `systems`, `maya`, `actions`, `guides` must not import the preferences packages.** Enforced by `tests/unit/test_import_boundaries.py`.
- **Modules never inherit from other modules.** Shared behaviour goes in `tik/trigger/systems/`.
- **Every dialog goes through `tik.shared.ui.feedback.Feedback`.** Raw `QMessageBox` / `QFileDialog` / `QInputDialog` fails `tests/unit/test_dialog_boundaries.py`.
- **House style:** properties for state (noun), methods for actions (verb), no `get_`/`set_` prefixes, no single-letter names, type hints and PEP 257 docstrings on public APIs.
- Run unit tests with: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/<file> -q`
- Run integration tests with: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/integration/trigger/<file> -q`
- Run UI tests with: `$env:PYTHONPATH="src/python"; $env:TIK_TESTS_NO_MAYA="1"; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui/<file> -q`
- Run `make lint` (black, isort, flake8) before every commit. `make format` fixes formatting.

---

### Task 1: `Field.with_default`

A module needs to change a base field's default rows without restating its columns, group, help and `last` flag.

**Files:**
- Modify: `src/python/tik/core/fields.py` (add a method to `Field`, around line 133 after `to_schema`)
- Test: `tests/unit/test_fields.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Field.with_default(default) -> Field` — returns a shallow copy of the field with `default` replaced (run through `validate`, so a `TableField` normalises its rows and an out-of-range value raises).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_fields.py`:

```python
def test_with_default_copies_the_field_and_replaces_its_default():
    from tik.core.fields import Column, IntField, Schema, TableField

    class Base(Schema):
        rows = TableField(
            [],
            label="Rows",
            help="original help",
            last=True,
            columns=(Column("control", "choice"), Column("label", "string")),
        )

    class Child(Base):
        rows = Base.rows.with_default([{"control": "ik", "label": "tip"}])

    assert Base().rows == []
    assert Child().rows == [{"control": "ik", "label": "tip"}]
    # the shape travels with the copy
    child_field = Child.fields()["rows"]
    assert [column.name for column in child_field.columns] == ["control", "label"]
    assert child_field.help == "original help"
    assert child_field.last is True
    assert child_field.label == "Rows"
    # the original is untouched
    assert Base.fields()["rows"].default == []
    # a plain field works too, and the new default is validated
    assert IntField(1, max=10).with_default(5).default == 5
    with pytest.raises(FieldValidationError):
        IntField(1, max=10).with_default(50)
```

Make sure `pytest` and `FieldValidationError` are imported at the top of the file; add them if they are not.

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_fields.py::test_with_default_copies_the_field_and_replaces_its_default -q`
Expected: FAIL with `AttributeError: 'TableField' object has no attribute 'with_default'`

- [ ] **Step 3: Write minimal implementation**

In `src/python/tik/core/fields.py`, inside `class Field`, immediately after `to_schema`:

```python
    def with_default(self, default: Any) -> "Field":
        """A copy of this field holding a different default.

        For a subclass that keeps a base field's shape -- its columns, group,
        help and ordering -- and changes only what it starts out holding.
        Restating the whole declaration to move a default would duplicate it in
        every subclass and drift the moment the shape changes.

        Args:
            default: The new default, validated the way an assignment would be.

        Returns:
            Field: A new field of the same type; this one is untouched.
        """
        clone = copy.copy(self)
        clone.default = clone.validate(default)
        return clone
```

`copy` is already imported at the top of the module.

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_fields.py -q`
Expected: PASS, whole file green.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/core/fields.py tests/unit/test_fields.py
git commit -m "Add Field.with_default for subclass default overrides"
```

---

### Task 2: The module declaration

`pivot_controls`, the `pivot_presets` table, its derived readers, and the validate/warnings split.

**Files:**
- Modify: `src/python/tik/trigger/core/module.py`
- Test: `tests/unit/test_core_trigger.py`
- Test helper: `tests/helpers/toy_modules.py`

**Interfaces:**
- Consumes: `Field.with_default` (Task 1).
- Produces:
  - `Module.pivot_controls: dict[str, str]` — control role -> anchor guide role.
  - `Module.pivot_presets` — `TableField` with columns `control` (choice, `choices_from="pivot_control_names"`) and `label` (string).
  - `Module.pivot_control_names(settings=None) -> tuple[str, ...]`
  - `Module.pivot_rows(settings=None) -> list[dict]`
  - `Module.pivot_guide_roles(settings=None) -> tuple[str, ...]` — `"pivot_<control>_<label>"` per well-formed row, in row order.
  - `Module.expected_guides()` now appends `(role, 0)` for each pivot guide role.
  - `Module.validate()` gains the empty-label and duplicate-role problems.
  - `Module.warnings()` gains the stale-control warning.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_core_trigger.py`:

```python
# ------------------------------------------------------------ pivot presets
def _pivot_module():
    """A module with one movable control and three preset rows."""

    class Pivoted(Module):
        guides = GuideLayout("root", "hand")
        controls = ("ik",)
        pivot_controls = {"ik": "hand"}
        pivot_presets = Module.pivot_presets.with_default(
            [{"control": "ik", "label": label} for label in ("tip", "ball", "wrist")]
        )

    return Pivoted


def test_pivot_control_names_comes_from_the_declaration():
    module = _pivot_module()()
    assert module.pivot_control_names(module.values()) == ("ik",)
    assert Module.pivot_control_names({}) == ()


def test_pivot_rows_default_to_the_modules_own():
    module = _pivot_module()()
    assert [row["label"] for row in module.pivot_rows(module.values())] == [
        "tip",
        "ball",
        "wrist",
    ]


def test_pivot_guide_roles_are_named_for_control_and_label():
    module = _pivot_module()()
    assert module.pivot_guide_roles(module.values()) == (
        "pivot_ik_tip",
        "pivot_ik_ball",
        "pivot_ik_wrist",
    )


def test_pivot_guide_roles_skip_incomplete_rows():
    module = _pivot_module()()
    module.pivot_presets = [
        {"control": "ik", "label": "tip"},
        {"control": "", "label": "orphan"},
        {"control": "ik", "label": ""},
    ]
    assert module.pivot_guide_roles(module.values()) == ("pivot_ik_tip",)


def test_expected_guides_includes_the_preset_guides():
    module = _pivot_module()()
    assert module.expected_guides() == [
        ("root", 0),
        ("hand", 0),
        ("pivot_ik_tip", 0),
        ("pivot_ik_ball", 0),
        ("pivot_ik_wrist", 0),
    ]


def test_validate_accepts_preset_guides():
    """The layout does not know the pivot roles; validate must not hand them over."""
    module = _pivot_module()()
    assert module.validate() == []


def test_validate_rejects_an_empty_preset_label():
    module = _pivot_module()()
    module.pivot_presets = [{"control": "ik", "label": ""}]
    assert module.validate() == ["pivot preset row 1: label is required"]


def test_validate_rejects_duplicate_preset_rows():
    module = _pivot_module()()
    module.pivot_presets = [
        {"control": "ik", "label": "tip"},
        {"control": "ik", "label": "tip"},
    ]
    assert module.validate() == ["pivot preset row 2: 'ik.tip' is already defined"]


def test_a_preset_on_a_control_with_no_movable_pivot_warns():
    """A settings change must cost a warning, never the rig."""
    module = _pivot_module()()
    module.pivot_presets = [{"control": "fk", "label": "tip"}]
    assert module.validate() == []
    assert module.warnings() == [
        "pivot preset 'fk.tip': control 'fk' has no movable pivot with the "
        "current settings"
    ]
```

Add `Module` and `GuideLayout` to the `tik.trigger.core` import list at the top of the file if they are not already there (`GuideLayout` is; add `Module`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_core_trigger.py -q -k pivot`
Expected: FAIL — `AttributeError: type object 'Module' has no attribute 'pivot_presets'`

- [ ] **Step 3: Write the implementation**

In `src/python/tik/trigger/core/module.py`, after the `SPACES` group definition:

```python
PIVOTS = FieldGroup("Pivots", collapsed=True)
"""Every module's pivot presets fold away; declared here, not per module."""
```

Inside `class Module`, after the `controls` declaration:

```python
    #: Controller roles that get a movable pivot, mapped to the guide their
    #: preset guides hang under. Declaring an entry is what makes the control
    #: movable, the way declaring an input is what makes its socket. The anchor
    #: is the module author's business, never the rigger's, so it is a class
    #: attribute rather than a table column.
    pivot_controls: dict[str, str] = {}
```

After the `anim_spaces` field:

```python
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

After `control_names`:

```python
    @classmethod
    def pivot_control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles with a movable pivot.

        Override when a setting drives them, exactly as ``control_names`` and
        ``output_names`` are overridden.
        """
        return tuple(cls.pivot_controls)

    @classmethod
    def pivot_rows(cls, settings=None) -> list[dict]:
        """The pivot-preset rows from ``settings`` (or the field default)."""
        if settings is None:
            return [dict(row) for row in cls.pivot_presets.default]
        return [dict(row) for row in (settings.get("pivot_presets") or [])]

    @classmethod
    def pivot_guide_roles(cls, settings=None) -> tuple[str, ...]:
        """``pivot_<control>_<label>`` per well-formed row, in row order.

        The role carries the *label*, never the row index: a document stores
        poses by ``(role, index)``, and an index-keyed role would shuffle every
        preset's position between presets the moment a row is reordered or
        removed.
        """
        found = []
        for row in cls.pivot_rows(settings):
            control, label = row.get("control", ""), row.get("label", "")
            if control and label:
                found.append(f"pivot_{control}_{label}")
        return tuple(found)
```

Replace `expected_guides`:

```python
    def expected_guides(self) -> list[tuple[str, int]]:
        """``(role, index)`` pairs this module wants when drawing fresh guides.

        The layout's pairs first, then one guide per pivot-preset row. A preset
        guide is an ordinary guide in every respect -- it poses, syncs,
        reconciles and round-trips through a ``.trg`` -- so the only thing that
        marks it out is where its role name comes from.
        """
        pairs = self.guides.expand(self.guide_count())
        pairs.extend((role, 0) for role in self.pivot_guide_roles(self.values()))
        return pairs
```

Replace `validate`:

```python
    def validate(self) -> list[str]:
        """Return problems that prevent building (empty list = ok)."""
        pairs = self.guide_pairs or self.expected_guides()
        pivot_roles = set(self.pivot_guide_roles(self.values()))
        problems = list(
            self.guides.validate([p for p in pairs if p[0] not in pivot_roles])
        )
        problems.extend(self._validate_spaces())
        problems.extend(self._validate_pivots())
        return problems
```

Add beside `_validate_spaces`:

```python
    def _validate_pivots(self) -> list[str]:
        """Pivot-preset rows must derive unique, well-formed guide roles."""
        problems, seen = [], set()
        for index, row in enumerate(self.pivot_presets):
            control, label = row.get("control", ""), row.get("label", "")
            if not label:
                problems.append(f"pivot preset row {index + 1}: label is required")
                continue
            name = f"{control}.{label}"
            if name in seen:
                problems.append(
                    f"pivot preset row {index + 1}: '{name}' is already defined"
                )
            seen.add(name)
        return problems
```

Extend `warnings`, after the anim-space loop and before `return problems`:

```python
        movable = type(self).pivot_control_names(self.values())
        for row in self.pivot_presets:
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            if control not in movable:
                problems.append(
                    f"pivot preset '{control}.{label}': control '{control}' has "
                    f"no movable pivot with the current settings"
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_core_trigger.py -q`
Expected: PASS, whole file green.

- [ ] **Step 5: Run the wider unit suite for regressions**

Run: `$env:PYTHONPATH="src/python"; mayapy tests/unit/invoke.py`
Expected: PASS. `expected_guides` and `validate` changed, so `test_document_trigger.py`, `test_session_trigger.py` and `test_guide_scene_trigger.py` are the ones to watch.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/core/module.py tests/unit/test_core_trigger.py
git commit -m "Declare movable pivot controls and pivot presets on Module"
```

---

### Task 3: Preset guides in the document

`expand_guides` is the one function that decides which `GuideRecord`s an entry holds. It must produce a record per preset row, so poses persist and reconcile sees them.

**Files:**
- Modify: `src/python/tik/trigger/core/guide_document.py` (`expand_guides`, around line 398)
- Modify: `src/python/tik/trigger/guides/scene.py` (3 call sites: ~line 312, ~line 482, ~line 761)
- Modify: `src/python/tik/trigger/guides/exchange.py` (1 call site, ~line 234)
- Test: `tests/unit/test_guide_document_trigger.py`

**Interfaces:**
- Consumes: `Module.pivot_guide_roles` (Task 2).
- Produces: `expand_guides(entry, layout, count, extra=()) -> None` — `extra` is a sequence of role names appended as `(role, 0)` pairs after the layout's own.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_guide_document_trigger.py`:

```python
def test_expand_guides_appends_extra_roles_and_keeps_their_poses():
    entry = ModuleEntry(instance_id="one", module_type="toy", name="toy")
    layout = GuideLayout("root", "hand")
    expand_guides(entry, layout, 0, extra=("pivot_ik_tip", "pivot_ik_ball"))
    assert entry.pairs == [
        ("root", 0),
        ("hand", 0),
        ("pivot_ik_tip", 0),
        ("pivot_ik_ball", 0),
    ]

    entry.guide("pivot_ik_tip", 0).position = (1.0, 2.0, 3.0)
    entry.guide("pivot_ik_tip", 0).posed = True
    # dropping the 'ball' row leaves 'tip' untouched
    expand_guides(entry, layout, 0, extra=("pivot_ik_tip",))
    assert entry.pairs == [("root", 0), ("hand", 0), ("pivot_ik_tip", 0)]
    assert entry.guide("pivot_ik_tip", 0).position == (1.0, 2.0, 3.0)

    # re-adding it restores the record, unposed, without disturbing 'tip'
    expand_guides(entry, layout, 0, extra=("pivot_ik_tip", "pivot_ik_ball"))
    assert entry.guide("pivot_ik_tip", 0).position == (1.0, 2.0, 3.0)
    assert entry.guide("pivot_ik_ball", 0).posed is False
```

Check the top of the file imports `GuideLayout`; add `from tik.trigger.core import GuideLayout` if not.

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_guide_document_trigger.py::test_expand_guides_appends_extra_roles_and_keeps_their_poses -q`
Expected: FAIL with `TypeError: expand_guides() got an unexpected keyword argument 'extra'`

- [ ] **Step 3: Write the implementation**

Replace `expand_guides` in `src/python/tik/trigger/core/guide_document.py`:

```python
def expand_guides(entry: ModuleEntry, layout, count: int, extra: Sequence[str] = ()) -> None:
    """Match ``entry.guides`` to ``layout.expand(count)`` plus ``extra``.

    The document-side answer to a settings change that adds or removes guides
    (``fkchain.segments`` 3 -> 5, or a pivot-preset row added or dropped).
    Survivors keep their records untouched; new pairs arrive unposed, so
    regenerate places them at their ``draw_guides`` position rather than at the
    origin.

    Args:
        entry: The document entry to rewrite.
        layout: The module's ``GuideLayout``.
        count: Number of multi-role guides.
        extra: Single-index roles appended after the layout's own -- the pivot
            preset guides, whose set follows a settings table rather than the
            layout.
    """
    existing = {record.pair: record for record in entry.guides}
    pairs = layout.expand(count) + [(role, 0) for role in extra]
    entry.guides = [
        existing.get(pair) or GuideRecord(role=pair[0], index=pair[1])
        for pair in pairs
    ]
```

Add `Sequence` to the `typing` import at the top of the file if it is not already there.

Then update all four call sites to pass the module's pivot roles. In `src/python/tik/trigger/guides/scene.py` and `src/python/tik/trigger/guides/exchange.py`, each currently reads:

```python
        expand_guides(entry, module.guides, module.guide_count())
```

(the scene.py third one uses `existing_entry` instead of `entry`). Replace each with:

```python
        expand_guides(
            entry,
            module.guides,
            module.guide_count(),
            extra=module.pivot_guide_roles(module.values()),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_guide_document_trigger.py -q`
Expected: PASS.

- [ ] **Step 5: Run the wider unit suite**

Run: `$env:PYTHONPATH="src/python"; mayapy tests/unit/invoke.py`
Expected: PASS.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/core/guide_document.py src/python/tik/trigger/guides/scene.py src/python/tik/trigger/guides/exchange.py tests/unit/test_guide_document_trigger.py
git commit -m "Carry pivot preset guides in the guide document"
```

---

### Task 4: Drawing preset guides

They draw after the module's own guides, under the anchor guide, styled as a locator marker.

**Files:**
- Modify: `src/python/tik/trigger/guides/nodes.py` (`create_guide_joint`)
- Modify: `src/python/tik/trigger/core/module.py` (`draw_all_guides`, `_draw_pivot_guides`)
- Modify: `src/python/tik/trigger/maya/rig.py` (`GuideDraft.joint` gains `marker`)
- Modify: `src/python/tik/trigger/guides/regenerate.py:103`
- Modify: `src/python/tik/trigger/guides/exchange.py:95`
- Test: `tests/unit/test_regenerate_trigger.py`

**Interfaces:**
- Consumes: `Module.pivot_guide_roles`, `Module.pivot_controls`, `Module.pivot_rows` (Task 2).
- Produces:
  - `create_guide_joint(..., marker: bool = False)` — when True, the joint's bone is not drawn (`drawStyle = 2`) and a locator shape is parented under it.
  - `GuideDraft.joint(..., marker: bool = False)` — passes `marker` through.
  - `Module.draw_all_guides(draft) -> None` — `draw_guides` then `_draw_pivot_guides`. **This is what the draw path calls**; `draw_guides` stays the module author's method.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_regenerate_trigger.py`:

```python
def test_preset_guides_draw_under_their_anchor_as_markers():
    """A preset row draws one locator-styled guide, parented to its anchor."""
    from tik.trigger.core import get_module, register_module, unregister_module
    from tik.trigger.core.module import Module
    from tik.trigger.core.manifest import GuideLayout

    class Pivoted(Module):
        guides = GuideLayout("root", "hand")
        controls = ("ik",)
        pivot_controls = {"ik": "hand"}
        pivot_presets = Module.pivot_presets.with_default(
            [{"control": "ik", "label": label} for label in ("tip", "ball")]
        )

        def draw_guides(self, guides):
            root = guides.joint("root", (0, 0, 0))
            guides.joint("hand", (5, 0, 0), parent=root)

    register_module("pivoted")(Pivoted)
    try:
        cmds.file(new=True, force=True)
        document = GuideDocument()
        entry = ModuleEntry(
            instance_id="one", module_type="pivoted", name="pivoted", side="C"
        )
        module = get_module("pivoted")()
        expand_guides(
            entry,
            module.guides,
            module.guide_count(),
            extra=module.pivot_guide_roles(module.values()),
        )
        document.modules.append(entry)

        created = regenerate(entry, document)

        assert ("pivot_ik_tip", 0) in created
        assert ("pivot_ik_ball", 0) in created
        tip = created[("pivot_ik_tip", 0)]
        # parented under the anchor guide, and drawn there
        assert tip.parent.long_name == created[("hand", 0)].long_name
        assert list(tip.world_position) == list(created[("hand", 0)].world_position)
        # a marker: the bone is not drawn, and it carries a locator shape
        assert tip["drawStyle"].value == 2
        assert [tm.cmds.nodeType(shape.long_name) for shape in tip.shapes] == ["locator"]
        # still a joint to every scan in the guide layer
        assert tm.cmds.nodeType(tip.long_name) == "joint"
        assert tip.meta.get(tags.ROLE) == "pivot_ik_tip"
    finally:
        unregister_module("pivoted")
```

Match the file's existing imports — it already imports `cmds`, `GuideDocument`, `ModuleEntry`, `expand_guides` and `regenerate`. Add `import tik.maya as tm` and `from tik.trigger.maya import tags` if missing, and use `cmds.nodeType` directly rather than `tm.cmds.nodeType` if that reads better in context.

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_regenerate_trigger.py::test_preset_guides_draw_under_their_anchor_as_markers -q`
Expected: FAIL — `assert ("pivot_ik_tip", 0) in created` fails; nothing draws them yet.

- [ ] **Step 3a: Style the joint as a marker**

In `src/python/tik/trigger/guides/nodes.py`, add the marker colour constant beside `SIDE_COLORS`:

```python
MARKER_COLOR = 14  # green: a pivot-preset marker, never a chain guide
```

Change `create_guide_joint`'s signature to take `marker: bool = False` (keyword-only, after `radius`) and add, just before `return joint`:

```python
    if marker:
        _style_as_marker(joint)
    return joint


def _style_as_marker(joint) -> None:
    """Draw ``joint`` as a locator cross instead of a bone.

    A pivot-preset guide is a marker, not a link in a chain, and must not be
    mistaken for one. It stays a joint so ``guide_nodes``, ``scan``,
    ``snapshot`` and the selection sync -- all of which filter ``type="joint"``
    -- keep working on it unchanged; only what it draws changes.
    """
    joint["drawStyle"].value = 2  # None: the bone is not drawn
    locator = tm.spaceLocator(name=f"{joint.name}_tmpMarker")
    locator = tm.resolve(locator[0] if isinstance(locator, (list, tuple)) else locator)
    shape = locator.shapes[0]
    for axis in "XYZ":
        shape[f"localScale{axis}"].value = 0.6
    tm.parent(shape, joint, relative=True, shape=True)
    tm.rename(shape, f"{joint.name}Shape")
    locator.delete()
    joint.color = MARKER_COLOR
```

Note: `joint.color` writes the drawing override on the *transform*, which the locator shape inherits — verified in a live session.

- [ ] **Step 3b: Pass `marker` through `GuideDraft.joint`**

In `src/python/tik/trigger/maya/rig.py`, add `marker: bool = False` as a keyword-only argument to `GuideDraft.joint` and forward it to `create_guide_joint`:

```python
        joint = create_guide_joint(
            self.module,
            role,
            position,
            index=index,
            parent=parent,
            radius=radius,
            marker=marker,
        )
```

- [ ] **Step 3c: Draw them from the base class**

In `src/python/tik/trigger/core/module.py`, after `draw_guides`:

```python
    def draw_all_guides(self, draft) -> None:
        """Everything a fresh draw creates: the module's guides, then its presets.

        The draw path calls this, not ``draw_guides``: preset guides follow a
        settings table rather than the layout, so no module author should have
        to remember to draw them.
        """
        self.draw_guides(draft)
        self._draw_pivot_guides(draft)

    def _draw_pivot_guides(self, draft) -> None:
        """One marker guide per pivot-preset row, at its control's anchor guide.

        Stacked on the anchor is deliberate: an unplaced preset should look
        unplaced, and moving the anchor carries its presets along.
        """
        settings = self.values()
        for row in self.pivot_rows(settings):
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            anchor_role = self.pivot_controls.get(control)
            anchor = draft.created.get((anchor_role, 0)) if anchor_role else None
            if anchor is None:
                continue  # a stale row; Module.warnings() reports it
            draft.joint(
                f"pivot_{control}_{label}",
                tuple(anchor.world_position),
                parent=anchor,
                marker=True,
            )
```

- [ ] **Step 3d: Point the two draw call sites at it**

`src/python/tik/trigger/guides/regenerate.py:103` — replace `module.draw_guides(draft)` with `module.draw_all_guides(draft)`.
`src/python/tik/trigger/guides/exchange.py:95` — replace `module.draw_guides(draft)` with `module.draw_all_guides(draft)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_regenerate_trigger.py tests/unit/test_guides_trigger.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full unit and integration suites**

Run: `$env:PYTHONPATH="src/python"; mayapy tests/unit/invoke.py`
Run: `$env:PYTHONPATH="src/python"; mayapy tests/integration/invoke.py`
Expected: PASS.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/guides/nodes.py src/python/tik/trigger/core/module.py src/python/tik/trigger/maya/rig.py src/python/tik/trigger/guides/regenerate.py src/python/tik/trigger/guides/exchange.py tests/unit/test_regenerate_trigger.py
git commit -m "Draw pivot preset guides as locator markers under their anchor"
```

---

### Task 5: `Controller.drive_pivot`

The tik.maya half: pure mechanism, creating nothing and naming nothing.

**Files:**
- Modify: `src/python/tik/maya/roles/controller.py`
- Test: `tests/unit/test_controller.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Controller.drive_pivot(source, *, scale: bool = True) -> None` — `source` is a `Transform`/`Controller` (its `translate` plug is used) or a double3 `Plug`. Connects it to `rotatePivot`, and to `scalePivot` when `scale`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_controller.py`:

```python
def test_drive_pivot_from_a_transform():
    import tik.maya as tm
    from tik.maya.roles.controller import Controller

    cmds.file(new=True, force=True)
    ctrl = Controller.create(name="main_ctrl")
    driver = tm.Transform.create(name="pivot_driver", parent=ctrl.transform)
    ctrl.drive_pivot(driver)

    driver.translate = (0.0, 0.0, 4.0)
    assert list(ctrl.transform["rotatePivot"].value[0]) == [0.0, 0.0, 4.0]
    assert list(ctrl.transform["scalePivot"].value[0]) == [0.0, 0.0, 4.0]


def test_drive_pivot_from_a_plug_and_without_scale():
    import tik.maya as tm
    from tik.maya.roles.controller import Controller

    cmds.file(new=True, force=True)
    ctrl = Controller.create(name="main_ctrl")
    one = tm.Transform.create(name="one", parent=ctrl.transform)
    two = tm.Transform.create(name="two", parent=one)
    ctrl.drive_pivot(one["translate"] + two["translate"], scale=False)

    one.translate = (0.0, 0.0, 2.0)
    two.translate = (0.5, 0.0, 0.0)
    assert list(ctrl.transform["rotatePivot"].value[0]) == [0.5, 0.0, 2.0]
    assert ctrl.transform["scalePivot"].value[0] == (0.0, 0.0, 0.0)


def test_a_child_at_the_rotate_pivot_is_the_rotations_fixed_point():
    """The property that lets the pivot controller be a plain child."""
    import tik.maya as tm
    from tik.maya.roles.controller import Controller

    cmds.file(new=True, force=True)
    ctrl = Controller.create(name="main_ctrl")
    driver = tm.Transform.create(name="pivot_driver", parent=ctrl.transform)
    ctrl.drive_pivot(driver)
    driver.translate = (0.0, 0.0, 5.0)

    rest = [round(value, 5) for value in driver.world_position]
    ctrl.transform.rotate = (0.0, 90.0, 0.0)
    assert [round(value, 5) for value in driver.world_position] == rest
```

Follow the file's existing import and fixture style; move the imports to the top of the file if that is what it already does.

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_controller.py -q -k pivot`
Expected: FAIL — `AttributeError: 'Transform' object has no attribute 'drive_pivot'` (via `Controller.__getattr__`).

- [ ] **Step 3: Write the implementation**

In `src/python/tik/maya/roles/controller.py`, add to `class Controller`, after `set_color`:

```python
    # --------------------------------------------------
    # pivot
    # --------------------------------------------------

    def drive_pivot(self, source, *, scale: bool = True) -> None:
        """Drive this controller's rotate (and scale) pivot from ``source``.

        Mechanism only: what a movable pivot *is*, with no opinion about who
        moves it, what the attribute driving it is called, or how many named
        positions it offers. Lazy by design -- call it at any time on any
        controller, after whatever attributes the caller wants ordered first.

        Args:
            source: A transform whose ``translate`` drives the pivot, or a
                double3 plug (a sum of several, say).
            scale: Also drive ``scalePivot``, so scaling happens about the same
                point (default True).
        """
        plug = source if hasattr(source, "connect") else node_of(source)["translate"]
        plug >> self.node["rotatePivot"]
        if scale:
            plug >> self.node["scalePivot"]
```

Add near the top of the file, after the imports:

```python
def node_of(value):
    """The Transform behind a role, or ``value`` unchanged."""
    return getattr(value, "transform", value)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_controller.py -q`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/maya/roles/controller.py tests/unit/test_controller.py
git commit -m "Add Controller.drive_pivot"
```

---

### Task 6: `rig.pivot_control`

The tik.trigger half: creates the pivot controller, names the two animator-facing attributes, wires the presets.

**Files:**
- Modify: `src/python/tik/trigger/maya/rig.py` (`ModuleRig`, after `tweak_control`)
- Create: `tests/unit/test_pivot_trigger.py`
- Test helper: `tests/helpers/toy_modules.py` (a toy module with a movable pivot)

**Interfaces:**
- Consumes: `Controller.drive_pivot` (Task 5), `Module.pivot_controls` / `pivot_rows` (Task 2), preset guides in the scene (Task 4).
- Produces: `ModuleRig.pivot_control(main, *, size=None, shape="Sphere") -> Controller` — the pivot controller. Side effects on `main`: a `showPivot` bool always, a `pivotPreset` enum only when the module has rows for `main`'s role.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_pivot_trigger.py`:

```python
"""Movable pivots and pivot presets, built against a real Maya scene.

Spec: docs/superpowers/specs/2026-09-07-movable-pivots-and-pivot-presets-design.md
"""

import pytest
from maya import cmds

import tik.maya as tm
from tik.trigger.core import (
    GuideLayout,
    Module,
    clear_registries,
    register_module,
)
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder


class PivotToy(Module):
    """One control with a movable pivot and two presets."""

    label = "Pivot Toy"
    sided = False
    guides = GuideLayout("root", "hand")
    inputs = ()
    outputs = ("root",)
    controls = ("main",)
    pivot_controls = {"main": "hand"}
    pivot_presets = Module.pivot_presets.with_default(
        [{"control": "main", "label": label} for label in ("tip", "ball")]
    )

    def draw_guides(self, guides):
        root = guides.joint("root", (0, 0, 0))
        guides.joint("hand", (5, 0, 0), parent=root)

    def build(self, rig):
        main = rig.controller("main", match=rig.guide("hand"))
        rig.pivot_control(main)
        rig.output("root", rig.bind_joint("root", match=rig.guide("root")))


class BarePivotToy(PivotToy):
    """A movable pivot with no presets at all."""

    pivot_presets = Module.pivot_presets.with_default([])


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("pivot_toy")(PivotToy)
    register_module("bare_pivot_toy")(BarePivotToy)
    yield
    clear_registries()


def _build(module_type, preset_positions=None):
    """Build one instance, optionally moving its preset guides first."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    from tik.trigger.core import get_module

    instance = scene.create_guides(get_module(module_type)(name="toy"))
    # draw/sync take an iterable of instance ids, never a bare string
    scene.draw([instance.instance_id])
    for role, position in (preset_positions or {}).items():
        scene.guide_node(instance.instance_id, role).world_position = position
    scene.sync([instance.instance_id])
    report = Builder().build(document=scene.document, afterlife="keep")
    return report.rigs[instance.instance_id]


def _pivot(ctx):
    return ctx.rig.controller_by_role("main_pivot")


def test_pivot_control_is_a_child_of_its_main_and_untiered():
    from tik.trigger.maya import tags

    ctx = _build("pivot_toy")
    main = ctx.rig.controller_by_role("main")
    pivot = _pivot(ctx)
    assert pivot is not None
    # under main, through its own offset group
    assert pivot.offset.parent.long_name == main.transform.long_name
    assert pivot.transform.meta.get(tags.TIER) is None


def test_show_pivot_drives_the_pivot_controls_visibility():
    ctx = _build("pivot_toy")
    main = ctx.rig.controller_by_role("main")
    pivot = _pivot(ctx)
    assert main.transform["showPivot"].exists()
    assert main.transform["showPivot"].keyable is False
    main.transform["showPivot"].value = True
    assert pivot.offset["visibility"].value is True
    main.transform["showPivot"].value = False
    assert pivot.offset["visibility"].value is False


def test_preset_enum_carries_default_first_then_the_rows_in_order():
    ctx = _build("pivot_toy")
    main = ctx.rig.controller_by_role("main")
    listed = cmds.attributeQuery(
        "pivotPreset", node=main.transform.long_name, listEnum=True
    )[0]
    assert listed == "default:tip:ball"


def test_each_preset_moves_the_rotate_and_scale_pivot():
    ctx = _build(
        "pivot_toy",
        {"pivot_main_tip": (9.0, 0.0, 0.0), "pivot_main_ball": (7.0, 0.0, 0.0)},
    )
    main = ctx.rig.controller_by_role("main")
    expected = {0: [0.0, 0.0, 0.0], 1: [4.0, 0.0, 0.0], 2: [2.0, 0.0, 0.0]}
    for index, value in expected.items():
        main.transform["pivotPreset"].value = index
        assert [
            round(item, 4) for item in main.transform["rotatePivot"].value[0]
        ] == value
        assert [
            round(item, 4) for item in main.transform["scalePivot"].value[0]
        ] == value


def test_a_manual_offset_adds_on_top_of_the_preset():
    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.rig.controller_by_role("main")
    pivot = _pivot(ctx)
    main.transform["pivotPreset"].value = 1
    pivot.transform.translate = (0.0, 0.5, 0.0)
    assert [round(item, 4) for item in main.transform["rotatePivot"].value[0]] == [
        4.0,
        0.5,
        0.0,
    ]


def test_the_pivot_control_marks_the_rotations_fixed_point():
    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.rig.controller_by_role("main")
    pivot = _pivot(ctx)
    main.transform["pivotPreset"].value = 1
    rest = [round(value, 4) for value in pivot.transform.world_position]
    main.transform.rotate = (0.0, 90.0, 0.0)
    assert [round(value, 4) for value in pivot.transform.world_position] == rest


def test_no_presets_means_no_preset_enum():
    ctx = _build("bare_pivot_toy")
    main = ctx.rig.controller_by_role("main")
    assert main.transform["showPivot"].exists()
    assert not main.transform["pivotPreset"].exists()
    # and the pivot still moves by hand
    _pivot(ctx).transform.translate = (0.0, 0.0, 3.0)
    assert [round(item, 4) for item in main.transform["rotatePivot"].value[0]] == [
        0.0,
        0.0,
        3.0,
    ]


def test_building_a_pivot_for_an_undeclared_control_raises():
    from tik.trigger.core.exceptions import GuideError

    class Undeclared(PivotToy):
        pivot_controls = {}

        def build(self, rig):
            main = rig.controller("main", match=rig.guide("hand"))
            rig.pivot_control(main)

    clear_registries()
    register_module("undeclared")(Undeclared)
    with pytest.raises((GuideError, Exception)):
        _build("undeclared")
```

The `GuideScene` API used here is `draw(scope=None, poses="keep")`, `sync(scope=None)` and `guide_node(instance_id, role, index=0)` — `scope` is an *iterable of instance ids*, so a bare string would iterate its characters.

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_pivot_trigger.py -q`
Expected: FAIL — `AttributeError: 'ModuleRig' object has no attribute 'pivot_control'`

- [ ] **Step 3: Write the implementation**

In `src/python/tik/trigger/maya/rig.py`, add to `ModuleRig` after `tweak_control`:

```python
    def pivot_control(
        self,
        main: Controller,
        *,
        size: Optional[float] = None,
        shape: str = "Sphere",
    ) -> Controller:
        """Give ``main`` a movable pivot, with this module's presets for its role.

        The pivot controller is a plain child of ``main``, which is exactly
        where it belongs: a child at the local position of ``rotatePivot`` is
        the rotation's fixed point, so the marker sits on the pivot and follows
        the control with no space maths.

        A preset drives the pivot controller's *offset* group and the
        controller translates on top, so a manual adjustment survives a preset
        change. Index 0 of the enum is ``default`` -- the control's own origin,
        the way ``world`` is always index 0 of a space switch.

        Args:
            main: The controller whose pivot becomes movable.
            size: Shape scale (defaults to 1.0).
            shape: Control shape name. A pivot is a point, and a sphere is the
                one shape that reads the same from every angle.

        Returns:
            Controller: The pivot controller.

        Raises:
            GuideError: If ``main``'s role is not in the module's
                ``pivot_controls`` -- a module-author error, and a silent one
                would leave the rigger's preset rows pointing at nothing.
        """
        role = main.transform.meta.get(tags.ROLE, main.transform.name)
        if role not in self.module.pivot_controls:
            raise GuideError(
                f"'{self.module.module_type}' does not declare a movable pivot "
                f"for control '{role}'."
            )
        pivot = self.controller(
            f"{role}_pivot",
            shape=shape,
            size=size if size is not None else 1.0,
            parent=main,
            match=main,
            mirror=main.meta.get(tags.MIRROR, tags.WORLD),
            tier=None,
        )
        show = main.transform["showPivot"].create(
            "bool", default=False, keyable=False
        )
        show.visible = True
        show >> pivot.offset["visibility"]

        labels = self._pivot_labels(role)
        if labels:
            self._wire_pivot_presets(main, pivot, role, labels)
        main.drive_pivot(
            pivot.offset["translate"] + pivot.transform["translate"], scale=True
        )
        return pivot

    def _pivot_labels(self, role: str) -> list[str]:
        """Preset labels declared for ``role``, in row order."""
        return [
            row["label"]
            for row in self.module.pivot_rows(self.module.values())
            if row.get("control") == role and row.get("label")
        ]

    def _wire_pivot_presets(
        self, main: Controller, pivot: Controller, role: str, labels: list[str]
    ) -> None:
        """Store each preset on ``pivot`` and switch between them with a choice.

        A ``choice`` node takes its input type from its *first connection*, not
        from a value written into it -- so the positions live as locked hidden
        ``double3`` attributes on the pivot controller and are connected in.
        That costs no extra node and leaves the preset data readable on the
        control that uses it.
        """
        entries = ["default", *labels]
        positions = {"default": (0.0, 0.0, 0.0)}
        for label in labels:
            guide = self.guide(f"pivot_{role}_{label}")
            # snap-and-read: the offset group is a child of main, so its own
            # translate *is* the guide's position in main's local space.
            pivot.offset.snap_to(guide, rotation=False)
            positions[label] = tuple(pivot.offset.translate)
        pivot.offset.translate = (0.0, 0.0, 0.0)

        choice = tm.create_node("choice", name=self.name(role, "pivotPreset"))
        for index, label in enumerate(entries):
            name = f"preset_{label}"
            plug = pivot.transform[name].create(attributeType="double3", hidden=True)
            for axis in "XYZ":
                pivot.transform[f"{name}{axis}"].create(
                    attributeType="double", parent=name
                )
            plug.value = positions[label]
            plug.locked = True
            plug >> choice[f"input[{index}]"]
        choice["output"] >> pivot.offset["translate"]

        preset = main.transform["pivotPreset"].create(
            "enum", items=entries, keyable=False
        )
        preset.visible = True
        preset >> choice["selector"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_pivot_trigger.py -q`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/maya/rig.py tests/unit/test_pivot_trigger.py
git commit -m "Add rig.pivot_control with guide-driven pivot presets"
```

---

### Task 7: The arm's presets, and the ground rules

The arm's IK hand control gets a movable pivot with `tip` / `ball` / `wrist`, and the ground-rules test learns that a `_pivot` role is not a manifest control.

**Files:**
- Modify: `src/python/tik/trigger/modules/arm/arm.py`
- Modify: `tests/integration/trigger/test_module_ground_rules.py:88-101` and `:325-340`
- Test: `tests/integration/trigger/test_arm_trigger.py`

**Interfaces:**
- Consumes: `rig.pivot_control` (Task 6), `Module.pivot_controls` / `pivot_presets` (Task 2).
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_arm_trigger.py` (follow the file's existing build fixture — reuse whatever helper it already has for building an arm rather than inventing one):

```python
def test_the_ik_hand_control_has_a_movable_pivot_with_three_presets(built_arm):
    from maya import cmds

    ik = built_arm.rig.controller_by_role("ik")
    assert ik.transform["showPivot"].exists()
    listed = cmds.attributeQuery(
        "pivotPreset", node=ik.transform.long_name, listEnum=True
    )[0]
    assert listed == "default:tip:ball:wrist"
    assert built_arm.rig.controller_by_role("ik_pivot") is not None
```

In `tests/integration/trigger/test_module_ground_rules.py`, extend the two `_tweak` checks. First, `_built_control_roles` (line ~88):

```python
def _built_control_roles(ctx):
    """Roles tagged on the controllers a build created, tweaks and pivots excluded.

    A tweak is parented under its main and follows it, so a space switch on
    one would fight the parent it hangs from -- it is never in a manifest. A
    pivot controller is the same species for the same reason.
    """
    return sorted(
        role
        for role in (
            controller.transform.meta.get(tags.ROLE) for controller in ctx.controllers
        )
        if role and not role.endswith(("_tweak", "_pivot"))
    )
```

Then `test_every_controller_carries_a_valid_tier` (line ~335):

```python
        if role.endswith(("_tweak", "_pivot")):
            assert tier is None, f"{controller.transform.name} is a tiered helper"
```

And add a new rule at the end of the file:

```python
@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_every_movable_pivot_names_a_control_and_a_guide_the_module_has(module_type):
    """Rule: pivot_controls points at real controls and real guide roles.

    A typo here is invisible until a rigger opens the properties table and
    finds a preset row pointing at nothing.
    """
    module_cls = get_module(module_type)
    for settings in CONTROL_VARIATIONS.get(module_type, [{}]):
        instance = module_cls(settings=settings)
        controls = set(module_cls.control_names(instance.values()))
        roles = set(module_cls.guides.all_roles)
        for control, anchor in module_cls.pivot_controls.items():
            assert control in controls, f"{module_type}: '{control}' is not a control"
            assert anchor in roles, f"{module_type}: anchor '{anchor}' is not a guide"


@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_every_preset_row_targets_a_movable_control(module_type):
    """Rule: a module's own default rows never warn out of the box."""
    module_cls = get_module(module_type)
    instance = module_cls()
    assert instance.warnings() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/integration/trigger/test_arm_trigger.py -q -k pivot`
Expected: FAIL — `showPivot` does not exist on the IK control.

- [ ] **Step 3: Write the implementation**

In `src/python/tik/trigger/modules/arm/arm.py`, inside `class Arm` after `controls`:

```python
    pivot_controls = {"ik": "hand"}
    pivot_presets = Module.pivot_presets.with_default(
        [{"control": "ik", "label": label} for label in ("tip", "ball", "wrist")]
    )
```

and in `build()`, right after the `build_ikfk_limb(...)` call that assigns `limb`:

```python
        # A planted hand rolls about the fingertips, then the knuckles, then
        # the wrist. The rigger places all three; the animator picks one.
        rig.pivot_control(limb.ik_control)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/integration/trigger/test_arm_trigger.py tests/integration/trigger/test_module_ground_rules.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suites**

Run: `$env:PYTHONPATH="src/python"; mayapy tests/unit/invoke.py`
Run: `$env:PYTHONPATH="src/python"; mayapy tests/integration/invoke.py`
Expected: PASS.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/modules/arm/arm.py tests/integration/trigger/test_arm_trigger.py tests/integration/trigger/test_module_ground_rules.py
git commit -m "Give the arm's IK hand a movable pivot with tip/ball/wrist presets"
```

---

### Task 8: Switch Pivot (Preserve)

A pivot switch always disturbs a non-zero rotation — no live network can prevent it (spec Part 0.1). This tool compensates once, at the moment of the switch.

**Files:**
- Create: `src/python/tik/trigger/maya/pivot.py`
- Modify: `src/python/tik/trigger/ui/main.py` (`_build_tools_menu`, ~line 426)
- Test: `tests/unit/test_pivot_trigger.py` (append)

**Interfaces:**
- Consumes: `rig.pivot_control`'s output shape — a `pivotPreset` enum on the control.
- Produces: `switch_pivot_preset(control, preset, key: bool = False) -> None` in `tik.trigger.maya.pivot`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_pivot_trigger.py`:

```python
def test_switch_pivot_preset_holds_the_pose():
    from tik.trigger.maya.pivot import switch_pivot_preset

    ctx = _build(
        "pivot_toy",
        {"pivot_main_tip": (9.0, 0.0, 0.0), "pivot_main_ball": (7.0, 0.0, 0.0)},
    )
    main = ctx.rig.controller_by_role("main")
    main.transform["pivotPreset"].value = 1
    main.transform.rotate = (0.0, 45.0, 0.0)
    before = [round(value, 4) for value in main.transform.world_matrix]

    switch_pivot_preset(main, "ball")

    assert main.transform["pivotPreset"].value == 2
    assert [round(value, 4) for value in main.transform.world_matrix] == before


def test_switch_pivot_preset_accepts_an_index_and_rejects_an_unknown_name():
    from tik.trigger.maya.pivot import switch_pivot_preset

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.rig.controller_by_role("main")
    switch_pivot_preset(main, 1)
    assert main.transform["pivotPreset"].value == 1
    with pytest.raises(ValueError):
        switch_pivot_preset(main, "knuckle")


def test_switch_pivot_preset_rejects_a_control_with_no_movable_pivot():
    from tik.trigger.maya.pivot import switch_pivot_preset

    ctx = _build("pivot_toy")
    root = ctx.rig.controller_by_role("main_pivot")
    with pytest.raises(ValueError):
        switch_pivot_preset(root, "tip")
```

If `Transform.world_matrix` returns an `MMatrix` rather than a flat sequence, compare `[round(value, 4) for value in main.transform.world_position]` plus the rotation instead — check the property first and pick whichever comparison is honest.

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_pivot_trigger.py -q -k switch`
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.maya.pivot'`

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/trigger/maya/pivot.py`:

```python
"""Switching a control's pivot preset without moving it.

A pivot switch always disturbs a non-zero rotation: rotating about a different
point *is* a different transform, and a live ``rotatePivotTranslate``
compensation does not fix it -- the algebra collapses to ``p' = p.R`` and the
pivot stops doing anything at all (spec Part 0.1). What works is compensating
once, at the moment of the switch, which is what Maya's own pivot edit does.

Animation-time only. Nothing in the build path imports this.
"""

from __future__ import annotations

from typing import Union

import tik.maya as tm
from tik.maya.core.decorators import undo

PRESET_ATTR = "pivotPreset"


def _transform(control):
    """The Transform behind a role, or ``control`` resolved."""
    node = getattr(control, "transform", None)
    return node if node is not None else tm.resolve(control)


def preset_labels(control) -> list[str]:
    """The preset names on ``control``, ``default`` first.

    Args:
        control: A controller, transform or node name.

    Returns:
        list[str]: The enum labels, or an empty list when the control has no
        movable pivot with presets.
    """
    node = _transform(control)
    if not node[PRESET_ATTR].exists():
        return []
    listed = tm.attributeQuery(PRESET_ATTR, node=node.long_name, listEnum=True)
    return listed[0].split(":") if listed else []


@undo
def switch_pivot_preset(control, preset: Union[str, int], key: bool = False) -> None:
    """Set ``control``'s pivot preset while holding its current pose.

    Reads the world matrix, switches the preset, then writes ``translate`` so
    the control lands back where it was. Rotation applied *after* the switch
    swings about the new pivot, which is the point.

    Args:
        control: A controller, transform or node name carrying ``pivotPreset``.
        preset: A preset label or its enum index.
        key: Set a key on ``pivotPreset`` and ``translate`` afterwards.

    Raises:
        ValueError: If the control has no pivot presets, or ``preset`` names
            one it does not have.
    """
    node = _transform(control)
    labels = preset_labels(node)
    if not labels:
        raise ValueError(f"'{node.name}' has no pivot presets.")
    if isinstance(preset, int):
        index = preset
        if not 0 <= index < len(labels):
            raise ValueError(f"'{node.name}' has no pivot preset at index {preset}.")
    else:
        if preset not in labels:
            raise ValueError(
                f"'{node.name}' has no pivot preset '{preset}'. Known: {labels}."
            )
        index = labels.index(preset)

    before = node.world_position
    node[PRESET_ATTR].value = index
    after = node.world_position
    node.translate = tuple(
        current - (new - old)
        for current, old, new in zip(node.translate, before, after)
    )
    if key:
        tm.setKeyframe(node.long_name, attribute=[PRESET_ATTR, "translate"])
```

Note on the compensation: `rotatePivot` moves the control by a pure translation in its *parent* space, so correcting `translate` by the world delta expressed in that space is exact when the parent has no scale. The test asserts it against a real hierarchy.

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_pivot_trigger.py -q`
Expected: PASS. If `test_switch_pivot_preset_holds_the_pose` fails under a rotated *parent*, convert the delta through the parent's inverse matrix rather than subtracting in world space, and add a test with a rotated parent group.

- [ ] **Step 5a: Add `Feedback.ask_choice`**

Append to `tests/ui/test_feedback.py`, matching however that file already fakes a dialog (it monkeypatches the `QtWidgets` dialog statics):

```python
def test_ask_choice_returns_the_picked_item(monkeypatch):
    from tik.shared.ui import feedback as feedback_module

    monkeypatch.setattr(
        feedback_module.QtWidgets.QInputDialog,
        "getItem",
        staticmethod(lambda *args, **kwargs: ("ball", True)),
    )
    assert feedback_module.Feedback().ask_choice("t", "l", ["tip", "ball"]) == "ball"


def test_ask_choice_returns_none_on_cancel(monkeypatch):
    from tik.shared.ui import feedback as feedback_module

    monkeypatch.setattr(
        feedback_module.QtWidgets.QInputDialog,
        "getItem",
        staticmethod(lambda *args, **kwargs: ("", False)),
    )
    assert feedback_module.Feedback().ask_choice("t", "l", ["tip"]) is None
```

Then add to `src/python/tik/shared/ui/feedback.py`, directly after `ask_text`:

```python
    def ask_choice(
        self, title: str = "", label: str = "", options: Sequence[str] = (), current: int = 0
    ) -> Optional[str]:
        """Ask the user to pick one of ``options``; ``None`` when they cancel."""
        picked, accepted = QtWidgets.QInputDialog.getItem(
            self._host(), title, label, list(options), current, False
        )
        return picked if accepted else None
```

`Sequence` and `Optional` are already imported in that module.

Run: `$env:PYTHONPATH="src/python"; $env:TIK_TESTS_NO_MAYA="1"; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui/test_feedback.py -q`
Expected: PASS.

- [ ] **Step 5: Add the menu entry**

In `src/python/tik/trigger/ui/main.py`, in `_build_tools_menu` after the Guide Designer action and its separator:

```python
        self._action(
            tools_menu,
            "Switch Pivot (Preserve)…",
            self.switch_pivot_preset,
        )
```

and add the handler on the window class, near the other tool handlers:

```python
    def switch_pivot_preset(self) -> None:
        """Switch the selected control's pivot preset without moving it."""
        from tik.shared.ui.feedback import Feedback
        from tik.trigger.maya import pivot as pivot_tool

        selected = tm.ls(selection=True, type="transform") or []
        controls = [node for node in selected if pivot_tool.preset_labels(node)]
        if not controls:
            Feedback().warning(
                "Switch Pivot",
                "Select a control that has pivot presets.",
            )
            return
        labels = pivot_tool.preset_labels(controls[0])
        choice = Feedback().ask_choice("Switch Pivot", "Pivot preset:", labels)
        if choice is None:
            return
        for node in controls:
            pivot_tool.switch_pivot_preset(node, choice, key=True)
```

`Feedback` currently offers `pop_info` / `pop_error` / `pop_warning` / `pop_question` / `ask_text` and the browsers — there is no list chooser, so Step 5a adds one. A raw `QInputDialog` here would fail `tests/unit/test_dialog_boundaries.py`.

- [ ] **Step 6: Run the dialog-boundary and UI tests**

Run: `$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_dialog_boundaries.py -q`
Run: `$env:PYTHONPATH="src/python"; $env:TIK_TESTS_NO_MAYA="1"; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui/test_menus.py tests/ui/test_feedback.py -q`
Expected: PASS.

- [ ] **Step 7: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/maya/pivot.py src/python/tik/trigger/ui/main.py src/python/tik/shared/ui/feedback.py tests/unit/test_pivot_trigger.py tests/ui/test_feedback.py
git commit -m "Add Switch Pivot (Preserve)"
```

---

### Task 9: Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AI/coding_rules.md` (the Module Ground Rules section)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Update `CLAUDE.md`**

In the `tik.trigger (IN DEVELOPMENT)` **Status** paragraph, after the sentence about `guide_attrs`, add:

```
A module may also declare `pivot_controls` (control role -> anchor guide role),
which gives that controller a movable pivot: a `showPivot` bool, a pivot
controller under it driving `rotatePivot`/`scalePivot`, and — when the rigger's
`pivot_presets` table has rows for it — a `pivotPreset` enum switching between
named positions the rigger places as guides. A preset guide is an ordinary
guide joint drawn as a locator marker.
```

Add to the **Design specs** list, first:

```
`docs/superpowers/specs/2026-09-07-movable-pivots-and-pivot-presets-design.md`
(movable pivots and pivot presets — the declaration, the preset guides, and why
a live pivot compensation cannot work),
```

Add to the **tik.trigger Tests** list:

```
- `tests/unit/test_pivot_trigger.py` — movable pivots, presets, and the
  pose-preserving switch
```

- [ ] **Step 2: Update `AI/coding_rules.md`**

In the Module Ground Rules section, after the sentence about tweak controllers, add:

```
A module may declare `pivot_controls` — `{control role: anchor guide role}` —
which gives that control a movable pivot through `rig.pivot_control(ctrl)`.
Like a tweak, a pivot controller is untiered and excluded from the control
manifest by construction: a role ending in `_pivot` is never in it.
```

- [ ] **Step 3: Verify the whole suite one last time**

Run: `$env:PYTHONPATH="src/python"; mayapy tests/unit/invoke.py`
Run: `$env:PYTHONPATH="src/python"; mayapy tests/integration/invoke.py`
Run: `$env:PYTHONPATH="src/python"; $env:TIK_TESTS_NO_MAYA="1"; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui -q`
Run: `make lint`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md AI/coding_rules.md
git commit -m "Document movable pivots and pivot presets"
```
