# Guide Ownership and Lockstep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every guide fact exactly one durable home in a uuid-keyed guide document, make guide joints a rebuildable rendering of it, and keep scene and document in lockstep so deleting a joint in Maya can never destroy a module.

**Architecture:** A pure-Python `GuideDocument` (modules, connections, layout, poses, guide attrs — all keyed by instance uuid) is the durable home. A pure `reconcile()` compares it with a scene snapshot and returns a diff that separates *pose drift* (resolved by **capture**, scene wins) from *structural staleness* (resolved by **regenerate**, document wins). In the Maya scene the document lives on one node per module instance, so Maya's undo covers it. Lockstep is a thin policy that consumes the diff automatically.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), pytest, tik.maya, PySide (Qt) for the Designer.

**Spec:** `docs/superpowers/specs/2026-08-31-guide-ownership-and-lockstep-design.md`

This plan covers **items 1–5** of spec §9 (ownership and lockstep, entirely within the guide layer). Items 6–7 (guides into the `.tr`, Designer under the session tabs) are a separate plan written after this substrate has been lived with.

## Global Constraints

- **Layering:** `tik/trigger/core` is pure Python — no `maya`, no `tik.maya`, no Qt, no `tik.shared`. Enforced by `tests/unit/test_import_boundaries.py`. Tasks 1–2 add files to `core` and MUST respect this.
- **Consume tik.maya:** no raw `maya.cmds` / `OpenMaya` / `pymel` outside `tik.maya`, except the scene-scanning primitives `tik/trigger/guides/nodes.py` already reaches for (documented exception in spec §5.3 of the simplification design). New OpenMaya callback code in `tik/trigger/maya/observer.py` is a deliberate, documented exception — Maya exposes no `scriptJob` equivalent.
- **No third-party deps.** Stdlib and Maya-bundled modules only.
- **No backward compatibility.** The tool is unreleased. Do not write migration shims for scenes carrying `trg_settings` / `trg_inputs` on root guides, and do not add `.trg` version negotiation.
- **Modules never inherit from other modules.** Shared behaviour goes in `tik/trigger/systems/`.
- **Identity is the instance uuid, never a name.** Every new dict, connection source and layout entry is keyed by `instance_id`.
- **Test command (single file/test):**
  `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/<file>.py -q`
  (`tests/unit/invoke.py` hardcodes the whole directory and ignores argv, so call pytest directly when running one file.)
- **Test command (full unit suite):** `make tests-unit`
- **Naming convention:** tik.trigger tests are `test_<module>_trigger.py`.

---

### Task 1: The guide document schema (pure)

The durable home for every guide fact. Pure data — no Maya, no registry lookups at read time. The document stores *which guides a module should have*, so `reconcile` in Task 2 never needs the module registry to know what to expect.

**Files:**
- Create: `src/python/tik/trigger/core/guide_document.py`
- Test: `tests/unit/test_guide_document_trigger.py`

**Interfaces:**
- Consumes: `GuideLayout` from `tik.trigger.core.manifest` (for `expand_guides` only).
- Produces:
  - `GuideRecord(role, index=0, position=None, rotation=None, rotate_order=0, joint_orient=(0,0,0), radius=1.0, color=17, attrs={}, parent=None)`; `.pair -> tuple[str, int]`; `.posed -> bool`; `.to_dict()`; `.from_dict(data)`
  - `ModuleEntry(instance_id, module_type, name, side="C", settings={}, inputs={}, guides=[])`; `.key -> str`; `.pairs -> list[tuple[str,int]]`; `.guide(role, index=0) -> Optional[GuideRecord]`; `.to_dict()`; `.from_dict(data)`
  - `SceneGroup(group_id, name, nodes=[])`; `.to_dict()`; `.from_dict(data)`
  - `GuideDocument(schema=1, modules=[], scene_groups=[], positions={}, collapse={})`; `.module(instance_id)`; `.by_key(key)`; `.group(group_id)`; `.to_dict()`; `.from_dict(data)`
  - `expand_guides(entry, layout, count) -> None`
  - `SCHEMA_VERSION = 1`
- Note for later tasks: a connection source is `"<instance_id>.<output>"` for a module, or a bare Maya node name for a scene node. `core.schemas.split_source` still splits it correctly — Maya node names cannot contain `.`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_guide_document_trigger.py`:

```python
"""The pure guide document: records, entries, serialization, guide expansion."""

import pytest

from tik.trigger.core.guide_document import (
    SCHEMA_VERSION,
    GuideDocument,
    GuideRecord,
    ModuleEntry,
    SceneGroup,
    expand_guides,
)
from tik.trigger.core.manifest import GuideLayout


def test_record_pair_and_posed():
    unposed = GuideRecord(role="root")
    assert unposed.pair == ("root", 0)
    assert unposed.posed is False
    posed = GuideRecord(role="segment", index=2, position=(1.0, 2.0, 3.0))
    assert posed.pair == ("segment", 2)
    assert posed.posed is True


def test_entry_key_follows_side():
    assert ModuleEntry("id1", "arm", "arm", "L").key == "L_arm"
    assert ModuleEntry("id2", "spine", "spine", "C").key == "spine"


def test_entry_guide_lookup():
    entry = ModuleEntry(
        "id1", "fkchain", "tail", "C",
        guides=[GuideRecord("root"), GuideRecord("segment", 1)],
    )
    assert entry.guide("segment", 1).index == 1
    assert entry.guide("segment", 9) is None
    assert entry.pairs == [("root", 0), ("segment", 1)]


def test_document_round_trip_preserves_everything():
    document = GuideDocument(
        modules=[
            ModuleEntry(
                "id1", "arm", "arm", "L",
                settings={"segments": 3},
                inputs={"root": "id2.hand"},
                guides=[GuideRecord("root", position=(1.0, 0.0, 0.0), attrs={"twistWeight": 0.5})],
            )
        ],
        scene_groups=[SceneGroup("g1", "sceneNodes1", ["some_jnt"])],
        positions={"id1": [10.0, 20.0]},
        collapse={"id1": 2},
    )
    restored = GuideDocument.from_dict(document.to_dict())
    assert restored.schema == SCHEMA_VERSION
    entry = restored.module("id1")
    assert entry.key == "L_arm"
    assert entry.settings == {"segments": 3}
    assert entry.inputs == {"root": "id2.hand"}
    assert entry.guide("root").position == (1.0, 0.0, 0.0)
    assert entry.guide("root").attrs == {"twistWeight": 0.5}
    assert restored.group("g1").nodes == ["some_jnt"]
    assert restored.positions == {"id1": [10.0, 20.0]}
    assert restored.collapse == {"id1": 2}


def test_document_by_key():
    document = GuideDocument(modules=[ModuleEntry("id1", "arm", "arm", "L")])
    assert document.by_key("L_arm").instance_id == "id1"
    assert document.by_key("nope") is None


def test_from_dict_rejects_newer_schema():
    with pytest.raises(ValueError, match="newer than supported"):
        GuideDocument.from_dict({"schema": SCHEMA_VERSION + 1})


def test_expand_guides_grows_keeping_existing_poses():
    layout = GuideLayout("root", multi="segment", min=1, max=50)
    entry = ModuleEntry(
        "id1", "fkchain", "tail", "C",
        guides=[
            GuideRecord("root", position=(0.0, 0.0, 0.0)),
            GuideRecord("segment", 0, position=(5.0, 0.0, 0.0)),
            GuideRecord("segment", 1, position=(10.0, 0.0, 0.0)),
        ],
    )
    expand_guides(entry, layout, 4)
    assert entry.pairs == [("root", 0), ("segment", 0), ("segment", 1), ("segment", 2), ("segment", 3)]
    # survivors keep their authored poses
    assert entry.guide("segment", 0).position == (5.0, 0.0, 0.0)
    assert entry.guide("segment", 1).position == (10.0, 0.0, 0.0)
    # new ones are unposed, so regenerate places them at their draw_guides pose
    assert entry.guide("segment", 2).posed is False
    assert entry.guide("segment", 3).posed is False


def test_expand_guides_shrinks():
    layout = GuideLayout("root", multi="segment", min=1, max=50)
    entry = ModuleEntry(
        "id1", "fkchain", "tail", "C",
        guides=[GuideRecord("root"), GuideRecord("segment", 0), GuideRecord("segment", 1)],
    )
    expand_guides(entry, layout, 1)
    assert entry.pairs == [("root", 0), ("segment", 0)]


def test_expand_guides_keeps_fixed_roles():
    layout = GuideLayout("collar", "shoulder", "elbow", "hand")
    entry = ModuleEntry(
        "id1", "arm", "arm", "L",
        guides=[GuideRecord("collar", position=(1.0, 0.0, 0.0))],
    )
    expand_guides(entry, layout, 0)
    assert entry.pairs == [("collar", 0), ("shoulder", 0), ("elbow", 0), ("hand", 0)]
    assert entry.guide("collar").position == (1.0, 0.0, 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_guide_document_trigger.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.core.guide_document'`

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/trigger/core/guide_document.py`:

```python
"""The guide document: every guide fact, keyed by instance uuid.

Pure data. The document — not the scene — is the durable home for which
modules exist, what they are connected to, where their guides sit, and what
the Guide Designer laid out. Guide joints in Maya are a *rendering* of this,
owned by it and rebuildable from it.

A connection source is ``"<instance_id>.<output>"`` for a module, or a bare
Maya node name for a scene node; ``core.schemas.split_source`` splits both,
because Maya node names cannot contain a dot.

An unposed ``GuideRecord`` (``position is None``) means "no authored pose
yet" — regenerate places it wherever the module's ``draw_guides`` puts it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

SCHEMA_VERSION = 1


def _triple(value, default=(0.0, 0.0, 0.0)):
    return default if value is None else tuple(float(item) for item in value)


@dataclass
class GuideRecord:
    """One guide joint's durable data."""

    role: str
    index: int = 0
    #: ``None`` means "never authored"; regenerate uses the draw_guides pose.
    position: Optional[tuple] = None
    rotation: Optional[tuple] = None
    rotate_order: int = 0
    joint_orient: tuple = (0.0, 0.0, 0.0)
    radius: float = 1.0
    color: int = 17
    #: Values of the module's declared ``guide_attrs`` for this guide.
    attrs: dict = field(default_factory=dict)
    #: ``(role, index)`` of this guide's parent *within the same module*.
    parent: Optional[tuple] = None

    @property
    def pair(self) -> tuple:
        return (self.role, self.index)

    @property
    def posed(self) -> bool:
        """True once a pose has been captured or imported for this guide."""
        return self.position is not None

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "index": self.index,
            "position": list(self.position) if self.position is not None else None,
            "rotation": list(self.rotation) if self.rotation is not None else None,
            "rotate_order": self.rotate_order,
            "joint_orient": list(self.joint_orient),
            "radius": self.radius,
            "color": self.color,
            "attrs": dict(self.attrs),
            "parent": list(self.parent) if self.parent else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GuideRecord":
        parent = data.get("parent")
        position = data.get("position")
        rotation = data.get("rotation")
        return cls(
            role=data["role"],
            index=int(data.get("index", 0)),
            position=None if position is None else _triple(position),
            rotation=None if rotation is None else _triple(rotation),
            rotate_order=int(data.get("rotate_order", 0)),
            joint_orient=_triple(data.get("joint_orient")),
            radius=float(data.get("radius", 1.0)),
            color=int(data.get("color", 17)),
            attrs={key: float(value) for key, value in (data.get("attrs") or {}).items()},
            parent=(str(parent[0]), int(parent[1])) if parent else None,
        )


@dataclass
class ModuleEntry:
    """One module instance: identity, settings, connections and its guides."""

    instance_id: str
    module_type: str
    name: str
    side: str = "C"
    settings: dict = field(default_factory=dict)
    #: ``{input name: "<instance_id>.<output>" | "<scene node>"}``
    inputs: dict = field(default_factory=dict)
    guides: list = field(default_factory=list)

    @property
    def key(self) -> str:
        """Display key: ``L_arm`` / ``spine``. Never an identity — that is the uuid."""
        return self.name if self.side in ("C", "") else f"{self.side}_{self.name}"

    @property
    def pairs(self) -> list:
        return [record.pair for record in self.guides]

    def guide(self, role: str, index: int = 0) -> Optional[GuideRecord]:
        for record in self.guides:
            if record.role == role and record.index == index:
                return record
        return None

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "module_type": self.module_type,
            "name": self.name,
            "side": self.side,
            "settings": dict(self.settings),
            "inputs": dict(self.inputs),
            "guides": [record.to_dict() for record in self.guides],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleEntry":
        return cls(
            instance_id=data["instance_id"],
            module_type=data["module_type"],
            name=data.get("name", data["module_type"]),
            side=data.get("side", "C"),
            settings=dict(data.get("settings") or {}),
            inputs=dict(data.get("inputs") or {}),
            guides=[GuideRecord.from_dict(item) for item in data.get("guides", [])],
        )


@dataclass
class SceneGroup:
    """A named bag of arbitrary Maya nodes modules can connect to."""

    group_id: str
    name: str
    nodes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"group_id": self.group_id, "name": self.name, "nodes": list(self.nodes)}

    @classmethod
    def from_dict(cls, data: dict) -> "SceneGroup":
        return cls(
            group_id=data["group_id"],
            name=data.get("name", data["group_id"]),
            nodes=list(data.get("nodes") or []),
        )


