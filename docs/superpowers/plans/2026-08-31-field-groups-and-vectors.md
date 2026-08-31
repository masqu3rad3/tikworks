# Field Groups and Vector Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give module and action properties collapsible groups with a
declared default fold state, and Vector2/Vector3 fields so a pair or triple
occupies one row.

**Architecture:** `FieldGroup` is a frozen dataclass in `tik.core.fields`,
declared at class level and passed to each field's existing `group`
argument. `FormBuilder` swaps its single `QFormLayout` for a `QVBoxLayout`
holding an ungrouped form first and one `CollapsibleGroup` per group —
that widget already exists, themed and tested, and was simply never wired
in. `Vector2Field`/`Vector3Field` are thin subclasses of the existing
`VectorField`, which gains per-component `labels`.

**Tech Stack:** Python 3.10+, Qt (via `tik.shared.ui.Qt`), pytest under
`mayapy`. The UI suite runs Qt-only with `TIK_TESTS_NO_MAYA=1`.

**Spec:** `docs/superpowers/specs/2026-08-31-field-groups-and-vectors-design.md`

## Global Constraints

- **`tik/core` is pure Python** — no Maya, no Qt. `FieldGroup`,
  `Vector2Field` and `Vector3Field` all live there and must import neither.
  Enforced by `tests/unit/test_import_boundaries.py`.
- **Back-compat on `group`.** `Field(group="Geometry")` as a plain string
  must keep working — `tests/ui/test_form_builder.py:20` already does this,
  and that test must pass untouched.
- **`to_schema()["group"]` stays a label string.** Anything reading a schema
  today must be unaffected; the fold state rides along as a separate key.
- **`FormBuilder`'s public surface is frozen**: `widget(name)`,
  `mark_overrides(names, reference_values)`, `refresh()`, `set_target()`,
  `clear()`, and the `changed` / `error` signals keep their behaviour, and
  `_widgets` / `_labels` stay flat dicts keyed by field name.
- **No third-party dependencies.** Stdlib and Maya-bundled modules only.
- Test commands, run from the repo root:
  - unit: `PYTHONPATH=src/python mayapy tests/unit/invoke.py`
  - ui: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src/python mayapy -m pytest tests/ui -q`
  - integration: `PYTHONPATH=src/python mayapy tests/integration/invoke.py`
  - Baselines before this work: **1019 unit, 53 ui, 137 integration.**
- Commit after every task. Branch is `TW-6-Trigger-structuring`; do not
  push, reset, or checkout.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/python/tik/core/fields.py` | The field schema | Modify: `FieldGroup`, `labels`, `Vector2Field`, `Vector3Field` |
| `src/python/tik/shared/ui/fields.py` | Generated form | Modify: `_VectorEditor` bounds/captions, `FormBuilder` grouping |
| `src/python/tik/trigger/modules/arm/arm.py` | Arm module | Modify: groups, four Vector2 fields |
| `src/python/tik/trigger/modules/ribbon/ribbon.py` | Ribbon module | Modify: groups |
| `src/python/tik/trigger/modules/twist/twist.py` | Twist module | Modify: groups |
| `src/python/tik/trigger/actions/kinematics/kinematics.py` | Kinematics action | Modify: groups |
| `src/python/tik/trigger/actions/reference/reference.py` | Reference action | Modify: groups |
| `tests/unit/test_fields.py` | Field schema tests | Modify |
| `tests/ui/test_form_builder.py` | Form tests | Modify |

---

### Task 1: `FieldGroup`

**Files:**
- Modify: `src/python/tik/core/fields.py:35-115`
- Test: `tests/unit/test_fields.py`

**Interfaces:**
- Produces: `FieldGroup(label: str, collapsed: bool = False)`, a frozen
  dataclass exported from `tik.core.fields`. `Field.group` is normalised in
  `__init__` to a `FieldGroup` or `None`; a plain `str` becomes
  `FieldGroup(value, collapsed=False)`. `to_schema()` emits
  `"group"` as the label string (or `None`) and `"group_collapsed"` as a
  bool.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_fields.py`, adding `FieldGroup` to the existing
`from tik.core.fields import (...)` block:

```python
# --------------------------------------------------------------- field groups

TUNING = FieldGroup("Tuning", collapsed=True)


class Grouped(Schema):
    plain = IntField(1)
    legacy = IntField(2, group="Geometry")
    tuned = FloatField(0.5, group=TUNING)
    also_tuned = FloatField(1.5, group=TUNING)


def test_a_field_group_survives_declaration():
    field = Grouped.fields()["tuned"]
    assert isinstance(field.group, FieldGroup)
    assert field.group.label == "Tuning"
    assert field.group.collapsed is True


