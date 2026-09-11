# Control Capability Declarations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A module names the candidate controls for each of the three rigger-facing sections (Anim Spaces, Pivot Presets, Control Shapes), the framework builds pivots where preset rows exist, and a section with no possible candidates does not render.

**Architecture:** Four manifest attributes on `Module`, each with a `*_for_copy` hook and a qualified `*_names` classmethod, replacing two tables that read `control_names` and one hook that dropped its data. `pivot_controls` values gain an optional guide index so a settings-driven module can declare pivots; both readers stop reaching past the hook to the class attribute. A post-`build()` seam in the builder creates the pivot controller, so no module contains pivot code. `FormBuilder` skips a table whose candidate columns resolve empty and that holds no rows.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), PySide (Qt) for UI, `pytest`. No third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-09-11-control-capability-declarations-design.md`

## Global Constraints

- **Layering:** `tik/trigger/core` is pure Python — no Maya, no Qt imports. Enforced by `tests/unit/test_import_boundaries.py`.
- **Consume tik.maya:** no raw `maya.cmds` / `OpenMaya` / `pymel` in tool code outside `tik/maya` itself.
- **No third-party deps:** stdlib and Maya-bundled modules only.
- **Preferences never change the rig:** nothing in `core`, `modules`, `systems`, `maya`, `actions`, `guides` may import the preferences packages.
- **Modules never inherit from other modules** — shared behaviour goes in `tik/trigger/systems/`.
- **The manifest must equal what `build()` creates, minus tweaks** — `tests/integration/trigger/test_module_ground_rules.py` enforces it.
- **Logging convention in core:** `logger = logging.getLogger(__name__)` at module scope.

**Test commands** (run from repo root, Windows PowerShell or Git Bash):
- Unit (under Maya standalone): `make tests-unit`
- Integration (under Maya standalone): `make tests-integration`
- Qt UI (no Maya): `make tests-ui`
- A single unit test file: `mayapy -m pytest tests/unit/test_core_trigger.py -v`
- Lint: `make lint` (black, isort profile=black, flake8). Run before every commit.

---

### Task 1: `space_controls` — the Spaces candidate set

**Files:**
- Modify: `src/python/tik/trigger/core/module.py` (the `controls` block near line 57; the `anim_spaces` TableField near line 103; the `*_for_copy` hooks near line 250; the `*_names` classmethods near line 310)
- Test: `tests/unit/test_core_trigger.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `Module.space_controls: tuple[str, ...] = ()` — class attribute; empty means "all controls".
  - `Module.space_controls_for_copy(settings=None) -> tuple[str, ...]`
  - `Module.space_control_names(settings=None) -> tuple[str, ...]` — qualified per copy.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_core_trigger.py`:

```python
def test_space_controls_defaults_to_every_control():
    """Hosting a space is something any controller can do; a module narrows."""

    class Everything(Module):
        controls = ("a", "b", "c")

    assert Everything.space_control_names({}) == ("a", "b", "c")


def test_space_controls_narrows_when_declared():
    class Narrow(Module):
        controls = ("a", "b", "c")
        space_controls = ("b",)

    assert Narrow.space_control_names({}) == ("b",)


def test_space_controls_follows_a_settings_driven_control_set():
    """The hook sees one copy's settings, like every other *_for_copy."""

    class Dynamic(Module):
        count = IntField(2)

        @classmethod
        def controls_for_copy(cls, settings=None):
            number = int((settings or {}).get("count", 2))
            return tuple(f"fk{index}" for index in range(number))

    assert Dynamic.space_control_names({"count": 3}) == ("fk0", "fk1", "fk2")
```

`IntField` and `Module` are already imported in this file; if `IntField` is not, add it to the existing `from tik.trigger.core import (...)` block.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mayapy -m pytest tests/unit/test_core_trigger.py -k space_controls -v`
Expected: FAIL with `AttributeError: type object 'Everything' has no attribute 'space_control_names'`

- [ ] **Step 3: Declare the attribute**

In `src/python/tik/trigger/core/module.py`, directly after the `controls` declaration:

```python
    #: Controller roles that may host an animation space. Empty means *every*
    #: control -- the one manifest entry whose default is "all", because
    #: hosting a space is something any controller can do, so a module narrows
    #: rather than opts in. A pivot and a shape are offers a module makes.
    space_controls: tuple[str, ...] = ()
```

- [ ] **Step 4: Add the hook and the qualified resolver**

After `controls_for_copy`:

```python
    @classmethod
    def space_controls_for_copy(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles of *one copy* that may host an animation space.

        Falls back to every control the copy builds, which is what makes an
        undeclared module behave exactly as it did before this hook existed.
        """
        if cls.space_controls:
            return tuple(cls.space_controls)
        return tuple(cls.controls_for_copy(settings))
```

After `control_names`:

```python
    @classmethod
    def space_control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles that may host an animation space, qualified per copy."""
        return tuple(
            cls.qualify(slug, name)
            for slug, one in cls._copy_settings(settings)
            for name in cls.space_controls_for_copy(one)
        )
```

- [ ] **Step 5: Point the `anim_spaces` table at it**

In the `anim_spaces = TableField(...)` declaration, change the `control` column:

```python
            Column("control", "choice", choices_from="space_control_names"),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `mayapy -m pytest tests/unit/test_core_trigger.py -k space_controls -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Run the full unit suite for regressions**

Run: `make tests-unit`
Expected: PASS. If `tests/unit/test_module_copies_trigger.py` or `tests/ui/test_shape_fold.py` referenced `control_names` as the spaces source, update those references to `space_control_names`.

- [ ] **Step 8: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/core/module.py tests/unit/test_core_trigger.py
git commit -m "Modules declare which controls may host an anim space"
```

---

### Task 2: `shape_control_names` — the Shapes candidate set

**Files:**
- Modify: `src/python/tik/trigger/core/module.py` (the `control_shape_overrides` TableField near line 126; the `*_names` classmethods)
- Test: `tests/unit/test_core_trigger.py`

**Interfaces:**
- Consumes: `Module.control_shape_defaults(settings)` (exists), `Module.qualify` (exists).
- Produces: `Module.shape_control_names(settings=None) -> tuple[str, ...]` — the qualified keys of `control_shape_defaults`, in control order.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_core_trigger.py`:

```python
def test_shape_control_names_come_from_the_declared_defaults():
    """A control with a declared default shape is shape-editable."""

    class Partial(Module):
        controls = ("a", "b")
        control_shapes = {"a": "Circle"}

    assert Partial.shape_control_names({}) == ("a",)


def test_a_module_with_no_controls_offers_no_shape_rows():
    class Nothing(Module):
        controls = ()

    assert Nothing.shape_control_names({}) == ()


def test_shape_control_names_keep_control_order():
    """Row order follows the manifest, not dict insertion luck."""

    class Ordered(Module):
        controls = ("a", "b", "c")
        control_shapes = {"c": "Cube", "a": "Circle", "b": "Diamond"}

    assert Ordered.shape_control_names({}) == ("a", "b", "c")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mayapy -m pytest tests/unit/test_core_trigger.py -k shape_control_names -v`
Expected: FAIL with `AttributeError: ... has no attribute 'shape_control_names'`

- [ ] **Step 3: Add the resolver**

In `module.py`, after `space_control_names`:

```python
    @classmethod
    def shape_control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles with a definable shape, qualified per copy.

        The keys of ``control_shape_defaults`` rather than a list of its own:
        a control with a declared default is shape-editable, and a second list
        would repeat ``controls`` line for line and then drift from it.
        Ordered by the control manifest so the table's rows are stable.
        """
        defaults = cls.control_shape_defaults(settings)
        return tuple(
            name for name in cls.control_names(settings) if name in defaults
        )
```

- [ ] **Step 4: Point the shape table at it**

In `control_shape_overrides = TableField(...)`, change both the row source and the column:

```python
        rows_from="shape_control_names",
        columns=(
            Column("control", "choice", choices_from="shape_control_names"),
            Column("shape", "shape"),
            Column("size", "float"),
        ),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `mayapy -m pytest tests/unit/test_core_trigger.py -k shape_control_names -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Run the shape suites**

Run: `mayapy -m pytest tests/unit/test_shape_resolution_trigger.py tests/unit/test_pinned_shapes_trigger.py -v`
Then: `make tests-ui`
Expected: PASS. `tests/ui/test_shape_fold.py` builds the fold from `rows_from`; it should be unaffected because every shipped module declares a default for every control.

- [ ] **Step 7: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/core/module.py tests/unit/test_core_trigger.py
git commit -m "The Shapes table offers the controls that declare a default shape"
```

---

### Task 3: `warnings()` reads the narrowed sets

**Files:**
- Modify: `src/python/tik/trigger/core/module.py:576-609` (the body of `warnings`)
- Test: `tests/unit/test_core_trigger.py`

**Interfaces:**
- Consumes: `space_control_names` (Task 1), `shape_control_names` (Task 2).
- Produces: no new API. `warnings()` keeps returning `list[str]`.

- [ ] **Step 1: Write the failing test**

```python
def test_a_space_row_on_a_narrowed_out_control_warns():
    class Narrow(Module):
        controls = ("a", "b")
        space_controls = ("a",)
        control_shapes = {"a": "Circle", "b": "Circle"}

    module = Narrow()
    module.anim_spaces = [{"control": "b", "mode": "parent", "label": "world"}]
    problems = module.warnings()
    assert len(problems) == 1
    assert "'b'" in problems[0]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `mayapy -m pytest tests/unit/test_core_trigger.py -k narrowed_out -v`
Expected: FAIL — `assert len(problems) == 1` gets `0`, because `warnings` checks against `control_names`, which still contains `b`.

- [ ] **Step 3: Point the two checks at their own sets**

In `warnings()`, replace the single `known` binding with two, and use each where it belongs:

```python
        spaceable = type(self).space_control_names(self.values())
        for row in self.anim_spaces:
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            if control not in spaceable:
                problems.append(
                    f"anim space '{control}_{label}': control '{control}' is "
                    f"not offered an animation space with the current settings"
                )
```

and for the shape loop:

```python
        shapeable = type(self).shape_control_names(self.values())
        for row in self.control_shape_overrides:
            control, shape = row.get("control", ""), row.get("shape", "")
            if not control:
                continue
            if control not in shapeable:
                problems.append(
                    f"control shape '{control}': control is not built with the "
                    f"current settings"
                )
            elif shape and not shape_library.has_shape(shape):
                problems.append(
                    f"control shape '{control}': shape '{shape}' is not in the "
                    f"shape library"
                )
```

Delete the now-unused `known = type(self).control_names(self.values())` line. The pivot loop between them already reads `pivot_control_names` and is left alone.

- [ ] **Step 4: Run the test to verify it passes**

Run: `mayapy -m pytest tests/unit/test_core_trigger.py -k narrowed_out -v`
Expected: PASS

- [ ] **Step 5: Run the unit suite**

Run: `make tests-unit`
Expected: PASS

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/core/module.py tests/unit/test_core_trigger.py
git commit -m "Stale-row warnings check the set each table actually offers"
```

---

### Task 4: `space_rows` filters an ineligible row

**Files:**
- Modify: `src/python/tik/trigger/core/module.py` (add `logging` import at top; `space_rows` near line 157)
- Test: `tests/unit/test_core_trigger.py`

**Interfaces:**
- Consumes: `space_controls_for_copy` (Task 1).
- Produces: `Module.space_rows(settings=None)` keeps its `list[dict]` return but drops rows naming a control the module does not offer, logging a warning.

**Why here:** `space_rows` is the single source for `space_inputs()` (the ports) and for the builder's space loop at `maya/build.py:559`. Filtering here means a stale row grows no phantom port *and* builds nothing, in one place.

- [ ] **Step 1: Write the failing tests**

```python
def test_space_rows_drop_a_control_the_module_does_not_offer(caplog):
    class Narrow(Module):
        controls = ("a", "b")
        space_controls = ("a",)

    settings = {
        "anim_spaces": [
            {"control": "a", "mode": "parent", "label": "world"},
            {"control": "b", "mode": "parent", "label": "world"},
        ]
    }
    rows = Narrow.space_rows(settings)
    assert [row["control"] for row in rows] == ["a"]


def test_a_dropped_space_row_grows_no_port():
    class Narrow(Module):
        controls = ("a", "b")
        space_controls = ("a",)

    settings = {
        "anim_spaces": [{"control": "b", "mode": "parent", "label": "world"}]
    }
    assert [item.name for item in Narrow.space_inputs(settings)] == []
