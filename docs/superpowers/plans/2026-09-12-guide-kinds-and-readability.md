# Guide Kinds and Guide Readability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a guide declare *what it is* and let the framework derive how it looks — so guide radius, colour, shape, bone-drawing and labels stop being magic numbers at module call sites.

**Architecture:** A four-value `GuideKind` vocabulary lives in `tik/trigger/core/manifest.py` (pure Python). `ROOT` and `JOINT` are derived from the structure `draw_guides` already builds; `REFERENCE` and `DRIVEN` are declared on `GuideLayout`. `tik/trigger/guides/nodes.py` owns the single kind→appearance table. A `REFERENCE` guide is a `transform` carrying a locator shape, which is the only measured way to suppress a bone without suppressing its siblings.

**Tech Stack:** Python 3.10+, Maya 2024+, `tik.maya` wrapper, pytest under `mayapy`, Qt via `tik.shared.ui.Qt`.

**Spec:** `docs/superpowers/specs/2026-09-12-guide-kinds-and-readability-design.md`

## Global Constraints

- **No third-party deps.** Stdlib and Maya-bundled modules only.
- **`tik/trigger/core` is pure Python** — no Maya, no Qt. Enforced by `tests/unit/test_import_boundaries.py`.
- **Preferences never change the rig.** `trigger/core`, `modules`, `systems`, `maya`, `actions` and `guides` may not import the preferences packages at all. Only `trigger/ui` may read `tik.trigger.config.prefs`.
- **Consume tik.maya** — no raw `maya.cmds` in tool code, *except* inside `tik/trigger/guides/` and `tik/trigger/maya/`, which already use `cmds` directly for scene scans and world-space queries. Follow the surrounding file.
- **Modules never inherit from other modules.** Shared behaviour goes in `tik/trigger/systems/`.
- **One dialog surface** — every user dialog goes through `tik.shared.ui.feedback.Feedback`.
- **No backward compatibility required.** There are no sessions to migrate; do not add compatibility shims, and do not keep old function names as aliases.
- **Maya colour indices in use:** `SIDE_COLORS = {"L": 6, "R": 13, "C": 17}`, `MARKER_COLOR = 14`.

**Test commands:**
- Unit: `make tests-unit`
- Integration: `make tests-integration`
- UI: `make tests-ui`
- Single test: `mayapy -m pytest tests/unit/test_guide_kinds_trigger.py::test_name -v`

---

### Task 1: The `GuideKind` vocabulary

**Files:**
- Modify: `src/python/tik/trigger/core/manifest.py:70-150`
- Modify: `src/python/tik/trigger/core/__init__.py:53,101`
- Test: `tests/unit/test_guide_kinds_trigger.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `GuideKind` — a `str` `Enum` with members `ROOT`, `JOINT`, `REFERENCE`, `DRIVEN` (values `"root"`, `"joint"`, `"reference"`, `"driven"`).
  - `GuideLayout(*roles, multi=None, min=None, max=None, reference=(), driven=())`
  - `GuideLayout.reference: tuple[str, ...]`, `GuideLayout.driven: tuple[str, ...]`
  - `GuideLayout.kind_for(role: str, *, is_root: bool = False) -> GuideKind`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_guide_kinds_trigger.py`:

```python
"""Guide kinds: what a guide *is*, and what the framework may derive from it.

Pure — no Maya. The appearance these kinds resolve to lives in
``tik/trigger/guides/nodes.py`` and is covered by the integration tests.
"""

from __future__ import annotations

import pytest

from tik.trigger.core import GuideKind, GuideLayout


def test_first_role_is_root_and_the_rest_are_joints():
    layout = GuideLayout("collar", "shoulder", "elbow", "hand")
    assert layout.kind_for("collar", is_root=True) is GuideKind.ROOT
    assert layout.kind_for("shoulder") is GuideKind.JOINT
    assert layout.kind_for("hand") is GuideKind.JOINT


def test_declared_reference_wins_over_derivation():
    layout = GuideLayout("collar", "shoulder", "neutral", reference=("neutral",))
    assert layout.kind_for("neutral") is GuideKind.REFERENCE
    assert layout.reference == ("neutral",)


def test_declared_driven_wins_over_derivation():
    layout = GuideLayout("base", "end", multi="twist", driven=("twist",))
    assert layout.kind_for("twist") is GuideKind.DRIVEN
    assert layout.driven == ("twist",)


def test_a_multi_role_may_be_declared():
    # the multi role is not in `roles`, so validation must consult all_roles
    GuideLayout("base", multi="twist", driven=("twist",))


def test_unknown_role_is_a_plain_joint():
    # pivot preset roles are created by the framework and are not in any layout
    layout = GuideLayout("hand")
    assert layout.kind_for("pivot_ik_wrist") is GuideKind.JOINT


def test_reference_naming_an_absent_role_raises():
    with pytest.raises(ValueError, match="not one of its roles"):
        GuideLayout("collar", "shoulder", reference=("nope",))


def test_driven_naming_an_absent_role_raises():
    with pytest.raises(ValueError, match="not one of its roles"):
        GuideLayout("collar", "shoulder", driven=("nope",))


def test_a_role_in_both_raises():
    with pytest.raises(ValueError, match="both reference and driven"):
        GuideLayout("collar", "neutral", reference=("neutral",), driven=("neutral",))


def test_the_root_role_may_not_be_declared():
    # root_guide() and parent_ref() walk joints; a module's root must be one
    with pytest.raises(ValueError, match="root role"):
        GuideLayout("collar", "shoulder", reference=("collar",))
    with pytest.raises(ValueError, match="root role"):
        GuideLayout("collar", "shoulder", driven=("collar",))


def test_defaults_are_empty_so_existing_layouts_are_unchanged():
    layout = GuideLayout("root", multi="segment", min=2)
    assert layout.reference == ()
    assert layout.driven == ()
    assert layout.kind_for("segment") is GuideKind.JOINT
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `make tests-unit` (or `mayapy -m pytest tests/unit/test_guide_kinds_trigger.py -v`)
Expected: FAIL with `ImportError: cannot import name 'GuideKind'`

- [ ] **Step 3: Add the enum**

In `src/python/tik/trigger/core/manifest.py`, add near the top (after the existing imports):

```python
from enum import Enum


class GuideKind(str, Enum):
    """What a guide *is*, to the rig. Never what it looks like.

    The look is a pure function of the kind and lives in one table, in
    ``tik/trigger/guides/nodes.py``. A module states the kind; nothing
    anywhere states a radius, a colour or a shape.
    """

    #: The module's anchor. Derived: the first guide a copy draws.
    ROOT = "root"
    #: A joint in the rig. Move it, a bone moves. Derived: the default.
    JOINT = "joint"
    #: Only its *position* is read; nothing in the rig is shaped like it.
    REFERENCE = "reference"
    #: A real rig joint the module places, not the rigger. Declared.
    DRIVEN = "driven"