def test_a_plain_string_group_still_works():
    """Back-compat: callers passing a bare string keep today's behaviour."""
    field = Grouped.fields()["legacy"]
    assert isinstance(field.group, FieldGroup)
    assert field.group.label == "Geometry"
    assert field.group.collapsed is False


def test_an_ungrouped_field_has_no_group():
    assert Grouped.fields()["plain"].group is None


def test_the_same_group_object_is_shared():
    fields = Grouped.fields()
    assert fields["tuned"].group == fields["also_tuned"].group


def test_schema_keeps_group_as_a_label_string():
    """Anything reading a schema today must be unaffected."""
    schema = Grouped.schema()
    assert schema["tuned"]["group"] == "Tuning"
    assert schema["tuned"]["group_collapsed"] is True
    assert schema["legacy"]["group"] == "Geometry"
    assert schema["legacy"]["group_collapsed"] is False
    assert schema["plain"]["group"] is None
    assert schema["plain"]["group_collapsed"] is False
    json.dumps(schema)  # still serialisable


def test_field_groups_compare_by_value():
    assert FieldGroup("A") == FieldGroup("A")
    assert FieldGroup("A", collapsed=True) != FieldGroup("A")
```

`Schema.schema()` returns `{name: field.to_schema()}`
(`core/fields.py:412-414`), so these assertions match its real shape.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src/python mayapy tests/unit/invoke.py`
Expected: FAIL — `ImportError: cannot import name 'FieldGroup'`.

- [ ] **Step 3: Implement `FieldGroup`**

In `src/python/tik/core/fields.py`, after `FieldValidationError`:

```python
@dataclass(frozen=True)
class FieldGroup:
    """A titled, foldable run of fields.

    Declared once at class level and passed to each field's ``group``, so the
    label and the default fold state live in one place and a typo cannot
    silently invent a second group. Groups render in the order their first
    field is declared.
    """

    label: str
    collapsed: bool = False
```

`dataclass` is already imported at `fields.py:20`.

In `Field.__init__`, replace `self.group = group` with:

```python
        # A bare string keeps working: it is a group that starts open.
        if isinstance(group, str):
            group = FieldGroup(group)
        self.group: Optional[FieldGroup] = group
```

and widen the parameter's annotation to
`group: Optional["FieldGroup | str"] = None`.

In `to_schema()`, replace `"group": self.group,` with:

```python
            "group": self.group.label if self.group else None,
            "group_collapsed": bool(self.group and self.group.collapsed),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src/python mayapy tests/unit/invoke.py`
Expected: PASS, 1019 + the new tests.

Then run the UI suite, which will now fail:
`TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src/python mayapy -m pytest tests/ui -q`
Expected: FAIL in `test_form_builder.py` — `shared/ui/fields.py:308` calls
`field.group.upper()`, and `group` is now a `FieldGroup`. **Fix that line
in this task** so the tree is never left broken:

```python
            if field.group != current_group and field.group:
                label = QtWidgets.QLabel(field.group.label.upper())
```

Task 4 replaces this block wholesale; this is the one-line stopgap.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/core/fields.py src/python/tik/shared/ui/fields.py tests/unit/test_fields.py
git commit -m "feat(tik.core): FieldGroup carries a label and a fold state

A bare string group keeps working, so nothing existing changes; the schema
still reports the label as a string and adds the fold state beside it."
```

---

### Task 2: `Vector2Field`, `Vector3Field` and component labels

**Files:**
- Modify: `src/python/tik/core/fields.py:170-203`
- Test: `tests/unit/test_fields.py`

**Interfaces:**
- Produces: `VectorField(..., labels: Optional[Sequence[str]] = None)`, with
  `labels` in `to_schema()` beside `size`; `Vector2Field(default=(0.0, 0.0), **kwargs)`
  and `Vector3Field(default=(0.0, 0.0, 0.0), **kwargs)`, both fixing `size`
  and rejecting a caller-supplied `size`. Both keep `type_name == "vector"`,
  so `_make_widget` needs no new branch.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_fields.py`, extending the import block:

```python
# ------------------------------------------------------------- vector fields


class Vectors(Schema):
    pair = Vector2Field((-60.0, 75.0), min=-89.0, max=89.0, labels=("Lower", "Upper"))
    triple = Vector3Field((0.0, 1.0, 0.0), labels=("X", "Y", "Z"))


def test_vector2_holds_two_floats():
    thing = Vectors()
    assert thing.pair == (-60.0, 75.0)
    thing.pair = (-10, 20)
    assert thing.pair == (-10.0, 20.0)


def test_vector2_rejects_the_wrong_arity():
    thing = Vectors()
    with pytest.raises(FieldValidationError):
        thing.pair = (1.0, 2.0, 3.0)


def test_vector_bounds_apply_to_every_component():
    thing = Vectors()
    with pytest.raises(FieldValidationError):
        thing.pair = (-95.0, 10.0)
    with pytest.raises(FieldValidationError):
        thing.pair = (-10.0, 95.0)


def test_vector_size_and_labels_reach_the_schema():
    schema = Vectors.schema()
    assert schema["pair"]["type"] == "vector"
    assert schema["pair"]["size"] == 2
    assert schema["pair"]["labels"] == ["Lower", "Upper"]
    assert schema["triple"]["size"] == 3
    json.dumps(schema)


def test_labels_default_to_none():
    class Bare(Schema):
        up = Vector3Field()

    assert Bare.schema()["up"]["labels"] is None


def test_a_vector_round_trips_through_values_and_apply():
    thing = Vectors()
    thing.pair = (-30.0, 45.0)
    restored = Vectors()
    restored.apply(thing.values())
    assert restored.pair == (-30.0, 45.0)


def test_vector2_rejects_a_size_override():
    with pytest.raises(TypeError):
        Vector2Field((0.0, 0.0), size=3)
```

Confirm `Schema.apply`'s signature before writing the round-trip test —
read how `values()` and `apply()` are used elsewhere in this file and match.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src/python mayapy tests/unit/invoke.py`
Expected: FAIL — `ImportError: cannot import name 'Vector2Field'`.

- [ ] **Step 3: Implement**

In `VectorField.__init__`, add the argument and store it:

```python
    def __init__(
        self, default=(0.0, 0.0, 0.0), *, size: int = 3,
        labels: Optional[Sequence[str]] = None, **kwargs,
    ) -> None:
        self.size = size
        # Per-component captions. Presentation only -- validation never uses
        # them -- but the form has no other way to say which slot is which.
        self.labels = list(labels) if labels is not None else None
        super().__init__(tuple(float(item) for item in default), **kwargs)
```

and in its `to_schema()`:

```python
        data["labels"] = list(self.labels) if self.labels else None
```

Then, after `VectorField`:

```python
class Vector2Field(VectorField):
    """Two floats on one row -- a range, a min/max pair, a UV."""

    def __init__(self, default=(0.0, 0.0), **kwargs) -> None:
        if "size" in kwargs:
            raise TypeError("Vector2Field has a fixed size of 2.")
        super().__init__(default, size=2, **kwargs)


class Vector3Field(VectorField):
    """Three floats on one row -- a position, an axis, an RGB."""

    def __init__(self, default=(0.0, 0.0, 0.0), **kwargs) -> None:
        if "size" in kwargs:
            raise TypeError("Vector3Field has a fixed size of 3.")
        super().__init__(default, size=3, **kwargs)
```

If `tik/core/__init__.py` or `tik/trigger/core/__init__.py` re-export field
types, add `FieldGroup`, `Vector2Field` and `Vector3Field` there too —
`grep -n "VectorField" src/python/tik/core/__init__.py src/python/tik/trigger/core/__init__.py` to check.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src/python mayapy tests/unit/invoke.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/core/fields.py src/python/tik/core/__init__.py tests/unit/test_fields.py
git commit -m "feat(tik.core): Vector2Field, Vector3Field and component labels

Both are VectorField with the size fixed and a caller-supplied size
refused. `labels` is presentation metadata the form uses to say which slot
is which; validation ignores it."
```

---

### Task 3: `_VectorEditor` honours bounds and shows captions

**Files:**
- Modify: `src/python/tik/shared/ui/fields.py:15-40`, and the `"vector"`
  branch of `_make_widget` at `fields.py:362-364`
- Test: `tests/ui/test_form_builder.py`

**Interfaces:**
- Consumes: `VectorField.labels`, `.min`, `.max` (Task 2).
- Produces: `_VectorEditor(size, minimum=None, maximum=None, labels=None)`.
  `value()` and `setValue()` are unchanged, so every existing caller and
  test keeps working.

**Why:** today it hardcodes `setRange(-1e9, 1e9)` and ignores the field's
bounds, so a spinbox offers values `validate()` then rejects.

- [ ] **Step 1: Write the failing tests**

Add to `tests/ui/test_form_builder.py`, and add `Vector2Field` to its
import block plus a field to the existing `Settings` class:

```python
    span = Vector2Field((-60.0, 75.0), min=-89.0, max=89.0, labels=("Lower", "Upper"))
```

