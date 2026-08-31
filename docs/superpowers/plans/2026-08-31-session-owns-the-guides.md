# The Session Owns the Guides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the guide document out of the Maya scene and into the session, so scene operations — deleting a group, File > New Scene — can no longer destroy the rig description.

**Architecture:** `Document.guides` becomes a live `GuideDocument`. `GuideScene` binds to a `Session` and reads that document instead of assembling one from scene nodes; every write ends in `session.touch()` (the existing undo push) plus a scoped regenerate. The scene keeps guide joints and two labels on the holder, and nothing else. `guides/module_node.py` and the document half of `guides/document_store.py` are deleted.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), pytest, tik.maya, PySide.

**Spec:** `docs/superpowers/specs/2026-08-31-session-owns-the-guides-design.md`

## Global Constraints

- **Layering:** `tik/trigger/core` stays pure — no `maya`, no `tik.maya`, no Qt, no `tik.shared`. `core/document.py` and `core/guide_document.py` must import without Maya (`tests/unit/test_import_boundaries.py`).
- **`session.py` stays Maya-free at import time.** `tests/ui` runs with `TIK_TESTS_NO_MAYA=1` and imports `ui/main.py`, which imports `session`. Every Maya touch is a function-level import.
- **No backward compatibility.** Unreleased. No migration for scenes carrying `trigger_modules_grp`.
- **Identity is the uuid.** Display keys appear only at read boundaries.
- **Nothing in the Maya scene is read as authority** once this lands. That is the invariant the whole plan exists to establish.
- **Test commands:**
  - one file — `PYTHONPATH="D:/dev/tikworks/src/python" mayapy -m pytest tests/unit/<file>.py -q`
  - suites — `mayapy tests/unit/invoke.py`, `mayapy tests/integration/invoke.py`
  - Qt — `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui -q`

---

### Task 1: `Document.guides` becomes a live `GuideDocument`

**Files:**
- Modify: `src/python/tik/trigger/core/document.py`
- Test: `tests/unit/test_document_trigger.py`

**Interfaces:**
- `Document.guides: GuideDocument` (was `dict`), default `GuideDocument()`.
- `to_dict()` emits `self.guides.to_dict()`; `from_dict()` builds `GuideDocument.from_dict(...)`.
- `is_modified` and the undo stack need no change — both go through `Document.to_dict()`.

- [ ] **Step 1: Write the failing test**

Replace the three guide tests added earlier in `tests/unit/test_document_trigger.py` with:

```python
def test_document_guides_is_a_live_guide_document():
    from tik.trigger.core.document import Document
    from tik.trigger.core.guide_document import GuideDocument, ModuleEntry

    document = Document()
    assert isinstance(document.guides, GuideDocument)
    document.guides.modules.append(ModuleEntry("id1", "fkchain", "tail", "C"))
    assert document.to_dict()["guides"]["modules"][0]["name"] == "tail"


def test_document_guides_round_trip(tmp_path):
    from tik.trigger.core.document import SCHEMA_VERSION, Document
    from tik.trigger.core.guide_document import GuideRecord, ModuleEntry

    document = Document()
    document.guides.modules.append(ModuleEntry(
        "id1", "fkchain", "tail", "C", settings={"segments": 3},
        guides=[GuideRecord("root", position=(1.0, 2.0, 3.0))],
    ))
    restored = Document.load(document.save(tmp_path / "hero.tr"))
    assert restored.schema == SCHEMA_VERSION
    assert restored.guides.module("id1").guide("root").position == (1.0, 2.0, 3.0)


def test_editing_guides_shows_up_in_the_documents_state():
    """This is what gives guide work the session's dirty flag and its undo."""
    from tik.trigger.core.document import Document
    from tik.trigger.core.guide_document import ModuleEntry

    document = Document()
    before = document.to_dict()
    document.guides.modules.append(ModuleEntry("id1", "fkchain", "tail", "C"))
    assert document.to_dict() != before
```