```

- [ ] **Step 4: Extend `GuideLayout`**

Replace `GuideLayout.__init__` in `src/python/tik/trigger/core/manifest.py` (currently lines 82-101) with:

```python
    def __init__(
        self,
        *roles: str,
        multi: Optional[str] = None,
        min: Optional[int] = None,  # noqa: A002
        max: Optional[int] = None,  # noqa: A002
        reference: Sequence[str] = (),
        driven: Sequence[str] = (),
    ) -> None:
        if not roles:
            raise ValueError("GuideLayout needs at least one role.")
        if len(set(roles)) != len(roles):
            raise ValueError("Guide roles must be unique.")
        if multi in roles:
            raise ValueError("The multi role must not repeat a fixed role.")
        self.roles: tuple[str, ...] = tuple(roles)
        self.multi = multi
        self.min_count = (min if min is not None else 1) if multi else 0
        self.max_count = max if multi else 0
        self.reference: tuple[str, ...] = tuple(reference)
        self.driven: tuple[str, ...] = tuple(driven)
        self._validate_kinds()

    def _validate_kinds(self) -> None:
        """Declared kinds must name real, distinct, non-root roles."""
        known = set(self.all_roles)
        for label, group in (("reference", self.reference), ("driven", self.driven)):
            for role in group:
                if role not in known:
                    raise ValueError(
                        f"GuideLayout {label}={role!r} is not one of its roles."
                    )
                if role == self.root:
                    # root_guide() and parent_ref() find a module by walking
                    # guide joints; a root that is neither would strand it.
                    raise ValueError(
                        f"GuideLayout {label}={role!r} is the root role, which "
                        "must stay an ordinary joint."
                    )
        both = set(self.reference) & set(self.driven)
        if both:
            raise ValueError(
                f"Guide role(s) {sorted(both)} declared both reference and driven."
            )

    def kind_for(self, role: str, *, is_root: bool = False) -> "GuideKind":
        """What ``role`` is. Declared kinds win; the rest is derived.

        ``is_root`` comes from the draft, which knows which guide a copy
        created first — not from ``self.root``, because a copy's first guide
        is its own root.

        A role this layout has never heard of is a plain ``JOINT``: pivot
        preset guides are created by the framework, not declared here, and
        ask for their kind explicitly.
        """
        if role in self.reference:
            return GuideKind.REFERENCE
        if role in self.driven:
            return GuideKind.DRIVEN
        return GuideKind.ROOT if is_root else GuideKind.JOINT
```

- [ ] **Step 5: Export it**

In `src/python/tik/trigger/core/__init__.py`, extend the manifest import (line 53) and the `__all__` list (near line 101):

```python
from .manifest import TIERS, GuideAttr, GuideKind, GuideLayout, Input, instance_key
```

and add `"GuideKind",` next to `"GuideLayout",` in `__all__`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `make tests-unit`
Expected: PASS — all 10 new tests, and every existing unit test still green (no existing layout passes `reference=` or `driven=`, so defaults keep them identical).

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/core/manifest.py src/python/tik/trigger/core/__init__.py tests/unit/test_guide_kinds_trigger.py
git commit -m "feat(trigger): a guide has a kind

ROOT and JOINT derive from the structure draw_guides builds; REFERENCE and
DRIVEN are declared on GuideLayout. Pure: the appearance each kind resolves
to lands in guides/nodes.py next."
```

---

### Task 2: Kind-aware guide creation

This is the load-bearing task. `create_guide_joint` becomes `create_guide_node`, gains the kind→appearance table, and learns to build a `REFERENCE` guide as a `transform` with a locator shape. `GuideDraft` resolves the kind and stops accepting `radius` and `marker`. The five `type="joint"` filters widen. All module call sites drop their radius arguments in the same commit, so the tree is never red.

**Files:**
- Modify: `src/python/tik/trigger/guides/nodes.py:96-166` (create), `:172`, `:281`, `:362-363` (filters)
- Modify: `src/python/tik/trigger/guides/snapshot.py:48`
- Modify: `src/python/tik/trigger/maya/rig.py:25` (import), `:139-186` (`GuideDraft.joint`)
- Modify: `src/python/tik/trigger/core/module.py:855-861` (the one `marker=True` call site)
- Modify: `src/python/tik/trigger/modules/arm/arm.py:173-186`, `modules/base/base.py`, `modules/twist/twist.py:117-133`
- Test: `tests/integration/trigger/test_guide_kinds_trigger.py` (create)
- Test: `tests/helpers/toy_modules.py` (add a toy module with a reference guide)

**Interfaces:**
- Consumes: `GuideKind`, `GuideLayout.kind_for` (Task 1).
- Produces:
  - `nodes.KIND_RADIUS: dict[GuideKind, float]`, `nodes.REFERENCE_SCALE: float`, `nodes.DRIVEN_COLORS: dict[str, int]`
  - `nodes.make_guide_shell(name, kind, parent=None) -> tm.Transform` — the bare node, no tags, no pose. Shared by creation and by `.trg` import (Task 4).
  - `nodes.create_guide_node(module, role, position, *, kind, index=0, parent=None, tag_role="") -> tm.Transform`
  - `GuideDraft.joint(role, position, *, index=0, parent=None) -> tm.Transform` — no `radius`, no `marker`
  - `GuideDraft.reference(role, position, *, index=0, parent=None) -> tm.Transform`
  - `GuideDraft.chain_step(anchor) -> tuple[tuple[float, float, float], float]`
- **Removed:** `nodes.create_guide_joint`, `nodes._style_as_marker`, the `radius=` and `marker=` parameters.

- [ ] **Step 1: Add a toy module with a reference guide**

In `tests/helpers/toy_modules.py`, add alongside the existing toys:

```python
@register_module("toy_reference", category="tests")
class ToyReference(Module):
    """A root, a chain joint, a reference and a driven guide — one of each kind."""

    label = "Toy Reference"
    guides = GuideLayout(
        "root", "tip", "aim", multi="rail",
        reference=("aim",),
        driven=("rail",),
    )
    outputs = ("root",)

    def draw_guides(self, guides) -> None:
        root = guides.joint("root", (0, 0, 0))
        guides.joint("tip", (5 * guides.side_mult, 0, 0), parent=root)
        guides.joint("aim", (0, 0, 8), parent=root)
        guides.joint("rail", (2 * guides.side_mult, 0, 0), index=0, parent=root)

    def build(self, rig) -> None:
        rig.output("root", rig.bind_joint("root", match=rig.guide("root")))
```

Import `GuideLayout` and `register_module` from `tik.trigger.core` if the file does not already.

- [ ] **Step 2: Write the failing integration tests**

Create `tests/integration/trigger/test_guide_kinds_trigger.py`:

```python
"""Each guide kind renders as the one thing its kind says it is.

Against a real Maya. The kind vocabulary itself is unit-tested in
``tests/unit/test_guide_kinds_trigger.py``.
"""

from __future__ import annotations

from maya import cmds

from tik.trigger.core import GuideKind
from tik.trigger.guides import nodes


def _drawn(session, module_type="toy_reference", side="L"):
    """Draw one module and return ``{role: long name}``."""
    handle = session.guides.create(module_type, name="toy", side=side)
    session.guides.draw([handle.instance_id])
    return {
        role: node.long_name
        for (role, _index), node in session.guides.guide_nodes(
            handle.instance_id
        ).items()
    }


def test_reference_guide_is_not_a_joint(trigger_session):
    drawn = _drawn(trigger_session)
    assert cmds.nodeType(drawn["aim"]) == "transform"
    assert cmds.nodeType(drawn["root"]) == "joint"


def test_reference_guide_carries_a_locator_shape(trigger_session):
    drawn = _drawn(trigger_session)
    shapes = cmds.listRelatives(drawn["aim"], shapes=True, type="locator") or []
    assert len(shapes) == 1
    assert cmds.getAttr(f"{shapes[0]}.localScaleX") == nodes.REFERENCE_SCALE


def test_reference_guide_still_hangs_under_its_anchor(trigger_session):
    drawn = _drawn(trigger_session)
    parent = cmds.listRelatives(drawn["aim"], parent=True, fullPath=True)[0]
    assert parent == drawn["root"]


def test_radius_comes_from_the_kind(trigger_session):
    drawn = _drawn(trigger_session)
    assert cmds.getAttr(f"{drawn['root']}.radius") == nodes.KIND_RADIUS[GuideKind.ROOT]
    assert cmds.getAttr(f"{drawn['tip']}.radius") == nodes.KIND_RADIUS[GuideKind.JOINT]
    assert (
        cmds.getAttr(f"{drawn['rail']}.radius") == nodes.KIND_RADIUS[GuideKind.DRIVEN]
    )


def test_driven_guide_is_a_joint_and_keeps_its_bone(trigger_session):
    # DRIVEN is subordinate, not absent: it stays a joint so the chain reads
    drawn = _drawn(trigger_session)
    assert cmds.nodeType(drawn["rail"]) == "joint"


def test_a_reference_guide_is_still_found_by_the_scans(trigger_session):
    # the five filters widened from type="joint" to type="transform"
    handle = trigger_session.guides.create("toy_reference", name="toy", side="L")
    trigger_session.guides.draw([handle.instance_id])
    assert ("aim", 0) in trigger_session.guides.guide_nodes(handle.instance_id)
    instances = trigger_session.guides.find_instances([handle.instance_id])
    assert any(pose.role == "aim" for pose in instances[0].guides)


def test_sync_captures_a_reference_guide_pose(trigger_session):
    handle = trigger_session.guides.create("toy_reference", name="toy", side="L")
    trigger_session.guides.draw([handle.instance_id])
    node = trigger_session.guides.guide_nodes(handle.instance_id)[("aim", 0)]
    cmds.xform(node.long_name, worldSpace=True, translation=(1.0, 2.0, 3.0))
    trigger_session.guides.sync([handle.instance_id])
    entry = trigger_session.guides.document.module(handle.instance_id)
    pose = next(item for item in entry.poses if item.role == "aim")
    assert tuple(round(value, 3) for value in pose.position) == (1.0, 2.0, 3.0)
```

**Note for the implementer:** `trigger_session` is the existing integration fixture — check `tests/integration/trigger/conftest.py` for its real name and the real spelling of `session.guides.create/draw/sync/guide_nodes/find_instances` and of the document's pose accessor (`entry.poses` above is a guess). Fix the calls to match the codebase before running; do **not** change what the tests assert. Delete the nonsense `assert any(... or [])` line in `test_a_reference_guide_is_still_found_by_the_scans` — it is a leftover; the other two assertions in that test are the real ones.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `mayapy -m pytest tests/integration/trigger/test_guide_kinds_trigger.py -v`
Expected: FAIL — `AttributeError: module 'tik.trigger.guides.nodes' has no attribute 'REFERENCE_SCALE'`

- [ ] **Step 4: Add the appearance table and the shell builder**

In `src/python/tik/trigger/guides/nodes.py`, replace the colour constants block (lines 26-27) with:

```python
from tik.trigger.core.manifest import GuideKind

SIDE_COLORS = {"L": 6, "R": 13, "C": 17}
MARKER_COLOR = 14  # green: a reference guide, never a chain link

#: The kind -> appearance table. The *only* place a guide's look is decided.
#: A module states a kind; nothing anywhere states a radius or a colour.
KIND_RADIUS = {
    GuideKind.ROOT: 1.5,
    GuideKind.JOINT: 1.0,
    GuideKind.DRIVEN: 0.5,
}
#: localScale of a reference guide's locator shape.
REFERENCE_SCALE = 0.6
#: A railed guide reads as subordinate to the chain it sits in, so it takes a
#: darker shade of its side colour rather than a colour of its own.
DRIVEN_COLORS = {"L": 15, "R": 12, "C": 3}
#: Maya's joint-label side enum: 0 centre, 1 left, 2 right, 3 none.
LABEL_SIDES = {"C": 0, "L": 1, "R": 2}
```

Then add, above `create_guide_joint`:

```python
def make_guide_shell(name: str, kind: GuideKind, parent=None) -> tm.Transform:
    """The bare node for one guide of ``kind`` — no tags, no pose, no label.

    Shared by a fresh draw and by ``.trg`` import, so the two can never
    disagree about what a kind renders as.

    A ``REFERENCE`` guide is a plain transform because that is the only thing
    that suppresses the bone. Measured in Maya 2024: the bone belongs to the
    *parent* joint, so ``drawStyle`` on the child does nothing and
    ``drawStyle`` on the parent removes every one of its bones; and an
    intervening transform does not break it, because joint drawing walks
    through transforms to find descendant joints. A non-joint child draws
    nothing at all, which is the whole mechanism.
    """
    parent_name = parent.long_name if hasattr(parent, "long_name") else parent
    if kind is GuideKind.REFERENCE:
        node = tm.Transform.create(name=name, parent=parent_name)
        # Created straight under the transform rather than via ``spaceLocator``
        # and a reparent: importing a ``.trg`` draws a scratch copy beside the
        # real one, so two guides legitimately share a short name.
        shape = tm.create_node("locator", name=f"{name}Shape", parent=node.long_name)
        for axis in "XYZ":
            shape[f"localScale{axis}"].value = REFERENCE_SCALE
        return node
    return tm.Joint.create(name=name, parent=parent_name, radius=KIND_RADIUS[kind])


def guide_color(kind: GuideKind, side: str) -> int:
    """The colour index for a guide of ``kind`` on ``side``."""
    if kind is GuideKind.REFERENCE:
        return MARKER_COLOR
    table = DRIVEN_COLORS if kind is GuideKind.DRIVEN else SIDE_COLORS
    return table.get(side, 17)
```

- [ ] **Step 5: Replace `create_guide_joint` with `create_guide_node`**

In `src/python/tik/trigger/guides/nodes.py`, replace the whole of `create_guide_joint` (lines 96-146) and delete `_style_as_marker` (lines 149-166) entirely:

```python
def create_guide_node(
    module,
    role: str,
    position: Sequence[float],
    *,
    kind: GuideKind,
    index: int = 0,
    parent=None,
    tag_role: str = "",
) -> tm.Transform:
    """Create one tagged guide node for ``module``, rendered by its ``kind``.

    ``tag_role`` is the role the *document* keys this guide by, when that
    differs from the one the node is named after. A module's second copy keys
    its guides ``c1_root`` while the joint reads ``L_thumb_root_guide``: the
    slug is bookkeeping and has no business in a name a rigger reads. Defaults
    to ``role``, which is every non-copy case.
    """
    name = naming.format_name(
        module.name,
        role,
        index if index else None,
        side=module.side.value,
        suffix="guide",
    )
    node = make_guide_shell(name, kind, parent=parent)
    node.world_position = position
    tags.tag(
        node,
        **{
            tags.KIND: tags.GUIDE,
            tags.MODULE: module.module_type,
            tags.INSTANCE: module.instance_id,
            tags.ROLE: tag_role or role,
            tags.INDEX: index,
            tags.SIDE: module.side.value,
            # what this rendering was drawn as, so reconcile can notice a
            # rename -- guides are matched on the uuid, never on names
            tags.DRAWN_KEY: instance_key(module.name, module.side.value),
        },
    )
    node.color = guide_color(kind, module.side.value)
    return node
```

