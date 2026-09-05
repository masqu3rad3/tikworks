# Dynamic Anim-Space Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static `Module.space_controls` tuple with a settings-aware control manifest, so modules whose controllers depend on their settings — `fkchain`, `ribbon` — can offer animation spaces at all.

**Architecture:** A module declares `controls` and, when a setting drives them, overrides `control_names(settings)` — deliberately the shape of the existing `outputs` / `output_names(settings)` pair. The anim-space table's `control` column resolves against it, which needs the shared field layer to accept a *callable* `choices_from`. A row naming a control that no longer exists survives, reported through a new non-fatal `Module.warnings()` channel rather than through `validate()`, which the builder treats as fatal. A ground-rules test holds every module's manifest to the controllers it actually builds.

**Tech Stack:** Python 3.10+, Autodesk Maya 2024+ (`mayapy`), PySide2/6 via `tik.shared.ui`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-05-dynamic-anim-space-controls-design.md`

## Global Constraints

- **No third-party dependencies.** Stdlib and Maya-bundled modules only.
- **Consume tik.maya.** No `maya.cmds`, `OpenMaya` or `pymel` in `tik.trigger` code. (Tests may use `cmds` — the existing suites do.)
- **`tik/trigger/core` is pure Python** — no Maya, no Qt. Enforced by `tests/unit/test_import_boundaries.py`. Tasks 3 and 8 touch files on both sides of that line; keep the manifest itself in `core`.
- **Modules never inherit from other modules.** Shared behaviour goes in `tik/trigger/systems/`.
- **One dialog surface.** No raw `QMessageBox` / `QFileDialog` / `QInputDialog`; enforced by `tests/unit/test_dialog_boundaries.py`. No task here should need a dialog.
- **Every commit must leave the suites green.** Task order is chosen so no intermediate commit has a broken `choices_from` or a dangling `space_controls`.

### Commands

Run from the repo root. On Windows these are `cmd` shell forms; the Makefile targets work in any shell.

| What | Command |
|---|---|
| Whole unit suite | `make tests-unit` |
| Whole integration suite | `make tests-integration` |
| Whole Qt UI suite | `make tests-ui` |
| One unit test | `set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_core_trigger.py::test_name -v` |
| One UI test | `set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_form_builder.py::test_name -v` |
| One integration test | `set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && set MAYA_PLUG_IN_PATH=%CD%\src\plugins\python;%MAYA_PLUG_IN_PATH% && mayapy -m pytest tests/integration/trigger/test_builder_trigger.py::test_name -v` |
| Lint | `make lint` |

`tests/unit/invoke.py` and `tests/integration/invoke.py` take no arguments — they always run their whole directory. Use the direct `mayapy -m pytest` forms above for a single test.

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `src/python/tik/core/fields.py` (modify) | `Column.choices_from` documents that it may name a callable | 1 |
| `src/python/tik/shared/ui/fields.py` (modify) | Resolve a callable `choices_from`; keep an unresolvable choice value instead of rewriting it | 1, 2 |
| `src/python/tik/trigger/core/module.py` (modify) | `controls`, `control_names(settings)`, `warnings()`; `space_controls` removed | 3 |
| `src/python/tik/trigger/maya/build.py` (modify) | Log a module's warnings; skip a space whose controller was not built | 4 |
| `src/python/tik/trigger/systems/limb.py` (modify) | `limb_control_names()` — the roles `build_ikfk_limb` will create | 5 |
| `src/python/tik/trigger/modules/arm/arm.py` (modify) | Arm's manifest, from `limb_control_names` | 3, 5 |
| `src/python/tik/trigger/modules/base/base.py` (modify) | `controls = ("root",)` | 6 |
| `src/python/tik/trigger/modules/fkchain/fkchain.py` (modify) | `control_names` → `fk0..fk{segments-1}` | 6 |
| `src/python/tik/trigger/modules/twist/twist.py` (modify) | `controls = ()` — it builds none, and says so | 6 |
| `src/python/tik/trigger/modules/ribbon/ribbon.py` (modify) | Optional start/end controllers; manifest | 7 |
| `src/python/tik/trigger/session.py` (modify) | `Session.validate()` gains a module pass | 8 |
| `src/python/tik/trigger/ui/designer/properties.py` (modify) | `_topology()` includes the control manifest | 9 |
| `tests/unit/test_core_trigger.py` (modify) | Manifest defaults/overrides, `warnings()`, row survival | 3 |
| `tests/unit/test_ribbon_trigger.py` (modify) | Ribbon start/end controllers and twist wiring | 7 |
| `tests/unit/test_session_trigger.py` (modify) | Session validate reports module warnings | 8 |
| `tests/ui/test_form_builder.py` (modify) | Callable resolver; stale value round-trip | 1, 2 |
| `tests/ui/test_pipeline_ui.py` (modify) | Migrated off `space_controls` | 3 |
| `tests/ui/test_guide_designer.py` (modify) | Form repaints when the manifest moves | 9 |
| `tests/helpers/toy_modules.py` (modify) | Migrated off `space_controls` | 3 |
| `tests/integration/trigger/test_builder_trigger.py` (modify) | Migrated off `space_controls`; space on a dynamic control; missing control warns | 3, 4 |
| `tests/integration/trigger/test_arm_trigger.py` (modify) | Arm's manifest assertion | 3, 5 |
| `tests/integration/trigger/test_module_ground_rules.py` (modify) | The drift guard | 10 |
| `CLAUDE.md`, `AI/coding_rules.md` (modify) | The manifest is a module ground rule | 11 |

---

### Task 1: `choices_from` may name a callable

The anim-space table's `control` column will resolve against `Module.control_names`, a classmethod taking settings. `FormBuilder` currently resolves `choices_from` with a bare `getattr`, which would hand `_TableEditor` a bound method and blow up in `list()`. Widen the contract first, so no later commit has a broken combo box.

**Files:**
- Modify: `src/python/tik/core/fields.py:373-390` (the `Column` docstring)
- Modify: `src/python/tik/shared/ui/fields.py:505-512` (the `_TableEditor` construction in `FormBuilder._make_widget`)
- Test: `tests/ui/test_form_builder.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `FormBuilder._resolve_choices(self, attr: str) -> tuple` — resolves `attr` on the current target; calls it with `self._target.values()` when the resolved object is callable. Task 3 relies on this to point a column at `control_names`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_form_builder.py`, directly after `test_table_widget_resolves_choices_from_the_target`:

```python
def test_table_widget_resolves_choices_from_a_callable():
    """A column's options may be computed from the target's own values."""
    from tik.core.fields import Column, IntField, TableField

    class Holder(Schema):
        count = IntField(3)
        rows = TableField(
            columns=(Column("control", "choice", choices_from="control_names"),)
        )

        @classmethod
        def control_names(cls, settings=None):
            total = int((settings or {}).get("count", 3))
            return tuple(f"fk{index}" for index in range(total))

    holder = Holder()
    holder.count = 2
    builder = FormBuilder(holder)
    widget = builder.widget("rows")
    widget.add_row()
    combo = widget.cell_widget(0, 0)
    assert [combo.itemText(index) for index in range(combo.count())] == ["fk0", "fk1"]
