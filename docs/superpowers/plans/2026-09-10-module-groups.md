# Module Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Guide Designer treat N same-type module instances as one node and one panel, so a hand is one node instead of five.

**Architecture:** A `ModuleGroup` is a document record holding `group_id`, `label` and an ordered list of member `instance_id`s. Members stay ordinary `ModuleEntry` objects — nothing about a member is special because it is a member — so build, guides, shapes, spaces, pivots, reconcile and the publish set are untouched. Which settings are "shared" is derived by comparing member values, never declared. The graph reuses the reference-frame machinery already in `ui/graph/`.

**Tech Stack:** Python 3.10+, Maya 2024+, Qt via `tik.shared.ui.Qt`, pytest under `mayapy` (unit/integration) and `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen` (ui).

**Spec:** `docs/superpowers/specs/2026-09-10-module-groups-and-tabs-design.md`

## Global Constraints

- **`tik/trigger/core` is pure Python.** No `maya`, no `tik.maya`, no Qt, no `tik.shared`, no `tik.trigger.actions`. Enforced by `tests/unit/test_import_boundaries.py`.
- **Grouping never changes the rig.** No group id, label or membership may reach `build()`, a guide joint, the bind skeleton or a node name. `trigger/maya`, `trigger/modules` and `trigger/systems` must never name `ModuleGroup` or touch `.module_groups`.
- **The document field is `module_groups`, never `groups`.** `rig.groups` is already the four per-module rig groups on the build path; a bare `groups` makes the guard above unenforceable.
- **No third-party dependencies.** Stdlib and Maya-bundled modules only.
- **Every dialog goes through `tik.shared.ui.feedback.Feedback`.** Raw `QMessageBox`/`QFileDialog`/`QInputDialog` outside `shared/ui/feedback.py` fails `tests/unit/test_dialog_boundaries.py`.
- **Consume tik.maya.** No raw `maya.cmds` / `OpenMaya` in tool code outside `tik/maya` and `tik/trigger/guides/nodes.py`.
- **Guide document schema goes 2 → 3.** The `.tr` stays at schema 7.
- Run unit/integration tests with `make tests`; UI tests with `make tests-ui`.

---

### Task 1: The `ModuleGroup` record

**Files:**
- Create: `src/python/tik/trigger/core/module_group.py`
- Test: `tests/unit/test_module_group_trigger.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ModuleGroup(group_id: str, label: str, members: list)` with `to_dict() -> dict` and `from_dict(data: dict) -> ModuleGroup`, and `key(side: str) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_module_group_trigger.py`:

```python
"""Module groups: the pure record, the operations, and shared-value derivation."""

from tik.trigger.core.module_group import ModuleGroup


def test_group_holds_members_in_tab_order():
    group = ModuleGroup(group_id="g1", label="fingers", members=["a", "b", "c"])
    assert group.members == ["a", "b", "c"]


def test_group_key_follows_side_like_a_module():
    """A group and a module name themselves by one rule: instance_key."""
    group = ModuleGroup(group_id="g1", label="fingers", members=["a"])
    assert group.key("L") == "L_fingers"
    assert group.key("C") == "fingers"
    assert group.key("") == "fingers"


def test_group_round_trips_through_dict():
    group = ModuleGroup(group_id="g1", label="fingers", members=["a", "b"])
    restored = ModuleGroup.from_dict(group.to_dict())
    assert restored == group


def test_group_from_dict_tolerates_a_missing_member_list():
    restored = ModuleGroup.from_dict({"group_id": "g1", "label": "toes"})
    assert restored.members == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `mayapy -m pytest tests/unit/test_module_group_trigger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.core.module_group'`

- [ ] **Step 3: Write the minimal implementation**

Create `src/python/tik/trigger/core/module_group.py`:

```python
"""Module groups: many copies of one module, drawn as one node.

A group is a set of same-type module instances the Guide Designer draws as a
single node and edits through a single panel. It is a document-and-UI fact and
nothing else: **grouping never changes the rig**. No group id, label or
membership reaches ``build()``, a guide joint, the bind skeleton or a node
name, and given the same members the build is identical grouped or ungrouped.

Members stay ordinary :class:`~.guide_document.ModuleEntry` objects. Nothing
about a member is special because it is a member, which is what keeps build,
guides, shapes, anim spaces, pivot presets, reconcile and the publish set out
of the feature entirely.

Membership is stored on the group, never on the entry. A ``group_id`` field on
``ModuleEntry`` would be a second copy of the same fact, and the entry is the
thing that gets serialized, diffed against a reference source and copied by
``duplicate`` -- three chances for the two copies to disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .manifest import instance_key


@dataclass
class ModuleGroup:
    """A set of same-type module instances the Designer treats as one.

    ``module_type`` and ``side`` are deliberately absent: both are properties
    of the members, enforced homogeneous when a module joins, so there is no
    second copy of either to fall out of step.
    """

    group_id: str
    label: str
    #: instance_ids, in tab order.
    members: list = field(default_factory=list)

    def key(self, side: str) -> str:
        """Display key: ``L_fingers`` / ``fingers``.

        The same function ``ModuleEntry.key`` uses, so a group and a module
        name themselves by one rule.
        """
        return instance_key(self.label, side)

    def to_dict(self) -> dict:
        """The JSON form stored in the document."""
        return {
            "group_id": self.group_id,
            "label": self.label,
            "members": list(self.members),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleGroup":
        """Rebuild a group from its JSON form."""
        return cls(
            group_id=data["group_id"],
            label=data.get("label", data["group_id"]),
            members=list(data.get("members") or []),
        )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `mayapy -m pytest tests/unit/test_module_group_trigger.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/core/module_group.py tests/unit/test_module_group_trigger.py
git commit -m "Module groups: the pure ModuleGroup record"
```

---

### Task 2: The document holds groups

**Files:**
- Modify: `src/python/tik/trigger/core/guide_document.py` (`SCHEMA_VERSION`, `GuideDocument`)
- Test: `tests/unit/test_guide_document_trigger.py`

**Interfaces:**
- Consumes: `ModuleGroup` from Task 1.
- Produces: `GuideDocument.module_groups: list`, `GuideDocument.module_group(group_id) -> Optional[ModuleGroup]`, `GuideDocument.group_of(instance_id) -> Optional[ModuleGroup]`, `SCHEMA_VERSION == 3`. Group keys appear in `node_ids()` mapped to `group_id`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_guide_document_trigger.py`:

```python
def test_document_stores_module_groups_and_looks_them_up():
    from tik.trigger.core.module_group import ModuleGroup

    document = GuideDocument()
    document.modules = [
        ModuleEntry("a", "fkchain", "index", "L"),
        ModuleEntry("b", "fkchain", "middle", "L"),
    ]
    document.module_groups = [ModuleGroup("g1", "fingers", ["a", "b"])]
    assert document.module_group("g1").label == "fingers"
    assert document.module_group("nope") is None
    assert document.group_of("b").group_id == "g1"
    assert document.group_of("a").group_id == "g1"
    assert document.group_of("c") is None


def test_group_keys_join_node_ids_under_the_member_side():
    from tik.trigger.core.module_group import ModuleGroup

    document = GuideDocument()
    document.modules = [ModuleEntry("a", "fkchain", "index", "L")]
    document.module_groups = [ModuleGroup("g1", "fingers", ["a"])]
    assert document.node_ids()["L_fingers"] == "g1"


def test_document_round_trips_module_groups():
    from tik.trigger.core.module_group import ModuleGroup

    document = GuideDocument()
    document.modules = [ModuleEntry("a", "fkchain", "index", "L")]
    document.module_groups = [ModuleGroup("g1", "fingers", ["a"])]
    restored = GuideDocument.from_dict(document.to_dict())
    assert restored.module_groups == document.module_groups
    assert restored.schema == 3


def test_a_document_without_groups_loads_with_an_empty_list():
    """Old files predate the section; there is no migration."""
    restored = GuideDocument.from_dict({"schema": 2, "modules": []})
    assert restored.module_groups == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `mayapy -m pytest tests/unit/test_guide_document_trigger.py -k module_group -v`
Expected: FAIL — `AttributeError: 'GuideDocument' object has no attribute 'module_group'`

- [ ] **Step 3: Write the minimal implementation**

In `src/python/tik/trigger/core/guide_document.py`:

Bump the version and import the record:

```python
from .module_group import ModuleGroup

SCHEMA_VERSION = 3
```

Add the field to `GuideDocument`, directly under `scene_groups` (they are siblings and read as a pair):

```python
    #: Same-type module instances the Designer draws as one node. Named
    #: ``module_groups`` rather than ``groups`` for two reasons: it is
    #: symmetric with ``scene_groups``, and ``rig.groups`` is already the four
    #: per-module rig groups all over the build path, so a bare ``groups``
    #: would make the "grouping never changes the rig" guard unenforceable.
    module_groups: list = field(default_factory=list)
```

Add the two lookups beside `group()`:

```python
    def module_group(self, group_id: str):
        """The module group with ``group_id``, or None."""
        for entry in self.module_groups:
            if entry.group_id == group_id:
                return entry
        return None

    def group_of(self, instance_id: str):
        """The module group ``instance_id`` belongs to, or None."""
        for entry in self.module_groups:
            if instance_id in entry.members:
                return entry
        return None
```

Extend `node_ids()` so the graph can address a group. A group's key needs its
members' side, which only the document can resolve:

```python
    def node_ids(self) -> dict:
        ids = {entry.key: entry.instance_id for entry in self.modules}
        ids.update({group.name: group.group_id for group in self.scene_groups})
        sides = {entry.instance_id: entry.side for entry in self.modules}
        for group in self.module_groups:
            side = next(
                (sides[member] for member in group.members if member in sides), "C"
            )
            ids[group.key(side)] = group.group_id
        return ids
```

Add to `to_dict()` after `scene_groups`:

```python
            "module_groups": [entry.to_dict() for entry in self.module_groups],