@dataclass
class GuideDocument:
    """Every guide fact for one rig. Keyed by uuid throughout."""

    schema: int = SCHEMA_VERSION
    modules: list = field(default_factory=list)
    scene_groups: list = field(default_factory=list)
    #: Graph node positions, keyed by instance_id or group_id.
    positions: dict = field(default_factory=dict)
    #: Graph collapse modes, keyed by instance_id or group_id.
    collapse: dict = field(default_factory=dict)

    def module(self, instance_id: str) -> Optional[ModuleEntry]:
        for entry in self.modules:
            if entry.instance_id == instance_id:
                return entry
        return None

    def by_key(self, key: str) -> Optional[ModuleEntry]:
        """Look up by display key. For UI convenience only — never for storage."""
        for entry in self.modules:
            if entry.key == key:
                return entry
        return None

    def group(self, group_id: str) -> Optional[SceneGroup]:
        for entry in self.scene_groups:
            if entry.group_id == group_id:
                return entry
        return None

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "modules": [entry.to_dict() for entry in self.modules],
            "scene_groups": [entry.to_dict() for entry in self.scene_groups],
            "positions": {key: list(value) for key, value in self.positions.items()},
            "collapse": dict(self.collapse),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GuideDocument":
        schema = int(data.get("schema", SCHEMA_VERSION))
        if schema > SCHEMA_VERSION:
            raise ValueError(
                f"Guide document schema {schema} is newer than supported {SCHEMA_VERSION}."
            )
        return cls(
            schema=SCHEMA_VERSION,
            modules=[ModuleEntry.from_dict(item) for item in data.get("modules", [])],
            scene_groups=[SceneGroup.from_dict(item) for item in data.get("scene_groups", [])],
            positions={key: list(value) for key, value in (data.get("positions") or {}).items()},
            collapse={key: int(value) for key, value in (data.get("collapse") or {}).items()},
        )


def expand_guides(entry: ModuleEntry, layout, count: int) -> None:
    """Match ``entry.guides`` to ``layout.expand(count)``, keeping authored poses.

    This is the document-side answer to a settings change that adds or removes
    guides (``fkchain.segments`` 3 -> 5). Survivors keep their records untouched;
    new pairs arrive unposed so regenerate places them at their ``draw_guides``
    position rather than at the origin.
    """
    existing = {record.pair: record for record in entry.guides}
    entry.guides = [
        existing.get(pair) or GuideRecord(role=pair[0], index=pair[1])
        for pair in layout.expand(count)
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_guide_document_trigger.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: Verify the layering rule still holds**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_import_boundaries.py -q`
Expected: PASS — `guide_document.py` imports only `dataclasses` and `typing`.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/core/guide_document.py tests/unit/test_guide_document_trigger.py
git commit -m "feat(tik.trigger): the pure guide document schema"
```

---

### Task 2: Reconcile — document versus scene (pure)

The comparison that tells lockstep what to do. Its whole job is to separate the two kinds of drift so they can never be confused: **pose drift is resolved by capture (scene wins), structural staleness by regenerate (document wins)**. A regenerate triggered by pose drift would teleport a guide away from where the rigger just dragged it.

Pure and registry-free: the document already records which guides a module should have, so nothing here needs to instantiate a module class.

**Files:**
- Create: `src/python/tik/trigger/core/reconcile.py`
- Test: `tests/unit/test_reconcile_trigger.py`

**Interfaces:**
- Consumes: `GuideDocument`, `ModuleEntry`, `GuideRecord` from Task 1.
- Produces:
  - `RenderedGuide(instance_id, role, index, node, position=(0,0,0), rotation=(0,0,0), rotate_order=0, attrs={}, parent=None)`; `.pair`
  - `ModuleDiff(instance_id, absent=False, missing=[], unexpected=[], drifted=[], parent_wrong=False)`; `.needs_regenerate -> bool`; `.needs_capture -> bool`; `.is_clean -> bool`
  - `GuideDiff(modules={}, orphans=[], duplicates=[])`; `.structural -> list[str]`; `.drifted -> list[str]`; `.is_clean -> bool`
  - `reconcile(document, rendered, tolerance=POSE_TOLERANCE, primary_input_of=None) -> GuideDiff`
  - `POSE_TOLERANCE = 1e-5`
- `primary_input_of` is `entry -> input name`, used to find which module a *root* guide should hang under. Omitted (the default) skips the root-parent check — that is what unit tests without a registry want; `GuideScene.diff()` (Task 9) supplies the real one.
- `rendered` is a flat `list[RenderedGuide]` — the Maya side builds it in Task 7; nothing here touches Maya.
- `RenderedGuide.parent` is `(instance_id, role, index)` of the DAG parent guide, or `None` for a guide parented to the holder. For a module's **root** guide this is the *inter-module* parent, and reconcile compares it against the module's primary input; for non-root guides it is the intra-module parent from the record.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_reconcile_trigger.py`:

```python
"""Reconcile: what the document says versus what the scene renders."""

from tik.trigger.core.guide_document import GuideDocument, GuideRecord, ModuleEntry
from tik.trigger.core.reconcile import RenderedGuide, reconcile


def entry(instance_id="id1", **kwargs):
    kwargs.setdefault("module_type", "fkchain")
    kwargs.setdefault("name", "tail")
    kwargs.setdefault("side", "C")
    kwargs.setdefault("guides", [
        GuideRecord("root", position=(0.0, 0.0, 0.0)),
        GuideRecord("segment", 0, position=(5.0, 0.0, 0.0), parent=("root", 0)),
    ])
    return ModuleEntry(instance_id, **kwargs)


def rendered(instance_id="id1", pairs=(("root", 0), ("segment", 0)), positions=None):
    positions = positions or {("root", 0): (0.0, 0.0, 0.0), ("segment", 0): (5.0, 0.0, 0.0)}
    parents = {("root", 0): None, ("segment", 0): (instance_id, "root", 0)}
    return [
        RenderedGuide(
            instance_id=instance_id, role=role, index=index,
            node=f"{role}{index}_guide",
            position=positions[(role, index)],
            parent=parents.get((role, index)),
        )
        for role, index in pairs
    ]


def test_clean_document_and_scene_agree():
    diff = reconcile(GuideDocument(modules=[entry()]), rendered())
    assert diff.is_clean
    assert diff.structural == []
    assert diff.drifted == []


def test_module_with_nothing_rendered_is_absent():
    diff = reconcile(GuideDocument(modules=[entry()]), [])
    assert diff.modules["id1"].absent is True
    assert diff.structural == ["id1"]
    assert diff.drifted == []


def test_deleted_guide_is_missing_and_structural():
    diff = reconcile(GuideDocument(modules=[entry()]), rendered(pairs=(("root", 0),)))
    module = diff.modules["id1"]
    assert module.missing == [("segment", 0)]
    assert module.needs_regenerate is True
    assert diff.structural == ["id1"]


def test_extra_rendered_guide_is_unexpected_and_structural():
    scene = rendered() + [
        RenderedGuide("id1", "segment", 1, "segment1_guide", position=(9.0, 0.0, 0.0))
    ]
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    assert diff.modules["id1"].unexpected == [("segment", 1)]
    assert diff.structural == ["id1"]


def test_moved_guide_is_drift_not_structural():
    """The rigger dragged the elbow. Capture must win; regenerate must not run."""
    scene = rendered(positions={("root", 0): (0.0, 0.0, 0.0), ("segment", 0): (7.5, 1.0, 0.0)})
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    module = diff.modules["id1"]
    assert module.drifted == [("segment", 0)]
    assert module.needs_capture is True
    assert module.needs_regenerate is False
    assert diff.structural == []
    assert diff.drifted == ["id1"]


def test_changed_guide_attr_is_drift():
    document = GuideDocument(modules=[entry(guides=[
        GuideRecord("root", position=(0.0, 0.0, 0.0), attrs={"twistWeight": 0.5}),
    ])])
    scene = [RenderedGuide("id1", "root", 0, "root_guide",
                           position=(0.0, 0.0, 0.0), attrs={"twistWeight": 0.9})]
    diff = reconcile(document, scene)
    assert diff.modules["id1"].drifted == [("root", 0)]
    assert diff.structural == []


def test_unposed_record_is_reported_so_capture_claims_it():
    """A guide the document has no pose for yet must be captured, not redrawn."""
    document = GuideDocument(modules=[entry(guides=[GuideRecord("root")])])
    scene = [RenderedGuide("id1", "root", 0, "root_guide", position=(3.0, 3.0, 3.0))]
    diff = reconcile(document, scene)
    assert diff.modules["id1"].drifted == [("root", 0)]


def test_tiny_float_difference_is_not_drift():
    scene = rendered(positions={("root", 0): (0.0, 0.0, 0.0), ("segment", 0): (5.0 + 1e-9, 0.0, 0.0)})
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    assert diff.modules["id1"].drifted == []


def test_wrong_intra_module_parent_is_structural():
    scene = rendered()
    scene[1] = RenderedGuide("id1", "segment", 0, "segment0_guide",
                             position=(5.0, 0.0, 0.0), parent=None)
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    assert diff.modules["id1"].parent_wrong is True
    assert diff.structural == ["id1"]


def test_root_parent_follows_the_primary_input():
    """The DAG is a rendering of the primary input connection (spec 4.4)."""
    document = GuideDocument(modules=[
        entry("child", inputs={"root": "parent.end"}),
        entry("parent", name="spine", guides=[GuideRecord("root", position=(0.0, 0.0, 0.0))]),
    ])
    scene = rendered("child") + [
        RenderedGuide("parent", "root", 0, "spine_root_guide", position=(0.0, 0.0, 0.0))
    ]
    # child's root is parented to nothing, but should hang under parent's guide
    diff = reconcile(document, scene, primary_input_of=lambda entry: "root")
    assert diff.modules["child"].parent_wrong is True
    assert "child" in diff.structural


def test_orphan_joints_are_reported_never_regenerated():
    scene = rendered() + [RenderedGuide("ghost", "root", 0, "ghost_root_guide")]
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    assert diff.orphans == ["ghost_root_guide"]
    assert diff.structural == []
    assert diff.is_clean is False


def test_maya_duplicate_reports_duplicates_not_a_merge():
    """Duplicating a hierarchy copies trg_instance; the copies must not merge."""
    scene = rendered() + [
        RenderedGuide("id1", "root", 0, "root_guide1", position=(0.0, 0.0, 0.0)),
        RenderedGuide("id1", "segment", 0, "segment0_guide1", position=(5.0, 0.0, 0.0)),
    ]
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    assert sorted(diff.duplicates) == ["root_guide1", "segment0_guide1"]
    assert diff.modules["id1"].needs_regenerate is False


def test_empty_document_and_empty_scene_is_clean():
    assert reconcile(GuideDocument(), []).is_clean
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_reconcile_trigger.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.core.reconcile'`

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/trigger/core/reconcile.py`:

```python
"""Reconcile the guide document against what the Maya scene renders.

Pure comparison — no Maya, no writes, no registry. The document records which
guides a module should have, so nothing here instantiates a module class.

The output separates the two kinds of drift, and the separation is the point:

===============================  ==========  ===============
Drift                            Resolved by  Winner
===============================  ==========  ===============
pose / guide attr differs        capture      the scene
absent, missing, unexpected,     regenerate   the document
  wrong parent
orphans, duplicates              reported     nothing
===============================  ==========  ===============

A regenerate triggered by pose drift would teleport a guide away from where the
rigger just dragged it, so ``needs_regenerate`` deliberately ignores ``drifted``.
Orphans and duplicates are never acted on automatically: they may be a rigger's
scratch work, and destroying untracked scene content is not a repair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .guide_document import GuideDocument

POSE_TOLERANCE = 1e-5


@dataclass
class RenderedGuide:
    """One guide joint as the scene currently has it."""

    instance_id: str
    role: str
    index: int
    #: Opaque scene identifier (a long name). Reported, never parsed.
    node: str
    position: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0)
    rotate_order: int = 0
    attrs: dict = field(default_factory=dict)
    #: ``(instance_id, role, index)`` of the DAG parent guide, or None.
    parent: Optional[tuple] = None

    @property
    def pair(self) -> tuple:
        return (self.role, self.index)


@dataclass
class ModuleDiff:
    """How one module's rendering differs from its document entry."""

    instance_id: str
    absent: bool = False
    missing: list = field(default_factory=list)
    unexpected: list = field(default_factory=list)
    drifted: list = field(default_factory=list)
    parent_wrong: bool = False

    @property
    def needs_regenerate(self) -> bool:
        """Structural staleness only. Never true merely because a guide moved."""
        return bool(self.absent or self.missing or self.unexpected or self.parent_wrong)

    @property
    def needs_capture(self) -> bool:
        return bool(self.drifted)

    @property
    def is_clean(self) -> bool:
        return not self.needs_regenerate and not self.needs_capture


@dataclass
class GuideDiff:
    """The whole comparison."""

    modules: dict = field(default_factory=dict)
    orphans: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)

    @property
    def structural(self) -> list:
        """Instance ids whose rendering must be rebuilt."""
        return [key for key, diff in self.modules.items() if diff.needs_regenerate]

    @property
    def drifted(self) -> list:
        """Instance ids whose poses must be captured."""
        return [key for key, diff in self.modules.items() if diff.needs_capture]

    @property
    def is_clean(self) -> bool:
        return not self.structural and not self.drifted and not self.orphans and not self.duplicates


