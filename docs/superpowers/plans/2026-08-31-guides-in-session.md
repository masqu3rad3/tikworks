# Guides in the Session Implementation Plan

**Status: complete** (2026-08-31). All 6 tasks landed; unit 1124, integration 178, UI 80 passing.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move guide data into the `.tr` session document so a session is a self-contained rig description, and give each session its own Guide Designer and its own checkout of the Maya scene — making "whose guides are these?" a well-formed question.

**Architecture:** `Document` gains a `guides` field carrying a serialized `GuideDocument` (schema 4 → 5). `Session` gains `capture_guides()` / `checkout_guides()`, the two directions of a working-copy checkout, plus a session id stamped on the scene's guide holder so a scene that belongs to another session is reported rather than silently adopted. In the UI the Guide Designer mode's page becomes a stack that follows the active session tab, so each session owns a Designer and a checkout.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), pytest, tik.maya, PySide (Qt).

**Spec:** `docs/superpowers/specs/2026-08-31-guide-ownership-and-lockstep-design.md` (items 6–7 of §9)

**Depends on:** `docs/superpowers/plans/2026-08-31-guide-ownership-and-lockstep.md` (items 1–5, complete).

## Deviation from the spec, deliberate

Spec §6.4 says the Designer "becomes a view owned by `SessionView`, one per tab", replacing the window-level mode. Literally restructuring the mode bar is large churn for the same outcome. Instead **the Designer mode stays where it is, and its page becomes a `QStackedWidget` that follows the active session tab.** Each session gets its own `GuideDesigner` instance and its own checkout; tear-off is unaffected. The observable behaviour is what §6.4 asks for; the widget tree is cheaper.

## Global Constraints

- **Layering:** `tik/trigger/core` stays pure Python — no `maya`, no `tik.maya`, no Qt, no `tik.shared`. Enforced by `tests/unit/test_import_boundaries.py`. `core/document.py` must remain importable without Maya.
- **`session.py` must stay Maya-free at import time.** `tests/ui` runs with `TIK_TESTS_NO_MAYA=1` and imports `ui/main.py`, which imports `session`. Every Maya touch goes in a function-level import, as `GuideScene` already does.
- **No backward compatibility.** The tool is unreleased. `Document.from_dict` raises on a schema newer than it knows; it does not migrate older ones.
- **Consume tik.maya** — no raw `maya.cmds` / `OpenMaya` outside `tik.maya` and the documented guide-layer exceptions.
- **Identity is the uuid.** Connection sources and layout stay id-keyed in storage; display keys appear only at read boundaries.
- **Test command (one file):** `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/<file>.py -q`
- **Test command (suites):** `mayapy tests/unit/invoke.py`, `mayapy tests/integration/invoke.py`, and for Qt: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui -q` (all with the PYTHONPATH above).

---

### Task 1: `Document` carries guides (schema 5)

**Files:**
- Modify: `src/python/tik/trigger/core/document.py`
- Test: `tests/unit/test_document_trigger.py`

**Interfaces:**
- Produces: `Document(schema=5, meta={}, actions=[], guides={})`; `SCHEMA_VERSION = 5`.
- `guides` is a serialized `GuideDocument` (`GuideDocument.to_dict()`), or `{}` when the session has none.
- `is_modified` needs no change: it already compares `document.to_dict()`, so a guide edit makes the session dirty for free.

- [x] **Step 1: Write the failing test**

Append to `tests/unit/test_document_trigger.py`:

```python
def test_document_carries_guides_and_round_trips(tmp_path):
    from tik.trigger.core.document import SCHEMA_VERSION, Document
    from tik.trigger.core.guide_document import GuideDocument, GuideRecord, ModuleEntry

    guides = GuideDocument(modules=[ModuleEntry(
        "id1", "fkchain", "tail", "C",
        settings={"segments": 3},
        guides=[GuideRecord("root", position=(1.0, 2.0, 3.0))],
    )])
    document = Document(guides=guides.to_dict())
    path = document.save(tmp_path / "hero.tr")
    restored = Document.load(path)
    assert restored.schema == SCHEMA_VERSION
    recovered = GuideDocument.from_dict(restored.guides)
    assert recovered.module("id1").name == "tail"
    assert recovered.module("id1").guide("root").position == (1.0, 2.0, 3.0)