- [ ] **Step 2: Run it, expect `AttributeError: 'dict' object has no attribute 'modules'`.**

- [ ] **Step 3: Implement**

In `core/document.py`:

```python
from .guide_document import GuideDocument
```

```python
    #: The rig's guides. A live ``GuideDocument`` -- the session is their only
    #: store, so the Maya scene holds nothing but a rendering of them.
    guides: GuideDocument = field(default_factory=GuideDocument)
```

`to_dict`: `"guides": self.guides.to_dict(),`
`from_dict`: `guides=GuideDocument.from_dict(data.get("guides") or {}),`

- [ ] **Step 4: Run the test file and `test_import_boundaries.py`.** Both pass.

- [ ] **Step 5: Run the unit suite.** Anything reading `document.guides` as a dict fails here — fix those call sites to the object API.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/core/document.py tests/unit/test_document_trigger.py
git commit -m "feat(tik.trigger): the session document holds a live GuideDocument"
```

---

### Task 2: `Session` owns a `GuideScene`

**Files:**
- Modify: `src/python/tik/trigger/session.py`
- Test: `tests/unit/test_session_guides_trigger.py`

**Interfaces:**
- `Session.touch()` — public; `_touch()` becomes an alias kept only if something still calls it.
- `Session.guides -> GuideScene` — built once, bound to this session.
- `capture_guides()` / `checkout_guides()` keep their names and meaning; both now work against `self.document.guides`.
- The empty-scene guard in `capture_guides` is **deleted** — capture can no longer remove a module, so there is nothing to guard.

- [ ] **Step 1: Write the failing test**

```python
def test_a_session_hands_out_a_guide_scene_bound_to_itself():
    session = Session()
    scene = session.guides
    assert scene is session.guides                      # built once
    assert scene.document is session.document.guides    # the same object


def test_a_structural_edit_pushes_an_undo_step():
    session = Session()
    session.guides.add("fkchain", side="C", name="tail", segments=1)
    assert session.can_undo is True
    session.undo()
    assert session.document.guides.modules == []


def test_undo_puts_the_module_back():
    session = Session()
    session.guides.add("fkchain", side="C", name="tail", segments=1)
    session.undo()
    session.redo()
    assert [entry.name for entry in session.document.guides.modules] == ["tail"]


def test_guides_survive_a_new_scene():
    """The failure this whole spec exists to remove."""
    session = Session()
    session.guides.add("fkchain", side="C", name="tail", segments=1)
    cmds.file(new=True, force=True)
    assert [entry.name for entry in session.document.guides.modules] == ["tail"]
    assert session.guides.instances()[0].name == "tail"


def test_capture_against_an_empty_scene_leaves_the_modules_alone():
    session = Session()
    session.guides.add("fkchain", side="C", name="tail", segments=1)
    cmds.file(new=True, force=True)
    session.capture_guides()
    assert [entry.name for entry in session.document.guides.modules] == ["tail"]
```

- [ ] **Step 2: Run it, expect `AttributeError: 'Session' object has no attribute 'guides'`.**

- [ ] **Step 3: Implement**

Rename `_touch` to `touch` (keep `_touch = touch` if any caller remains), and add:

```python
    @property
    def guides(self):
        """This session's guides. The scene renders them; the session owns them."""
        if self._guides is None:
            from tik.trigger.guides import GuideScene

            self._guides = GuideScene(events=self.events, session=self)
        return self._guides
```

with `self._guides = None` in `__init__`. `capture_guides` drops its empty-scene guard and its `document_store.write_document` call; `checkout_guides` drops `write_document` and simply clears and regenerates.

- [ ] **Step 4: Run the test file.** Some tests need Task 3 to pass; note which and move on.

- [ ] **Step 5: Commit** (may be red until Task 3 — commit together if so).

---

### Task 3: `GuideScene` binds to the session; the scene-side store is deleted

The core of the change, and the biggest single edit.

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py`
- Modify: `src/python/tik/trigger/guides/document_store.py`
- Delete: `src/python/tik/trigger/guides/module_node.py`
- Modify: `src/python/tik/trigger/guides/__init__.py` (drop the lazy `module_node` export)
- Delete: `tests/unit/test_module_node_trigger.py`, `tests/unit/test_document_store_trigger.py`
- Modify: `src/python/tik/trigger/guides/nodes.py`