```

`IntField` may already be imported at the top of the file — if so, drop it from this local import rather than shadowing.

- [ ] **Step 2: Run the test and watch it fail**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_form_builder.py::test_table_widget_resolves_choices_from_a_callable -v
```

Expected: FAIL — `TypeError: 'method' object is not iterable` (or an empty combo), because `getattr` returns the bound classmethod and `_choices` calls `list()` on it.

- [ ] **Step 3: Widen the resolver**

In `src/python/tik/shared/ui/fields.py`, replace the inline lambda:

```python
        elif kind == "table":
            widget = _TableEditor(
                getattr(field, "columns", ()),
                choices_resolver=lambda attr: getattr(self._target, attr, ()),
            )
```

with a call to a named method:

```python
        elif kind == "table":
            widget = _TableEditor(
                getattr(field, "columns", ()),
                choices_resolver=self._resolve_choices,
            )
```

and add the method to `FormBuilder`, immediately after `_make_widget`:

```python
    def _resolve_choices(self, attr: str) -> tuple:
        """The options a column's ``choices_from`` names on the current target.

        The attribute may be a plain sequence or a callable taking the
        target's values -- a field is a class attribute and cannot know the
        subclass it will be edited on, so a column whose options depend on
        the target's *settings* has to compute them at render time.
        """
        if self._target is None:
            return ()
        found = getattr(self._target, attr, ())
        if callable(found):
            found = found(self._target.values())
        return tuple(found or ())
```

- [ ] **Step 4: Document the contract on `Column`**

In `src/python/tik/core/fields.py`, extend the `Column` docstring:

```python
class Column:
    """One column of a :class:`TableField`.

    ``choices_from`` names an attribute on the *target object* supplying the
    options. A field is a class attribute and cannot know the subclass it will
    be edited on, so a column whose options vary per module resolves them at
    render time instead. The named attribute may be a plain sequence, or a
    callable taking the target's values and returning one -- which is how a
    column follows options that depend on the target's own settings.
    """
```

- [ ] **Step 5: Run the test and the neighbouring one**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_form_builder.py -v
```

Expected: PASS, including the pre-existing `test_table_widget_resolves_choices_from_the_target` (a plain tuple still resolves).

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/core/fields.py src/python/tik/shared/ui/fields.py tests/ui/test_form_builder.py
git commit -m "feat(fields): choices_from may name a callable taking the target's values"
```

---

### Task 2: A stale choice value survives its combo box

`_make_cell` populates a combo, then `findText(value)`; a missing value returns `-1`, the combo shows index 0, and the next `_emit()` writes that first item back — silently rewriting `fk5` to `fk0`. That would defeat the whole "keep the row" decision before it is even made. Fix it now, while the failure is easy to see in isolation.

**Files:**
- Modify: `src/python/tik/shared/ui/fields.py:105-117` (`_TableEditor._make_cell`) and `:150-166` (`_TableEditor.value`)
- Test: `tests/ui/test_form_builder.py`

**Interfaces:**
- Consumes: `FormBuilder._resolve_choices` from Task 1.
- Produces: `tik.shared.ui.fields.MISSING_SUFFIX = " (missing)"` — a module-level constant. Each choice combo item now carries its raw value as item *data*; `value()` reads `currentData()`. Task 3's stale-row behaviour depends on this round-trip.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_form_builder.py`, after the test from Task 1:

```python
def test_table_widget_keeps_a_value_the_target_no_longer_offers():
    """A row is never silently rewritten to the first choice."""
    from tik.core.fields import Column, TableField

    class Holder(Schema):
        controls = ("fk0", "fk1")
        rows = TableField(
            columns=(Column("control", "choice", choices_from="controls"),)
        )

    holder = Holder()
    builder = FormBuilder(holder)
    widget = builder.widget("rows")
    widget.setValue([{"control": "fk5"}])
    combo = widget.cell_widget(0, 0)
    assert "missing" in combo.currentText()
    assert widget.value() == [{"control": "fk5"}]
```

- [ ] **Step 2: Run the test and watch it fail**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_form_builder.py::test_table_widget_keeps_a_value_the_target_no_longer_offers -v
```

Expected: FAIL — `assert "missing" in "fk0"`, because the combo fell back to index 0.

- [ ] **Step 3: Carry the raw value as item data**

In `src/python/tik/shared/ui/fields.py`, add the constant near the top of the module, beside the other module-level names:

```python
#: Appended to a choice a target no longer offers, so a row that references a
#: renamed or removed option stays visible instead of being rewritten.
MISSING_SUFFIX = " (missing)"
```

Replace `_TableEditor._make_cell`:

```python
    def _make_cell(self, column, value):
        if column.kind == "choice":
            widget = QtWidgets.QComboBox()
            for item in self._choices(column):
                widget.addItem(str(item), str(item))
            if value:
                index = widget.findData(str(value))
                if index < 0:
                    # The target stopped offering this option. Keep it, marked:
                    # falling back to index 0 would quietly rewrite the row.
                    widget.addItem(f"{value}{MISSING_SUFFIX}", str(value))
                    index = widget.count() - 1
                widget.setCurrentIndex(index)
            widget.currentIndexChanged.connect(self._emit)
            return widget
        widget = QtWidgets.QLineEdit(str(value or ""))
        widget.editingFinished.connect(self._emit)
        return widget
```

and in `_TableEditor.value`, read the data rather than the display text:

```python
                if isinstance(widget, QtWidgets.QComboBox):
                    data = widget.currentData()
                    row[column.name] = (
                        data if data is not None else widget.currentText()
                    )
```

- [ ] **Step 4: Run the UI suite**

```
make tests-ui
```

Expected: PASS. `test_table_widget_resolves_choices_from_the_target` reads `itemText`, which is unchanged for resolvable values.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/shared/ui/fields.py tests/ui/test_form_builder.py
git commit -m "fix(fields): keep a table choice the target no longer offers instead of rewriting the row"
```