```python
def test_vector_editor_clamps_to_the_field_bounds(qapp):
    form = FormBuilder(Settings())
    editor = form.widget("span")
    assert editor.value() == (-60.0, 75.0)
    for spin in editor.spins:
        assert spin.minimum() == -89.0
        assert spin.maximum() == 89.0


def test_vector_editor_shows_a_caption_per_component(qapp):
    form = FormBuilder(Settings())
    captions = [
        widget.text()
        for widget in form.widget("span").findChildren(QtWidgets.QLabel)
    ]
    assert captions == ["Lower", "Upper"]


def test_an_unlabelled_vector_has_no_captions(qapp):
    form = FormBuilder(Settings())
    assert not form.widget("up").findChildren(QtWidgets.QLabel)


def test_vector_editing_still_reaches_the_target(qapp):
    target = Settings()
    form = FormBuilder(target)
    form.widget("span").spins[0].setValue(-20.0)
    assert target.span == (-20.0, 75.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src/python mayapy -m pytest tests/ui -q`
Expected: FAIL — the spinboxes still read ±1e9 and there are no captions.

- [ ] **Step 3: Implement**

Replace `_VectorEditor.__init__`:

```python
    def __init__(self, size: int, minimum=None, maximum=None, labels=None, parent=None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.spins: list[QtWidgets.QDoubleSpinBox] = []
        for index in range(size):
            spin = QtWidgets.QDoubleSpinBox()
            # The field's own bounds, so the widget cannot offer a value
            # validate() would then reject.
            spin.setRange(
                float(minimum) if minimum is not None else -1e9,
                float(maximum) if maximum is not None else 1e9,
            )
            spin.setDecimals(3)
            spin.valueChanged.connect(lambda _value: self.valueChanged.emit(self.value()))
            if labels:
                column = QtWidgets.QVBoxLayout()
                column.setContentsMargins(0, 0, 0, 0)
                column.setSpacing(1)
                caption = QtWidgets.QLabel(str(labels[index]))
                caption.setObjectName("FieldCaption")
                column.addWidget(caption)
                column.addWidget(spin)
                layout.addLayout(column)
            else:
                layout.addWidget(spin)
            self.spins.append(spin)
```

and the `_make_widget` branch:

```python
        elif kind == "vector":
            widget = _VectorEditor(
                getattr(field, "size", 3),
                minimum=field.min,
                maximum=field.max,
                labels=getattr(field, "labels", None),
            )
            widget.valueChanged.connect(lambda value, n=name: self._on_change(n, value))
```

`labels` is indexed by position, so it must have at least `size` entries;
`Vector2Field`/`Vector3Field` callers supply exactly that. If a shorter
sequence is a real risk, guard with `labels[index] if index < len(labels) else ""`.

- [ ] **Step 4: Run the tests to verify they pass**

Run the ui suite, then the unit suite.
Expected: PASS both.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/shared/ui/fields.py tests/ui/test_form_builder.py
git commit -m "fix(tik.shared): vector spinboxes take the field's bounds

They hardcoded +/-1e9, so the widget offered values validate() rejected.
Component captions render above each spinbox when the field names them."
```

---

### Task 4: `FormBuilder` renders collapsible groups

**Files:**
- Modify: `src/python/tik/shared/ui/fields.py:240-320`
- Test: `tests/ui/test_form_builder.py`

**Interfaces:**
- Consumes: `FieldGroup` (Task 1), `CollapsibleGroup` from
  `tik.shared.ui.collapsible` (already exists:
  `CollapsibleGroup(title, parent=None, expanded=True)`, with
  `content_layout` (a `QVBoxLayout`), `is_expanded()`, `set_expanded()` and
  a `toggled(bool)` signal).
- Produces: `FormBuilder.group_widget(label) -> CollapsibleGroup` for tests
  and callers; `_widgets` / `_labels` stay flat, keyed by field name.

- [ ] **Step 1: Write the failing tests**

Add to `tests/ui/test_form_builder.py`, importing `FieldGroup` and
`CollapsibleGroup`, and adding a second schema below `Settings`:

```python
TUNING = FieldGroup("Tuning", collapsed=True)
SHAPE = FieldGroup("Shape")


class Groupy(Schema):
    loose = IntField(1)
    also_loose = BoolField(True)
    width = FloatField(1.0, group=SHAPE)
    depth = FloatField(2.0, group=SHAPE)
    gain = FloatField(0.5, group=TUNING)
    stray = FloatField(0.0, group=SHAPE)  # non-adjacent, same group