def test_a_session_with_no_guides_stores_an_empty_dict():
    from tik.trigger.core.document import Document

    assert Document().guides == {}
    assert Document.from_dict({"actions": []}).guides == {}


def test_editing_guides_makes_the_document_differ():
    """This is what gives the session its dirty flag for guide work."""
    from tik.trigger.core.document import Document

    document = Document()
    before = document.to_dict()
    document.guides = {"schema": 1, "modules": [], "scene_groups": [],
                       "positions": {}, "collapse": {}}
    assert document.to_dict() != before
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_document_trigger.py -q`
Expected: FAIL — `TypeError: Document.__init__() got an unexpected keyword argument 'guides'`

- [x] **Step 3: Implement**

In `src/python/tik/trigger/core/document.py`:

- `SCHEMA_VERSION = 5`
- Add to the `Document` dataclass, after `actions`:

```python
    #: Serialized ``GuideDocument`` — the rig's guides travel with the session,
    #: so a ``.tr`` is a self-contained rig description and there is no version
    #: skew between it and a separate guides file.
    guides: dict = field(default_factory=dict)
```

- In `to_dict`, add `"guides": copy.deepcopy(self.guides),`
- In `from_dict`, add `guides=dict(data.get("guides") or {}),`

- [x] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_document_trigger.py tests/unit/test_import_boundaries.py -q`
Expected: PASS