def _same(left, right, tolerance: float) -> bool:
    if left is None or right is None:
        return left is right
    return all(abs(float(a) - float(b)) <= tolerance for a, b in zip(left, right))


def reconcile(
    document: GuideDocument,
    rendered: list,
    tolerance: float = POSE_TOLERANCE,
    primary_input_of: Optional[Callable] = None,
) -> GuideDiff:
    """Compare ``document`` with a flat list of :class:`RenderedGuide`.

    Args:
        document: The durable guide document.
        rendered: What the scene currently draws.
        tolerance: Float slack before a pose counts as drifted.
        primary_input_of: ``entry -> input name`` used to find the module a root
            guide should hang under. Omitted (the default) skips the root-parent
            check, which is what unit tests without a registry want.
    """
    diff = GuideDiff()
    by_instance: dict = {}
    for guide in rendered:
        by_instance.setdefault(guide.instance_id, []).append(guide)

    known = {entry.instance_id for entry in document.modules}
    for instance_id, guides in by_instance.items():
        if instance_id not in known:
            diff.orphans.extend(guide.node for guide in guides)

    for entry in document.modules:
        module_diff = ModuleDiff(entry.instance_id)
        guides = by_instance.get(entry.instance_id, [])
        if not guides:
            module_diff.absent = True
            diff.modules[entry.instance_id] = module_diff
            continue

        # A Maya-duplicate copies trg_instance, so several nodes can claim one
        # pair. The first wins; the rest are duplicates and are only reported.
        seen: dict = {}
        for guide in guides:
            if guide.pair in seen:
                diff.duplicates.append(guide.node)
            else:
                seen[guide.pair] = guide

        expected = {record.pair: record for record in entry.guides}
        module_diff.missing = [pair for pair in expected if pair not in seen]
        module_diff.unexpected = [pair for pair in seen if pair not in expected]

        root_pair = entry.guides[0].pair if entry.guides else None
        primary_source = None
        if primary_input_of is not None:
            name = primary_input_of(entry)
            primary_source = entry.inputs.get(name) if name else None

        for pair, record in expected.items():
            guide = seen.get(pair)
            if guide is None:
                continue
            if (
                not record.posed
                or not _same(record.position, guide.position, tolerance)
                or not _same(record.rotation, guide.rotation, tolerance)
                or record.rotate_order != guide.rotate_order
                or record.attrs != guide.attrs
            ):
                module_diff.drifted.append(pair)
            if pair == root_pair:
                if primary_source is not None:
                    expected_id, _dot, _output = primary_source.rpartition(".")
                    actual_id = guide.parent[0] if guide.parent else None
                    if expected_id and expected_id != actual_id:
                        module_diff.parent_wrong = True
            elif record.parent is not None:
                want = (entry.instance_id, record.parent[0], record.parent[1])
                if guide.parent != want:
                    module_diff.parent_wrong = True

        module_diff.missing.sort()
        module_diff.unexpected.sort()
        module_diff.drifted.sort()
        diff.modules[entry.instance_id] = module_diff

    return diff
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_reconcile_trigger.py -q`
Expected: PASS (13 tests)

- [ ] **Step 5: Verify the layering rule still holds**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_import_boundaries.py -q`
Expected: PASS

- [ ] **Step 6: Export both new modules from the core package**

Modify `src/python/tik/trigger/core/__init__.py` — add to the imports and `__all__`:

```python
from .guide_document import (
    GuideDocument,
    GuideRecord,
    ModuleEntry,
    SceneGroup,
    expand_guides,
)
from .reconcile import GuideDiff, ModuleDiff, RenderedGuide, reconcile
```

and add `"GuideDocument"`, `"GuideRecord"`, `"ModuleEntry"`, `"SceneGroup"`, `"expand_guides"`, `"GuideDiff"`, `"ModuleDiff"`, `"RenderedGuide"`, `"reconcile"` to `__all__`.

- [ ] **Step 7: Run the whole unit suite**

Run: `make tests-unit`
Expected: PASS — no existing test touched.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/core/reconcile.py tests/unit/test_reconcile_trigger.py src/python/tik/trigger/core/__init__.py
git commit -m "feat(tik.trigger): reconcile the guide document against the scene"
```

---

*Tasks 3–13 follow the same TDD shape. They are written out below in the same
detail; each is independently testable and ends in a commit.*

### Task 3: Module document nodes in the scene

The scene-side home for a `ModuleEntry`: one node per module instance, carrying scalar settings as real Maya attributes (so the channel box and the existing two-way bindings keep working) and the rest of the entry as `trg_*` meta. This node — not the root guide joint — is the module's durable identity, so deleting guides cannot destroy it.

**Files:**
- Create: `src/python/tik/trigger/guides/module_node.py`
- Modify: `src/python/tik/trigger/maya/tags.py` (add keys)
- Test: `tests/unit/test_module_node_trigger.py`

**Interfaces:**
- Consumes: `ModuleEntry`, `GuideRecord` (Task 1); `tik.maya` as `tm`; `tik.maya.attribute`.
- Produces:
  - `MODULE_NODES_GRP = "trigger_modules_grp"`
  - `holder() -> tm.Transform` — the group every module node hangs under
  - `create(entry, module) -> tm.Transform` — make the node, write meta, sync setting attrs
  - `read(node) -> ModuleEntry`
  - `write(node, entry, module=None) -> None`
  - `find(instance_id) -> Optional[tm.Transform]`
  - `find_all() -> list[tm.Transform]`
  - `remove(instance_id) -> None`
  - `settings_plug(instance_id, field_name)` — plug for two-way binding
- New tags in `maya/tags.py`: `MODULE_NODE = "trg_module_node"` (kind value `"module_node"`), `ENTRY = "trg_entry"` (the serialized `ModuleEntry` dict minus the scalar settings mirrored as attributes).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_module_node_trigger.py`:

```python
"""Module document nodes: the scene-side home of a ModuleEntry."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core.guide_document import GuideRecord, ModuleEntry
from tik.trigger.core import registry
from tik.trigger.guides import module_node


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def make_entry(instance_id="id1"):
    return ModuleEntry(
        instance_id, "fkchain", "tail", "C",
        settings={"segments": 3, "spacing": 5.0},
        inputs={"root": "other.end"},
        guides=[GuideRecord("root", position=(0.0, 0.0, 0.0))],
    )


def test_create_makes_one_node_under_the_holder():
    entry = make_entry()
    module = registry.get_module("fkchain")(instance_id="id1", name="tail", settings=entry.settings)
    node = module_node.create(entry, module)
    assert node.parent.name == module_node.MODULE_NODES_GRP
    assert module_node.find("id1").long_name == node.long_name


def test_round_trip_preserves_the_entry():
    entry = make_entry()
    module = registry.get_module("fkchain")(instance_id="id1", name="tail", settings=entry.settings)
    node = module_node.create(entry, module)
    restored = module_node.read(node)
    assert restored.instance_id == "id1"
    assert restored.module_type == "fkchain"
    assert restored.name == "tail"
    assert restored.inputs == {"root": "other.end"}
    assert restored.settings["segments"] == 3
    assert restored.guide("root").position == (0.0, 0.0, 0.0)


def test_scalar_settings_become_real_attributes():
    entry = make_entry()
    module = registry.get_module("fkchain")(instance_id="id1", name="tail", settings=entry.settings)
    node = module_node.create(entry, module)
    assert node.has_attr("segments")
    assert node["segments"].value == 3
    plug = module_node.settings_plug("id1", "segments")
    assert plug is not None


def test_deleting_guide_joints_leaves_the_module_node_alone():
    """The whole point: guides are a rendering, the node is the identity."""
    entry = make_entry()
    module = registry.get_module("fkchain")(instance_id="id1", name="tail", settings=entry.settings)
    module_node.create(entry, module)
    joint = cmds.joint(name="some_guide")
    cmds.delete(joint)
    assert module_node.find("id1") is not None
    assert module_node.read(module_node.find("id1")).name == "tail"


def test_remove_deletes_the_node():
    entry = make_entry()
    module = registry.get_module("fkchain")(instance_id="id1", name="tail", settings=entry.settings)
    module_node.create(entry, module)
    module_node.remove("id1")
    assert module_node.find("id1") is None


def test_find_all_returns_every_module_node():
    for index in range(3):
        entry = make_entry(f"id{index}")
        module = registry.get_module("fkchain")(
            instance_id=f"id{index}", name=f"tail{index}", settings=entry.settings
        )
        module_node.create(entry, module)
    assert len(module_node.find_all()) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_module_node_trigger.py -q`
Expected: FAIL — `ImportError: cannot import name 'module_node'`

- [ ] **Step 3: Add the new tags**

Modify `src/python/tik/trigger/maya/tags.py` — add after `DESIGNER`:

```python
MODULE_NODE = "module_node"  # KIND value for a module document node
ENTRY = "trg_entry"  # serialized ModuleEntry (module document node only)
DOCUMENT = "trg_document"  # scene_groups / positions / collapse (holder only)
```

- [ ] **Step 4: Write the implementation**

Create `src/python/tik/trigger/guides/module_node.py`:

```python
"""Module document nodes: one scene node per module instance.

This node is the module's durable identity. Scalar settings live on it as real
Maya attributes, so the channel box and the Designer's two-way bindings work
against it exactly as they used to work against the root guide joint; the rest
of the ``ModuleEntry`` is a meta dict. Guide joints hold no structural data any
more, so deleting them can never destroy a module.
"""

from __future__ import annotations

from typing import Optional

import tik.maya as tm
from maya import cmds
from tik.maya import attribute
from tik.trigger.core.guide_document import ModuleEntry
from tik.trigger.maya import tags

MODULE_NODES_GRP = "trigger_modules_grp"

#: Field kinds with no sensible single-attribute form; they live only in meta.
_NON_SCALAR = ("list", "dict", "vector", "table")


def holder() -> tm.Transform:
    """The group every module document node hangs under."""
    if cmds.objExists(MODULE_NODES_GRP):
        return tm.Transform(MODULE_NODES_GRP)
    node = tm.Transform.create(name=MODULE_NODES_GRP)
    node.meta[tags.KIND] = "module_holder"
    return node


def create(entry: ModuleEntry, module=None) -> tm.Transform:
    """Create the document node for ``entry`` and write it."""
    node = tm.Transform.create(name=f"{entry.key}_module", parent=holder().long_name)
    node.meta[tags.KIND] = tags.MODULE_NODE
    node.meta[tags.INSTANCE] = entry.instance_id
    write(node, entry, module)
    return node


def write(node, entry: ModuleEntry, module=None) -> None:
    """Store ``entry`` on ``node``: meta for everything, attributes for scalars."""
    node.meta[tags.MODULE] = entry.module_type
    node.meta[tags.INSTANCE] = entry.instance_id
    node.meta[tags.NAME] = entry.name
    node.meta[tags.SIDE] = entry.side
    node.meta[tags.ENTRY] = entry.to_dict()
    if module is not None:
        _sync_setting_attrs(node, module)


def read(node) -> ModuleEntry:
    """Rebuild the ``ModuleEntry`` stored on ``node``."""
    entry = ModuleEntry.from_dict(dict(node.meta[tags.ENTRY]))
    # Attributes win over the meta copy: the channel box is an authoring surface.
    for name in list(entry.settings):
        if node.has_attr(name):
            entry.settings[name] = node[name].value
    return entry


def find(instance_id: str):
    """The document node for ``instance_id``, or None."""
    for node in find_all():
        if node.meta.get(tags.INSTANCE) == instance_id:
            return node
    return None


def find_all() -> list:
    """Every module document node in the scene."""
    found = []
    for name in cmds.ls(f"*.{tm.META_PREFIX}{tags.KIND}", long=True, objectsOnly=True) or []:
        node = tm.resolve(name)
        if node.meta.get(tags.KIND) == tags.MODULE_NODE:
            found.append(node)
    return found


def remove(instance_id: str) -> None:
    node = find(instance_id)
    if node is not None and node.exists():
        cmds.delete(node.long_name)


def settings_plug(instance_id: str, field_name: str):
    """Plug backing a module property, for the Designer's two-way binding."""
    node = find(instance_id)
    if node is None or not node.has_attr(field_name):
        return None
    return node[field_name]


def _sync_setting_attrs(node, module) -> None:
    """Mirror the module's scalar fields as real attributes on ``node``."""
    for name, field_obj in module.fields().items():
        value = getattr(module, name)
        kind = field_obj.type_name
        if kind in _NON_SCALAR:
            continue
        if not node.has_attr(name):
            if kind == "bool":
                attribute.add_bool(node, name, default=bool(value))
            elif kind == "int":
                attribute.add_int(node, name, default=int(value), min=field_obj.min, max=field_obj.max)
            elif kind == "float":
                attribute.add_float(node, name, default=float(value), min=field_obj.min, max=field_obj.max)
            elif kind == "choice":
                attribute.add_enum(
                    node, name, [str(item) for item in field_obj.choices],
                    default=field_obj.choices.index(value),
                )
            else:
                attribute.add_string(node, name)
        if kind == "choice":
            node[name].value = field_obj.choices.index(value)
        elif kind in ("string", "file", "node"):
            node[name].value = str(value)
        else:
            node[name].value = value
```

- [ ] **Step 5: Export it from the guides package**

Modify `src/python/tik/trigger/guides/__init__.py` — add `from . import module_node` and include `"module_node"` in `__all__`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_module_node_trigger.py -q`
Expected: PASS (6 tests)

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/guides/module_node.py src/python/tik/trigger/maya/tags.py src/python/tik/trigger/guides/__init__.py tests/unit/test_module_node_trigger.py
git commit -m "feat(tik.trigger): module document nodes own module identity"
```

---

### Task 4: The scene document — read and write the whole GuideDocument

Assemble a `GuideDocument` from the module nodes plus the holder's document meta, and write one back. This is the bridge between Task 1's pure schema and the scene.

**Files:**
- Create: `src/python/tik/trigger/guides/document_store.py`
- Test: `tests/unit/test_document_store_trigger.py`

**Interfaces:**
- Consumes: `module_node` (Task 3), `GuideDocument`, `SceneGroup` (Task 1).
- Produces:
  - `read_document() -> GuideDocument`
  - `write_document(document) -> None`
  - `read_entry(instance_id) -> Optional[ModuleEntry]`
  - `write_entry(entry, module=None) -> None`
  - `remove_entry(instance_id) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_document_store_trigger.py`:

```python
"""The scene-side GuideDocument: module nodes plus holder layout."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core.guide_document import GuideDocument, GuideRecord, ModuleEntry, SceneGroup
from tik.trigger.core import registry
from tik.trigger.guides import document_store


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def fkchain(instance_id, name):
    entry = ModuleEntry(
        instance_id, "fkchain", name, "C",
        settings={"segments": 3},
        guides=[GuideRecord("root", position=(0.0, 0.0, 0.0))],
    )
    module = registry.get_module("fkchain")(
        instance_id=instance_id, name=name, settings=entry.settings
    )
    return entry, module


def test_empty_scene_reads_an_empty_document():
    document = document_store.read_document()
    assert document.modules == []
    assert document.scene_groups == []


def test_write_then_read_round_trips():
    entry, module = fkchain("id1", "tail")
    document = GuideDocument(
        modules=[entry],
        scene_groups=[SceneGroup("g1", "sceneNodes1", ["some_jnt"])],
        positions={"id1": [5.0, 6.0]},
        collapse={"id1": 1},
    )
    document_store.write_document(document, modules={"id1": module})
    restored = document_store.read_document()
    assert restored.module("id1").name == "tail"
    assert restored.module("id1").settings["segments"] == 3
    assert restored.group("g1").nodes == ["some_jnt"]
    assert restored.positions == {"id1": [5.0, 6.0]}
    assert restored.collapse == {"id1": 1}


def test_write_document_removes_entries_no_longer_present():
    first, first_module = fkchain("id1", "tail")
    second, second_module = fkchain("id2", "antenna")
    document_store.write_document(
        GuideDocument(modules=[first, second]),
        modules={"id1": first_module, "id2": second_module},
    )
    document_store.write_document(GuideDocument(modules=[first]), modules={"id1": first_module})
    restored = document_store.read_document()
    assert [entry.instance_id for entry in restored.modules] == ["id1"]


def test_single_entry_write_and_read():
    entry, module = fkchain("id1", "tail")
    document_store.write_entry(entry, module)
    assert document_store.read_entry("id1").name == "tail"
    document_store.remove_entry("id1")
    assert document_store.read_entry("id1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_document_store_trigger.py -q`
Expected: FAIL — `ImportError: cannot import name 'document_store'`

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/trigger/guides/document_store.py`:

```python
"""Read and write the whole ``GuideDocument`` in the Maya scene.

Module entries live one per document node (:mod:`.module_node`); the scene-node
groups and the Designer's graph layout live on the guide holder, because they
belong to the document as a whole rather than to any one module.

Everything here is a plain scene write, so Maya's undo covers the document the
same way it covers a joint move.
"""

from __future__ import annotations

from typing import Optional

import tik.maya as tm
from maya import cmds
from tik.trigger.core.guide_document import GuideDocument, ModuleEntry, SceneGroup
from tik.trigger.maya import tags

from . import module_node, nodes


