# Optional Sync, Scope-Split Action Bar, and Snapshot From Scene — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Guide Designer's four action buttons into a full-width bottom bar grouped by
what they act on, make scene syncing optional with an explicit Sync button, and add a
Snapshot-From-Scene recovery command that can rebuild a lost session from tagged guide joints.

**Architecture:** Three independent strands that share one bar. (1) A *breadcrumb*: `regenerate`
stamps each module's `ModuleEntry` — minus its poses — onto its root guide as `trg_entry`,
written by regenerate and read only by Snapshot. (2) *Optional sync*: a `GuideScene.auto_sync`
flag that gates only the scene-watcher path, never the capture that precedes every write.
(3) *The bar*: a new `DesignerActionBar` widget hosted by the Designer page, replacing the
button row at the bottom of the properties panel.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), PySide (via `tik.shared.ui.Qt`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-01-optional-sync-and-snapshot-design.md`

## Global Constraints

- `tik/trigger/core` is **pure Python** — no Maya, no Qt. Enforced by
  `tests/unit/test_import_boundaries.py`.
- `tik/trigger/session.py` must stay **Maya-free at import time**; UI tests run with
  `TIK_TESTS_NO_MAYA=1`.
- No third-party dependencies. Stdlib and Maya-bundled modules only.
- Never call `maya.cmds` / `OpenMaya` directly outside `tik.maya`, `tik/trigger/guides` and
  `tik/trigger/maya` — those layers already do, and stay the only ones that may.
- Theme values are **lifted, never invented**: `#1e1e1e` bar, `1px #353535` top rule, margins
  `(10, 7, 10, 7)`, spacing `8`, captions `#FieldCaption` (`#7b7b7b`, 10px, 1px letter-spacing),
  pill `#3a2e1f` on `#FE7E00`, label `#e0c8a8`. All already in
  `src/python/tik/shared/ui/theme/__init__.py`.
- **The invariant, quoted verbatim in the code it governs:** *A write always captures first.
  `Auto` only decides whether the scene may start a sync.*
- **The breadcrumb rule, likewise:** *`trg_entry` is WRITTEN by `regenerate` and READ only by
  Snapshot.* And: *the breadcrumb carries only what a document write can change; poses come
  from the joints.*
- Run commands assume `PYTHONPATH` includes `src/python`. Single tests:
  `mayapy -m pytest tests/unit/<file>::<test> -v`. Suites: `make tests-unit`,
  `make tests-integration`, `make tests-ui`.
- Baseline before starting: **1112 unit · 201 integration · 102 UI, all passing.**

## File Structure

**Create**
| File | Responsibility |
|---|---|
| `src/python/tik/trigger/core/scene_recovery.py` | Pure: assemble a `GuideDocument` + `RecoveryReport` from scene-shaped records. No Maya. |
| `src/python/tik/trigger/guides/from_scene.py` | Maya: read `SceneModule` records (type, side, breadcrumb) off the joints. Thin. |
| `src/python/tik/trigger/ui/designer/action_bar.py` | The scope-split bar widget. Qt only, no scene access. |
| `src/python/tik/trigger/ui/designer/snapshot_dialog.py` | The recovery report dialog. Renders a `RecoveryReport`. |
| `tests/unit/test_scene_recovery_trigger.py` | Pure recovery tests. |
| `tests/unit/test_from_scene_trigger.py` | Maya reader + round trip. |
| `tests/ui/test_action_bar.py` | Bar groups, states, menu/checkbox round trip. |

**Modify**
| File | Change |
|---|---|
| `src/python/tik/trigger/guides/regenerate.py` | Write the breadcrumb at the end of `regenerate`. |
| `src/python/tik/trigger/guides/scene.py` | `auto_sync` attribute; `snapshot_from_scene()`. |
| `src/python/tik/trigger/session.py` | `Session.snapshot_guides_from_scene()`, pushes one undo step. |
| `src/python/tik/trigger/ui/designer/window.py` | Remove the button row; host the bar; honour `auto_sync` in `_on_scene_event`. |
| `src/python/tik/trigger/ui/designer/commands.py` | `sync_now`, `set_auto_sync`, `snapshot_guides`. |
| `src/python/tik/trigger/ui/main.py` | Guides-menu group; `Refresh` → `Redraw Views`; F6. |
| `tests/ui/stub.py` | Add `auto_sync`, `diff`, `snapshot_from_scene`; **drop the dead `settings_plug`**. |
| `tests/integration/trigger/test_lockstep_trigger.py` | The auto-off regression fence. |
| `CLAUDE.md` | Point at the new spec. |

Tasks 1–3 (breadcrumb → recovery) and tasks 4 (optional sync) are independent of tasks 5–7
(the bar); 8–10 join them up. Tasks 1, 4 and 5 can run in parallel.

---

### Task 1: The scene breadcrumb

**Files:**
- Modify: `src/python/tik/trigger/guides/regenerate.py`
- Test: `tests/unit/test_regenerate_trigger.py`

**Interfaces:**
- Consumes: `ModuleEntry.to_dict()`, `nodes.root_guide(created, module_type)`, `tags.ENTRY`.
- Produces: every root guide carries `meta[tags.ENTRY]` — an `entry.to_dict()` dict with the
  `"guides"` key removed. Task 2's reader depends on that exact shape.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_regenerate_trigger.py`:

```python
def test_regenerate_stamps_the_entry_on_the_root_guide():
    """Snapshot's only way back: what the module *is*, parked on its root joint."""
    entry = chain_entry(2, name="tail")
    entry.inputs["parent"] = "other-id.root"
    joints = regenerate.regenerate(entry)
    root = joints[(registry.get_module("fkchain").guides.root, 0)]
    stored = root.meta[tags.ENTRY]
    assert stored["name"] == "tail"
    assert stored["module_type"] == "fkchain"
    assert stored["settings"]["segments"] == 2
    assert stored["inputs"]["parent"] == "other-id.root"


def test_the_breadcrumb_never_carries_poses():
    """A guide moves with no document write, so a stored pose would rot in place."""
    entry = chain_entry(2)
    entry.guide("segment", 0).position = (12.0, 3.0, 0.0)
    joints = regenerate.regenerate(entry)
    root = joints[(registry.get_module("fkchain").guides.root, 0)]
    assert "guides" not in root.meta[tags.ENTRY]


def test_only_the_root_guide_carries_the_breadcrumb():
    entry = chain_entry(3)
    joints = regenerate.regenerate(entry)
    root_role = registry.get_module("fkchain").guides.root
    for (role, index), joint in joints.items():
        assert (tags.ENTRY in joint.meta) is ((role, index) == (root_role, 0))
```

- [ ] **Step 2: Run them and watch them fail**

Run: `mayapy -m pytest tests/unit/test_regenerate_trigger.py -k breadcrumb -v`
Expected: FAIL — `KeyError: 'trg_entry'`.

- [ ] **Step 3: Write the breadcrumb**

In `src/python/tik/trigger/guides/regenerate.py`, add above `regenerate`:

```python
def _stamp_breadcrumb(entry: ModuleEntry, created: dict) -> None:
    """Park the module's identity on its root guide, for Snapshot to find.

    WRITTEN here, READ only by Snapshot (spec 4.1). Capture, reconcile, build,
    the Designer and the Builder never consult it, so the document stays the
    sole authority and a stale or hand-edited tag can corrupt nothing.

    Poses are deliberately absent (spec 4.2): a guide moves when a rigger drags
    it, with no document write and so no regenerate to refresh this tag. What is
    kept here changes *only* through a document write, and every document write
    ends in a regenerate -- so the breadcrumb can never be staler than the joints
    it sits on.
    """
    root = nodes.root_guide(created, entry.module_type)
    if root is None:
        return
    data = entry.to_dict()
    data.pop("guides", None)
    root.meta[tags.ENTRY] = data
```

Then, inside `regenerate`'s `with` block, immediately after `module.wire_guides(created)`:

```python
        _stamp_breadcrumb(entry, created)
```

- [ ] **Step 4: Run them and watch them pass**

Run: `mayapy -m pytest tests/unit/test_regenerate_trigger.py -v`
Expected: PASS, and every pre-existing test in the file still passes.

- [ ] **Step 5: Confirm the .trg import path inherits it**

`import_guide_instances` creates joints directly, but every import ends in a regenerate. Add to
`tests/unit/test_guides_trigger.py`:

```python
def test_imported_guides_end_up_with_a_breadcrumb(guides):
    """The .trg path draws joints itself; the breadcrumb must still arrive."""
    handle = guides.add("fkchain", name="tail", segments=2)
    path = guides.export_file(tmp_path / "lib.trg")
    guides.clear()
    restored = guides.import_file(path)[0]
    root = nodes.root_guide(nodes.guide_nodes(restored.instance_id), "fkchain")
    assert root.meta[tags.ENTRY]["name"] == "tail"
```

Adapt the fixture names to the ones already in that file. If this fails, the fix belongs in
`import_guide_instances` — call `regenerate` for each imported entry rather than duplicating
the stamp.

Run: `make tests-unit`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/guides/regenerate.py tests/unit/test_regenerate_trigger.py tests/unit/test_guides_trigger.py
git commit -m "feat(tik.trigger): guides carry their module entry for recovery"
```

---

### Task 2: Pure recovery — a document out of scene-shaped records

**Files:**
- Create: `src/python/tik/trigger/core/scene_recovery.py`
- Test: `tests/unit/test_scene_recovery_trigger.py`

**Interfaces:**
- Consumes: `GuideDocument`, `ModuleEntry`, `GuideRecord` (`core/guide_document.py`);
  `RenderedGuide` (`core/reconcile.py`); `core.registry`.
- Produces:
  - `SceneModule(instance_id: str, module_type: str, side: str, entry: Optional[dict])`
  - `RecoveredModule(instance_id: str, key: str, module_type: str, complete: bool, guide_count: int)`
  - `RecoveryReport` with `.modules`, `.guide_count`, `.unknown_types`, and properties
    `.complete`, `.partial`, `.is_lossless`
  - `document_from_scene(scene_modules, rendered) -> tuple[GuideDocument, RecoveryReport]`

  Task 3 calls `document_from_scene`; Task 9 renders `RecoveryReport`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_scene_recovery_trigger.py`:

```python
"""Rebuilding a session out of what the scene carries. Pure: no Maya."""

import pytest

from tik.trigger.core.reconcile import RenderedGuide
from tik.trigger.core.scene_recovery import SceneModule, document_from_scene


def rendered(instance_id, role, index=0, position=(1.0, 2.0, 3.0), parent=None):
    return RenderedGuide(
        instance_id=instance_id, role=role, index=index,
        node=f"|{role}{index}", position=position, rotation=(0.0, 0.0, 0.0),
        rotate_order=0, attrs={}, parent=parent,
    )


def test_a_breadcrumb_restores_name_settings_and_inputs():
    scene = [SceneModule("id1", "fkchain", "L", {
        "instance_id": "id1", "module_type": "fkchain", "name": "tail",
        "side": "L", "settings": {"segments": 2}, "inputs": {"parent": "id0.root"},
    })]
    document, report = document_from_scene(scene, [rendered("id1", "root")])
    entry = document.module("id1")
    assert entry.name == "tail"
    assert entry.settings == {"segments": 2}
    assert entry.inputs == {"parent": "id0.root"}
    assert report.is_lossless


def test_poses_come_from_the_joints_not_the_breadcrumb():
    """The breadcrumb has no poses by design; the rendering supplies them."""
    scene = [SceneModule("id1", "fkchain", "C", {
        "instance_id": "id1", "module_type": "fkchain", "name": "tail",
        "side": "C", "settings": {}, "inputs": {},
    })]
    document, _report = document_from_scene(
        scene, [rendered("id1", "root", position=(7.0, 8.0, 9.0))]
    )
    assert document.module("id1").guide("root", 0).position == pytest.approx((7.0, 8.0, 9.0))


def test_without_a_breadcrumb_it_degrades_and_says_so():
    """An older scene: type and side survive on the joints, nothing else does."""
    scene = [SceneModule("id1", "fkchain", "R", None)]
    document, report = document_from_scene(scene, [rendered("id1", "root")])
    entry = document.module("id1")
    assert entry.name == "fkchain"   # falls back to the module type
    assert entry.side == "R"         # trg_side is on every joint
    assert entry.settings == {}
    assert entry.inputs == {}
    assert not report.is_lossless
    assert [item.instance_id for item in report.partial] == ["id1"]


def test_a_mixed_scene_reports_a_mixed_result():
    scene = [
        SceneModule("id1", "fkchain", "C", {
            "instance_id": "id1", "module_type": "fkchain", "name": "tail",
            "side": "C", "settings": {}, "inputs": {},
        }),
        SceneModule("id2", "fkchain", "C", None),
    ]
    _document, report = document_from_scene(
        scene, [rendered("id1", "root"), rendered("id2", "root")]
    )
    assert len(report.complete) == 1
    assert len(report.partial) == 1
    assert not report.is_lossless


def test_an_unregistered_module_type_is_skipped_and_reported():
    scene = [SceneModule("id1", "nosuchmodule", "C", None)]
    document, report = document_from_scene(scene, [rendered("id1", "root")])
    assert document.modules == []
    assert report.unknown_types == ["nosuchmodule"]


def test_guide_parents_within_the_module_survive():
    scene = [SceneModule("id1", "fkchain", "C", None)]
    document, _report = document_from_scene(scene, [
        rendered("id1", "root"),
        rendered("id1", "segment", 0, parent=("id1", "root", 0)),
    ])
    assert document.module("id1").guide("segment", 0).parent == ("root", 0)


def test_a_parent_in_another_module_is_not_an_internal_parent():
    """RenderedGuide.parent is a global triple; GuideRecord.parent is module-local."""
    scene = [SceneModule("id1", "fkchain", "C", None)]
    document, _report = document_from_scene(
        scene, [rendered("id1", "root", parent=("id0", "root", 0))]
    )
    assert document.module("id1").guide("root", 0).parent is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `mayapy -m pytest tests/unit/test_scene_recovery_trigger.py -v`
Expected: FAIL — `ModuleNotFoundError: tik.trigger.core.scene_recovery`.

- [ ] **Step 3: Write the module**

Create `src/python/tik/trigger/core/scene_recovery.py`:

```python
"""Rebuild a guide document out of what a Maya scene carries.

The recovery half of the breadcrumb (spec 4, 5). Pure: it is handed records
another layer read out of the scene, so it unit-tests without Maya.

Two sources, and which supplies what is the whole design:

* the **breadcrumb** (``trg_entry`` on the root guide) supplies identity,
  settings and connections -- things that change only through a document write;
* the **joints** supply poses and guide attrs -- things that change whenever a
  rigger drags something, with no write to refresh a tag.

A scene drawn by an older build has no breadcrumb. That is reported, never
papered over: the module comes back with its type and side and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import registry
from .guide_document import GuideDocument, GuideRecord, ModuleEntry


@dataclass
class SceneModule:
    """One module as the scene knows it, before any interpretation."""

    instance_id: str
    module_type: str
    side: str = "C"
    #: The ``trg_entry`` payload, or None on a scene drawn before breadcrumbs.
    entry: Optional[dict] = None


@dataclass
class RecoveredModule:
    """What one module came back as."""

    instance_id: str
    key: str
    module_type: str
    complete: bool
    guide_count: int


@dataclass
class RecoveryReport:
    """What a snapshot found, and what it could not bring back."""

    modules: list = field(default_factory=list)
    guide_count: int = 0
    #: Module types in the scene that this build does not know; skipped.
    unknown_types: list = field(default_factory=list)

    @property
    def complete(self) -> list:
        """Modules recovered with everything intact."""
        return [item for item in self.modules if item.complete]

    @property
    def partial(self) -> list:
        """Modules with no breadcrumb: name, settings and inputs are lost."""
        return [item for item in self.modules if not item.complete]

    @property
    def is_lossless(self) -> bool:
        return bool(self.modules) and not self.partial and not self.unknown_types


def _entry_for(scene_module: SceneModule) -> ModuleEntry:
    """The module's identity, from its breadcrumb or from the joints alone."""
    if scene_module.entry:
        data = dict(scene_module.entry)
        data.pop("guides", None)  # never stored; the joints are the poses
        return ModuleEntry.from_dict(data)
    # No breadcrumb: trg_module and trg_side are on every guide joint, so the
    # module comes back as itself -- unnamed, unconfigured and unconnected.
    return ModuleEntry(
        instance_id=scene_module.instance_id,
        module_type=scene_module.module_type,
        name=scene_module.module_type,
        side=scene_module.side,
    )


def document_from_scene(scene_modules: list, rendered: list) -> tuple:
    """Assemble a document and a report from scene records.

    Args:
        scene_modules: One :class:`SceneModule` per instance found.
        rendered: ``RenderedGuide`` records for every guide joint.

    Returns:
        ``(GuideDocument, RecoveryReport)``. The document is new; nothing is
        mutated in place, so a caller can show the report before committing.
    """
    by_instance: dict = {}
    for guide in rendered:
        by_instance.setdefault(guide.instance_id, []).append(guide)

    document = GuideDocument()
    report = RecoveryReport()
    for scene_module in scene_modules:
        if not registry.is_module_registered(scene_module.module_type):
            if scene_module.module_type not in report.unknown_types:
                report.unknown_types.append(scene_module.module_type)
            continue
        entry = _entry_for(scene_module)
        guides = by_instance.get(scene_module.instance_id, [])
        for guide in sorted(guides, key=lambda item: (item.role, item.index)):
            entry.guides.append(
                GuideRecord(
                    role=guide.role,
                    index=guide.index,
                    position=tuple(guide.position),
                    rotation=None if guide.rotation is None else tuple(guide.rotation),
                    rotate_order=guide.rotate_order,
                    attrs=dict(guide.attrs),
                    # RenderedGuide.parent is a global (instance, role, index);
                    # GuideRecord.parent is module-local, so a parent in another
                    # module is not an internal parent at all.
                    parent=(
                        (guide.parent[1], guide.parent[2])
                        if guide.parent and guide.parent[0] == scene_module.instance_id
                        else None
                    ),
                )
            )
        document.modules.append(entry)
        report.modules.append(
            RecoveredModule(
                instance_id=entry.instance_id,
                key=entry.key,
                module_type=entry.module_type,
                complete=bool(scene_module.entry),
                guide_count=len(entry.guides),
            )
        )
        report.guide_count += len(entry.guides)
    return document, report
```

- [ ] **Step 4: Run them and watch them pass**

Run: `mayapy -m pytest tests/unit/test_scene_recovery_trigger.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Prove core stayed pure**

Run: `mayapy -m pytest tests/unit/test_import_boundaries.py -v`
Expected: PASS. If it fails, `scene_recovery.py` imported something from `guides/` — the
`RenderedGuide` import must come from `core.reconcile`, never `guides.snapshot`.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/core/scene_recovery.py tests/unit/test_scene_recovery_trigger.py
git commit -m "feat(tik.trigger): rebuild a guide document from scene records"
```

---

### Task 3: The Maya reader and the session command

**Files:**
- Create: `src/python/tik/trigger/guides/from_scene.py`
- Modify: `src/python/tik/trigger/guides/scene.py`, `src/python/tik/trigger/session.py`
- Test: `tests/unit/test_from_scene_trigger.py`

**Interfaces:**
- Consumes: `snapshot()` (`guides/snapshot.py`), `tags`, `document_from_scene` (Task 2).
- Produces:
  - `from_scene.scene_modules() -> list[SceneModule]`
  - `from_scene.read() -> tuple[GuideDocument, RecoveryReport]`
  - `GuideScene.snapshot_from_scene() -> tuple[GuideDocument, RecoveryReport]` — reads only
  - `Session.snapshot_guides_from_scene(document) -> None` — commits, one undo step

  Task 9's dialog calls `GuideScene.snapshot_from_scene()` to preview, then
  `Session.snapshot_guides_from_scene()` to commit.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_from_scene_trigger.py`:

```python
"""Reading a scene back into a session. The recovery round trip."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core import registry
from tik.trigger.core.guide_document import GuideDocument, ModuleEntry, expand_guides
from tik.trigger.guides import from_scene, nodes, regenerate
from tik.trigger.maya import tags


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def drawn_chain(segments=2, instance_id="id1", name="tail", side="L", **settings):
    entry = ModuleEntry(instance_id, "fkchain", name, side,
                        settings={"segments": segments, **settings})
    expand_guides(entry, registry.get_module("fkchain").guides, segments)
    regenerate.regenerate(entry)
    return entry


def test_a_drawn_module_comes_back_whole():
    drawn_chain(2, name="tail", side="L")
    document, report = from_scene.read()
    entry = document.module("id1")
    assert entry.name == "tail"
    assert entry.side == "L"
    assert entry.settings["segments"] == 2
    assert report.is_lossless


def test_poses_survive_the_round_trip():
    entry = drawn_chain(2)
    joint = nodes.guide_nodes("id1")[("segment", 0)]
    cmds.xform(joint.long_name, worldSpace=True, translation=(5.0, 6.0, 7.0))
    document, _report = from_scene.read()
    assert document.module("id1").guide("segment", 0).position == pytest.approx((5.0, 6.0, 7.0))


def test_a_scene_without_breadcrumbs_still_recovers_the_modules():
    """Files drawn by an older build arrive forever; they must not be refused."""
    drawn_chain(2, name="tail")
    root = nodes.root_guide(nodes.guide_nodes("id1"), "fkchain")
    del root.meta[tags.ENTRY]
    document, report = from_scene.read()
    assert document.module("id1").module_type == "fkchain"
    assert document.module("id1").name == "fkchain"
    assert not report.is_lossless
    assert len(report.partial) == 1


def test_an_empty_scene_recovers_nothing_and_says_so():
    document, report = from_scene.read()
    assert document.modules == []
    assert not report.is_lossless
```

- [ ] **Step 2: Run them and watch them fail**

Run: `mayapy -m pytest tests/unit/test_from_scene_trigger.py -v`
Expected: FAIL — `ImportError: cannot import name 'from_scene'`.

- [ ] **Step 3: Write the reader**

Create `src/python/tik/trigger/guides/from_scene.py`:

```python
"""Read the scene's guide joints back into a document (spec 5).

The Maya half of recovery, and deliberately thin: it gathers records and hands
them to :mod:`tik.trigger.core.scene_recovery`, which does the thinking without
importing Maya.

This is the ONLY module that reads ``trg_entry``. Capture, reconcile, build and
the Designer never do -- the document is the authority everywhere except here,
where there is no document yet to be authoritative (spec 4.1).
"""

from __future__ import annotations

from tik.trigger.core.scene_recovery import SceneModule, document_from_scene
from tik.trigger.maya import tags

from . import nodes
from .snapshot import snapshot


def scene_modules(rendered: list) -> list:
    """One :class:`SceneModule` per instance in ``rendered``.

    The type and side come off any of the instance's joints; the breadcrumb only
    off its root, which is where regenerate stamps it.
    """
    seen: dict = {}
    for guide in rendered:
        if guide.instance_id in seen:
            continue
        joints = nodes.guide_nodes(guide.instance_id)
        any_joint = next(iter(joints.values()), None)
        if any_joint is None:
            continue
        meta = any_joint.meta.as_dict()
        module_type = meta.get(tags.MODULE, "")
        root = nodes.root_guide(joints, module_type) if module_type else None
        seen[guide.instance_id] = SceneModule(
            instance_id=guide.instance_id,
            module_type=module_type,
            side=meta.get(tags.SIDE, "C"),
            entry=root.meta.get(tags.ENTRY) if root is not None else None,
        )
    return list(seen.values())


def read() -> tuple:
    """``(GuideDocument, RecoveryReport)`` for whatever the scene holds."""
    rendered = snapshot()
    return document_from_scene(scene_modules(rendered), rendered)
```

`nodes.root_guide` calls `registry.get_module`, which raises on an unregistered type — guard by
passing the type through only when registered, or let `scene_modules` fall back to
`entry=None`. Confirm against `nodes.root_guide`'s actual behaviour and adjust rather than
guessing.

- [ ] **Step 4: Run them and watch them pass**

Run: `mayapy -m pytest tests/unit/test_from_scene_trigger.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Add the scene and session entry points**

In `src/python/tik/trigger/guides/scene.py`:

```python
    def snapshot_from_scene(self) -> tuple:
        """Read the scene into a fresh document. Commits nothing.

        The caller shows the report first: replacing the module list is
        destructive, so it never happens as a side effect of looking.
        """
        from .from_scene import read

        return read()
```

In `src/python/tik/trigger/session.py` — kept Maya-free by taking the document rather than
reading the scene itself:

```python
    def snapshot_guides_from_scene(self, document) -> None:
        """Replace this session's guides with ``document`` in one undo step.

        Read by the caller (``GuideScene.snapshot_from_scene``) so this module
        stays importable without Maya. No regenerate follows: the joints in the
        scene already *are* the rendering, and redrawing them would teleport
        guides that are exactly where the rigger left them.
        """
        self.document.guides = document
        self.touch()
```

- [ ] **Step 6: Test the commit path**

Add to `tests/unit/test_session_guides_trigger.py`:

```python
def test_snapshot_replaces_the_guides_in_one_undo_step(session):
    session.guides.add("fkchain", name="original")
    document, _report = session.guides.snapshot_from_scene()
    session.snapshot_guides_from_scene(document)
    assert [entry.name for entry in session.document.guides.modules] == ["original"]
    session.undo()
    assert [entry.name for entry in session.document.guides.modules] == ["original"]
```

Adapt the fixture and undo call to the ones already in that file.

Run: `make tests-unit`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/guides/from_scene.py src/python/tik/trigger/guides/scene.py src/python/tik/trigger/session.py tests/unit/test_from_scene_trigger.py tests/unit/test_session_guides_trigger.py
git commit -m "feat(tik.trigger): recover a session from the guides in the scene"
```

---

### Task 4: Optional sync

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py`, `src/python/tik/trigger/ui/designer/window.py`
- Test: `tests/integration/trigger/test_lockstep_trigger.py`

**Interfaces:**
- Produces: `GuideScene.auto_sync: bool` (default `True`). Tasks 5–8 read and write it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/trigger/test_lockstep_trigger.py`, under the existing header
explaining that these tests never call `sync()`:

```python
def test_auto_sync_off_still_captures_before_a_write(guides):
    """The fence for spec 3.1.

    Auto governs the *watcher*, never capture-before-regenerate. If capture ever
    moves behind the flag, changing a property throws the posing away again --
    the exact bug this codebase already shipped once.
    """
    guides.auto_sync = False
    handle = guides.add("fkchain", name="tail", segments=2)
    joint = guides.guide_nodes(handle.instance_id)[("segment", 0)]
    cmds.xform(joint.long_name, worldSpace=True, translation=(9.0, 0.0, 0.0))
    guides.write_settings(handle.instance_id, {"segments": 3})
    moved = guides.guide_nodes(handle.instance_id)[("segment", 0)]
    placed = cmds.xform(moved.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([9.0, 0.0, 0.0])


def test_auto_sync_defaults_to_on(guides):
    assert guides.auto_sync is True
```

- [ ] **Step 2: Run them and watch them fail**

Run: `mayapy -m pytest tests/integration/trigger/test_lockstep_trigger.py -k auto_sync -v`
Expected: FAIL — `AttributeError: 'GuideScene' object has no attribute 'auto_sync'`.

- [ ] **Step 3: Add the flag**

In `GuideScene.__init__` (`src/python/tik/trigger/guides/scene.py`):

```python
        # Governs ONE thing: whether a scene event may start a sync. It must
        # never gate the capture in _apply -- "a write always captures first;
        # Auto only decides whether the scene may start a sync" (spec 3.1).
        # Nothing in Maya fires when a guide is dragged, so a write that skipped
        # capture would redraw from stale records and discard the posing.
        self.auto_sync = True
```

Change nothing else in `scene.py`. `_apply` and `sync()` stay exactly as they are — `sync()`
remains unconditional, because pressing the button must work at any setting.

- [ ] **Step 4: Gate the watcher, not the write**

In `src/python/tik/trigger/ui/designer/window.py`, `_on_scene_event`:

```python
    def _on_scene_event(self, name: str) -> None:
        if name == "SelectionChanged":
            return  # selection is not synced; structure changes are
        if not self.guides.auto_sync:
            # Look, do not touch: report the drift and leave the document alone
            # until the rigger presses Sync.
            self._show_drift(self.guides.diff())
            return
        # Muted throughout: sync() deletes and recreates joints, which fires the
        # removal callback that brought us here and would re-enter.
        with self.watcher.mute():
            try:
                self.guides.sync()
            except Exception as error:  # noqa: BLE001 - keep the tool alive
                self.events.log(f"Guide sync failed: {error}", level="warning")
        self.refresh()
```

Add a placeholder `_show_drift` that Task 7 fills in:

```python
    def _show_drift(self, diff) -> None:
        """Report unabsorbed scene changes. Wired to the bar in Task 7."""
```

- [ ] **Step 5: Run the suites**

Run: `make tests-integration && make tests-unit`
Expected: PASS. Every pre-existing lockstep test must still pass — they exercise the auto-on
path and nothing about it changed.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/guides/scene.py src/python/tik/trigger/ui/designer/window.py tests/integration/trigger/test_lockstep_trigger.py
git commit -m "feat(tik.trigger): scene syncing can be turned off"
```

---

### Task 5: The action bar widget

**Files:**
- Create: `src/python/tik/trigger/ui/designer/action_bar.py`
- Create: `tests/ui/test_action_bar.py`

**Interfaces:**
- Produces: `DesignerActionBar(QtWidgets.QFrame)` with signals
  `select_requested`, `mirror_requested`, `build_selected_requested`, `build_all_requested`,
  `sync_requested`, `auto_sync_toggled(bool)`; and methods
  `set_selection(keys: list[str])`, `set_auto_sync(on: bool)`, `set_drift(count: int)`.

  Task 6 hosts it; Tasks 7 and 8 drive `set_drift` and `set_auto_sync`.

- [ ] **Step 1: Write the failing tests**

Create `tests/ui/test_action_bar.py`:

```python
"""The Guide Designer's bottom bar: three groups, split by what they act on."""

import pytest

from tik.shared.ui.Qt import QtWidgets
from tik.trigger.ui.designer.action_bar import DesignerActionBar


@pytest.fixture
def bar(qapp):
    widget = DesignerActionBar()
    yield widget
    widget.deleteLater()


def test_nothing_selected_disables_the_selection_group(bar):
    bar.set_selection([])
    assert bar.selection_label.text().endswith("none")
    assert not bar.select_button.isEnabled()
    assert not bar.mirror_button.isEnabled()
    assert not bar.build_selected_button.isEnabled()


def test_one_selection_names_it(bar):
    """The label is the answer to 'what will Mirror mirror?'."""
    bar.set_selection(["L_arm"])
    assert bar.selection_label.text().endswith("L_arm")
    assert bar.select_button.isEnabled()


def test_several_selections_are_counted(bar):
    bar.set_selection(["L_arm", "R_arm"])
    assert "2 modules" in bar.selection_label.text()


def test_build_all_never_depends_on_the_selection(bar):
    bar.set_selection([])
    assert bar.build_all_button.isEnabled()


def test_the_auto_checkbox_reports_but_does_not_echo(bar):
    seen = []
    bar.auto_sync_toggled.connect(seen.append)
    bar.auto_check.setChecked(False)
    assert seen == [False]
    seen.clear()
    bar.set_auto_sync(True)   # programmatic: must not re-emit
    assert seen == []


def test_drift_shows_a_pill_only_when_there_is_drift(bar):
    bar.set_drift(0)
    assert not bar.drift_pill.isVisible() or bar.drift_pill.text() == ""
    bar.set_drift(3)
    assert "3" in bar.drift_pill.text()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_action_bar.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the widget**

Create `src/python/tik/trigger/ui/designer/action_bar.py`:

```python
"""The Guide Designer's bottom bar (spec 2).

Six controls that do not share a scope, grouped so the difference is visible:
what acts on the SELECTION, what acts on the SCENE, and what acts on the
SESSION. Build all sits alone past a rule, where it cannot be read as "build
what I picked".

The bar knows nothing about the scene: it emits, the Designer acts.
"""

from __future__ import annotations

from tik.shared.ui.Qt import QtCore, QtWidgets


class DesignerActionBar(QtWidgets.QFrame):
    """The full-width action row under the Designer's four panes."""

    select_requested = QtCore.Signal()
    mirror_requested = QtCore.Signal()
    build_selected_requested = QtCore.Signal()
    build_all_requested = QtCore.Signal()
    sync_requested = QtCore.Signal()
    auto_sync_toggled = QtCore.Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # the Session sub-tab's build bar wears the same object name; one look
        # for both sub-tabs is the point
        self.setObjectName("BuildBar")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)

        self.selection_label = self._caption("SELECTION  none")
        self.select_button = QtWidgets.QPushButton("Select guides")
        self.mirror_button = QtWidgets.QPushButton("Mirror")
        self.build_selected_button = QtWidgets.QPushButton("Build selected")
        layout.addWidget(self.selection_label)
        for button in (self.select_button, self.mirror_button, self.build_selected_button):
            layout.addWidget(button)

        layout.addStretch(1)

        layout.addWidget(self._caption("SCENE"))
        self.sync_button = QtWidgets.QPushButton("Sync")
        self.sync_button.setToolTip("Read the guides in the scene into this session")
        layout.addWidget(self.sync_button)
        self.auto_check = QtWidgets.QCheckBox("Auto")
        self.auto_check.setChecked(True)
        self.auto_check.setToolTip(
            "Follow the scene automatically. Off, the session updates only when you press Sync."
        )
        layout.addWidget(self.auto_check)
        self.drift_pill = QtWidgets.QLabel("")
        self.drift_pill.setObjectName("FilterPillLabel")
        self.drift_pill.setVisible(False)
        layout.addWidget(self.drift_pill)

        rule = QtWidgets.QFrame()
        rule.setFrameShape(QtWidgets.QFrame.VLine)
        rule.setObjectName("BarRule")
        layout.addWidget(rule)

        layout.addWidget(self._caption("SESSION"))
        self.build_all_button = QtWidgets.QPushButton("▶  Build all")
        self.build_all_button.setObjectName("PrimaryButton")
        layout.addWidget(self.build_all_button)

        self.select_button.clicked.connect(self.select_requested)
        self.mirror_button.clicked.connect(self.mirror_requested)
        self.build_selected_button.clicked.connect(self.build_selected_requested)
        self.build_all_button.clicked.connect(self.build_all_requested)
        self.sync_button.clicked.connect(self.sync_requested)
        self.auto_check.toggled.connect(self.auto_sync_toggled)

        self.set_selection([])

    @staticmethod
    def _caption(text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setObjectName("FieldCaption")
        return label

    # ------------------------------------------------------------- state
    def set_selection(self, keys: list) -> None:
        """Name what the selection group is pointed at, and enable it or not.

        The label is why the buttons are greyed out -- today they simply are,
        with nothing on screen to say so.
        """
        if not keys:
            text = "none"
        elif len(keys) == 1:
            text = keys[0]
        else:
            text = f"{len(keys)} modules"
        self.selection_label.setText(f"SELECTION  {text}")
        for button in (self.select_button, self.mirror_button, self.build_selected_button):
            button.setEnabled(bool(keys))

    def set_auto_sync(self, on: bool) -> None:
        """Reflect the setting without reporting it back as a user action.

        The menu action and this checkbox are one setting with two front doors;
        without the block they would ping-pong.
        """
        self.auto_check.blockSignals(True)
        try:
            self.auto_check.setChecked(bool(on))
        finally:
            self.auto_check.blockSignals(False)
        self.sync_button.setProperty("quiet", bool(on))
        self._repolish(self.sync_button)

    def set_drift(self, count: int) -> None:
        """Report scene changes the document has not been told about."""
        self.drift_pill.setVisible(bool(count))
        self.drift_pill.setText(
            f"{count} module{'s' if count != 1 else ''} changed" if count else ""
        )
        self.sync_button.setProperty("alert", bool(count))
        self._repolish(self.sync_button)

    @staticmethod
    def _repolish(widget) -> None:
        """Qt does not restyle on a property change unless asked."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)
```

- [ ] **Step 4: Add the two style rules the bar needs**

In `src/python/tik/shared/ui/theme/__init__.py`, inside `TOOL_QSS`, next to the existing
`#BuildBar` rules:

```
#BarRule { color: #353535; max-width: 1px; }
#BuildBar QPushButton[quiet="true"] { color: #8f8f8f; }
#BuildBar QPushButton[alert="true"] { border-color: #FE7E00; color: #e0c8a8; }
#BuildBar #FilterPillLabel { background-color: #3a2e1f; border: 1px solid #FE7E00; border-radius: 9px; padding: 2px 10px; }
```

- [ ] **Step 5: Run them and watch them pass**

Run: `make tests-ui`
Expected: PASS (6 new tests, 102 existing still passing).

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/ui/designer/action_bar.py src/python/tik/shared/ui/theme/__init__.py tests/ui/test_action_bar.py
git commit -m "feat(tik.trigger): a scope-split action bar for the Guide Designer"
```

---

### Task 6: Host the bar; empty the properties panel

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/window.py`
- Test: `tests/ui/test_designer.py` (add to the existing file)

**Interfaces:**
- Consumes: `DesignerActionBar` (Task 5), the existing `select_current`, `mirror_current`,
  `test_build` commands.
- Produces: `GuideDesigner.action_bar`. The four `*_button` attributes move off the designer
  onto the bar — **update every existing reference**.

- [ ] **Step 1: Find every reference before breaking them**

Run:
```bash
grep -rn "select_button\|mirror_button\|test_button\|build_all_button" src tests --include=*.py
```
Expected: the definitions and connections in `window.py`, plus any UI tests. Note them all —
this is the step that stops the bad-cut failure that has happened in this codebase before.

- [ ] **Step 2: Write the failing test**

Add to `tests/ui/test_designer.py`:

```python
def test_the_action_buttons_left_the_properties_panel(designer):
    """They belong to the window now, not to a 270px column."""
    assert not hasattr(designer, "select_button")
    assert designer.action_bar is not None
    assert designer.action_bar.parent() is not designer.properties


def test_selecting_a_module_names_it_in_the_bar(designer):
    handle = designer.guides.add("fkchain", name="tail", side="L")
    designer.refresh()
    designer._set_current(handle)
    assert designer.action_bar.selection_label.text().endswith("L_tail")


def test_the_bar_spans_the_window_not_a_pane(designer):
    """It is a sibling of the splitter, so it is as wide as the page."""
    layout = designer.layout()
    assert layout.indexOf(designer.action_bar) > layout.indexOf(designer.splitter)
```

Adapt the `designer` fixture name and the module type to the ones already in that file.

- [ ] **Step 3: Run it and watch it fail**

Run: `make tests-ui`
Expected: FAIL — `AttributeError: 'GuideDesigner' object has no attribute 'action_bar'`.

- [ ] **Step 4: Remove the button row**

In `window.py`, `_build_central`, delete this block entirely:

```python
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.select_button = QtWidgets.QPushButton("Select guides")
        self.mirror_button = QtWidgets.QPushButton("Mirror")
        self.test_button = QtWidgets.QPushButton("Build selected")
        self.build_all_button = QtWidgets.QPushButton("Build all")
        self.build_all_button.setObjectName("PrimaryButton")
        for button in (self.select_button, self.mirror_button, self.test_button, self.build_all_button):
            buttons.addWidget(button)
        props.addLayout(buttons)
```

and these four connections further down:

```python
        self.select_button.clicked.connect(self.select_current)
        self.mirror_button.clicked.connect(self.mirror_current)
        self.test_button.clicked.connect(lambda: self.test_build())
        self.build_all_button.clicked.connect(lambda: self.test_build(all_modules=True))
```

- [ ] **Step 5: Add the bar below the splitter**

Replace the page layout at the end of `_build_central`:

```python
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.splitter, 1)
        self.action_bar = DesignerActionBar(self)
        layout.addWidget(self.action_bar)
```

and wire it:

```python
        self.action_bar.select_requested.connect(self.select_current)
        self.action_bar.mirror_requested.connect(self.mirror_current)
        self.action_bar.build_selected_requested.connect(lambda: self.test_build())
        self.action_bar.build_all_requested.connect(lambda: self.test_build(all_modules=True))
        self.action_bar.sync_requested.connect(self.sync_now)
        self.action_bar.auto_sync_toggled.connect(self.set_auto_sync)
```

Add the import at the top: `from .action_bar import DesignerActionBar`.

- [ ] **Step 6: Keep the label in step with the selection**

At the end of `_set_current`:

```python
        self.action_bar.set_selection(
            [handle.key for handle in (self._multi or ([handle] if handle else []))]
        )
```

- [ ] **Step 7: Add the two commands the bar calls**

In `src/python/tik/trigger/ui/designer/commands.py`:

```python
    def sync_now(self) -> None:
        """Pull the scene into the session, whatever the Auto setting says."""
        with self.watcher.mute():
            try:
                self.guides.sync()
            except Exception as error:  # noqa: BLE001 - keep the tool alive
                self.events.log(f"Guide sync failed: {error}", level="warning")
        self.refresh()
        self._show_drift(self.guides.diff())

    def set_auto_sync(self, on: bool) -> None:
        """One setting, three front doors: the checkbox, the menu, and here."""
        self.guides.auto_sync = bool(on)
        self.action_bar.set_auto_sync(on)
        if hasattr(self, "auto_sync_action"):
            self.auto_sync_action.blockSignals(True)
            try:
                self.auto_sync_action.setChecked(bool(on))
            finally:
                self.auto_sync_action.blockSignals(False)
        if on:
            self.sync_now()
```

- [ ] **Step 8: Persist the setting (spec 3.2)**

This is the app's **first** persisted preference — `recent_files` is in-memory only — so keep
the mechanism as small as the need and do not build a preferences framework around it.

Write the failing test first, in `tests/ui/test_designer.py`:

```python
def test_auto_sync_survives_a_relaunch(designer, qapp):
    """A working habit, not rig data: it belongs to the user, not the .tr."""
    from tik.shared.ui.Qt import QtCore

    designer.set_auto_sync(False)
    stored = QtCore.QSettings("tikworks", "trigger").value("designer/auto_sync")
    assert stored in (False, "false")
```

Then in `commands.py`, extend `set_auto_sync`:

```python
        QtCore.QSettings("tikworks", "trigger").setValue("designer/auto_sync", bool(on))
```

and read it once in `GuideDesigner.__init__`, after `_build_central`:

```python
        # QSettings hands back a string on some platforms, so normalise rather
        # than trusting the type.
        stored = QtCore.QSettings("tikworks", "trigger").value("designer/auto_sync", True)
        self.set_auto_sync(stored not in (False, "false", "0", 0))
```

Run: `make tests-ui`
Expected: PASS.

- [ ] **Step 9: Run everything**

Run: `make tests-ui`
Expected: PASS. Then `make tests-unit && make tests-integration` — the button move must not
touch either, and a failure there means something outside the UI referenced those buttons.

- [ ] **Step 10: Commit**

```bash
git add src/python/tik/trigger/ui/designer/window.py src/python/tik/trigger/ui/designer/commands.py tests/ui/test_designer.py
git commit -m "refactor(tik.trigger): the Designer's verbs move to a window-wide bar"
```

---

### Task 7: The drift indicator

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/window.py`
- Test: `tests/ui/test_designer.py`

**Interfaces:**
- Consumes: `GuideDiff.structural`, `GuideDiff.drifted` (`core/reconcile.py`);
  `DesignerActionBar.set_drift`.

- [ ] **Step 1: Write the failing test**

```python
def test_drift_counts_structure_and_pose_together(designer):
    """The pill reports work the document has not been told about -- posing included."""
    from tik.trigger.core.reconcile import GuideDiff, ModuleDiff

    diff = GuideDiff(modules={
        "a": ModuleDiff(missing=["root"]),      # structural
        "b": ModuleDiff(drifted=["root"]),      # pose only
    })
    designer._show_drift(diff)
    assert "2" in designer.action_bar.drift_pill.text()
```

Check `ModuleDiff`'s real field names in `core/reconcile.py` and use them — the names above are
illustrative.

- [ ] **Step 2: Run it and watch it fail**

Run: `make tests-ui`
Expected: FAIL — the pill is empty (`_show_drift` is still the Task 4 placeholder).

- [ ] **Step 3: Fill in the placeholder**

```python
    def _show_drift(self, diff) -> None:
        """Report scene changes the document has not absorbed.

        Structural staleness *and* pose drift, unlike ``diff_summary``, which
        deliberately omits drift: that describes a redraw about to happen, this
        describes the rigger's own work waiting to be picked up.
        """
        self.action_bar.set_drift(len(set(diff.structural) | set(diff.drifted)))
```

- [ ] **Step 4: Run it and watch it pass**

Run: `make tests-ui`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/ui/designer/window.py tests/ui/test_designer.py
git commit -m "feat(tik.trigger): the bar reports scene changes it has not absorbed"
```

---

### Task 8: Menu commands and the F5 clash

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py`
- Test: `tests/ui/test_main_window.py`

**Interfaces:**
- Consumes: `_designer_call` (already in `main.py`), `sync_now`, `set_auto_sync` (Task 6).
- Produces: `MainWindow.auto_sync_action` (checkable).

- [ ] **Step 1: Write the failing tests**

```python
def test_redraw_views_keeps_f5_and_sync_takes_f6(window):
    labels = {action.text(): action for action in window._menus["&Guides"].actions()}
    assert "Sync From Scene" in labels
    assert labels["Sync From Scene"].shortcut().toString() == "F6"
    layout = {action.text(): action for action in window._menus["Layout"].actions()}
    assert "Redraw Views" in layout
    assert "Refresh" not in layout
    assert layout["Redraw Views"].shortcut().toString() == "F5"


def test_snapshot_is_a_menu_command_not_a_button(window):
    labels = [action.text() for action in window._menus["&Guides"].actions()]
    assert "Snapshot Guides From Scene…" in labels


def test_auto_sync_action_is_checkable_and_starts_on(window):
    assert window.auto_sync_action.isCheckable()
    assert window.auto_sync_action.isChecked()
```

Adapt the `window` fixture to the one already in that file.

- [ ] **Step 2: Run them and watch them fail**

Run: `make tests-ui`
Expected: FAIL — the actions do not exist.

- [ ] **Step 3: Add the scene-boundary group**

In `_build_menus`, replace the block between `Build All Guides` and `Clear Scene Guides`:

```python
        guides_menu.addSeparator()
        # The four verbs that cross the session/scene line, together: pull from
        # the scene, rebuild from the scene, wipe the scene.
        self._action(guides_menu, "Sync From Scene", lambda: self._designer_call("sync_now"), "F6")
        self.auto_sync_action = self._action(
            guides_menu, "Auto Sync",
            lambda: self._designer_call("set_auto_sync", self.auto_sync_action.isChecked()),
            checkable=True,
        )
        self.auto_sync_action.setChecked(True)
        self._action(
            guides_menu, "Snapshot Guides From Scene…",
            lambda: self._designer_call("snapshot_guides"),
        )
        guides_menu.addSeparator()
        self._action(guides_menu, "Clear Scene Guides", lambda: self._designer_call("clear_guides"))
```

- [ ] **Step 4: Resolve the F5 clash**

In the Layout submenu, rename the entry:

```python
        # Was "Refresh". It redraws the UI from the document; "Sync From Scene"
        # runs the other way. Two neighbouring commands that both read as
        # "update" is the ambiguity this work exists to remove.
        self._action(layout_menu, "Redraw Views", lambda: self._designer_call("refresh"), "F5")
```

The method stays `refresh` — only the label and the user-facing name change.

- [ ] **Step 5: Run them and watch them pass**

Run: `make tests-ui`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/ui/main.py tests/ui/test_main_window.py
git commit -m "feat(tik.trigger): scene-boundary commands get their own menu group"
```

---

### Task 9: The snapshot dialog

**Files:**
- Create: `src/python/tik/trigger/ui/designer/snapshot_dialog.py`
- Modify: `src/python/tik/trigger/ui/designer/commands.py`
- Test: `tests/ui/test_snapshot_dialog.py`

**Interfaces:**
- Consumes: `RecoveryReport` (Task 2), `GuideScene.snapshot_from_scene` (Task 3),
  `Session.snapshot_guides_from_scene` (Task 3).
- Produces: `SnapshotDialog(report, parent=None)` — standard `QDialog`, `exec()` returns
  `Accepted`/`Rejected`.

- [ ] **Step 1: Write the failing tests**

```python
"""The dialog that says what a snapshot can and cannot bring back."""

import pytest

from tik.trigger.core.scene_recovery import RecoveredModule, RecoveryReport
from tik.trigger.ui.designer.snapshot_dialog import SnapshotDialog


def report(complete=2, partial=0):
    modules = [
        RecoveredModule(f"c{i}", f"mod{i}", "fkchain", True, 4) for i in range(complete)
    ] + [
        RecoveredModule(f"p{i}", f"old{i}", "fkchain", False, 4) for i in range(partial)
    ]
    return RecoveryReport(modules=modules, guide_count=4 * len(modules))


def test_a_lossless_scene_says_nothing_was_lost(qapp):
    dialog = SnapshotDialog(report(complete=2))
    assert "2 modules" in dialog.found_label.text()
    assert not dialog.losses_group.isVisible() or dialog.losses_group.isHidden()
    dialog.deleteLater()


def test_an_older_scene_lists_what_it_cannot_recover(qapp):
    """Old files arrive forever; the dialog must degrade honestly."""
    dialog = SnapshotDialog(report(complete=1, partial=2))
    text = dialog.losses_label.text()
    assert "2" in text
    assert "settings" in text.lower()
    assert "connections" in text.lower()
    dialog.deleteLater()


def test_an_empty_scene_cannot_be_confirmed(qapp):
    dialog = SnapshotDialog(RecoveryReport())
    assert not dialog.confirm_button.isEnabled()
    dialog.deleteLater()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `make tests-ui`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the dialog**

Create `src/python/tik/trigger/ui/designer/snapshot_dialog.py`:

```python
"""The report a snapshot shows before it replaces anything (spec 5.3).

Snapshot is destructive to the module list, so it reports first. The part that
matters is the honest degradation: a scene drawn by an older build carries no
``trg_entry`` breadcrumb, and this dialog says exactly what will not come back
rather than quietly restoring a module called "fkchain" with default settings.
Scenes are files, and old files keep arriving.
"""

from __future__ import annotations

from tik.shared.ui.Qt import QtWidgets

#: What a module without a breadcrumb loses. Kept as prose, not a table: it is
#: read once, under pressure, by someone who has already lost their session.
LOSSES = (
    "names fall back to the module type, settings reset to their defaults, "
    "input connections are lost, and the graph will be auto-laid out"
)


class SnapshotDialog(QtWidgets.QDialog):
    """Show a ``RecoveryReport`` and ask whether to commit it."""

    def __init__(self, report, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Snapshot Guides From Scene")
        self.report = report
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)

        blurb = QtWidgets.QLabel(
            "Read the guide joints in the Maya scene and rebuild this session's "
            "modules from them. The session's current modules are replaced."
        )
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        count = len(report.modules)
        self.found_label = QtWidgets.QLabel(
            f"{count} module{'s' if count != 1 else ''}"
            f"  ·  {report.guide_count} guide joints"
        )
        self.found_label.setObjectName("PanelTitle")
        layout.addWidget(self.found_label)

        recovered = QtWidgets.QLabel("RECOVERED FROM THE SCENE")
        recovered.setObjectName("FieldCaption")
        layout.addWidget(recovered)
        self.recovered_label = QtWidgets.QLabel(self._recovered_text())
        self.recovered_label.setWordWrap(True)
        layout.addWidget(self.recovered_label)

        # Only ever shown when something really is lost: a permanently visible
        # warning teaches people to stop reading warnings.
        self.losses_group = QtWidgets.QWidget()
        losses_layout = QtWidgets.QVBoxLayout(self.losses_group)
        losses_layout.setContentsMargins(0, 0, 0, 0)
        losses_layout.setSpacing(4)
        caption = QtWidgets.QLabel("NOT STORED IN THE SCENE")
        caption.setObjectName("FieldCaption")
        losses_layout.addWidget(caption)
        self.losses_label = QtWidgets.QLabel(self._losses_text())
        self.losses_label.setObjectName("FilterPillLabel")
        self.losses_label.setWordWrap(True)
        losses_layout.addWidget(self.losses_label)
        self.losses_group.setVisible(bool(report.partial or report.unknown_types))
        layout.addWidget(self.losses_group)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.confirm_button = QtWidgets.QPushButton(
            f"Snapshot {count} module{'s' if count != 1 else ''}"
        )
        self.confirm_button.setObjectName("PrimaryButton")
        self.confirm_button.setEnabled(bool(count))
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)

    def _recovered_text(self) -> str:
        whole = len(self.report.complete)
        if not self.report.modules:
            return "No tagged guide joints were found in the scene."
        lines = [
            f"Guide positions, rotations and attributes  ·  "
            f"{self.report.guide_count} joints",
            "Module type, side and guide hierarchy  ·  "
            f"{len(self.report.modules)} modules",
        ]
        if whole:
            lines.append(
                f"Names, settings and connections  ·  {whole} of "
                f"{len(self.report.modules)} modules"
            )
        return "\n".join(lines)

    def _losses_text(self) -> str:
        parts = []
        if self.report.partial:
            count = len(self.report.partial)
            parts.append(
                f"{count} module{'s' if count != 1 else ''} "
                f"({', '.join(item.key for item in self.report.partial)}) "
                f"came from an older scene and carry no saved entry — {LOSSES}."
            )
        if self.report.unknown_types:
            parts.append(
                "Skipped, because this build has no such module: "
                + ", ".join(self.report.unknown_types)
                + "."
            )
        return " ".join(parts)