---

### Task 3: The control manifest replaces `space_controls`

The core change. `space_controls` is removed everywhere in one commit — five call sites across one module and four test files — so no commit is left half-migrated. Arm gets a straight rename here (`controls = ("ik", "pole")`); Task 5 replaces that with the full manifest.

**Files:**
- Modify: `src/python/tik/trigger/core/module.py:44-64` (class attributes), `:80-92` (classmethods), `:167-192` (`validate` / `_validate_spaces`)
- Modify: `src/python/tik/trigger/modules/arm/arm.py:42`
- Modify: `tests/helpers/toy_modules.py:18`
- Modify: `tests/integration/trigger/test_builder_trigger.py:36`, `:55`
- Modify: `tests/integration/trigger/test_arm_trigger.py:437-438`
- Modify: `tests/ui/test_pipeline_ui.py:367`
- Test: `tests/unit/test_core_trigger.py:258-315`

**Interfaces:**
- Consumes: `FormBuilder._resolve_choices` (Task 1), `MISSING_SUFFIX` round-trip (Task 2).
- Produces:
  - `Module.controls: tuple[str, ...] = ()`
  - `Module.control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]`
  - `Module.warnings(self) -> list[str]` — non-fatal problems, empty by default.
  - `Module.space_controls` **no longer exists**. Tasks 4–10 use `control_names`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_core_trigger.py`, replace the `_spaced_module` helper and `test_validate_rejects_an_unknown_control` in the `anim spaces` section:

```python
def _spaced_module():
    from tik.trigger.core import Module

    class Spaced(Module):
        controls = ("ik", "pole")

    return Spaced


def _dynamic_module():
    from tik.trigger.core import IntField, Module

    class Dynamic(Module):
        segments = IntField(3, min=1)

        @classmethod
        def control_names(cls, settings=None):
            count = int((settings or {}).get("segments", cls.segments.default))
            return tuple(f"fk{index}" for index in range(count))

    return Dynamic
```

and add, after `test_validate_rejects_duplicate_rows`:

```python
def test_control_names_defaults_to_the_declared_controls():
    assert _spaced_module().control_names() == ("ik", "pole")
    assert _spaced_module().control_names({}) == ("ik", "pole")


def test_control_names_can_follow_a_setting():
    module_cls = _dynamic_module()
    assert module_cls.control_names({"segments": 2}) == ("fk0", "fk1")
    assert module_cls.control_names() == ("fk0", "fk1", "fk2")


def test_a_stale_control_warns_instead_of_failing_validation():
    """Lowering a count must not make an authored rig unbuildable."""
    module = _dynamic_module()(name="x")
    module.segments = 2
    module.anim_spaces = [{"control": "fk5", "mode": "parent", "label": "world"}]
    assert module.validate() == []
    assert any("fk5" in item for item in module.warnings())


def test_a_stale_control_keeps_its_row_and_its_port():
    """Ports come from rows, not from controls, so the wire survives."""
    module_cls = _dynamic_module()
    settings = {
        "segments": 2,
        "anim_spaces": [{"control": "fk5", "mode": "parent", "label": "world"}],
    }
    assert module_cls.input_names(settings) == ["root", "fk5_world"]


def test_warnings_are_empty_when_every_control_exists():
    module = _spaced_module()(name="x")
    module.anim_spaces = [{"control": "ik", "mode": "parent", "label": "chest"}]
    assert module.warnings() == []
```

Delete `test_validate_rejects_an_unknown_control` — that check has moved to `warnings()` and is covered by `test_a_stale_control_warns_instead_of_failing_validation`.

- [ ] **Step 2: Run the tests and watch them fail**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_core_trigger.py -k "control_names or stale_control or warnings_are_empty" -v
```

Expected: FAIL — `AttributeError: type object 'Spaced' has no attribute 'control_names'`.

- [ ] **Step 3: Add the manifest to `Module`**

In `src/python/tik/trigger/core/module.py`, replace the `space_controls` class attribute:

```python
    space_controls: tuple[str, ...] = ()  # controller roles that accept spaces
```

with:

```python
    #: Controller roles this module builds. Every one of them can host an
    #: animation space; tweak controllers are excluded by construction, since
    #: ``rig.tweak_control`` parents them under their main.
    controls: tuple[str, ...] = ()
```

Point the table column at the new name:

```python
            Column("control", "choice", choices_from="control_names"),
```

Add the classmethod, immediately after `output_names`:

```python
    @classmethod
    def control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles an instance builds.

        Override when a setting drives them -- ``fkchain`` builds one per
        segment. This is the shape of ``output_names`` on purpose: one idiom
        for a manifest entry whose set depends on settings, not two.
        """
        return tuple(cls.controls)
```

- [ ] **Step 4: Split fatal problems from warnings**

Still in `module.py`, drop the unknown-control branch from `_validate_spaces`:

```python
    def _validate_spaces(self) -> list[str]:
        """Anim-space rows must derive unique, well-formed port names."""
        problems, seen = [], set()
        for index, row in enumerate(self.anim_spaces):
            control, label = row.get("control", ""), row.get("label", "")
            if not label:
                problems.append(f"anim space row {index + 1}: label is required")
                continue
            name = f"{control}_{label}"
            if name in seen:
                problems.append(
                    f"anim space row {index + 1}: '{name}' is already defined"
                )
            seen.add(name)
        return problems
```

and add the new channel, directly after `validate`:

```python
    def warnings(self) -> list[str]:
        """Problems worth showing that must not stop a build.

        Separate from ``validate`` because the builder treats every validation
        problem as fatal. Lowering ``segments`` leaves a row naming a control
        that is no longer built; that must cost the rigger a warning, not the
        rig -- and the row is kept, so raising the count restores the setup
        with its wire intact.
        """
        problems = []
        known = type(self).control_names(self.values())
        for row in self.anim_spaces:
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            if control not in known:
                problems.append(
                    f"anim space '{control}_{label}': control '{control}' is "
                    f"not built with the current settings"
                )
        return problems
```

- [ ] **Step 5: Migrate the five `space_controls` call sites**

Each is a one-line rename to `controls`:

- `src/python/tik/trigger/modules/arm/arm.py:42` → `controls = ("ik", "pole")` (Task 5 widens this)
- `tests/helpers/toy_modules.py:18` → `controls = ("root",)`
- `tests/integration/trigger/test_builder_trigger.py:36` → `controls = ("root",)`
- `tests/integration/trigger/test_builder_trigger.py:55` → `controls = ("fk",)`
- `tests/ui/test_pipeline_ui.py:367` → `controls = ("ik",)`

