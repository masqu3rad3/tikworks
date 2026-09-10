# Module Copies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every module a list of copies of itself, so a hand is one module with five copies instead of five modules — one tree row, one graph node, one selection.

**Architecture:** `copies` is a hidden settings field holding one row per copy. For each copy the builder makes a *per-copy view* — the same module class with `{**settings, **row}` and a `ModuleInstance` whose `name` is the copy's name — and calls the ordinary `draw_guides` / `build`. Module authors write single-copy code and change nothing. `per_copy=True` on a field declares only which settings vary per copy.

**Tech Stack:** Python 3.10+, Maya 2024+, Qt via `tik.shared.ui.Qt`, pytest under `mayapy`.

**Spec:** `docs/superpowers/specs/2026-09-10-module-copies-design.md`

## Global Constraints

- **There is exactly one selectable thing, and it is the module.** The tab bar edits a settings field. It must never change `_current`, touch the tree, or alter what `selected_handles()` returns. This is the rule the superseded group design broke.
- **`tik/trigger/core` is pure Python.** No `maya`, no `tik.maya`, no Qt, no `tik.shared`. Enforced by `tests/unit/test_import_boundaries.py`.
- **A one-copy module is byte-identical to today** at every layer: same guide roles, same node names, same `.tr`. No migration, no guide-document schema bump.
- **The first copy's slug is `""`.** Roles are `<slug>_<role>`, so copy one is `root`/`segment` exactly as now.
- **The copy name is the naming unit.** The module name never reaches the rig. A blank name on a single copy falls back to the module's name.
- **Module authors write single-copy code.** No task may require a change to `FkChain.build()` or any other module body.
- **No third-party dependencies.** Stdlib and Maya-bundled only.
- **Every dialog goes through `tik.shared.ui.feedback.Feedback`** (`tests/unit/test_dialog_boundaries.py`).

**Test commands.** Define once; every task refers to these.

```bash
# unit + integration (needs Maya)
export TIK="PYTHONPATH=D:/dev/tikworks/src/python MAYA_PLUG_IN_PATH=D:/dev/tikworks/src/plugins/python"
PYTHONPATH=D:/dev/tikworks/src/python MAYA_PLUG_IN_PATH=D:/dev/tikworks/src/plugins/python mayapy -m pytest tests/unit -q
# ui (no Maya standalone)
PYTHONPATH=D:/dev/tikworks/src/python TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui -q
# lint
python -m black -q src/python/tik tests && python -m isort -q src/python/tik tests && python -m flake8 src/python/tik tests
```

**Baseline before starting:** 1962 unit+integration, 676 UI, lint clean.

---

### Task 1: `per_copy` on Field

**Files:**
- Modify: `src/python/tik/core/fields.py` (`Field.__init__` at line 54; `Schema` at 603)
- Test: `tests/unit/test_fields.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Field(..., per_copy: bool = False)` with `field.per_copy`; `Schema.per_copy_fields() -> dict[str, Field]` and `Schema.shared_fields() -> dict[str, Field]`, both classmethods returning subsets of `fields()` in the same order.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_fields.py`:

```python
def test_a_field_is_shared_unless_it_says_otherwise():
    from tik.core.fields import IntField

    assert IntField(3).per_copy is False
    assert IntField(3, per_copy=True).per_copy is True


def test_a_schema_splits_its_fields_by_per_copy():
    from tik.core.fields import FloatField, IntField, Schema

    class Toy(Schema):
        segments = IntField(3, per_copy=True)
        spacing = FloatField(5.0, per_copy=True)
        size = FloatField(2.0)

    assert list(Toy.per_copy_fields()) == ["segments", "spacing"]
    assert list(Toy.shared_fields()) == ["size"]


def test_the_two_subsets_partition_the_fields():
    """Every field is on exactly one side; none is lost or counted twice."""
    from tik.core.fields import FloatField, IntField, Schema

    class Toy(Schema):
        segments = IntField(3, per_copy=True)
        size = FloatField(2.0)

    every = set(Toy.fields())
    assert set(Toy.per_copy_fields()) | set(Toy.shared_fields()) == every
    assert not set(Toy.per_copy_fields()) & set(Toy.shared_fields())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `mayapy -m pytest tests/unit/test_fields.py -k per_copy -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'per_copy'`

- [ ] **Step 3: Implement**

In `Field.__init__`, add the keyword after `last`:

```python
        last: bool = False,
        per_copy: bool = False,
    ) -> None:
```

and in the body, after `self.last = last`:

```python
        #: True when this setting belongs to one *copy* of the module rather
        #: than to the module as a whole -- a chain's length is a property of
        #: that chain. Declared once by the module author, never inferred from
        #: values: a panel that reshuffles as the rigger types is a poor
        #: substitute for a fact the author already knows.
        self.per_copy = per_copy
```

On `Schema`, beside `fields()`:

```python
    @classmethod
    def per_copy_fields(cls) -> dict[str, "Field"]:
        """Fields that belong to one copy, in declaration order."""
        return {
            name: field for name, field in cls.fields().items() if field.per_copy
        }

    @classmethod
    def shared_fields(cls) -> dict[str, "Field"]:
        """Fields that belong to the module as a whole, in declaration order."""
        return {
            name: field
            for name, field in cls.fields().items()
            if not field.per_copy
        }
```

- [ ] **Step 4: Run it to verify it passes**

Run: `mayapy -m pytest tests/unit/test_fields.py -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/core/fields.py tests/unit/test_fields.py
git commit -m "Fields: per_copy declares a setting belongs to one copy"
```

---

### Task 2: The `copies` list and its operations

**Files:**
- Create: `src/python/tik/trigger/core/copies.py`
- Modify: `src/python/tik/trigger/core/module.py` (the `copies` field)
- Test: `tests/unit/test_module_copies_trigger.py`

**Interfaces:**
- Consumes: `Schema.per_copy_fields()` from Task 1.
- Produces, in `core/copies.py`, all pure and all taking plain data:
  - `EMPTY_SLUG = ""`
  - `new_slug(existing: Iterable[str]) -> str` — `"c1"`, `"c2"`… never reusing one in `existing`
  - `normalise(rows, per_copy_defaults: dict, module_name: str) -> list[dict]` — guarantees at least one row and every per-copy key present
  - `row_for(rows, slug) -> Optional[dict]`
  - `duplicate_row(rows, slug, per_copy_defaults, taken_names) -> dict` — the `[+]` verb
  - `copy_name(row, module_name) -> str` — the blank-name fallback
  - `CopyError(TriggerError)`
- And on `Module`: `copies` (a hidden `ListField`), `copy_rows() -> list[dict]`, `copy_slugs() -> list[str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_module_copies_trigger.py`:

```python
"""Module copies: the row list, slugs, and the per-copy view."""

import pytest

from tik.trigger.core.copies import (
    EMPTY_SLUG,
    CopyError,
    copy_name,
    duplicate_row,
    new_slug,
    normalise,
    row_for,
)

DEFAULTS = {"segments": 3, "spacing": 5.0}


def test_the_first_slug_is_empty():
    """Which is what makes an existing .tr already a one-copy module."""
    rows = normalise([], DEFAULTS, "fingers")
    assert [row["slug"] for row in rows] == [EMPTY_SLUG]


def test_normalise_fills_in_every_per_copy_value():
    rows = normalise([{"slug": "", "name": "index"}], DEFAULTS, "fingers")
    assert rows[0]["segments"] == 3
    assert rows[0]["spacing"] == 5.0


def test_normalise_keeps_values_that_are_already_there():
    rows = normalise([{"slug": "", "name": "i", "segments": 9}], DEFAULTS, "f")
    assert rows[0]["segments"] == 9


def test_normalise_drops_keys_that_are_no_longer_per_copy():
    """A field that stopped being per_copy must not leave a value behind."""
    rows = normalise([{"slug": "", "name": "i", "gone": 1}], DEFAULTS, "f")
    assert "gone" not in rows[0]


def test_new_slug_never_reuses_one():
    assert new_slug([""]) == "c1"
    assert new_slug(["", "c1"]) == "c2"
    assert new_slug(["", "c2"]) == "c3"  # c1 was used and removed; never reused


def test_row_for_finds_by_slug():
    rows = normalise(
        [{"slug": "", "name": "a"}, {"slug": "c1", "name": "b"}], DEFAULTS, "f"
    )
    assert row_for(rows, "c1")["name"] == "b"
    assert row_for(rows, "nope") is None


def test_duplicate_copies_the_values_not_the_defaults():
    """A fifth finger wants the fourth finger's settings, not the module's."""
    rows = normalise([{"slug": "", "name": "index", "segments": 9}], DEFAULTS, "f")
    made = duplicate_row(rows, "", DEFAULTS, taken_names={"index"})
    assert made["segments"] == 9
    assert made["slug"] == "c1"


def test_duplicate_gives_the_new_row_a_free_name():
    rows = normalise([{"slug": "", "name": "index"}], DEFAULTS, "f")
    made = duplicate_row(rows, "", DEFAULTS, taken_names={"index"})
    assert made["name"] != "index"
    assert made["name"]


def test_duplicating_an_unknown_slug_is_refused():
    rows = normalise([{"slug": "", "name": "index"}], DEFAULTS, "f")
    with pytest.raises(CopyError, match="no copy"):
        duplicate_row(rows, "nope", DEFAULTS, taken_names=set())


def test_a_blank_name_falls_back_to_the_module_name():
    """Which is what keeps an untouched single-copy module named as it is."""
    assert copy_name({"slug": "", "name": ""}, "arm") == "arm"
    assert copy_name({"slug": "", "name": "index"}, "fingers") == "index"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `mayapy -m pytest tests/unit/test_module_copies_trigger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.core.copies'`

- [ ] **Step 3: Implement `core/copies.py`**

```python
"""The copy list: one module, N repeats of itself.

Pure data. A copy is a row: a slug that keys its guides, a name that reaches
the rig, and a value for every field the module declares ``per_copy``.

The slug and the name are deliberately different things. The slug is minted
once and never reused, so renaming a copy or dragging its tab cannot orphan a
guide pose -- the same trap the pivot-preset spec called out and avoided the
same way. The name is the rigger's, and it is what the built nodes are called.

**The first slug is the empty string**, so its roles are ``root``/``segment``
exactly as every module writes today. That is what makes every existing
``.tr`` already a valid one-copy module: no migration, no schema bump, and
adding a second copy cannot disturb the first.

Spec: ``docs/superpowers/specs/2026-09-10-module-copies-design.md``
"""

from __future__ import annotations

from typing import Iterable, Optional

from .exceptions import TriggerError

#: The first copy carries no prefix, so a one-copy module is today's module.
EMPTY_SLUG = ""


class CopyError(TriggerError):
    """A copy-list operation the module refuses."""


def new_slug(existing: Iterable[str]) -> str:
    """A slug no copy has ever held. Never reuses one still in ``existing``."""
    taken = set(existing)
    index = 1
    while f"c{index}" in taken:
        index += 1
    return f"c{index}"


def normalise(rows, per_copy_defaults: dict, module_name: str) -> list[dict]:
    """Return well-formed copy rows: at least one, each fully populated.

    Values for keys that are no longer ``per_copy`` are dropped rather than
    carried, so a module that stops declaring a field does not leave stale
    data in every ``.tr`` that ever used it.
    """
    found = []
    for row in rows or [{"slug": EMPTY_SLUG, "name": ""}]:
        clean = {"slug": str(row.get("slug", EMPTY_SLUG)), "name": row.get("name", "")}
        for key, default in per_copy_defaults.items():
            clean[key] = row[key] if key in row else default
        found.append(clean)
    return found


def row_for(rows, slug: str) -> Optional[dict]:
    """The row with ``slug``, or None."""
    return next((row for row in rows if row.get("slug") == slug), None)


def copy_name(row, module_name: str) -> str:
    """The name this copy builds under.

    A blank name falls back to the module's own, which is what keeps a module
    nobody has added copies to named exactly as it is today.
    """
    return row.get("name") or module_name


def duplicate_row(rows, slug: str, per_copy_defaults: dict, taken_names) -> dict:
    """The ``[+]`` verb: a new row carrying ``slug``'s values.

    Its values, not the field defaults: a fifth finger wants the fourth
    finger's settings. Its guides are copied by the caller, which is what
    lands the new copy stacked on the one it came from -- an unplaced thing
    should look unplaced.
    """
    source = row_for(rows, slug)
    if source is None:
        raise CopyError(f"There is no copy '{slug}' to duplicate.")
    made = dict(source)
    made["slug"] = new_slug(row.get("slug", "") for row in rows)
    made["name"] = _free_name(source.get("name") or "copy", taken_names)
    return made


def _free_name(name: str, taken) -> str:
    """``index`` -> ``index1`` -> ``index2`` until it is free."""
    taken = set(taken)
    base = name.rstrip("0123456789") or name
    candidate, index = name, 1
    while candidate in taken:
        candidate = f"{base}{index}"
        index += 1
    return candidate
```

- [ ] **Step 4: Run it to verify it passes**

Run: `mayapy -m pytest tests/unit/test_module_copies_trigger.py -v`
Expected: 10 passed

- [ ] **Step 5: Add the `copies` field to `Module`**

In `src/python/tik/trigger/core/module.py`, import and declare it beside the
other base fields:

```python
from tik.core.fields import Column, FieldGroup, ListField, Schema, TableField

from . import copies as copy_list
```

```python
    copies = ListField(
        [],
        label="Copies",
        hidden=True,
        help="One row per copy of this module.",
        last=True,
    )
    """Hidden because the tab bar is its editor, the same arrangement
    ``filterable`` uses for the ``<name>_only_selected`` field it injects."""
```

and the two readers:

```python
    def copy_rows(self) -> list[dict]:
        """Well-formed copy rows: at least one, each fully populated."""
        defaults = {
            name: field.default
            for name, field in type(self).per_copy_fields().items()
        }
        return copy_list.normalise(self.copies, defaults, self.name)

    def copy_slugs(self) -> list[str]:
        """Every copy's slug, in tab order. ``[""]`` for an untouched module."""
        return [row["slug"] for row in self.copy_rows()]
```

- [ ] **Step 6: Test the module-level readers**

Append to `tests/unit/test_module_copies_trigger.py`:

```python
def _toy():
    from tik.core.fields import FloatField, IntField
    from tik.trigger.core import GuideLayout, Module

    class Toy(Module):
        module_type = "toy"
        guides = GuideLayout("root", multi="segment", min=1)
        outputs = ("root", "end")
        controls = ("fk",)
        segments = IntField(2, per_copy=True)
        size = FloatField(1.0)

        def draw_guides(self, guides):
            guides.joint("root", (0, 0, 0))
            for index in range(self.segments):
                guides.joint("segment", (index + 1, 0, 0), index=index)

        def build(self, rig):
            pass

    return Toy


def test_an_untouched_module_has_exactly_one_empty_slug():
    module = _toy()(name="arm")
    assert module.copy_slugs() == [EMPTY_SLUG]


def test_copy_rows_carry_the_per_copy_defaults():
    module = _toy()(name="arm")
    assert module.copy_rows()[0]["segments"] == 2


def test_a_shared_field_is_not_in_the_rows():
    module = _toy()(name="arm")
    assert "size" not in module.copy_rows()[0]
```