```

- [ ] **Step 4: Wire the command**

In `commands.py` — named `snapshot_guides`, **not** `snapshot_from_scene`, so it cannot be
confused with `GuideScene.snapshot_from_scene` that it calls:

```python
    def snapshot_guides(self) -> None:
        """Rebuild this session's modules from the guides in the scene.

        Reads and reports first: replacing the module list is destructive, so it
        never happens as a side effect of opening the dialog.
        """
        from .snapshot_dialog import SnapshotDialog

        document, report = self.guides.snapshot_from_scene()
        dialog = SnapshotDialog(report, self)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        session = self.guides.session
        if session is None:
            self.events.log("Snapshot needs a session.", level="warning")
            return
        session.snapshot_guides_from_scene(document)
        self.refresh()
        self._show_drift(self.guides.diff())
        self.events.log(f"Snapshot restored {len(report.modules)} module(s).")
```

Add the public accessor to `GuideScene` rather than reaching into `_session`:

```python
    @property
    def session(self):
        """The session that owns these guides, or None when free-standing."""
        return self._session
```

- [ ] **Step 5: Run them and watch them pass**

Run: `make tests-ui`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/ui/designer/snapshot_dialog.py src/python/tik/trigger/ui/designer/commands.py tests/ui/test_snapshot_dialog.py
git commit -m "feat(tik.trigger): Snapshot Guides From Scene reports before it acts"
```

