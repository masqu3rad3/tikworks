# Movable Pivots Without Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a rigger give any offered control a movable pivot without inventing a named preset.

**Architecture:** One per-copy `ListField` on `Module` holds the ticked control roles. A new
`Module.pivot_wanted(role)` folds "ticked or carrying preset rows" into one question, and the
builder seam's existing gate calls it instead of `pivot_labels`. Two `FormBuilder`
generalizations make a `ListField` picker render in the Guide Designer at all, and make an
unfillable one hide like an unfillable table.

**Tech Stack:** Python 3.10+, Maya 2024+ (tests run under `mayapy`), PySide/Qt via
`tik.shared.ui.Qt`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-12-movable-pivots-without-presets-design.md`

## Global Constraints

- `tik/trigger/core` is pure Python: no Maya, no Qt imports (`tests/unit/test_import_boundaries.py`).
- No third-party dependencies: stdlib and Maya-bundled modules only.
- Never call `maya.cmds` or `maya.api.OpenMaya` outside `src/python/tik/maya/`; use `import tik.maya as tm`.
- Preferences may never reach the build path: nothing under `core`, `modules`, `systems`, `maya`, `actions`, `guides` may import `tik.trigger.config.prefs`.
- A preset row **implies** a tick. The implication runs one way only; a tick never invents rows.
- Nothing is ticked by default: `movable_pivots` defaults to `[]` on every module.
- No `.tr` schema bump. The field fills in through `per_copy_defaults` on read.
- Run commands from the repo root `D:\dev\tikworks`.

**Test commands** (copy verbatim):

```bash
PYTHONPATH=src/python mayapy -m pytest <path> -q          # one file
PYTHONPATH=src/python mayapy tests/unit/invoke.py          # whole unit suite
PYTHONPATH=src/python mayapy tests/integration/invoke.py   # whole integration suite
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src/python mayapy -m pytest tests/ui -q
python -m black --check src/python/tik tests && python -m isort --check-only src/python/tik tests && python -m flake8 src/python/tik tests
```

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/python/tik/trigger/core/module.py` | the field, `pivot_wanted`, the stale-tick warning | modify |
| `src/python/tik/trigger/maya/build.py` | the builder seam's gate | modify (1 line) |
| `src/python/tik/shared/ui/fields.py` | `ListField` picker resolution, `_field_is_dead` | modify |
| `tests/unit/test_pivot_trigger.py` | `pivot_wanted`, per-copy qualification | modify |
| `tests/integration/trigger/test_pivot_build_trigger.py` | what the builder makes for each of the four combinations | modify |
| `tests/ui/test_pivot_picker.py` | the Designer renders a picker for the new field | create |
| `tests/ui/test_empty_sections.py` | an unfillable list hides its fold | modify |
| `tests/integration/trigger/test_control_module_trigger.py` | the control module's pivot cases | modify |

---

### Task 1: `movable_pivots` and `pivot_wanted`

**Files:**
- Modify: `src/python/tik/trigger/core/module.py` (declare beside `pivot_presets`; method beside `pivot_labels` at :568)
- Test: `tests/unit/test_pivot_trigger.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Module.movable_pivots` (a `ListField` of `str`, per copy, default `[]`) and
  `Module.pivot_wanted(self, role: str) -> bool`. Task 2 calls `pivot_wanted` on a per-copy
  view; Task 3's UI test reads `movable_pivots.choices_from == "pivot_control_names"`;
  Task 4 adds a warning that reads `self.movable_pivots`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_pivot_trigger.py`:

```python
# ------------------------------------------------- a tick, not a preset row
class TickToy(PivotToy):
    """Offers a pivot on ``main`` and ships no preset rows."""

    pivot_presets = Module.pivot_presets.with_default([])

    def build(self, rig):
        rig.controller("main", match=rig.guide("hand"))
        rig.output("root", rig.bind_joint("root", match=rig.guide("root")))


def test_nothing_is_wanted_by_default():
    assert TickToy(name="toy").pivot_wanted("main") is False


def test_a_tick_wants_a_pivot():
    toy = TickToy(name="toy", settings={"movable_pivots": ["main"]})
    assert toy.pivot_wanted("main") is True


def test_a_preset_row_wants_one_without_a_tick():
    """Every session written before the tick existed has rows and no ticks."""
    toy = TickToy(
        name="toy", settings={"pivot_presets": [{"control": "main", "label": "tip"}]}
    )
    assert toy.movable_pivots == []
    assert toy.pivot_wanted("main") is True