def read_document() -> GuideDocument:
    """Assemble the document from the scene."""
    document = GuideDocument(
        modules=[module_node.read(node) for node in module_node.find_all()]
    )
    document.modules.sort(key=lambda entry: entry.name)
    if cmds.objExists(tags.GUIDE_HOLDER):
        stored = dict(tm.Transform(tags.GUIDE_HOLDER).meta.get(tags.DOCUMENT, {}) or {})
        document.scene_groups = [
            SceneGroup.from_dict(item) for item in stored.get("scene_groups", [])
        ]
        document.positions = {
            key: list(value) for key, value in (stored.get("positions") or {}).items()
        }
        document.collapse = {
            key: int(value) for key, value in (stored.get("collapse") or {}).items()
        }
    return document


def write_document(document: GuideDocument, modules: Optional[dict] = None) -> None:
    """Store ``document``, removing module nodes it no longer contains.

    Args:
        document: The document to store.
        modules: ``{instance_id: Module}`` for entries whose scalar settings
            should be re-mirrored as attributes. Entries absent from it keep the
            attributes they already have.
    """
    modules = modules or {}
    with nodes.undo_chunk("Trigger write guide document"):
        wanted = {entry.instance_id for entry in document.modules}
        for node in module_node.find_all():
            if node.meta.get(tags.INSTANCE) not in wanted:
                cmds.delete(node.long_name)
        for entry in document.modules:
            write_entry(entry, modules.get(entry.instance_id))
        nodes.holder().meta[tags.DOCUMENT] = {
            "scene_groups": [group.to_dict() for group in document.scene_groups],
            "positions": {key: list(value) for key, value in document.positions.items()},
            "collapse": dict(document.collapse),
        }


def read_entry(instance_id: str) -> Optional[ModuleEntry]:
    node = module_node.find(instance_id)
    return module_node.read(node) if node is not None else None


def write_entry(entry: ModuleEntry, module=None) -> None:
    """Create or update one module's document node."""
    node = module_node.find(entry.instance_id)
    if node is None:
        module_node.create(entry, module)
    else:
        module_node.write(node, entry, module)