---

### Task 10: Stub hygiene and full verification

**Files:**
- Modify: `tests/ui/stub.py`, `CLAUDE.md`

- [ ] **Step 1: Bring the stub level with `GuideScene`**

Add to `StubScene`:

```python
        self.auto_sync = True   # in __init__

    def diff(self):
        from tik.trigger.core.reconcile import GuideDiff

        return GuideDiff()

    def snapshot_from_scene(self):
        from tik.trigger.core.guide_document import GuideDocument
        from tik.trigger.core.scene_recovery import RecoveryReport

        return GuideDocument(), RecoveryReport()
```

- [ ] **Step 2: Delete the method the real scene no longer has**

Remove `StubScene.settings_plug` — `GuideScene` lost it when settings stopped binding to Maya
plugs. A stub outliving its original is how the unbound-`GuideScene` bug stayed hidden, so it
goes now rather than later.

Run: `grep -rn "settings_plug" src tests --include=*.py`
Expected: no hits after the deletion. If the UI still calls it, that call is dead too.

- [ ] **Step 3: Point CLAUDE.md at the new spec**

In the tik.trigger **Design specs** list, add before the guide-ownership entry:

```
`docs/superpowers/specs/2026-09-01-optional-sync-and-snapshot-design.md` (optional sync, the
scope-split action bar, the `trg_entry` breadcrumb and Snapshot From Scene — **amends the
guide-ownership spec's sections 5 and 6**),
```