- [x] **Step 5: Run the unit suite**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy tests/unit/invoke.py`
Expected: PASS — the schema bump is additive.

- [x] **Step 6: Commit**

```bash
git add src/python/tik/trigger/core/document.py tests/unit/test_document_trigger.py
git commit -m "feat(tik.trigger): the session document carries its guides (schema 5)"
```

---

### Task 2: Session capture and checkout

The two directions of the working-copy relationship, plus the stamp that makes "whose guides are these?" answerable.

**Files:**
- Modify: `src/python/tik/trigger/session.py`
- Modify: `src/python/tik/trigger/maya/tags.py` (the stamp key)
- Modify: `src/python/tik/trigger/guides/document_store.py` (read/write the stamp)
- Test: `tests/unit/test_session_guides_trigger.py`

**Interfaces:**
- `tags.SESSION = "trg_session"` on the guide holder.
- `document_store.read_stamp() -> str`, `document_store.write_stamp(session_id) -> None`
- `Session.session_id -> str` — stable, stored in `document.meta["session_id"]`, minted on first use.
- `Session.capture_guides() -> bool` — scene → `document.guides`; True when it changed.
- `Session.checkout_guides(force=False) -> None` — `document.guides` → scene, regenerating; raises `SessionError` when the scene is stamped for a different session unless `force`.
- `Session.owns_scene_guides -> bool` — the stamp matches (or the scene has none).
- `save()` calls `capture_guides()` first, but only when this session owns the scene's guides.

- [x] **Step 1: Write the failing test**

Create `tests/unit/test_session_guides_trigger.py`:

```python
"""The session owns its guides; the scene is a checkout of one at a time."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core.exceptions import SessionError
from tik.trigger.guides import GuideScene
from tik.trigger.session import Session


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def test_a_session_has_a_stable_id():
    session = Session()
    assert session.session_id
    assert session.session_id == session.session_id
    assert session.document.meta["session_id"] == session.session_id


def test_capture_puts_the_scene_guides_into_the_document():
    session = Session()
    scene = GuideScene()
    scene.add("fkchain", side="C", name="tail", segments=2)
    assert session.capture_guides() is True
    assert session.document.guides["modules"][0]["name"] == "tail"


def test_capture_stamps_the_scene_with_the_session():
    session = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    session.capture_guides()
    assert session.owns_scene_guides is True


def test_checkout_projects_the_document_into_an_empty_scene():
    session = Session()
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    session.capture_guides()
    scene.clear()
    session.checkout_guides()
    restored = GuideScene()
    assert restored.get(handle.instance_id) is not None
    assert len(restored.guide_nodes(handle.instance_id)) == 3


def test_checkout_restores_authored_poses():
    session = Session()
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    target = scene.guide_nodes(handle.instance_id)[("segment", 0)]
    cmds.xform(target.long_name, worldSpace=True, translation=(4.0, 5.0, 6.0))
    scene.sync()
    session.capture_guides()
    cmds.file(new=True, force=True)
    session.checkout_guides()
    restored = GuideScene().guide_nodes(handle.instance_id)[("segment", 0)]
    placed = cmds.xform(restored.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([4.0, 5.0, 6.0])


def test_a_scene_stamped_for_another_session_is_reported_not_adopted():
    first = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    first.capture_guides()
    second = Session()
    assert second.owns_scene_guides is False
    with pytest.raises(SessionError, match="another session"):
        second.checkout_guides()


def test_forcing_a_checkout_takes_the_scene_over():
    first = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    first.capture_guides()
    second = Session()
    second.checkout_guides(force=True)
    assert second.owns_scene_guides is True
    assert GuideScene().instances() == []


def test_an_empty_scene_is_owned_by_nobody():
    assert Session().owns_scene_guides is True


def test_save_captures_the_guides_first(tmp_path):
    session = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    path = session.save(tmp_path / "hero.tr")
    import json
    data = json.loads(path.read_text())
    assert data["guides"]["modules"][0]["name"] == "tail"


def test_save_does_not_capture_another_sessions_guides(tmp_path):
    first = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    first.capture_guides()
    second = Session()
    second.save(tmp_path / "other.tr")
    assert second.document.guides == {}


def test_a_saved_session_round_trips_its_guides(tmp_path):
    session = Session()
    handle = GuideScene().add("fkchain", side="C", name="tail", segments=2)
    path = session.save(tmp_path / "hero.tr")
    cmds.file(new=True, force=True)
    reopened = Session.open(str(path))
    reopened.checkout_guides()
    assert GuideScene().get(handle.instance_id).name == "tail"
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_session_guides_trigger.py -q`
Expected: FAIL — `AttributeError: 'Session' object has no attribute 'session_id'`

- [x] **Step 3: Add the stamp to the tags and the store**

In `src/python/tik/trigger/maya/tags.py`, after `DOCUMENT`:

```python
SESSION = "trg_session"  # id of the session whose guides are checked out
```

In `src/python/tik/trigger/guides/document_store.py`:

```python
def read_stamp() -> str:
    """The id of the session whose guides the scene holds, or ""."""
    if not cmds.objExists(tags.GUIDE_HOLDER):
        return ""
    return str(tm.Transform(tags.GUIDE_HOLDER).meta.get(tags.SESSION, "") or "")


def write_stamp(session_id: str) -> None:
    """Record which session owns the guides currently in the scene."""
    nodes.holder().meta[tags.SESSION] = str(session_id)
```

- [x] **Step 4: Implement the Session half**

In `src/python/tik/trigger/session.py`, add to `Session` (Maya imported inside the methods, never at module level):

```python
    # ------------------------------------------------------------ guides
    @property
    def session_id(self) -> str:
        """Stable id for this session, used to stamp its checkout in the scene."""
        found = self.document.meta.get("session_id")
        if not found:
            found = uuid.uuid4().hex
            self.document.meta["session_id"] = found
        return found

    def _guide_scene(self):
        from tik.trigger.guides import GuideScene

        return GuideScene(self.events)

    @property
    def owns_scene_guides(self) -> bool:
        """True when the scene's guides are ours, or there are none."""
        from tik.trigger.guides import document_store

        stamp = document_store.read_stamp()
        return not stamp or stamp == self.session_id

    def capture_guides(self) -> bool:
        """Fold the scene's guide document into this session. Scene -> document."""
        from tik.trigger.guides import document_store

        if not self.owns_scene_guides:
            return False
        scene = self._guide_scene()
        scene.sync(regenerate_stale=False)  # poses first, but never redraw here
        captured = scene.document.to_dict()
        changed = captured != self.document.guides
        self.document.guides = captured
        document_store.write_stamp(self.session_id)
        return changed

    def checkout_guides(self, force: bool = False) -> None:
        """Project this session's guides into the scene. Document -> scene.

        The scene holds one checkout at a time. A scene stamped for another
        session is reported rather than silently adopted -- discarding someone
        else's working copy has to be a decision, not a side effect.
        """
        from tik.trigger.core.guide_document import GuideDocument
        from tik.trigger.guides import document_store, regenerate

        if not force and not self.owns_scene_guides:
            raise SessionError(
                "The guides in this scene belong to another session. "
                "Save that session first, or check out with force=True."
            )
        scene = self._guide_scene()
        scene.clear()
        document = GuideDocument.from_dict(self.document.guides or {})
        document_store.write_document(document)
        scene.reload()
        regenerate.regenerate_all(scene.document)
        document_store.write_stamp(self.session_id)