def test_ungrouped_fields_render_before_any_group(qapp):
    form = FormBuilder(Groupy())
    order = [form._layout.itemAt(i).widget() for i in range(form._layout.count())]
    groups = [w for w in order if isinstance(w, CollapsibleGroup)]
    assert [g.title for g in groups] == ["Shape", "Tuning"]
    # the plain rows live in the first item, before any CollapsibleGroup
    assert not isinstance(order[0], CollapsibleGroup)


def test_a_collapsed_group_starts_folded(qapp):
    form = FormBuilder(Groupy())
    assert form.group_widget("Tuning").is_expanded() is False
    assert form.group_widget("Shape").is_expanded() is True


def test_non_adjacent_fields_join_one_group(qapp):
    """Declaring A, A, B, A must make two groups, not three."""
    form = FormBuilder(Groupy())
    assert len(form.findChildren(CollapsibleGroup)) == 2


def test_widgets_inside_a_collapsed_group_are_still_reachable(qapp):
    """_widgets stays flat, so every caller keeps working."""
    form = FormBuilder(Groupy())
    assert form.widget("gain").value() == 0.5
    form.mark_overrides(["gain"])
    assert "bold" in form._labels["gain"].styleSheet()


def test_editing_inside_a_group_reaches_the_target(qapp):
    target = Groupy()
    form = FormBuilder(target)
    form.widget("gain").setValue(0.75)
    assert target.gain == 0.75


def test_the_fold_state_survives_retargeting(qapp):
    form = FormBuilder(Groupy())
    form.group_widget("Tuning").set_expanded(True)
    form.set_target(Settings())
    form.set_target(Groupy())
    assert form.group_widget("Tuning").is_expanded() is True


def test_a_fresh_builder_starts_from_the_declared_default(qapp):
    assert FormBuilder(Groupy()).group_widget("Tuning").is_expanded() is False


def test_a_module_with_no_groups_is_unchanged(qapp):
    """Settings declares one string group; everything else is loose."""
    form = FormBuilder(Settings())
    assert form.widget("segments").value() == 3
    assert form.widget("local").isChecked() is False
```

`Settings` declares `group="Geometry"` on `segments`
(`test_form_builder.py:20`), so that last test also proves the string
back-compat path renders a real group. Adjust its assertions if the
existing `Settings` shape has moved.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src/python mayapy -m pytest tests/ui -q`
Expected: FAIL — `FormBuilder` has no `group_widget`, and `_layout` is a
`QFormLayout` holding rows rather than groups.

- [ ] **Step 3: Implement**

Import the widget at the top of `shared/ui/fields.py`:

```python
from tik.shared.ui.collapsible import CollapsibleGroup
```

In `__init__`, replace the single form layout:

```python
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(4)
        self._plain: Optional[QtWidgets.QFormLayout] = None
        self._groups: dict[str, CollapsibleGroup] = {}
        # Fold state per target class, so tuning a group survives clicking
        # between modules and resets when the tool restarts.
        self._collapsed: dict[str, bool] = {}
```

Add a helper and replace `set_target`:

```python
    def group_widget(self, label: str) -> CollapsibleGroup:
        """The fold for a group, by label."""
        return self._groups[label]

    def _fold_key(self, group) -> str:
        return f"{type(self._target).__name__}.{group.label}"

    def _new_form(self) -> QtWidgets.QFormLayout:
        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        return form

    def set_target(self, target: Optional[Schema]) -> None:
        self.clear()
        self._target = target
        if target is None:
            return
        visible = [
            (name, field)
            for name, field in target.fields().items()
            if not field.hidden
        ]
        # Collected rather than emitted inline, so fields sharing a group but
        # declared apart land in one fold instead of two. Order is the order
        # each group is first seen.
        order: list = []
        rows: dict = {}
        for name, field in visible:
            key = field.group.label if field.group else None
            if key not in rows:
                rows[key] = []
                order.append((key, field.group))
            rows[key].append((name, field))

        for key, group in order:
            if key is None:
                self._plain = self._new_form()
                self._layout.addLayout(self._plain)
                form = self._plain
            else:
                expanded = self._collapsed.get(
                    self._fold_key(group), not group.collapsed
                )
                fold = CollapsibleGroup(group.label, expanded=expanded)
                fold.toggled.connect(
                    lambda state, g=group: self._collapsed.__setitem__(
                        self._fold_key(g), state
                    )
                )
                holder = QtWidgets.QWidget()
                form = self._new_form()
                holder.setLayout(form)
                fold.content_layout.addWidget(holder)
                self._layout.addWidget(fold)
                self._groups[group.label] = fold
            for name, field in rows[key]:
                widget = self._make_widget(name, field)
                widget.setToolTip(field.help or "")
                self._widgets[name] = widget
                label = QtWidgets.QLabel(field.label or name)
                self._labels[name] = label
                form.addRow(label, widget)
        self._layout.addStretch(1)
        self.refresh()
```