And in `tests/integration/trigger/test_arm_trigger.py:437-438`:

```python
def test_arm_declares_its_controls():
    assert get_module("arm").control_names() == ("ik", "pole")
```

Confirm nothing was missed:

```
grep -rn "space_controls" --include=*.py .
```

Expected: no matches. (Matches under `docs/superpowers/plans/` and `docs/superpowers/specs/` are historical records of superseded designs — leave them.)

- [ ] **Step 6: Run the unit, UI and integration suites**

```
make tests-unit
make tests-ui
make tests-integration
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/core/module.py src/python/tik/trigger/modules/arm/arm.py tests/
git commit -m "feat(trigger): control manifest replaces the static space_controls tuple"
```

---

### Task 4: The builder warns instead of dying

`_build_one` turns any `validate()` problem into a `BuildError`, and `connect_space` raises `AttachError` when the controller is missing. With the stale check now living in `warnings()`, both need wiring: log the warnings, and skip a space whose controller was not built.

**Files:**
- Modify: `src/python/tik/trigger/maya/build.py:104-124` (`connect_space`), `:368-378` (`_build_one`), `:285-325` (`_connect_spaces`)
- Test: `tests/integration/trigger/test_builder_trigger.py`

**Interfaces:**
- Consumes: `Module.warnings()` and `Module.control_names()` from Task 3.
- Produces: `connect_space(rig, control, mode, targets, labels) -> bool` — returns `False` (having built nothing) when no controller carries `control`, `True` otherwise. It no longer raises `AttachError`.

- [ ] **Step 1: Write the failing tests**

In `tests/integration/trigger/test_builder_trigger.py`, `ToyChain` already builds a single `fk` controller. Add a dynamic one beside `ToyChain`, so a space can name a control that a setting removes:

```python
class ToyFan(Module):
    """One controller per segment, so the manifest follows a setting."""

    label = "Toy Fan"
    sided = False
    guides = GuideLayout("root", multi="segment", min=1)
    inputs = ()
    outputs = ("root",)
    segments = IntField(2, min=1)

    @classmethod
    def control_names(cls, settings=None):
        count = int((settings or {}).get("segments", cls.segments.default))
        return tuple(f"fk{index}" for index in range(count))

    def guide_count(self) -> int:
        return self.segments

    def draw_guides(self, guides) -> None:
        previous = guides.joint("root", (0, 0, 0))
        for index in range(self.segments):
            previous = guides.joint(
                "segment", (index + 1, 0, 0), index=index, parent=previous
            )

    def build(self, rig) -> None:
        joint = rig.bind_joint("root", match=rig.guide("root"))
        for index in range(self.segments):
            rig.controller(f"fk{index}", match=joint)
        rig.output("root", joint)
```

Register and unregister it alongside the others in the `toys` fixture — add `("toy_fan", ToyFan)` to the registration tuple and `"toy_fan"` to the teardown list. Then add the two tests at the end of the file:

```python
def test_a_space_on_a_dynamic_control_builds_a_switch(toys):
    """A control the manifest computes from a setting is a real space target."""
    anchor = toys.create_guides(get_module("toy_root")(name="anchor"))
    fan = toys.create_guides(get_module("toy_fan")(name="fan"))
    toys.write_settings(
        fan.instance_id,
        {
            "segments": 3,
            "anim_spaces": [{"control": "fk2", "mode": "parent", "label": "anchor"}],
        },
    )
    toys.set_input(fan.instance_id, "fk2_anchor", f"{anchor.key}.root")

    report = Builder().build(document=toys.document, rig_name="fan", afterlife="keep")

    ctx = report.rigs[fan.instance_id]
    control = ctx.controller_by_role("fk2")
    assert control is not None
    assert control.transform["parentSwitch"].exists()


def test_a_space_on_a_removed_control_warns_and_still_builds(toys):
    """Lowering a count must cost a warning, never the rig."""
    anchor = toys.create_guides(get_module("toy_root")(name="anchor"))
    fan = toys.create_guides(get_module("toy_fan")(name="fan"))
    toys.write_settings(
        fan.instance_id,
        {
            "segments": 1,
            "anim_spaces": [{"control": "fk2", "mode": "parent", "label": "anchor"}],
        },
    )
    toys.set_input(fan.instance_id, "fk2_anchor", f"{anchor.key}.root")

    report = Builder().build(document=toys.document, rig_name="fan", afterlife="keep")

    assert fan.instance_id in report.built
    assert report.rigs[fan.instance_id].controller_by_role("fk2") is None
```

`ToyFan` needs `IntField` and `get_module` imported at the top of the file; add whichever is missing to the existing `from tik.trigger.core import ...` line.

- [ ] **Step 2: Run the tests and watch them fail**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && set MAYA_PLUG_IN_PATH=%CD%\src\plugins\python;%MAYA_PLUG_IN_PATH% && mayapy -m pytest tests/integration/trigger/test_builder_trigger.py -k "dynamic_control or removed_control" -v
```

Expected: the second test FAILs with `AttachError: fan: no controller with role 'fk2'.` The first should pass already — write it anyway; it is the regression guard that the whole feature exists for.

- [ ] **Step 3: Make `connect_space` skip rather than raise**

In `src/python/tik/trigger/maya/build.py`:

```python
def connect_space(rig, control, mode, targets, labels) -> bool:
    """Build one space switch on the controller with role ``control``.

    ``world=False``: nothing appears in the enum that the rigger did not define.
    Returns False, having built nothing, when no controller carries ``control``
    -- a setting that removed the control must cost a warning, not the rig.
    """
    controller = rig.controller_by_role(control)
    if controller is None:
        return False
    tm.SpaceSwitch.create(
        controller.transform,
        targets,
        attr_name=f"{mode}Switch",
        mode=mode,
        labels=list(labels),
        world=False,
        name=rig.name(control, mode),
    )
    return True
```

In `_connect_spaces`, report the skip:

```python
            for (control, mode), (targets, labels) in groups.items():
                if not connect_space(ctx, control, mode, targets, labels):
                    self.events.log(
                        f"{instance.key}: no controller with role '{control}'; "
                        f"its {mode} space was skipped.",
                        level="warning",
                    )