- [ ] **Step 7: Run and commit**

Run: `mayapy -m pytest tests/unit/test_module_copies_trigger.py -q`
Expected: 13 passed

```bash
git add src/python/tik/trigger/core/copies.py src/python/tik/trigger/core/module.py tests/unit/test_module_copies_trigger.py
git commit -m "Module copies: the copy list and its slugs"
```

---

### Task 3: The per-copy view

**Files:**
- Modify: `src/python/tik/trigger/core/module.py`
- Test: `tests/unit/test_module_copies_trigger.py`

**Interfaces:**
- Consumes: `copy_rows()`, `copy_name()` from Task 2.
- Produces: `Module.for_copy(slug: str) -> Module` — the same class, with the copy's per-copy values applied, its name set to the copy's name, and a `copies` list holding only that row (so the view is itself a well-formed one-copy module and every manifest call on it returns *bare* names).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_module_copies_trigger.py`:

```python
def test_the_view_resolves_the_copys_per_copy_values():
    """Inside build(), self.segments is a plain int -- the module author
    never learns that copies exist."""
    module = _toy()(name="fingers")
    module.copies = [
        {"slug": "", "name": "index", "segments": 4},
        {"slug": "c1", "name": "thumb", "segments": 3},
    ]
    assert module.for_copy("").segments == 4
    assert module.for_copy("c1").segments == 3


def test_the_view_takes_the_copys_name():
    module = _toy()(name="fingers")
    module.copies = [{"slug": "", "name": "index", "segments": 4}]
    assert module.for_copy("").name == "index"


def test_a_blank_copy_name_leaves_the_module_name():
    module = _toy()(name="arm")
    assert module.for_copy("").name == "arm"


def test_the_view_keeps_the_shared_fields():
    module = _toy()(name="fingers", settings={"size": 7.0})
    assert module.for_copy("").size == 7.0


def test_the_view_is_itself_a_one_copy_module():
    """So every manifest call on it returns bare, unqualified names."""
    module = _toy()(name="fingers")
    module.copies = [
        {"slug": "", "name": "index", "segments": 4},
        {"slug": "c1", "name": "thumb", "segments": 3},
    ]
    assert module.for_copy("c1").copy_slugs() == [EMPTY_SLUG]


def test_the_view_keeps_the_modules_side_and_id():
    from tik.core.side import Side

    module = _toy()(name="fingers", side=Side.LEFT)
    view = module.for_copy("")
    assert view.side is Side.LEFT
    assert view.instance_id == module.instance_id


def test_an_unknown_slug_is_refused():
    module = _toy()(name="fingers")
    with pytest.raises(CopyError, match="no copy"):
        module.for_copy("nope")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `mayapy -m pytest tests/unit/test_module_copies_trigger.py -k for_copy -v`
Expected: FAIL — `AttributeError: 'Toy' object has no attribute 'for_copy'`

- [ ] **Step 3: Implement**

```python
    def for_copy(self, slug: str) -> "Module":
        """This module as one of its copies sees itself.

        Same class, the copy's per-copy values applied, named after the copy,
        and holding only that copy's row -- so the view is a well-formed
        one-copy module and every manifest call on it returns *bare* names.
        That is the whole trick: ``build()`` and ``draw_guides()`` receive an
        ordinary single-copy module and no module author writes anything.
        """
        rows = self.copy_rows()
        row = copy_list.row_for(rows, slug)
        if row is None:
            raise copy_list.CopyError(f"There is no copy '{slug}' on '{self.name}'.")
        settings = self.values()
        settings.update(
            {
                name: row[name]
                for name in type(self).per_copy_fields()
                if name in row
            }
        )
        settings["copies"] = [dict(row, slug=copy_list.EMPTY_SLUG)]
        view = type(self)(
            instance_id=self.instance_id,
            name=copy_list.copy_name(row, self.name),
            side=self.side,
            settings=settings,
        )
        return view
```

- [ ] **Step 4: Run and commit**

Run: `mayapy -m pytest tests/unit/test_module_copies_trigger.py -q`
Expected: 20 passed

```bash
git add src/python/tik/trigger/core/module.py tests/unit/test_module_copies_trigger.py
git commit -m "Module copies: the per-copy view"
```

---

### Task 4: Role expansion and manifest qualification

**Files:**
- Modify: `src/python/tik/trigger/core/module.py` (`expected_guides` at 308, `validate` at 316, `output_names`, `control_names`, `control_shape_defaults`, `control_orient_defaults`)
- Test: `tests/unit/test_module_copies_trigger.py`

**Interfaces:**
- Consumes: `copy_rows()`, `for_copy()`.
- Produces:
  - `Module.qualify(slug: str, name: str) -> str` — `""` → `name`, `"c1"` → `"c1_name"`
  - `expected_guides()` returns the layout expanded once per copy, roles qualified
  - `output_names(settings)` / `control_names(settings)` / `control_shape_defaults(settings)` / `control_orient_defaults(settings)` return copy-qualified names
  - `validate()` accepts the expanded roles

**Note on the classmethods.** `output_names` and friends are classmethods taking `settings`. Keep the author's single-copy override exactly as it is and qualify *around* it: rename the author-facing hook to `<name>_for_copy` on the base class, have the base `output_names` loop the copies in `settings` and call the hook per copy. `fkchain` overrides `output_names` today, so the base must dispatch to the subclass's override — call `cls.output_names.__func__` on a one-copy settings dict, not a new hook name, to avoid touching every module. Concretely: build a one-copy settings dict per row and re-enter the subclass override with it.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_module_copies_trigger.py`:

```python
def test_qualify_leaves_the_first_copy_bare():
    module = _toy()(name="arm")
    assert module.qualify("", "root") == "root"
    assert module.qualify("c1", "root") == "c1_root"


def test_one_copy_expands_to_todays_roles_exactly():
    """The zero-change guarantee, at the guide layer."""
    module = _toy()(name="arm")
    assert module.expected_guides() == [("root", 0), ("segment", 0), ("segment", 1)]


def test_a_second_copy_adds_prefixed_roles_and_disturbs_nothing():
    module = _toy()(name="fingers")
    module.copies = [
        {"slug": "", "name": "index", "segments": 2},
        {"slug": "c1", "name": "thumb", "segments": 1},
    ]
    assert module.expected_guides() == [
        ("root", 0),
        ("segment", 0),
        ("segment", 1),
        ("c1_root", 0),
        ("c1_segment", 0),
    ]


def test_outputs_are_qualified_per_copy():
    Toy = _toy()
    settings = {
        "copies": [
            {"slug": "", "name": "index"},
            {"slug": "c1", "name": "thumb"},
        ]
    }
    assert Toy.output_names(settings) == ("root", "end", "c1_root", "c1_end")


def test_one_copy_leaves_the_outputs_bare():
    Toy = _toy()
    assert Toy.output_names({}) == ("root", "end")


def test_controls_are_qualified_per_copy():
    Toy = _toy()
    settings = {
        "copies": [
            {"slug": "", "name": "index"},
            {"slug": "c1", "name": "thumb"},
        ]
    }
    assert Toy.control_names(settings) == ("fk", "c1_fk")