**Labels are Task 3** — do not add them here.

- [ ] **Step 6: Widen the five filters**

In `src/python/tik/trigger/guides/nodes.py`:

- line 172 — `tm.find_by_meta(tags.INSTANCE, instance_id, node_type="joint")` becomes `node_type="transform"`
- line 281 — `cmds.ls(..., type="joint")` becomes `type="transform"`
- line 362 — `cmds.ls(selection=True, long=True, type="joint")` becomes `type="transform"`
- line 363 — `node = tm.Joint(name)` becomes `node = tm.resolve(name)`

In `src/python/tik/trigger/guides/snapshot.py` line 48 — `cmds.ls(..., type="joint")` becomes `type="transform"`.

Update the comment above each `cmds.ls` from "every tagged joint" to "every tagged guide node", and add once, at line 281:

```python
    # type="transform" rather than "joint": `joint` inherits from `transform`,
    # so this is a widening that cannot lose a node, and reference guides are
    # transforms. The KIND == GUIDE check below is what makes it exact.
```

Also update the type hints: `guide_nodes` returns `dict[tuple[str, int], tm.Transform]`, and `guide_node` returns `tm.Transform`.

- [ ] **Step 7: Rework `GuideDraft`**

In `src/python/tik/trigger/maya/rig.py`, change the import on line 25:

```python
from tik.trigger.core.manifest import GuideKind
from tik.trigger.guides.nodes import SIDE_COLORS, create_guide_node
```

Add `import math` at the top if absent. Replace `GuideDraft.joint` (lines 150-186) with:

```python
    def joint(
        self,
        role: str,
        position: Sequence[float],
        *,
        index: int = 0,
        parent: Any = None,
    ) -> tm.Transform:
        """Create one tagged guide; the first one becomes the copy's root.

        There is no ``radius`` and no ``marker``. What a guide looks like is a
        consequence of what it *is*, and what it is comes from the module's
        ``GuideLayout`` — so no call site anywhere picks a number.
        """
        layout = type(self._drawing).guides
        kind = layout.kind_for(role, is_root=self.root is None)
        return self._create(role, position, kind, index=index, parent=parent)

    def reference(
        self,
        role: str,
        position: Sequence[float],
        *,
        index: int = 0,
        parent: Any = None,
    ) -> tm.Transform:
        """Create a reference guide for a role no layout declares.

        Pivot preset guides are made by the framework from a settings table,
        not declared in a ``GuideLayout``, so they name their kind here rather
        than being looked up. Module authors never call this.
        """
        return self._create(
            role, position, GuideKind.REFERENCE, index=index, parent=parent
        )

    def _create(self, role, position, kind, *, index=0, parent=None) -> tm.Transform:
        key = (Module.qualify(self._slug, role), index)
        if key in self.created:
            raise GuideError(f"Guide '{key[0]}' [{index}] created twice.")
        is_root = self.root is None
        if parent is None:
            parent = self.parent_node if is_root else self.root
            if parent is None:
                parent = self.holder
        node = create_guide_node(
            self._drawing,
            role,
            position,
            kind=kind,
            index=index,
            parent=parent,
            tag_role=key[0],
        )
        for declared in self._drawing.attrs_for_role(role):
            node[declared.name].create(
                "float", default=declared.default, keyable=declared.keyable
            )
        self.created[key] = node
        if is_root:
            self.root = node
        return node

    def chain_step(self, anchor) -> tuple[tuple[float, float, float], float]:
        """Unit direction and step length for fanning markers off ``anchor``.

        The direction is the anchor's own incoming bone (parent -> anchor), so
        a fan off a hand runs along the hand's forward axis. A root has no
        incoming bone, so it falls back to the module's aim axis.
        """
        parent = anchor.parent
        if parent is not None:
            here = tuple(anchor.world_position)
            there = tuple(parent.world_position)
            vector = [a - b for a, b in zip(here, there)]
            length = math.sqrt(sum(value * value for value in vector))
            if length > 1e-6:
                unit = tuple(value / length for value in vector)
                return unit, 0.25 * length
        return (float(self.side_mult), 0.0, 0.0), 0.5
```

- [ ] **Step 8: Update the one framework call site that passed `marker`**

In `src/python/tik/trigger/core/module.py`, in `_draw_pivot_guides` (lines 855-861), change the `draft.joint(...)` call to:

```python
            draft.reference(
                f"pivot_{control}_{label}",
                tuple(anchor.world_position),
                parent=anchor,
            )
```

(The fan itself is Task 5 — for now the markers still stack, and the existing tests still pass.)

- [ ] **Step 9: Drop the radius arguments from every module**

- `src/python/tik/trigger/modules/arm/arm.py:175` — `guides.joint("collar", (2 * mult, 0, 0), radius=1.5)` becomes `guides.joint("collar", (2 * mult, 0, 0))`
- `src/python/tik/trigger/modules/arm/arm.py:186` — drop `, radius=0.8` from the `neutral` call
- `src/python/tik/trigger/modules/base/base.py` — `guides.joint("root", (0, 0, 0), radius=2.0)` becomes `guides.joint("root", (0, 0, 0))`
- `src/python/tik/trigger/modules/twist/twist.py:121-122` — drop `, radius=1.5` from both the `base` and `end` calls
- `src/python/tik/trigger/modules/twist/twist.py:126-128` — drop `, radius=0.5` from the `twist` call

`control`, `fkchain` and `ribbon` pass no radius and change nothing.

- [ ] **Step 10: Run the full suite**

Run: `make tests-unit && make tests-integration`
Expected: PASS. The new integration tests pass; `test_module_ground_rules.py`, `test_draw_sync_trigger.py`, `test_guides_trigger.py`, `test_reconcile_trigger.py` and `test_pivot_trigger.py` all stay green.

If `test_guides_trigger.py` fails on `.trg` round-tripping a reference guide, **stop and note it** — that is Task 4's job. Do not patch it here.

- [ ] **Step 11: Commit**

```bash
git add -A src/python/tik/trigger tests
git commit -m "feat(trigger): guides render by kind

create_guide_joint becomes create_guide_node and dispatches on the kind.
A REFERENCE guide is a transform with a locator shape -- the only measured
way to suppress a bone without suppressing its siblings -- so _style_as_marker
and its drawStyle hack are deleted rather than extended. The five type=joint
scan filters widen to transform; each already re-checked KIND == GUIDE, and
joint inherits from transform, so nothing can be lost.

GuideDraft.joint loses radius and marker: no call site picks a number now."
```

---

### Task 3: Labels

**Files:**
- Modify: `src/python/tik/trigger/guides/nodes.py` (add `label_guide`, call it from `create_guide_node`)
- Test: `tests/integration/trigger/test_guide_kinds_trigger.py` (extend)

**Interfaces:**
- Consumes: `GuideKind`, `make_guide_shell`, `LABEL_SIDES`, `MARKER_COLOR` (Task 2).
- Produces:
  - `nodes.label_guide(node, kind: GuideKind, text: str, side: str) -> None`
  - `nodes.guide_label_nodes(node) -> list[str]` — the annotation transforms under a guide, for the toggle in Task 7.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_guide_kinds_trigger.py`:

```python
def test_joint_guides_carry_a_native_label(trigger_session):
    drawn = _drawn(trigger_session, side="L")
    assert cmds.getAttr(f"{drawn['root']}.drawLabel") == 1
    assert cmds.getAttr(f"{drawn['root']}.type") == 18  # Other
    assert cmds.getAttr(f"{drawn['root']}.otherType") == "root"
    assert cmds.getAttr(f"{drawn['root']}.side") == 1  # Left