- [ ] **Step 4: Run every suite**

```bash
make tests-unit
make tests-integration
make tests-ui
```
Expected: unit ≥ 1112 + 11 new, integration ≥ 201 + 2 new, UI ≥ 102 + 15 new. **All passing.**
Report the real counts; do not claim a number you have not seen.

- [ ] **Step 5: Verify by hand in Maya**

The suites cannot catch a bar that is laid out wrong. In a real Maya session:
1. Build a few modules, pose a guide, change a property — the pose holds.
2. Untick `Auto`, move a guide in the outliner — the pill appears with a count; the document
   does not move. Press `Sync` — the pill clears.
3. `Guides ▸ Snapshot Guides From Scene…` on a scene whose session was never saved — the
   dialog reports lossless, and confirming restores names, settings and connections.
4. `Ctrl+Z` after a snapshot returns the previous module list.

- [ ] **Step 6: Commit**

```bash
git add tests/ui/stub.py CLAUDE.md
git commit -m "test(tik.trigger): the UI stub matches the scene it stands in for"
```

---

### Task 11: Visual parity with the mockups

The mockups read better than the shipped UI, and this task closes the gap rather than leaving
it as taste. It is last because it needs the new bar in place, but its **Step 2 font fix is
tool-wide and should be verified first** — every screenshot after it changes.