def test_a_settings_driven_manifest_still_works_per_copy():
    """fkchain returns one output per segment; each copy gets its own count."""
    import tik.trigger as trigger

    trigger.load_plugins()
    from tik.trigger.core import registry

    FkChain = registry.get_module("fkchain")
    settings = {
        "copies": [
            {"slug": "", "name": "index", "segments": 2},
            {"slug": "c1", "name": "thumb", "segments": 1},
        ]
    }
    names = FkChain.output_names(settings)
    assert names[:4] == ("root", "segment1", "segment2", "end")
    assert names[4:] == ("c1_root", "c1_segment1", "c1_end")


def test_validate_accepts_the_expanded_roles():
    module = _toy()(name="fingers")
    module.copies = [
        {"slug": "", "name": "index", "segments": 2},
        {"slug": "c1", "name": "thumb", "segments": 1},
    ]
    module.guide_pairs = module.expected_guides()
    assert module.validate() == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `mayapy -m pytest tests/unit/test_module_copies_trigger.py -k "qualify or expand or qualified" -v`
Expected: FAIL — `AttributeError: 'Toy' object has no attribute 'qualify'`

- [ ] **Step 3: Implement**

```python
    @staticmethod
    def qualify(slug: str, name: str) -> str:
        """``("", "root")`` -> ``root``; ``("c1", "root")`` -> ``c1_root``.

        The first copy is bare, which is what makes an existing document
        already valid and what stops a second copy from disturbing it.
        """
        return name if not slug else f"{slug}_{name}"

    @classmethod
    def _per_copy_settings(cls, settings: Optional[dict]) -> list[tuple[str, dict]]:
        """``[(slug, one-copy settings)]`` for a settings dict.

        Re-enters the subclass's own ``output_names``/``control_names``
        override with a single-copy dict, so a module that computes its
        manifest from a setting keeps working per copy without being touched.
        """
        settings = dict(settings or {})
        defaults = {
            name: field.default for name, field in cls.per_copy_fields().items()
        }
        rows = copy_list.normalise(settings.get("copies"), defaults, "")
        found = []
        for row in rows:
            one = dict(settings)
            one.update({name: row[name] for name in defaults if name in row})
            one["copies"] = [dict(row, slug=copy_list.EMPTY_SLUG)]
            found.append((row["slug"], one))
        return found
```

Then wrap each manifest classmethod. The pattern is the same for all four;
here is `output_names`, and the others differ only in the inner call and the
return type:

```python
    @classmethod
    def output_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Outputs an instance exposes, qualified per copy.

        A module author overrides ``outputs_for_copy`` (or leaves it, and gets
        ``cls.outputs``); this method repeats it across the copies.
        """
        found: list[str] = []
        for slug, one in cls._per_copy_settings(settings):
            for name in cls.outputs_for_copy(one):
                found.append(cls.qualify(slug, name))
        return tuple(found)

    @classmethod
    def outputs_for_copy(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Outputs of a *single* copy. Override this when a setting drives them."""
        return tuple(cls.outputs)
```

Do the same for `control_names` → `controls_for_copy`,
`control_shape_defaults` → `control_shape_defaults_for_copy` (merging the
per-copy dicts under qualified keys), and `control_orient_defaults` →
`control_orient_defaults_for_copy`.

- [ ] **Step 4: Move the four module overrides onto the new hooks**

`fkchain`, `arm`, `ribbon`, `twist` and `base` override some of these. Rename
each override from `output_names` to `outputs_for_copy`, `control_names` to
`controls_for_copy`, and so on. The bodies do not change — they already take
`settings` and return one copy's worth.

```bash
grep -rn "def output_names\|def control_names\|def control_shape_defaults\|def control_orient_defaults" src/python/tik/trigger/modules/ src/python/tik/trigger/systems/
```

- [ ] **Step 5: Expand the guides and widen validate**

```python
    def expected_guides(self) -> list[tuple[str, int]]:
        """Every ``(role, index)`` this module wants, across all its copies."""
        pairs: list[tuple[str, int]] = []
        for row in self.copy_rows():
            view = self.for_copy(row["slug"])
            for role, index in view.guides.expand(view.guide_count()):
                pairs.append((self.qualify(row["slug"], role), index))
            for role in view.pivot_guide_roles(view.values()):
                pairs.append((self.qualify(row["slug"], role), 0))
        return pairs
```

and `validate` checks each copy's own pairs through its view, stripping the
prefix before handing them to `GuideLayout.validate`.

- [ ] **Step 6: Run everything**

Run: `mayapy -m pytest tests/unit tests/integration -q`
Expected: all passed. The manifest is the spine of the build, so a regression
here shows up immediately in `tests/integration/trigger/`.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/core/module.py src/python/tik/trigger/modules src/python/tik/trigger/systems tests/unit/test_module_copies_trigger.py
git commit -m "Module copies: expand roles and qualify the manifest per copy"
```

---

### Task 5: `expand_guides` takes pairs

**Files:**
- Modify: `src/python/tik/trigger/core/guide_document.py:434`
- Modify: `src/python/tik/trigger/guides/exchange.py:239`, `src/python/tik/trigger/guides/scene.py` at 324, 499, 797
- Test: `tests/unit/test_guide_document_trigger.py`

**Interfaces:**
- Consumes: `Module.expected_guides()` from Task 4.
- Produces: `expand_guides(entry, pairs)` — the layout/count/extra arguments are gone; every caller now passes `module.expected_guides()`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_guide_document_trigger.py`:

```python
def test_expand_guides_matches_the_entry_to_the_pairs():
    entry = ModuleEntry("a", "toy", "arm", "L")
    entry.guides = [GuideRecord(role="root", position=(1.0, 2.0, 3.0))]
    expand_guides(entry, [("root", 0), ("c1_root", 0)])
    assert [record.pair for record in entry.guides] == [("root", 0), ("c1_root", 0)]


def test_survivors_keep_their_pose():
    entry = ModuleEntry("a", "toy", "arm", "L")
    entry.guides = [GuideRecord(role="root", position=(1.0, 2.0, 3.0))]
    expand_guides(entry, [("root", 0), ("c1_root", 0)])
    assert entry.guide("root", 0).position == (1.0, 2.0, 3.0)
    assert entry.guide("c1_root", 0).position is None


def test_dropped_pairs_go_away():
    entry = ModuleEntry("a", "toy", "arm", "L")
    entry.guides = [GuideRecord(role="root"), GuideRecord(role="c1_root")]
    expand_guides(entry, [("root", 0)])
    assert [record.pair for record in entry.guides] == [("root", 0)]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `mayapy -m pytest tests/unit/test_guide_document_trigger.py -k expand_guides -v`
Expected: FAIL — `TypeError: expand_guides() missing 2 required positional arguments`

- [ ] **Step 3: Implement**

```python
def expand_guides(entry: ModuleEntry, pairs) -> None:
    """Match ``entry.guides`` to ``pairs``, keeping every survivor's record.

    The document-side answer to a settings change that adds or removes guides
    -- ``fkchain.segments`` 3 -> 5, a pivot-preset row, or a copy added or
    removed. Survivors keep their records untouched; new pairs arrive unposed,
    so regenerate places them at their ``draw_guides`` position rather than at
    the origin.

    Takes the pairs rather than a layout and a count because a module's guides
    are no longer one layout expanded once: they are its layout expanded once
    per copy, which only the module can work out (``expected_guides``).
    """
    existing = {record.pair: record for record in entry.guides}
    entry.guides = [
        existing.get(pair) or GuideRecord(role=pair[0], index=pair[1])
        for pair in pairs
    ]