```

If `AttachError` is now unused in `build.py`, leave the import alone only if something else still raises it — `_connect_one` and `resolve` do, so it stays.

- [ ] **Step 4: Log a module's warnings before building it**

In `_build_one`, after the `validate()` block:

```python
        problems = module.validate()
        if problems:
            raise BuildError(
                f"'{instance.name}' cannot build: " + "; ".join(problems),
                instance_id=instance.instance_id,
                module_type=instance.module_type,
            )
        for warning in module.warnings():
            self.events.log(f"{instance.key}: {warning}", level="warning")
```

- [ ] **Step 5: Run the integration suite**

```
make tests-integration
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/maya/build.py tests/integration/trigger/test_builder_trigger.py
git commit -m "feat(trigger): a space whose controller was not built warns instead of failing the rig"
```

---

### Task 5: The limb system names its own controller roles

`build_ikfk_limb` chooses the limb's controller roles through `_role(name, ...)`. Arm must not hardcode strings the system owns, or the two drift the moment a role is renamed.

**Files:**
- Modify: `src/python/tik/trigger/systems/limb.py` (add `limb_control_names` beside `_role`, around `:465`)
- Modify: `src/python/tik/trigger/modules/arm/arm.py:26` (import) and `:42` (manifest)
- Test: `tests/integration/trigger/test_arm_trigger.py:437`

**Interfaces:**
- Consumes: `Module.control_names` from Task 3.
- Produces: `limb_control_names(name: str = "", labels: Sequence[str] = ()) -> tuple[str, ...]` in `tik.trigger.systems.limb` — the ordered roles `build_ikfk_limb` creates: the IK control, one FK control per label, then the pole. Task 10's drift test compares against it via `Arm.control_names`.

- [ ] **Step 1: Write the failing test**

Replace `test_arm_declares_its_controls` in `tests/integration/trigger/test_arm_trigger.py`:

```python
def test_arm_declares_every_controller_it_builds():
    """The manifest is what the module builds, not a curated subset."""
    assert get_module("arm").control_names() == (
        "collar",
        "ik",
        "fk_upper",
        "fk_lower",
        "fk_hand",
        "pole",
    )
```

- [ ] **Step 2: Run the test and watch it fail**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && set MAYA_PLUG_IN_PATH=%CD%\src\plugins\python;%MAYA_PLUG_IN_PATH% && mayapy -m pytest tests/integration/trigger/test_arm_trigger.py::test_arm_declares_every_controller_it_builds -v
```

Expected: FAIL — `assert ('ik', 'pole') == ('collar', 'ik', ...)`.

- [ ] **Step 3: Publish the limb's role names**

In `src/python/tik/trigger/systems/limb.py`, directly after `_role`:

```python
def limb_control_names(name: str = "", labels: Sequence[str] = ()) -> tuple[str, ...]:
    """The controller roles ``build_ikfk_limb`` creates for these arguments.

    A module declaring its controls must not hardcode names this system
    chose: the two would drift the moment a role is renamed. Tweaks are
    omitted -- ``rig.tweak_control`` parents them under their main, so a
    space switch on one would fight the parent it hangs from.
    """
    return (
        _role(name, "ik"),
        *(_role(name, "fk", label) for label in labels),
        _role(name, "pole"),
    )
```

`Sequence` must be imported — add `from typing import Sequence` (or extend the existing `typing` import) at the top of `limb.py` if it is not already there.

- [ ] **Step 4: Point the arm at it**

In `src/python/tik/trigger/modules/arm/arm.py`, extend the limb import:

```python
from tik.trigger.systems.limb import _derive_size, build_ikfk_limb, limb_control_names
```

Add a module-level constant next to `LIMB_LOCK` / `AUTO_COLLAR`, so `build()` and the manifest cannot disagree:

```python
#: The FK labels `build()` passes to `build_ikfk_limb`. Named once so the
#: manifest and the build read the same list.
LIMB_LABELS = ("upper", "lower", "hand")
```

Replace `controls = ("ik", "pole")` with:

```python
    controls = ("collar", *limb_control_names(labels=LIMB_LABELS))
```

and in `build()`, replace the literal at the `build_ikfk_limb` call (`arm.py:215`):

```python
            labels=LIMB_LABELS,
```

- [ ] **Step 5: Run the arm suite**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && set MAYA_PLUG_IN_PATH=%CD%\src\plugins\python;%MAYA_PLUG_IN_PATH% && mayapy -m pytest tests/integration/trigger/test_arm_trigger.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/systems/limb.py src/python/tik/trigger/modules/arm/arm.py tests/integration/trigger/test_arm_trigger.py
git commit -m "feat(trigger): the limb system names the controller roles it builds; arm declares all six"
```

---

### Task 6: `base`, `fkchain` and `twist` declare their controls

The bug the whole plan exists for: `fkchain` offers an empty combo because its controllers depend on `segments`.

**Files:**
- Modify: `src/python/tik/trigger/modules/base/base.py:17`
- Modify: `src/python/tik/trigger/modules/fkchain/fkchain.py:29-33`
- Modify: `src/python/tik/trigger/modules/twist/twist.py` (class attributes, beside `outputs`)
- Test: `tests/unit/test_core_trigger.py`

**Interfaces:**
- Consumes: `Module.control_names` from Task 3.
- Produces: nothing new. `FkChain.control_names(settings)` returns `("fk0", ..., f"fk{segments-1}")`; `Base.controls == ("root",)`; `Twist.controls == ()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_core_trigger.py`, in the anim-spaces section:

```python
def test_shipped_modules_declare_their_controls():
    """The bug this replaces: fkchain offered an empty control combo."""
    from tik.trigger.core import get_module

    assert get_module("base").control_names() == ("root",)
    assert get_module("twist").control_names() == ()
    assert get_module("fkchain").control_names({"segments": 4}) == (
        "fk0",
        "fk1",
        "fk2",
        "fk3",
    )
```

If `get_module` is already imported at the top of the file, use that import instead of the local one.

- [ ] **Step 2: Run the test and watch it fail**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_core_trigger.py::test_shipped_modules_declare_their_controls -v
```

Expected: FAIL — `assert () == ('root',)`.

- [ ] **Step 3: Declare them**

`src/python/tik/trigger/modules/base/base.py` — after `outputs = ("root",)`:

```python
    controls = ("root",)
```

`src/python/tik/trigger/modules/fkchain/fkchain.py` — after `output_names`, add the sibling classmethod:

```python
    @classmethod
    def control_names(cls, settings=None):
        """One FK controller per segment: ``build`` skips the last joint."""
        count = int((settings or {}).get("segments", cls.segments.default))
        return tuple(f"fk{index}" for index in range(count))
```