```

`space_rows` is called with `settings=None` in `warnings()`-adjacent paths; the filter must not fire on the field default, which is checked by the existing suite.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mayapy -m pytest tests/unit/test_core_trigger.py -k "does_not_offer or grows_no_port" -v`
Expected: FAIL — both rows come back and `b_world` is a port.

- [ ] **Step 3: Add the logger**

At the top of `module.py`, after `import uuid`:

```python
import logging
```

and after the imports, beside the `SPACES` / `PIVOTS` / `SHAPES` group constants:

```python
logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Filter in `space_rows`**

```python
    @classmethod
    def space_rows(cls, settings=None) -> list[dict]:
        """The anim-space rows from ``settings`` (or the field default).

        A row naming a control this module does not offer a space is dropped
        here rather than at either consumer, because this is what feeds both
        ``space_inputs`` (the ports) and the builder's space loop: filtering
        once means a stale row can neither grow a phantom port nor build.
        The row is kept in the document -- widening the set restores it with
        its wire intact -- and ``warnings()`` is what tells the rigger.
        """
        if settings is None:
            return [dict(row) for row in cls.anim_spaces.default]
        offered = set(cls.space_controls_for_copy(settings))
        found = []
        for row in settings.get("anim_spaces") or []:
            control = row.get("control", "")
            if control and control not in offered:
                logger.warning(
                    "%s: anim space row names control %r, which this module "
                    "does not offer; skipped.",
                    cls.__name__,
                    control,
                )
                continue
            found.append(dict(row))
        return found
```

**Note on qualification:** `space_rows` is called both on a whole module and on a `for_copy` view. `space_controls_for_copy` returns *bare* roles, and the rows of a copy view carry bare roles too (`_copy_settings` de-qualifies them). On a whole multi-copy module the rows are also bare, because each copy's tables are per-copy. So comparing bare to bare is correct on both paths.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `mayapy -m pytest tests/unit/test_core_trigger.py -k "does_not_offer or grows_no_port" -v`
Expected: PASS

- [ ] **Step 6: Run the unit, copies and integration suites**

Run: `make tests-unit`
Then: `mayapy -m pytest tests/integration/trigger/test_builder_trigger.py -v`
Expected: PASS

- [ ] **Step 7: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/core/module.py tests/unit/test_core_trigger.py
git commit -m "An anim space row on an unoffered control builds nothing and warns"
```

---

### Task 5: the pivot anchor addresses a guide by role and index

**Files:**
- Modify: `src/python/tik/trigger/core/module.py` (the `pivot_controls` declaration near line 61; `pivot_controls_for_copy` near line 257; `_draw_pivot_guides` near line 666)
- Modify: `src/python/tik/trigger/maya/rig.py:544` (the membership check in `pivot_control`)
- Test: `tests/unit/test_pivot_trigger.py`

**Interfaces:**
- Consumes: `Module.qualify`, `_copy_settings` (exist).
- Produces:
  - `Module.pivot_controls: dict[str, str | tuple[str, int]]` — a bare string means index 0.
  - `Module.pivot_controls_for_copy(settings=None) -> dict[str, str | tuple[str, int]]` — **returns the whole dict**, no longer a tuple of keys.
  - `Module.pivot_anchor(control, settings=None) -> tuple[str, int] | None` — the normalised `(role, index)`.

**Breaking change:** `pivot_controls_for_copy` changes its return type from `tuple[str, ...]` to `dict`. `pivot_control_names` iterates it and so is unaffected (iterating a dict yields its keys). Grep for other callers before finishing: `grep -rn "pivot_controls_for_copy" src tests`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_pivot_trigger.py`:

```python
def test_pivot_anchor_normalises_a_bare_role_to_index_zero():
    class Simple(Module):
        guides = GuideLayout("root")
        controls = ("root",)
        control_shapes = {"root": "Circle"}
        pivot_controls = {"root": "root"}

    assert Simple.pivot_anchor("root", {}) == ("root", 0)


def test_pivot_anchor_carries_an_explicit_index():
    class Chain(Module):
        guides = GuideLayout("root", multi="segment", min=1, max=10)
        controls = ("fk0", "fk1")
        control_shapes = {"fk0": "Circle", "fk1": "Circle"}
        pivot_controls = {"fk0": ("root", 0), "fk1": ("segment", 1)}

    assert Chain.pivot_anchor("fk1", {}) == ("segment", 1)


def test_pivot_controls_for_copy_returns_the_anchors_not_just_the_names():
    """The hook dropped its anchors on the floor, so no computed module
    could declare a pivot at all."""

    class Chain(Module):
        guides = GuideLayout("root", multi="segment", min=1, max=10)
        count = IntField(2)

        @classmethod
        def controls_for_copy(cls, settings=None):
            number = int((settings or {}).get("count", 2))
            return tuple(f"fk{index}" for index in range(number))

        @classmethod
        def control_shape_defaults_for_copy(cls, settings=None):
            return {role: "Circle" for role in cls.controls_for_copy(settings)}

        @classmethod
        def pivot_controls_for_copy(cls, settings=None):
            found = {"fk0": ("root", 0)}
            for index in range(1, len(cls.controls_for_copy(settings))):
                found[f"fk{index}"] = ("segment", index - 1)
            return found

    assert Chain.pivot_control_names({"count": 3}) == ("fk0", "fk1", "fk2")
    assert Chain.pivot_anchor("fk2", {"count": 3}) == ("segment", 1)
```

`GuideLayout` and `IntField` are imported in this file's `from tik.trigger.core import (...)` block; add any that are missing.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mayapy -m pytest tests/unit/test_pivot_trigger.py -k "pivot_anchor or for_copy_returns" -v`
Expected: FAIL with `AttributeError: ... has no attribute 'pivot_anchor'`

- [ ] **Step 3: Widen the declaration and the hook**

Replace the `pivot_controls` docstring-comment and annotation in `module.py`:

```python
    #: Controller roles that get a movable pivot, mapped to the guide their
    #: preset guides hang under. Declaring an entry is what makes the control
    #: movable, the way declaring an input is what makes its socket. The anchor
    #: is the module author's business, never the rigger's.
    #:
    #: A value is a guide *reference*: ``"hand"`` means that role at index 0,
    #: and ``("segment", 2)`` addresses the third guide of a multi -- which is
    #: what lets a module whose controls depend on a setting declare a pivot
    #: for each of them.
    pivot_controls: dict[str, object] = {}
```

Replace `pivot_controls_for_copy`:

```python
    @classmethod
    def pivot_controls_for_copy(cls, settings: Optional[dict] = None) -> dict:
        """Controller roles of *one copy* with a movable pivot, and their anchors.

        Returns the whole mapping rather than its keys: an anchor a computed
        module works out from its settings has nowhere else to come from, and
        dropping it here is what stopped ``fkchain`` and ``ribbon`` declaring
        a pivot at all.
        """
        return dict(cls.pivot_controls)
```

Add the normaliser after `pivot_control_names`:

```python
    @classmethod
    def pivot_anchor(cls, control: str, settings: Optional[dict] = None):
        """The ``(guide role, index)`` a control's preset guides hang under.

        ``None`` if the control has no movable pivot. ``control`` may be
        qualified (``c1_ik``); the copy's own anchors are consulted, because
        two copies of a chain anchor to different guides.
        """
        slug = cls.slug_of(control)
        bare = control[len(slug) + 1 :] if slug else control
        for found, one in cls._copy_settings(settings):
            if found != slug:
                continue
            anchor = cls.pivot_controls_for_copy(one).get(bare)
            if anchor is None:
                return None
            return (anchor, 0) if isinstance(anchor, str) else tuple(anchor)
        return None
```

- [ ] **Step 4: Read the anchor through the hook when drawing**

In `_draw_pivot_guides`, replace the anchor lookup:

```python
            anchor_ref = type(self).pivot_anchor(control, settings)
            # Through ``made``, which qualifies with the copy currently
            # drawing: a bare lookup finds the first copy's anchor whichever
            # copy is asking.
            anchor = draft.made(*anchor_ref) if anchor_ref else None
```

- [ ] **Step 5: Route the build-time check through the hook**

In `src/python/tik/trigger/maya/rig.py`, in `pivot_control`:

```python
        role = main.transform.meta.get(tags.ROLE, main.transform.name)
        if role not in self.module.pivot_controls_for_copy(self.module.values()):
            raise GuideError(
                f"'{self.module.module_type}' does not declare a movable pivot "
                f"for control '{role}'."
            )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `mayapy -m pytest tests/unit/test_pivot_trigger.py -v`
Expected: PASS (the whole file, including the existing arm-based tests)

- [ ] **Step 7: Check for other callers and run the suites**

Run: `grep -rn "pivot_controls" src/python tests`
Expected: only `module.py`, `rig.py`, the modules' own declarations, and tests. Any site still reading the raw class attribute for an anchor must move to `pivot_anchor`.

Run: `make tests-unit && make tests-integration`
Expected: PASS. `test_every_movable_pivot_names_a_control_and_a_guide_the_module_has` will still pass at this point because `arm`'s anchor is a bare string; Task 8 updates it for tuples.

- [ ] **Step 8: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/core/module.py src/python/tik/trigger/maya/rig.py tests/unit/test_pivot_trigger.py
git commit -m "A pivot anchor addresses a guide by role and index"
```

---

### Task 6: `pivot_labels` moves to `Module`

**Files:**
- Modify: `src/python/tik/trigger/core/module.py` (add beside `pivot_rows` near line 448)
- Modify: `src/python/tik/trigger/maya/rig.py:576-583` (`ModuleRig._pivot_labels` delegates)
- Test: `tests/unit/test_pivot_trigger.py`

**Interfaces:**
- Consumes: `Module.pivot_rows` (exists).
- Produces: `Module.pivot_labels(role) -> list[str]` — preset labels declared for one control, in row order.

**Why:** Task 7's builder seam needs the labels, and `core` is where the rows live. `maya/build.py` must not reach into `ModuleRig` for a pure question about settings.

- [ ] **Step 1: Write the failing test**

```python
def test_pivot_labels_lists_one_controls_rows_in_order():
    class Simple(Module):
        guides = GuideLayout("root")
        controls = ("root", "other")
        control_shapes = {"root": "Circle", "other": "Circle"}
        pivot_controls = {"root": "root", "other": "root"}

    module = Simple()
    module.pivot_presets = [
        {"control": "root", "label": "tip"},
        {"control": "other", "label": "ignored"},
        {"control": "root", "label": "heel"},
    ]
    assert module.pivot_labels("root") == ["tip", "heel"]
    assert module.pivot_labels("nobody") == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `mayapy -m pytest tests/unit/test_pivot_trigger.py -k pivot_labels -v`
Expected: FAIL with `AttributeError: 'Simple' object has no attribute 'pivot_labels'`

- [ ] **Step 3: Add it to `Module`**

In `module.py`, after `pivot_rows`:

```python
    def pivot_labels(self, role: str) -> list[str]:
        """Preset labels declared for ``role``, in row order.

        On ``Module`` rather than on ``ModuleRig`` because the builder asks
        the same question to decide whether to make a pivot at all, and that
        is a question about settings, not about a scene.
        """
        return [
            row["label"]
            for row in self.pivot_rows(self.values())
            if row.get("control") == role and row.get("label")
        ]
```

- [ ] **Step 4: Delegate from `ModuleRig`**

In `src/python/tik/trigger/maya/rig.py`, replace the body of `_pivot_labels`:

```python
    def _pivot_labels(self, role: str) -> list[str]:
        """Preset labels declared for ``role``, in row order."""
        return self.module.pivot_labels(role)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `mayapy -m pytest tests/unit/test_pivot_trigger.py -v`
Expected: PASS

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/core/module.py src/python/tik/trigger/maya/rig.py tests/unit/test_pivot_trigger.py
git commit -m "pivot_labels is a question about settings, so it lives on Module"
```

---

### Task 7: the framework builds the pivot

**Files:**
- Modify: `src/python/tik/trigger/maya/build.py:744` (directly after `view.build(ctx)` in the per-copy loop)
- Modify: `src/python/tik/trigger/modules/arm/arm.py:237` (delete the explicit call)
- Test: `tests/integration/trigger/test_pivot_build_trigger.py` (create)

**Interfaces:**
- Consumes: `Module.pivot_controls_for_copy` (Task 5), `Module.pivot_labels` (Task 6), `ModuleRig.controller_by_role` (exists, `maya/rig.py:623`), `ModuleRig.pivot_control` (exists).
- Produces: no new API. A pivot controller named `<side>_<name>_<role>_pivot_ctrl` exists after build for every declared role with preset rows.

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/trigger/test_pivot_build_trigger.py`:

```python
"""The framework builds a movable pivot where the rigger asked for one.

Spec: docs/superpowers/specs/2026-09-11-control-capability-declarations-design.md

Declaring is what makes a pivot available; a preset row is what builds it --
the same sentence the ground rules use for sockets.
"""

from maya import cmds

from tik.trigger.core import get_module
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder


def _build(module_type, settings=None):
    cmds.file(new=True, force=True)
    scene = GuideScene()
    module = get_module(module_type)(name=module_type)
    if settings:
        module.apply(settings, strict=False)
    instance = scene.create_guides(module)
    report = Builder().build(document=scene.document, afterlife="keep")
    return report.rigs[instance.instance_id]


def _pivots(rig):
    return sorted(
        controller.transform.name
        for controller in rig.controllers
        if controller.transform.name.endswith("_pivot_ctrl")
    )


def test_arm_still_builds_its_hand_pivot_without_an_explicit_call():
    """arm ships three preset rows, so a fresh arm is unchanged."""
    rig = _build("arm")
    assert any("ik_pivot_ctrl" in name for name in _pivots(rig))


def test_a_declared_control_with_no_preset_rows_builds_no_pivot():
    """fkchain declares a pivot per segment; a fresh one has no rows."""
    rig = _build("fkchain")
    assert _pivots(rig) == []


def test_a_preset_row_is_what_builds_the_pivot():
    rig = _build(
        "fkchain",
        {"segments": 3, "pivot_presets": [{"control": "fk1", "label": "tip"}]},
    )
    names = _pivots(rig)
    assert len(names) == 1
    assert "fk1_pivot_ctrl" in names[0]


def test_an_emptied_arm_builds_no_pivot():
    """The rule is uniform: no rows means no pivot, arm included."""
    rig = _build("arm", {"pivot_presets": []})
    assert _pivots(rig) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mayapy -m pytest tests/integration/trigger/test_pivot_build_trigger.py -v`