**Files:**
- Create: `tools/uishot.py`
- Modify: `src/python/tik/shared/ui/theme/theme.qss`, `src/python/tik/trigger/ui/designer/window.py`, `src/python/tik/trigger/ui/main.py`
- Reference: the mockup artboards at
  `C:/Users/kutlu/AppData/Local/Temp/claude/D--dev-tikworks/b2d5dc24-b040-4aec-897e-a45f4af00ca9/scratchpad/designer-bar/*.dc.html`
  and the published canvas <https://claude.ai/code/artifact/12479ad4-4aed-40a1-b493-58395c070185>

**Interfaces:**
- Produces: `tools/uishot.py` — `python tools/uishot.py <out.png> [--widget designer|bar|window]`,
  runnable headless under `mayapy` *and* pasteable into a live Maya session.

**Two facts established before this plan was written — do not re-derive them, and do not
"fix" the second:**

1. **The tool renders in Tahoma 8.** `theme.qss` says `font-family: "Roboto"` with no fallback
   stack, and Roboto is not installed on this machine (nor in Maya's font database, checked:
   187 families, `Roboto: False`, `Segoe UI: True`). Qt therefore falls back to its default,
   Tahoma. The mockups used Roboto with a Segoe UI fallback. This is the single biggest
   contributor to the difference in look.