```

Add `import uuid` at the top of `session.py` (stdlib, no Maya).

In `save()`, before `self.document.save(target)`:

```python
        self.capture_guides()
```

- [x] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_session_guides_trigger.py -q`
Expected: PASS (11 tests)

- [x] **Step 6: Confirm session.py is still Maya-free at import**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui -q`
Expected: PASS — a Maya import at module scope in `session.py` would break these.

- [x] **Step 7: Commit**

```bash
git add src/python/tik/trigger/session.py src/python/tik/trigger/maya/tags.py src/python/tik/trigger/guides/document_store.py tests/unit/test_session_guides_trigger.py
git commit -m "feat(tik.trigger): sessions capture and check out their guides"
```

---

### Task 3: Kinematics builds from the session's guides

The version-skew fix. `guides_file` becomes an override for a shared guide library rather than the only source.

**Files:**
- Modify: `src/python/tik/trigger/actions/kinematics/kinematics.py`
- Test: `tests/integration/trigger/test_session_build_trigger.py`

**Interfaces:**
- `guides_file` stays a `FileField` but is optional; empty means "this session's guides".
- The action reads `ctx.session.document.guides` when no file is set.

- [x] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_session_build_trigger.py`:

```python
def test_kinematics_builds_from_the_sessions_own_guides(tmp_path):
    """No guides file: the rig description is self-contained."""
    import tik.trigger as trigger
    from maya import cmds
    from tik.trigger.guides import GuideScene
    from tik.trigger.session import Session

    trigger.load_plugins()
    cmds.file(new=True, force=True)
    session = Session()
    GuideScene().add("base", side="C", name="body")
    session.capture_guides()
    session.add("kinematics", rig_name="fromsession")
    session.build()
    assert cmds.objExists("fromsession_rig")


def test_kinematics_without_guides_or_a_file_reports_clearly(tmp_path):
    from maya import cmds
    import tik.trigger as trigger
    from tik.trigger.core.exceptions import ActionExecutionError
    from tik.trigger.session import Session

    trigger.load_plugins()
    cmds.file(new=True, force=True)
    session = Session()
    session.add("kinematics", rig_name="empty")
    with pytest.raises(ActionExecutionError, match="no guides"):
        session.build()
```

- [x] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/integration/trigger/test_session_build_trigger.py -q`
Expected: FAIL — `kinematics: no guides file set.`

- [x] **Step 3: Implement**

In `kinematics.py`, change the field help and `run`:

```python
    guides_file = FileField(
        "", extensions=[".trg"], label="GuideLayout file",
        help="Leave empty to build this session's own guides; set a path to "
             "build a shared guide library instead.",
    )