def test_a_centre_module_labels_without_a_side(trigger_session):
    drawn = _drawn(trigger_session, side="C")
    assert cmds.getAttr(f"{drawn['root']}.side") == 0


def test_reference_guides_carry_an_annotation(trigger_session):
    drawn = _drawn(trigger_session, side="L")
    children = cmds.listRelatives(drawn["aim"], children=True, fullPath=True) or []
    shapes = [
        shape
        for child in children
        for shape in cmds.listRelatives(child, shapes=True, fullPath=True) or []
        if cmds.nodeType(shape) == "annotationShape"
    ]
    assert len(shapes) == 1
    # Maya appends "(L)" itself for joint labels but not for annotations,
    # so the side is built into the text here.
    assert cmds.getAttr(f"{shapes[0]}.text") == "aim (L)"


def test_the_annotation_is_visible_but_unpickable(trigger_session):
    drawn = _drawn(trigger_session, side="L")
    label = nodes.guide_label_nodes(tm.resolve(drawn["aim"]))[0]
    shape = cmds.listRelatives(label, shapes=True, fullPath=True)[0]
    assert cmds.getAttr(f"{shape}.overrideEnabled") == 1
    assert cmds.getAttr(f"{shape}.overrideDisplayType") == 2  # reference


def test_the_annotation_is_invisible_to_the_guide_scans(trigger_session):
    # it carries no trg_kind, and every scan gates on KIND == GUIDE
    handle = trigger_session.guides.create("toy_reference", name="toy", side="L")
    trigger_session.guides.draw([handle.instance_id])
    roles = {role for (role, _index) in trigger_session.guides.guide_nodes(
        handle.instance_id
    )}
    assert roles == {"root", "tip", "aim", "rail"}


def test_a_copy_labels_with_its_slug(trigger_session):
    handle = trigger_session.guides.create("toy_reference", name="toy", side="L")
    handle.copies = ["index", "thumb"]
    trigger_session.guides.draw([handle.instance_id])
    labels = {
        cmds.getAttr(f"{node.long_name}.otherType")
        for (role, _index), node in trigger_session.guides.guide_nodes(
            handle.instance_id
        ).items()
        if role.endswith("root")
    }
    assert labels == {"index_root", "thumb_root"}
```

**Note for the implementer:** add `import tik.maya as tm` to the test file for `tm.resolve`. Check the real API for setting a handle's copies (`handle.copies = [...]` is a guess; see `tests/unit/test_module_copies_trigger.py`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mayapy -m pytest tests/integration/trigger/test_guide_kinds_trigger.py -v -k label`
Expected: FAIL — `getAttr: No object matches name: ...drawLabel` is not it; expect `AssertionError: 0 != 1` on `drawLabel`.

- [ ] **Step 3: Implement labelling**

In `src/python/tik/trigger/guides/nodes.py`, add after `guide_color`:

```python
def label_guide(node, kind: GuideKind, text: str, side: str) -> None:
    """Draw ``text`` beside ``node``, by whatever means its kind allows.

    A joint gets Maya's native label. A reference guide is a transform and has
    no ``drawLabel``, so it gets an annotation parented *at* it -- at zero
    offset, which collapses the leader to a stub arrow rather than a line
    across the scene, which is the streak this whole design removes.

    ``text`` is the *qualified* role, so a five-copy ``fingers`` reads
    ``index_root`` and ``thumb_root`` rather than five guides all reading
    ``root``; a one-copy module has an empty slug and reads as it always has.
    The side is appended only for an annotation, because Maya appends it
    itself for a native joint label and doubling it would read ``(L) (L)``.
    """
    if kind is not GuideKind.REFERENCE:
        node["drawLabel"].value = 1
        node["side"].value = LABEL_SIDES.get(side, 3)
        node["type"].value = 18  # Other: otherType carries the string
        # cmds rather than a tik.maya plug write: `otherType` is a string
        # attribute and setAttr needs its type named explicitly.
        cmds.setAttr(f"{node.long_name}.otherType", text, type="string")
        return

    suffix = f" ({side})" if side in ("L", "R") else ""
    shape = cmds.annotate(node.long_name, text=f"{text}{suffix}")
    # annotate() returns the shape; its transform is a fresh world-space node.
    transform = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
    transform = cmds.parent(transform, node.long_name, relative=True)[0]
    transform = cmds.rename(transform, f"{node.name}_label")
    cmds.setAttr(f"{transform}.translate", 0, 0, 0, type="double3")
    # Re-query: the rename invalidated the path returned by annotate().
    shape = cmds.listRelatives(transform, shapes=True, fullPath=True)[0]
    cmds.setAttr(f"{shape}.overrideEnabled", 1)
    # 2 = reference: visible, and unpickable -- without this, riggers grab the
    # label instead of the guide.
    cmds.setAttr(f"{shape}.overrideDisplayType", 2)
    cmds.setAttr(f"{shape}.overrideColor", MARKER_COLOR)


def guide_label_nodes(node) -> list[str]:
    """The annotation transforms under a guide, long names.

    The Designer's Labels toggle hides these; a joint guide's label is an
    attribute and is toggled directly.
    """
    found = []
    for child in cmds.listRelatives(node.long_name, children=True, fullPath=True) or []:
        shapes = cmds.listRelatives(child, shapes=True, fullPath=True) or []
        if any(cmds.nodeType(shape) == "annotationShape" for shape in shapes):
            found.append(child)
    return found
```

- [ ] **Step 4: Call it from `create_guide_node`**

In `create_guide_node`, immediately before `return node`:

```python
    label_guide(node, kind, tag_role or role, module.side.value)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `make tests-integration`
Expected: PASS, including the pre-existing guide tests — the annotation carries no `trg_kind`, so no scan sees it.

- [ ] **Step 6: Commit**

```bash
git add -A src/python/tik/trigger/guides tests
git commit -m "feat(trigger): guides carry labels

A joint guide takes Maya's native drawLabel; a reference guide is a transform
with no such attribute and takes an annotation parented at zero offset, so its
leader collapses to a stub instead of a line across the scene. The text is the
qualified role, so five finger copies read index_root and thumb_root rather
than five guides all reading root.

The annotation is unpickable and carries no trg_kind, so no scan sees it."
```

---

### Task 4: `.trg` import rebuilds by kind

**Files:**
- Modify: `src/python/tik/trigger/guides/exchange.py:144-170`
- Test: `tests/unit/test_guides_trigger.py` (extend)

**Interfaces:**
- Consumes: `nodes.make_guide_shell`, `nodes.guide_color`, `nodes.label_guide`, `GuideLayout.kind_for`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_guides_trigger.py`:

```python
def test_trg_round_trip_rebuilds_a_reference_guide_as_a_locator(tmp_path, guide_scene):
    """A kind is not stored in the file — it is read back off the module."""
    handle = guide_scene.create("toy_reference", name="toy", side="L")
    guide_scene.draw([handle.instance_id])
    path = guide_scene.export_trg(tmp_path / "toy.trg", [handle.instance_id])
    guide_scene.delete_guides([handle.instance_id])
    guide_scene.import_trg(path)

    rebuilt = guide_scene.guide_nodes(guide_scene.modules()[0].instance_id)
    assert cmds.nodeType(rebuilt[("aim", 0)].long_name) == "transform"
    assert cmds.nodeType(rebuilt[("rail", 0)].long_name) == "joint"
    assert cmds.getAttr(f"{rebuilt[('rail', 0)].long_name}.radius") == 0.5
```