2. **`letter-spacing` DOES work in Qt Style Sheets.** Measured: `SELECTION` is 49px without it
   and 58px with it, and `font().letterSpacing()` reads back `1.0`. An earlier suspicion that
   Qt ignored it was wrong. Leave the caption tracking alone.

**Screenshots: headless shows layout, live Maya shows type.** The headless `mayapy` +
`QT_QPA_PLATFORM=offscreen` environment has **zero** fonts (`QFontDatabase.families()` returns
an empty list), so text renders as tofu boxes there. Headless captures are still valid for
geometry, margins, alignment and colour — just never for typography. For type, run the same
script inside the live Maya session.

- [ ] **Step 1: Write the screenshot harness**

Create `tools/uishot.py`:

```python
"""Grab a Trigger UI widget to a PNG, for comparing against the design mockups.

Two environments, two purposes:

* headless (``mayapy tools/uishot.py out.png``) has **no fonts at all**, so text
  comes out as tofu. Use it for geometry: margins, alignment, control heights,
  colour.
* inside a running Maya, the same ``capture()`` has the real font stack. Use it
  for anything about type.

Not a test: nothing here asserts. It produces an image for a human -- or a model
with eyes -- to compare against the mockups.
"""

from __future__ import annotations

import argparse
import os
import sys


def capture(out_path: str, which: str = "bar", width: int = 1240, height: int = 760) -> str:
    """Render one widget offscreen and save it. Returns the path."""
    from tik.shared.ui import theme
    from tik.shared.ui.Qt import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if which == "bar":
        from tik.trigger.ui.designer.action_bar import DesignerActionBar

        widget = DesignerActionBar()
        widget.set_selection(["L_arm"])
        widget.resize(width, widget.sizeHint().height())
    else:
        from tik.trigger.ui.designer import GuideDesigner

        widget = GuideDesigner()
        widget.resize(width, height)
    theme.apply(widget)
    widget.show()
    app.processEvents()
    widget.grab().save(out_path)
    widget.close()
    return out_path


if __name__ == "__main__":
    os.environ.setdefault("TIK_TESTS_NO_MAYA", "1")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--widget", default="bar", choices=("bar", "designer"))
    args = parser.parse_args()
    print("saved:", capture(args.out, args.widget))
```