```

- [ ] **Step 4: Update the four call sites**

Each currently reads roughly:

```python
expand_guides(entry, module.guides, module.guide_count(),
              extra=module.pivot_guide_roles(module.values()))
```

and becomes:

```python
expand_guides(entry, module.expected_guides())
```

- [ ] **Step 5: Run everything and commit**

Run: `mayapy -m pytest tests/unit tests/integration -q`
Expected: all passed

```bash
git add src/python/tik/trigger/core/guide_document.py src/python/tik/trigger/guides tests/unit/test_guide_document_trigger.py
git commit -m "Guides: expand_guides takes the pairs a module wants"
```

---

### Task 6: Drawing every copy

**Files:**
- Modify: `src/python/tik/trigger/core/module.py` (`draw_all_guides`)
- Modify: `src/python/tik/trigger/guides/regenerate.py`
- Test: `tests/integration/trigger/test_module_copies_trigger.py` (create)

**Interfaces:**
- Consumes: `for_copy`, `qualify`, `expected_guides`.
- Produces: `draw_all_guides(draft)` draws every copy, each through its own view, with roles qualified as they are created. The `GuideDraft.joint(role, ...)` call inside a module body stays unqualified — the draft is given the copy's slug and qualifies on the way in.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/trigger/test_module_copies_trigger.py`:

```python
"""Module copies against a real scene.

The ``scene`` fixture comes from ``tests/integration/trigger/conftest.py``.
"""


def _two_copies(scene):
    handle = scene.add("fkchain", name="fingers", side="L", segments=2)
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 1, "spacing": 5.0},
    ]
    return handle


def test_one_copy_draws_todays_guides(scene):
    """The zero-change guarantee, in the scene."""
    handle = scene.add("fkchain", name="tail", side="C", segments=3)
    scene.draw()
    roles = sorted(role for role, _index in scene.guide_nodes(handle.instance_id))
    assert roles == ["root", "segment", "segment", "segment"]


def test_a_second_copy_draws_its_own_guides(scene):
    handle = _two_copies(scene)
    scene.draw()
    pairs = set(scene.guide_nodes(handle.instance_id))
    assert ("root", 0) in pairs
    assert ("c1_root", 0) in pairs
    assert ("c1_segment", 0) in pairs


def test_adding_a_copy_leaves_the_first_copys_pose_alone(scene):
    from maya import cmds

    handle = scene.add("fkchain", name="fingers", side="L", segments=2)
    scene.draw()
    node = scene.guide_node(handle.instance_id, "root").long_name
    cmds.xform(node, worldSpace=True, translation=(7.0, 8.0, 9.0))
    scene.sync()
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 2, "spacing": 5.0},
    ]
    scene.draw()
    moved = scene.guide_node(handle.instance_id, "root").long_name
    assert cmds.xform(moved, query=True, worldSpace=True, translation=True) == [
        7.0,
        8.0,
        9.0,
    ]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `mayapy -m pytest tests/integration/trigger/test_module_copies_trigger.py -v`
Expected: FAIL — the second copy draws no guides.

- [ ] **Step 3: Implement**

In `core/module.py`:

```python
    def draw_all_guides(self, draft) -> None:
        """Every copy's guides, each drawn through that copy's own view.

        The module author's ``draw_guides`` sees an ordinary single-copy
        module and names its roles bare; ``draft`` carries the copy's slug and
        qualifies them on the way in, so no module body changes.
        """
        for row in self.copy_rows():
            view = self.for_copy(row["slug"])
            with draft.for_copy(row["slug"]):
                view.draw_guides(draft)
                view._draw_pivot_guides(draft)
```

and in `maya/rig.py`, `GuideDraft` gains the slug scope (the file does not
import `contextmanager` yet — add `from contextlib import contextmanager`):

```python
    @contextmanager
    def for_copy(self, slug: str):
        """Qualify every role created inside this block with ``slug``."""
        previous, self._slug = getattr(self, "_slug", ""), slug
        try:
            yield self
        finally:
            self._slug = previous
```

with `GuideDraft.joint` qualifying `role` through `Module.qualify(self._slug,
role)` before the duplicate check and the tag write, and `draft.created`
keyed by the qualified pair. `self.root` must reset per copy so each copy's
first joint becomes its own root.

- [ ] **Step 4: Run and commit**

Run: `mayapy -m pytest tests/integration/trigger/test_module_copies_trigger.py tests/integration -q`
Expected: all passed

```bash
git add src/python/tik/trigger/core/module.py src/python/tik/trigger/maya/rig.py tests/integration/trigger/test_module_copies_trigger.py
git commit -m "Module copies: draw every copy's guides"
```

---

### Task 7: Copy names are unique

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py:588` (`unique_name`)
- Modify: `src/python/tik/trigger/core/module.py` (`warnings`)
- Test: `tests/integration/trigger/test_module_copies_trigger.py`

**Interfaces:**
- Consumes: `copy_rows`, `copy_name`.
- Produces: `GuideScene.unique_name` counts copy names as taken; `Module.warnings()` reports a duplicate copy name.

**Why it matters.** The module name never reaches the rig (spec §5), so two
modules on one side can both hold a copy called `index` and their controls
would collide. Nothing else catches that.

- [ ] **Step 1: Write the failing test**

Append to the integration test file:

```python
def test_a_copy_name_is_taken_for_naming_purposes(scene):
    handle = scene.add("fkchain", name="fingers", side="L")
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 2, "spacing": 5.0},
    ]
    assert scene.unique_name("index", "L") != "index"


def test_two_copies_with_one_name_are_a_warning(scene):
    from tik.trigger.core import registry

    handle = scene.add("fkchain", name="fingers", side="L")
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "index", "segments": 2, "spacing": 5.0},
    ]
    module = registry.get_module("fkchain").from_instance(handle.instance)
    assert any("index" in item for item in module.warnings())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `mayapy -m pytest tests/integration/trigger/test_module_copies_trigger.py -k name -v`
Expected: FAIL — `assert 'index' != 'index'`

- [ ] **Step 3: Implement**

In `unique_name`, widen the taken set:

```python
        taken = {entry.key for entry in self.document.modules} | {
            group.name for group in self.document.scene_groups
        }
        # Copy names reach the rig where the module name does not, so two
        # modules each holding a copy called `index` would collide.
        for entry in self.document.modules:
            module_cls = registry.get_module(entry.module_type)
            module = module_cls.from_instance(
                ModuleInstance(
                    module_type=entry.module_type,
                    instance_id=entry.instance_id,
                    name=entry.name,
                    side=entry.side,
                    settings=entry.settings,
                )
            )
            for row in module.copy_rows():
                taken.add(instance_key(copy_list.copy_name(row, entry.name), entry.side))
```

and in `Module.warnings()`:

```python
        seen: set = set()
        for row in self.copy_rows():
            name = copy_list.copy_name(row, self.name)
            if name in seen:
                problems.append(
                    f"two copies are both called '{name}'; their controls "
                    f"would collide"
                )
            seen.add(name)