**Interfaces:**
- `GuideScene(events=None, session=None)`; `document` is the session's (or a free-standing one when unbound).
- Deleted: `commit()`, `reload()`, `invalidate()`, `settings_plug()`, `_write()`.
- `document_store` keeps only `read_stamp`, `write_stamp`, `read_dismissed`, `write_dismissed`.
- `nodes.find_instances(scope="scene", document=None)` — the document is passed in.

- [ ] **Step 1: Rewrite `GuideScene`'s document half**

```python
    def __init__(self, events=None, session=None) -> None:
        self.events = events or EventBus()
        self._session = session
        # unbound: a free-standing document for scripting, that no session sees
        self._own = None if session is not None else GuideDocument()
        self._syncing = False

    @property
    def document(self) -> GuideDocument:
        return self._session.document.guides if self._session is not None else self._own

    def _touch(self) -> None:
        """Record the edit on the session's undo stack."""
        if self._session is not None:
            self._session.touch()
```

Every write method (`create_guides`, `rename_instance`, `set_inputs`, `set_input`, `write_settings`, `remove`, `clear`, `write_layout`, the scene-group methods, `mirror`, `duplicate`, `import_`) replaces its `self._write(entry)` / `self.commit()` calls with `self._touch()`, keeping the `regenerate(...)` that follows.

- [ ] **Step 2: Strip `document_store`** to the four label functions. Delete `module_node.py` and the two test files above.

- [ ] **Step 3: Hand the document to `find_instances`**

```python
def find_instances(scope="scene", document=None) -> list[ModuleInstance]:
```

replacing the internal `read_document()` with the argument; callers that have no document pass `None` and get identity plus poses only.

- [ ] **Step 4: Run the guide suites**

`test_guides_trigger.py`, `test_guide_scene_trigger.py`, `test_connections_trigger.py`, `test_guides_reparent_trigger.py`, `test_snapshot_trigger.py`, `test_capture_trigger.py`, `test_regenerate_trigger.py`.
Expect failures where a test constructs `GuideScene()` and expects scene persistence across instances — those now need one scene, or a session.

- [ ] **Step 5: Commit with Task 2**

```bash
git add -A src/python/tik/trigger/guides src/python/tik/trigger/session.py tests/unit
git commit -m "refactor(tik.trigger): the session owns the guide document"
```

---

### Task 4: The Builder is handed the document

**Files:**
- Modify: `src/python/tik/trigger/maya/build.py`
- Modify: `src/python/tik/trigger/actions/kinematics/kinematics.py`
- Modify: `src/python/tik/trigger/guides/scene.py` (`test_build`)
- Test: `tests/integration/trigger/test_session_guides_build_trigger.py`

- [ ] **Step 1: Write the failing test**

```python
def test_the_builder_needs_no_document_in_the_scene(tmp_path):
    """Nothing in the scene is authority: the document comes from the session."""
    session = Session()
    session.guides.add("base", side="C", name="body")
    session.add("kinematics", rig_name="hero")
    session.build()
    assert cmds.objExists("hero_rig")
    assert not cmds.objExists("trigger_modules_grp")
```

- [ ] **Step 2: Run it, expect the module holder to still exist (or the build to find nothing).**

- [ ] **Step 3: Implement.** `Builder.build(..., document=None)` forwards it to `find_instances`; `GuideScene.test_build` passes `self.document`; kinematics passes `ctx.session.document.guides` and drops its `document_store.write_document` call, keeping the clear + `regenerate_all`.