```

And to `from_dict()`:

```python
            module_groups=[
                ModuleGroup.from_dict(item)
                for item in (data.get("module_groups") or [])
            ],
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mayapy -m pytest tests/unit/test_guide_document_trigger.py tests/unit/test_module_group_trigger.py -v`
Expected: all passed

- [ ] **Step 5: Run the wider document suite for regressions**

Run: `mayapy -m pytest tests/unit/test_document_trigger.py tests/unit/test_session_trigger.py tests/unit/test_reconcile_trigger.py -q`
Expected: all passed — the schema bump must not disturb them.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/core/guide_document.py tests/unit/test_guide_document_trigger.py
git commit -m "Module groups: the document holds them (guide schema 3)"
```

---

### Task 3: The pure group operations

**Files:**
- Modify: `src/python/tik/trigger/core/module_group.py`
- Test: `tests/unit/test_module_group_trigger.py`

**Interfaces:**
- Consumes: `ModuleGroup`, `GuideDocument.module_groups`, `GuideDocument.group_of`, `GuideDocument.module`.
- Produces, all taking the document first and mutating it in place:
  - `make_group(document, label: str, member_ids: list) -> ModuleGroup`
  - `join_group(document, group_id: str, instance_id: str) -> None`
  - `leave_group(document, instance_id: str) -> Optional[str]` — returns the `group_id` it left, and dissolves a group that drops to one member
  - `dissolve_group(document, group_id: str) -> None`
  - `GroupError(TriggerError)`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_module_group_trigger.py`:

```python
import pytest

from tik.trigger.core.guide_document import GuideDocument, ModuleEntry
from tik.trigger.core.module_group import (
    GroupError,
    dissolve_group,
    join_group,
    leave_group,
    make_group,
)


def _document():
    document = GuideDocument()
    document.modules = [
        ModuleEntry("a", "fkchain", "index", "L"),
        ModuleEntry("b", "fkchain", "middle", "L"),
        ModuleEntry("c", "fkchain", "ring", "L"),
    ]
    return document


def test_make_group_registers_the_members_in_order():
    document = _document()
    group = make_group(document, "fingers", ["a", "b"])
    assert document.module_groups == [group]
    assert group.members == ["a", "b"]
    assert group.label == "fingers"
    assert group.group_id


def test_make_group_refuses_mixed_types():
    document = _document()
    document.modules.append(ModuleEntry("d", "arm", "arm", "L"))
    with pytest.raises(GroupError, match="same type"):
        make_group(document, "mixed", ["a", "d"])


def test_make_group_refuses_mixed_sides():
    """A shared value stops being shared the moment the sides differ."""
    document = _document()
    document.modules.append(ModuleEntry("d", "fkchain", "index", "R"))
    with pytest.raises(GroupError, match="same side"):
        make_group(document, "mixed", ["a", "d"])


def test_make_group_refuses_fewer_than_two_members():
    document = _document()
    with pytest.raises(GroupError, match="two"):
        make_group(document, "lonely", ["a"])


def test_make_group_refuses_a_module_already_in_a_group():
    document = _document()
    make_group(document, "fingers", ["a", "b"])
    with pytest.raises(GroupError, match="already"):
        make_group(document, "other", ["b", "c"])


def test_make_group_refuses_mixing_local_and_borrowed_modules():
    """A half-borrowed group has a membership list that is partly this file's
    word and partly upstream's, with no answer when upstream drops a member."""
    document = _document()
    document.module("b").origin = "ref1"
    with pytest.raises(GroupError, match="referenced"):
        make_group(document, "fingers", ["a", "b"])


def test_join_appends_to_the_group():
    document = _document()
    group = make_group(document, "fingers", ["a", "b"])
    join_group(document, group.group_id, "c")
    assert group.members == ["a", "b", "c"]


def test_join_refuses_a_different_type():
    document = _document()
    document.modules.append(ModuleEntry("d", "arm", "arm", "L"))
    group = make_group(document, "fingers", ["a", "b"])
    with pytest.raises(GroupError, match="same type"):
        join_group(document, group.group_id, "d")


def test_leave_returns_the_group_it_left():
    document = _document()
    group = make_group(document, "fingers", ["a", "b", "c"])
    assert leave_group(document, "c") == group.group_id
    assert group.members == ["a", "b"]


def test_leave_dissolves_a_group_that_drops_to_one_member():
    """A group of one is a module."""
    document = _document()
    group = make_group(document, "fingers", ["a", "b"])
    leave_group(document, "b")
    assert document.module_group(group.group_id) is None
    assert document.module_groups == []


def test_leave_is_silent_for_a_module_in_no_group():
    document = _document()
    assert leave_group(document, "a") is None


def test_dissolve_removes_the_group_and_leaves_the_modules():
    document = _document()
    group = make_group(document, "fingers", ["a", "b"])
    dissolve_group(document, group.group_id)
    assert document.module_groups == []
    assert [entry.instance_id for entry in document.modules] == ["a", "b", "c"]


def test_dissolve_drops_the_groups_frame():
    document = _document()
    group = make_group(document, "fingers", ["a", "b"])
    document.frames[group.group_id] = {"position": [10.0, 20.0], "collapsed": True}
    dissolve_group(document, group.group_id)
    assert group.group_id not in document.frames
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `mayapy -m pytest tests/unit/test_module_group_trigger.py -v`
Expected: FAIL — `ImportError: cannot import name 'GroupError'`

- [ ] **Step 3: Write the minimal implementation**

Add to `src/python/tik/trigger/core/module_group.py`:

```python
import uuid
from typing import Optional

from .exceptions import TriggerError


class GroupError(TriggerError):
    """A group operation the document refuses."""


def _entries(document, member_ids):
    """The entries for ``member_ids``, refusing any id the document lacks."""
    found = []
    for instance_id in member_ids:
        entry = document.module(instance_id)
        if entry is None:
            raise GroupError(f"No module '{instance_id}' to group.")
        found.append(entry)
    return found


def _check_homogeneous(entries) -> None:
    """Same type, same side, wholly local or wholly borrowed."""
    types = {entry.module_type for entry in entries}
    if len(types) > 1:
        raise GroupError(
            f"A group holds modules of the same type; got {sorted(types)}."
        )
    sides = {entry.side for entry in entries}
    if len(sides) > 1:
        raise GroupError(
            f"A group holds modules of the same side; got {sorted(sides)}. "
            "Mirror the group instead."
        )
    origins = {entry.origin for entry in entries}
    if len(origins) > 1:
        raise GroupError(
            "A group is wholly local or wholly referenced. Mixing them would "
            "leave a membership list that is partly this file's word and "
            "partly upstream's."
        )


def _check_free(document, member_ids) -> None:
    for instance_id in member_ids:
        existing = document.group_of(instance_id)
        if existing is not None:
            raise GroupError(
                f"'{instance_id}' is already in group '{existing.label}'."
            )


def make_group(document, label: str, member_ids: list) -> ModuleGroup:
    """Group ``member_ids`` under ``label``. Mutates ``document`` in place.

    Two members is the minimum, because a group of one is a module -- the same
    rule that makes ``leave_group`` dissolve on the way down.
    """
    member_ids = list(member_ids)
    if len(member_ids) < 2:
        raise GroupError("A group needs at least two modules.")
    _check_free(document, member_ids)
    _check_homogeneous(_entries(document, member_ids))
    group = ModuleGroup(
        group_id=uuid.uuid4().hex, label=label, members=member_ids
    )
    document.module_groups.append(group)
    return group


def join_group(document, group_id: str, instance_id: str) -> None:
    """Append ``instance_id`` to the group, at the end of the tab order."""
    group = document.module_group(group_id)
    if group is None:
        raise GroupError(f"No group '{group_id}'.")
    _check_free(document, [instance_id])
    _check_homogeneous(_entries(document, group.members + [instance_id]))
    group.members.append(instance_id)


def leave_group(document, instance_id: str) -> Optional[str]:
    """Remove ``instance_id`` from whatever group holds it.

    Returns the group id it left, or None when it was in none. A group that
    drops to one member dissolves: a group of one is a module.
    """
    group = document.group_of(instance_id)
    if group is None:
        return None
    group.members = [member for member in group.members if member != instance_id]
    if len(group.members) < 2:
        dissolve_group(document, group.group_id)
    return group.group_id


def dissolve_group(document, group_id: str) -> None:
    """Drop the group and its frame. The modules themselves are untouched."""
    document.module_groups = [
        group for group in document.module_groups if group.group_id != group_id
    ]
    document.frames.pop(group_id, None)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mayapy -m pytest tests/unit/test_module_group_trigger.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/core/module_group.py tests/unit/test_module_group_trigger.py
git commit -m "Module groups: make, join, leave, dissolve"
```

---

### Task 4: Shared-value derivation

**Files:**
- Modify: `src/python/tik/trigger/core/module_group.py`
- Test: `tests/unit/test_module_group_trigger.py`

**Interfaces:**
- Consumes: `GuideDocument`, `ModuleGroup`.
- Produces: `shared_values(entries: list) -> dict` and `varying_names(entries: list) -> set`. `entries` is a list of `ModuleEntry`. A settings key present in every entry with an equal value is shared; anything else varies. Input names are folded in under the key `"@input:<name>"` so one function answers for both settings and connections.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_module_group_trigger.py`:

```python
from tik.trigger.core.module_group import shared_values, varying_names


def _members(*settings_and_inputs):
    found = []
    for index, (settings, inputs) in enumerate(settings_and_inputs):
        entry = ModuleEntry(f"m{index}", "fkchain", f"f{index}", "L")
        entry.settings = dict(settings)
        entry.inputs = dict(inputs)
        found.append(entry)
    return found


def test_a_setting_every_member_agrees_on_is_shared():
    members = _members(
        ({"segments": 3, "stretch": True}, {}),
        ({"segments": 3, "stretch": True}, {}),
    )
    assert shared_values(members) == {"segments": 3, "stretch": True}
    assert varying_names(members) == set()


def test_a_setting_one_member_differs_on_is_not_shared():
    members = _members(
        ({"segments": 3, "stretch": True}, {}),
        ({"segments": 5, "stretch": True}, {}),
    )
    assert shared_values(members) == {"stretch": True}
    assert varying_names(members) == {"segments"}