The `designer` mode needs a `GuideScene`, which needs Maya — headless it will only work if the
Designer is constructed with the UI test stub. Wire it the way `tests/ui/conftest.py` does, or
restrict `designer` mode to the live-Maya path and say so in the docstring. Do not leave a mode
that raises.

- [ ] **Step 2: Fix the font fallback**

In `src/python/tik/shared/ui/theme/theme.qss`, first rule:

```
QWidget { background-color: rgb(36,36,36); color: white; selection-background-color: #FE7E00; font-family: "Roboto", "Segoe UI", sans-serif; }
```

Roboto is still preferred — a studio that installs it gets it. Everyone else now lands on Segoe
UI instead of Tahoma.

Verify in the live Maya session rather than headless (headless has no fonts to resolve):

```python
from PySide6 import QtGui, QtWidgets
from tik.shared.ui import theme
label = QtWidgets.QLabel("Build all")
label.setStyleSheet(theme.stylesheet())
label.show(); QtWidgets.QApplication.processEvents()
print(QtGui.QFontInfo(label.font()).family())   # expect: Segoe UI
label.close()
```

Expected: `Segoe UI`, not `Tahoma`.

- [ ] **Step 3: Capture the bar and compare it against the mockup**

```bash
PYTHONPATH=src/python mayapy tools/uishot.py <scratch>/bar_real.png --widget bar
```