Note the ungrouped block only appears if some field is ungrouped, and it
appears at the position of the first ungrouped field — which, for every
module in this repo, is the top.

Rewrite `clear()` to tear down the nested structure:

```python
    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
                continue
            child = item.layout()
            if child is not None:
                self._clear_layout(child)
        self._plain = None
        self._groups.clear()
        self._widgets.clear()
        self._labels.clear()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())
```

Delete the old `current_group` caption block — the `FieldCaption` label at
`fields.py:307-311` and the one-line stopgap from Task 1 both go.

- [ ] **Step 4: Run the tests until they pass**

Run the ui suite, then the unit suite, then the integration suite.
Expected: PASS all three. `tests/ui/test_guide_designer.py` and
`test_pipeline_ui.py` both host a `FormBuilder`; if either asserts on the
old flat layout, update it to the new structure rather than reverting the
design.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/shared/ui/fields.py tests/ui/test_form_builder.py
git commit -m "feat(tik.shared): FormBuilder renders collapsible field groups

Ungrouped rows first with no header, then one CollapsibleGroup per group in
declaration order -- reusing the widget that already existed, themed and
tested, and was never wired in. Fields sharing a group but declared apart
now join one fold instead of rendering the caption twice. Fold state is
remembered per target class for the session."
```

---

### Task 5: The arm's four Vector2 fields

**Files:**
- Modify: `src/python/tik/trigger/modules/arm/arm.py:55-120`
- Test: `tests/integration/trigger/test_arm_trigger.py`

**Interfaces:**
- Consumes: `Vector2Field` (Task 2).
- Produces: `auto_collar_lift_angles`, `auto_collar_lift_degrees`,
  `auto_collar_swing_angles`, `auto_collar_swing_degrees` — each a
  `Vector2Field` of `(min, max)`. The eight scalar fields are removed.
  `_lift_axis()` and `_swing_axis()` keep their signatures and still return
  a `ReachAxis`, so `build()` and every auto-collar behaviour test are
  untouched.

- [ ] **Step 1: Update the field-name tests**

In `tests/integration/trigger/test_arm_trigger.py`, update
`test_has_only_the_behaviour_fields`:

```python
    assert names == {
        "stretch", "squash", "pole_pin", "anim_spaces",
        "limb_lock", "lock_from",
        "auto_collar",
        "auto_collar_lift_angles", "auto_collar_lift_degrees",
        "auto_collar_swing_angles", "auto_collar_swing_degrees",
        "auto_collar_interpolation",
    }
```

`test_auto_collar_fields_exist`:

```python
def test_auto_collar_fields_exist():
    names = set(get_module("arm").fields())
    assert {"auto_collar", "auto_collar_lift_angles",
            "auto_collar_lift_degrees", "auto_collar_swing_angles",
            "auto_collar_interpolation"} <= names
```

`test_the_angle_fields_cannot_reach_the_drivers_ceiling`:

```python
def test_the_angle_fields_cannot_reach_the_drivers_ceiling():
    """Off-plane angles saturate at +/-90, so a wider limit never completes."""
    fields = get_module("arm").fields()
    for name in ("auto_collar_lift_angles", "auto_collar_swing_angles"):
        field = fields[name]
        assert abs(field.min) < 90.0 and abs(field.max) < 90.0, name
```

`test_validate_rejects_a_neutral_on_the_boundary`:

```python
def test_validate_rejects_a_neutral_on_the_boundary():
    """The neutral must sit *strictly* inside each axis's input range."""
    module = get_module("arm")(name="arm")
    module.auto_collar_lift_angles = (0.0, 75.0)
    assert any("lift" in problem for problem in module.validate())
    module.auto_collar_lift_angles = (-60.0, 75.0)
    module.auto_collar_swing_angles = (-45.0, 0.0)
    assert any("swing" in problem for problem in module.validate())
```

And add one round-trip test:

```python
def test_a_vector_setting_round_trips_through_a_trg(guides, tmp_path):
    arm = guides.add("arm", side="L", name="arm")
    arm.auto_collar_lift_angles = (-30.0, 50.0)
    path = guides.export(tmp_path / "hero")
    guides.clear()
    guides.import_(path)
    assert tuple(guides.find("arm", "L").auto_collar_lift_angles) == (-30.0, 50.0)