def test_a_setting_missing_from_one_member_is_not_shared():
    members = _members(({"segments": 3}, {}), ({}, {}))
    assert shared_values(members) == {}
    assert varying_names(members) == {"segments"}


def test_inputs_share_under_an_at_input_key():
    members = _members(
        ({}, {"root": "hand.hand"}),
        ({}, {"root": "hand.hand"}),
    )
    assert shared_values(members) == {"@input:root": "hand.hand"}


def test_a_differing_input_is_not_shared():
    members = _members(
        ({}, {"root": "hand.hand"}),
        ({}, {"root": "other.out"}),
    )
    assert shared_values(members) == {}
    assert varying_names(members) == {"@input:root"}


def test_an_unwired_input_still_counts_as_a_value():
    """Leaving an input unwired is an ordinary state, not an absence."""
    members = _members(({}, {"root": ""}), ({}, {"root": ""}))
    assert shared_values(members) == {"@input:root": ""}


def test_a_table_setting_compares_by_value_not_identity():
    rows = [{"control": "fk", "mode": "parent", "label": "world"}]
    members = _members(
        ({"anim_spaces": [dict(row) for row in rows]}, {}),
        ({"anim_spaces": [dict(row) for row in rows]}, {}),
    )
    assert shared_values(members) == {"anim_spaces": rows}


def test_one_member_shares_everything_it_has():
    members = _members(({"segments": 3}, {"root": "a.b"}))
    assert shared_values(members) == {"segments": 3, "@input:root": "a.b"}


def test_no_members_share_nothing():
    assert shared_values([]) == {}
    assert varying_names([]) == set()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `mayapy -m pytest tests/unit/test_module_group_trigger.py -k shared -v`
Expected: FAIL — `ImportError: cannot import name 'shared_values'`

- [ ] **Step 3: Write the minimal implementation**

Add to `src/python/tik/trigger/core/module_group.py`:

```python
#: Prefix that folds an input's source into the same table as the settings, so
#: one function answers "is this shared?" for both. A settings key can never
#: collide with it: ``@`` is not a legal Python identifier character, and
#: settings keys are field names.
INPUT_PREFIX = "@input:"


def _value_table(entry) -> dict:
    """One entry's settings and inputs, in a single flat mapping."""
    table = dict(entry.settings)
    table.update(
        {f"{INPUT_PREFIX}{name}": source for name, source in entry.inputs.items()}
    )
    return table


def shared_values(entries: list) -> dict:
    """Values every entry carries and agrees on.

    Sharing is *derived*, never declared. Nothing in a module class, a manifest
    or the group record says which settings are common -- which is what makes
    the feature land on every module, the ones that ship and the ones written
    afterwards, with no module author doing anything.

    A key missing from any entry is not shared: the members do not agree about
    it, they do not even agree that it exists.
    """
    tables = [_value_table(entry) for entry in entries]
    if not tables:
        return {}
    common = set(tables[0])
    for table in tables[1:]:
        common &= set(table)
    first = tables[0]
    return {
        name: first[name]
        for name in common
        if all(table[name] == first[name] for table in tables)
    }


def varying_names(entries: list) -> set:
    """Keys some entry has that are not shared -- the fields the tabs own."""
    tables = [_value_table(entry) for entry in entries]
    every = set().union(*tables) if tables else set()
    return every - set(shared_values(entries))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mayapy -m pytest tests/unit/test_module_group_trigger.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/core/module_group.py tests/unit/test_module_group_trigger.py
git commit -m "Module groups: derive shared values from the members"
```

---

### Task 5: The invariant guard

Do this **before** any code that could violate it, so every later task is checked as it lands.

**Files:**
- Modify: `tests/unit/test_import_boundaries.py`

**Interfaces:**
- Consumes: the existing `SRC` path and `_imports` helper in that file.
- Produces: `test_the_build_path_cannot_see_module_groups`, parametrized over `trigger/maya`, `trigger/modules`, `trigger/systems`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_import_boundaries.py`:

```python
#: Grouping never changes the rig. The build path is therefore forbidden from
#: naming the group object or touching the document's group list at all --
#: a stronger and cheaper guarantee than reviewing every read site, and the
#: same trick the preferences rule above uses.
#:
#: ``trigger/guides`` is deliberately absent: the guide layer is not the build
#: path. It owns the document's rendering and the ``.trg``, which is exactly
#: where the group operations and the ``.trg`` section have to live. What must
#: stay blind is the code that turns guides into a rig.
GROUP_BLIND = ("trigger/maya", "trigger/modules", "trigger/systems")


def _group_reads(py_file: Path):
    """Names and attributes that would let this file see a module group.

    ``.module_groups`` rather than ``.groups`` on purpose: ``rig.groups`` is
    the four per-module rig groups and is all over the build path, so a bare
    ``groups`` could not be told apart from it. The distinct name is what
    makes this check possible.
    """
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "module_groups":
            yield f"line {node.lineno}: reads .module_groups"
        elif isinstance(node, ast.Name) and node.id == "ModuleGroup":
            yield f"line {node.lineno}: names ModuleGroup"
        elif isinstance(node, ast.Attribute) and node.attr in (
            "module_group",
            "group_of",
        ):
            yield f"line {node.lineno}: calls .{node.attr}()"


@pytest.mark.parametrize("package", GROUP_BLIND)
def test_the_build_path_cannot_see_module_groups(package):
    found = [
        f"{py_file.relative_to(SRC)} {problem}"
        for py_file in (SRC / package).rglob("*.py")
        for problem in _group_reads(py_file)
    ]
    assert found == []


def test_the_group_guard_would_catch_a_violation(tmp_path):
    """The guard is only worth having if it fails on the thing it forbids."""
    offender = tmp_path / "offender.py"
    offender.write_text("def build(doc):\n    return doc.module_groups\n")
    assert list(_group_reads(offender)) == ["line 2: reads .module_groups"]
```

- [ ] **Step 2: Run the test to verify it passes for the right reason**

Run: `mayapy -m pytest tests/unit/test_import_boundaries.py -v`
Expected: all passed. The three parametrized cases pass because nothing on the
build path touches groups yet; `test_the_group_guard_would_catch_a_violation`
is what proves the check is not vacuous.

- [ ] **Step 3: Verify `tik/trigger/core` stays pure**

Run: `mayapy -m pytest tests/unit/test_import_boundaries.py -k "forbidden and core" -v`
Expected: PASS — `core/module_group.py` imports only `dataclasses`, `typing`, `uuid`, `.manifest` and `.exceptions`.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_import_boundaries.py
git commit -m "Module groups: guard that the build path can never see them"
```

---

### Task 6: `GuideScene` group operations

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py` (add after `duplicate`, around line 839)
- Test: `tests/integration/trigger/test_module_groups_trigger.py` (create)

**Interfaces:**
- Consumes: `make_group`, `join_group`, `leave_group`, `dissolve_group`, `GroupError`, `shared_values` from Tasks 3-4; the existing `GuideScene.duplicate`, `GuideScene.mirror`, `GuideScene.remove`, `GuideScene._touch`, `nodes.undo_chunk`.
- Produces on `GuideScene`:
  - `groups() -> list[ModuleGroup]`
  - `group_of(instance_id: str) -> Optional[ModuleGroup]`
  - `group(handles: list[GuideHandle], label: str = "") -> ModuleGroup`
  - `ungroup(group_id: str) -> None`
  - `add_copy(handle: GuideHandle) -> GuideHandle` — the `[+]` verb
  - `remove_from_group(handle: GuideHandle) -> None`
  - `mirror_group(group_id: str) -> ModuleGroup`
  - `group_members(group_id) -> list[GuideHandle]`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/trigger/test_module_groups_trigger.py`:

The `scene` fixture already exists in `tests/integration/trigger/conftest.py`:
it does `cmds.file(new=True, force=True)`, loads the plug-ins and hands back a
`GuideScene`. Do not write a new one.

```python
"""Module groups against a real scene: the [+] verb, mirroring, teardown."""

import pytest

from tik.trigger.core.module_group import GroupError


def _three_chains(scene):
    return [scene.add("fkchain", name=name, side="L") for name in ("a", "b", "c")]


def test_group_makes_one_group_of_the_handles(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    assert [h.instance_id for h in scene.group_members(group.group_id)] == [
        handles[0].instance_id,
        handles[1].instance_id,
    ]
    assert scene.group_of(handles[0].instance_id).group_id == group.group_id


def test_group_defaults_its_label_to_the_first_members_name(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2])
    assert group.label == "a"


def test_add_copy_duplicates_the_member_and_joins_it(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    copy = scene.add_copy(handles[0])
    assert copy.instance_id in group.members
    assert group.members[-1] == copy.instance_id


def test_add_copy_on_a_lone_module_creates_the_group(scene):
    """A group springs into existence around the pair; nothing to learn."""
    handle = scene.add("fkchain", name="index", side="L")
    assert scene.group_of(handle.instance_id) is None
    copy = scene.add_copy(handle)
    group = scene.group_of(handle.instance_id)
    assert group is not None
    assert group.members == [handle.instance_id, copy.instance_id]
    assert group.label == "index"


def test_add_copy_carries_settings_and_poses(scene):
    handle = scene.add("fkchain", name="index", side="L")
    handle.segments = 5
    copy = scene.add_copy(handle)
    assert copy.settings["segments"] == 5
    assert [record.pair for record in copy.entry.guides] == [
        record.pair for record in handle.entry.guides
    ]


def test_removing_a_member_down_to_one_dissolves_the_group(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    scene.remove(handles[1])
    assert scene.document.module_group(group.group_id) is None


def test_deleting_a_member_of_three_leaves_the_group_standing(scene):
    handles = _three_chains(scene)
    group = scene.group(handles, label="fingers")
    scene.remove(handles[2])
    assert scene.document.module_group(group.group_id).members == [
        handles[0].instance_id,
        handles[1].instance_id,
    ]


def test_ungroup_keeps_every_module(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    scene.ungroup(group.group_id)
    assert scene.document.module_groups == []
    assert len(scene.instances()) == 3


def test_group_refuses_mixed_types(scene):
    chain = scene.add("fkchain", name="index", side="L")
    arm = scene.add("arm", name="arm", side="L")
    with pytest.raises(GroupError, match="same type"):
        scene.group([chain, arm])


def test_mirror_group_builds_the_opposite_group_whole(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    mirrored = scene.mirror_group(group.group_id)
    assert mirrored.group_id != group.group_id
    assert len(mirrored.members) == 2
    sides = {scene.document.module(m).side for m in mirrored.members}
    assert sides == {"R"}
    assert mirrored.label == "fingers"


def test_mirror_group_twice_updates_rather_than_duplicates(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    first = scene.mirror_group(group.group_id)
    second = scene.mirror_group(group.group_id)
    assert first.group_id == second.group_id
    assert len(scene.document.module_groups) == 2
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `mayapy -m pytest tests/integration/trigger/test_module_groups_trigger.py -v`
Expected: FAIL — `AttributeError: 'GuideScene' object has no attribute 'group'`

- [ ] **Step 3: Write the minimal implementation**

Add to `src/python/tik/trigger/guides/scene.py`, after `duplicate` and before the
`# --- build` divider. Import the operations at the top of the file:

```python
from tik.trigger.core.module_group import (
    ModuleGroup,
    dissolve_group,
    join_group,
    leave_group,
    make_group,
)
```

```python
    # ------------------------------------------------------------ groups
    def groups(self) -> list:
        """Every module group in the document."""
        return list(self.document.module_groups)

    def group_of(self, instance_id: str) -> Optional[ModuleGroup]:
        """The group holding ``instance_id``, or None."""
        return self.document.group_of(instance_id)

    def group_members(self, group_id: str) -> list[GuideHandle]:
        """Handles for a group's members, in tab order."""
        group = self.document.module_group(group_id)
        if group is None:
            return []
        return [GuideHandle(self, member) for member in group.members]

    def group(self, handles, label: str = "") -> ModuleGroup:
        """Group ``handles`` under ``label``.

        The label defaults to the first member's name, which is the useful
        answer for the ``[+]`` path -- pressing it on ``index`` gives a group
        called ``index``, which the rigger renames to ``fingers`` if they care.
        """
        handles = list(handles)
        ids = [handle.instance_id for handle in handles]
        if not label and handles:
            label = handles[0].instance.name
        with nodes.undo_chunk("Trigger group modules"):
            group = make_group(self.document, label, ids)
            self._touch()
        return group

    def ungroup(self, group_id: str) -> None:
        """Drop the group. Its modules and their guides are untouched."""
        with nodes.undo_chunk("Trigger ungroup modules"):
            dissolve_group(self.document, group_id)
            self._touch()

    def add_copy(self, handle: GuideHandle) -> GuideHandle:
        """The ``[+]`` verb: duplicate ``handle`` and put the copy beside it.

        An exact duplicate -- settings, inputs and guide poses -- so the copy's
        joints sit precisely on the original's and the rigger drags them into
        place. That matches ``duplicate`` and it matches the pivot-preset rule:
        an unplaced thing should look unplaced.

        If ``handle`` is alone, the group springs into existence around the
        pair. There is no "create a group" concept to learn: a group is simply
        a module with more than one copy.
        """
        with nodes.undo_chunk("Trigger add module copy"):
            copy = self.duplicate(handle)
            group = self.document.group_of(handle.instance_id)
            if group is None:
                group = make_group(
                    self.document,
                    handle.instance.name,
                    [handle.instance_id, copy.instance_id],
                )
            else:
                join_group(self.document, group.group_id, copy.instance_id)
            self._touch()
        return copy

    def remove_from_group(self, handle: GuideHandle) -> None:
        """Take a module out of its group, leaving the module in the rig."""
        with nodes.undo_chunk("Trigger remove from group"):
            leave_group(self.document, handle.instance_id)
            self._touch()

    def mirror_group(self, group_id: str) -> ModuleGroup:
        """Create (or update) the opposite-side copy of a whole group.

        Mirrors every member through :meth:`mirror`, which already handles the
        update case, the connection remapping and drawing both halves. The
        group on the far side is found by its members rather than by name: a
        second mirror must update the group it made the first time, not add a
        second one beside it.
        """
        group = self.document.module_group(group_id)
        if group is None:
            raise GuideError(f"No module group '{group_id}'.")
        with nodes.undo_chunk("Trigger mirror group"):
            mirrored = [
                self.mirror(GuideHandle(self, member)) for member in group.members
            ]
            existing = next(
                (
                    self.document.group_of(handle.instance_id)
                    for handle in mirrored
                    if self.document.group_of(handle.instance_id) is not None
                ),
                None,
            )
            if existing is None:
                existing = make_group(
                    self.document,
                    group.label,
                    [handle.instance_id for handle in mirrored],
                )
            else:
                for handle in mirrored:
                    if handle.instance_id not in existing.members:
                        join_group(self.document, existing.group_id, handle.instance_id)
            self._touch()
        return existing
```

- [ ] **Step 4: Make `remove` drop the module from its group**

In `GuideScene.remove`, inside the `undo_chunk`, before `self.delete_guides(instance_id)`:

```python
            leave_group(self.document, instance_id)
```

This is what makes `test_removing_a_member_down_to_one_dissolves_the_group`
pass: `leave_group` already dissolves on the way down.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `mayapy -m pytest tests/integration/trigger/test_module_groups_trigger.py -v`
Expected: all passed

- [ ] **Step 6: Run the guide suite for regressions**

Run: `mayapy -m pytest tests/unit/test_guides_trigger.py tests/integration/trigger/test_draw_sync_trigger.py -q`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/guides/scene.py tests/integration/trigger/test_module_groups_trigger.py
git commit -m "Module groups: the GuideScene verbs, including [+] and mirror"
```

---

### Task 7: Mirror the group surface onto `StubScene`

The Qt tests cannot import Maya, so every `GuideScene` method the Designer
touches has a stand-in. Without this, Tasks 9-12 have nothing to test against.

**Files:**
- Modify: `tests/ui/stub.py`
- Test: `tests/ui/test_stub_groups.py` (create)

**Interfaces:**
- Consumes: the Task 6 signatures, exactly.
- Produces: the same eight methods on `StubScene`, backed by a real
  `GuideDocument` so the pure operations are the ones actually running.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_stub_groups.py`:

```python
"""The stub's group surface matches GuideScene's, so the designer tests mean something."""

import inspect

from tests.ui.stub import StubScene
from tik.trigger.guides.scene import GuideScene

GROUP_API = (
    "groups",
    "group_of",
    "group_members",
    "group",
    "ungroup",
    "add_copy",
    "remove_from_group",
    "mirror_group",
)


def test_the_stub_offers_every_group_method_the_scene_does():
    missing = [name for name in GROUP_API if not hasattr(StubScene, name)]
    assert missing == []


def test_the_signatures_match():
    """A stub that drifts from the real surface tests nothing."""
    for name in GROUP_API:
        real = inspect.signature(getattr(GuideScene, name))
        stub = inspect.signature(getattr(StubScene, name))
        assert list(real.parameters) == list(stub.parameters), name


def test_add_copy_groups_a_lone_module():
    scene = StubScene()
    handle = scene.add("fkchain", name="index", side="L")
    copy = scene.add_copy(handle)
    group = scene.group_of(handle.instance_id)
    assert group.members == [handle.instance_id, copy.instance_id]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_stub_groups.py -v`
Expected: FAIL — `assert ['groups', 'group_of', ...] == []`

- [ ] **Step 3: Write the minimal implementation**

Add to `tests/ui/stub.py`. The stub already builds a `GuideDocument` in
`_document_cache`; the group methods run the **real** pure operations over the
stub's document so the logic under test is the shipping logic:

```python
    # ------------------------------------------------------------ groups
    def groups(self) -> list:
        return list(self._module_groups)

    def group_of(self, instance_id):
        from tik.trigger.core.module_group import ModuleGroup  # noqa: F401

        for group in self._module_groups:
            if instance_id in group.members:
                return group
        return None

    def group_members(self, group_id) -> list:
        group = self._group(group_id)
        return [GuideHandle(self, member) for member in group.members] if group else []

    def group(self, handles, label: str = ""):
        from tik.trigger.core.module_group import make_group

        handles = list(handles)
        if not label and handles:
            label = handles[0].instance.name
        group = make_group(
            self.document, label, [h.instance_id for h in handles]
        )
        self.calls.append(("group", group.group_id, label))
        return group

    def ungroup(self, group_id) -> None:
        from tik.trigger.core.module_group import dissolve_group

        dissolve_group(self.document, group_id)
        self.calls.append(("ungroup", group_id))

    def add_copy(self, handle):
        from tik.trigger.core.module_group import join_group, make_group

        copy = self.duplicate(handle)
        document = self.document
        group = self.group_of(handle.instance_id)
        if group is None:
            make_group(
                document, handle.instance.name, [handle.instance_id, copy.instance_id]
            )
        else:
            join_group(document, group.group_id, copy.instance_id)
        self.calls.append(("add_copy", handle.instance_id, copy.instance_id))
        return copy

    def remove_from_group(self, handle) -> None:
        from tik.trigger.core.module_group import leave_group

        leave_group(self.document, handle.instance_id)
        self.calls.append(("remove_from_group", handle.instance_id))

    def mirror_group(self, group_id):
        from tik.trigger.core.module_group import join_group, make_group

        group = self._group(group_id)
        mirrored = [self.mirror(GuideHandle(self, m)) for m in group.members]
        document = self.document
        existing = self.group_of(mirrored[0].instance_id)
        if existing is None:
            existing = make_group(
                document, group.label, [h.instance_id for h in mirrored]
            )
        else:
            for handle in mirrored:
                if handle.instance_id not in existing.members:
                    join_group(document, existing.group_id, handle.instance_id)
        self.calls.append(("mirror_group", group_id))
        return existing

    def _group(self, group_id):
        return next(
            (g for g in self._module_groups if g.group_id == group_id), None
        )
```

**Do not write a `_group_document` helper.** `StubScene` already has a
`document` property (line 118) that builds a real `GuideDocument` from
`_instances`, complete with `origin` on borrowed entries. Extend *that* so the
pure operations run against it — and attach the stub's own lists **by
reference**, not by copy, so a mutation inside `make_group` actually sticks:

```python
        document.positions = dict(self._positions)
        document.collapse = dict(self._collapse)
        # by reference: the pure operations mutate these in place, and the
        # cache below would otherwise hand back a document whose edits are
        # thrown away on the next invalidation
        document.module_groups = self._module_groups
        document.frames = self._frames
```

Everywhere the group methods above say `self.document`, say
`self.document`. Then in `StubScene.__init__`, beside `self._frames`:

```python
        # module groups, stored the way the real document stores them
        self._module_groups: list = []
```

Also add group teardown to the stub's `remove`, matching Task 6 step 4:

```python
        from tik.trigger.core.module_group import leave_group

        leave_group(self.document, handle.instance_id)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_stub_groups.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the whole UI suite for regressions**

Run: `make tests-ui`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add tests/ui/stub.py tests/ui/test_stub_groups.py
git commit -m "Module groups: mirror the group surface onto the Qt stub"
```

---

### Task 8: Rename `FrameSpec.ref_id` to `frame_id`

A pure rename, on its own commit, so the behaviour change in Task 9 reviews clean.

**Files:**
- Modify: `src/python/tik/trigger/ui/graph/items.py:123-176` (`FrameSpec`, `FrameItem`)
- Modify: `src/python/tik/trigger/ui/graph/scene.py:24,25,68-74` (signals, `add_frame`)
- Modify: `src/python/tik/trigger/ui/graph/view.py` (every `ref_id` that is a *frame* id)
- Test: `tests/ui/` (existing graph tests must keep passing unchanged)

**Interfaces:**
- Consumes: nothing new.
- Produces: `FrameSpec(frame_id: str, title: str, collapsed: bool = False)`, `FrameItem.frame_id`, `GraphScene.frames: dict[str, FrameItem]` keyed by frame id.

- [ ] **Step 1: Establish the baseline**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui -q`
Expected: all passed. Record the count — it must not change.

- [ ] **Step 2: Rename in `items.py`**

```python
@dataclass
class FrameSpec:
    """Everything a frame is drawn from.

    A frame comes from a reference or from a module group; the item does not
    care which, so the id is a frame id rather than a reference id.
    """

    frame_id: str
    title: str
    collapsed: bool = False
```

In `FrameItem.__init__`: `self.frame_id = spec.frame_id`.
In `FrameItem.mousePressEvent`: `scene.frame_toggle_requested.emit(self.frame_id)`.

- [ ] **Step 3: Rename in `scene.py`**

```python
    frame_toggle_requested = QtCore.Signal(str)  # frame id
    frame_selected = QtCore.Signal(str)  # frame id
```

In `add_frame`: `self.frames[spec.frame_id] = frame`.

- [ ] **Step 4: Rename the frame-id locals in `view.py`**

Rename only the identifiers that hold a *frame* id — the ones read from
`self.guides.frames` at lines 180, 290 and 353 and built at 405. Leave every
`ref_id` that identifies a `ModuleReference` alone.

- [ ] **Step 5: Verify nothing else names the old attribute**

Run: `grep -rn "spec.ref_id\|FrameSpec(ref_id\|\.ref_id" src/python/tik/trigger/ui/graph/`
Expected: no hits on `FrameSpec`/`FrameItem`; remaining `ref_id` hits are `ModuleReference` ids.

- [ ] **Step 6: Run the UI suite to verify the rename is behaviour-neutral**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui -q`
Expected: the same count as Step 1, all passed.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/ui/graph/
git commit -m "Graph: a frame carries a frame id, not a reference id"
```

---

### Task 9: Groups draw as frames and collapsed nodes

**Files:**
- Modify: `src/python/tik/trigger/ui/graph/view.py` (`_add_frames` at 405, the frame reads at 180/290/353, the node build)
- Test: `tests/ui/test_graph_groups.py` (create)

**Interfaces:**
- Consumes: `StubScene.groups()`, `StubScene.group_members()`, `StubScene.frames`, `StubScene.set_frame`; `FrameSpec(frame_id=...)` from Task 8.
- Produces: in the graph view, `_group_frames() -> list[FrameSpec]` and `_collapsed_group_node(group) -> NodeSpec`. A collapsed group contributes one node keyed `"@<group_id>"`; its members contribute none.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_graph_groups.py`:

```python
"""A module group in the graph: the frame, the collapsed node, its ports."""

import pytest

from tests.ui.stub import StubScene


@pytest.fixture
def scene_with_group(qtbot):
    scene = StubScene()
    handles = [scene.add("fkchain", name=n, side="L") for n in ("a", "b")]
    group = scene.group(handles, label="fingers")
    return scene, group, handles


def _view(qtbot, scene):
    from tik.trigger.ui.graph.view import GraphView

    view = GraphView(guides=scene)
    qtbot.addWidget(view)
    view.rebuild()
    return view


def test_an_expanded_group_draws_a_frame_around_its_members(qtbot, scene_with_group):
    scene, group, handles = scene_with_group
    scene.set_frame(group.group_id, collapsed=False)
    view = _view(qtbot, scene)
    assert group.group_id in view.scene().frames
    keys = set(view.scene().nodes)
    assert {"L_a", "L_b"} <= keys


def test_a_collapsed_group_draws_one_node_and_hides_its_members(
    qtbot, scene_with_group
):
    scene, group, handles = scene_with_group
    scene.set_frame(group.group_id, collapsed=True)
    view = _view(qtbot, scene)
    keys = set(view.scene().nodes)
    assert f"@{group.group_id}" in keys
    assert "L_a" not in keys
    assert "L_b" not in keys


def test_a_collapsed_group_node_is_titled_by_its_key(qtbot, scene_with_group):
    scene, group, handles = scene_with_group
    scene.set_frame(group.group_id, collapsed=True)
    view = _view(qtbot, scene)
    node = view.scene().nodes[f"@{group.group_id}"]
    assert node.spec.title == "L_fingers"
    assert "2" in node.spec.subtitle


def test_the_collapsed_node_carries_the_union_of_member_ports(
    qtbot, scene_with_group
):
    scene, group, handles = scene_with_group
    scene.set_frame(group.group_id, collapsed=True)
    view = _view(qtbot, scene)
    node = view.scene().nodes[f"@{group.group_id}"]
    member_inputs = set()
    for handle in handles:
        member_inputs |= set(handle.module_class.input_names(handle.settings))
    assert set(node.spec.inputs) == member_inputs


def test_a_group_defaults_to_collapsed(qtbot, scene_with_group):
    """The whole point is fewer nodes; a group that opened expanded would
    make the rigger collapse it every time."""
    scene, group, handles = scene_with_group
    view = _view(qtbot, scene)
    assert f"@{group.group_id}" in view.scene().nodes


def test_toggling_the_frame_expands_the_group(qtbot, scene_with_group):
    scene, group, handles = scene_with_group
    view = _view(qtbot, scene)
    view.scene().frame_toggle_requested.emit(group.group_id)
    assert scene.frames[group.group_id]["collapsed"] is False
    assert "L_a" in view.scene().nodes
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_graph_groups.py -v`
Expected: FAIL — the group's frame is not in `view.scene().frames`.

- [ ] **Step 3: Write the minimal implementation**

In `src/python/tik/trigger/ui/graph/view.py`:

Add a helper that reads groups the same way `_add_frames` reads references,
and treat a group with no stored frame as collapsed:

```python
    def _group_frames(self) -> dict:
        """``{group_id: (group, collapsed)}`` for every module group.

        A group with no stored frame reads as collapsed. The point of the
        feature is fewer nodes, so a group that opened expanded would make the
        rigger collapse it every time they redrew the graph.
        """
        stored = getattr(self.guides, "frames", {}) or {}
        found = {}
        for group in getattr(self.guides, "groups", lambda: [])():
            frame = stored.get(group.group_id, {})
            found[group.group_id] = (group, bool(frame.get("collapsed", True)))
        return found
```

When building nodes, skip members of a collapsed group and add one node for
the group. The node's key is `"@<group_id>"`, matching the collapsed-reference
convention the scene already strips with `key.lstrip("@")`:

```python
    def _collapsed_group_spec(self, group) -> NodeSpec:
        """One node standing for a whole group: the union of its ports."""
        members = self.guides.group_members(group.group_id)
        inputs, outputs = [], []
        for handle in members:
            for name in handle.module_class.input_names(handle.settings):
                if name not in inputs:
                    inputs.append(name)
            for name in handle.outputs:
                if name not in outputs:
                    outputs.append(name)
        side = members[0].instance.side if members else "C"
        module_cls = members[0].module_class if members else None
        return NodeSpec(
            title=group.key(side),
            subtitle=f"{len(members)} × {module_cls.display_label()}"
            if module_cls
            else f"{len(members)} modules",
            inputs=inputs,
            outputs=outputs,
            color=self._color_for(module_cls) if module_cls else "",
            reference=True,
            mode=MODE_FULL,
        )
```

Extend `_add_frames` so a group contributes a `FrameSpec` when expanded, using
the same geometry pass references already use.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_graph_groups.py -v`
Expected: all passed

- [ ] **Step 5: Run the UI suite for regressions**

Run: `make tests-ui`
Expected: all passed — reference frames must still draw exactly as before.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/ui/graph/view.py tests/ui/test_graph_groups.py
git commit -m "Graph: a module group draws as a frame and collapses to one node"
```

---

### Task 10: Input fan-in and the output member picker

**Files:**
- Modify: `src/python/tik/trigger/ui/graph/view.py` (the connect handler)
- (No change to `shared/ui/feedback.py`: `ask_choice` already covers the picker.)
- Test: `tests/ui/test_graph_groups.py`

**Interfaces:**
- Consumes: `StubScene.connect`, `StubScene.group_members`, `Feedback`.
- Produces: `GraphView._connect_to_group(group, input_name, source) -> None` (wires every member) and `GraphView._pick_group_output_member(group) -> Optional[str]` (returns an instance id or None).

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_graph_groups.py`:

```python
def test_wiring_a_collapsed_groups_input_wires_every_member(
    qtbot, scene_with_group
):
    """'All of these attach to the same place' is a meaningful thing to say."""
    scene, group, handles = scene_with_group
    other = scene.add("fkchain", name="hand", side="L")
    scene.set_frame(group.group_id, collapsed=True)
    view = _view(qtbot, scene)
    view._connect_to_group(group, "root", f"{other.key}.root")
    for handle in handles:
        assert handle.instance.inputs["root"] == f"{other.key}.root"