**Note for the implementer:** `export_trg` / `import_trg` / `delete_guides` / `modules()` are guesses — read the real names off the existing tests in this file and match them. What the test asserts must not change.

- [ ] **Step 2: Run it to verify it fails**

Run: `mayapy -m pytest tests/unit/test_guides_trigger.py -v -k trg_round_trip_rebuilds`
Expected: FAIL — `assert 'joint' == 'transform'`

- [ ] **Step 3: Branch the importer on kind**

In `src/python/tik/trigger/guides/exchange.py`, replace the creation block inside `import_guide_instances` (the `joint = tm.Joint.create(...)` through `joint.color = ...` lines):

```python
                layout = module_cls.guides
                for (role, index), record in guide_instance.joints.items():
                    kind = layout.kind_for(role, is_root=(role == layout.root))
                    joint = nodes.make_guide_shell(record["name"], kind)
                    joint.world_position = record["position"]
                    if kind is not GuideKind.REFERENCE:
                        # jointOrient exists only on a joint; a reference guide
                        # carries its orientation in `rotate` alone.
                        joint.joint_orient = record.get("joint_orient", (0, 0, 0))
                    joint.rotate = tuple(record.get("rotation", (0, 0, 0)))
                    # The record's colour and radius are advisory: the kind
                    # decides, so a file written before a module changed a
                    # role's kind still reads back correctly.
                    joint.color = nodes.guide_color(kind, module.side.value)
```

Leave the `attrs_for_role` loop, the `joint.meta.update(...)` call and the bookkeeping that follows exactly as they are, then add immediately after `joints[(role, index)] = joint`:

```python
                    nodes.label_guide(joint, kind, role, module.side.value)
```

Add `from tik.trigger.core.manifest import GuideKind` to the file's imports.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `make tests-unit`
Expected: PASS — the new test plus every existing `.trg` test.

- [ ] **Step 5: Commit**

```bash
git add -A src/python/tik/trigger/guides tests
git commit -m "feat(trigger): .trg import rebuilds guides by kind

The kind is not stored in the file. It is read back off the module class, so
a file written before a role changed kind still imports correctly, and the
stored radius and colour become advisory."
```

---

### Task 5: The preset fan

**Files:**
- Modify: `src/python/tik/trigger/core/module.py:836-861` (`_draw_pivot_guides`)
- Test: `tests/integration/trigger/test_guide_kinds_trigger.py` (extend)

**Interfaces:**
- Consumes: `GuideDraft.chain_step` and `GuideDraft.reference` (Task 2).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_guide_kinds_trigger.py`:

```python
def test_preset_markers_never_share_a_position(trigger_session):
    handle = trigger_session.guides.create("arm", name="arm", side="L")
    trigger_session.guides.draw([handle.instance_id])
    positions = [
        tuple(round(value, 4) for value in node.world_position)
        for (role, _index), node in trigger_session.guides.guide_nodes(
            handle.instance_id
        ).items()
        if role.startswith("pivot_")
    ]
    assert len(positions) == 3
    assert len(set(positions)) == 3


def test_preset_markers_fan_along_the_anchor_chain(trigger_session):
    """Each marker is further from the elbow than the last, in row order."""
    handle = trigger_session.guides.create("arm", name="arm", side="L")
    trigger_session.guides.draw([handle.instance_id])
    found = trigger_session.guides.guide_nodes(handle.instance_id)
    elbow = found[("elbow", 0)].world_position
    ordered = [
        found[(f"pivot_ik_{label}", 0)].world_position
        for label in ("wrist", "ball", "tip")
    ]
    distances = [
        sum((a - b) ** 2 for a, b in zip(point, elbow)) for point in ordered
    ]
    assert distances == sorted(distances)
```

- [ ] **Step 2: Run to verify it fails**

Run: `mayapy -m pytest tests/integration/trigger/test_guide_kinds_trigger.py -v -k preset`
Expected: FAIL — `assert 1 == 3` (all three markers share the anchor's position)

- [ ] **Step 3: Implement the fan**

In `src/python/tik/trigger/core/module.py`, replace `_draw_pivot_guides` with:

```python
    def _draw_pivot_guides(self, draft) -> None:
        """One marker guide per pivot-preset row, fanned off its anchor.

        The markers step along the anchor's own incoming chain direction, in
        table order, so an arm's wrist/ball/tip run along the hand's forward
        axis -- the direction a roll actually travels. They used to stack on
        the anchor so that an unplaced preset looked unplaced; three markers
        in one pixel are not selectable, and unselectable is worse.

        Parenting is unchanged: moving the anchor still carries its presets.
        """
        settings = self.values()
        placed: dict[str, int] = {}  # control -> markers already fanned
        for row in self.pivot_rows(settings):
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            anchor_ref = type(self).pivot_anchor(control, settings)
            # Through ``made``, which qualifies with the copy currently
            # drawing: a bare lookup finds the first copy's anchor whichever
            # copy is asking.
            anchor = draft.made(*anchor_ref) if anchor_ref else None
            if anchor is None:
                continue  # a stale row; Module.warnings() reports it
            rank = placed.get(control, 0)
            placed[control] = rank + 1
            direction, step = draft.chain_step(anchor)
            origin = tuple(anchor.world_position)
            position = tuple(
                value + axis * (rank + 1) * step
                for value, axis in zip(origin, direction)
            )
            draft.reference(
                f"pivot_{control}_{label}", position, parent=anchor
            )
```

- [ ] **Step 4: Run to verify it passes**

Run: `make tests-integration`
Expected: PASS, including `test_pivot_build_trigger.py` and `test_pivot_trigger.py` — the fan changes where a marker sits, never which pivots get built.

The `test_preset_markers_fan_along_the_anchor_chain` test will still FAIL until Task 6 reorders the arm's default rows. That is expected — note it and continue.

- [ ] **Step 5: Commit**

```bash
git add -A src/python/tik/trigger/core tests
git commit -m "feat(trigger): pivot preset markers fan instead of stacking

Each marker steps along its anchor's own incoming chain direction, so an
arm's presets run along the hand's forward axis. Parenting is unchanged --
moving the anchor still carries its presets along."
```

---

### Task 6: The arm's A-pose, and the module declarations

**Files:**
- Modify: `src/python/tik/trigger/modules/arm/arm.py:56,76-78,173-186`
- Modify: `src/python/tik/trigger/modules/twist/twist.py:~60` (the `guides` declaration)
- Test: `tests/integration/trigger/test_guide_kinds_trigger.py` (extend)

**Interfaces:**
- Consumes: `GuideLayout(reference=..., driven=...)` (Task 1).
- Produces: nothing new.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_guide_kinds_trigger.py`:

```python
def test_the_arm_draws_an_a_pose(trigger_session):
    handle = trigger_session.guides.create("arm", name="arm", side="L")
    trigger_session.guides.draw([handle.instance_id])
    found = trigger_session.guides.guide_nodes(handle.instance_id)
    shoulder = found[("shoulder", 0)].world_position
    hand = found[("hand", 0)].world_position
    # the hand hangs below the shoulder: a T-pose would leave them level
    assert hand[1] < shoulder[1] - 1.0


def test_the_arm_keeps_its_elbow_behind_the_chain(trigger_session):
    """A rotation about Z does not change Z, so the pole offset survives."""
    handle = trigger_session.guides.create("arm", name="arm", side="L")
    trigger_session.guides.draw([handle.instance_id])
    elbow = trigger_session.guides.guide_nodes(handle.instance_id)[("elbow", 0)]
    assert round(elbow.world_position[2], 3) == -1.0


def test_the_arms_neutral_is_a_reference_guide(trigger_session):
    handle = trigger_session.guides.create("arm", name="arm", side="L")
    trigger_session.guides.draw([handle.instance_id])
    node = trigger_session.guides.guide_nodes(handle.instance_id)[("neutral", 0)]
    assert cmds.nodeType(node.long_name) == "transform"


def test_the_twist_rails_are_driven_guides(trigger_session):
    handle = trigger_session.guides.create("twist", name="twist", side="L")
    trigger_session.guides.draw([handle.instance_id])
    found = trigger_session.guides.guide_nodes(handle.instance_id)
    rails = [node for (role, _index), node in found.items() if role == "twist"]
    assert rails
    for node in rails:
        assert cmds.nodeType(node.long_name) == "joint"
        assert cmds.getAttr(f"{node.long_name}.radius") == 0.5
```

- [ ] **Step 2: Run to verify they fail**

Run: `mayapy -m pytest tests/integration/trigger/test_guide_kinds_trigger.py -v -k "a_pose or neutral or twist_rails"`
Expected: FAIL — `assert 0.0 < -1.0` on the A-pose test.

- [ ] **Step 3: Declare the arm's reference guide and reorder its presets**

In `src/python/tik/trigger/modules/arm/arm.py`, line 56:

```python
    guides = GuideLayout(
        "collar", "shoulder", "elbow", "hand", "neutral", reference=("neutral",)
    )
```

and lines 76-78:

```python
    pivot_presets = Module.pivot_presets.with_default(
        [{"control": "ik", "label": label} for label in ("wrist", "ball", "tip")]
    )
```

- [ ] **Step 4: Draw the A-pose**

Replace `Arm.draw_guides` (lines 173-186) with:

```python
    def draw_guides(self, guides) -> None:
        """Collar, then an A-pose arm: the chain hangs 45 degrees below level.

        A-pose rather than T: it gives the better shoulder deformation, which
        is what modern rigs are built to. The collar stays level -- a clavicle
        is roughly horizontal in any pose -- so the A starts at the shoulder.

        The elbow's -1 in Z survives the rotation untouched, because turning
        about Z does not change Z. The pole direction stays behind the arm
        with no compensation.
        """
        mult = guides.side_mult
        collar = guides.joint("collar", (2 * mult, 0, 0))
        shoulder = guides.joint("shoulder", (5 * mult, 0, 0), parent=collar)
        elbow = guides.joint("elbow", (7.8 * mult, -2.8, -1), parent=shoulder)
        guides.joint("hand", (11.4 * mult, -6.4, 0), parent=elbow)
        # Where the wrist sits when the collar is at rest -- the auto-collar's
        # zero. Only the direction from `collar` matters, so sitting past the
        # hand costs nothing and keeps the guide selectable. It rides the same
        # A-pose ray as the arm, so it still means what its name says.
        guides.joint("neutral", (15.2 * mult, -9.0, 0), parent=collar)
```

- [ ] **Step 5: Declare twist's driven guides**

In `src/python/tik/trigger/modules/twist/twist.py`, change the `guides = GuideLayout(...)` line to add `driven=("twist",)`. For example, if it currently reads `GuideLayout("base", "end", multi="twist", min=1)`, it becomes:

```python
    guides = GuideLayout("base", "end", multi="twist", min=1, driven=("twist",))
```

Read the real current declaration and add only the `driven=` argument — do not change its roles, `multi`, `min` or `max`.

- [ ] **Step 6: Run the full suite**

Run: `make tests-unit && make tests-integration`
Expected: PASS, including `test_preset_markers_fan_along_the_anchor_chain` from Task 5, which needed this row reorder.

Watch `tests/integration/trigger/test_arm_*` and the auto-collar tests: the neutral guide moved, so any test asserting a hard-coded auto-collar angle will need its expected value updated. **Update the expectation, not the module** — the A-pose is the intended change. If a test asserts a *relationship* (for example that the collar lifts when the arm rises) it should still pass untouched; if one of those fails, stop, because that is a real regression.

- [ ] **Step 7: Commit**

```bash
git add -A src/python/tik/trigger/modules tests
git commit -m "feat(trigger): the arm draws an A-pose, and declares its kinds

45 degrees below level from the shoulder down; the collar stays level. The
elbow's -1 in Z survives untouched because turning about Z does not change Z,
so the pole direction needs no compensation, and the neutral guide rides the
same ray so it still means what its docstring says.

neutral is a reference guide, twist's rails are driven, and the arm's preset
rows are reordered proximal-to-distal so the fan lands anatomically."
```

---

### Task 7: The Labels toggle

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py` (add `set_labels_visible`)
- Modify: `src/python/tik/trigger/ui/designer/action_bar.py:28-95`
- Modify: `src/python/tik/trigger/ui/designer/commands.py` (wire the signal)
- Modify: `src/python/tik/trigger/config/pages/guides.py` (one field)
- Test: `tests/ui/test_designer_labels.py` (create)

**Interfaces:**
- Consumes: `nodes.guide_label_nodes` (Task 3).
- Produces:
  - `GuideScene.set_labels_visible(on: bool, instance_ids=None) -> None`
  - `DesignerActionBar.labels_toggled = QtCore.Signal(bool)`, `DesignerActionBar.labels_check`
  - `DesignerActionBar.set_labels(on: bool) -> None`
  - `GuidesPrefs.show_guide_labels: BoolField`

- [ ] **Step 1: Write the failing UI test**

Create `tests/ui/test_designer_labels.py`:

```python
"""The Designer's Labels toggle.

A view operation, not a preference read at draw time: `trigger/guides` may not
import the preferences packages, so Draw always writes labels on and this
button turns them off afterwards.
"""

from __future__ import annotations

from tik.trigger.ui.designer.action_bar import DesignerActionBar


def test_the_bar_has_a_labels_toggle(qtbot):
    bar = DesignerActionBar()
    qtbot.addWidget(bar)
    assert bar.labels_check.text() == "Labels"


def test_toggling_emits_its_state(qtbot):
    bar = DesignerActionBar()
    qtbot.addWidget(bar)
    seen = []
    bar.labels_toggled.connect(seen.append)
    bar.labels_check.setChecked(False)
    assert seen == [False]


def test_set_labels_does_not_re_emit(qtbot):
    """Restoring the saved state must not look like a user toggle."""
    bar = DesignerActionBar()
    qtbot.addWidget(bar)
    seen = []
    bar.labels_toggled.connect(seen.append)
    bar.set_labels(False)
    assert seen == []


def test_the_toggle_sits_in_the_scene_group(qtbot):
    """Labels change the scene, so the bar must place it left of the stretch."""
    bar = DesignerActionBar()
    qtbot.addWidget(bar)
    layout = bar.layout()
    order = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert order.index(bar.labels_check) < order.index(bar.sync_button)