```

Put that one wherever the file's `.trg` round-trip helpers already live —
`tests/unit/test_guides_trigger.py` has the `guides` fixture and the
export/import idiom; move it there if `test_arm_trigger.py` has no
equivalent.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src/python mayapy tests/integration/invoke.py`
Expected: FAIL — the vector field names do not exist yet.

- [ ] **Step 3: Replace the eight scalars with four vectors**

In `arm.py`, swap `FloatField` for `Vector2Field` in the import from
`tik.trigger.core` (keep `FloatField` only if something else still uses it
— `grep -n "FloatField" src/python/tik/trigger/modules/arm/arm.py`), and
replace the eight declarations:

```python
    auto_collar_lift_angles = Vector2Field(
        (-60.0, 75.0), min=-89.0, max=89.0, labels=("Lower", "Upper"),
        label="Lift Angles",
        help="Arm elevation either side of the neutral guide at full "
             "falloff. Both stay inside +/-89: the driver's off-plane "
             "angles saturate at 90, so a wider limit is never reached.",
    )
    auto_collar_lift_degrees = Vector2Field(
        (-6.0, 15.0), min=-90.0, max=90.0, labels=("Lower", "Upper"),
        label="Lift Degrees",
        help="Collar rotation at each of those angles.",
    )
    auto_collar_swing_angles = Vector2Field(
        (-45.0, 60.0), min=-89.0, max=89.0, labels=("Back", "Front"),
        label="Swing Angles",
        help="Arm azimuth either side of the neutral guide at full falloff.",
    )
    auto_collar_swing_degrees = Vector2Field(
        (-6.0, 10.0), min=-90.0, max=90.0, labels=("Back", "Front"),
        label="Swing Degrees",
        help="Collar rotation at each of those angles.",
    )
```

and the two accessors:

```python
    def _lift_axis(self) -> ReachAxis:
        # Component order is (min, max), matching ReachAxis's first two and
        # last two arguments.
        return ReachAxis(
            *self.auto_collar_lift_angles, *self.auto_collar_lift_degrees
        )

    def _swing_axis(self) -> ReachAxis:
        return ReachAxis(
            *self.auto_collar_swing_angles, *self.auto_collar_swing_degrees
        )
```

- [ ] **Step 4: Run every suite**

Run all three suites. Expected: PASS. The auto-collar *behaviour* tests
(`test_bind_pose_is_exact_with_the_automation_full_on`,
`test_raising_the_arm_never_dips_the_collar`,
`test_saturates_past_the_upper_limit`) must pass **without being edited** —
they are the proof the refactor changed presentation and not behaviour.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/modules/arm/arm.py tests/
git commit -m "refactor(tik.trigger): the auto-collar limits become Vector2 fields

Eight scalars become four (min, max) pairs, each one row. The component
order matches ReachAxis's arguments, so the accessors are a splat and every
auto-collar behaviour test passes untouched."
```

---

### Task 6: Declare the groups

**Files:**
- Modify: `arm.py`, `ribbon.py`, `twist.py`, `kinematics.py`, `reference.py`
- Test: `tests/unit/test_core_trigger.py`

**Interfaces:**
- Consumes: `FieldGroup` (Task 1). No behaviour change — only `group=` on
  existing declarations.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_core_trigger.py`, matching its import idiom:

```python
def test_the_arm_groups_its_tuning_knobs():
    fields = get_module("arm").fields()
    assert fields["stretch"].group is None
    assert fields["auto_collar"].group.label == "Auto Collar"
    assert fields["auto_collar"].group.collapsed is True
    assert fields["auto_collar_lift_angles"].group.label == "Auto Collar"
    assert fields["lock_from"].group.label == "Limb Lock"
    assert fields["lock_from"].group.collapsed is False
    assert fields["anim_spaces"].group.label == "Spaces"


def test_every_declared_group_is_a_shared_object():
    """Two fields in one group must compare equal, not merely look alike."""
    fields = get_module("arm").fields()
    assert fields["auto_collar"].group == fields["auto_collar_interpolation"].group
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=src/python mayapy tests/unit/invoke.py`
Expected: FAIL — `AttributeError: 'NoneType' object has no attribute 'label'`.

- [ ] **Step 3: Declare and apply the groups**

In each file, declare the groups as module-level constants above the class
and add `group=` to the listed fields.

**`anim_spaces` is declared on the `Module` base** (`trigger/core/module.py:48`),
not on `Arm`, so its `SPACES` group is declared and applied there. That puts
every module's animation spaces in a collapsed **Spaces** group, which is the
wanted outcome — but it means `base`, `fkchain`, `ribbon` and `twist` all
gain that fold too, so their "no groups" rows above describe their *own*
fields only.