`src/python/tik/trigger/modules/twist/twist.py` — after its `outputs` declaration:

```python
    controls = ()  # the joints ride an aimed frame; nothing here is animated
```

- [ ] **Step 4: Run the unit suite**

```
make tests-unit
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/modules/base/base.py src/python/tik/trigger/modules/fkchain/fkchain.py src/python/tik/trigger/modules/twist/twist.py tests/unit/test_core_trigger.py
git commit -m "feat(trigger): base, fkchain and twist declare their controls"
```

---

### Task 7: Optional start and end controllers on the ribbon

The ribbon pins its ends straight to sockets, so its only controllers are the mids. Two checkboxes add a controller at either end — and the twist extraction has to follow the new driver, or rotating a start controller would move the ribbon end without twisting it.

**Files:**
- Modify: `src/python/tik/trigger/modules/ribbon/ribbon.py:44-58` (fields), `:59-64` (`output_names` neighbourhood), `:72-125` (`build`)
- Test: `tests/unit/test_ribbon_trigger.py`

**Interfaces:**
- Consumes: `Module.control_names` from Task 3.
- Produces: `RibbonModule.start_controller` / `RibbonModule.end_controller` — `BoolField`, default `False`. `RibbonModule.control_names(settings)` returns `("start"?, "mid0" … f"mid{mid_count-1}", "end"?)` in that order.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_ribbon_trigger.py`. Follow whatever build fixture that file already uses for a ribbon instance; the assertions are:

```python
def test_ribbon_declares_its_controls():
    from tik.trigger.core import get_module

    module_cls = get_module("ribbon")
    assert module_cls.control_names({"mid_count": 2}) == ("mid0", "mid1")
    assert module_cls.control_names(
        {"mid_count": 1, "start_controller": True, "end_controller": True}
    ) == ("start", "mid0", "end")


def test_ribbon_end_controllers_are_off_by_default():
    """No existing ribbon changes shape."""
    from tik.trigger.core import get_module

    module = get_module("ribbon")()
    assert module.start_controller is False
    assert module.end_controller is False


def test_ribbon_builds_end_controllers_when_asked(ribbon_rig_factory):
    ctx = ribbon_rig_factory(
        {"mid_count": 1, "start_controller": True, "end_controller": True}
    )
    assert ctx.controller_by_role("start") is not None
    assert ctx.controller_by_role("end") is not None


def test_ribbon_builds_no_end_controllers_by_default(ribbon_rig_factory):
    ctx = ribbon_rig_factory({"mid_count": 1})
    assert ctx.controller_by_role("start") is None
    assert ctx.controller_by_role("end") is None
```

`ribbon_rig_factory` is a fixture you add to that file: it builds one ribbon with the given settings, wired `start` and `end` to a `base` module's `root` output (the ribbon's `end` input is **required**, so a solo ribbon cannot build), and returns the `ModuleRig` from `report.rigs[<ribbon instance id>]`. Model it on the `_solo` helper in `tests/integration/trigger/test_module_ground_rules.py` — create the `base` first, create the ribbon with `parent=ParentRef(body.instance_id, "root")`, then `scene.set_input(ribbon.instance_id, "end", f"{body.key}.root")` and `scene.write_settings(ribbon.instance_id, settings)` before building.

- [ ] **Step 2: Run the tests and watch them fail**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_ribbon_trigger.py -v
```

Expected: FAIL — `AttributeError: 'RibbonModule' object has no attribute 'start_controller'`.

- [ ] **Step 3: Add the fields and the manifest**

In `src/python/tik/trigger/modules/ribbon/ribbon.py`, after `mid_count`:

```python
    start_controller = BoolField(
        False, label="Start Controller", help="An animatable control at the start pin"
    )
    end_controller = BoolField(
        False, label="End Controller", help="An animatable control at the end pin"
    )
```

and beside `output_names`:

```python
    @classmethod
    def control_names(cls, settings=None):
        """The end controls, when asked for, around one control per mid."""
        settings = settings or {}
        count = int(settings.get("mid_count", cls.mid_count.default))
        start = settings.get("start_controller", cls.start_controller.default)
        end = settings.get("end_controller", cls.end_controller.default)
        return (
            *(("start",) if start else ()),
            *(f"mid{index}" for index in range(count)),
            *(("end",) if end else ()),
        )
```

- [ ] **Step 4: Build them, and move the twist onto the driver**

In `build()`, after the two sockets are created and before `tm.Ribbon.create`, add a helper and use it for both ends:

```python
        def end_control(role, socket, guide):
            """A control between the socket and the pin, when asked for.

            Driven through its offset group, never parented under the socket:
            control_grp holds nothing but controllers and their offsets.
            """
            control = rig.controller(
                role,
                shape="Circle",
                size=self.controller_size,
                match=guide,
                mirror="behaviour",
            )
            tm.MatrixConstraint.create(socket, control.offset, maintain_offset=True)
            return control.transform

        start_driver = (
            end_control("start", start_socket, start_guide)
            if self.start_controller
            else start_socket
        )
        end_driver = (
            end_control("end", end_socket, end_guide)
            if self.end_controller
            else end_socket
        )
```

Pin to the drivers:

```python
        ribbon.pin_start(start_driver)
        ribbon.pin_end(end_driver)
```

And in the `if self.twist:` block, read the drivers rather than the sockets — otherwise rotating a start controller moves the ribbon end without twisting it, and the ends and the roll disagree:

```python
            reference = (
                rig.socket("reference")
                if rig.instance.inputs.get("reference")
                else start_socket.parent
            )
            if reference is not None:
                (
                    twist_plug(start_driver, reference, name=rig.name("startTwist"))
                    >> ribbon.start_twist
                )
            (
                twist_plug(end_driver, start_driver, name=rig.name("endTwist"))
                >> ribbon.end_twist
            )
```

The `reference` fallback stays `start_socket.parent`: it is the frame the start twist is *measured against*, which must not move with the control being measured.

- [ ] **Step 5: Run the ribbon tests**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_ribbon_trigger.py -v
```

Expected: PASS.

- [ ] **Step 6: Run the wider ribbon coverage**

```
make tests-unit
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && set MAYA_PLUG_IN_PATH=%CD%\src\plugins\python;%MAYA_PLUG_IN_PATH% && mayapy -m pytest tests/integration/trigger/test_twist_ribbon_limblock.py -v
```

Expected: PASS. Both controllers default off, so no existing ribbon changes shape.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/modules/ribbon/ribbon.py tests/unit/test_ribbon_trigger.py
git commit -m "feat(ribbon): optional start and end controllers, with the twist reading them"
```

