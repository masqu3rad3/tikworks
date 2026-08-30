# Dynamic Animation Spaces and the Reach System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fixed manifest-declared animation spaces with rows in a properties table that each derive an input port, and move auto-collar into a generic, remappable `reach` system.

**Architecture:** Four phases. A removes the fixed-space machinery built last round. B adds `TableField` and its widget. C rebuilds spaces as settings-derived inputs, with the build pass grouping rows by `(control, mode)`. D adds the `Remap` and `AngleBetween` constructs and the `reach` system, then wires the arm to it.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), `tik.maya` wrapper, Qt (via `tik.shared.ui`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-dynamic-spaces-and-reach-design.md`

## Global Constraints

- **No third-party dependencies.** Stdlib and Maya-bundled modules only.
- **Maya 2024+.** Anything using a native math node needs a pre-2025 fallback (`NodeNames.uses_native_math_nodes` is `maya_version >= 2025`).
- **No raw `cmds` / `OpenMaya` outside `tik.maya`.** `tik/trigger/systems/` and module bodies consume `tik.maya` only.
- **The animator-opinion rule.** A `tik.maya` construct never creates a controller, names a user-facing attribute, or encodes a side convention.
- **Module ground rules** (all nine still binding): four groups per module; bind joints carry live TRS; one bind hierarchy; every output is a bind joint; every controller declares a mirror rule; no controller outside `control_grp`; no evaluation cycle; a module parents everything it creates.
- **Nothing appears that the rigger did not define** — no automatic `world` entry in any space enum.
- **`AimFrame` fails silently when the up reference is parallel to the aim.** The reach frame keeps `twist_axis="X"`.
- **Test commands:**
  - Maya: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest <path> -q`
  - UI: `set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui -q`
- **Commit after every task.** Never `--no-verify`. Never push.

---

## File Structure

| File | Responsibility | Phase |
|---|---|---|
| `src/python/tik/core/fields.py` (modify) | `Column`, `TableField` | B |
| `src/python/tik/shared/ui/fields.py` (modify) | `_TableEditor`, `kind == "table"` branch | B |
| `src/python/tik/trigger/core/manifest.py` (modify) | remove `Space` | A |
| `src/python/tik/trigger/core/module.py` (modify) | `space_controls`, `anim_spaces`, `space_rows`, `space_inputs`, `input_names(settings)` | A,C |
| `src/python/tik/trigger/core/schemas.py` (modify) | remove `ModuleInstance.spaces` | A |
| `src/python/tik/trigger/core/builder.py` (modify) | skip space inputs; rebuild the space pass | A,C |
| `src/python/tik/trigger/backends/maya/tags.py` (modify) | remove `SPACES` | A |
| `src/python/tik/trigger/backends/maya/backend.py` (modify) | remove persistence; new `connect_space` | A,C |
| `src/python/tik/trigger/guides/handler.py` (modify) | remove space accessors; revert `connections()` | A |
| `src/python/tik/trigger/guides/format.py` (modify) | remove `spaces_for` and the `kind` filter | A |
| `src/python/tik/trigger/ui/graph_view.py` (modify) | dynamic ports; `Port.space`; revert signals | A,C |
| `src/python/tik/maya/constructs/space_switch.py` (modify) | `world=False` | C |
| `src/python/tik/maya/constructs/remap.py` (create) | `Remap` | D |
| `src/python/tik/maya/constructs/angle_between.py` (create) | `AngleBetween` | D |
| `src/python/tik/trigger/systems/reach.py` (create) | `build_reach` | D |
| `src/python/tik/trigger/modules/arm/arm.py` (modify) | `space_controls`; reach fields and hookup | C,D |

---

## Phase A — Remove the Fixed-Space Machinery

### Task 1: Revert last round's spaces shape

**Files:**
- Modify: `src/python/tik/trigger/core/manifest.py`, `core/module.py`, `core/schemas.py`, `core/builder.py`, `core/__init__.py`
- Modify: `src/python/tik/trigger/backends/maya/tags.py`, `backends/maya/backend.py`
- Modify: `src/python/tik/trigger/guides/handler.py`, `guides/format.py`
- Modify: `src/python/tik/trigger/ui/graph_view.py`
- Modify: `src/python/tik/trigger/modules/arm/arm.py`
- Modify: `tests/helpers/trigger_fakes.py`
- Test: remove the space tests added last round from `tests/unit/test_core_trigger.py`, `tests/unit/test_guides_trigger.py`, `tests/integration/trigger/test_arm_trigger.py`, `tests/ui/test_pipeline_ui.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a tree with no space concept at all. `Module.spaces`, `Space`, `ModuleInstance.spaces`, `tags.SPACES`, `GuideHandle.spaces`, `GuideHandle.set_space`, `Guides.set_spaces`, `GuideFile.spaces_for`, `Port.multi` and the widened graph signals are gone.

**Background:** every space is about to become an ordinary input, so the parallel storage has no reason to exist. Removing it first keeps Phase C from having to reason about two mechanisms at once.

- [ ] **Step 1: Remove the manifest declaration**

In `src/python/tik/trigger/core/manifest.py`, delete the whole `Space` dataclass.
In `src/python/tik/trigger/core/__init__.py`, remove `Space` from the
`from .manifest import ...` line and from `__all__`.

- [ ] **Step 2: Remove the module and schema fields**

In `src/python/tik/trigger/core/module.py` delete the `spaces` class attribute,
the `space_names` and `get_space` classmethods, and `Space` from the manifest
import.

In `src/python/tik/trigger/core/schemas.py` delete the
`spaces: dict = field(default_factory=dict)` line from `ModuleInstance` and the
`spaces={...}` block from `from_dict`.

- [ ] **Step 3: Remove the builder's space pass**

In `src/python/tik/trigger/core/builder.py` delete `_connect_spaces`,
`_resolve_space_source`, the `self._connect_spaces(...)` call, and the
`spaces` field from `BuildReport`.

- [ ] **Step 4: Remove the Maya persistence**

In `backends/maya/tags.py` delete the `SPACES` line.

In `backends/maya/backend.py` delete the `SPACES = "trg_spaces"` constant, the
`spaces={...}` block in `find_instances`, the whole `set_spaces` method, the
`root.meta[SPACES] = ...` line in the legacy import path, and the
`connect_space` method.

- [ ] **Step 5: Remove the handler accessors**

In `guides/handler.py` delete the `spaces` property, `set_space`, and
`Guides.set_spaces`, and restore `connections()` to its input-only form:

```python
    def connections(self) -> list[dict]:
        found = []
        for handle in self.instances():
            for input_name, source in handle.inputs.items():
                found.append({"input": f"{handle.key}.{input_name}", "source": source})
        return found
```

In `guides/format.py` delete `spaces_for`, the `spaces` field on
`GuideInstance`, the `instance.spaces = self.spaces_for(...)` line, and the
`if item.get("kind") == "space": continue` guard in `inputs_for`.

- [ ] **Step 6: Revert the graph view**

In `ui/graph_view.py`:

- rename `Port.multi` to `Port.space` (constructor argument and attribute), keeping the colour behaviour and the tooltip suffix;
- restore the single-connection click path for every port:

```python
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != QtCore.Qt.LeftButton or event.modifiers() & QtCore.Qt.ControlModifier:
            event.ignore()
            return
        scene = self.scene()
        wires = scene.wires_for_input(self) if not self.is_output else []
        wire = wires[0] if wires else None
        if wire is not None:
            scene.pick_up_wire(wire, event.scenePos())
        else:
            scene.start_wire(self, event.scenePos())
        event.accept()
```

- revert the signals and their emits:

```python
    connect_requested = QtCore.Signal(str, str)  # input key, source key (node.port)
    disconnect_requested = QtCore.Signal(str)  # input key
```

`finish_wire` emits `self.disconnect_requested.emit(detached)` and
`self.connect_requested.emit(*target)`; `slice_wires` and `delete_selected`
emit `self.disconnect_requested.emit(wire.target_key)`.

- revert the view handlers:

```python
    def connect_input(self, input_key: str, source_key: str) -> None:
        source = self.resolve_source(source_key)
        self._apply(lambda: self.guides.connect(input_key, source))

    def disconnect_input(self, input_key: str) -> None:
        self._apply(lambda: self.guides.disconnect(input_key))
```

- delete the `for space_name, sources in handle.spaces.items():` wire loop in `rebuild`.

Keep `wires_for_input` plural, keep the `spaces=` parameter on `add_node` and
`NodeItem` (Phase C repopulates it), and keep `PORT_SPACE`.

- [ ] **Step 7: Remove the arm's declaration and the fake backend hook**

In `modules/arm/arm.py` delete the `spaces = (...)` block and `Space` from the
`tik.trigger.core` import.

In `tests/helpers/trigger_fakes.py` delete `connect_space`,
`self.space_connections`, the `spaces = (Space(...),)` on `ToyRoot`, and
`Space` from the imports.

- [ ] **Step 8: Delete the tests that covered the removed shape**

Remove these, by name:

- `tests/unit/test_core_trigger.py`: `test_space_declaration_defaults`, `test_module_space_lookup`, `test_module_has_no_spaces_by_default`, `test_instance_spaces_round_trip`, `test_instance_spaces_default_to_empty`, `test_builder_connects_spaces_after_every_module`, `test_space_sources_may_be_mutually_referential`, `test_unknown_space_source_is_skipped_with_a_warning`
- `tests/unit/test_guides_trigger.py`: `test_spaces_round_trip_through_the_scene`, `test_setting_an_unknown_space_raises`, `test_clearing_a_space_removes_it`, `test_mirror_maps_space_sources_across_sides`
- `tests/integration/trigger/test_arm_trigger.py`: `test_arm_declares_two_spaces`, `_arm_with_space`, `test_ik_space_switch_is_built`, `test_point_space_moves_without_rotating`, `test_trg_round_trip_keeps_spaces`
- `tests/ui/test_pipeline_ui.py`: `test_space_port_accepts_several_wires`, `test_connect_signal_reports_whether_the_port_is_a_space`, `test_disconnect_signal_carries_the_source_for_spaces`

In `tests/ui/test_guide_designer.py` restore the single-argument emit:

```python
    graph.disconnect_requested.emit(wire.target_key)
```

In `tests/ui/test_pipeline_ui.py` change `test_space_port_is_multi` to
`test_space_port_is_marked` asserting `.space` instead of `.multi`:

```python
def test_space_port_is_marked():
    scene = _graph_scene()
    node = scene.nodes["L_arm"]
    assert node.inputs["root"].space is False
    assert node.inputs["ik_hand"].space is True
```

- [ ] **Step 9: Run every suite**

```
set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit tests/integration -q
set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui -q
```

Expected: all pass. `git grep -n "spaces\|Space" -- src/python/tik/trigger`
should return only `space_switch`-related hits and the `space=`/`PORT_SPACE`
graph bits.

- [ ] **Step 10: Commit**

```bash
git add -A src/python/tik tests/
git commit -m "refactor(tik.trigger): remove fixed manifest-declared spaces"
```

---

## Phase B — `TableField`

### Task 2: `Column` and `TableField`

**Files:**
- Modify: `src/python/tik/core/fields.py`
- Test: `tests/unit/test_fields.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Column(name, kind="string", choices=(), choices_from="", label="")` — frozen dataclass.
  - `TableField(default=None, *, columns=(), **kwargs)` with `type_name = "table"`, `.columns`, and `coerce` returning a list of dicts.
  - `TableField.to_schema()` includes a `"columns"` key.

**Background:** the value is a list of plain dicts so it serialises into `.trg`
with no special handling. `choices_from` names an attribute on the *target
object* supplying a column's options, because the field is a class attribute and
cannot know the subclass at definition time.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_fields.py`:

```python
def test_table_field_defaults_to_empty():
    from tik.core.fields import Column, TableField

    field = TableField(columns=(Column("label"),))
    assert field.default == []
    assert field.type_name == "table"


def test_table_field_coerces_rows_to_dicts():
    from tik.core.fields import Column, Schema, TableField

    class Holder(Schema):
        rows = TableField(columns=(Column("label"), Column("mode", "choice", choices=("a", "b"))))

    holder = Holder()
    holder.rows = [{"label": "chest", "mode": "a"}]
    assert holder.rows == [{"label": "chest", "mode": "a"}]


def test_table_field_rejects_a_non_list():
    import pytest
    from tik.core.fields import Column, FieldValidationError, Schema, TableField

    class Holder(Schema):
        rows = TableField(columns=(Column("label"),))

    holder = Holder()
    with pytest.raises(FieldValidationError):
        holder.rows = "chest"


def test_table_field_rejects_unknown_columns():
    import pytest
    from tik.core.fields import Column, FieldValidationError, Schema, TableField

    class Holder(Schema):
        rows = TableField(columns=(Column("label"),))

    holder = Holder()
    with pytest.raises(FieldValidationError):
        holder.rows = [{"label": "chest", "nope": 1}]


def test_table_field_rejects_out_of_range_choices():
    import pytest
    from tik.core.fields import Column, FieldValidationError, Schema, TableField

    class Holder(Schema):
        rows = TableField(columns=(Column("mode", "choice", choices=("a", "b")),))

    holder = Holder()
    with pytest.raises(FieldValidationError):
        holder.rows = [{"mode": "z"}]


def test_table_field_fills_missing_columns():
    from tik.core.fields import Column, Schema, TableField

    class Holder(Schema):
        rows = TableField(columns=(Column("label"), Column("mode", "choice", choices=("a",))))

    holder = Holder()
    holder.rows = [{"label": "chest"}]
    assert holder.rows == [{"label": "chest", "mode": ""}]


def test_table_field_schema_carries_columns():
    from tik.core.fields import Column, TableField

    field = TableField(columns=(Column("mode", "choice", choices=("a", "b"), choices_from="modes"),))
    schema = field.to_schema()
    assert schema["type"] == "table"
    assert schema["columns"] == [
        {"name": "mode", "kind": "choice", "choices": ["a", "b"],
         "choices_from": "modes", "label": "Mode"}
    ]
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_fields.py -k table -q`
Expected: FAIL — `ImportError: cannot import name 'Column'`

- [ ] **Step 3: Implement**

Add to `src/python/tik/core/fields.py`, after `DictField`:

```python
@dataclass(frozen=True)
class Column:
    """One column of a :class:`TableField`.

    ``choices_from`` names an attribute on the *target object* supplying the
    options. A field is a class attribute and cannot know the subclass it will
    be edited on, so a column whose options vary per module resolves them at
    render time instead.
    """

    name: str
    kind: str = "string"  # "string" | "choice"
    choices: tuple = ()
    choices_from: str = ""
    label: str = ""

    def display(self) -> str:
        return self.label or self.name.replace("_", " ").title()


class TableField(Field):
    """A list of records, rendered as a table with add/remove rows.

    The value is a list of plain dicts, so it serialises with no special
    handling.
    """

    type_name = "table"

    def __init__(self, default=None, *, columns: Sequence[Column] = (), **kwargs) -> None:
        self.columns = tuple(columns)
        super().__init__([dict(row) for row in default] if default else [], **kwargs)

    def coerce(self, value):
        if value is None:
            return []
        if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
            raise FieldValidationError(self.name, value, "must be a list of rows")
        known = {column.name for column in self.columns}
        rows = []
        for row in value:
            if not isinstance(row, dict):
                raise FieldValidationError(self.name, value, "each row must be a mapping")
            unknown = set(row) - known
            if unknown:
                raise FieldValidationError(
                    self.name, value, f"unknown column(s): {sorted(unknown)}"
                )
            filled = {}
            for column in self.columns:
                entry = row.get(column.name, "")
                if column.kind == "choice" and column.choices and entry:
                    if entry not in column.choices:
                        raise FieldValidationError(
                            self.name, value,
                            f"'{column.name}' must be one of {list(column.choices)}",
                        )
                filled[column.name] = entry
            rows.append(filled)
        return rows

    def validate(self, value):
        return self.coerce(value)

    def to_schema(self) -> dict:
        schema = super().to_schema()
        schema["columns"] = [
            {
                "name": column.name,
                "kind": column.kind,
                "choices": list(column.choices),
                "choices_from": column.choices_from,
                "label": column.display(),
            }
            for column in self.columns
        ]
        return schema
```

Add `from dataclasses import dataclass` to the module's imports if it is not
already there, and add `"Column"` and `"TableField"` to `__all__` if the module
defines one.

- [ ] **Step 4: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_fields.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/core/fields.py tests/unit/test_fields.py
git commit -m "feat(tik.core): TableField for repeatable typed rows"
```

---

### Task 3: The table widget

**Files:**
- Modify: `src/python/tik/shared/ui/fields.py`
- Test: `tests/ui/test_form_builder.py` (append)

**Interfaces:**
- Consumes: `Column`, `TableField` from Task 2.
- Produces: `_TableEditor(columns, choices_resolver)` with `value()`, `setValue(rows)`, and a `valueChanged` signal; `FormBuilder._make_widget` handles `kind == "table"`.

**Background:** `_set_widget_value` already routes any widget exposing
`setValue` (`shared/ui/fields.py:301-306`), so the editor follows the
`_VectorEditor` pattern and needs no change there.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ui/test_form_builder.py`:

```python
def test_table_widget_round_trips_rows(qtbot):
    from tik.core.fields import Column, Schema, TableField
    from tik.shared.ui.fields import FormBuilder

    class Holder(Schema):
        rows = TableField(columns=(
            Column("mode", "choice", choices=("parent", "point")),
            Column("label", "string"),
        ))

    holder = Holder()
    holder.rows = [{"mode": "point", "label": "chest"}]
    builder = FormBuilder(holder)
    widget = builder.widget("rows")
    assert widget.value() == [{"mode": "point", "label": "chest"}]


def test_table_widget_adds_and_removes_rows(qtbot):
    from tik.core.fields import Column, Schema, TableField
    from tik.shared.ui.fields import FormBuilder

    class Holder(Schema):
        rows = TableField(columns=(Column("label", "string"),))

    holder = Holder()
    builder = FormBuilder(holder)
    widget = builder.widget("rows")
    widget.add_row()
    assert len(holder.rows) == 1
    widget.remove_row(0)
    assert holder.rows == []


def test_table_widget_resolves_choices_from_the_target(qtbot):
    """A column's options can come from the object being edited."""
    from tik.core.fields import Column, Schema, TableField
    from tik.shared.ui.fields import FormBuilder

    class Holder(Schema):
        controls = ("ik", "pole")
        rows = TableField(columns=(Column("control", "choice", choices_from="controls"),))

    builder = FormBuilder(Holder())
    widget = builder.widget("rows")
    widget.add_row()
    combo = widget.cell_widget(0, 0)
    assert [combo.itemText(index) for index in range(combo.count())] == ["ik", "pole"]
```

If `tests/ui/test_form_builder.py` has no `qtbot` fixture, drop the argument —
check the file's existing tests and match them.

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_form_builder.py -k table -q`
Expected: FAIL — the widget is a `QLineEdit` with no `value()`.

- [ ] **Step 3: Write the editor**

Add to `src/python/tik/shared/ui/fields.py`, after `_VectorEditor`:

```python
class _TableEditor(QtWidgets.QWidget):
    """A table of typed rows with add/remove buttons."""

    valueChanged = QtCore.Signal(object)  # noqa: N815 - matches the Qt widgets here

    def __init__(self, columns, choices_resolver=None, parent=None) -> None:
        super().__init__(parent)
        self.columns = list(columns)
        self._resolve = choices_resolver or (lambda _name: ())
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.table = QtWidgets.QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels([column.display() for column in self.columns])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        self.add_button = QtWidgets.QPushButton("+")
        self.remove_button = QtWidgets.QPushButton("-")
        for button in (self.add_button, self.remove_button):
            button.setFixedWidth(24)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.add_button.clicked.connect(lambda: self.add_row())
        self.remove_button.clicked.connect(self._remove_selected)

    # ------------------------------------------------------------- rows
    def _choices(self, column):
        if column.choices_from:
            return list(self._resolve(column.choices_from))
        return list(column.choices)

    def _make_cell(self, column, value):
        if column.kind == "choice":
            widget = QtWidgets.QComboBox()
            widget.addItems([str(item) for item in self._choices(column)])
            if value:
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)
            widget.currentIndexChanged.connect(self._emit)
            return widget
        widget = QtWidgets.QLineEdit(str(value or ""))
        widget.editingFinished.connect(self._emit)
        return widget

    def add_row(self, row: Optional[dict] = None) -> None:
        row = row or {}
        index = self.table.rowCount()
        self.table.insertRow(index)
        for column_index, column in enumerate(self.columns):
            self.table.setCellWidget(
                index, column_index, self._make_cell(column, row.get(column.name, ""))
            )
        self._emit()

    def remove_row(self, index: int) -> None:
        if 0 <= index < self.table.rowCount():
            self.table.removeRow(index)
            self._emit()

    def _remove_selected(self) -> None:
        rows = sorted({item.row() for item in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            rows = [self.table.rowCount() - 1] if self.table.rowCount() else []
        for index in rows:
            if index >= 0:
                self.table.removeRow(index)
        self._emit()

    def cell_widget(self, row: int, column: int):
        return self.table.cellWidget(row, column)

    # ------------------------------------------------------------ value
    def value(self) -> list:
        rows = []
        for row_index in range(self.table.rowCount()):
            row = {}
            for column_index, column in enumerate(self.columns):
                widget = self.table.cellWidget(row_index, column_index)
                if isinstance(widget, QtWidgets.QComboBox):
                    row[column.name] = widget.currentText()
                else:
                    row[column.name] = widget.text()
            rows.append(row)
        return rows

    def setValue(self, rows) -> None:  # noqa: N802 - matches the Qt widgets here
        self.table.setRowCount(0)
        for row in rows or []:
            index = self.table.rowCount()
            self.table.insertRow(index)
            for column_index, column in enumerate(self.columns):
                self.table.setCellWidget(
                    index, column_index, self._make_cell(column, row.get(column.name, ""))
                )

    def _emit(self, *_args) -> None:
        self.valueChanged.emit(self.value())
```

- [ ] **Step 4: Wire it into the builder**

In `FormBuilder._make_widget`, add before the final `else`:

```python
        elif kind == "table":
            widget = _TableEditor(
                getattr(field, "columns", ()),
                choices_resolver=lambda attr: getattr(self._target, attr, ()),
            )
            widget.valueChanged.connect(lambda value, n=name: self._on_change(n, value))
```

- [ ] **Step 5: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/shared/ui/fields.py tests/ui/test_form_builder.py
git commit -m "feat(tik.shared): table editor widget for TableField"
```

---

## Phase C — Spaces as Settings-Derived Inputs

### Task 4: `space_controls`, `anim_spaces` and settings-aware inputs

**Files:**
- Modify: `src/python/tik/trigger/core/module.py`
- Modify: `src/python/tik/trigger/modules/arm/arm.py`
- Test: `tests/unit/test_core_trigger.py` (append)

**Interfaces:**
- Consumes: `Column`, `TableField` from Task 2.
- Produces:
  - `Module.space_controls: tuple[str, ...] = ()`
  - `Module.anim_spaces` — a `TableField` on the base class.
  - `Module.space_rows(settings=None) -> list[dict]` — validated rows.
  - `Module.space_inputs(settings=None) -> list[Input]` — `Input(f"{control}_{label}", kind="space")` per row.
  - `Module.input_names(settings=None) -> list[str]` — declared plus space names.
  - `Module.validate()` reports bad rows.
  - `Arm.space_controls = ("ik", "pole")`.

**Background:** `output_names(settings)` is already settings-aware — it is how
`fkchain` publishes one output per segment. Inputs follow that precedent.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_core_trigger.py`:

```python
# ------------------------------------------------------------ anim spaces
def _spaced_module():
    from tik.trigger.core import Module

    class Spaced(Module):
        space_controls = ("ik", "pole")

    return Spaced


def test_space_rows_are_empty_by_default():
    assert _spaced_module().space_rows({}) == []


def test_space_inputs_derive_one_port_per_row():
    module_cls = _spaced_module()
    settings = {"anim_spaces": [
        {"control": "ik", "mode": "parent", "label": "chest"},
        {"control": "pole", "mode": "point", "label": "chest"},
    ]}
    assert [item.name for item in module_cls.space_inputs(settings)] == [
        "ik_chest", "pole_chest"
    ]
    assert all(item.kind == "space" for item in module_cls.space_inputs(settings))
    assert all(item.optional for item in module_cls.space_inputs(settings))


def test_input_names_include_spaces():
    module_cls = _spaced_module()
    settings = {"anim_spaces": [{"control": "ik", "mode": "parent", "label": "chest"}]}
    assert module_cls.input_names(settings) == ["root", "ik_chest"]
    assert module_cls.input_names({}) == ["root"]


def test_validate_rejects_an_empty_label():
    module_cls = _spaced_module()
    module = module_cls(name="x")
    module.anim_spaces = [{"control": "ik", "mode": "parent", "label": ""}]
    assert any("label" in problem for problem in module.validate())


def test_validate_rejects_an_unknown_control():
    module_cls = _spaced_module()
    module = module_cls(name="x")
    module.anim_spaces = [{"control": "ghost", "mode": "parent", "label": "chest"}]
    assert any("ghost" in problem for problem in module.validate())


def test_validate_rejects_duplicate_rows():
    """(control, label) is the derived port name; a clash would drop a wire."""
    module_cls = _spaced_module()
    module = module_cls(name="x")
    module.anim_spaces = [
        {"control": "ik", "mode": "parent", "label": "chest"},
        {"control": "ik", "mode": "orient", "label": "chest"},
    ]
    assert any("ik_chest" in problem for problem in module.validate())
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_core_trigger.py -k space -q`
Expected: FAIL — `AttributeError: type object 'Spaced' has no attribute 'space_rows'`

- [ ] **Step 3: Implement on `Module`**

In `src/python/tik/trigger/core/module.py`, import the field types:

```python
from tik.core.fields import Column, Schema, TableField
```

(keep the existing `Schema` import; add the other two).

Add the class attributes beside `inputs`:

```python
    space_controls: tuple[str, ...] = ()  # controller roles that accept spaces
    anim_spaces = TableField(
        [],
        label="Anim Spaces",
        help="Each row adds one animation space and one input port.",
        columns=(
            Column("control", "choice", choices_from="space_controls"),
            Column("mode", "choice", choices=("parent", "point", "orient")),
            Column("label", "string"),
        ),
    )
```

Replace `input_names` and add the two helpers:

```python
    @classmethod
    def space_rows(cls, settings=None) -> list[dict]:
        """The anim-space rows from ``settings`` (or the field default)."""
        if settings is None:
            return list(cls.anim_spaces.default)
        return [dict(row) for row in (settings.get("anim_spaces") or [])]

    @classmethod
    def space_inputs(cls, settings=None) -> list[Input]:
        """One optional, space-kind Input per row: ``<control>_<label>``."""
        found = []
        for row in cls.space_rows(settings):
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            found.append(Input(f"{control}_{label}", kind="space", optional=True))
        return found

    @classmethod
    def input_names(cls, settings=None) -> list[str]:
        return [item.name for item in cls.inputs] + [
            item.name for item in cls.space_inputs(settings)
        ]
```

Extend `validate`:

```python
    def validate(self) -> list[str]:
        """Return problems that prevent building (empty list = ok)."""
        pairs = self.guide_pairs or self.expected_guides()
        problems = list(self.guides.validate(pairs))
        problems.extend(self._validate_spaces())
        return problems

    def _validate_spaces(self) -> list[str]:
        """Anim-space rows must derive unique, well-formed port names."""
        problems, seen = [], set()
        for index, row in enumerate(self.anim_spaces):
            control, label = row.get("control", ""), row.get("label", "")
            if not label:
                problems.append(f"anim space row {index + 1}: label is required")
                continue
            if control not in self.space_controls:
                problems.append(
                    f"anim space row {index + 1}: '{control}' is not one of "
                    f"{list(self.space_controls)}"
                )
                continue
            name = f"{control}_{label}"
            if name in seen:
                problems.append(f"anim space row {index + 1}: '{name}' is already defined")
            seen.add(name)
        return problems
```

- [ ] **Step 4: Declare the arm's controls**

In `src/python/tik/trigger/modules/arm/arm.py`, add beside `outputs`:

```python
    space_controls = ("ik", "pole")
```

- [ ] **Step 5: Fix the settings-less callers**

Run `git grep -n "input_names()" -- src` and pass settings where a handle or
instance is available. Known sites: `guides/handler.py` (`GuideHandle.input_names`
returns `self.module_class.input_names(self.settings)`) and
`ui/graph_view.py` (Task 6 covers it).

- [ ] **Step 6: Run the suites**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit tests/integration -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger tests/unit/test_core_trigger.py
git commit -m "feat(tik.trigger): anim-space rows derive settings-aware input ports"
```

---

### Task 5: The builder skips space inputs and groups them

**Files:**
- Modify: `src/python/tik/trigger/core/builder.py`
- Modify: `tests/helpers/trigger_fakes.py`
- Test: `tests/unit/test_core_trigger.py` (append)

**Interfaces:**
- Consumes: `Module.space_inputs`, `Module.space_rows` from Task 4.
- Produces:
  - `BuildReport.spaces: list[tuple[str, str]]` — `("L_arm.ik_chest", "body.root")`.
  - `Builder._connect_spaces(instances, report, by_key)` — groups space rows by `(control, mode)` in row order and calls `backend.connect_space(ctx, control, mode, targets, labels)` once per group.
  - `FakeBackend.connect_space(ctx, control, mode, targets, labels)` recording into `self.space_connections`.

**Background — three skips, each a real defect if missed:**

| Site | Why |
|---|---|
| `_connect_one` | A space input has no `ctx.attach()` target and would raise "module did not call ctx.attach()". |
| `order_by_connections` | **The one that matters.** Space connections are legitimately mutually referential; leaving them in the topological sort makes a normal rig a false cycle. |
| `_bind_parent_for` | Spaces are never primary; the guard keeps it that way. |

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_core_trigger.py`:

```python
def _with_space_rows(instance, rows):
    instance.settings["anim_spaces"] = rows
    return instance


def test_space_inputs_do_not_feed_build_order():
    """An arm in head space while the head is in arm space is a normal rig."""
    backend = FakeBackend()
    first = backend.create_guides(ToyRoot(name="a"))
    second = backend.create_guides(ToyRoot(name="b"))
    _with_space_rows(first, [{"control": "root", "mode": "parent", "label": "b"}])
    _with_space_rows(second, [{"control": "root", "mode": "parent", "label": "a"}])
    first.inputs = {"root_b": "b.root"}
    second.inputs = {"root_a": "a.root"}
    report = Builder(backend).build(rig_name="rig", afterlife="keep")
    assert report.count == 2


def test_space_connections_are_grouped_by_control_and_mode():
    backend = FakeBackend()
    body = backend.create_guides(ToyRoot(name="body"))
    head = backend.create_guides(ToyRoot(name="head"))
    arm = backend.create_guides(ToyRoot(name="arm"))
    _with_space_rows(arm, [
        {"control": "root", "mode": "parent", "label": "body"},
        {"control": "root", "mode": "parent", "label": "head"},
    ])
    arm.inputs = {"root_body": "body.root", "root_head": "head.root"}
    Builder(backend).build(rig_name="rig", afterlife="keep")
    assert backend.space_connections == [("arm", "root", "parent", ["body", "head"])]


def test_row_order_is_enum_order():
    backend = FakeBackend()
    backend.create_guides(ToyRoot(name="body"))
    backend.create_guides(ToyRoot(name="head"))
    arm = backend.create_guides(ToyRoot(name="arm"))
    _with_space_rows(arm, [
        {"control": "root", "mode": "parent", "label": "head"},
        {"control": "root", "mode": "parent", "label": "body"},
    ])
    arm.inputs = {"root_body": "body.root", "root_head": "head.root"}
    Builder(backend).build(rig_name="rig", afterlife="keep")
    assert backend.space_connections[0][3] == ["head", "body"]


def test_an_unconnected_space_row_is_skipped():
    backend = FakeBackend()
    arm = backend.create_guides(ToyRoot(name="arm"))
    _with_space_rows(arm, [{"control": "root", "mode": "parent", "label": "ghost"}])
    report = Builder(backend).build(rig_name="rig", afterlife="keep")
    assert backend.space_connections == []
    assert report.spaces == []
```

`ToyRoot` needs `space_controls`. In `tests/helpers/trigger_fakes.py` add to
`ToyRoot`:

```python
    space_controls = ("root",)
```

and make its `build` register a controller so the Maya backend has a role to
find (it already calls `ctx.controller("root")`).

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_core_trigger.py -k "space_inputs_do_not or grouped or row_order or unconnected_space" -q`
Expected: FAIL — `AttributeError: 'FakeBackend' object has no attribute 'space_connections'`

- [ ] **Step 3: Add the fake backend hook**

In `tests/helpers/trigger_fakes.py`, add to `FakeBackend.__init__`:

```python
        self.space_connections: list = []
```

and the method:

```python
    def connect_space(self, ctx, control, mode, targets, labels):
        self.space_connections.append((ctx.instance.key, control, mode, list(labels)))
```

- [ ] **Step 4: Skip space inputs in the three sites**

In `src/python/tik/trigger/core/builder.py`, add a helper near `split_source`:

```python
def space_input_names(module_cls, settings) -> set:
    """Names of the inputs derived from anim-space rows."""
    return {item.name for item in module_cls.space_inputs(settings)}
```

In `build()`, filter the ordering callback:

```python
            def structural_inputs(item):
                module_cls = registry.get_module(item.module_type)
                skip = space_input_names(module_cls, item.settings)
                return {
                    name: source
                    for name, source in derive_inputs(item, by_id).items()
                    if name not in skip
                }

            # Space connections are legitimately mutually referential - an arm in
            # head space while the head sits in arm space is a normal rig - so
            # they must not reach the topological sort.
            instances = order_by_connections(instances, structural_inputs)
```

`_connect_one` already iterates `module_cls.inputs`, and space inputs are
derived rather than added to that tuple, so it excludes them already. Read the
loop header to confirm it says `for declared in module_cls.inputs:` and change
nothing.

In `_bind_parent_for`, guard explicitly after resolving the primary:

```python
        if primary is None or primary.kind == "space":
            return None
```

- [ ] **Step 5: Rebuild the space pass**

Add to `Builder`, after `_connect_one`:

```python
    def _connect_spaces(self, instances, report: BuildReport, by_key: dict) -> None:
        """Build one space switch per (control, mode), after all modules exist.

        Deliberately not part of ``order_by_connections``: a space switch does
        not affect the bind hierarchy, and spaces are legitimately mutually
        referential, which would be a false cycle in the topological sort.
        """
        by_id = {instance.instance_id: instance for instance in instances}
        for instance in instances:
            module_cls = registry.get_module(instance.module_type)
            ctx = report.contexts.get(instance.instance_id)
            if ctx is None:
                continue
            inputs = derive_inputs(instance, by_id)
            groups: dict = {}
            for row in module_cls.space_rows(instance.settings):
                control, mode = row.get("control", ""), row.get("mode", "parent")
                label = row.get("label", "")
                if not control or not label:
                    continue
                source = inputs.get(f"{control}_{label}")
                if not source:
                    self.events.log(
                        f"{instance.key}.{control}_{label}: no source connected; skipped.",
                        level="warning",
                    )
                    continue
                node = self._resolve_space_source(source, by_key, report)
                if node is None:
                    self.events.log(
                        f"{instance.key}.{control}_{label}: source '{source}' was not "
                        f"found; skipped.",
                        level="warning",
                    )
                    continue
                groups.setdefault((control, mode), ([], [])) 
                groups[(control, mode)][0].append(node)
                groups[(control, mode)][1].append(label)
                report.spaces.append((f"{instance.key}.{control}_{label}", source))
            for (control, mode), (targets, labels) in groups.items():
                self.backend.connect_space(ctx, control, mode, targets, labels)

    def _resolve_space_source(self, source: str, by_key: dict, report: BuildReport):
        """Return the node for a space source, or None when it cannot be found."""
        key, output = split_source(source)
        if key is not None and key in by_key:
            producer_ctx = report.contexts.get(by_key[key].instance_id)
            if producer_ctx is None:
                return None
            return producer_ctx.outputs.get(output)
        return self.backend.scene_node(source)
```

Add `spaces: list[tuple[str, str]] = field(default_factory=list)` back to
`BuildReport`, and call the pass inside the `undo_chunk` block before
`afterlife`:

```python
            self._connect_spaces(instances, report, by_key)
```

- [ ] **Step 6: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/core/builder.py tests/helpers/trigger_fakes.py tests/unit/test_core_trigger.py
git commit -m "feat(tik.trigger): group anim-space inputs into switches in a post-build pass"
```

---

### Task 6: `SpaceSwitch(world=False)` and the Maya backend

**Files:**
- Modify: `src/python/tik/maya/constructs/space_switch.py`
- Modify: `src/python/tik/trigger/backends/maya/backend.py`
- Test: `tests/unit/test_space_switch.py` (append), `tests/unit/test_maya_backend_trigger.py` (append)

**Interfaces:**
- Consumes: `ctx.controller_by_role` (already present).
- Produces:
  - `SpaceSwitch.create(..., world: bool = True)`.
  - `MayaBackend.connect_space(ctx, control, mode, targets, labels)` building one switch named `f"{mode}Switch"` on the controller with that role.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_space_switch.py`:

```python
def test_world_can_be_excluded():
    """Nothing should appear in the enum that was not defined."""
    node = tm.Transform.create(name="switched")
    first = tm.Transform.create(name="target_a")
    second = tm.Transform.create(name="target_b")
    switch = tm.SpaceSwitch.create(
        node, [first, second], labels=["a", "b"], world=False, name="noworld"
    )
    assert switch.labels == ["a", "b"]


def test_world_is_included_by_default():
    node = tm.Transform.create(name="switched_default")
    target = tm.Transform.create(name="target_default")
    switch = tm.SpaceSwitch.create(node, [target], labels=["a"], name="withworld")
    assert switch.labels == ["world", "a"]
```

Append to `tests/unit/test_maya_backend_trigger.py`:

```python
def test_connect_space_builds_a_named_switch(backend):
    ctx = _built(backend)
    main = ctx.controller("hand", mirror="world")
    first = tm.Transform.create(name="space_a")
    second = tm.Transform.create(name="space_b")
    backend.connect_space(ctx, "hand", "parent", [first, second], ["chest", "head"])
    assert main.transform.has_attr("parentSwitch")
    listed = cmds.attributeQuery(
        "parentSwitch", node=main.transform.long_name, listEnum=True
    )[0]
    assert listed.split(":") == ["chest", "head"]
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_space_switch.py tests/unit/test_maya_backend_trigger.py -k "world or connect_space" -q`
Expected: FAIL — `TypeError: create() got an unexpected keyword argument 'world'`

- [ ] **Step 3: Add the `world` flag**

In `src/python/tik/maya/constructs/space_switch.py`, add `world: bool = True` to
`create`'s keyword-only arguments, document it as:

```
            world: Prepend a ``world`` entry at index 0. Set False when only the
                given spaces should appear.
```

and replace the two construction lines:

```python
        entries = [WORLD, *spaces] if world else list(spaces)
        names = ["world", *labels] if world else list(labels)
        attr = attribute.add_enum(control, attr_name, names, default=default)
        switch = MatrixSwitch.create(
            entries,
            offset,
            control=attr,
            maintain_offset=True,
            name=name,
            **_MODES[mode],
        )
```

- [ ] **Step 4: Implement `connect_space`**

In `src/python/tik/trigger/backends/maya/backend.py`, beside `connect`:

```python
    def connect_space(self, ctx: MayaBuildContext, control, mode, targets, labels) -> None:
        """Build one space switch on the controller with role ``control``.

        ``world=False``: nothing appears in the enum that the rigger did not
        define.
        """
        controller = ctx.controller_by_role(control)
        if controller is None:
            raise AttachError(
                f"{ctx.instance.key}: no controller with role '{control}'.",
                instance_id=ctx.instance.instance_id,
                module_type=ctx.module.module_type,
            )
        tm.SpaceSwitch.create(
            controller.transform,
            targets,
            attr_name=f"{mode}Switch",
            mode=mode,
            labels=list(labels),
            world=False,
            name=ctx.name(control, mode),
        )
```

- [ ] **Step 5: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/maya/constructs/space_switch.py src/python/tik/trigger/backends/maya/backend.py tests/unit
git commit -m "feat(tik.maya): SpaceSwitch world flag; backend builds per-mode switches"
```

---

### Task 7: Dynamic ports in the graph view

**Files:**
- Modify: `src/python/tik/trigger/ui/graph_view.py`
- Test: `tests/ui/test_pipeline_ui.py` (append)

**Interfaces:**
- Consumes: `Module.input_names(settings)`, `Module.space_inputs(settings)`.
- Produces: `rebuild` builds ports from the instance's settings; space ports carry `Port.space = True`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_pipeline_ui.py`:

```python
def test_space_rows_become_ports():
    from tik.core.fields import Column, TableField
    from tik.trigger.core import Input, Module

    class Spaced(Module):
        inputs = (Input("root", primary=True),)
        space_controls = ("ik",)

    settings = {"anim_spaces": [{"control": "ik", "mode": "parent", "label": "chest"}]}
    assert Spaced.input_names(settings) == ["root", "ik_chest"]
    assert [item.name for item in Spaced.space_inputs(settings)] == ["ik_chest"]
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_pipeline_ui.py -k space_rows -q`
Expected: PASS if Task 4 is done — this test guards the contract the view relies
on. If it fails, Task 4 is incomplete; fix that first.

- [ ] **Step 3: Use settings in `rebuild`**

In `ui/graph_view.py`'s `rebuild`, replace the node creation block:

```python
            space_names = [item.name for item in module_cls.space_inputs(handle.settings)]
            rows = max(
                len(module_cls.inputs) + len(space_names), len(handle.outputs), 1
            )
            pos = free_pos(handle.key, HEADER + rows * ROW + 8)
            primary = module_cls.primary_input()
            self.graph.add_node(
                handle.key, handle.key, module_cls.display_label(),
                [item.name for item in module_cls.inputs], list(handle.outputs),
                theme.SIDE.get(handle.side.value, theme.SIDE["C"]),
                primary_input=primary.name if primary else None, pos=pos,
                mode=collapse.get(handle.key, MODE_FULL), spaces=space_names,
            )
```

and in `_auto_positions`:

```python
            rows = max(
                len(handle.module_class.inputs)
                + len(handle.module_class.space_inputs(handle.settings)),
                len(handle.outputs),
                1,
            )
```

- [ ] **Step 4: Run the UI suite**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/ui/graph_view.py tests/ui/test_pipeline_ui.py
git commit -m "feat(tik.trigger): graph ports follow the anim-space rows"
```

---

### Task 8: The arm end to end

**Files:**
- Test: `tests/integration/trigger/test_arm_trigger.py` (append)

**Interfaces:**
- Consumes: everything in Phase C.
- Produces: no source changes; the end-to-end guarantees.

- [ ] **Step 1: Write the tests**

Append to `tests/integration/trigger/test_arm_trigger.py`:

```python
# -------------------------------------------------------------------- spaces
def _arm_with_spaces(backend, rows, wires):
    body = backend.create_guides(get_module("base")(name="body"))
    cmds.xform(
        backend.guide_node(body.instance_id, "root").long_name, ws=True, t=(0, 15, 0)
    )
    arm = backend.create_guides(
        get_module("arm")(name="arm", side="L", settings={"anim_spaces": rows}),
        parent=ParentRef(body.instance_id, "root"),
    )
    inputs = dict(backend.find_instances([arm.instance_id])[0].inputs)
    inputs.update(wires)
    backend.set_inputs(arm.instance_id, inputs)
    report = Builder(backend).build(rig_name="hero", afterlife="keep")
    return report, report.contexts[arm.instance_id]


def test_arm_declares_its_space_controls():
    assert get_module("arm").space_controls == ("ik", "pole")


def test_two_rows_on_one_control_make_one_enum(backend):
    rows = [
        {"control": "ik", "mode": "parent", "label": "body"},
        {"control": "ik", "mode": "parent", "label": "root"},
    ]
    wires = {"ik_body": "body.root", "ik_root": "body.root"}
    _report, ctx = _arm_with_spaces(backend, rows, wires)
    control = _ik_control(ctx)
    assert control.has_attr("parentSwitch")
    listed = cmds.attributeQuery(
        "parentSwitch", node=control.long_name, listEnum=True
    )[0]
    assert listed.split(":") == ["body", "root"]


def test_no_world_entry_is_added(backend):
    """Nothing appears that the rigger did not define."""
    rows = [{"control": "ik", "mode": "parent", "label": "body"}]
    _report, ctx = _arm_with_spaces(backend, rows, {"ik_body": "body.root"})
    listed = cmds.attributeQuery(
        "parentSwitch", node=_ik_control(ctx).long_name, listEnum=True
    )[0]
    assert "world" not in listed.split(":")


def test_modes_build_separate_switches(backend):
    """Two modes on one control are two switches, so the labels must differ:
    (control, label) is the derived port name."""
    rows = [
        {"control": "ik", "mode": "parent", "label": "body"},
        {"control": "ik", "mode": "orient", "label": "chest"},
    ]
    wires = {"ik_body": "body.root", "ik_chest": "body.root"}
    _report, ctx = _arm_with_spaces(backend, rows, wires)
    control = _ik_control(ctx)
    assert control.has_attr("parentSwitch")
    assert control.has_attr("orientSwitch")


def test_trg_round_trip_keeps_rows_and_wires(backend, tmp_path):
    from tik.trigger.guides import Guides

    guides = Guides(backend)
    body = guides.add("base", name="body")
    arm = guides.add(
        "arm", side="L", name="arm", parent=body,
        anim_spaces=[{"control": "ik", "mode": "parent", "label": "body"}],
    )
    guides.connect("L_arm.ik_body", "body.root")

    path = guides.export(tmp_path / "spaces")
    guides.clear()
    guides.import_(path)

    restored = guides.find("arm", "L")
    assert restored.anim_spaces == [
        {"control": "ik", "mode": "parent", "label": "body"}
    ]
    assert restored.inputs.get("ik_body") == "body.root"
```

- [ ] **Step 2: Run the suite**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/trigger/test_arm_trigger.py
git commit -m "test(tik.trigger): arm anim spaces end to end"
```

---

## Phase D — The Reach System

### Task 9: `Remap` construct

**Files:**
- Create: `src/python/tik/maya/constructs/remap.py`
- Modify: `src/python/tik/maya/constructs/__init__.py`, `src/python/tik/maya/__init__.py`
- Test: `tests/unit/test_remap.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `Remap.create(input, *, input_min, input_max, output_min=0.0, output_max=1.0, interpolation="smooth", name=None)` with `.output` (a `Plug`), `.node`, `.delete()`. Accepts `Plug` or float for every bound.

**Background:** `remapValue`'s ramp interpolation enum is `none=0, linear=1,
smooth=2, spline=3`, which matches the three offered options exactly.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_remap.py`:

```python
"""Tests for the Remap construct."""

from maya import cmds

import tik.maya as tm


def _driver(value=0.0):
    node = tm.Transform.create(name="remap_driver")
    return tm.attribute.add_float(node, "angle", default=value)


def test_below_the_input_minimum_is_the_output_minimum():
    plug = _driver(-10.0)
    remap = tm.Remap.create(plug, input_min=0.0, input_max=90.0, name="r")
    assert abs(remap.output.value) < 1e-4


def test_above_the_input_maximum_is_the_output_maximum():
    plug = _driver(180.0)
    remap = tm.Remap.create(plug, input_min=0.0, input_max=90.0, name="r_high")
    assert abs(remap.output.value - 1.0) < 1e-4


def test_output_range_is_honoured():
    plug = _driver(90.0)
    remap = tm.Remap.create(
        plug, input_min=0.0, input_max=90.0, output_min=2.0, output_max=8.0, name="r_out"
    )
    assert abs(remap.output.value - 8.0) < 1e-4


def test_linear_midpoint_is_exactly_half():
    plug = _driver(45.0)
    remap = tm.Remap.create(
        plug, input_min=0.0, input_max=90.0, interpolation="linear", name="r_lin"
    )
    assert abs(remap.output.value - 0.5) < 1e-3


def test_the_three_interpolations_agree_at_the_ends_and_differ_between():
    """The only thing that proves the choice reached remapValue."""
    values = {}
    for index, kind in enumerate(("linear", "smooth", "spline")):
        plug = _driver(22.5)
        remap = tm.Remap.create(
            plug, input_min=0.0, input_max=90.0, interpolation=kind, name=f"r_{index}"
        )
        values[kind] = remap.output.value
        plug.value = 0.0
        assert abs(remap.output.value) < 1e-4
        plug.value = 90.0
        assert abs(remap.output.value - 1.0) < 1e-4
    assert abs(values["linear"] - values["smooth"]) > 1e-3


def test_rejects_an_unknown_interpolation():
    import pytest

    plug = _driver()
    with pytest.raises(ValueError, match="interpolation"):
        tm.Remap.create(plug, input_min=0.0, input_max=1.0, interpolation="wobble")


def test_delete_removes_the_node():
    plug = _driver()
    remap = tm.Remap.create(plug, input_min=0.0, input_max=1.0, name="r_del")
    name = remap.node.long_name
    remap.delete()
    assert not cmds.objExists(name)
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_remap.py -q`
Expected: FAIL — `AttributeError: module 'tik.maya' has no attribute 'Remap'`

- [ ] **Step 3: Write the construct**

Create `src/python/tik/maya/constructs/remap.py`:

```python
"""Remap a scalar from one range to another, with a choice of curve.

Wraps ``remapValue``, whose ramp interpolation enum is exactly
``none`` / ``linear`` / ``smooth`` / ``spline``.
"""

from __future__ import annotations

from typing import Optional

from maya import cmds

from ..core.decorators import undo
from ..core.plug import Plug
from ..core.scene import create_node

INTERPOLATIONS = {"none": 0, "linear": 1, "smooth": 2, "spline": 3}


class Remap:
    """Wrapper for a ``remapValue`` node."""

    def __init__(self, node) -> None:
        self.node = node

    @classmethod
    @undo
    def create(
        cls,
        value,
        *,
        input_min,
        input_max,
        output_min=0.0,
        output_max=1.0,
        interpolation: str = "smooth",
        name: Optional[str] = None,
    ) -> "Remap":
        """Remap ``value`` from the input range onto the output range.

        Args:
            value: Plug or float driving the remap.
            input_min: Plug or float; values at or below map to ``output_min``.
            input_max: Plug or float; values at or above map to ``output_max``.
            output_min: Plug or float.
            output_max: Plug or float.
            interpolation: ``none``, ``linear``, ``smooth`` or ``spline``.
            name: Prefix for the created node.

        Returns:
            The construct.
        """
        if interpolation not in INTERPOLATIONS:
            raise ValueError(
                f"Unknown interpolation '{interpolation}'. Use one of "
                f"{sorted(INTERPOLATIONS)}."
            )
        node = create_node("remapValue", name=f"{name or 'remap'}_remapValue")
        for attr, item in (
            ("inputValue", value),
            ("inputMin", input_min),
            ("inputMax", input_max),
            ("outputMin", output_min),
            ("outputMax", output_max),
        ):
            if isinstance(item, Plug):
                item >> node[attr]
            else:
                node[attr].value = float(item)
        # The ramp's two default points carry the curve shape.
        for index, position in ((0, 0.0), (1, 1.0)):
            node[f"value[{index}].value_Position"].value = position
            node[f"value[{index}].value_FloatValue"].value = position
            node[f"value[{index}].value_Interp"].value = INTERPOLATIONS[interpolation]
        return cls(node)

    @property
    def output(self) -> Plug:
        """The remapped scalar."""
        return self.node["outValue"]

    @undo
    def delete(self) -> None:
        """Delete the node."""
        if self.node.exists():
            cmds.delete(self.node.long_name)
```

- [ ] **Step 4: Export it**

Add `from .remap import Remap` to `src/python/tik/maya/constructs/__init__.py`
with `"Remap"` in `__all__`, and add `Remap` to `src/python/tik/maya/__init__.py`'s
constructs import block and `__all__`.

- [ ] **Step 5: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_remap.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/maya/constructs/remap.py src/python/tik/maya/constructs/__init__.py src/python/tik/maya/__init__.py tests/unit/test_remap.py
git commit -m "feat(tik.maya): Remap construct over remapValue"
```

---

### Task 10: `AngleBetween` construct

**Files:**
- Create: `src/python/tik/maya/constructs/angle_between.py`
- Modify: `src/python/tik/maya/constructs/__init__.py`, `src/python/tik/maya/__init__.py`
- Test: `tests/unit/test_angle_between.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `AngleBetween.create(first, second, name=None)` with `.angle` (a `Plug`, degrees), `.node`, `.delete()`. Each operand is a compound `Plug` or a 3-tuple.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_angle_between.py`:

```python
"""Tests for the AngleBetween construct."""

from maya import cmds

import tik.maya as tm


def test_perpendicular_vectors_are_ninety_degrees():
    angle = tm.AngleBetween.create((1, 0, 0), (0, 1, 0), name="perp")
    assert abs(angle.angle.value - 90.0) < 1e-3


def test_parallel_vectors_are_zero():
    angle = tm.AngleBetween.create((1, 0, 0), (2, 0, 0), name="para")
    assert abs(angle.angle.value) < 1e-3


def test_opposite_vectors_are_one_eighty():
    angle = tm.AngleBetween.create((1, 0, 0), (-1, 0, 0), name="opp")
    assert abs(angle.angle.value - 180.0) < 1e-3


def test_a_plug_operand_is_live():
    holder = tm.Transform.create(name="angle_holder")
    holder.translate = (1, 0, 0)
    angle = tm.AngleBetween.create((1, 0, 0), holder["translate"], name="live")
    assert abs(angle.angle.value) < 1e-3
    holder.translate = (0, 1, 0)
    assert abs(angle.angle.value - 90.0) < 1e-3


def test_delete_removes_the_node():
    angle = tm.AngleBetween.create((1, 0, 0), (0, 1, 0), name="gone")
    name = angle.node.long_name
    angle.delete()
    assert not cmds.objExists(name)
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_angle_between.py -q`
Expected: FAIL — `AttributeError: module 'tik.maya' has no attribute 'AngleBetween'`

- [ ] **Step 3: Write the construct**

Create `src/python/tik/maya/constructs/angle_between.py`:

```python
"""The angle between two vectors, in degrees."""

from __future__ import annotations

from typing import Optional

from maya import cmds

from ..core.decorators import undo
from ..core.plug import Plug
from ..core.scene import create_node


class AngleBetween:
    """Wrapper for an ``angleBetween`` node."""

    def __init__(self, node) -> None:
        self.node = node

    @classmethod
    @undo
    def create(cls, first, second, name: Optional[str] = None) -> "AngleBetween":
        """Measure the angle between ``first`` and ``second``.

        Args:
            first: Compound plug or a 3-tuple.
            second: Compound plug or a 3-tuple.
            name: Prefix for the created node.

        Returns:
            The construct.
        """
        node = create_node("angleBetween", name=f"{name or 'angle'}_angleBetween")
        for attr, item in (("vector1", first), ("vector2", second)):
            if isinstance(item, Plug):
                item >> node[attr]
            else:
                node[attr].value = tuple(float(component) for component in item)
        return cls(node)

    @property
    def angle(self) -> Plug:
        """The angle in degrees."""
        return self.node["angle"]

    @undo
    def delete(self) -> None:
        """Delete the node."""
        if self.node.exists():
            cmds.delete(self.node.long_name)
```

- [ ] **Step 4: Export it**

Add `from .angle_between import AngleBetween` to
`src/python/tik/maya/constructs/__init__.py` with `"AngleBetween"` in
`__all__`, and add `AngleBetween` to `src/python/tik/maya/__init__.py`.

- [ ] **Step 5: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit/test_angle_between.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/maya/constructs/angle_between.py src/python/tik/maya/constructs/__init__.py src/python/tik/maya/__init__.py tests/unit/test_angle_between.py
git commit -m "feat(tik.maya): AngleBetween construct"
```

---

### Task 11: `systems/reach.py`

**Files:**
- Create: `src/python/tik/trigger/systems/reach.py`
- Test: `tests/integration/trigger/test_reach_system.py` (create)

**Interfaces:**
- Consumes: `tm.Remap`, `tm.AngleBetween`, `tm.AimFrame`, `tm.MatrixBlend`, `tm.MatrixConstraint`.
- Produces:

```python
build_reach(
    ctx, base_group, rest_from, target, control, *,
    prefix="autoReach",
    start_angle=0.0,
    end_angle=90.0,
    interpolation="smooth",
    name=None,
) -> None
```

Adds `<prefix>` (0–1, default 0), `<prefix>Vertical` and `<prefix>Horizontal`
(0–1, default 0.5) to `control`, and drives `base_group`.

**Background:** the offset is read off a transform parented under `rest_from`
rather than by multiplying matrices, because `pointMatrixMult` is plugin-gated
and absent from a stock Maya. The multipliers reshape *where it aims*, so `0`
on an axis cleanly means "ignore that axis".

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/trigger/test_reach_system.py`:

```python
"""Integration tests for the reach system."""

from maya import cmds

import tik.maya as tm
from tik.trigger.systems.reach import build_reach


def _setup(ctx, **kwargs):
    """A socket, a base to drive, and a target standing in for the IK hand."""
    socket = tm.Transform.create(name="reach_socket", parent=ctx.groups.socket.long_name)
    base = tm.Transform.create(name="reach_base", parent=ctx.groups.control.long_name)
    base.translate = (2, 0, 0)
    target = tm.Transform.create(name="reach_target", parent=ctx.groups.control.long_name)
    target.translate = (12, 0, 0)
    control = ctx.controller("reach_ctrl", mirror="world")
    build_reach(ctx, base, socket, target, control.transform, prefix="autoCollar",
                name="reach", **kwargs)
    return socket, base, target, control.transform


def _matrix(node):
    return list(node["worldMatrix[0]"].value)


def _close(first, second, tolerance=1e-4):
    return all(abs(a - b) < tolerance for a, b in zip(first, second))


def test_adds_the_three_attributes(build_context):
    _socket, _base, _target, control = _setup(build_context())
    assert control.has_attr("autoCollar")
    assert control.has_attr("autoCollarVertical")
    assert control.has_attr("autoCollarHorizontal")
    assert abs(control["autoCollar"].value) < 1e-6
    assert abs(control["autoCollarVertical"].value - 0.5) < 1e-6


def test_off_is_inert(build_context):
    _socket, base, target, _control = _setup(build_context())
    before = _matrix(base)
    target.translate = (12, 20, 8)
    assert _close(_matrix(base), before)


def test_below_the_start_angle_is_inert(build_context):
    """Catches an inverted or unclamped remap."""
    _socket, base, target, control = _setup(build_context(), start_angle=30.0, end_angle=60.0)
    control["autoCollar"].value = 1.0
    before = _matrix(base)
    target.translate = (12, 0.2, 0)  # a fraction of a degree off the rest direction
    assert _close(_matrix(base), before, tolerance=1e-3)


def test_above_the_start_angle_moves(build_context):
    _socket, base, target, control = _setup(build_context(), start_angle=5.0, end_angle=45.0)
    control["autoCollar"].value = 1.0
    before = _matrix(base)
    target.translate = (12, 12, 0)
    assert not _close(_matrix(base), before, tolerance=1e-3)


def test_zero_vertical_ignores_vertical_motion(build_context):
    """The per-axis test: proves the multipliers reach the right components."""
    _socket, base, target, control = _setup(build_context())
    control["autoCollar"].value = 1.0
    control["autoCollarVertical"].value = 0.0
    control["autoCollarHorizontal"].value = 1.0
    before = _matrix(base)
    target.translate = (12, 20, 0)
    assert _close(_matrix(base), before, tolerance=1e-3)
    target.translate = (12, 0, 20)
    assert not _close(_matrix(base), before, tolerance=1e-3)


def test_does_not_cycle(build_context):
    _socket, _base, _target, control = _setup(build_context())
    control["autoCollar"].value = 1.0
    cmds.dgdirty(allPlugs=True)
    assert not (cmds.cycleCheck(all=True) or [])


def test_everything_is_parented(build_context):
    """Ground rule nine: a system parents everything it creates."""
    before = set(cmds.ls(assemblies=True, long=True))
    _setup(build_context())
    assert set(cmds.ls(assemblies=True, long=True)) == before
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_reach_system.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.systems.reach'`

- [ ] **Step 3: Write the system**

Create `src/python/tik/trigger/systems/reach.py`:

```python
"""Reach: a base rotates toward an end-effector as it reaches away.

Auto-clavicle is shoulder reach; the same system serves a hip. It is named for
the behaviour rather than the anatomy, and it names no animator-facing
attribute itself -- the module supplies a prefix, because wording is policy.

    probe        transform under rest_from, point-constrained to the target
                 -> probe.translate IS the offset in the rest frame
    scaled       (t.x, t.y * <prefix>Vertical, t.z * <prefix>Horizontal)
    aim_point    transform under rest_from at `scaled`
    angle        AngleBetween(rest direction, scaled)
    factor       Remap(angle, start, end, 0..1, interpolation) * <prefix>
                 |
    MatrixBlend(rest, AimFrame(rest -> aim_point, up = rest_from), weight)
                 -> base_group
"""

from __future__ import annotations

from typing import Optional

import tik.maya as tm
from tik.maya import attribute


def build_reach(
    ctx,
    base_group,
    rest_from,
    target,
    control,
    *,
    prefix: str = "autoReach",
    start_angle: float = 0.0,
    end_angle: float = 90.0,
    interpolation: str = "smooth",
    name: Optional[str] = None,
) -> None:
    """Drive ``base_group`` to reach toward ``target``.

    Args:
        ctx: The module build context.
        base_group: Transform driven by the automation.
        rest_from: Transform the rest pose and the up vector come from
            (the module's socket).
        target: What the base reaches toward; MUST be upstream of any IK solve
            it feeds, or the graph cycles.
        control: Transform carrying the animator-facing attributes.
        prefix: Attribute prefix, e.g. ``autoCollar``.
        start_angle: Degrees below which the automation does nothing.
        end_angle: Degrees at or above which it is fully applied.
        interpolation: ``linear``, ``smooth`` or ``spline``.
        name: Prefix for created nodes.
    """
    name = name or prefix
    attribute.add_separator(control, "auto_")
    amount = attribute.add_float(control, prefix, default=0.0, min=0.0, max=1.0)
    vertical = attribute.add_float(
        control, f"{prefix}Vertical", default=0.5, min=0.0, max=1.0
    )
    horizontal = attribute.add_float(
        control, f"{prefix}Horizontal", default=0.5, min=0.0, max=1.0
    )

    # The rest pose: where the base sits with no automation at all.
    rest = tm.Transform.create(
        name=ctx.name(name, "rest"), parent=ctx.groups.rig.long_name
    )
    rest.snap_to(base_group)
    tm.MatrixConstraint.create(rest_from, rest, maintain_offset=True)

    # A transform under rest_from whose local translate IS the target offset in
    # that frame. Avoids pointMatrixMult, which is plugin-gated.
    probe = tm.Transform.create(
        name=ctx.name(name, "probe"), parent=rest_from.long_name
    )
    tm.MatrixConstraint.create(
        target, probe, maintain_offset=False, skip_rotate="xyz", skip_scale="xyz"
    )
    rest_direction = tuple(probe.translate)

    scaled = tm.create_node("multiplyDivide", name=ctx.name(name, "scaleMultiply"))
    probe["translate"] >> scaled["input1"]
    scaled["input2X"].value = 1.0
    vertical >> scaled["input2Y"]
    horizontal >> scaled["input2Z"]

    aim_point = tm.Transform.create(
        name=ctx.name(name, "aimPoint"), parent=rest_from.long_name
    )
    scaled["output"] >> aim_point["translate"]

    angle = tm.AngleBetween.create(
        rest_direction, scaled["output"], name=ctx.name(name, "angle")
    )
    ramp = tm.Remap.create(
        angle.angle,
        input_min=start_angle,
        input_max=end_angle,
        interpolation=interpolation,
        name=ctx.name(name),
    )
    weight = ramp.output * amount

    frame = tm.AimFrame.create(
        rest,
        aim_point,
        rest_from,
        twist_axis="X",
        parent=ctx.groups.rig,
        name=ctx.name(name, "frame"),
    )
    blend = tm.MatrixBlend.create(
        rest, [frame.transform], [weight], name=ctx.name(name, "blend")
    )
    tm.MatrixConstraint.create(blend.output, base_group, maintain_offset=True)
```

- [ ] **Step 4: Run the tests**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_reach_system.py -q`
Expected: PASS, 7 tests.

If `test_off_is_inert` fails, `rest` captured the wrong pose — confirm
`rest.snap_to(base_group)` runs *before* the constraint from `rest_from`.
If `test_zero_vertical_ignores_vertical_motion` fails, the multiplier is wired
to the wrong component of `multiplyDivide.input2`.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/systems/reach.py tests/integration/trigger/test_reach_system.py
git commit -m "feat(tik.trigger): reach system with angle remapping and per-axis multipliers"
```

---

### Task 12: The arm uses reach

**Files:**
- Modify: `src/python/tik/trigger/modules/arm/arm.py`
- Test: `tests/integration/trigger/test_arm_trigger.py` (modify)

**Interfaces:**
- Consumes: `build_reach` from Task 11.
- Produces: the arm's `auto_collar`, `auto_collar_start`, `auto_collar_end`, `auto_collar_interpolation` fields; `Arm.validate()` rejecting `start >= end`; `_build_auto_collar` replaced by a `build_reach` call.

- [ ] **Step 1: Write the failing tests**

In `tests/integration/trigger/test_arm_trigger.py`, replace
`test_auto_collar_defaults_to_off` and add:

```python
def test_auto_collar_fields_exist():
    names = set(get_module("arm").fields())
    assert {"auto_collar", "auto_collar_start", "auto_collar_end",
            "auto_collar_interpolation"} <= names


def test_auto_collar_can_be_switched_off(backend):
    control = _ik_control(_arm_ctx(backend, auto_collar=False))
    assert not control.has_attr("autoCollar")


def test_auto_collar_on_adds_the_multipliers(backend):
    control = _ik_control(_arm_ctx(backend))
    assert control.has_attr("autoCollar")
    assert abs(control["autoCollarVertical"].value - 0.5) < 1e-6
    assert abs(control["autoCollarHorizontal"].value - 0.5) < 1e-6


def test_validate_rejects_a_degenerate_angle_range():
    module = get_module("arm")(name="arm")
    module.auto_collar_start = 90.0
    module.auto_collar_end = 30.0
    assert any("angle" in problem for problem in module.validate())
```

- [ ] **Step 2: Run to verify failure**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration/trigger/test_arm_trigger.py -k "auto_collar or degenerate" -q`
Expected: FAIL — `auto_collar` is not a field.

- [ ] **Step 3: Add the fields**

In `src/python/tik/trigger/modules/arm/arm.py`, add `ChoiceField` and
`FloatField` to the `tik.trigger.core` import and add beside the other fields:

```python
    auto_collar = BoolField(True, help="Build the auto-collar network")
    auto_collar_start = FloatField(
        0.0, min=0.0, max=180.0, label="Auto Collar Start Angle",
        help="Degrees below which the automation does nothing",
    )
    auto_collar_end = FloatField(
        90.0, min=0.0, max=180.0, label="Auto Collar End Angle",
        help="Degrees at or above which it is fully applied",
    )
    auto_collar_interpolation = ChoiceField(
        "smooth", choices=("linear", "smooth", "spline"), label="Auto Collar Interpolation"
    )
```

- [ ] **Step 4: Validate the range**

Add to `Arm`:

```python
    def validate(self) -> list[str]:
        problems = super().validate()
        if self.auto_collar and self.auto_collar_start >= self.auto_collar_end:
            problems.append(
                "auto collar start angle must be below the end angle "
                f"({self.auto_collar_start} >= {self.auto_collar_end})"
            )
        return problems
```

- [ ] **Step 5: Replace the inline auto-collar with `build_reach`**

Delete the whole `_build_auto_collar` static method, and replace its call:

```python
        if self.auto_collar:
            auto_grp = tm.Transform.create(
                name=ctx.name("collar", "auto", suffix="grp"),
                parent=collar_offset.long_name,
            )
            auto_grp.snap_to(collar_ctrl.transform)
            # Relative, so set_parent writes no compensation into the channels.
            collar_ctrl.transform.set_parent(auto_grp, relative=True)
            build_reach(
                ctx,
                auto_grp,
                socket,
                limb.ik_tweak.transform,
                limb.ik_control.transform,
                prefix="autoCollar",
                start_angle=self.auto_collar_start,
                end_angle=self.auto_collar_end,
                interpolation=self.auto_collar_interpolation,
                name="collar",
            )
```

Change the import to `from tik.trigger.systems.reach import build_reach` and
keep `from tik.trigger.systems.limb import _derive_size, build_ikfk_limb`.

- [ ] **Step 6: Run the suites**

Run: `set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration -q`
Expected: PASS. The existing `test_auto_collar_off_is_inert`,
`test_auto_collar_on_follows_the_hand`, `test_wrist_roll_does_not_spin_the_collar`
and `test_auto_collar_does_not_cycle` must all still pass unchanged — they are
the behavioural contract carried over from the previous implementation.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/modules/arm tests/integration/trigger/test_arm_trigger.py
git commit -m "feat(tik.trigger): arm auto-collar becomes an optional, remappable reach"
```

---

### Task 13: Verification sweep

**Files:**
- Test: `tests/integration/trigger/test_module_ground_rules.py` (no change expected; run it)

- [ ] **Step 1: Run every suite and record the counts**

```
set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/unit -q
set PYTHONPATH=D:\dev\tikworks\src\python && mayapy -m pytest tests/integration -q
set PYTHONPATH=D:\dev\tikworks\src\python && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui -q
```

Expected: all pass. Report any failure with its output rather than moving on.

- [ ] **Step 2: Confirm the removals actually left**

Run: `git grep -n "trg_spaces\|set_spaces\|spaces_for\|Port.multi\|\.multi\b" -- src/python/tik`
Expected: no hits.

- [ ] **Step 3: Commit if anything changed**

```bash
git add -A
git commit -m "test(tik.trigger): full sweep after dynamic spaces and reach"
```

---

## Self-Review Notes

**Spec coverage.** §1.1 → Tasks 4, 5. §1.2 → Task 1. §1.3 → Tasks 2, 4. §1.4 →
Task 4. §1.5 → Task 5. §1.6 → Tasks 5, 6. Part 2 → Tasks 2, 3. Part 3 → Tasks 1,
7. §4.1-4.2 → Task 11. §4.3 → Tasks 9, 10. §4.4 → Task 12. §5.1 → Tasks 5, 6, 8,
9, 11. §5.2 → all. §5.3 risk 1 → Task 4 Step 5; risk 2 → Task 3.

**Known risks, stated rather than hidden.**

1. **Task 1 is a large subtraction across ten files.** Nothing exercises the
   removed code afterwards, so a half-removal shows up as an import error rather
   than a wrong rig — annoying but loud. Step 9's `git grep` is the check.
2. **The ordering filter in Task 5 Step 4** is the single line that matters
   most. If `structural_inputs` is not used, `test_space_inputs_do_not_feed_build_order`
   is the only thing that fails, and it fails as a cycle error rather than
   anything that names spaces.
3. **API guesses.** `tests/ui/test_form_builder.py`'s fixture style (Task 3),
   `GuideHandle.settings` on the graph handle (Task 7), and
   `backend.set_inputs` accepting a full dict (Task 8) are used as written from
   surrounding code but not verified line by line. Each step says to read the
   real names and adjust the call, never the assertion.
4. **`test_below_the_start_angle_is_inert` uses a very small offset** so the
   angle stays under `start_angle`. If the probe's rest direction is captured
   after the constraint rather than before, the rest direction is zero and the
   angle is undefined — that is the failure mode to look for.