`arm.py`:

```python
LIMB_LOCK = FieldGroup("Limb Lock")
AUTO_COLLAR = FieldGroup("Auto Collar", collapsed=True)
SPACES = FieldGroup("Spaces", collapsed=True)
```

- ungrouped: `stretch`, `squash`, `pole_pin`
- `LIMB_LOCK`: `limb_lock`, `lock_from`
- `AUTO_COLLAR`: `auto_collar`, the four vectors, `auto_collar_interpolation`
- `SPACES`: `anim_spaces`

`ribbon.py`:

```python
DEFORMATION = FieldGroup("Deformation", collapsed=True)
GUIDES = FieldGroup("Guides", collapsed=True)
```

- ungrouped: `joint_count`, `mid_count`, `twist`
- `DEFORMATION`: `scaleable`, `preserve_volume`, `degree`
- `GUIDES`: `controller_size`, `spacing`

`twist.py`:

```python
EXTRACTION = FieldGroup("Extraction", collapsed=True)
GUIDES = FieldGroup("Guides", collapsed=True)
```

- ungrouped: `count`, `axis`
- `EXTRACTION`: `twist_source`, `extraction`
- `GUIDES`: `spacing`

`kinematics.py`:

```python
BUILD_OPTIONS = FieldGroup("Build Options", collapsed=True)
```

- ungrouped: `guides_file`, `rig_name`
- `BUILD_OPTIONS`: `guide_roots`, `after_build`, `auto_switchers`

`reference.py`:

```python
SCOPE = FieldGroup("Scope", collapsed=True)
```

- ungrouped: `file`, `version`
- `SCOPE`: `include`

`base.py`, `fkchain.py`, `import_asset.py` and `script.py` are left alone —
grouping two or three fields is worse than not.

- [ ] **Step 4: Run every suite**

Run all three suites. Expected: PASS, and no behaviour test anywhere needs
editing — `group=` is pure presentation.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/
git commit -m "feat(tik.trigger): group module and action properties

A field stays loose if a rigger changes it while shaping the rig; it goes
in a collapsed group if the default is good and they will only visit it to
tune. The arm now opens as three checkboxes and three folds instead of
sixteen flat rows."
```

---

### Task 7: Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-08-31-field-groups-and-vectors-design.md`

- [ ] **Step 1: Note the pattern in CLAUDE.md**

In the tik.trigger **Status** paragraph, add the new spec to the
design-specs list, and add one line to the field/schema notes:
`Fields group with FieldGroup(label, collapsed=) and render as folds;
Vector2Field/Vector3Field put a pair or triple on one row.`

- [ ] **Step 2: Mark the spec implemented**

Change `Status: designed, not implemented.` to `Status: implemented
2026-08-31.` and add a "Corrections after implementation" section recording
whatever the build proved wrong — the `Schema.schema()` shape, whether
`anim_spaces` lives on the base module, any UI test that asserted the flat
layout, and the real `CollapsibleGroup` constructor signature. Follow the
pattern at the end of `2026-08-31-auto-collar-redesign-design.md`.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/
git commit -m "docs(tik.trigger): record field groups and vector fields as built"
```

---

## Self-Review

**Spec coverage.** Section 2 (what exists) is context, not work. Section 3
`FieldGroup` → Task 1. Section 4 vectors → Tasks 2 and 5, `_VectorEditor` →
Task 3. Section 5 `FormBuilder` → Task 4, including the non-adjacent-group
join and the fold memory. Section 6 the grouping → Task 6. Section 7
migration → deliberately nothing, as specified. Section 8 testing → spread
across Tasks 1-6. Section 9 out-of-scope items are absent, as intended.

**Known risks, flagged rather than resolved:**

- `tests/ui/test_guide_designer.py`, `tests/ui/test_ui_kit.py` and
  `tests/ui/stub.py` all reference `FormBuilder` or `_layout` and may assert
  on the flat layout. Task 4 step 4 says to update them to the new
  structure, not to revert the design.
- `Schema.schema()`'s shape and `anim_spaces`' declaration site were both
  checked before writing this plan and are stated as facts above.

**Type consistency.** `FieldGroup(label, collapsed)` is constructed
identically in Tasks 1, 4 and 6. `Vector2Field(default, min, max, labels,
label, help)` is constructed identically in Tasks 2, 3 and 5.
`FormBuilder.group_widget(label)` is defined in Task 4 and used only there.
`_VectorEditor(size, minimum, maximum, labels)` is defined in Task 3 and
called only from `_make_widget`.