- [ ] **Step 4: Run the integration suite.**

- [ ] **Step 5: Commit**

```bash
git commit -am "refactor(tik.trigger): the Builder is handed the guide document"
```

---

### Task 5: Remove `useRefOri` and the settings binding

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/window.py`, `properties.py`
- Modify: `tests/ui/test_guide_designer.py`

- [ ] **Step 1: Delete** `self.inherit_orientation` and its layout row, `_on_inherit_toggled`, the `useRefOri` binding in `_bind_properties`, the `useRefOri` block in `_set_current`, and every mention in the visibility tuples.
- [ ] **Step 2: Delete** `_bind_properties`'s settings loop and `_plug_adapter` — with no `settings_plug` there is nothing to bind. The panel already writes through `write_settings`.
- [ ] **Step 3: Delete** `test_multi_inherit_orientation_and_duplicate`, keeping any duplicate assertions it carried by moving them into a new test.
- [ ] **Step 4: Run the UI suite.**
- [ ] **Step 5: Commit**

```bash
git commit -am "refactor(tik.trigger): drop useRefOri and the settings plug binding"
```

---

### Task 6: Ctrl+Z on the Designer tab undoes Trigger actions

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py`
- Test: `tests/ui/test_menus.py`

- [ ] **Step 1: Write the failing test**

Replace `test_undo_on_the_designer_tab_goes_to_maya` with:

```python
def test_undo_on_the_designer_tab_undoes_trigger_actions(window, monkeypatch):
    """Guide structure lives in the session, so its undo stack is the right one.

    Moving a guide is a scene edit and stays on Maya's stack, undone with focus
    in the viewport.
    """
    view = window.views[0]
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    hits = []
    monkeypatch.setattr(view.session, "undo", lambda: hits.append("session") or True)
    undo = next(a for a in menu(window, "&Edit").actions() if a.text() == "Undo")
    undo.trigger()
    assert hits == ["session"]
```

- [ ] **Step 2: Run it, expect `hits == []` (it calls Maya).**
- [ ] **Step 3: Implement.** Delete the `_designer is not None` branch from `TriggerWindow.undo` and `_maya_undo`; undo is the session's on both tabs.
- [ ] **Step 4: Run the UI suite.**
- [ ] **Step 5: Commit**

```bash
git commit -am "feat(tik.trigger): Ctrl+Z undoes Trigger actions on the Designer tab"
```

---

### Task 7: New Scene redraws

**Files:**
- Test: `tests/integration/trigger/test_lockstep_trigger.py`

- [ ] **Step 1: Write the test**

```python
def test_a_new_scene_leaves_the_modules_and_redraws_them(scene):
    """The reported failure: New Scene emptied the Designer."""
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    root = scene.guide_nodes(handle.instance_id)[("root", 0)]
    cmds.xform(root.long_name, worldSpace=True, translation=(2.0, 3.0, 4.0))
    scene.sync()
    cmds.file(new=True, force=True)
    assert scene.get(handle.instance_id).name == "tail"   # never left
    scene.sync()
    restored = scene.guide_nodes(handle.instance_id)[("root", 0)]
    placed = cmds.xform(restored.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([2.0, 3.0, 4.0])
```

The `scene` fixture must become session-bound for this to mean anything:
`Session().guides` rather than a bare `GuideScene()`.

- [ ] **Step 2: Run it.** It may already pass once Task 3 lands — that is the point of writing it.
- [ ] **Step 3: Run every suite.**
- [ ] **Step 4: Commit**

```bash
git commit -am "test(tik.trigger): New Scene leaves the modules and redraws them"
```

## Done when

- File > New Scene leaves every module in the Designer and redraws its guides.
- `trigger_modules_grp` does not exist; nothing in the scene is read as authority.
- Ctrl+Z in the Designer undoes add / connect / delete / settings.
- Capture against an empty scene cannot remove a module.
- `make tests` passes.