Open `bar_real.png` beside `OptionB.dc.html`'s bar and check, in this order — geometry first,
because the headless capture is trustworthy for it:

| Property | Mockup |
|---|---|
| Bar height | 34px content + 1px top rule |
| Margins | `10, 7, 10, 7` |
| Spacing between controls | `8` |
| Button min width | `110` (`Sync` `92`) |
| Caption colour / size | `#7b7b7b`, 10px, 1px tracking |
| Group rule | 1px `#353535`, full bar height |
| Primary button | `#FE7E00` ground, `#1a1a1a` text |

Fix what differs **in the widget**, not in the mockup. Record each difference found and what
changed, so Step 6 can report something concrete.

- [ ] **Step 4: Check the tab strips the user called out**

The session tabs and sub-tabs were named specifically. Compare `Main.dc.html`'s chrome against
a live-Maya capture of the real window:

| Property | Mockup |
|---|---|
| Tab padding | `5px 12px` |
| Selected tab | `#2a2a2a` ground, `#ececec` text, 2px `#FE7E00` top border |
| Unselected tab | `#1f1f1f` ground, `#8a8a8a` text, 1px `#303030` border, no bottom border |
| Tab strip ground | `#151515` |
| Gap between tabs | 2px |
| Sub-tab strip | inset 14px from the left, 1px `#303030` bottom rule |

`QTabWidget.setDocumentMode(True)` is already set on the session tabs (`main.py`) and changes
how the frame paints — if the strip cannot be made to match with document mode on, note that
rather than fighting it, and say which of the two looks better.

- [ ] **Step 5: Run the suites**

Run: `make tests-ui && make tests-unit`
Expected: PASS. The font change touches every widget, so a UI test asserting a pixel width or
a `sizeHint` may legitimately need updating — update it, and say which and why. A test failing
because text got wider is a real signal, not noise to suppress.

- [ ] **Step 6: Commit**

```bash
git add tools/uishot.py src/python/tik/shared/ui/theme/theme.qss src/python/tik/trigger/ui/designer/window.py src/python/tik/trigger/ui/main.py
git commit -m "fix(tik.shared): the theme falls back to Segoe UI instead of Tahoma"
```