```

and in `run`, replace the `if not self.guides_file: raise` opening with:

```python
        guides = GuideScene(ctx.events)
        if self.guides_file:
            handles = guides.import_(ctx.resolve(self.guides_file))
        else:
            stored = getattr(ctx.session, "document", None)
            stored = dict(getattr(stored, "guides", {}) or {})
            if not stored.get("modules"):
                raise ActionExecutionError(
                    "kinematics: no guides in this session and no guides file set."
                )
            from tik.trigger.core.guide_document import GuideDocument
            from tik.trigger.guides import document_store, regenerate

            guides.clear()
            document_store.write_document(GuideDocument.from_dict(stored))
            guides.reload()
            regenerate.regenerate_all(guides.document)
            handles = guides.instances()
```

- [x] **Step 4: Run tests**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/integration/trigger/test_session_build_trigger.py -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/python/tik/trigger/actions/kinematics/kinematics.py tests/integration/trigger/test_session_build_trigger.py
git commit -m "feat(tik.trigger): kinematics builds this session's guides by default"
```

---

### Task 4: `.trg` import reassigns identity

`.trg` demotes to an exchange format, so importing one is *grafting*, not *opening*. Today `import_` mints fresh uuids but leaves names colliding: import the same file twice and you get two modules called `L_arm`.

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py` (`_entries_from_import`)
- Test: `tests/unit/test_guides_trigger.py`

- [x] **Step 1: Write the failing test**

Append to `tests/unit/test_guides_trigger.py`:

```python
def test_importing_the_same_trg_twice_uniquifies_names(guides, tmp_path):
    """A .trg is grafted, not opened: identity is reassigned on the way in."""
    guides.add("fkchain", side="L", name="tail", segments=2)
    path = guides.export(tmp_path / "lib")
    original_id = guides.find("tail", "L").instance_id
    imported = guides.import_(path)
    keys = sorted(handle.key for handle in guides.instances())
    assert keys == ["L_tail", "L_tail1"]
    assert imported[0].instance_id != original_id
    assert len({handle.instance_id for handle in guides.instances()}) == 2


def test_importing_remaps_connections_onto_the_new_ids(guides, tmp_path):
    parent = guides.add("fkchain", side="C", name="spine", segments=1)
    child = guides.add("fkchain", side="L", name="tail", segments=1)
    guides.connect(f"{child.key}.root", f"{parent.key}.root")
    path = guides.export(tmp_path / "pair")
    imported = guides.import_(path)
    new_child = next(handle for handle in imported if handle.name.startswith("tail"))
    new_parent = next(handle for handle in imported if handle.name.startswith("spine"))
    # the copy points at its own copy of the producer, not the original
    assert new_child.inputs["root"] == f"{new_parent.key}.root"
```

- [x] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_guides_trigger.py -q`
Expected: FAIL — duplicate names.

- [x] **Step 3: Implement**

In `_entries_from_import`, uniquify the name before building the entry. The connection remap already resolves through `keys`, which is built from the *entries being imported*, so it follows the new names automatically — but the key map must be built from the pre-rename keys and the entries' post-rename ids:

```python
        document = self.document
        entries = {}
        original_keys = {}
        for guide_instance, module, _joints in built:
            module.name = self.unique_name(module.name, module.side.value)
            entry = ModuleEntry(
                instance_id=module.instance_id, module_type=module.module_type,
                name=module.name, side=module.side.value, settings=module.values(),
            )
            expand_guides(entry, module.guides, module.guide_count())
            document.modules.append(entry)
            entries[module.instance_id] = (entry, guide_instance)
            # the file's key, so its own connections still resolve
            original_keys[guide_instance.key] = entry.instance_id
        for entry, guide_instance in entries.values():
            entry.inputs = {
                name: (
                    f"{original_keys[source.rpartition('.')[0]]}.{source.rpartition('.')[2]}"
                    if "." in source and source.rpartition(".")[0] in original_keys
                    else source
                )
                for name, source in guide_instance.inputs.items() if source
            }
```