---

### Task 8: `Session.validate()` reports module problems

`Session.validate()` validates actions only, so a broken anim space is invisible until the build. The window's *Validate Session* action already logs whatever it returns.

**Files:**
- Modify: `src/python/tik/trigger/session.py:452-478`
- Test: `tests/unit/test_session_trigger.py`

**Interfaces:**
- Consumes: `Module.warnings()` and `Module.validate()` from Task 3.
- Produces: `Session._module_problems(self) -> list[str]` — one line per module problem, `validate()` entries as `"<key>: <problem>"` and `warnings()` entries as `"warning: <key>: <problem>"`. Appended to `Session.validate()`'s existing list.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_session_trigger.py`:

```python
def test_validate_reports_a_module_warning():
    """A broken space is caught before Build, not during it."""
    from tik.trigger.core import get_module

    session = Session()
    scene = session.guides
    chain = scene.create_guides(get_module("fkchain")(name="tail"))
    scene.write_settings(
        chain.instance_id,
        {
            "segments": 2,
            "anim_spaces": [{"control": "fk5", "mode": "parent", "label": "world"}],
        },
    )
    problems = session.validate()
    assert any("fk5" in item and item.startswith("warning:") for item in problems)
```

Match the file's existing way of getting a `Session` with guides — if its tests build one through a fixture, use that fixture rather than constructing a bare `Session()`.

- [ ] **Step 2: Run the test and watch it fail**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_session_trigger.py::test_validate_reports_a_module_warning -v
```

Expected: FAIL — the assertion finds nothing; `validate()` returns action problems only.

- [ ] **Step 3: Add the module pass**

In `src/python/tik/trigger/session.py`, add the helper directly before `validate`:

```python
    def _module_problems(self) -> list[str]:
        """Problems and warnings from every module in the guide document.

        The rigger should not have to press Build to find out that a setting
        change orphaned an animation space.
        """
        problems: list[str] = []
        for entry in self.document.guides.modules:
            try:
                module_cls = registry.get_module(entry.module_type)
            except Exception:  # an unregistered type is the runner's report
                continue
            module = module_cls(
                instance_id=entry.instance_id,
                name=entry.name,
                side=entry.side,
                settings=entry.settings,
            )
            module.guide_pairs = list(entry.pairs)
            problems.extend(f"{entry.key}: {item}" for item in module.validate())
            problems.extend(f"warning: {entry.key}: {item}" for item in module.warnings())
        return problems
```

and append its result at the end of `validate`, replacing the final `return problems`:

```python
        problems.extend(self._module_problems())
        return problems
```

- [ ] **Step 4: Run the unit suite**

```
make tests-unit
```

Expected: PASS. If a pre-existing session test now reports extra problems, that is `validate()` doing its new job — read the message and fix the fixture, not the feature.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/session.py tests/unit/test_session_trigger.py
git commit -m "feat(trigger): Session.validate reports module problems and warnings"
```

---

### Task 9: The properties form repaints when the manifest moves

`_topology()` snapshots what a settings change might alter and refreshes the form when it moved. Without the manifest in that snapshot, dropping `segments` from 6 to 3 leaves the control combo offering `fk0..fk5` until the panel is reselected.

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/properties.py:66-75`
- Test: `tests/ui/test_guide_designer.py`

**Interfaces:**
- Consumes: `Module.control_names` from Task 3.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_guide_designer.py`, following the file's existing designer/chain fixtures:

```python
def test_changing_segments_repaints_the_control_choices(designer_with_chain):
    """The anim-space combo must not offer controls the module stopped building."""
    designer, chain = designer_with_chain
    designer.form.widget("segments").setValue(2)
    combo_choices = designer.form._resolve_choices("control_names")
    assert combo_choices == ("fk0", "fk1")
```

Use whatever fixture the file already provides for "a designer with an fkchain selected" — around `tests/ui/test_guide_designer.py:475` there is an existing test that does `designer.form.widget("segments").setValue(4)`; reuse its setup.

- [ ] **Step 2: Run the test and watch it fail**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_guide_designer.py::test_changing_segments_repaints_the_control_choices -v
```

Expected: FAIL — the form was not refreshed, so its target still carries the old `segments`.

- [ ] **Step 3: Add the manifest to the snapshot**

In `src/python/tik/trigger/ui/designer/properties.py`:

```python
    @staticmethod
    def _topology(handle) -> tuple:
        """What a settings change might alter: ports, controls and guide count."""
        module_cls = handle.module_class
        settings = handle.settings
        return (
            tuple(module_cls.input_names(settings)),
            tuple(module_cls.output_names(settings)),
            tuple(module_cls.control_names(settings)),
            len(handle.instance.guides),
        )
```

- [ ] **Step 4: Run the UI suite**

```
make tests-ui
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/ui/designer/properties.py tests/ui/test_guide_designer.py
git commit -m "feat(designer): repaint the properties form when a setting moves the control manifest"
```

---

### Task 10: The drift guard

The test that makes this design self-enforcing: a module that builds a controller it did not declare fails CI.

**Files:**
- Modify: `tests/integration/trigger/test_module_ground_rules.py`

**Interfaces:**
- Consumes: every module's `control_names` from Tasks 5–7; `Controller` and `tags` are already imported in this file.
- Produces: nothing consumed elsewhere.

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/trigger/test_module_ground_rules.py`. First a settings-aware builder beside `_solo` — the existing helper takes no settings and cannot wire a second required input, which `ribbon` has:

```python
#: Settings each shipped module is checked at. A type absent from this mapping
#: is checked once, at its defaults.
CONTROL_VARIATIONS = {
    "fkchain": [{"segments": 1}, {"segments": 5}],
    "ribbon": [
        {"mid_count": 0},
        {"mid_count": 2, "start_controller": True, "end_controller": True},
    ],
}


def _shipped_module_types():
    """The modules this repo ships, ignoring anything a test registered."""
    from tik.trigger.core import registry

    return sorted(
        cls.module_type
        for cls in registry.iter_modules()
        if cls.__module__.startswith("tik.trigger.modules.")
    )


def _built_with(module_type, settings):
    """Build one instance under a base, with every required input wired."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    body = scene.create_guides(get_module("base")(name="body"))
    module_cls = get_module(module_type)
    primary = module_cls.primary_input()
    instance = scene.create_guides(
        module_cls(name=module_type),
        parent=(
            ParentRef(body.instance_id, "root") if primary is not None else None
        ),
    )
    for declared in module_cls.inputs:
        if declared.optional or (primary is not None and declared.name == primary.name):
            continue
        scene.set_input(instance.instance_id, declared.name, f"{body.key}.root")
    if settings:
        scene.write_settings(
            instance.instance_id,
            {**scene.read_settings(instance.instance_id), **settings},
        )
    report = Builder().build(
        document=scene.document, rig_name="rules", afterlife="keep"
    )
    return report.rigs[instance.instance_id]


def _built_control_roles(ctx):
    """Roles tagged on the controllers a build created, tweaks excluded.

    A tweak is parented under its main and follows it, so a space switch on
    one would fight the parent it hangs from -- it is never in a manifest.
    """
    return sorted(
        role
        for role in (
            controller.transform.meta.get(tags.ROLE)
            for controller in ctx.controllers
        )
        if role and not role.endswith("_tweak")
    )


@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_every_module_declares_exactly_the_controllers_it_builds(module_type):
    """Rule: the control manifest is what the module builds, minus tweaks.

    Equality, not subset. A control the module forgot to declare is invisible
    in the anim-space table -- the exact bug fkchain and ribbon shipped with.
    """
    module_cls = get_module(module_type)
    for settings in CONTROL_VARIATIONS.get(module_type, [{}]):
        ctx = _built_with(module_type, settings)
        declared = sorted(module_cls.control_names(ctx.instance.settings))
        assert _built_control_roles(ctx) == declared, (
            f"{module_type} at {settings or 'defaults'}: manifest and build disagree"
        )
```

- [ ] **Step 2: Run it and see what it catches**

```
set PYTHONPATH=%CD%\src\python;%PYTHONPATH% && set MAYA_PLUG_IN_PATH=%CD%\src\plugins\python;%MAYA_PLUG_IN_PATH% && mayapy -m pytest tests/integration/trigger/test_module_ground_rules.py -k declares_exactly -v
```

Expected: PASS for all five shipped modules if Tasks 5–7 were done correctly. **A failure here is a finding about the module, not a test to relax** — the file's own docstring says so. Fix the module's `control_names` (or the controller it forgot to declare) and re-run.

The one judgement call: if `arm`'s `pole_tweak` or `ik_tweak` turns up in `_built_control_roles`, confirm they end in `_tweak` and are being stripped. If a module creates a helper controller under some other naming convention, do **not** widen the filter — declare that controller in the manifest, since the animator can select it.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/trigger/test_module_ground_rules.py
git commit -m "test(trigger): a module's control manifest must equal the controllers it builds"
```

---

### Task 11: Document the rule, then verify the whole thing

**Files:**
- Modify: `CLAUDE.md` (the "Module Ground Rules" section)
- Modify: `AI/coding_rules.md` (module ground rules)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Add the rule to `CLAUDE.md`**

In the **Module Ground Rules** section, after the sentence about sockets, add:

```markdown
A module also declares the **controllers it builds** — `controls`, or
`control_names(settings)` when a setting drives them, the same shape as
`outputs` / `output_names(settings)`. Every declared control can host an
animation space; tweak controllers are excluded by construction. The manifest
must equal what `build()` actually creates, minus tweaks —
`tests/integration/trigger/test_module_ground_rules.py` enforces it.
```

- [ ] **Step 2: Add the same rule to `AI/coding_rules.md`**

Add it to that file's module ground rules in the same words, so an agent reading either file learns it.

- [ ] **Step 3: Confirm no `space_controls` survives in live code**

```
grep -rn "space_controls" --include=*.py --include=*.md src tests AI CLAUDE.md
```

Expected: no matches. Historical plans and specs under `docs/superpowers/` keep theirs.

- [ ] **Step 4: Run everything**

```
make lint
make tests-unit
make tests-integration
make tests-ui
```

Expected: all green. Paste the actual tail of each run into the completion report — do not claim a pass you have not seen.

- [ ] **Step 5: Manual check in Maya (the acceptance test)**

The whole point of the work, verified by hand in a running Maya:

1. Open the Trigger window, new session, add an `fkchain`.
2. In its properties, open the **Spaces** fold and add a row. **The control combo must now offer `fk0`, `fk1`, `fk2`** — this was empty before.
3. Pick `fk2`, mode `parent`, label `world`. A gold `fk2_world` port appears on the module in the graph.
4. Add a `base`, wire `base.root` into that port, press **Build**. The `fk2` controller carries a `parentSwitch` enum with a single `world` entry.
5. Back in the designer, lower `segments` to 2. The row survives, its wire survives, the combo now reads `fk2 (missing)`, and *Validate Session* logs a warning. Build again: the rig builds, with a warning in the log.
6. Raise `segments` back to 3 and rebuild: the space switch is back.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md AI/coding_rules.md
git commit -m "docs: the control manifest is a module ground rule"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| 1.1 Declaration (`controls` / `control_names`, column resolver) | 3 |
| 1.2 Every controller, minus tweaks | 3 (rule), 10 (enforcement) |
| 1.3 Roles owned by a system (`limb_control_names`) | 5 |
| 2.1 The row survives | 3 (ports from rows), 2 (combo does not rewrite it) |
| 2.2 `validate()` vs `warnings()` | 3 |
| 2.3 Surfaces: Session.validate / build log / properties table | 8, 4, 2 |
| 3.1 Callable `choices_from` | 1 |
| 3.2 Stale value not silently rewritten | 2 |
| 3.3 `_topology` includes the manifest | 9 |
| 4 Module manifests (base, arm, fkchain, twist, ribbon) | 5, 6, 7 |
| 4.1 Ribbon start/end controllers + twist follows the driver | 7 |
| 5.1 Drift guard | 10 |
| 5.2 Remaining tests | 1, 2, 3, 4, 6, 7, 8, 9 |
| Migration: no `space_controls` shim | 3 (removed in one commit), 11 (verified) |

No gaps.

**Type consistency:** `control_names(settings=None) -> tuple[str, ...]` is used identically in Tasks 3, 5, 6, 7, 9 and 10. `warnings() -> list[str]` in Tasks 3, 4 and 8. `connect_space(...) -> bool` is defined and consumed only in Task 4. `_resolve_choices(attr) -> tuple` is produced in Task 1 and consumed in Tasks 2 and 9. `MISSING_SUFFIX` is produced in Task 2 and referenced nowhere else by name.