```

**Note for the implementer:** check how the other UI tests build widgets — if the suite does not use `pytest-qt`'s `qtbot`, follow whatever `tests/ui/test_copy_tabs.py` does instead and drop the fixture.

- [ ] **Step 2: Run to verify it fails**

Run: `make tests-ui`
Expected: FAIL — `AttributeError: 'DesignerActionBar' object has no attribute 'labels_check'`

- [ ] **Step 3: Add the toggle to the bar**

In `src/python/tik/trigger/ui/designer/action_bar.py`, add the signal next to the others:

```python
    labels_toggled = QtCore.Signal(bool)
```

After the `mirror_button` is added to the layout (line 61) and before `layout.addStretch(1)`:

```python
        self.labels_check = QtWidgets.QCheckBox("Labels")
        self.labels_check.setChecked(True)
        self.labels_check.setToolTip(
            "Show each guide's name in the viewport. "
            "Turn off on dense modules, where labels overlap."
        )
        layout.addWidget(self.labels_check)
```

Wire it with the other connections:

```python
        self.labels_check.toggled.connect(self.labels_toggled)
```

And add the setter beside `set_auto_sync`:

```python
    def set_labels(self, on: bool) -> None:
        """Restore the saved state without it reading as a user toggle."""
        blocked = self.labels_check.blockSignals(True)
        self.labels_check.setChecked(bool(on))
        self.labels_check.blockSignals(blocked)
```

- [ ] **Step 4: Add the scene operation**

In `src/python/tik/trigger/guides/scene.py`, add a method to `GuideScene` (match the file's own style for how it resolves instance ids — copy the pattern from `select_guides` or `sync`):

```python
    def set_labels_visible(self, on: bool, instance_ids=None) -> None:
        """Show or hide every drawn guide's label.

        A view operation over what is already drawn, never a change to the
        document. Two node kinds, one switch: a joint guide's label is an
        attribute, a reference guide's is an annotation transform.
        """
        for instance_id in instance_ids or [
            entry.instance_id for entry in self.document.modules
        ]:
            for node in self.guide_nodes(instance_id).values():
                if node["drawLabel"].exists:
                    node["drawLabel"].value = bool(on)
                for label in nodes.guide_label_nodes(node):
                    cmds.setAttr(f"{label}.visibility", bool(on))
```

**Note for the implementer:** `plug.exists` is a guess at the tik.maya API for "does this attribute exist". Find the real spelling (grep `tik/maya` for an existence check on a plug) — a reference guide is a transform and genuinely has no `drawLabel`, so this guard is load-bearing.

- [ ] **Step 5: Wire the signal**

In `src/python/tik/trigger/ui/designer/commands.py`, connect the bar's signal alongside the existing `auto_sync_toggled` wiring (see line ~433 for the pattern):

```python
        self.action_bar.labels_toggled.connect(self._on_labels_toggled)
```

and add the handler:

```python
    def _on_labels_toggled(self, on: bool) -> None:
        """Flip the labels in the scene and remember the choice."""
        self.scene.set_labels_visible(on)
        prefs.set("guides", "show_guide_labels", bool(on))
```

Match how the file already reads and writes preferences — copy the pattern used for `auto_sync`, including its import of `prefs`. Read the saved default when the Designer builds its bar, next to wherever `set_auto_sync` is called:

```python
        self.action_bar.set_labels(prefs.get("guides", "show_guide_labels"))
```

- [ ] **Step 6: Add the preference**

In `src/python/tik/trigger/config/pages/guides.py`, add inside the `AUTHORING` group:

```python
    show_guide_labels = BoolField(
        True,
        group=AUTHORING,
        label="Show guide labels",
        help=(
            "Show each guide's name in the viewport. Guides are always drawn "
            "with labels; this is the Designer toggle's starting state."
        ),
    )
```

- [ ] **Step 7: Run everything**

Run: `make tests-ui && make tests-unit && make tests-integration`
Expected: PASS. In particular `tests/unit/test_import_boundaries.py` must still pass — the preference is read in `trigger/ui` only, and `trigger/guides` imports nothing from the preferences packages.

- [ ] **Step 8: Commit**

```bash
git add -A src/python/tik/trigger tests
git commit -m "feat(trigger): a Labels toggle in the Designer bar

Draw always writes labels on, because trigger/guides may not read
preferences -- a preference can never change what Draw renders. Turning them
off is a view operation over what is already drawn, and the saved default
lives in trigger/ui, which may read prefs.

One switch, two node kinds: an attribute on a joint, a visibility on an
annotation."
```

---

### Task 8: Sweep and documentation

**Files:**
- Modify: `CLAUDE.md` (the tik.trigger status paragraph)
- Modify: `AI/coding_rules.md` (the Module Ground Rules section, if it names `radius`)

- [ ] **Step 1: Check for stragglers**

```bash
grep -rn "create_guide_joint\|_style_as_marker\|marker=True" src/python tests
grep -rn "radius=" src/python/tik/trigger/modules src/python/tik/trigger/systems
grep -rn 'type="joint"' src/python/tik/trigger
```

Expected: no hits for the first two greps. The third should show only places that genuinely mean joints (the build path, `bind_joint` lookups) — not the guide scans.

- [ ] **Step 2: Run lint and the whole suite**

```bash
make lint
make tests-unit && make tests-integration && make tests-ui
```

Expected: clean, and all green.

- [ ] **Step 3: Update `CLAUDE.md`**

In the `tik.trigger` status paragraph, add after the sentence about `guide_attrs`:

> A guide has a **kind** — `ROOT` and `JOINT` derived from the structure `draw_guides` builds, `REFERENCE` and `DRIVEN` declared on `GuideLayout` — and the kind is the only thing that decides its radius, colour, shape, bone-drawing and label, in one table in `guides/nodes.py`. A `REFERENCE` guide is a locator transform, not a joint, which is the only way to suppress a bone without suppressing its siblings; module code never names a radius. The arm draws an A-pose, and pivot preset markers fan along their anchor's chain direction instead of stacking on it.

Add the spec to the design-specs list:

> `docs/superpowers/specs/2026-09-12-guide-kinds-and-readability-design.md` (guide kinds: the four-value vocabulary, what is derived and what is declared, the measured Maya bone-drawing behaviour that forces a reference guide to be a transform, labels per kind, the A-pose and the preset fan; **amends the movable-pivots and draw/sync specs**)

And add to the tests list:

> `tests/unit/test_guide_kinds_trigger.py` — the kind vocabulary and its validation (pure); `tests/integration/trigger/test_guide_kinds_trigger.py` — what each kind renders as, labels, and the preset fan; `tests/ui/test_designer_labels.py` — the Labels toggle

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md AI/coding_rules.md
git commit -m "docs: record the guide kind vocabulary"
```

---

## Notes for the executor

**Where the plan is guessing.** Tasks 2, 3, 4 and 7 contain test code that calls session and scene APIs by names taken from the spec rather than verified against the codebase (`trigger_session`, `guide_scene`, `export_trg`, `handle.copies`, `plug.exists`). Each of those steps flags it. **Fix the call to match the real API; never weaken what the test asserts.** If an assertion cannot be expressed against the real API, stop and say so rather than deleting it.

**Where the plan expects a red test.** Task 5's `test_preset_markers_fan_along_the_anchor_chain` fails until Task 6 reorders the arm's preset rows. That is the only planned cross-task red.

**The auto-collar expectations.** Moving the `neutral` guide changes the auto-collar's zero, so integration tests asserting hard-coded collar angles will need new expected values. Tests asserting a *relationship* should not move; if one does, it is a real regression — stop.