def remove_entry(instance_id: str) -> None:
    module_node.remove(instance_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_document_store_trigger.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/guides/document_store.py tests/unit/test_document_store_trigger.py
git commit -m "feat(tik.trigger): read and write the guide document in the scene"
```

---

### Task 5: Snapshot the scene as RenderedGuides

The Maya half of reconcile's input. Scans guide joints and produces the pure `RenderedGuide` list Task 2 consumes.

**Files:**
- Create: `src/python/tik/trigger/guides/snapshot.py`
- Test: `tests/unit/test_snapshot_trigger.py`

**Interfaces:**
- Consumes: `RenderedGuide` (Task 2); `nodes` (existing); `tags`.
- Produces: `snapshot() -> list[RenderedGuide]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_snapshot_trigger.py`:

```python
"""Scanning guide joints into pure RenderedGuide records."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.guides import snapshot
from tik.trigger.maya import tags


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def tagged_joint(name, instance, role, index=0, parent=None, position=(0, 0, 0)):
    cmds.select(clear=True)
    if parent:
        cmds.select(parent)
    joint = cmds.joint(name=name)
    cmds.xform(joint, worldSpace=True, translation=position)
    import tik.maya as tm
    node = tm.Joint(joint)
    node.meta.update({
        tags.KIND: tags.GUIDE, tags.MODULE: "fkchain", tags.INSTANCE: instance,
        tags.ROLE: role, tags.INDEX: index, tags.SIDE: "C",
    })
    return joint


def test_empty_scene_snapshots_nothing():
    assert snapshot.snapshot() == []


def test_snapshot_reports_identity_and_pose():
    tagged_joint("root_guide", "id1", "root", position=(1.0, 2.0, 3.0))
    found = snapshot.snapshot()
    assert len(found) == 1
    guide = found[0]
    assert guide.instance_id == "id1"
    assert guide.pair == ("root", 0)
    assert guide.position == pytest.approx((1.0, 2.0, 3.0))
    assert guide.parent is None


def test_snapshot_reports_the_dag_parent_as_a_guide_triple():
    root = tagged_joint("root_guide", "id1", "root")
    tagged_joint("seg_guide", "id1", "segment", 0, parent=root, position=(5.0, 0.0, 0.0))
    by_pair = {guide.pair: guide for guide in snapshot.snapshot()}
    assert by_pair[("segment", 0)].parent == ("id1", "root", 0)


def test_untagged_joints_are_ignored():
    cmds.joint(name="just_a_joint")
    assert snapshot.snapshot() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_snapshot_trigger.py -q`
Expected: FAIL — `ImportError: cannot import name 'snapshot'`

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/trigger/guides/snapshot.py`:

```python
"""Scan the scene's guide joints into pure ``RenderedGuide`` records.

The Maya half of reconcile's input. Everything Maya-shaped stops here; what
comes out is plain data :mod:`tik.trigger.core.reconcile` can compare without
importing Maya.
"""

from __future__ import annotations

import tik.maya as tm
from maya import cmds
from tik.trigger.core.reconcile import RenderedGuide
from tik.trigger.maya import tags


def _guide_triple(node) -> tuple:
    """``(instance_id, role, index)`` for a guide joint."""
    return (
        node.meta[tags.INSTANCE],
        node.meta.get(tags.ROLE, ""),
        int(node.meta.get(tags.INDEX, 0)),
    )


def snapshot() -> list:
    """Every tagged guide joint in the scene, as pure records."""
    found = []
    # cmds rather than tik.maya: one attribute-qualified ls finds every tagged
    # joint without walking the DAG. This runs on every refresh.
    for name in cmds.ls(
        f"*.{tm.META_PREFIX}{tags.KIND}", long=True, objectsOnly=True, type="joint"
    ) or []:
        node = tm.resolve(name)
        data = node.meta.as_dict()
        if data.get(tags.KIND) != tags.GUIDE or tags.INSTANCE not in data:
            continue
        parent = node.parent
        parent_triple = None
        if parent is not None and parent.meta.get(tags.KIND) == tags.GUIDE:
            parent_triple = _guide_triple(parent)
        attrs = {}
        for attr_name in cmds.listAttr(node.long_name, userDefined=True) or []:
            if attr_name.startswith(tm.META_PREFIX):
                continue
            try:
                attrs[attr_name] = float(cmds.getAttr(f"{node.long_name}.{attr_name}"))
            except (ValueError, RuntimeError):
                continue
        found.append(
            RenderedGuide(
                instance_id=data[tags.INSTANCE],
                role=data.get(tags.ROLE, ""),
                index=int(data.get(tags.INDEX, 0)),
                node=node.long_name,
                position=tuple(
                    cmds.xform(node.long_name, query=True, worldSpace=True, translation=True)
                ),
                rotation=tuple(
                    cmds.xform(node.long_name, query=True, worldSpace=True, rotation=True)
                ),
                rotate_order=int(cmds.getAttr(f"{node.long_name}.rotateOrder")),
                attrs=attrs,
                parent=parent_triple,
            )
        )
    return found
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_snapshot_trigger.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/guides/snapshot.py tests/unit/test_snapshot_trigger.py
git commit -m "feat(tik.trigger): snapshot guide joints as pure records"
```

---

### Task 6: Capture — scene into document, additively

The scene → document direction. Three rules from spec §4.2, all load-bearing: **additive** (a missing joint leaves its stored pose alone — this is what makes deleting a joint lossless), **undo-safe**, and **never inside a regenerate**.

**Files:**
- Create: `src/python/tik/trigger/guides/capture.py`
- Test: `tests/unit/test_capture_trigger.py`

**Interfaces:**
- Consumes: `snapshot` (Task 5), `document_store` (Task 4), `GuideDocument`.
- Produces: `capture(document, rendered=None) -> bool` — mutates `document` in place, returns True when anything changed.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_capture_trigger.py`:

```python
"""Capture: poses and guide attrs flow from the scene into the document."""

from tik.trigger.core.guide_document import GuideDocument, GuideRecord, ModuleEntry
from tik.trigger.core.reconcile import RenderedGuide
from tik.trigger.guides.capture import capture


def document():
    return GuideDocument(modules=[ModuleEntry(
        "id1", "fkchain", "tail", "C",
        guides=[GuideRecord("root", position=(0.0, 0.0, 0.0)),
                GuideRecord("segment", 0, position=(5.0, 0.0, 0.0))],
    )])


def test_capture_updates_a_moved_guide():
    doc = document()
    changed = capture(doc, [RenderedGuide("id1", "segment", 0, "n", position=(7.0, 1.0, 0.0))])
    assert changed is True
    assert doc.module("id1").guide("segment", 0).position == (7.0, 1.0, 0.0)


def test_capture_is_additive_a_deleted_guide_keeps_its_pose():
    """The rule that makes deleting a joint lossless."""
    doc = document()
    capture(doc, [RenderedGuide("id1", "root", 0, "n", position=(0.0, 0.0, 0.0))])
    assert doc.module("id1").guide("segment", 0).position == (5.0, 0.0, 0.0)


def test_capture_never_drops_a_record():
    doc = document()
    capture(doc, [])
    assert doc.module("id1").pairs == [("root", 0), ("segment", 0)]


def test_capture_records_guide_attrs():
    doc = document()
    capture(doc, [RenderedGuide("id1", "root", 0, "n", position=(0.0, 0.0, 0.0),
                                attrs={"twistWeight": 0.25})])
    assert doc.module("id1").guide("root").attrs == {"twistWeight": 0.25}


def test_capture_marks_an_unposed_record_as_posed():
    doc = GuideDocument(modules=[ModuleEntry(
        "id1", "fkchain", "tail", "C", guides=[GuideRecord("root")],
    )])
    capture(doc, [RenderedGuide("id1", "root", 0, "n", position=(2.0, 0.0, 0.0))])
    record = doc.module("id1").guide("root")
    assert record.posed is True
    assert record.position == (2.0, 0.0, 0.0)


def test_capture_ignores_guides_of_unknown_modules():
    doc = document()
    assert capture(doc, [RenderedGuide("ghost", "root", 0, "n", position=(1.0, 1.0, 1.0))]) is False


def test_capture_reports_no_change_when_nothing_moved():
    doc = document()
    scene = [RenderedGuide("id1", "root", 0, "n", position=(0.0, 0.0, 0.0)),
             RenderedGuide("id1", "segment", 0, "n2", position=(5.0, 0.0, 0.0))]
    assert capture(doc, scene) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_capture_trigger.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.guides.capture'`

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/trigger/guides/capture.py`:

```python
"""Capture: the scene's poses and guide attrs, into the document.

Three rules, all load-bearing (spec 4.2):

1. **Additive.** Only records for joints that exist are updated. A missing
   joint leaves its stored pose alone — this single rule is what makes deleting
   a guide joint lossless rather than a race.
2. **Undo-safe.** Callers persist the result inside the undo chunk of whatever
   operation triggered them, or not at all; capture itself only mutates Python.
3. **Never inside a regenerate**, or it captures a half-built rendering.

Pure apart from the optional scene read, so it unit-tests without Maya.
"""

from __future__ import annotations

from typing import Optional

from tik.trigger.core.guide_document import GuideDocument


def capture(document: GuideDocument, rendered: Optional[list] = None) -> bool:
    """Fold the scene's poses and guide attrs into ``document``.

    Args:
        document: Mutated in place.
        rendered: A ``RenderedGuide`` list; read from the scene when omitted.

    Returns:
        True when anything changed.
    """
    if rendered is None:
        from .snapshot import snapshot

        rendered = snapshot()

    by_instance: dict = {}
    for guide in rendered:
        by_instance.setdefault(guide.instance_id, {})[guide.pair] = guide

    changed = False
    for entry in document.modules:
        found = by_instance.get(entry.instance_id)
        if not found:
            continue  # additive: nothing rendered, nothing to say
        for record in entry.guides:
            guide = found.get(record.pair)
            if guide is None:
                continue  # additive: this one is gone, keep what we stored
            position = tuple(float(value) for value in guide.position)
            rotation = tuple(float(value) for value in guide.rotation)
            attrs = {key: float(value) for key, value in guide.attrs.items()}
            if (
                record.position != position
                or record.rotation != rotation
                or record.rotate_order != guide.rotate_order
                or record.attrs != attrs
            ):
                changed = True
            record.position = position
            record.rotation = rotation
            record.rotate_order = guide.rotate_order
            record.attrs = attrs
    return changed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_capture_trigger.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/guides/capture.py tests/unit/test_capture_trigger.py
git commit -m "feat(tik.trigger): additive capture from scene into the document"
```

---

### Task 7: Regenerate — document into scene, scoped to one module

The document → scene direction. Scoped, never global. Step 4 of spec §4.3 decides whether lockstep feels helpful or hostile: `segments 3→5` must keep segments 0–2 exactly where the rigger put them.

**Files:**
- Create: `src/python/tik/trigger/guides/regenerate.py`
- Test: `tests/unit/test_regenerate_trigger.py`

**Interfaces:**
- Consumes: `document_store` (Task 4), `capture` (Task 6), `GuideDraft` from `tik.trigger.maya.rig`, `nodes`, `registry`.
- Produces: `regenerate(entry, document=None) -> dict` — `{(role, index): joint}`; `regenerate_all(document) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_regenerate_trigger.py`:

```python
"""Regenerate: rebuild a module's guide joints from its document entry."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core.guide_document import GuideDocument, GuideRecord, ModuleEntry, expand_guides
from tik.trigger.core import registry
from tik.trigger.guides import document_store, regenerate, snapshot
from tik.trigger.maya import tags


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def chain_entry(segments=3):
    entry = ModuleEntry("id1", "fkchain", "tail", "C", settings={"segments": segments})
    layout = registry.get_module("fkchain").guides
    expand_guides(entry, layout, segments)
    return entry


def test_regenerate_draws_every_declared_guide():
    entry = chain_entry(3)
    joints = regenerate.regenerate(entry)
    assert sorted(joints) == sorted(entry.pairs)
    assert all(cmds.objExists(joint.long_name) for joint in joints.values())


def test_regenerated_joints_carry_the_stored_uuid():
    entry = chain_entry(2)
    joints = regenerate.regenerate(entry)
    for joint in joints.values():
        assert joint.meta[tags.INSTANCE] == "id1"


def test_regenerate_restores_stored_poses():
    entry = chain_entry(2)
    entry.guide("segment", 0).position = (12.0, 3.0, 0.0)
    joints = regenerate.regenerate(entry)
    placed = cmds.xform(joints[("segment", 0)].long_name, query=True,
                        worldSpace=True, translation=True)
    assert placed == pytest.approx([12.0, 3.0, 0.0])


def test_unposed_guides_land_at_their_draw_guides_pose():
    """A guide the document has never seen posed must not collapse to the origin."""
    entry = chain_entry(2)
    joints = regenerate.regenerate(entry)
    placed = cmds.xform(joints[("segment", 1)].long_name, query=True,
                        worldSpace=True, translation=True)
    assert placed != pytest.approx([0.0, 0.0, 0.0])


def test_growing_the_chain_keeps_the_poses_of_survivors():
    """The case that decides whether lockstep is helpful or hostile."""
    entry = chain_entry(2)
    entry.guide("segment", 0).position = (12.0, 3.0, 0.0)
    regenerate.regenerate(entry)
    entry.settings["segments"] = 4
    expand_guides(entry, registry.get_module("fkchain").guides, 4)
    joints = regenerate.regenerate(entry)
    kept = cmds.xform(joints[("segment", 0)].long_name, query=True,
                      worldSpace=True, translation=True)
    assert kept == pytest.approx([12.0, 3.0, 0.0])
    assert ("segment", 3) in joints


def test_regenerate_replaces_rather_than_duplicates():
    entry = chain_entry(2)
    regenerate.regenerate(entry)
    regenerate.regenerate(entry)
    rendered = [guide for guide in snapshot.snapshot() if guide.instance_id == "id1"]
    assert len(rendered) == len(entry.pairs)


def test_regenerate_rebuilds_the_intra_module_dag():
    entry = chain_entry(2)
    joints = regenerate.regenerate(entry)
    parent = joints[("segment", 0)].parent
    assert parent.meta[tags.ROLE] == "root"


def test_regenerate_parents_the_root_under_its_primary_input_producer():
    """The DAG is a rendering of the primary input (spec 4.4)."""
    producer = chain_entry(1)
    producer.instance_id = "producer"
    producer.name = "spine"
    child = chain_entry(1)
    child.inputs = {"root": "producer.root"}
    document = GuideDocument(modules=[producer, child])
    regenerate.regenerate(producer, document)
    joints = regenerate.regenerate(child, document)
    root_parent = joints[("root", 0)].parent
    assert root_parent.meta[tags.INSTANCE] == "producer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_regenerate_trigger.py -q`
Expected: FAIL — `ImportError: cannot import name 'regenerate'`

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/trigger/guides/regenerate.py`:

```python
"""Regenerate: rebuild one module's guide joints from its document entry.

Scoped to a single module, never global — if changing one field redrew the whole
character, lockstep would not be viable.

The step that matters is restoring stored poses (spec 4.3 step 4). A guide the
document has a pose for goes back exactly where the rigger put it; a guide it has
never seen posed lands wherever ``draw_guides`` puts it, never at the origin.
That is the difference between a tool that keeps up with you and one that throws
your work away.
"""

from __future__ import annotations

from typing import Optional

from maya import cmds
from tik.trigger.core import registry
from tik.trigger.core.guide_document import GuideDocument, ModuleEntry
from tik.trigger.maya import tags
from tik.trigger.maya.rig import GuideDraft

from . import nodes


def _module_for(entry: ModuleEntry):
    """Rebuild the ``Module`` object for ``entry``, keeping its identity."""
    module_cls = registry.get_module(entry.module_type)
    return module_cls(
        instance_id=entry.instance_id,
        name=entry.name,
        side=entry.side,
        settings=dict(entry.settings),
    )


def _producer_guide(entry: ModuleEntry, document: Optional[GuideDocument]):
    """The guide joint this module's root should hang under, or None.

    The DAG is a rendering of the primary input connection, rebuilt every time,
    so the joint hierarchy and the connection graph cannot diverge.
    """
    if document is None:
        return None
    module_cls = registry.get_module(entry.module_type)
    primary = module_cls.primary_input()
    if primary is None:
        return None
    source = entry.inputs.get(primary.name)
    if not source or "." not in source:
        return None
    producer_id, _dot, output = source.rpartition(".")
    producer = document.module(producer_id)
    if producer is None:
        return None
    producer_cls = registry.get_module(producer.module_type)
    role = output if output in producer_cls.guides.all_roles else producer_cls.guides.root
    found = nodes.guide_nodes(producer_id)
    return found.get((role, 0)) or found.get((producer_cls.guides.root, 0))


def regenerate(entry: ModuleEntry, document: Optional[GuideDocument] = None) -> dict:
    """Rebuild ``entry``'s guide joints. Returns ``{(role, index): joint}``."""
    module = _module_for(entry)
    holder = nodes.holder()
    with nodes.undo_chunk(f"Trigger regenerate: {entry.name}"):
        existing = nodes.guide_nodes(entry.instance_id)
        for node in existing.values():
            # keep other instances' guides that hang under ours
            for child in node.children:
                if child.meta.get(tags.INSTANCE) not in (None, entry.instance_id):
                    child.parent = holder
        if existing:
            cmds.delete([node.long_name for node in existing.values() if node.exists()])

        draft = GuideDraft(module, holder, _producer_guide(entry, document))
        module.draw_guides(draft)
        created = draft.created
        for record in entry.guides:
            joint = created.get(record.pair)
            if joint is None or not record.posed:
                continue  # unposed: leave it where draw_guides put it
            cmds.setAttr(f"{joint.long_name}.rotateOrder", record.rotate_order)
            cmds.xform(joint.long_name, worldSpace=True, translation=record.position)
            if record.rotation is not None:
                cmds.xform(joint.long_name, worldSpace=True, rotation=record.rotation)
            for name, value in record.attrs.items():
                if joint.has_attr(name):
                    joint[name].value = value
        # after the poses land, so a guide rig can take over the channels
        module.wire_guides(created)
    return created


def regenerate_all(document: GuideDocument) -> None:
    """Rebuild every module, producers first so roots find their parent guide."""
    from tik.trigger.core.schemas import order_by_connections

    ordered = _ordered(document)
    for entry in ordered:
        regenerate(entry, document)


def _ordered(document: GuideDocument) -> list:
    """Entries with producers before consumers, so root parenting resolves."""
    by_id = {entry.instance_id: entry for entry in document.modules}
    ordered: list = []
    done: set = set()
    visiting: set = set()

    def visit(entry: ModuleEntry) -> None:
        if entry.instance_id in done:
            return
        if entry.instance_id in visiting:
            return  # a cycle: break it rather than recursing forever
        visiting.add(entry.instance_id)
        for source in entry.inputs.values():
            if source and "." in source:
                producer = by_id.get(source.rpartition(".")[0])
                if producer is not None and producer is not entry:
                    visit(producer)
        visiting.discard(entry.instance_id)
        done.add(entry.instance_id)
        ordered.append(entry)

    for entry in document.modules:
        visit(entry)
    return ordered
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_regenerate_trigger.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Remove the unused import**

`regenerate_all` imports `order_by_connections` but uses the local `_ordered`. Delete the import line.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/guides/regenerate.py tests/unit/test_regenerate_trigger.py
git commit -m "feat(tik.trigger): scoped regenerate that preserves authored poses"
```

---

### Task 8: The missing scene callbacks

Node removal has no `scriptJob` equivalent, which is defect 1 in the spec. One scene-wide `MDGMessage` callback needs no re-registration as guides come and go, unlike per-node `scriptJob(nodeDeleted=…)`. It must be deregistered on teardown — a live OpenMaya callback into a destroyed widget crashes Maya on shutdown.

**Files:**
- Modify: `src/python/tik/trigger/maya/observer.py`
- Modify: `src/python/tik/shared/ui/scene_watcher.py`
- Test: `tests/unit/test_observer_trigger.py`

**Interfaces:**
- Produces: `ApiCallbacks(callback)` with `.start()`, `.stop()`, `.active`; events `"NodeRemoved"` and `"ParentChanged"`.
- `SceneWatcher` gains `api_callbacks=True` — installs `ApiCallbacks` alongside the scriptJobs and uninstalls both.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_observer_trigger.py`:

```python
"""API callbacks for the events scriptJob cannot see."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.maya.observer import ApiCallbacks


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def test_node_removal_fires_a_callback():
    seen = []
    callbacks = ApiCallbacks(seen.append)
    callbacks.start()
    try:
        joint = cmds.joint(name="doomed")
        cmds.delete(joint)
    finally:
        callbacks.stop()
    assert "NodeRemoved" in seen


def test_reparenting_fires_a_callback():
    seen = []
    parent = cmds.group(empty=True, name="parent")
    child = cmds.group(empty=True, name="child")
    callbacks = ApiCallbacks(seen.append)
    callbacks.start()
    try:
        cmds.parent(child, parent)
    finally:
        callbacks.stop()
    assert "ParentChanged" in seen


def test_stop_deregisters_everything():
    callbacks = ApiCallbacks(lambda _name: None)
    callbacks.start()
    assert callbacks.active is True
    callbacks.stop()
    assert callbacks.active is False


def test_stop_is_idempotent():
    callbacks = ApiCallbacks(lambda _name: None)
    callbacks.start()
    callbacks.stop()
    callbacks.stop()
    assert callbacks.active is False


def test_no_callbacks_fire_after_stop():
    seen = []
    callbacks = ApiCallbacks(seen.append)
    callbacks.start()
    callbacks.stop()
    joint = cmds.joint(name="doomed")
    cmds.delete(joint)
    assert seen == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_observer_trigger.py -q`
Expected: FAIL — `ImportError: cannot import name 'ApiCallbacks'`

- [ ] **Step 3: Write the implementation**

Append to `src/python/tik/trigger/maya/observer.py`:

```python
class ApiCallbacks:
    """The scene events ``scriptJob`` cannot see: node removal and reparenting.

    Maya offers no generic node-deleted ``scriptJob`` event, so the Guide
    Designer was blind to a rigger deleting a guide in the outliner. One
    scene-wide ``MDGMessage`` callback covers every removal and — unlike
    per-node ``scriptJob(nodeDeleted=...)`` — needs no re-registration as guides
    come and go.

    Raw OpenMaya is a deliberate exception to the consume-tik.maya rule: there
    is no ``cmds`` equivalent. ``stop()`` must be called on teardown; a live
    callback firing into a destroyed widget crashes Maya on shutdown.
    """

    def __init__(self, callback: Callable[[str], None]) -> None:
        self.callback = callback
        self._ids: list = []
        self.muted = False

    def start(self) -> None:
        import maya.api.OpenMaya as om

        self.stop()
        self._ids.append(
            om.MDGMessage.addNodeRemovedCallback(
                lambda *_args: self._fire("NodeRemoved"), "dependNode"
            )
        )
        self._ids.append(
            om.MDagMessage.addParentAddedCallback(
                lambda *_args: self._fire("ParentChanged")
            )
        )

    def stop(self) -> None:
        import maya.api.OpenMaya as om

        while self._ids:
            try:
                om.MMessage.removeCallback(self._ids.pop())
            except RuntimeError:
                pass

    def _fire(self, name: str) -> None:
        if not self.muted:
            self.callback(name)

    @property
    def active(self) -> bool:
        return bool(self._ids)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_observer_trigger.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Wire it into SceneWatcher**

Modify `src/python/tik/shared/ui/scene_watcher.py`:

- Add `api_callbacks: bool = False` to `__init__`, store as `self._api_callbacks_wanted`, and `self._api = None`.
- In `install()`, after the scriptJob loop:

```python
        if self._api_callbacks_wanted:
            try:
                from tik.trigger.maya.observer import ApiCallbacks

                self._api = ApiCallbacks(self.notify)
                self._api.start()
            except Exception as error:  # noqa: BLE001 - keep the tool alive
                LOG.debug("cannot install API callbacks: %s", error)
                self._api = None
```

- In `uninstall()`, before the scriptJob loop:

```python
        if self._api is not None:
            self._api.stop()
            self._api = None
```

- In `mute()`, set `self._api.muted` alongside `self._muted` so tool-caused deletions are ignored:

```python
    @contextlib.contextmanager
    def mute(self):
        """Ignore events while the tool changes the scene itself."""
        self._muted += 1
        if self._api is not None:
            self._api.muted = True
        try:
            yield
        finally:
            self._muted -= 1
            if self._api is not None and not self._muted:
                self._api.muted = False
```

- [ ] **Step 6: Turn it on in the Designer**

Modify `src/python/tik/trigger/ui/designer/window.py` — add `api_callbacks=True` to the `SceneWatcher(...)` construction.

- [ ] **Step 7: Run the unit and UI suites**

Run: `make tests-unit` then `make tests-ui`
Expected: PASS — `api_callbacks` defaults to False, so the Qt stub path is unaffected.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/maya/observer.py src/python/tik/shared/ui/scene_watcher.py src/python/tik/trigger/ui/designer/window.py tests/unit/test_observer_trigger.py
git commit -m "feat(tik.trigger): notice node removal and reparenting in the scene"
```

---

### Task 9: GuideScene on the document

Point `GuideScene` and `GuideHandle` at the document instead of root-guide meta. This is the migration described in spec §7: `trg_name`, `trg_settings` and `trg_inputs` leave the root guide, connections become uuid-keyed, and `_rename_key` / `_forget_key` are deleted because uuid keying leaves nothing to patch.

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py`
- Modify: `src/python/tik/trigger/guides/handle.py`
- Modify: `src/python/tik/trigger/guides/nodes.py`
- Test: `tests/unit/test_guide_scene_trigger.py` (existing — update), `tests/unit/test_guides_trigger.py` (existing — update)

**Interfaces:**
- `GuideScene` gains `.document -> GuideDocument` (cached), `.reload()`, `.commit()`, `.diff() -> GuideDiff`.
- `GuideScene.add/remove/mirror/duplicate/connect/disconnect/set_inputs/write_settings` all read-modify-write the document, then regenerate the affected entry.
- `GuideHandle` reads its `ModuleEntry` from the document; `.key` stays a display key.
- Connections change format from `"L_arm.hand"` to `"<uuid>.hand"`. `split_source` is unchanged; the *meaning* of the left half changes.
- Delete from `scene.py`: `_rename_key`, `_forget_key`, `_write_root_meta`, `_write_guide_attrs`, `_sync_setting_attrs`, `read_layout`, `write_layout`, `settings_plug` (moves to `module_node`).
- `nodes.instance_from_nodes` stops reading `tags.NAME`, `tags.SETTINGS`, `INPUTS`.

- [ ] **Step 1: Update the existing tests to the new contract**

The current tests assert structure on the root guide. Rewrite those assertions to read the document. Run the suite first to see the full list:

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_guide_scene_trigger.py tests/unit/test_guides_trigger.py -q`
Record every failure; each is a place structure was read off a joint.

- [ ] **Step 2: Add the new behaviour test**

Append to `tests/unit/test_guide_scene_trigger.py`:

```python
def test_deleting_the_root_guide_does_not_destroy_the_module(fresh_scene):
    """The defect this whole design exists to fix."""
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail")
    root = handle.root
    cmds.delete(root.long_name)
    scene.reload()
    assert scene.get(handle.instance_id) is not None
    assert scene.get(handle.instance_id).name == "tail"


def test_connections_survive_a_rename_in_maya(fresh_scene):
    scene = GuideScene()
    parent = scene.add("fkchain", side="C", name="spine")
    child = scene.add("fkchain", side="L", name="tail")
    scene.connect(f"{child.key}.root", f"{parent.key}.root")
    cmds.rename(parent.root.long_name, "renamed_by_hand")
    scene.reload()
    assert scene.get(child.instance_id).inputs["root"].startswith(parent.instance_id)
```

- [ ] **Step 3: Rewrite `scene.py` onto the document**

Replace the settings/inputs/layout half of `GuideScene`. The shape:

```python
    def __init__(self, events=None):
        self.events = events or EventBus()
        self._document: Optional[GuideDocument] = None

    @property
    def document(self) -> GuideDocument:
        if self._document is None:
            self._document = document_store.read_document()
        return self._document

    def reload(self) -> GuideDocument:
        """Drop the cached document and re-read it from the scene."""
        self._document = None
        return self.document

    def commit(self, modules=None) -> None:
        """Write the cached document back to the scene."""
        document_store.write_document(self.document, modules=modules)

    def diff(self):
        from tik.trigger.core.reconcile import reconcile
        from .snapshot import snapshot

        return reconcile(
            self.document,
            snapshot(),
            primary_input_of=lambda entry: (
                registry.get_module(entry.module_type).primary_input().name
                if registry.get_module(entry.module_type).primary_input()
                else None
            ),
        )

    def invalidate(self) -> None:
        self.reload()
```

`add()` becomes: build the module, `expand_guides` its entry, `write_entry`, `regenerate`. `remove()` becomes: drop the entry from the document, `commit`, delete the joints. `set_inputs`/`write_settings` mutate the entry and `commit`. `settings_plug` delegates to `module_node.settings_plug`.

- [ ] **Step 4: Rewrite `handle.py` onto the document**

`GuideHandle` holds `(guides, instance_id)` and reads its entry through `guides.document.module(instance_id)`. `_refresh` raises `GuideError` when the entry is gone (not when the joints are). `name.setter` no longer calls `_rename_key`.

- [ ] **Step 5: Strip `nodes.instance_from_nodes`**

Remove the `tags.NAME` / `tags.SETTINGS` / `INPUTS` reads; it now returns identity and poses only. Callers that need settings go through the document.

- [ ] **Step 6: Run the suites**

Run: `make tests-unit`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/guides/ tests/unit/test_guide_scene_trigger.py tests/unit/test_guides_trigger.py
git commit -m "refactor(tik.trigger): move module structure off the guide joints"
```

---

### Task 10: Repoint the Designer's property bindings

The properties panel binds widgets two-way to `settings_plug()`. The plug now lives on the module node.

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/properties.py`
- Modify: `src/python/tik/trigger/ui/designer/window.py`
- Test: `tests/ui/test_designer_bindings.py` (existing — check), `tests/unit/test_guide_scene_trigger.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_guide_scene_trigger.py`:

```python
def test_settings_plug_lives_on_the_module_node(fresh_scene):
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail")
    plug = scene.settings_plug(handle.instance_id, "segments")
    assert plug is not None
    assert "_module" in plug.path
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_guide_scene_trigger.py::test_settings_plug_lives_on_the_module_node -q`
Expected: FAIL

- [ ] **Step 3: Implement**

`GuideScene.settings_plug` delegates to `module_node.settings_plug`. `properties.py` needs no change — it already goes through `getattr(self.guides, "settings_plug", None)`. Verify `_plug_adapter` handles a `None` return (it currently catches `TriggerError`; add a `None` guard).

- [ ] **Step 4: Run the suites**

Run: `make tests-unit` then `make tests-ui`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/ui/designer/ tests/unit/test_guide_scene_trigger.py
git commit -m "refactor(tik.trigger): bind properties to the module node"
```

---

### Task 11: Substrate complete — reconcile reported, nothing automatic

The branch point of spec §9. Reconcile runs on every refresh and its result is reported in the status strip. Nothing acts on it yet, so both lockstep (Task 12) and a checkpointed policy can be built from here.

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/window.py`
- Test: `tests/ui/test_designer_status.py`

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_designer_status.py`:

```python
"""The Designer reports reconcile results in its status strip."""

from tik.trigger.core.reconcile import GuideDiff, ModuleDiff


def test_status_text_for_a_clean_diff():
    from tik.trigger.ui.designer.window import diff_summary

    assert diff_summary(GuideDiff()) == ""


def test_status_text_counts_stale_modules():
    from tik.trigger.ui.designer.window import diff_summary

    diff = GuideDiff(modules={"a": ModuleDiff("a", absent=True)})
    assert diff_summary(diff) == "1 module(s) need redraw"


def test_status_text_counts_orphans():
    from tik.trigger.ui.designer.window import diff_summary

    diff = GuideDiff(orphans=["ghost_guide"])
    assert diff_summary(diff) == "1 orphan guide(s)"


def test_status_text_combines_both():
    from tik.trigger.ui.designer.window import diff_summary

    diff = GuideDiff(modules={"a": ModuleDiff("a", absent=True)}, orphans=["g"])
    assert diff_summary(diff) == "1 module(s) need redraw · 1 orphan guide(s)"
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui/test_designer_status.py -q`
Expected: FAIL — `ImportError: cannot import name 'diff_summary'`

- [ ] **Step 3: Implement**

Add to `window.py`, module level:

```python
def diff_summary(diff) -> str:
    """One-line description of a reconcile result for the status strip."""
    parts = []
    if diff.structural:
        parts.append(f"{len(diff.structural)} module(s) need redraw")
    if diff.orphans:
        parts.append(f"{len(diff.orphans)} orphan guide(s)")
    if diff.duplicates:
        parts.append(f"{len(diff.duplicates)} duplicate guide(s)")
    return " · ".join(parts)
```

In `refresh()`, after the connection count, compute `diff = self.guides.diff()` and add `diff_summary(diff)` to the status. Guard it with `try/except` so a scene without Maya (the UI stub) still refreshes.

- [ ] **Step 4: Run the suites**

Run: `make tests-ui` then `make tests-unit`
Expected: PASS

- [ ] **Step 5: Commit — this is the substrate boundary**

```bash
git add src/python/tik/trigger/ui/designer/window.py tests/ui/test_designer_status.py
git commit -m "feat(tik.trigger): report reconcile results in the Designer"
```

---

### Task 12: Lockstep

The policy. Consumes the diff automatically: capture absorbs pose drift, regenerate fixes structural staleness, and a document write plus its regenerate are one undo chunk.

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py`
- Modify: `src/python/tik/trigger/ui/designer/window.py`
- Test: `tests/integration/trigger/test_lockstep_trigger.py`

**Interfaces:**
- Produces: `GuideScene.sync() -> GuideDiff` — capture, reconcile, regenerate the structurally stale, return what it found.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/trigger/test_lockstep_trigger.py`:

```python
"""Lockstep: the scene and the document are never knowingly apart."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.guides import GuideScene


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def test_deleting_a_guide_redraws_it():
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=3)
    joints = scene.guide_nodes(handle.instance_id)
    cmds.delete(joints[("segment", 1)].long_name)
    scene.sync()
    assert ("segment", 1) in scene.guide_nodes(handle.instance_id)


def test_a_deleted_guide_comes_back_where_it_was():
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=3)
    joints = scene.guide_nodes(handle.instance_id)
    target = joints[("segment", 1)]
    cmds.xform(target.long_name, worldSpace=True, translation=(13.0, 4.0, 0.0))
    scene.sync()  # capture the move
    cmds.delete(scene.guide_nodes(handle.instance_id)[("segment", 1)].long_name)
    scene.sync()  # regenerate it
    restored = scene.guide_nodes(handle.instance_id)[("segment", 1)]
    placed = cmds.xform(restored.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([13.0, 4.0, 0.0])


def test_moving_a_guide_never_triggers_a_redraw():
    """Pose drift is captured, never regenerated — the guide must not snap back."""
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    target = scene.guide_nodes(handle.instance_id)[("segment", 0)]
    cmds.xform(target.long_name, worldSpace=True, translation=(9.0, 9.0, 0.0))
    diff = scene.sync()
    assert diff.structural == []
    placed = cmds.xform(target.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([9.0, 9.0, 0.0])


def test_growing_the_chain_draws_the_new_guides_immediately():
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    handle.segments = 4
    assert ("segment", 3) in scene.guide_nodes(handle.instance_id)


def test_growing_the_chain_keeps_existing_poses():
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    target = scene.guide_nodes(handle.instance_id)[("segment", 0)]
    cmds.xform(target.long_name, worldSpace=True, translation=(11.0, 2.0, 0.0))
    scene.sync()
    handle.segments = 4
    kept = scene.guide_nodes(handle.instance_id)[("segment", 0)]
    placed = cmds.xform(kept.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([11.0, 2.0, 0.0])


def test_a_settings_change_and_its_redraw_undo_together():
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    handle.segments = 4
    cmds.undo()
    scene.reload()
    assert scene.get(handle.instance_id).segments == 2
    assert ("segment", 3) not in scene.guide_nodes(handle.instance_id)


def test_orphans_are_reported_and_left_alone():
    scene = GuideScene()
    scene.add("fkchain", side="C", name="tail", segments=1)
    ghost = cmds.joint(name="ghost_guide")
    import tik.maya as tm
    from tik.trigger.maya import tags
    tm.Joint(ghost).meta.update({
        tags.KIND: tags.GUIDE, tags.MODULE: "fkchain",
        tags.INSTANCE: "nosuchmodule", tags.ROLE: "root", tags.INDEX: 0, tags.SIDE: "C",
    })
    diff = scene.sync()
    assert diff.orphans
    assert cmds.objExists("ghost_guide")
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/integration/trigger/test_lockstep_trigger.py -q`
Expected: FAIL — `AttributeError: 'GuideScene' object has no attribute 'sync'`

- [ ] **Step 3: Implement `sync()`**

Add to `GuideScene`:

```python
    def sync(self, regenerate_stale: bool = True):
        """Capture, reconcile, and redraw whatever is structurally stale.

        The order is the point (spec 5): capture runs first, so pose drift is
        absorbed before reconcile sees it and can never be mistaken for a reason
        to redraw a guide the rigger has just dragged.
        """
        from tik.trigger.core.reconcile import reconcile
        from .capture import capture
        from .regenerate import regenerate
        from .snapshot import snapshot

        if self._syncing:
            return self._empty_diff()
        self._syncing = True
        try:
            rendered = snapshot()
            if capture(self.document, rendered):
                self.commit()
                rendered = snapshot()
            diff = self.diff()
            if regenerate_stale and diff.structural:
                with nodes.undo_chunk("Trigger lockstep redraw"):
                    for instance_id in diff.structural:
                        entry = self.document.module(instance_id)
                        if entry is not None:
                            regenerate(entry, self.document)
            return diff
        finally:
            self._syncing = False
```

Add `self._syncing = False` to `__init__`, and make every write path (`write_settings`, `set_inputs`, `add`, `remove`) end with a scoped `regenerate` inside the same undo chunk as the document write.

- [ ] **Step 4: Wire it into the Designer's scene-event path**

In `window.py:_on_scene_event`, replace the bare `self.refresh()` with:

```python
    def _on_scene_event(self, name: str) -> None:
        if name == "SelectionChanged":
            return  # selection is not synced; structure changes are
        with self.watcher.mute():
            self.guides.sync()
        self.refresh()
```

The `mute()` is required: `sync()` deletes and recreates joints, which fires the removal callback, which would re-enter.

- [ ] **Step 5: Run the suites**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/integration/trigger/test_lockstep_trigger.py -q`
Expected: PASS (7 tests)

Run: `make tests-unit` then `make tests-integration` then `make tests-ui`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/guides/scene.py src/python/tik/trigger/ui/designer/window.py tests/integration/trigger/test_lockstep_trigger.py
git commit -m "feat(tik.trigger): lockstep the scene and the guide document"
```

---

### Task 13: Re-entrancy hardening and the round-trip guarantee

The rule that holds lockstep together, plus the test the whole design rests on.

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py`
- Test: `tests/integration/trigger/test_lockstep_trigger.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_lockstep_trigger.py`:

```python
def test_sync_does_not_re_enter_itself():
    """Regenerate deletes joints, which fires the removal callback."""
    scene = GuideScene()
    scene.add("fkchain", side="C", name="tail", segments=2)
    calls = []
    original = scene.sync

    def counting_sync(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    scene.sync = counting_sync
    scene.sync()
    assert len(calls) == 1


def test_document_survives_a_full_round_trip():
    """The guarantee the whole design rests on."""
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=3)
    target = scene.guide_nodes(handle.instance_id)[("segment", 1)]
    cmds.xform(target.long_name, worldSpace=True, translation=(6.0, 7.0, 8.0))
    scene.sync()
    before = scene.document.to_dict()

    # tear the whole rendering down and rebuild it from the document alone
    for joint in list(scene.guide_nodes(handle.instance_id).values()):
        cmds.delete(joint.long_name)
    scene.sync()

    scene.reload()
    assert scene.document.to_dict() == before
    restored = scene.guide_nodes(handle.instance_id)[("segment", 1)]
    placed = cmds.xform(restored.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([6.0, 7.0, 8.0])
```

- [ ] **Step 2: Run to verify they fail or pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/integration/trigger/test_lockstep_trigger.py -q`
Note which fail; the `_syncing` guard from Task 12 may already cover the first.

- [ ] **Step 3: Fix whatever the tests expose**

The likely gap is that `capture` runs against a rendering `regenerate` is midway through building. Assert it: raise `GuideError("capture ran inside a regenerate")` if `capture` is entered while `self._regenerating` is set, and set that flag in `regenerate`.

- [ ] **Step 4: Run the whole suite**

Run: `make tests`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/guides/ tests/integration/trigger/test_lockstep_trigger.py
git commit -m "test(tik.trigger): lockstep re-entrancy and the round-trip guarantee"
```

---

## Done when

- Deleting any guide joint in the outliner — including a root — redraws it where it was, and never destroys a module.
- Moving a guide never causes a redraw.
- `fkchain.segments` 3→5 draws two joints immediately, keeps the first three where they were, and undoes as one step.
- Maya-duplicating a module reports duplicates instead of silently merging them.
- Renaming a guide joint in Maya changes nothing.
- `make tests` passes.