Note the rename must happen *before* `unique_name` is consulted for the next module, and `self.unique_name` reads `self.document.modules`, so appending as we go is what makes a two-module import uniquify against itself.

- [x] **Step 4: Run tests**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/test_guides_trigger.py -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/python/tik/trigger/guides/scene.py tests/unit/test_guides_trigger.py
git commit -m "fix(tik.trigger): importing a .trg reassigns names and connections"
```

---

### Task 5: A Designer per session

The Designer mode's page becomes a stack that follows the active session tab.

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py`
- Test: `tests/ui/test_designer_per_session.py`

**Interfaces:**
- `TriggerWindow._designers: dict[id(view), GuideDesigner]`
- `TriggerWindow.designer_for(view) -> GuideDesigner` — built on first use for that view.
- `TriggerWindow._ensure_designer()` returns the designer for the **active** session view.
- Closing a session tab tears down and drops its designer.

- [x] **Step 1: Write the failing test**

Create `tests/ui/test_designer_per_session.py`:

```python
"""Each session tab owns a Guide Designer and a checkout."""

import pytest

from tik.trigger.ui.main import DESIGNER_MODE, TriggerWindow


@pytest.fixture
def window(qapp):
    win = TriggerWindow()
    yield win
    win.close()


def test_each_session_tab_gets_its_own_designer(window):
    first = window.views[0]
    window.new_session()
    second = window.views[-1]
    assert first is not second
    assert window.designer_for(first) is not window.designer_for(second)


def test_the_designer_mode_follows_the_active_tab(window):
    first = window.views[0]
    window.new_session()
    second = window.views[-1]
    window.mode_bar.setCurrentIndex(DESIGNER_MODE)
    assert window.active_designer is window.designer_for(second)
    window.tabs.setCurrentIndex(0)
    assert window.active_designer is window.designer_for(first)


def test_closing_a_tab_drops_its_designer(window):
    window.new_session()
    second = window.views[-1]
    designer = window.designer_for(second)
    window.close_tab(window.tabs.indexOf(second))
    assert designer not in window._designers.values()


def test_the_designer_is_not_built_until_the_mode_is_opened(window):
    assert window._designers == {}
```

- [x] **Step 2: Run to verify it fails**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui/test_designer_per_session.py -q`
Expected: FAIL — `AttributeError: 'TriggerWindow' object has no attribute 'designer_for'`

- [x] **Step 3: Implement**

Replace the single `self._guide_designer` with a per-view map. In `_build_designer_mode`, make the page holder a `QStackedWidget`; `designer_for(view)` builds a `GuideDesigner` for that view (passing `view.session`), adds it to the stack, and remembers it. `_activate_mode(DESIGNER_MODE)` and the tab-changed signal both call `_show_active_designer()`, which sets the stack's current widget and swaps the mode's menu bar and status strip. `close_tab` calls `teardown()` on that view's designer and drops it.

Keep `open_guide_designer` working by delegating to the active view.

- [x] **Step 4: Run tests**

Run: `PYTHONPATH="D:/dev/tikworks/src/python" TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui -q`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/python/tik/trigger/ui/main.py tests/ui/test_designer_per_session.py
git commit -m "feat(tik.trigger): one Guide Designer per session tab"
```

---

### Task 6: Checkout on activation, and the indicator

The scene holds one checkout at a time, and which one is always visible.

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py`
- Modify: `src/python/tik/trigger/ui/designer/window.py`
- Test: `tests/ui/test_designer_per_session.py`, `tests/integration/trigger/test_session_checkout_trigger.py`

- [x] **Step 1: Write the failing tests**

Append to `tests/ui/test_designer_per_session.py`:

```python
def test_activating_a_designer_checks_its_session_out(window, monkeypatch):
    calls = []
    for view in window.views:
        monkeypatch.setattr(view.session, "checkout_guides",
                            lambda force=False, v=view: calls.append(v))
        monkeypatch.setattr(type(view.session), "owns_scene_guides", property(lambda self: True))
    window.mode_bar.setCurrentIndex(DESIGNER_MODE)
    assert calls == [window.views[0]]