def test_wiring_a_group_input_skips_a_member_without_that_input(
    qtbot, scene_with_group
):
    scene, group, handles = scene_with_group
    other = scene.add("fkchain", name="hand", side="L")
    view = _view(qtbot, scene)
    view._connect_to_group(group, "not_an_input", f"{other.key}.root")
    for handle in handles:
        assert "not_an_input" not in handle.instance.inputs


def test_dragging_from_a_group_output_asks_which_member(
    qtbot, scene_with_group, monkeypatch
):
    """'Which one of these drives that' has no default answer, so fanning an
    output out would silently create wires the rigger did not intend."""
    scene, group, handles = scene_with_group
    view = _view(qtbot, scene)
    asked = {}

    def fake_pick(options, **kwargs):
        asked["options"] = list(options)
        return handles[1].instance_id

    monkeypatch.setattr(view, "_pick_member", fake_pick)
    picked = view._pick_group_output_member(group)
    assert picked == handles[1].instance_id
    assert len(asked["options"]) == 2


def test_cancelling_the_member_picker_makes_no_connection(
    qtbot, scene_with_group, monkeypatch
):
    scene, group, handles = scene_with_group
    view = _view(qtbot, scene)
    monkeypatch.setattr(view, "_pick_member", lambda options, **kw: None)
    assert view._pick_group_output_member(group) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_graph_groups.py -k "fan or member" -v`
Expected: FAIL — `AttributeError: 'GraphView' object has no attribute '_connect_to_group'`

- [ ] **Step 3: Write the minimal implementation**

In `src/python/tik/trigger/ui/graph/view.py`:

```python
    def _connect_to_group(self, group, input_name: str, source: str) -> None:
        """Give every member of ``group`` the same source on ``input_name``.

        Inputs fan in and outputs do not, and the asymmetry is the point: *all
        of these attach to the same place* is a meaningful thing to say, while
        *which one of these drives that* is a question with no default answer.
        A member that has no such input is skipped rather than refused -- the
        union of ports is what the collapsed node advertises, so a port that
        only some members carry is normal.
        """
        for handle in self.guides.group_members(group.group_id):
            if input_name not in handle.module_class.input_names(handle.settings):
                continue
            self.guides.connect(f"{handle.key}.{input_name}", source)

    def _pick_member(self, options, title: str = "Which module?"):
        """Ask which member; returns an instance id or None.

        ``options`` is ``[(instance_id, label)]``. Goes through ``Feedback``,
        which is the one dialog surface -- a raw ``QInputDialog`` here would
        fail ``tests/unit/test_dialog_boundaries.py``.
        """
        from tik.shared.ui.feedback import Feedback

        labels = [label for _id, label in options]
        picked = Feedback(parent=self).ask_choice(
            title=title, label="Module:", options=labels
        )
        if picked is None:
            return None
        return next(item_id for item_id, label in options if label == picked)

    def _pick_group_output_member(self, group):
        """Which member a wire dragged from a collapsed group comes from."""
        members = self.guides.group_members(group.group_id)
        options = [(handle.instance_id, handle.key) for handle in members]
        return self._pick_member(options, title=f"{group.label}: which module?")
```

`Feedback.ask_choice(title, label, options, current=0)` already exists
(`shared/ui/feedback.py:316`) and returns the picked **label** or `None`, which
is why `_pick_member` maps back to the id. Do not add a new `Feedback` method.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_graph_groups.py -v`
Expected: all passed

- [ ] **Step 5: Verify the dialog boundary still holds**

Run: `mayapy -m pytest tests/unit/test_dialog_boundaries.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/ui/graph/view.py tests/ui/test_graph_groups.py
git commit -m "Graph: group inputs fan in, group outputs ask which member"
```

---

### Task 11: The tab bar and the Common/per-tab split

The largest task. It is one task because the tab bar without the split shows
nothing useful, and the split without the tab bar has nowhere to live.

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/window.py` (the properties panel, around the `_multi` handling at 141, 529, 876-949)
- Modify: `src/python/tik/trigger/ui/designer/properties.py` (`_on_setting_changed`, `_on_input_changed`)
- Test: `tests/ui/test_group_tabs.py` (create)

**Interfaces:**
- Consumes: `shared_values`, `varying_names`, `INPUT_PREFIX` from Task 4; `StubScene.group_of`, `group_members`, `add_copy`, `remove_from_group`, `ungroup` from Task 7.
- Produces on the designer window:
  - `_group_members() -> list[GuideHandle]` — the current group's members, or `[self._current]`
  - `_is_common(name: str) -> bool` — whether a field renders in `Common`
  - `tab_bar` (a `QTabBar`) and `add_copy_button`
  - `_on_tab_changed(index: int)`, `_on_add_copy()`, `_on_tab_renamed(index, text)`, `_on_tabs_reordered()`

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_group_tabs.py`:

```python
"""The properties panel for a group: the tab bar, and what sits above it."""

import pytest

from tests.ui.stub import StubScene


@pytest.fixture
def designer(qtbot):
    from tik.trigger.ui.designer.window import GuideDesigner

    scene = StubScene()
    window = GuideDesigner(guides=scene)
    qtbot.addWidget(window)
    return window, scene


def _grouped(designer, count=3, **settings):
    window, scene = designer
    handles = [
        scene.add("fkchain", name=f"f{index}", side="L") for index in range(count)
    ]
    for handle in handles:
        for name, value in settings.items():
            setattr(handle, name, value)
    group = scene.group(handles, label="fingers")
    window.select(handles[0].instance_id)
    return window, scene, group, handles


def test_a_lone_module_still_shows_a_tab_bar_with_a_plus(designer):
    window, scene = designer
    handle = scene.add("fkchain", name="index", side="L")
    window.select(handle.instance_id)
    assert window.tab_bar.count() == 1
    assert window.tab_bar.tabText(0) == "index"
    assert window.add_copy_button.isEnabled()


def test_a_group_shows_one_tab_per_member_in_order(designer):
    window, scene, group, handles = _grouped(designer)
    assert window.tab_bar.count() == 3
    assert [window.tab_bar.tabText(i) for i in range(3)] == ["f0", "f1", "f2"]


def test_a_setting_every_member_agrees_on_is_common(designer):
    window, scene, group, handles = _grouped(designer, segments=3)
    assert window._is_common("segments") is True


def test_a_setting_one_member_differs_on_drops_into_the_tabs(designer):
    window, scene, group, handles = _grouped(designer, segments=3)
    handles[1].segments = 5
    window.refresh()
    assert window._is_common("segments") is False


def test_name_is_never_common(designer):
    """Member names must stay unique, so the field is fixed per-tab."""
    window, scene, group, handles = _grouped(designer)
    assert window._is_common("name") is False


def test_editing_a_common_setting_writes_to_every_member(designer):
    window, scene, group, handles = _grouped(designer, segments=3)
    window._module_obj.segments = 7
    window._on_setting_changed("segments", 7)
    assert [handle.settings["segments"] for handle in handles] == [7, 7, 7]


def test_editing_a_varying_setting_writes_to_the_current_tab_only(designer):
    window, scene, group, handles = _grouped(designer, segments=3)
    handles[1].segments = 5
    window.refresh()
    window._module_obj.segments = 9
    window._on_setting_changed("segments", 9)
    assert handles[0].settings["segments"] == 9
    assert handles[1].settings["segments"] == 5
    assert handles[2].settings["segments"] == 3


def test_a_common_input_wires_every_member(designer):
    window, scene, group, handles = _grouped(designer)
    other = scene.add("fkchain", name="hand", side="L")
    window._on_input_changed("root", f"{other.key}.root")
    assert [handle.instance.inputs.get("root") for handle in handles] == [
        f"{other.key}.root"
    ] * 3


def test_plus_adds_a_tab_and_selects_it(designer):
    window, scene, group, handles = _grouped(designer)
    window._on_add_copy()
    assert window.tab_bar.count() == 4
    assert window.tab_bar.currentIndex() == 3


def test_plus_on_a_lone_module_creates_the_group(designer):
    window, scene = designer
    handle = scene.add("fkchain", name="index", side="L")
    window.select(handle.instance_id)
    window._on_add_copy()
    assert window.tab_bar.count() == 2
    assert scene.group_of(handle.instance_id) is not None


def test_switching_tabs_changes_the_current_module(designer):
    window, scene, group, handles = _grouped(designer)
    window.tab_bar.setCurrentIndex(2)
    assert window._current.instance_id == handles[2].instance_id


def test_renaming_a_tab_renames_the_member(designer):
    window, scene, group, handles = _grouped(designer)
    window._on_tab_renamed(1, "middle")
    assert handles[1].instance.name == "middle"
    assert window.tab_bar.tabText(1) == "middle"


def test_removing_the_last_but_one_member_dissolves_the_group(designer):
    window, scene, group, handles = _grouped(designer, count=2)
    scene.remove_from_group(handles[1])
    window.refresh()
    assert scene.group_of(handles[0].instance_id) is None
    assert window.tab_bar.count() == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_group_tabs.py -v`
Expected: FAIL — `AttributeError: 'GuideDesigner' object has no attribute 'tab_bar'`

- [ ] **Step 3: Build the tab bar**

In `window.py`, where the properties panel is assembled, add above the form:

```python
        self.tab_bar = QtWidgets.QTabBar()
        self.tab_bar.setMovable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.tabMoved.connect(self._on_tabs_reordered)
        self.add_copy_button = QtWidgets.QToolButton()
        self.add_copy_button.setText("+")
        self.add_copy_button.setAutoRaise(True)
        self.add_copy_button.setToolTip("Add another copy of this module")
        self.add_copy_button.clicked.connect(self._on_add_copy)
```

- [ ] **Step 4: Add the membership and split helpers**