def test_a_tick_on_one_control_leaves_another_alone():
    toy = TickToy(name="toy", settings={"movable_pivots": ["main"]})
    assert toy.pivot_wanted("other") is False


def test_the_tick_belongs_to_the_copy():
    """Per copy like every field but ``copies``: each view sees its own."""
    toy = TickToy(
        name="toy",
        settings={
            "copies": [
                {"slug": "", "name": "a", "movable_pivots": ["main"]},
                {"slug": "c1", "name": "b", "movable_pivots": []},
            ]
        },
    )
    assert toy.for_copy("").pivot_wanted("main") is True
    assert toy.for_copy("c1").pivot_wanted("main") is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src/python mayapy -m pytest tests/unit/test_pivot_trigger.py -q -k "wanted or tick"`
Expected: FAIL with `AttributeError: 'TickToy' object has no attribute 'pivot_wanted'`.

- [ ] **Step 3: Declare the field**

In `src/python/tik/trigger/core/module.py`, insert immediately **before** the existing
`pivot_presets = TableField(...)` declaration. `ListField` is already imported.

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
    """Which offered controls actually get a pivot.

    Declaring ``pivot_controls`` is the offer; this is the acceptance. Above
    ``pivot_presets`` in the fold because "does this control have a movable
    pivot" comes before "and what named positions does it have" -- ``last=True``
    keeps the two in declaration order.
    """
```

- [ ] **Step 4: Add `pivot_wanted`**

In the same file, directly after `pivot_labels` (ends at :579):

```python
    def pivot_wanted(self, role: str) -> bool:
        """Whether ``role`` gets a movable pivot: ticked, or carrying presets.

        A preset row implies the tick rather than requiring it. A row that
        built no pivot would be a row that does nothing, and every session
        written before the tick existed has rows and no ticks -- so the
        implication is also what makes this change need no migration.
        """
        return role in (self.movable_pivots or ()) or bool(self.pivot_labels(role))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=src/python mayapy -m pytest tests/unit/test_pivot_trigger.py -q`
Expected: PASS, whole file.

- [ ] **Step 6: Run the full unit suite**

Run: `PYTHONPATH=src/python mayapy tests/unit/invoke.py`
Expected: all pass. A new field on `Module` touches `test_core_trigger.py` and
`test_document_trigger.py`; if either asserts an exact field list, add `movable_pivots` to it.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/core/module.py tests/unit/test_pivot_trigger.py
git commit -m "Movable pivots: a tick list beside the preset rows"
```

---

### Task 2: The builder gate

**Files:**
- Modify: `src/python/tik/trigger/maya/build.py:759-764`
- Test: `tests/integration/trigger/test_pivot_build_trigger.py`

**Interfaces:**
- Consumes: `Module.pivot_wanted(role)` from Task 1.
- Produces: no new names. After this task a ticked control builds a pivot controller named
  `<control>_pivot_ctrl` and carries no `pivotPreset` attribute.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_pivot_build_trigger.py`. The file's existing `_build`
and `_pivots` helpers are used as-is.

```python
def test_a_tick_with_no_rows_builds_a_bare_pivot():
    """The feature: showPivot and a pivot to move, with no enum at all."""
    rig = _build("fkchain", {"segments": 3, "movable_pivots": ["fk1"]})

    names = _pivots(rig)
    assert len(names) == 1
    assert "fk1_pivot_ctrl" in names[0]
    assert not rig.controller_by_role("fk1").transform.has_attr("pivotPreset")


def test_a_tick_and_rows_together_build_one_pivot_with_its_enum():
    rig = _build(
        "fkchain",
        {
            "segments": 3,
            "movable_pivots": ["fk1"],
            "pivot_presets": [{"control": "fk1", "label": "tip"}],
        },
    )

    assert len(_pivots(rig)) == 1
    assert rig.controller_by_role("fk1").transform.has_attr("pivotPreset")


def test_a_tick_on_one_control_builds_nothing_on_the_others():
    rig = _build("fkchain", {"segments": 3, "movable_pivots": ["fk1"]})

    assert all("fk0_pivot" not in name for name in _pivots(rig))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src/python mayapy -m pytest tests/integration/trigger/test_pivot_build_trigger.py -q`
Expected: `test_a_tick_with_no_rows_builds_a_bare_pivot` FAILS on `len(names) == 1` (got 0) —
the tick is stored but the gate still reads `pivot_labels`.

- [ ] **Step 3: Change the gate**

In `src/python/tik/trigger/maya/build.py`, in the pivot loop at :759, replace

```python
                    if main is None or not view.pivot_labels(role):
```

with

```python
                    if main is None or not view.pivot_wanted(role):
```