def test_a_foreign_checkout_is_reported_not_taken(window, monkeypatch):
    view = window.views[0]
    monkeypatch.setattr(type(view.session), "owns_scene_guides", property(lambda self: False))
    taken = []
    monkeypatch.setattr(view.session, "checkout_guides", lambda force=False: taken.append(force))
    window.mode_bar.setCurrentIndex(DESIGNER_MODE)
    assert taken == []  # never forced on the user's behalf
```

Create `tests/integration/trigger/test_session_checkout_trigger.py`:

```python
"""Switching sessions swaps the scene's checkout."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.guides import GuideScene
from tik.trigger.session import Session


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def test_switching_sessions_swaps_the_guides_in_the_scene():
    first = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    first.capture_guides()

    second = Session()
    second.checkout_guides(force=True)  # takes the scene; first's guides go away
    GuideScene().add("base", side="C", name="body")
    second.capture_guides()
    assert GuideScene().find("tail") is None

    first.checkout_guides(force=True)
    assert GuideScene().find("tail") is not None
    assert GuideScene().find("body") is None


def test_a_checkout_round_trips_poses_between_two_sessions():
    first = Session()
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    target = scene.guide_nodes(handle.instance_id)[("segment", 0)]
    cmds.xform(target.long_name, worldSpace=True, translation=(8.0, 1.0, 2.0))
    scene.sync()
    first.capture_guides()

    Session().checkout_guides(force=True)  # somebody else takes the scene
    first.checkout_guides(force=True)  # and we take it back

    restored = GuideScene().guide_nodes(handle.instance_id)[("segment", 0)]
    placed = cmds.xform(restored.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([8.0, 1.0, 2.0])
```

- [x] **Step 2: Run to verify they fail**

Run both suites; expect failures on the missing activation hook.

- [x] **Step 3: Implement**

In `_show_active_designer()`, before showing: capture the outgoing view's guides (it owns them), then for the incoming view call `session.checkout_guides()` inside a `try/except SessionError`, logging the message rather than forcing. Add a status field to the Designer showing the owning session's name, set from the host.

- [x] **Step 4: Run every suite**

Run: `mayapy tests/unit/invoke.py`, `mayapy tests/integration/invoke.py`, and the UI suite.
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/python/tik/trigger/ui/ tests/ui/test_designer_per_session.py tests/integration/trigger/test_session_checkout_trigger.py
git commit -m "feat(tik.trigger): the scene is a checkout of one session at a time"
```

---

## Done when

- A `.tr` saved with guides reopens with them, and building it needs no `.trg`.
- Two session tabs each have their own Designer; switching swaps the scene's guides.
- A scene belonging to another session is reported, never silently adopted.
- Importing the same `.trg` twice gives uniquely named modules with correctly remapped connections.
- `make tests` passes.

---

# Addendum: the shell inversion (2026-08-31, after first use)

Tasks 5–6 above kept the window-level mode bar and made its pages follow the
active session tab. In use that reads as inverted: the mode bar sits *above* the
sessions, sessions are reachable from only one mode, and one document has two
menu bars. Spec §6.4 is revised; these tasks implement the revision.

**Target shell**

```
  File  Edit  Session  Guides  View  Build  Help      <- one menu bar
 ┌──────────────┬─────────────────┐
 │ something.tr │ somethingElse.tr│                   <- session tabs, outermost
 ├──────────────┴─────────────────┴────────────────┐
 │  Session │ Guide Designer                       │  <- sub-tabs, per session
```

**What gets deleted:** the mode bar, `menu_stack`, `status_stack`, `add_mode`,
`_mode_menus`, `_activate_mode`, `TRIGGER_MODE`/`DESIGNER_MODE`, the
`designer_menus`/`designer_pages`/`designer_status` stacks, `_designers`,
`designer_for`, `active_designer`, `_show_active_designer`, and the Designer's
own `file_path`/`title`/`set_file`.

---

### Task 7: `SessionView` hosts its own Designer

**Files:**
- Modify: `src/python/tik/trigger/ui/session_view.py`
- Test: `tests/ui/test_session_subtabs.py`

**Interfaces:**
- `SessionView.sub_tabs` — a `QTabWidget` with pages "Session" and "Guide Designer".
- `SessionView.designer` — built lazily on first activation of the Designer page; `None` before.
- `SessionView.designer_factory` — injection point so the Qt tests can supply a Maya-free Designer.
- `SessionView.sub_tab_changed` — signal `(int)`, so the window can re-point the status strip.
- `SessionView.teardown()` — tears the Designer down; called by `close_tab`.

- [ ] **Step 1: Write the failing test** — a `SessionView` with a stub factory; assert the Designer is not built until the sub-tab is selected, is built once, and that `teardown()` releases it.
- [ ] **Step 2: Run it, see it fail.**
- [ ] **Step 3:** Wrap the existing pipeline splitter in page 0 of a `QTabWidget`; page 1 is a placeholder that swaps for the Designer on first activation.
- [ ] **Step 4: Run the UI suite.**
- [ ] **Step 5: Commit.**

---

### Task 8: One menu bar

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py`, `src/python/tik/trigger/ui/designer/window.py`
- Test: `tests/ui/test_menus.py`

The Designer stops building a `QMenuBar`. Its verbs move onto the window's bar
as a **Guides** menu, and its file verbs join **File** as *Import Guides…* /
*Export Guides…* (no `Ctrl+S` — that saves the session). The Guides menu and the
Designer's view toggles are disabled while the Session sub-tab is active, so the
bar never offers a verb that has no target.

- [ ] **Step 1: Write the failing test** — assert one menu bar; `File` contains Save (Ctrl+S) and Import/Export Guides; `Guides` exists and is disabled on the Session sub-tab, enabled on the Designer sub-tab.
- [ ] **Step 2: Run it, see it fail.**
- [ ] **Step 3:** Add `GuideDesigner.build_menus(bar)` that populates a given bar instead of owning one; call it from the window.
- [ ] **Step 4: Run the UI suite.**
- [ ] **Step 5: Commit.**

---

### Task 9: Flatten the window

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py`
- Test: `tests/ui/test_pipeline_ui.py`, `tests/ui/test_designer_per_session.py`

- [ ] **Step 1: Update the tests** to the flat shell — `window.tabs` is the central widget, there is no `mode_bar`, `window.menu_bar` is the one bar.
- [ ] **Step 2: Run them, see them fail.**
- [ ] **Step 3:** Delete the mode machinery listed above; `setCentralWidget(self.tabs)`; one `_build_menus`; one status strip that the active sub-view writes into.
- [ ] **Step 4: Run every suite.**
- [ ] **Step 5: Commit.**

---

### Task 10: The hand-off moves to the session tab

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py`
- Test: `tests/ui/test_designer_per_session.py`

Switching session tabs is the hand-over. Switching sub-tabs within a session
changes nothing about the scene, so it must not trigger one.

- [ ] **Step 1: Write the failing test** — switching session tabs calls `Session.hand_over(outgoing, incoming)`; switching sub-tabs does not.
- [ ] **Step 2: Run it, see it fail.**
- [ ] **Step 3:** Move the hand-off from designer activation to `tabs.currentChanged`; check out on first Designer activation too, for a tab whose guides were never projected.
- [ ] **Step 4: Run every suite.**
- [ ] **Step 5: Commit.**

## Done when

- The window shows one menu bar, session tabs, and Session / Guide Designer inside each.
- Guides are reachable without leaving the session you are working on.
- Switching session tabs hands the scene over; switching sub-tabs does not.
- `make tests` passes.