```

- [ ] **Step 4: Run and commit**

Run: `mayapy -m pytest tests/unit tests/integration -q`
Expected: all passed

```bash
git add src/python/tik/trigger/guides/scene.py src/python/tik/trigger/core/module.py tests/integration/trigger/test_module_copies_trigger.py
git commit -m "Module copies: copy names are unique, because they reach the rig"
```

---

### Task 8: The build loop

The task the whole design rests on. Both invariant tests live here.

**Files:**
- Modify: `src/python/tik/trigger/maya/build.py` (`_build_one` at 550, the build loop at 240-330)
- Test: `tests/integration/trigger/test_copy_invariant_trigger.py` (create)

**Interfaces:**
- Consumes: `for_copy`, `qualify`, `copy_rows`.
- Produces: `Builder._build_one` builds every copy of an instance and merges their outputs into one map under qualified names. A copy is not independently schedulable: a module's copies build together, in list order.

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/trigger/test_copy_invariant_trigger.py`:

```python
"""The two guarantees the copy model rests on.

The ``scene`` fixture comes from ``tests/integration/trigger/conftest.py``.
"""

from maya import cmds

from tik.trigger.maya import sandbox
from tik.trigger.maya.scaffold import TEST_ROOT


def _shape():
    """A stable description of the built test rig."""
    nodes = sorted(cmds.ls(TEST_ROOT, dag=True, long=True) or [])
    return [
        (
            name.rsplit("|", 1)[-1],
            cmds.nodeType(name),
            sorted(cmds.listRelatives(name, children=True) or []),
        )
        for name in nodes
    ]


def test_one_copy_builds_todays_rig(scene):
    """No migration, no schema bump, nothing renamed."""
    scene.add("fkchain", name="tail", side="C", segments=3)
    scene.draw()
    scene.test_build()
    assert _shape(), "the build produced nothing to compare"
    assert cmds.ls("tail_fk0*"), "a one-copy module must build under its own name"


def test_copies_build_what_separate_modules_build(scene):
    """The naming decision from the spec's question two, made falsifiable."""
    for name in ("index", "middle", "thumb"):
        scene.add("fkchain", name=name, side="L", segments=2)
    scene.draw()
    scene.test_build()
    separate = _shape()
    assert separate, "the build produced nothing to compare"

    sandbox.clear()
    scene.clear()
    handle = scene.add("fkchain", name="fingers", side="L", segments=2)
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "middle", "segments": 2, "spacing": 5.0},
        {"slug": "c2", "name": "thumb", "segments": 2, "spacing": 5.0},
    ]
    scene.draw()
    scene.test_build()

    assert _shape() == separate


def test_a_copys_outputs_are_addressable(scene):
    handle = scene.add("fkchain", name="fingers", side="L", segments=2)
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 2, "spacing": 5.0},
    ]
    assert "c1_end" in handle.outputs
    assert "end" in handle.outputs
```

- [ ] **Step 2: Run them to verify they fail**

Run: `mayapy -m pytest tests/integration/trigger/test_copy_invariant_trigger.py -v`
Expected: FAIL on the second and third — only one copy builds.

- [ ] **Step 3: Implement**

Rework `_build_one` to loop the copies. Each copy gets its own per-copy
`ModuleInstance` — this is what makes `ModuleRig.name` (which reads
`self.instance.name`, `maya/rig.py:264`) produce `L_index_fk0` with no change
to the naming code:

```python
    def _build_one(self, instance: ModuleInstance, scaffold, bind_parent=None):
        module_cls = registry.get_module(instance.module_type)
        module = module_cls.from_instance(instance)
        problems = module.validate()
        if problems:
            raise BuildError(...)
        for warning in module.warnings():
            self.events.log(f"{instance.key}: {warning}", level="warning")
        merged: dict = {}
        for row in module.copy_rows():
            slug = row["slug"]
            view = module.for_copy(slug)
            copy_instance = self._copy_instance(instance, view, slug)
            ctx = build_context(view, copy_instance, scaffold, bind_parent)
            view.build(ctx)
            # The module's outputs are its copies' outputs, qualified. The
            # author registers `end`; the module publishes `c1_end`.
            for name, node in ctx.outputs.items():
                merged[module_cls.qualify(slug, name)] = node
        missing = [
            name
            for name in module_cls.output_names(instance.settings)
            if name not in merged
        ]
        if missing:
            raise BuildError(...)
```

`_copy_instance` builds the per-copy `ModuleInstance`: the copy's name, the
view's settings, and only this copy's guide poses with the slug stripped from
their roles, so the module body sees `root` and `segment` as always.

Keep one `ctx` per *instance* in whatever registry `_connect_one` and
`resolve` read (`producer_ctx.outputs` at `build.py:399` and `:526`) so a
consumer naming `L_fingers.c1_end` resolves. The simplest shape is a small
holder object carrying `merged` as its `.outputs`.

- [ ] **Step 4: Run the invariants**

Run: `mayapy -m pytest tests/integration/trigger/test_copy_invariant_trigger.py -v`
Expected: all passed. **If the second fails, the naming is wrong — fix the
naming, not the test.**

- [ ] **Step 5: Run everything**

Run: `mayapy -m pytest tests/unit tests/integration -q`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/maya/build.py tests/integration/trigger/test_copy_invariant_trigger.py
git commit -m "Module copies: build every copy, merge their outputs"
```

---

### Task 9: The tab bar

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/window.py` (`_build_properties_pane` at 258, `_set_current` at 872)
- Test: `tests/ui/test_copy_tabs.py` (create)

**Interfaces:**
- Consumes: `copy_rows`, `copy_slugs`, `duplicate_row`.
- Produces on the designer: `tab_bar` (a `QTabBar`), `add_copy_button`, `current_slug() -> str`, `_on_copy_tab_changed(index)`, `_on_add_copy()`, `_on_copy_renamed(index, text)`, `_on_copy_tabs_reordered()`, `_on_remove_copy()`.

**First, give the toy module something to test with.** `ToyChain`
(`tests/helpers/toy_modules.py`) declares only `segments = IntField(2, min=1)`
and no shared field, so neither side of the split can be asserted. Change it
to:

```python
class ToyChain(Module):
    ...
    segments = IntField(2, min=1, per_copy=True)
    controller_size = FloatField(1.0)   # shared: one value for the set
```

adding `FloatField` to its imports. `controls_for_copy` (the renamed hook from
Task 4) stays as it is. Run the full UI suite after this edit and before
writing anything else — several existing tests construct `ToyChain`.

**UI test conventions** (the superseded plan got these wrong — do not repeat
it): tests import `from stub import StubScene` and `from toy_modules import
...`, register with `clear_registries()` / `register_module(...)`, construct
`GuideDesigner(scene=StubScene())`, and select through the tree:

```python
def _select(designer, handle):
    designer.refresh()
    item = designer.item_for(handle.instance_id)
    designer.tree.setCurrentItem(item)
    item.setSelected(True)
```

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_copy_tabs.py`:

```python
"""The copy tab bar. It edits a settings field and nothing else."""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module
from tik.trigger.ui.designer import GuideDesigner


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


@pytest.fixture
def designer(qapp):
    window = GuideDesigner(scene=StubScene())
    window.show()
    yield window
    window.close()


def _select(designer, handle):
    designer.refresh()
    item = designer.item_for(handle.instance_id)
    designer.tree.setCurrentItem(item)
    item.setSelected(True)


def _chain(designer, name="fingers"):
    handle = designer.guides.add("toy_chain", name=name, side="L")
    _select(designer, handle)
    return handle


def test_an_untouched_module_shows_one_tab(designer):
    _chain(designer, name="arm")
    assert designer.tab_bar.count() == 1
    assert designer.tab_bar.tabText(0) == "arm"
    assert designer.add_copy_button.isEnabled()