Update the comment above the loop (:751) to read "A pivot per declared role the rigger asked
for -- a tick, or preset rows, which imply one:".

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src/python mayapy -m pytest tests/integration/trigger/test_pivot_build_trigger.py -q`
Expected: PASS, including the four pre-existing tests (`arm` still builds its hand pivot from
its three default rows; an emptied arm still builds none).

- [ ] **Step 5: Run the full integration suite**

Run: `PYTHONPATH=src/python mayapy tests/integration/invoke.py`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/maya/build.py tests/integration/trigger/test_pivot_build_trigger.py
git commit -m "Movable pivots: the builder gate reads pivot_wanted"
```

---

### Task 3: The two FormBuilder generalizations

**Files:**
- Modify: `src/python/tik/shared/ui/fields.py` (`_make_widget`'s list branch at :747; `_table_is_dead` at :839; its call site at :622)
- Create: `tests/ui/test_pivot_picker.py`
- Modify: `tests/ui/test_empty_sections.py`

**Interfaces:**
- Consumes: `Module.movable_pivots` from Task 1 (only the UI tests touch it; the `fields.py`
  changes know nothing about pivots).
- Produces: `FormBuilder._field_is_dead(name, field)` replacing `_table_is_dead`, covering both
  `table` and `list` fields. No other module calls either name — verify with
  `grep -rn "_table_is_dead" src tests`.

- [ ] **Step 1: Write the failing picker test**

Create `tests/ui/test_pivot_picker.py`:

```python
"""A module's list field renders as a picker in the Guide Designer.

Spec: docs/superpowers/specs/2026-09-12-movable-pivots-without-presets-design.md

``session_view`` injects a ``list_choices`` callback for the pipeline's action
panel; the Designer's module forms never did, so a ``ListField`` on a module
fell through to the comma-separated line edit. A ``TableField`` column has
always resolved ``choices_from`` off the target -- a list now does the same.
"""

from tik.core.fields import ListField, Schema
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.Qt import QtCore, QtWidgets


class Toy(Schema):
    """A list whose options are resolved from the target, with no callback."""

    roles: tuple = ("ik", "fk0")
    picked = ListField([], item_type=str, choices_from="roles")


def _rows(widget):
    return [widget.list.item(row) for row in range(widget.list.count())]


def test_a_list_field_resolves_its_choices_off_the_target(qapp):
    """No list_choices callback: the target answers, as a column's does."""
    form = FormBuilder(Toy())
    widget = form.widget("picked")

    assert not isinstance(widget, QtWidgets.QLineEdit)
    assert [item.text() for item in _rows(widget)] == ["ik", "fk0"]


def test_a_role_is_its_own_label_and_its_own_value(qapp):
    form = FormBuilder(Toy())

    row = _rows(form.widget("picked"))[0]
    assert row.text() == "ik"
    assert row.data(QtCore.Qt.UserRole) == "ik"


def test_ticking_a_row_writes_the_role(qapp):
    target = Toy()
    form = FormBuilder(target)

    _rows(form.widget("picked"))[1].setCheckState(QtCore.Qt.Checked)

    assert target.picked == ["fk0"]


def test_an_injected_callback_still_wins(qapp):
    """The pipeline's action panel keeps supplying its own options."""
    form = FormBuilder(Toy(), list_choices=lambda _key: [("Spine", "aaa")])

    assert [item.text() for item in _rows(form.widget("picked"))] == ["Spine"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src/python mayapy -m pytest tests/ui/test_pivot_picker.py -q`
Expected: FAIL — `test_a_list_field_resolves_its_choices_off_the_target` gets a `QLineEdit`,
because the branch at :747 requires `self.list_choices`.

- [ ] **Step 3: Let a list field resolve its own choices**

In `src/python/tik/shared/ui/fields.py`, replace the list branch's condition and options source:

```python
        elif kind == "list" and getattr(field, "choices_from", ""):
            source = field.choices_from
            # An injected callback wins -- the pipeline's action panel offers
            # modules by display key and stores their ids, which no attribute
            # on the target can answer. Without one the target answers for
            # itself, exactly as a table column's choices_from already does,
            # and a plain role is its own label.
            options = (
                (lambda key=source: self.list_choices(key))
                if self.list_choices
                else (lambda key=source: [(one, one) for one in self._resolve_choices(key)])
            )
            widget = CheckListEditor(
                options,
                filterable=getattr(field, "filterable", False),
            )
```

The rest of that branch (the `valueChanged` connection and the `only_selected` companion) is
unchanged.

- [ ] **Step 4: Run the picker test to verify it passes**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src/python mayapy -m pytest tests/ui/test_pivot_picker.py -q`
Expected: PASS, 4 tests.

- [ ] **Step 5: Write the failing empty-section test**

Append to `tests/ui/test_empty_sections.py`:

```python
class ListToy(Schema):
    """A tick list whose options are resolved from the target."""

    options: tuple = ()
    picked = ListField([], item_type=str, group=GROUP, choices_from="options")


def test_a_list_nobody_can_tick_renders_no_widget(qapp):
    """Same rule as a table nobody can fill, same reason."""
    form = _form(ListToy(), qapp)
    with pytest.raises(KeyError):
        form.widget("picked")


def test_an_unfillable_lists_fold_hides_with_it(qapp):
    form = _form(ListToy(), qapp)
    fold = form._groups.get("Rows")
    assert fold is None or fold.isHidden()


def test_a_list_holding_a_value_always_renders(qapp):
    """A setting that narrowed the options must never strand a tick."""
    form = _form(ListToy(settings={"picked": ["gone"]}), qapp)
    assert form.widget("picked") is not None
```

Add `ListField` to the file's existing `from tik.core.fields import ...` line.

- [ ] **Step 6: Run it to verify it fails**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src/python mayapy -m pytest tests/ui/test_empty_sections.py -q`
Expected: FAIL — `test_a_list_nobody_can_tick_renders_no_widget` finds a widget, because only
tables are skipped.

- [ ] **Step 7: Generalize the skip**

In `src/python/tik/shared/ui/fields.py`, rename `_table_is_dead` to `_field_is_dead` and widen
it:

```python
    def _field_is_dead(self, name: str, field) -> bool:
        """A widget nobody could add to, that holds nothing to remove.

        For a table the test is per *column*: a column whose options are fixed
        and empty is what makes a row unfillable, and a table may carry a
        static column beside a resolved one. For a list it is the one
        ``choices_from``. Either holding a value always renders, whatever its
        options say -- otherwise a setting that narrows the candidates would
        strand a value where the rigger cannot reach it.
        """
        if getattr(self._target, name, None):
            return False
        if field.type_name == "list":
            source = getattr(field, "choices_from", "")
            return bool(source) and not self._resolve_choices(source)
        source = getattr(field, "rows_from", "")
        if source and not self._resolve_choices(source):
            return True
        return any(
            column.choices_from and not self._resolve_choices(column.choices_from)
            for column in getattr(field, "columns", ())
        )
```

At the call site (:622) drop the type check, since the method now decides per kind:

```python
            for name, field in rows[key]:
                if self._field_is_dead(name, field):
                    # No widget and no label, so the fold pass below finds
                    # nothing in this group and closes it.
                    continue
```

Note: a list with no `choices_from` (a plain comma-separated one) is never dead — the guard
returns `False` when `source` is empty.

- [ ] **Step 8: Run both UI files to verify they pass**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src/python mayapy -m pytest tests/ui/test_empty_sections.py tests/ui/test_pivot_picker.py tests/ui/test_kinematics_picker.py -q`
Expected: PASS.

- [ ] **Step 9: Run the whole UI suite**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src/python mayapy -m pytest tests/ui -q`
Expected: all pass. `test_copy_tabs.py` and `test_guide_designer.py` both render module forms
and are the ones that would notice a new widget in the Pivots fold.

- [ ] **Step 10: Commit**

```bash
git add src/python/tik/shared/ui/fields.py tests/ui/test_pivot_picker.py tests/ui/test_empty_sections.py
git commit -m "FormBuilder: a list field resolves its own choices and hides when unfillable"
```

---

### Task 4: The stale-tick warning

**Files:**
- Modify: `src/python/tik/trigger/core/module.py` (`warnings()`, in the block that already checks `pivot_presets` rows around :713-722)
- Test: `tests/unit/test_pivot_trigger.py`

**Interfaces:**
- Consumes: `Module.movable_pivots` from Task 1.
- Produces: a warning string of the form
  `"movable pivot '<control>': control has no movable pivot with the current settings"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_pivot_trigger.py`:

```python
def test_a_tick_on_a_control_the_settings_removed_warns():
    toy = TickToy(name="toy", settings={"movable_pivots": ["gone"]})

    assert any("movable pivot 'gone'" in item for item in toy.warnings())


def test_a_stale_tick_is_never_a_validation_error():
    """A build must not fail over a control the rigger is not using."""
    toy = TickToy(name="toy", settings={"movable_pivots": ["gone"]})

    assert not any("gone" in item for item in toy.validate())


def test_a_stale_tick_is_kept():
    """Lowering a count and raising it again restores the setup."""
    toy = TickToy(name="toy", settings={"movable_pivots": ["gone"]})
    toy.warnings()

    assert toy.movable_pivots == ["gone"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `PYTHONPATH=src/python mayapy -m pytest tests/unit/test_pivot_trigger.py -q -k "stale or tick"`
Expected: `test_a_tick_on_a_control_the_settings_removed_warns` FAILS — `warnings()` returns no
such entry. The other two pass already; they are there to pin what must *not* change.

- [ ] **Step 3: Add the warning**

In `warnings()`, directly after the `for row in self.pivot_presets:` loop (which ends at :722)
and before `shapeable = ...`, reusing the `movable` name already bound above that loop:

```python
        for control in self.movable_pivots:
            if control and control not in movable:
                problems.append(
                    f"movable pivot '{control}': control has no movable pivot "
                    f"with the current settings"
                )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src/python mayapy -m pytest tests/unit/test_pivot_trigger.py -q`
Expected: PASS, whole file.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/core/module.py tests/unit/test_pivot_trigger.py
git commit -m "Movable pivots: a tick on a removed control warns, and is kept"
```

---

### Task 5: The control module's cases, and the docs

**Files:**
- Modify: `tests/integration/trigger/test_control_module_trigger.py`
- Modify: `docs/superpowers/specs/2026-09-12-movable-pivots-without-presets-design.md` (status line)
- Modify: `docs/superpowers/specs/2026-09-11-control-capability-declarations-design.md` (amended-by note)
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: nothing further tasks depend on.

- [ ] **Step 1: Update the control module's pivot tests**

In `tests/integration/trigger/test_control_module_trigger.py`, replace
`test_no_preset_rows_means_no_pivot` with the pair below and keep
`test_a_preset_row_builds_the_pivot` as it stands:

```python
def test_neither_a_tick_nor_a_row_means_no_pivot():
    """Declaring offers a pivot; a tick or a row is what builds it."""
    assert "L_head_root_pivot_ctrl" not in _controls(_build())


def test_a_tick_alone_builds_a_pivot_with_no_presets():
    """The whole point of the control module's 'optional movable pivot'."""
    rig = _build(movable_pivots=["root"])

    assert "L_head_root_pivot_ctrl" in _controls(rig)
    assert not rig.controller_by_role("root").transform.has_attr("pivotPreset")
```

- [ ] **Step 2: Run the file**

Run: `PYTHONPATH=src/python mayapy -m pytest tests/integration/trigger/test_control_module_trigger.py -q`
Expected: PASS, 12 tests.

- [ ] **Step 3: Flip the spec status and record the amendment**

In `docs/superpowers/specs/2026-09-12-movable-pivots-without-presets-design.md`, change
`**Status:** proposed` to `**Status:** implemented`.

In `docs/superpowers/specs/2026-09-11-control-capability-declarations-design.md`, add directly
under its `**Status:**` line:

```markdown
**Amended by:** `2026-09-12-movable-pivots-without-presets-design.md` — §4's closing rule
becomes "declaring is what makes it available; a **tick** is what builds it, and a preset row
implies a tick". §4.1's claimed escape hatch ("adds a row and clears its label") is withdrawn:
`_validate_pivots` has always refused a blank label. The seam and its idempotence guard stand.
```

- [ ] **Step 4: Update CLAUDE.md**

In the tik.trigger status paragraph, find the sentence ending

```
and — when the rigger's `pivot_presets` table has rows for it — a `pivotPreset` enum switching between named positions the rigger places as guides.
```

and append immediately after it:

```
A pivot is built where the rigger ticks the control in `movable_pivots` **or** gives it preset rows (a row implies the tick), so a movable pivot and a set of named positions are two features rather than one.
```

In the tests list, add to the `test_pivot_build_trigger.py` line: `; a tick with no rows builds
a bare pivot`. Add `tests/ui/test_pivot_picker.py` beside `tests/ui/test_kinematics_picker.py`.

- [ ] **Step 5: Run every suite and the linters**

```bash
PYTHONPATH=src/python mayapy tests/unit/invoke.py
PYTHONPATH=src/python mayapy tests/integration/invoke.py
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src/python mayapy -m pytest tests/ui -q
python -m black --check src/python/tik tests && python -m isort --check-only src/python/tik tests && python -m flake8 src/python/tik tests
```

Expected: all green, linters silent.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/trigger/test_control_module_trigger.py docs CLAUDE.md
git commit -m "Movable pivots without presets: control module cases and docs"
```