Expected: `test_arm_still_builds...` PASSES (arm's explicit call is still there), the other three FAIL — `fkchain` declares no pivots yet (Task 8) and `arm` builds one unconditionally.

- [ ] **Step 3: Add the builder seam**

In `src/python/tik/trigger/maya/build.py`, in the per-copy loop, directly after `view.build(ctx)`:

```python
                view.build(ctx)
                # A pivot per declared role that the rigger gave preset rows:
                # declaring is what makes it available, a row is what builds
                # it -- the same arrangement as a socket per declared input.
                for role in view.pivot_controls_for_copy(view.values()):
                    main = ctx.controller_by_role(role)
                    if main is not None and view.pivot_labels(role):
                        ctx.pivot_control(main)
```

- [ ] **Step 4: Delete arm's explicit call**

In `src/python/tik/trigger/modules/arm/arm.py`, remove line 237:

```python
        rig.pivot_control(limb.ik_control)
```

Check the surrounding lines for a now-orphaned comment and remove it too.

- [ ] **Step 5: Run the tests**

Run: `mayapy -m pytest tests/integration/trigger/test_pivot_build_trigger.py -v`
Expected: `test_arm_still_builds...` and `test_an_emptied_arm...` PASS. The two `fkchain` tests still FAIL until Task 8 declares its pivots — that is expected; note it and continue.

- [ ] **Step 6: Run the pivot and arm suites**

Run: `mayapy -m pytest tests/unit/test_pivot_trigger.py -v`
Then: `mayapy -m pytest tests/integration/trigger/ -k arm -v`
Expected: PASS

- [ ] **Step 7: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/maya/build.py src/python/tik/trigger/modules/arm/arm.py tests/integration/trigger/test_pivot_build_trigger.py
git commit -m "The builder makes the pivot, so no module carries pivot code"
```

---

### Task 8: every module declares its pivots

**Files:**
- Modify: `src/python/tik/trigger/modules/base/base.py`
- Modify: `src/python/tik/trigger/modules/fkchain/fkchain.py`
- Modify: `src/python/tik/trigger/modules/ribbon/ribbon.py`
- Modify: `src/python/tik/trigger/modules/arm/arm.py:58`
- Modify: `tests/integration/trigger/test_module_ground_rules.py:369-382`
- Test: `tests/integration/trigger/test_pivot_build_trigger.py` (the two failing `fkchain` tests from Task 7)

**Interfaces:**
- Consumes: `Module.pivot_controls_for_copy` returning a dict (Task 5).
- Produces: no new API; every shipped module that builds a control offers a pivot on each.

- [ ] **Step 1: Update the ground-rules test for tuple anchors**

Replace `test_every_movable_pivot_names_a_control_and_a_guide_the_module_has`:

```python
@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_every_movable_pivot_names_a_control_and_a_guide_the_module_has(module_type):
    """Rule: pivot_controls points at real controls and real guide roles.

    A typo here is invisible until a rigger opens the properties table and
    finds a preset row pointing at nothing. Read through the hook, because a
    computed module works its anchors out from its settings.
    """
    module_cls = get_module(module_type)
    for settings in CONTROL_VARIATIONS.get(module_type, [{}]):
        instance = module_cls(settings=settings)
        controls = set(module_cls.control_names(instance.values()))
        roles = set(module_cls.guides.all_roles)
        for control in module_cls.pivot_control_names(instance.values()):
            assert control in controls, f"{module_type}: '{control}' is not a control"
            anchor = module_cls.pivot_anchor(control, instance.values())
            assert anchor is not None, f"{module_type}: '{control}' has no anchor"
            role, index = anchor
            assert role in roles, f"{module_type}: anchor '{role}' is not a guide"
            assert index >= 0, f"{module_type}: anchor index {index} is negative"
```

- [ ] **Step 2: Add a ground rule that every control is offered a pivot**

Append to the same file:

```python
@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_every_control_is_offered_a_movable_pivot(module_type):
    """Rule: a rigger can put a pivot on any controller a module builds.

    Offering is free -- nothing is built until a preset row exists -- so a
    control left out of pivot_controls is an oversight, not a decision.
    """
    module_cls = get_module(module_type)
    for settings in CONTROL_VARIATIONS.get(module_type, [{}]):
        instance = module_cls(settings=settings)
        controls = set(module_cls.control_names(instance.values()))
        movable = set(module_cls.pivot_control_names(instance.values()))
        assert controls - movable == set(), (
            f"{module_type}: {sorted(controls - movable)} have no movable pivot"
        )
```

- [ ] **Step 3: Run both tests to verify they fail**

Run: `mayapy -m pytest tests/integration/trigger/test_module_ground_rules.py -k "movable_pivot or offered_a_movable" -v`
Expected: `test_every_control_is_offered_a_movable_pivot` FAILS for `base`, `fkchain` and `ribbon`, and for `arm` on the five controls beyond `ik`.

- [ ] **Step 4: Declare `base`'s pivot**

In `base.py`, after `control_shapes`:

```python
    pivot_controls = {"root": "root"}
```

- [ ] **Step 5: Declare `fkchain`'s pivots**

In `fkchain.py`, after `control_orient_defaults_for_copy`:

```python
    @classmethod
    def pivot_controls_for_copy(cls, settings=None):
        """Each FK control anchors to the guide it is matched to.

        ``build`` matches ``fk0`` to the root guide and ``fk{i}`` to
        ``segment{i-1}``, so the anchors carry the index rather than a bare
        role -- a bare ``"segment"`` would stack every preset on the first.
        """
        found = {"fk0": ("root", 0)}
        for index in range(1, len(cls.controls_for_copy(settings))):
            found[f"fk{index}"] = ("segment", index - 1)
        return found
```

- [ ] **Step 6: Declare `ribbon`'s pivots**

In `ribbon.py`, after `control_shape_defaults_for_copy`:

```python
    @classmethod
    def pivot_controls_for_copy(cls, settings=None):
        """Start and end anchor to their own guides; the mids have none.

        A mid is computed along the surface and has no guide of its own, so
        its presets stack on ``start`` until the rigger drags them where they
        belong -- which is how an unplaced preset already behaves.
        """
        return {
            role: ("end" if role == "end" else "start", 0)
            for role in cls.controls_for_copy(settings)
        }
```

- [ ] **Step 7: Declare the rest of `arm`'s pivots**

In `arm.py`, replace line 58:

```python
    pivot_controls = {
        "collar": "collar",
        "ik": "hand",
        "pole": "elbow",  # the pole is placed at a computed rest position
        **{
            role: guide
            for role, guide in zip(
                limb_control_names(labels=LIMB_LABELS)[1:-1],
                ("shoulder", "elbow", "hand"),
            )
        },
    }
```

**Verify this slice is right before trusting it.** `limb_control_names` returns `(ik, fk_upper, fk_lower, fk_hand, pole)`, so `[1:-1]` is the three FK roles in order. Confirm with:

```bash
mayapy -c "from tik.trigger.systems.limb import limb_control_names; print(limb_control_names(labels=('upper','lower','hand')))"
```

If the shape differs, write the three FK entries out literally instead of slicing.

- [ ] **Step 8: Run the ground-rules tests to verify they pass**

Run: `mayapy -m pytest tests/integration/trigger/test_module_ground_rules.py -v`
Expected: PASS

- [ ] **Step 9: Run Task 7's remaining failures**

Run: `mayapy -m pytest tests/integration/trigger/test_pivot_build_trigger.py -v`
Expected: PASS (all four now)

- [ ] **Step 10: Run the full suites**

Run: `make tests-unit && make tests-integration`
Expected: PASS

- [ ] **Step 11: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/modules tests/integration/trigger/test_module_ground_rules.py
git commit -m "Every module offers a movable pivot on every control it builds"
```

---

### Task 9: a table nobody can fill renders nothing

**Files:**
- Modify: `src/python/tik/shared/ui/fields.py` (`set_target` near line 580; add `_table_is_dead` beside `_resolve_choices` near line 822)
- Test: `tests/ui/test_empty_sections.py` (create)

**Interfaces:**
- Consumes: `FormBuilder._resolve_choices(attr)` (exists).
- Produces: `FormBuilder._table_is_dead(name, field) -> bool` — private; no public API change.

**Run these with:** `make tests-ui` (sets `TIK_TESTS_NO_MAYA=1` and `QT_QPA_PLATFORM=offscreen`; Maya standalone cannot host a QApplication).

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_empty_sections.py`:

```python
"""A section with no candidate controls does not render.

Spec: docs/superpowers/specs/2026-09-11-control-capability-declarations-design.md

A fold the rigger cannot use is worse than a missing one: it claims the
module offers something it does not.
"""

import pytest

from tik.core.fields import Column, FieldGroup, Schema, TableField
from tik.shared.ui.fields import FormBuilder

GROUP = FieldGroup("Rows", collapsed=True)


class _Target(Schema):
    """A table whose only option column is resolved from the target."""

    options: tuple = ()
    table = TableField(
        [],
        label="Table",
        group=GROUP,
        columns=(
            Column("control", "choice", choices_from="options"),
            Column("mode", "choice", choices=("parent", "point")),
        ),
    )


def _form(target):
    builder = FormBuilder()
    builder.set_target(target)
    return builder


def test_a_table_with_no_options_renders_no_widget(qtbot):
    target = _Target()
    target.options = ()
    form = _form(target)
    with pytest.raises(KeyError):
        form.widget("table")


def test_its_fold_hides_with_it(qtbot):
    target = _Target()
    target.options = ()
    form = _form(target)
    assert "Rows" not in form._groups or not form._groups["Rows"].isVisible()


def test_a_table_with_options_renders(qtbot):
    target = _Target()
    target.options = ("a", "b")
    form = _form(target)
    assert form.widget("table") is not None


def test_a_table_holding_rows_renders_even_with_no_options(qtbot):
    """The stale-row escape: the rigger must be able to delete what is there."""
    target = _Target()
    target.options = ()
    target.table = [{"control": "gone", "mode": "parent"}]
    form = _form(target)
    assert form.widget("table") is not None
```

Add the trigger-module cases in the same file, using the Qt-only stub conventions already in `tests/ui/`:

```python
def test_twist_renders_none_of_the_three_sections(qtbot):
    from tik.trigger.core import get_module

    form = _form(get_module("twist")())
    for name in ("anim_spaces", "pivot_presets", "control_shape_overrides"):
        with pytest.raises(KeyError):
            form.widget(name)


def test_arm_renders_all_three(qtbot):
    from tik.trigger.core import get_module

    form = _form(get_module("arm")())
    for name in ("anim_spaces", "pivot_presets", "control_shape_overrides"):
        assert form.widget(name) is not None


def test_a_ribbon_with_no_controllers_renders_none(qtbot):
    from tik.trigger.core import get_module

    module = get_module("ribbon")()
    module.apply(
        {"mid_count": 0, "start_controller": False, "end_controller": False},
        strict=False,
    )
    form = _form(module)
    for name in ("anim_spaces", "pivot_presets", "control_shape_overrides"):
        with pytest.raises(KeyError):
            form.widget(name)
```

If `tests/ui/` does not use a `qtbot` fixture, drop the parameter and follow whatever `tests/ui/test_shape_fold.py` does to get a QApplication.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `make tests-ui`
Expected: the empty-table tests FAIL — `form.widget("table")` returns a widget instead of raising.

- [ ] **Step 3: Add the predicate**

In `src/python/tik/shared/ui/fields.py`, beside `_resolve_choices`:

```python
    def _table_is_dead(self, name: str, field) -> bool:
        """A table nobody could add a row to, that holds no rows to remove.

        The test is per *column*: a column whose options are fixed and empty
        is what makes a row unfillable, and a table may have a static column
        beside a resolved one. A table holding rows always renders, whatever
        its options say -- otherwise a setting that narrows the candidates
        would strand a row where the rigger cannot reach it.
        """
        if getattr(self._target, name, None):
            return False
        source = getattr(field, "rows_from", "")
        if source and not self._resolve_choices(source):
            return True
        return any(
            column.choices_from and not self._resolve_choices(column.choices_from)
            for column in getattr(field, "columns", ())
        )
```

- [ ] **Step 4: Skip such a field in `set_target`**

In the inner loop of `set_target`, as the first statement of the `for name, field in rows[key]:` body:

```python
            for name, field in rows[key]:
                if field.type_name == "table" and self._table_is_dead(name, field):
                    # No widget and no label, so the existing rule -- a group
                    # whose fields are all hidden hides too -- closes the fold.
                    continue
                widget = self._make_widget(name, field)
```

- [ ] **Step 5: Make the empty fold actually hide**

`set_visible_fields` hides a group when none of its fields are shown, but `set_target` alone does not. After the `for key, group in order:` loop and before `self._layout.addStretch(1)`, add:

```python
        for label, fold in self._groups.items():
            # A fold whose every field was skipped has nothing to open.
            fold.setVisible(
                any(
                    field.group and field.group.label == label
                    for name, field in target.fields().items()
                    if name in self._widgets
                )
            )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `make tests-ui`
Expected: PASS

- [ ] **Step 7: Guard the rest of the UI suite**

Run: `make tests-ui`
Expected: PASS overall. `tests/ui/test_shape_fold.py`, `test_kinematics_picker.py` and `test_copy_tabs.py` all build forms; if any asserts on a widget that is now skipped, the target in that test genuinely has no candidates and the assertion should move to a target that does.

Also check `ui/designer/window.py:_split_forms`, which calls `form.widget(...)` indirectly through `set_visible_fields`; `set_visible_fields` iterates `self._widgets`, so a skipped field is simply absent and needs no change. Verify with `mayapy -m pytest tests/ui/test_copy_tabs.py -v`.

- [ ] **Step 8: Lint and commit**

```bash
make lint
git add src/python/tik/shared/ui/fields.py tests/ui/test_empty_sections.py
git commit -m "A table nobody can fill renders nothing, and its fold closes with it"
```

---

### Task 10: the panel rebuilds when a candidate set changes

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/properties.py:71-81` (`_topology`)
- Test: `tests/ui/test_empty_sections.py`

**Interfaces:**
- Consumes: `space_control_names` (Task 1), `shape_control_names` (Task 2), `pivot_control_names` (exists).
- Produces: no new API. `_topology` returns a longer tuple.

**Why:** the form is rebuilt when `_topology` changes. Without this, setting `mid_count` to 0 on a ribbon leaves the three folds on screen until something else forces a rebuild.

- [ ] **Step 1: Write the failing test**

Add to `tests/ui/test_empty_sections.py`:

```python
def test_topology_notices_a_candidate_set_emptying():
    from tik.trigger.core import get_module
    from tik.trigger.ui.designer.properties import PropertiesPanel

    module_cls = get_module("ribbon")

    class _Handle:
        def __init__(self, settings):
            self.module_class = module_cls
            self.settings = settings
            self.instance = type("I", (), {"guides": ()})()

    full = _Handle({"mid_count": 2, "start_controller": True})
    none = _Handle(
        {"mid_count": 0, "start_controller": False, "end_controller": False}
    )
    assert PropertiesPanel._topology(full) != PropertiesPanel._topology(none)
```

If `_topology` is not reachable as a static method on the panel class under this name, read `properties.py:71` and call it the way that file does.

- [ ] **Step 2: Run the test to verify it fails or passes**

Run: `mayapy -m pytest tests/ui/test_empty_sections.py -k topology -v`
Expected: this may already PASS, because `control_names` shrinks too. Keep the test — it pins the guarantee — and continue to step 3 so a module that narrows *only* its space set is also covered.

- [ ] **Step 3: Extend `_topology`**

```python
    @staticmethod
    def _topology(handle) -> tuple:
        """What a settings change might alter: ports, controls and guide count.

        The three candidate sets are here as well as ``control_names``,
        because a module may narrow one of them without changing the controls
        it builds -- and a section that empties has to leave the screen.
        """
        module_cls = handle.module_class
        settings = handle.settings
        return (
            tuple(module_cls.input_names(settings)),
            tuple(module_cls.output_names(settings)),
            tuple(module_cls.control_names(settings)),
            tuple(module_cls.space_control_names(settings)),
            tuple(module_cls.pivot_control_names(settings)),
            tuple(module_cls.shape_control_names(settings)),
            len(handle.instance.guides),
        )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `mayapy -m pytest tests/ui/test_empty_sections.py -k topology -v`
Expected: PASS

- [ ] **Step 5: Run the UI suite**

Run: `make tests-ui`
Expected: PASS

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add src/python/tik/trigger/ui/designer/properties.py tests/ui/test_empty_sections.py
git commit -m "The panel rebuilds when a section's candidate set empties or refills"
```

---

### Task 11: copies carry the new sets

**Files:**
- Test: `tests/unit/test_module_copies_trigger.py`
- Modify: whatever the tests find broken (expected: nothing)

**Interfaces:**
- Consumes: everything from Tasks 1-8.
- Produces: no new API.

**Why a task of its own:** the copy layer qualifies every manifest name, and three of the four sets are new or changed shape. A copy leaking another copy's controls into a panel is the exact bug the copies spec was written to prevent.

- [ ] **Step 1: Write the tests**

Add to `tests/unit/test_module_copies_trigger.py`:

```python
def test_space_control_names_qualify_per_copy():
    module_cls = get_module("base")
    module = module_cls(name="base")
    module.copies = [{"slug": "", "name": "a"}, {"slug": "c1", "name": "b"}]
    assert module_cls.space_control_names(module.values()) == ("root", "c1_root")


def test_shape_control_names_qualify_per_copy():
    module_cls = get_module("base")
    module = module_cls(name="base")
    module.copies = [{"slug": "", "name": "a"}, {"slug": "c1", "name": "b"}]
    assert module_cls.shape_control_names(module.values()) == ("root", "c1_root")


def test_pivot_anchor_resolves_per_copy():
    """Two copies of a chain anchor to their own guides, not copy one's."""
    module_cls = get_module("fkchain")
    module = module_cls(name="chain")
    module.copies = [
        {"slug": "", "name": "a", "segments": 2},
        {"slug": "c1", "name": "b", "segments": 3},
    ]
    values = module.values()
    assert module_cls.pivot_anchor("c1_fk2", values) == ("segment", 1)
    assert module_cls.pivot_anchor("fk2", values) is None


def test_a_copy_view_sees_only_its_own_candidates():
    module_cls = get_module("base")
    module = module_cls(name="base")
    module.copies = [{"slug": "", "name": "a"}, {"slug": "c1", "name": "b"}]
    view = module.for_copy("c1")
    assert type(view).space_control_names(view.values()) == ("root",)
```

Match the file's existing import style; `get_module` is imported there already.

- [ ] **Step 2: Run the tests**

Run: `mayapy -m pytest tests/unit/test_module_copies_trigger.py -v`
Expected: PASS if Tasks 1-8 were done correctly. A failure here is a real bug in one of them — fix it in the file it belongs to, not by weakening the test. The copy-row schema in the first three tests must match what `copies.normalise` expects; read `src/python/tik/trigger/core/copies.py` and adjust the dict keys if `name`/`slug` are not the right ones.

- [ ] **Step 3: Run the copy integration suites**

Run: `mayapy -m pytest tests/integration/trigger/test_copy_guides_trigger.py tests/integration/trigger/test_copy_invariant_trigger.py -v`
Expected: PASS

- [ ] **Step 4: Lint and commit**

```bash
make lint
git add tests/unit/test_module_copies_trigger.py
git commit -m "Pin that the three candidate sets qualify per copy"
```

---

### Task 12: documentation

**Files:**
- Modify: `CLAUDE.md` (the tik.trigger Status paragraph and the "Module Ground Rules" section)
- Modify: `AI/coding_rules.md` (the module ground rules)
- Modify: `docs/superpowers/specs/2026-09-11-control-capability-declarations-design.md` (status line)

- [ ] **Step 1: Mark the spec implemented**

Change `**Status:** draft` to `**Status:** implemented`.

- [ ] **Step 2: Add the spec to CLAUDE.md's design-spec list**

In the `**Design specs:**` bullet, as the first entry:

```
`docs/superpowers/specs/2026-09-11-control-capability-declarations-design.md` (control capability declarations: the four manifest attributes, why the Shapes candidate set is the keys of `control_shapes`, the addressable pivot anchor, and the builder seam that makes the pivot; **amends the movable-pivots spec and the definable-shapes spec**),
```

- [ ] **Step 3: Update the Module Ground Rules paragraph**

In `CLAUDE.md`, in "Module Ground Rules", replace the sentence *"Every declared control can host an animation space"* with:

```
A module names the candidate controls for each rigger-facing section: `space_controls` (which controls may host an animation space -- empty means all of them, the one default that is "all", because any controller can host one and a module narrows), `pivot_controls` (which get a movable pivot, mapped to the guide their presets anchor to -- a bare role means index 0, `("segment", 2)` addresses a multi), and `control_shapes`, whose keys are the Shapes section's candidate set. Declaring a pivot is what offers it; a preset row is what builds it, and the builder makes it after `build()` returns, so no module contains pivot code. A section with no candidates and no rows does not render.
```

- [ ] **Step 4: Mirror it into `AI/coding_rules.md`**

Find the module ground rules section and add the same four-attribute table plus the "declaring offers, a row builds" sentence, in that file's voice.

- [ ] **Step 5: Add the new test files to CLAUDE.md's test list**

In the "tik.trigger Tests" list, extend the pivot line and add the UI one:

```
- `tests/integration/trigger/test_pivot_build_trigger.py` — the builder seam: a pivot where preset rows exist and nowhere else
- `tests/ui/test_empty_sections.py` — a table nobody can fill renders nothing, and its fold closes with it
```

- [ ] **Step 6: Run everything once more**

Run: `make lint && make tests-unit && make tests-integration && make tests-ui`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md AI/coding_rules.md docs/superpowers/specs/2026-09-11-control-capability-declarations-design.md
git commit -m "Document the control capability declarations"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §2 the four attributes | 1 (`space_controls`), 2 (`shape_control_names`), 5 (`pivot_controls`) |
| §2.1 why the second job is safe | 8 (the existing shape ground rule is kept and a pivot one added) |
| §3 addressable anchor | 5 |
| §4 framework builds the pivot | 6 (`pivot_labels`), 7 (the seam) |
| §4.1 what changes for an existing arm | 7 (`test_an_emptied_arm_builds_no_pivot`) |
| §5 validation, both layers | 3 (`warnings`), 4 (`space_rows` filter), 8 (ground rules) |
| §6 the UI rule | 9 (the predicate), 10 (`_topology`) |
| §7 what each module declares | 8 |
| §8 testing | every task; 11 covers the copy layer |
| §9 out of scope | nothing implements it, by design |

**Type consistency:** `space_control_names`, `shape_control_names`, `pivot_control_names` all return `tuple[str, ...]` of qualified names. `pivot_controls_for_copy` returns `dict`; `pivot_anchor` returns `tuple[str, int] | None`. `pivot_labels` returns `list[str]` and is an instance method on `Module` (Task 6) called as `view.pivot_labels(role)` in Task 7 — consistent.

**Known ordering dependency:** Task 7's `fkchain` tests fail until Task 8 lands. This is called out in Task 7 step 5 and is deliberate — the seam and the declarations are separately reviewable, and splitting them keeps each commit honest about what it does.