def test_plus_adds_a_copy_and_selects_its_tab(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    assert designer.tab_bar.count() == 2
    assert designer.tab_bar.currentIndex() == 1
    assert len(handle.settings["copies"]) == 2


def test_the_new_copy_carries_the_current_copys_values(designer):
    handle = _chain(designer)
    handle.segments = 7
    _select(designer, handle)
    designer._on_add_copy()
    rows = handle.settings["copies"]
    assert rows[1]["segments"] == 7


def test_the_new_copy_gets_a_free_name(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    names = [row["name"] for row in handle.settings["copies"]]
    assert len(set(names)) == 2


def test_renaming_a_tab_renames_the_copy(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer._on_copy_renamed(1, "thumb")
    assert handle.settings["copies"][1]["name"] == "thumb"
    assert designer.tab_bar.tabText(1) == "thumb"


def test_removing_a_copy_drops_its_row(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer.tab_bar.setCurrentIndex(1)
    designer._on_remove_copy()
    assert len(handle.settings["copies"]) == 1
    assert designer.tab_bar.count() == 1


def test_the_last_copy_cannot_be_removed(designer):
    """A module always has at least one copy: itself."""
    handle = _chain(designer)
    designer._on_remove_copy()
    assert len(handle.settings["copies"]) == 1


def test_reordering_tabs_reorders_the_rows(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer._on_copy_renamed(0, "a")
    designer._on_copy_renamed(1, "b")
    designer.tab_bar.moveTab(0, 1)
    assert [row["name"] for row in handle.settings["copies"]] == ["b", "a"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui/test_copy_tabs.py -v`
Expected: FAIL — `AttributeError: 'GuideDesigner' object has no attribute 'tab_bar'`

- [ ] **Step 3: Build the tab bar**

In `_build_properties_pane`, above the `MODULE` caption:

```python
        tabs = QtWidgets.QHBoxLayout()
        tabs.setContentsMargins(0, 0, 0, 0)
        tabs.setSpacing(0)
        self.tab_bar = QtWidgets.QTabBar()
        self.tab_bar.setMovable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.add_copy_button = QtWidgets.QToolButton()
        self.add_copy_button.setText("+")
        self.add_copy_button.setAutoRaise(True)
        self.add_copy_button.setToolTip("Add another copy of this module")
        tabs.addWidget(self.tab_bar)
        tabs.addWidget(self.add_copy_button)
        tabs.addStretch(1)
        props.addLayout(tabs)
```

and wire the signals beside the existing `self.form.changed.connect(...)`:

```python
        self.tab_bar.currentChanged.connect(self._on_copy_tab_changed)
        self.tab_bar.tabMoved.connect(self._on_copy_tabs_reordered)
        self.tab_bar.tabBarDoubleClicked.connect(self._on_copy_tab_double_clicked)
        self.add_copy_button.clicked.connect(self._on_add_copy)
```

- [ ] **Step 4: Implement the verbs**

```python
    def current_slug(self) -> str:
        """The slug of the copy whose tab is showing. ``""`` when there is none."""
        if self._module_obj is None:
            return copy_list.EMPTY_SLUG
        slugs = self._module_obj.copy_slugs()
        index = self.tab_bar.currentIndex()
        return slugs[index] if 0 <= index < len(slugs) else slugs[0]

    def _rebuild_copy_tabs(self) -> None:
        """One tab per copy. Signals are blocked: this reflects state, it
        does not change it."""
        self.tab_bar.blockSignals(True)
        try:
            while self.tab_bar.count():
                self.tab_bar.removeTab(0)
            if self._module_obj is not None:
                for row in self._module_obj.copy_rows():
                    self.tab_bar.addTab(
                        copy_list.copy_name(row, self._module_obj.name)
                    )
        finally:
            self.tab_bar.blockSignals(False)
        self.add_copy_button.setEnabled(self._module_obj is not None)

    def _write_copies(self, rows) -> None:
        """Store the copy list back on the current module."""
        if self._current is None:
            return
        self._module_obj.copies = [dict(row) for row in rows]
        self._current.copies = self._module_obj.copies
```

with `_on_add_copy` calling `copy_list.duplicate_row`, `_on_remove_copy`
refusing to drop the last row, `_on_copy_renamed` writing `row["name"]`, and
`_on_copy_tabs_reordered` reordering the list to match the tab texts.

**`_on_copy_tab_changed` must not touch the selection.** It re-renders the
form for the new copy and nothing else — no `_set_current`, no tree call.

- [ ] **Step 5: Call `_rebuild_copy_tabs` from `_set_current`**

After `self.form.set_target(self._module_obj)`, and in the `handle is None`
branch too.

- [ ] **Step 6: Run and commit**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui -q`
Expected: all passed

```bash
git add src/python/tik/trigger/ui/designer/window.py tests/ui/test_copy_tabs.py
git commit -m "Designer: a tab bar over a module's copies"
```

---

### Task 10: Per-copy fields render in the tab, and the selection is untouched

**Files:**
- Modify: `src/python/tik/shared/ui/fields.py` (`FormBuilder`)
- Modify: `src/python/tik/trigger/ui/designer/window.py`, `properties.py`
- Test: `tests/ui/test_copy_tabs.py`

**Interfaces:**
- Consumes: `Schema.per_copy_fields()`, `Schema.shared_fields()`, `current_slug()`.
- Produces: a second `FormBuilder` (`self.copy_form`) below the tab bar showing only the per-copy fields, with the shared form above showing the rest; writes from `copy_form` land in the current copy's row.

`FormBuilder.set_visible_fields(names)` already exists (`fields.py:654`) and
hides a fold whose fields are all hidden, so no new form plumbing is needed —
two builders over the same target, each given its half.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_copy_tabs.py`:

```python
def test_a_per_copy_field_renders_in_the_copy_form(designer):
    handle = _chain(designer)
    assert designer.copy_form.widget("segments") is not None
    assert designer.copy_form.widget("segments").isVisible()


def test_a_shared_field_renders_above_the_tabs(designer):
    _chain(designer)
    module_cls = type(designer._module_obj)
    assert "segments" in module_cls.per_copy_fields()
    assert "controller_size" in module_cls.shared_fields()
    assert designer.form.widget("controller_size").isVisible()


def test_editing_a_per_copy_field_writes_to_the_current_copy(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer.tab_bar.setCurrentIndex(1)
    designer._module_obj.segments = 9
    designer._on_setting_changed("segments", 9)
    rows = handle.settings["copies"]
    assert rows[1]["segments"] == 9
    assert rows[0]["segments"] != 9


def test_editing_a_shared_field_writes_to_the_module(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer._module_obj.controller_size = 4.0
    designer._on_setting_changed("controller_size", 4.0)
    assert handle.settings["controller_size"] == 4.0
    assert "controller_size" not in handle.settings["copies"][0]


def test_switching_tabs_shows_that_copys_values(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer.tab_bar.setCurrentIndex(1)
    designer._module_obj.segments = 9
    designer._on_setting_changed("segments", 9)
    designer.tab_bar.setCurrentIndex(0)
    assert designer._module_obj.segments != 9


# ----------------------------------------------- the rule that broke before
def test_switching_tabs_does_not_change_the_selection(designer):
    """The Designer has exactly one selectable thing and the tree owns it."""
    handle = _chain(designer)
    designer._on_add_copy()
    before = [item.instance_id for item in designer.selected_handles()]
    designer.tab_bar.setCurrentIndex(1)
    assert [item.instance_id for item in designer.selected_handles()] == before
    assert designer._current.instance_id == handle.instance_id


def test_draw_selected_works_while_a_copy_tab_is_showing(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer.tab_bar.setCurrentIndex(1)
    designer.draw_selected()
    drawn = [call for call in designer.guides.calls if call[0] == "draw"]
    assert drawn
    assert handle.instance_id in (drawn[-1][1] or [])


def test_a_module_with_copies_is_one_tree_row(designer):
    """Five copies are one module, so the tree says one module."""
    handle = _chain(designer)
    designer._on_add_copy()
    designer._on_add_copy()
    designer.refresh()
    assert designer.tree.topLevelItemCount() == 1
    row = designer.tree.topLevelItem(0)
    assert row.text(0) == handle.key
    assert row.childCount() == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui/test_copy_tabs.py -k "copy_form or selection or draw_selected" -v`
Expected: FAIL — `AttributeError: 'GuideDesigner' object has no attribute 'copy_form'`

- [ ] **Step 3: Add the second form**

In `_build_properties_pane`, after the tab-bar layout:

```python
        self.copy_form = FormBuilder()
        props.addWidget(self.copy_form)
```

and in `_set_current`, after `self.form.set_target(self._module_obj)`:

```python
        self.copy_form.set_target(self._module_obj)
        per_copy = list(type(self._module_obj).per_copy_fields())
        self.form.set_visible_fields(
            [n for n in type(self._module_obj).fields() if n not in set(per_copy)]
        )
        self.copy_form.set_visible_fields(per_copy)
```

- [ ] **Step 4: Route the writes**

In `properties.py`, `_on_setting_changed` decides by the field, not the panel:

```python
    def _on_setting_changed(self, name: str, _value) -> None:
        if self._current is None or self._module_obj is None:
            return
        value = getattr(self._module_obj, name)
        if name in type(self._module_obj).per_copy_fields():
            # A per-copy field belongs to the copy whose tab is showing.
            rows = self._module_obj.copy_rows()
            row = copy_list.row_for(rows, self.current_slug())
            if row is None:
                return
            row[name] = value
            self._write_copies(rows)
            self.refresh()
            return
        targets = self._multi or [self._current]
        ...  # unchanged from here
```

and `_on_copy_tab_changed` re-applies the new copy's values to
`self._module_obj` so the form shows them, then calls
`self.copy_form.refresh()`.

- [ ] **Step 5: Run the whole UI suite**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui -q`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/shared/ui/fields.py src/python/tik/trigger/ui/designer tests/ui/test_copy_tabs.py
git commit -m "Designer: per-copy fields in the tab form, selection untouched"
```

---

### Task 11: Round-trip, graph, and documentation

**Files:**
- Test: `tests/unit/test_guides_trigger.py`, `tests/ui/test_copy_tabs.py`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: no new source API. `copies` is an ordinary settings field, so the
  `.tr`, the `.trg` and the reference override diff already carry it — these
  tests prove it rather than build it.

- [ ] **Step 1: Write the tests**

Append to `tests/unit/test_guides_trigger.py`:

```python
def test_copies_round_trip_through_a_trg(guides, tmp_path):
    from tik.trigger.guides import GuideScene

    handle = guides.add("fkchain", name="fingers", side="L", segments=2)
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 1, "spacing": 5.0},
    ]
    guides.draw()
    path = guides.export(tmp_path / "hand.trg")

    fresh = GuideScene()
    fresh.clear()
    fresh.import_(path, reset=True)
    restored = fresh.instances()[0]
    rows = restored.settings["copies"]
    assert [row["name"] for row in rows] == ["index", "thumb"]
    assert [row["segments"] for row in rows] == [2, 1]


def test_an_existing_tr_loads_as_a_one_copy_module(guides, tmp_path):
    """No migration: a file written before copies existed is already valid."""
    from tik.trigger.core.guide_document import GuideDocument, ModuleEntry
    from tik.trigger.core import registry

    document = GuideDocument()
    document.modules = [ModuleEntry("a", "fkchain", "tail", "C", {"segments": 3})]
    again = GuideDocument.from_dict(document.to_dict())
    module = registry.get_module("fkchain").from_instance(
        registry.get_module("fkchain")(
            instance_id="a", name="tail", settings=again.modules[0].settings
        ).to_instance()
    )
    assert module.copy_slugs() == [""]
    assert module.expected_guides()[0] == ("root", 0)
```

Append to `tests/ui/test_copy_tabs.py`:

```python
def test_a_module_with_copies_is_one_graph_node(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer.refresh()
    assert handle.key in designer.graph.graph.nodes
    assert len(designer.graph.graph.nodes) == 1


def test_the_graph_node_exposes_every_copys_outputs(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer.refresh()
    node = designer.graph.graph.nodes[handle.key]
    assert any(name.startswith("c1_") for name in node.outputs)
```

- [ ] **Step 2: Run them**

Run: `mayapy -m pytest tests/unit/test_guides_trigger.py -q` and the UI suite.
Expected: all passed. **If the `.trg` test fails, do not add a `.trg`
section** — `copies` is a settings field and settings already round-trip;
find out why this one does not.

- [ ] **Step 3: Update `CLAUDE.md`**

Add copies to the tik.trigger status paragraph (a module has a list of copies
of itself; `per_copy=True` declares which settings vary; the author writes one
copy and the framework repeats it; the copy name is the naming unit and the
module name never reaches the rig; one module means one tree row, one graph
node and one selection). Add the spec to the design-specs list, mark the
withdrawn group spec as superseded there, and add the new test files.

- [ ] **Step 4: Run everything and commit**

Run: all three suites and lint.
Expected: all passed, lint clean.

```bash
git add tests CLAUDE.md
git commit -m "Module copies: round-trip, graph and documentation"
```

---

## Self-Review Notes

**Spec coverage.** §2 the decision → Tasks 2, 3, 8. §2 `per_copy` → Task 1.
§3 the copy list and `[+]` duplicating values and poses → Tasks 2, 6, 9.
§4 slugs and the empty first slug → Tasks 2, 4. §5 names in the rig → Tasks 7,
8. §6 expansion → Tasks 4, 5; the build loop → Task 8. §7 the panel → Tasks 9,
10; the selection rule → Task 10. §8 what stays module-level → Task 10 (shared
fields) and Task 4 (the three base tables address qualified control names).
§9 what this gives up → nothing to build. §10 proof → Task 8's two invariants
and Task 10's selection test. §11 disposition → already done (commits
`d1bea7f`, `f6c182f`). §12 files, §13 tests → the task list.

**A prerequisite hidden in Task 9.** `ToyChain` gains a `per_copy` field and a
shared one before any UI test can assert the split. It is listed inside Task 9
rather than as its own task because nothing else needs it.

**Three things an executor should expect to discover.**

1. **Task 4 is the risky one.** Wrapping classmethods that subclasses already
   override is fiddly. If re-entering the subclass override with a one-copy
   settings dict proves awkward, the fallback is to rename the hook in the
   five modules that override it (`grep -rn "def output_names\|def
   control_names" src/python/tik/trigger/modules src/python/tik/trigger/systems`)
   and have the base class own the public name outright. Prefer that fallback
   over anything clever.
2. **Task 8's output registry.** `_connect_one` and `resolve` read
   `producer_ctx.outputs` (`build.py:399`, `:526`). Whatever holds the merged
   map must satisfy those two call sites; read them before writing the loop.
3. **Task 6's `GuideDraft.root`.** It is set by the first joint created. With
   copies it must reset per copy, or copy two's guides parent under copy one's
   root.

**Deferred deliberately.** Per-copy *inputs* (all copies share the module's
connections — spec §8), and the *Merge into copies* command for folding
existing separate modules (spec §9).