```python
    def _group_members(self) -> list:
        """The current module's group members in tab order, or just itself."""
        if self._current is None:
            return []
        group = self.guides.group_of(self._current.instance_id)
        if group is None:
            return [self._current]
        return self.guides.group_members(group.group_id)

    #: Fields that never derive. ``name`` must stay unique per member, and
    #: ``side`` is enforced homogeneous when a module joins a group.
    ALWAYS_PER_TAB = ("name",)

    def _is_common(self, name: str) -> bool:
        """Whether ``name`` renders above the tabs rather than inside one.

        Recomputed on every write. A setting the members agree on is shared;
        one they disagree on is not. Nothing declares this anywhere, which is
        what makes the feature land on every module for free.
        """
        if name in self.ALWAYS_PER_TAB:
            return False
        members = self._group_members()
        if len(members) < 2:
            return False
        return name in shared_values([handle.entry for handle in members])
```

- [ ] **Step 5: Point the writes at the right targets**

In `properties.py`, replace the target line in `_on_setting_changed`:

```python
        targets = (
            self._group_members()
            if self._is_common(name)
            else (self._multi or [self._current])
        )
```

Everything after it is unchanged — the same loop under `watcher.mute()`, the
same per-handle `_topology` snapshot, the same refresh when a change moved a
port or a guide. Multi-select across ungrouped modules keeps using `_multi`.

And in `_on_input_changed`, fan a common input in:

```python
        targets = (
            self._group_members()
            if self._is_common(f"{INPUT_PREFIX}{input_name}")
            else [self._current]
        )
        try:
            for handle in targets:
                if source:
                    self.guides.connect(f"{handle.key}.{input_name}", source)
                else:
                    self.guides.disconnect(f"{handle.key}.{input_name}")
        except TriggerError as error:
            ...  # unchanged
```

- [ ] **Step 6: Add the tab verbs**

```python
    def _on_tab_changed(self, index: int) -> None:
        members = self._group_members()
        if 0 <= index < len(members):
            self._current = members[index]
            self._multi = []
            self.refresh()

    def _on_add_copy(self) -> None:
        if self._current is None:
            return
        copy = self.guides.add_copy(self._current)
        self._current = copy
        self.refresh()
        self.tab_bar.setCurrentIndex(self.tab_bar.count() - 1)

    def _on_tab_renamed(self, index: int, text: str) -> None:
        members = self._group_members()
        if 0 <= index < len(members) and text:
            self.guides.rename_instance(members[index].instance_id, text)
            self.refresh()

    def _on_tabs_reordered(self, *_args) -> None:
        group = (
            self.guides.group_of(self._current.instance_id)
            if self._current
            else None
        )
        if group is None:
            return
        order = {
            self.tab_bar.tabText(i): i for i in range(self.tab_bar.count())
        }
        names = {
            handle.instance.name: handle.instance_id
            for handle in self.guides.group_members(group.group_id)
        }
        group.members = [
            names[text]
            for text in sorted(order, key=order.get)
            if text in names
        ]
        self.guides._touch()
```

- [ ] **Step 7: Render the split in `refresh`**

Where the form is populated, route each field to the `Common` container or the
per-tab container using `_is_common(name)`, and mark a per-tab field the
members disagree on. Use a glyph that is **not** the reference override diamond
— they would sit in the same panel and mean different things. Use `≠`:

```python
            if not self._is_common(name) and name in varying:
                widget.setToolTip("Members differ on this setting")
                label.setText(f"{label.text()}  ≠")
```

where `varying = varying_names([h.entry for h in self._group_members()])`.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_group_tabs.py -v`
Expected: all passed

- [ ] **Step 9: Run the whole UI suite for regressions**

Run: `make tests-ui`
Expected: all passed — multi-select editing of ungrouped modules must still work.

- [ ] **Step 10: Commit**

```bash
git add src/python/tik/trigger/ui/designer/ tests/ui/test_group_tabs.py
git commit -m "Designer: a tab bar per module, and a Common fold above it"
```

---

### Task 12: Group rows in the tree and the kinematics picker

**Files:**
- Modify: `src/python/tik/trigger/ui/draw_state.py` (add `worst_state`)
- Modify: `src/python/tik/trigger/ui/designer/window.py:535-594` (the tree fill)
- Modify: `src/python/tik/shared/ui/check_list.py`
- Test: `tests/unit/test_draw_state_trigger.py` (create), `tests/ui/test_group_tabs.py`, `tests/ui/test_check_list.py`

**Interfaces:**
- Consumes: `StubScene.groups()`, `group_members()`; the existing
  `states_from(diff) -> {instance_id: state}` in `ui/draw_state.py`.
- Produces: `worst_state(states) -> str` in `ui/draw_state.py`; a group parent
  `QTreeWidgetItem` in the Designer's tree plus `GuideDesigner.item_for_group`;
  and on `CheckListEditor`, `set_groups(groups)` plus `tick_group(label, on)`.

**Note on the two trees.** `ui/model.py` is the *pipeline* (actions) model and
is **not** involved. The Guide Designer's tree is a plain `GuideTree`
(`QTreeWidget`, `ui/designer/widgets.py:32`) filled in `window.py:535-594`.

**Note on the states.** There are three, not four:
`NOT_DRAWN` / `DRAWN` / `STALE` (`ui/draw_state.py`). "Drifted" and "absent"
are `reconcile` vocabulary that `state_of` has already folded into these.

- [ ] **Step 1: Write the failing test for the pure part**

Create `tests/unit/test_draw_state_trigger.py`:

```python
"""Draw-state aggregation: what a group row shows."""

from tik.trigger.ui.draw_state import DRAWN, NOT_DRAWN, STALE, worst_state


def test_stale_wins_over_everything():
    """A group row says the most urgent thing any member is saying."""
    assert worst_state([DRAWN, STALE, NOT_DRAWN]) == STALE


def test_drawn_wins_over_not_drawn():
    assert worst_state([NOT_DRAWN, DRAWN]) == DRAWN


def test_all_undrawn_is_undrawn():
    assert worst_state([NOT_DRAWN, NOT_DRAWN]) == NOT_DRAWN


def test_no_members_reads_as_undrawn():
    assert worst_state([]) == NOT_DRAWN
```

- [ ] **Step 2: Run it to verify it fails**

Run: `mayapy -m pytest tests/unit/test_draw_state_trigger.py -v`
Expected: FAIL - `ImportError: cannot import name 'worst_state'`

- [ ] **Step 3: Implement `worst_state`**

Add to `src/python/tik/trigger/ui/draw_state.py`:

```python
#: Most urgent first. A group row shows the worst thing any member is saying,
#: so one glance at a collapsed hand tells the rigger whether anything in it
#: needs redrawing.
_RANK = (STALE, DRAWN, NOT_DRAWN)


def worst_state(states) -> str:
    """The most urgent of ``states``; ``NOT_DRAWN`` when there are none."""
    present = set(states)
    for state in _RANK:
        if state in present:
            return state
    return NOT_DRAWN
```

- [ ] **Step 4: Run it to verify it passes**

Run: `mayapy -m pytest tests/unit/test_draw_state_trigger.py -v`
Expected: 4 passed

- [ ] **Step 5: Write the failing tests for the tree and the picker**

Append to `tests/ui/test_group_tabs.py`:

```python
def test_the_tree_shows_a_group_as_a_parent_of_its_members(designer):
    window, scene, group, handles = _grouped(designer)
    parent = window.item_for_group(group.group_id)
    assert parent is not None
    assert parent.text(0) == "L_fingers"
    children = [parent.child(i).text(0) for i in range(parent.childCount())]
    assert children == ["L_f0", "L_f1", "L_f2"]


def test_a_grouped_member_is_not_also_a_top_level_row(designer):
    window, scene, group, handles = _grouped(designer)
    top = [
        window.tree.topLevelItem(i).text(0)
        for i in range(window.tree.topLevelItemCount())
    ]
    assert "L_f0" not in top
    assert "L_fingers" in top
```

Append to `tests/ui/test_check_list.py`:

```python
def test_a_group_row_ticks_every_member(qtbot):
    from tik.shared.ui.check_list import CheckListEditor

    editor = CheckListEditor(choices=[("L_f0", "a"), ("L_f1", "b"), ("spine", "c")])
    qtbot.addWidget(editor)
    editor.set_groups([("L_fingers", ["a", "b"])])
    editor.tick_group("L_fingers", True)
    assert set(editor.value()) == {"a", "b"}


def test_unticking_a_group_leaves_other_ticks_alone(qtbot):
    from tik.shared.ui.check_list import CheckListEditor

    editor = CheckListEditor(choices=[("L_f0", "a"), ("L_f1", "b"), ("spine", "c")])
    qtbot.addWidget(editor)
    editor.set_value(["a", "b", "c"])
    editor.set_groups([("L_fingers", ["a", "b"])])
    editor.tick_group("L_fingers", False)
    assert editor.value() == ["c"]


def test_the_picker_still_stores_member_ids_not_group_ids(qtbot):
    """A group row is a way to tick several boxes, never a stored value."""
    from tik.shared.ui.check_list import CheckListEditor

    editor = CheckListEditor(choices=[("L_f0", "a"), ("L_f1", "b")])
    qtbot.addWidget(editor)
    editor.set_groups([("L_fingers", ["a", "b"])])
    editor.tick_group("L_fingers", True)
    assert "L_fingers" not in editor.value()
```

Check the `CheckListEditor(choices=...)` keyword against its `__init__`
(`shared/ui/check_list.py:49`) before running - match whatever the existing
cases in `tests/ui/test_check_list.py` already pass in, rather than guessing.

- [ ] **Step 6: Run them to verify they fail**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_group_tabs.py tests/ui/test_check_list.py -k "tree or group" -v`
Expected: FAIL - no `item_for_group`, no `set_groups`.

- [ ] **Step 7: Fill group rows into the tree**

In the tree fill at `window.py:535-594`, before the per-module loop, create one
`QTreeWidgetItem` per group and remember which member belongs to which; then
parent each member item to its group's item instead of calling
`self.tree.addTopLevelItem(item)`:

```python
        group_items = {}
        for group in self.guides.groups():
            members = self.guides.group_members(group.group_id)
            side = members[0].instance.side if members else "C"
            item = QtWidgets.QTreeWidgetItem([group.key(side)])
            item.setData(0, GROUP_ID_ROLE, group.group_id)
            item.setData(
                0,
                STATE_ROLE,
                worst_state(
                    states.get(handle.instance_id, NOT_DRAWN) for handle in members
                ),
            )
            self.tree.addTopLevelItem(item)
            for member in group.members:
                group_items[member] = item
```

Then in the member loop, `group_items.get(instance_id)` decides the parent.
`GROUP_ID_ROLE` is a new item role beside the existing per-module id role;
`STATE_ROLE` already exists in `ui/designer/delegates.py:21`.

Add the lookup the tests use:

```python
    def item_for_group(self, group_id: str):
        """The tree row for a module group, or None."""
        iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, GROUP_ID_ROLE) == group_id:
                return item
            iterator += 1
        return None
```

- [ ] **Step 8: Add the picker's group rows**

In `check_list.py`. Storage is unchanged - `value()` still returns member ids
only, so nothing in the action layer learns the concept:

```python
    def set_groups(self, groups) -> None:
        """Add a parent row per group. ``groups`` is ``[(label, [id, ...])]``.

        Display only, in the same sense the sort order is display only: a
        group row is a way to tick several boxes at once, never a value the
        list stores.
        """
        self._groups = list(groups)
        self._repopulate()

    def tick_group(self, label: str, on: bool) -> None:
        """Tick or untick every member of the named group."""
        members = next(
            (set(ids) for name, ids in self._groups if name == label), set()
        )
        ticked = set(self.value())
        self.set_value(sorted(ticked | members if on else ticked - members))
```

Initialise `self._groups = []` in `__init__`. `set_value` is the existing
public path - it re-reads the options, preserves stored-but-unoffered values
and calls `_repopulate` - so `tick_group` needs no new item plumbing.

- [ ] **Step 9: Run the tests to verify they pass**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_group_tabs.py tests/ui/test_check_list.py -v`
Expected: all passed

- [ ] **Step 10: Verify the kinematics picker still round-trips**

Run: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ui/test_kinematics_picker.py -v`
Expected: all passed

- [ ] **Step 11: Commit**

```bash
git add src/python/tik/trigger/ui/draw_state.py src/python/tik/trigger/ui/designer/window.py src/python/tik/shared/ui/check_list.py tests/unit/test_draw_state_trigger.py tests/ui/
git commit -m "Module groups: parent rows in the tree and the kinematics picker"
```

---

### Task 13: The `.trg` carries groups

**Files:**
- Modify: `src/python/tik/trigger/guides/exchange.py`
- Modify: `src/python/tik/trigger/guides/format.py` (if the file schema is declared there)
- Test: `tests/unit/test_guides_trigger.py`

**Interfaces:**
- Consumes: `ModuleGroup.to_dict`/`from_dict`, `GuideDocument.module_groups`.
- Produces: an optional `"module_groups"` key in the `.trg` payload, written on export and restored on import with **fresh** `group_id`s and remapped member ids.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_guides_trigger.py`:

```python
def test_trg_round_trips_a_module_group(guides, tmp_path):
    from tik.trigger.guides.scene import GuideScene

    handles = [guides.add("fkchain", name=n, side="L") for n in ("a", "b")]
    guides.group(handles, label="fingers")
    path = tmp_path / "hand.trg"
    guides.export_file(str(path))

    fresh = GuideScene()
    fresh.import_file(str(path))
    assert len(fresh.document.module_groups) == 1
    group = fresh.document.module_groups[0]
    assert group.label == "fingers"
    assert len(group.members) == 2
    assert set(group.members) <= {e.instance_id for e in fresh.document.modules}


def test_importing_a_trg_twice_gives_two_independent_groups(guides, tmp_path):
    """Member ids are remapped on import, so the second group cannot claim
    the first one's modules."""
    from tik.trigger.guides.scene import GuideScene

    handles = [guides.add("fkchain", name=n, side="L") for n in ("a", "b")]
    guides.group(handles, label="fingers")
    path = tmp_path / "hand.trg"
    guides.export_file(str(path))

    fresh = GuideScene()
    fresh.import_file(str(path))
    fresh.import_file(str(path))
    assert len(fresh.document.module_groups) == 2
    first, second = fresh.document.module_groups
    assert set(first.members).isdisjoint(second.members)


def test_a_trg_without_groups_imports_as_loose_modules(guides, tmp_path):
    """A reader that predates the section gets modules, which is the correct
    degraded result."""
    from tik.trigger.guides.scene import GuideScene

    [guides.add("fkchain", name=n, side="L") for n in ("a", "b")]
    path = tmp_path / "loose.trg"
    guides.export_file(str(path))
    fresh = GuideScene()
    fresh.import_file(str(path))
    assert fresh.document.module_groups == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mayapy -m pytest tests/unit/test_guides_trigger.py -k trg_round_trips_a_module_group -v`
Expected: FAIL — `assert 0 == 1`

- [ ] **Step 3: Write the minimal implementation**

In `exchange.py`, on export, add the section beside the modules:

```python
        payload["module_groups"] = [
            group.to_dict() for group in self.document.module_groups
        ]
```

On import, rebuild each group with a fresh id and the import's id remapping.
The import path already builds a map from file instance ids to newly created
ones — reuse it; if it does not keep one, build it as modules are created:

```python
        for data in payload.get("module_groups") or []:
            members = [
                remapped[member]
                for member in data.get("members", [])
                if member in remapped
            ]
            if len(members) >= 2:
                make_group(self.document, data.get("label", "group"), members)
```

Fresh ids are not optional: importing the same `.trg` twice must give two
independent groups, and a reused `group_id` would make the second import
silently overwrite the first.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mayapy -m pytest tests/unit/test_guides_trigger.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/guides/exchange.py src/python/tik/trigger/guides/format.py tests/unit/test_guides_trigger.py
git commit -m "Module groups: the .trg carries them"
```

---

### Task 14: Prove the invariant end to end

**Files:**
- Test: `tests/integration/trigger/test_group_invariant_trigger.py` (create)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing. This task adds no source changes; if it fails, an earlier task is wrong.

- [ ] **Step 1: Write the test**

Create `tests/integration/trigger/test_group_invariant_trigger.py`:

```python
"""Grouping never changes the rig.

The mechanical half of this guarantee is in
``tests/unit/test_import_boundaries.py``, which forbids the build path from
seeing a group at all. This is the behavioural half: the same members, grouped
or not, build the same rig.

The ``scene`` fixture comes from ``tests/integration/trigger/conftest.py``.
"""

from maya import cmds


def _built_shape():
    """A stable description of what the scene contains after a build."""
    nodes = sorted(cmds.ls("rig_grp", dag=True, long=True) or [])
    return [
        (
            name.rsplit("|", 1)[-1],
            cmds.nodeType(name),
            sorted(cmds.listRelatives(name, children=True) or []),
        )
        for name in nodes
    ]


def _five_chains(scene):
    return [
        scene.add("fkchain", name=f"f{index}", side="L") for index in range(5)
    ]


def test_a_grouped_build_matches_an_ungrouped_build(scene):
    handles = _five_chains(scene)
    scene.draw()
    scene.test_build()
    ungrouped = _built_shape()

    scene.clear_test_rig()
    scene.group(handles, label="fingers")
    scene.test_build()
    grouped = _built_shape()

    assert grouped == ungrouped


def test_ungrouping_between_builds_changes_nothing(scene):
    handles = _five_chains(scene)
    group = scene.group(handles, label="fingers")
    scene.draw()
    scene.test_build()
    grouped = _built_shape()

    scene.clear_test_rig()
    scene.ungroup(group.group_id)
    scene.test_build()
    assert _built_shape() == grouped


def test_no_built_node_is_named_after_the_group(scene):
    handles = _five_chains(scene)
    scene.group(handles, label="fingers")
    scene.draw()
    scene.test_build()
    assert not cmds.ls("*fingers*")
```

- [ ] **Step 2: Run the test**

Run: `mayapy -m pytest tests/integration/trigger/test_group_invariant_trigger.py -v`
Expected: all passed. **If any fails, an earlier task leaked a group into the
build — fix that task rather than weakening this test.**

- [ ] **Step 3: Run everything**

Run: `make tests && make tests-ui && make lint`
Expected: all passed, lint clean.

- [ ] **Step 4: Update `CLAUDE.md`**

Add module groups to the tik.trigger status paragraph and add the spec to the
design-specs list, plus the two new test files to the tests list.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/trigger/test_group_invariant_trigger.py CLAUDE.md
git commit -m "Module groups: prove grouping never changes the rig"
```

---

## Self-Review Notes

**Spec coverage.** §3 the record → Tasks 1-2. §3 the operations → Task 3. §4 frames → Tasks 8-9. §5.1 derivation → Tasks 4, 11. §5.2 the write path → Task 11 steps 5. §5.3 tab verbs → Task 11 step 6. §5.4 stacking → Task 6 (`add_copy` uses `duplicate`, which copies poses). §6 graph → Tasks 9-10. §7 tree → Task 12. §7 mirror → Task 6. §7 references → Task 3 (`_check_homogeneous` refuses mixed origin). §7 kinematics → Task 12. §7 `.trg` → Task 13. §7.1 untouched → Task 5 and Task 14. §8 → Tasks 5 and 14. §9 lifecycle → Task 3 and Task 6 step 4. §10 tests → all tasks.

**Two things an executor should expect to discover.**

1. Task 11 step 7 assumes `FormBuilder` can render into two containers. If it cannot, the smallest honest change is to build **two** `FormBuilder`s — one for `Common`, one for the tab — each given the field subset it owns. Do that rather than teaching one builder about groups.
2. Task 13 assumes the `.trg` import path keeps a map from file instance ids to created ones. If it does not, build the map as modules are created; do not match members by name, which is not unique across an import.

**Deferred deliberately.** Per-member *guide* sharing, cross-side groups, and nested groups are all out of scope. So is a group-level shape or space table: those resolve per module and a group-level one would be a second place for the same fact.
