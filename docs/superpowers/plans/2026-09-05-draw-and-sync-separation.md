# Draw and Sync Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the one overloaded "sync" into two explicitly named directions — **Draw** (session → scene, always manual) and **Sync** (scene → session, Auto or on demand) — so neither can ever move data the other way.

**Architecture:** `GuideScene` gets one method per direction and nothing does both: `sync()` captures and never regenerates; `draw()` regenerates and only captures when told to; `_apply()` touches the document and never touches the scene. `reconcile` already computes every state needed — only the *reading* changes, with `absent` reclassified from "damage to repair" into "not drawn, which is normal". The Guide Designer's bar puts the two directions at opposite ends, and the tree and graph paint the per-module state from one shared diff object.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), PySide2/6 via `tik.shared.ui.Qt`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-05-draw-and-sync-separation-design.md`

## Global Constraints

- **No third-party dependencies.** Stdlib and Maya-bundled modules only.
- **`tik/trigger/core` is pure Python** — no Maya, no Qt. Enforced by `tests/unit/test_import_boundaries.py`.
- **`tik/trigger/guides` may use Maya but never Qt.** No dialog may be opened from `GuideScene`.
- **Every user dialog goes through `tik.shared.ui.feedback.Feedback`.** Raw `QMessageBox` / `QFileDialog` / `QInputDialog` outside `shared/ui/feedback.py` fails `tests/unit/test_dialog_boundaries.py`.
- **Consume `tik.maya`, not `maya.cmds`,** in tool code. Inside `tik/trigger/guides/nodes.py`, `snapshot.py` and `regenerate.py`, raw `cmds` is already the established pattern for bulk scene scans — follow the file you are in.
- **No backward compatibility.** Delete what this design makes redundant; never deprecate, never leave a shim.
- **`GuideDocument.dismissed` is runtime-only and never serialized, so no `.tr` schema bump is needed.** `document.py` stays at `SCHEMA_VERSION = 6`.
- **Orange (`#FE7E00`) means out of date. It never means not-drawn.**

### Running tests

`make tests-unit` / `make tests-integration` run whole suites through `invoke.py`, which takes no arguments. To run one file or one test, invoke `mayapy` directly. From the repo root, in PowerShell:

```powershell
$env:PYTHONPATH = "$PWD/src/python"; mayapy -m pytest tests/unit/test_reconcile_trigger.py -v
```

Referred to below as **`TP <path>`**. For UI tests add the two environment variables:

```powershell
$env:PYTHONPATH = "$PWD/src/python"; $env:TIK_TESTS_NO_MAYA = "1"; $env:QT_QPA_PLATFORM = "offscreen"; mayapy -m pytest tests/ui/test_action_bar.py -v
```

Referred to below as **`TPUI <path>`**.

---

## File Structure

**Modified**

| File | Responsibility after this plan |
|---|---|
| `src/python/tik/trigger/core/reconcile.py` | Reports three states: not drawn, out of date, moved. Never says "regenerate". |
| `src/python/tik/trigger/guides/capture.py` | Scene → document, optionally scoped to a set of instance ids. |
| `src/python/tik/trigger/guides/snapshot.py` | Reads the drawn display key onto each `RenderedGuide`. |
| `src/python/tik/trigger/guides/nodes.py` | Stamps `tags.NAME` on every guide joint; `find_instances` skips orphans. |
| `src/python/tik/trigger/guides/scene.py` | `draw()` and `sync()`, one direction each. `_apply()` touches only. |
| `src/python/tik/trigger/session.py` | `checkout_guides` clears and stamps; it no longer draws. |
| `src/python/tik/trigger/maya/build.py` | `apply_afterlife` loses its `document` parameter. |
| `src/python/tik/trigger/maya/tags.py` | `DISMISSED` removed. |
| `src/python/tik/shared/ui/feedback.py` | `pop_question` accepts `("key", "Label")` tuples. |
| `src/python/tik/trigger/ui/designer/action_bar.py` | The two-ended bar. |
| `src/python/tik/trigger/ui/designer/commands.py` | `draw_selected`, `draw_all`, the dirty prompt, sync-then-draw before build. |
| `src/python/tik/trigger/ui/designer/window.py` | One diff per refresh, four consumers. |
| `src/python/tik/trigger/ui/graph/items.py`, `scene.py`, `constants.py` | The node's draw-state stripe. |
| `src/python/tik/trigger/ui/main.py` | Guides menu; the restore-on-tab block deleted. |
| `tests/ui/stub.py` | Gains `draw()`; `set_selection` assertions dropped. |

**Created**

| File | Responsibility |
|---|---|
| `src/python/tik/trigger/ui/designer/delegates.py` | `GuideStateDelegate` — the tree's gutter dot. |
| `tests/integration/trigger/test_draw_sync_trigger.py` | Replaces `test_lockstep_trigger.py`. |

---

### Task 1: Reconcile reports three states, not two

**Files:**
- Modify: `src/python/tik/trigger/core/reconcile.py:57-105`
- Test: `tests/unit/test_reconcile_trigger.py`

**Interfaces:**
- Produces: `ModuleDiff.is_stale -> bool` (replaces `needs_regenerate`), `GuideDiff.not_drawn -> list[str]`, `GuideDiff.stale -> list[str]` (together they replace `GuideDiff.structural`). `ModuleDiff.needs_capture` and `GuideDiff.drifted` are unchanged.

- [x] **Step 1: Write the failing tests**

Append to `tests/unit/test_reconcile_trigger.py`. The existing helpers `_document` and `_rendered` in that file build a one-module document and its rendering; read the top of the file and reuse them exactly as the existing tests do.

```python
def test_absent_is_not_drawn_and_never_stale():
    diff = reconcile(_document(), [])
    assert diff.not_drawn == ["id1"]
    assert diff.stale == []
    assert diff.modules["id1"].is_stale is False


def test_missing_guide_is_stale_not_not_drawn():
    rendered = _rendered()[:1]  # one of the two guides is gone
    diff = reconcile(_document(), rendered)
    assert diff.stale == ["id1"]
    assert diff.not_drawn == []


def test_not_drawn_is_not_clean():
    assert reconcile(_document(), []).is_clean is False
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `TP tests/unit/test_reconcile_trigger.py -k "not_drawn or is_stale"`
Expected: FAIL with `AttributeError: 'GuideDiff' object has no attribute 'not_drawn'`.

- [x] **Step 3: Rewrite the two dataclasses' properties**

In `reconcile.py`, replace `ModuleDiff.needs_regenerate` and `ModuleDiff.is_clean`:

```python
    @property
    def is_stale(self) -> bool:
        """The rendering exists but no longer matches the entry.

        Absence is deliberately excluded: a module with no joints is *not
        drawn*, which is the normal state of a new module, not damage.
        """
        return bool(self.missing or self.unexpected or self.parent_wrong)

    @property
    def needs_capture(self) -> bool:
        """True when a guide moved in the scene (the scene wins)."""
        return bool(self.drifted)

    @property
    def is_clean(self) -> bool:
        """True when this module is drawn, current, and captured."""
        return not (self.absent or self.is_stale or self.needs_capture)
```

Replace `GuideDiff.structural` with two properties:

```python
    @property
    def not_drawn(self) -> list:
        """Instance ids with no rendering at all. Not an error."""
        return [key for key, diff in self.modules.items() if diff.absent]

    @property
    def stale(self) -> list:
        """Instance ids whose rendering no longer matches the document."""
        return [key for key, diff in self.modules.items() if diff.is_stale]

    @property
    def is_clean(self) -> bool:
        """True when nothing is pending in either direction."""
        return not (
            self.not_drawn
            or self.stale
            or self.drifted
            or self.orphans
            or self.duplicates
        )
```

- [x] **Step 4: Update the module docstring**

The table at the top of `reconcile.py` still says `absent` is resolved by regenerate. Replace the table and the paragraph under it:

```
===============================  ===========  ==============
Drift                            Resolved by  Winner
===============================  ===========  ==============
pose / guide attr differs        Sync         the scene
absent                           Draw         the document
missing, unexpected,             Draw         the document
  wrong parent
orphans, duplicates              reported     nothing
===============================  ===========  ==============

``absent`` is reported apart from the rest: a module with no joints is *not
drawn*, which is the ordinary state of a new module, while ``missing`` and
``unexpected`` mean a rendering exists and has gone out of date. Neither is
ever repaired automatically -- only an explicit Draw rebuilds a rendering.

A redraw triggered by pose drift would teleport a guide away from where the
rigger just dragged it, so ``is_stale`` deliberately ignores ``drifted``.
Orphans and duplicates are never acted on automatically: they may be a
rigger's scratch work, and destroying untracked scene content is not a repair.
```

- [x] **Step 5: Fix the existing tests in this file**

`tests/unit/test_reconcile_trigger.py` references `diff.structural` on lines 43, 50, 59, 68, 81, 109, 118, 136, 156, 163 and `needs_regenerate` on 58, 80, 175. Change each `diff.structural` to `diff.stale` and each `.needs_regenerate` to `.is_stale`, **except** line 50 (`test_absent_module_is_structural`, or whatever the absent case is called) — that test now asserts `not_drawn`, so rewrite it as:

```python
def test_absent_module_is_reported_as_not_drawn():
    diff = reconcile(_document(), [])
    assert diff.not_drawn == ["id1"]
    assert diff.stale == []
```

Line 42's `assert diff.is_clean` and line 179's `test_empty_document_and_empty_scene_is_clean` stay as they are — an empty document has no modules, so nothing is not-drawn.

- [x] **Step 6: Run the whole file**

Run: `TP tests/unit/test_reconcile_trigger.py`
Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add src/python/tik/trigger/core/reconcile.py tests/unit/test_reconcile_trigger.py
git commit -m "Split reconcile's structural state into not-drawn and stale

Absence stops being damage the tool repairs and becomes the ordinary
state of a module nobody has drawn yet."
```

---

### Task 2: A rename shows up as out of date

Without the auto-redraw, renaming `L_arm` to `L_frontLeg` leaves joints called `L_arm_*` in the scene and nothing flags it — `reconcile` matches on the `trg_instance` uuid, never on names.

**Files:**
- Modify: `src/python/tik/trigger/core/reconcile.py:35-52` (`RenderedGuide`), `57-75` (`ModuleDiff`), `140-200` (`reconcile`)
- Test: `tests/unit/test_reconcile_trigger.py`

**Interfaces:**
- Consumes: `ModuleDiff.is_stale` from Task 1.
- Produces: `RenderedGuide.key: str` (default `""`), `ModuleDiff.key_stale: bool`. Task 3 fills `RenderedGuide.key` from the scene.

- [x] **Step 1: Write the failing test**

```python
def test_renamed_entry_is_stale_when_the_joints_carry_the_old_key():
    document = _document()
    document.modules[0].name = "frontLeg"  # the joints were drawn as "arm"
    diff = reconcile(document, _rendered())
    assert diff.stale == ["id1"]
    assert diff.modules["id1"].key_stale is True


def test_an_untagged_rendering_is_never_key_stale():
    """A guide with no recorded key says nothing about the name."""
    rendered = _rendered()
    for guide in rendered:
        guide.key = ""
    diff = reconcile(_document(), rendered)
    assert diff.modules["id1"].key_stale is False
```

For the first test to be meaningful, `_rendered()` must stamp a key. Update the helper at the top of the file so every `RenderedGuide` it builds carries `key="arm"` (matching `_document()`'s module name and centre side). Read the helper before editing — if `_document()` uses a different name or side, use `instance_key(name, side)` for that pair instead of the literal.

- [x] **Step 2: Run the test to verify it fails**

Run: `TP tests/unit/test_reconcile_trigger.py -k key_stale`
Expected: FAIL with `TypeError: RenderedGuide.__init__() got an unexpected keyword argument 'key'`.

- [x] **Step 3: Add the field, the flag and the check**

In `RenderedGuide`, after `attrs`:

```python
    #: Display key the joints were drawn under (``L_arm``). Empty when the
    #: rendering predates the tag or was not made by regenerate.
    key: str = ""
```

In `ModuleDiff`, after `parent_wrong`:

```python
    key_stale: bool = False
```

and add it to `is_stale`:

```python
        return bool(
            self.missing or self.unexpected or self.parent_wrong or self.key_stale
        )
```

In `reconcile`, inside the `for entry in document.modules:` loop, immediately after the `root_pair` assignment:

```python
        # A rename changes the joints' names, and nothing else here would
        # notice: guides are matched on the uuid tag. Compared against the
        # key the rendering recorded, so an untagged guide stays silent.
        root_guide = seen.get(root_pair) if root_pair else None
        if root_guide is not None and root_guide.key:
            module_diff.key_stale = root_guide.key != entry.key
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `TP tests/unit/test_reconcile_trigger.py`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/python/tik/trigger/core/reconcile.py tests/unit/test_reconcile_trigger.py
git commit -m "Report a renamed module as out of date

Without the automatic redraw nothing else would notice: guides are
matched on their uuid tag, never on their names."
```

---

### Task 3: The scene records the key it drew under

**Files:**
- Modify: `src/python/tik/trigger/guides/nodes.py:53-87` (`create_guide_joint`), `src/python/tik/trigger/guides/snapshot.py:55-95`
- Test: `tests/unit/test_guides_trigger.py`

**Interfaces:**
- Consumes: `RenderedGuide.key` from Task 2.
- Produces: every guide joint carries `tags.NAME` and `tags.SIDE`; `snapshot()` fills `RenderedGuide.key`.

- [x] **Step 1: Write the failing test**

Append to `tests/unit/test_guides_trigger.py`. Read the file's existing fixtures first — it already has a `guides` fixture that builds a `GuideScene` in a fresh scene; use it the way the neighbouring tests do.

```python
def test_snapshot_records_the_key_the_guides_were_drawn_under(guides):
    from tik.trigger.guides.snapshot import snapshot

    handle = guides.add("fkchain", side="L", name="arm")
    guides.draw()
    keys = {guide.key for guide in snapshot() if guide.instance_id == handle.instance_id}
    assert keys == {"L_arm"}
```

`guides.draw()` does not exist until Task 5. Until then, call `regenerate` directly so this task is independently testable:

```python
    from tik.trigger.guides.regenerate import regenerate_all

    handle = guides.add("fkchain", side="L", name="arm")
    regenerate_all(guides.document)
```

- [x] **Step 2: Run the test to verify it fails**

Run: `TP tests/unit/test_guides_trigger.py -k drawn_under`
Expected: FAIL — `keys == {""}`.

- [x] **Step 3: Stamp the name**

In `nodes.create_guide_joint`, add `tags.NAME` to the `tags.tag(...)` call:

```python
    tags.tag(
        joint,
        **{
            tags.KIND: tags.GUIDE,
            tags.MODULE: module.module_type,
            tags.INSTANCE: module.instance_id,
            tags.ROLE: role,
            tags.INDEX: index,
            tags.SIDE: module.side.value,
            # with SIDE, this is the display key the rendering was made
            # under; reconcile compares it to catch a rename
            tags.NAME: module.name,
        },
    )
```

Update `tags.py`'s comment on `NAME`, which claims "root guide only":

```python
NAME = "trg_name"  # user facing instance name; with SIDE, the drawn display key
```

- [x] **Step 4: Read it back in the snapshot**

In `snapshot.py`, import the pure key helper at the top:

```python
from tik.trigger.core.manifest import instance_key
```

and add the field to the `RenderedGuide(...)` construction, after `attrs=...`:

```python
                key=instance_key(
                    data.get(tags.NAME, ""), data.get(tags.SIDE, "C")
                )
                if data.get(tags.NAME)
                else "",
```

- [x] **Step 5: Run the test to verify it passes**

Run: `TP tests/unit/test_guides_trigger.py -k drawn_under`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/python/tik/trigger/guides/nodes.py src/python/tik/trigger/guides/snapshot.py src/python/tik/trigger/maya/tags.py tests/unit/test_guides_trigger.py
git commit -m "Stamp the drawn display key on every guide joint

reconcile needs it to notice a rename; nothing else reads it."
```

---

### Task 4: Capture can be scoped

`draw(poses="keep")` must capture only the modules it is about to redraw, not the whole scene.

**Files:**
- Modify: `src/python/tik/trigger/guides/capture.py:42-88`
- Test: `tests/unit/test_capture_trigger.py`

**Interfaces:**
- Produces: `capture(document, rendered=None, scope=None) -> bool`, where `scope` is an iterable of instance ids or None for every module.

- [x] **Step 1: Write the failing test**

Read `tests/unit/test_capture_trigger.py` for its existing document/rendered helpers and follow them. Append:

```python
def test_scope_limits_which_modules_are_captured():
    document = _two_module_document()  # ids "id1" and "id2"
    rendered = _moved_rendering(document)  # both modules moved in the scene
    assert capture(document, rendered, scope=["id1"]) is True
    assert document.module("id1").guides[0].position != (0.0, 0.0, 0.0)
    assert document.module("id2").guides[0].position == (0.0, 0.0, 0.0)


def test_scope_none_captures_everything():
    document = _two_module_document()
    rendered = _moved_rendering(document)
    assert capture(document, rendered) is True
    assert document.module("id2").guides[0].position != (0.0, 0.0, 0.0)
```

If `_two_module_document` / `_moved_rendering` do not exist, write them at the top of the file next to the existing helpers, building two `ModuleEntry` objects with one `GuideRecord` each at the origin, and a `RenderedGuide` per module at `(1.0, 2.0, 3.0)`.

- [x] **Step 2: Run the tests to verify they fail**

Run: `TP tests/unit/test_capture_trigger.py -k scope`
Expected: FAIL with `TypeError: capture() got an unexpected keyword argument 'scope'`.

- [x] **Step 3: Add the parameter**

Change the signature and the loop in `capture.py`:

```python
def capture(
    document: GuideDocument,
    rendered: Optional[list] = None,
    scope: Optional[Iterable[str]] = None,
) -> bool:
    """Fold the scene's poses and guide attrs into ``document``.

    Args:
        document: Mutated in place.
        rendered: A ``RenderedGuide`` list; read from the scene when omitted.
        scope: Instance ids to capture, or None for every module. Draw uses
            it to capture exactly the modules it is about to redraw, without
            quietly pulling the rest of the scene in as a side effect.

    Returns:
        True when anything changed.
    """
```

Add `from typing import Iterable, Optional` to the imports, and filter at the top of the module loop:

```python
    wanted = None if scope is None else set(scope)
    changed = False
    for entry in document.modules:
        if wanted is not None and entry.instance_id not in wanted:
            continue
        found = by_instance.get(entry.instance_id)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `TP tests/unit/test_capture_trigger.py`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/python/tik/trigger/guides/capture.py tests/unit/test_capture_trigger.py
git commit -m "Let capture be scoped to a set of instances

Draw captures exactly what it is about to redraw, rather than pulling
the whole scene in as a side effect."
```

---

### Task 5: `GuideScene` gets one method per direction

The centre of the change. After this task nothing in `GuideScene` moves data both ways.

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py:44-46` (`auto_sync` comment), `56-75` (`_apply`), `100-165` (`dismissed`, `restore`, `sync`), `290-296` (`create_guides`), `680-683` (`test_build`)
- Test: `tests/unit/test_guide_scene_trigger.py`

**Interfaces:**
- Consumes: `capture(..., scope=)` from Task 4; `GuideDiff.not_drawn` / `.stale` from Task 1.
- Produces: `GuideScene.draw(scope=None, poses="keep") -> GuideDiff` and `GuideScene.sync(scope=None) -> GuideDiff`. `GuideScene.dismissed`, `GuideScene.restore()` and `sync(regenerate_stale=)` no longer exist.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_guide_scene_trigger.py`, using its existing `guides` fixture:

```python
def test_adding_a_module_creates_no_joints(guides):
    handle = guides.add("fkchain", side="L", name="arm")
    assert guides.guide_nodes(handle.instance_id) == {}
    assert guides.diff().not_drawn == [handle.instance_id]


def test_changing_a_setting_leaves_the_joints_alone(guides):
    handle = guides.add("fkchain", side="L", name="arm")
    guides.draw()
    before = {node.long_name for node in guides.guide_nodes(handle.instance_id).values()}
    handle.settings["segments"] = 5
    after = {node.long_name for node in guides.guide_nodes(handle.instance_id).values()}
    assert after == before
    assert guides.diff().stale == [handle.instance_id]


def test_sync_never_creates_or_deletes_a_joint(guides):
    guides.add("fkchain", side="L", name="arm")
    guides.draw()
    before = {guide.node for guide in snapshot()}
    guides.sync()
    assert {guide.node for guide in snapshot()} == before


def test_draw_keeps_poses_by_default(guides):
    handle = guides.add("fkchain", side="L", name="arm")
    guides.draw()
    root = guides.guide_node(handle.instance_id, handle.module_class.guides.root)
    cmds.xform(root.long_name, worldSpace=True, translation=(7.0, 0.0, 0.0))
    guides.draw([handle.instance_id])
    moved = guides.guide_node(handle.instance_id, handle.module_class.guides.root)
    assert cmds.xform(
        moved.long_name, query=True, worldSpace=True, translation=True
    )[0] == pytest.approx(7.0)


def test_draw_with_discard_rebuilds_at_the_stored_pose(guides):
    handle = guides.add("fkchain", side="L", name="arm")
    guides.draw()
    root = guides.guide_node(handle.instance_id, handle.module_class.guides.root)
    stored = cmds.xform(root.long_name, query=True, worldSpace=True, translation=True)
    cmds.xform(root.long_name, worldSpace=True, translation=(7.0, 0.0, 0.0))
    guides.draw([handle.instance_id], poses="discard")
    moved = guides.guide_node(handle.instance_id, handle.module_class.guides.root)
    assert cmds.xform(
        moved.long_name, query=True, worldSpace=True, translation=True
    )[0] == pytest.approx(stored[0])
```

Add `import pytest`, `from maya import cmds` and `from tik.trigger.guides.snapshot import snapshot` at the top of the file if they are not already there.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TP tests/unit/test_guide_scene_trigger.py -k "no_joints or leaves_the_joints or never_creates or keeps_poses or discard"`
Expected: FAIL with `AttributeError: 'GuideScene' object has no attribute 'draw'`.

- [ ] **Step 3: Rewrite `_apply`**

Replace the whole `_apply` method:

```python
    def _apply(self, entry) -> None:
        """Record a document edit. **The scene is not touched.**

        This used to capture and then redraw the module. Both are gone: a
        redraw that happens because a field changed is the tool moving the
        rigger's work without being asked, and the capture only existed to
        stop that redraw from rebuilding on stale records. With no redraw
        there is nothing to protect against, and capture goes back to being
        a deliberate act -- ``sync()``.
        """
        self._touch()
```

`entry` is now unused but every call site passes it; keep the parameter so the call sites are untouched.

- [ ] **Step 4: Delete `dismissed` and `restore`, and rewrite `sync`**

Remove the `dismissed` property, its setter and `restore()` entirely (`scene.py:100-114`). Remove `self.dismissed = False` from `create_guides` (`scene.py:294`).

Replace `sync`:

```python
    def sync(self, scope: Optional[Iterable[str]] = None):
        """Read the scene's poses and guide attrs into the document.

        One direction, always. Sync can create nothing, delete nothing and
        move nothing: after this call the scene is byte-for-byte what it was.
        Rebuilding a rendering is ``draw()``'s job and only ever happens
        because somebody pressed a button.

        Args:
            scope: Instance ids to capture, or None for every module.

        Returns:
            The :class:`~tik.trigger.core.reconcile.GuideDiff` as the scene
            now stands.
        """
        from tik.trigger.core.reconcile import GuideDiff

        if self._syncing:
            return GuideDiff()
        self._syncing = True
        try:
            if capture(self.document, snapshot(), scope=scope):
                self._touch()
            return self.diff()
        finally:
            self._syncing = False
```

Add `Iterable` to the `typing` import at the top of `scene.py`.

- [ ] **Step 5: Add `draw`**

Immediately after `sync`:

```python
    def draw(self, scope: Optional[Iterable[str]] = None, poses: str = "keep"):
        """Render modules into the scene, rebuilding what is already there.

        The other direction, and the only thing that ever creates a guide
        joint. Never automatic: every call is a button somebody pressed.

        Args:
            scope: Instance ids to draw, or None for every module.
            poses: ``"keep"`` captures the scoped drift first, so a guide the
                rigger has dragged goes back where they put it. ``"discard"``
                skips that capture and rebuilds at the stored poses.

        Returns:
            The :class:`~tik.trigger.core.reconcile.GuideDiff` afterwards.

        Raises:
            GuideError: when ``poses`` is neither ``"keep"`` nor ``"discard"``.
        """
        if poses not in ("keep", "discard"):
            raise GuideError(f"draw(poses={poses!r}): expected 'keep' or 'discard'.")
        wanted = None if scope is None else set(scope)
        entries = [
            entry
            for entry in regenerate_module.ordered(self.document)
            if wanted is None or entry.instance_id in wanted
        ]
        if not entries:
            return self.diff()
        if poses == "keep":
            # Scoped deliberately: drawing one module must not quietly pull
            # the rest of the scene into the document as a side effect.
            if capture(
                self.document,
                snapshot(),
                scope=[entry.instance_id for entry in entries],
            ):
                self._touch()
        with nodes.undo_chunk("Trigger draw guides"):
            for entry in entries:
                regenerate(entry, self.document)
        return self.diff()
```

- [ ] **Step 6: Fix `test_build`**

`GuideScene.test_build` (`scene.py:676-683`) calls `self.sync(regenerate_stale=False)`. Replace its body's sync line with the full sync-then-draw preamble:

```python
    def test_build(self, *handles: GuideHandle, rig_name: str = "test") -> Any:
        """Build the given modules (or every module) into a throwaway rig.

        Draws first, and has to: ``find_instances`` reads tagged joints, so a
        module nobody has drawn contributes nothing and would be skipped in
        silence. The sync before it makes the draw lossless, which is why this
        path never has to ask about discarding poses.
        """
        ids = [handle.instance_id for handle in handles]
        scope = ids or "scene"
        from tik.trigger.maya.build import Builder

        self.sync()
        self.draw(ids or None)
        return Builder(self.events).build(
            scope=scope, document=self.document, rig_name=rig_name, afterlife="keep"
        )
```

- [ ] **Step 7: Run the tests**

Run: `TP tests/unit/test_guide_scene_trigger.py`
Expected: PASS. Tests that relied on a write redrawing the scene will fail — fix them by adding an explicit `guides.draw()`, which is the behaviour change this task exists to make.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/guides/scene.py tests/unit/test_guide_scene_trigger.py
git commit -m "Give GuideScene one method per direction

sync() captures and never regenerates; draw() regenerates and only
captures when told to; _apply() touches the document and never touches
the scene. dismissed and restore() go with the automatic redraw."
```

---

### Task 6: Delete `dismissed` from the document, the tags and the build

**Files:**
- Modify: `src/python/tik/trigger/core/guide_document.py:194-197`, `src/python/tik/trigger/maya/tags.py:19`, `src/python/tik/trigger/maya/build.py:127-140,229`, `src/python/tik/trigger/session.py:280-286`
- Test: `tests/unit/test_session_guides_trigger.py`, `tests/integration/trigger/test_session_checkout_trigger.py`

**Interfaces:**
- Consumes: `GuideScene.draw` from Task 5.
- Produces: `apply_afterlife(instances, mode)` — two parameters. `Session.checkout_guides(force=False)` clears and stamps without drawing.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_session_guides_trigger.py`:

```python
def test_checkout_does_not_draw(tmp_path):
    session = Session()
    session.guides.add("fkchain", side="L", name="arm")
    session.checkout_guides()
    assert session.guides.diff().not_drawn == [
        entry.instance_id for entry in session.document.guides.modules
    ]
```

Match the file's existing `Session` import and fixture style — read the neighbouring tests first.

- [ ] **Step 2: Run it to verify it fails**

Run: `TP tests/unit/test_session_guides_trigger.py -k does_not_draw`
Expected: FAIL — `not_drawn == []`, because checkout drew the guides.

- [ ] **Step 3: Delete the field and the tag**

In `core/guide_document.py`, delete the `dismissed` field and its two comment lines (194-197).

In `maya/tags.py`, delete the `DISMISSED` line. It is defined and read nowhere else — confirm with `grep -rn DISMISSED src tests` before deleting, and expect no other hits.

- [ ] **Step 4: Simplify `apply_afterlife`**

In `maya/build.py`:

```python
def apply_afterlife(instances, mode: str) -> None:
    """What happens to the guides once the rig is built.

    The document outlives the rendering and nothing redraws by itself, so
    taking the guides away needs no record: they are simply not drawn, and
    the rigger presses Draw when they want them back.
    """
    if mode == "keep":
        return
    if not cmds.objExists(tags.GUIDE_HOLDER):
        return
    ...
```

Keep everything from `holder = guide_nodes.holder()` down unchanged, and delete the `if document is not None: document.dismissed = True` block. Change the call at line 229 to `apply_afterlife(instances, afterlife)`.

- [ ] **Step 5: Stop `checkout_guides` from drawing**

In `session.py`, delete the `regenerate.regenerate_all(scene.document)` line so the tail reads:

```python
        scene = self.guides
        # Clear, but never draw: taking the scene over has to remove the
        # previous session's rendering, or this session's reconcile reads it
        # as orphans. What this session draws is the rigger's call.
        scene.clear_rendering()
        document_store.write_stamp(self.session_id)
```

Remove the now-unused `regenerate` import from `session.py` if nothing else in the file uses it — check with `grep -n regenerate src/python/tik/trigger/session.py`.

- [ ] **Step 6: Run the affected suites**

Run: `TP tests/unit/test_session_guides_trigger.py` then `TP tests/integration/trigger/test_session_checkout_trigger.py`
Expected: PASS. The checkout tests that assert joints exist after `checkout_guides()` must gain an explicit `session.guides.draw()` — that is the behaviour change.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/core/guide_document.py src/python/tik/trigger/maya/tags.py src/python/tik/trigger/maya/build.py src/python/tik/trigger/session.py tests/unit/test_session_guides_trigger.py tests/integration/trigger/test_session_checkout_trigger.py
git commit -m "Delete dismissed, and stop checkout from drawing

The flag existed to stop the next reconcile redrawing guides a build had
taken away. With no automatic redraw there is nothing to suppress."
```

---

### Task 7: Orphan guides are never built

**Files:**
- Modify: `src/python/tik/trigger/guides/nodes.py:230-248` (`find_instances`)
- Test: `tests/integration/trigger/test_builder_trigger.py`

**Interfaces:**
- Produces: `find_instances(scope, document)` skips instance ids absent from `document` when `document is not None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_builder_trigger.py`, following its existing fixtures:

```python
def test_a_guide_with_no_document_entry_is_not_built(guides):
    handle = guides.add("fkchain", side="L", name="arm")
    guides.draw()
    # the joints stay, the entry goes: exactly what an orphan is
    guides.document.modules = [
        entry
        for entry in guides.document.modules
        if entry.instance_id != handle.instance_id
    ]
    assert guides.find_instances("scene") == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `TP tests/integration/trigger/test_builder_trigger.py -k no_document_entry`
Expected: FAIL — one phantom instance named `fkchain` comes back.

- [ ] **Step 3: Add the guard**

In `find_instances`, replace the document defaulting and the loop head:

```python
    from tik.trigger.core.guide_document import GuideDocument

    # None means "no document to check against" -- the guard below would
    # otherwise reject every instance in the scene.
    known = None if document is None else {
        entry.instance_id for entry in document.modules
    }
    document = document if document is not None else GuideDocument()
    keys = {entry.instance_id: entry.key for entry in document.modules}
    instances = []
    for instance_id, nodes in grouped.items():
        if known is not None and instance_id not in known:
            continue  # an orphan: reported by reconcile, never built
        entry = document.module(instance_id)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `TP tests/integration/trigger/test_builder_trigger.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/guides/nodes.py tests/integration/trigger/test_builder_trigger.py
git commit -m "Never build a guide with no document entry

It used to build as a phantom module named after its type, with default
settings and no connections."
```

---

### Task 8: A pipeline build captures before it resets the scene

**Files:**
- Modify: `src/python/tik/trigger/actions/kinematics/kinematics.py:90-101`
- Test: `tests/integration/trigger/test_draw_sync_trigger.py` (created here)

**Interfaces:**
- Consumes: `GuideScene.sync()` from Task 5.

- [ ] **Step 1: Read how the run reaches `kinematics`**

Before writing code, read `src/python/tik/trigger/actions/kinematics/kinematics.py` in full and find where the scene reset happens relative to it (`grep -rn "new_scene\|reset" src/python/tik/trigger/maya/runner.py src/python/tik/trigger/session.py`). The capture must run **before** the reset, not inside the action — an action that runs after the reset has nothing left to capture.

- [ ] **Step 2: Write the failing test**

Create `tests/integration/trigger/test_draw_sync_trigger.py` with the header and this test. Model the fixtures on the file it replaces, `test_lockstep_trigger.py`.

```python
"""Draw and Sync: the two directions, and the guarantee that neither
crosses into the other's job.

Replaces test_lockstep_trigger.py. Lockstep is gone as a concept: the
document no longer chases the scene, and the scene no longer chases the
document. Each direction moves only when it is asked to.
"""


def test_a_build_captures_before_it_resets_the_scene(session):
    handle = session.guides.add("fkchain", side="L", name="arm")
    session.guides.draw()
    root = session.guides.guide_node(handle.instance_id, handle.module_class.guides.root)
    cmds.xform(root.long_name, worldSpace=True, translation=(7.0, 0.0, 0.0))
    session.guides.auto_sync = False  # nothing has captured that drag

    session.build()

    record = session.document.guides.module(handle.instance_id).guides[0]
    assert record.position[0] == pytest.approx(7.0)
```

- [ ] **Step 3: Run it to verify it fails**

Run: `TP tests/integration/trigger/test_draw_sync_trigger.py -k resets_the_scene`
Expected: FAIL — the stored position is still the drawn one; the drag was lost at the reset.

- [ ] **Step 4: Capture before the reset**

At the point identified in Step 1, immediately before the scene is reset, add:

```python
        # A reset destroys the guides, and with Auto off nothing has read
        # them since the rigger last dragged one. Capture is the scene's only
        # chance to reach the document before it goes.
        if session.owns_scene_guides:
            session.guides.sync()
```

Use the receiver the surrounding code already has for the session — read it rather than assuming the name.

- [ ] **Step 5: Run it to verify it passes**

Run: `TP tests/integration/trigger/test_draw_sync_trigger.py`
Expected: PASS.

- [ ] **Step 6: Delete the file this one replaces**

```bash
git rm tests/integration/trigger/test_lockstep_trigger.py
```

Before deleting, read it once and carry over any test that is still meaningful — the pose-drift-wins and structural-redraw cases become `draw`/`sync` tests. Its `dismissed` and `restore` tests (lines 163, 291, 307, 323, 331) have nothing to test any more and go.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/actions/kinematics/kinematics.py tests/integration/trigger/test_draw_sync_trigger.py
git commit -m "Capture the guides before a build resets the scene

With Auto off nothing had read them since the last drag, so the posing
went out with the reset."
```

---

### Task 9: `Feedback` can label its buttons

**Files:**
- Modify: `src/python/tik/shared/ui/feedback.py:101-155` (`_pop`), `211-231` (`pop_question`)
- Test: `tests/ui/test_feedback.py`

**Interfaces:**
- Produces: `pop_question(..., buttons=[("key", "Label"), "plainkey", ...])`. Plain string keys behave exactly as before; the returned value is always the key, never the label.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_feedback.py`, following its existing `set_handler` style:

```python
def test_a_labelled_button_still_answers_with_its_key():
    seen = {}

    def handler(kind, title, text, details, buttons):
        seen["buttons"] = buttons
        return "discard"

    feedback.set_handler(handler)
    try:
        answer = feedback.Feedback().pop_question(
            "Redraw", "moved", buttons=[("yes", "Sync and redraw"), "discard", "cancel"]
        )
    finally:
        feedback.set_handler(None)
    assert answer == "discard"
    assert seen["buttons"] == ["yes", "discard", "cancel"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `TPUI tests/ui/test_feedback.py -k labelled_button`
Expected: FAIL — the handler receives the raw tuple, so `seen["buttons"]` is `[("yes", "Sync and redraw"), ...]`.

- [ ] **Step 3: Normalise in `_pop`**

At the top of `_pop`, before the handler call, split keys from labels:

```python
        # buttons may carry a custom label: ("yes", "Sync and redraw"). The
        # key is what callers pass and what comes back; the label only
        # changes what the button says.
        labels = {}
        keys = []
        for item in buttons:
            if isinstance(item, tuple):
                key, label = item
                labels[key] = label
            else:
                key = item
            keys.append(key)
        buttons = keys
```

Then, after `message_box.setDefaultButton(...)`, apply the labels:

```python
        for key, label in labels.items():
            button = message_box.button(BUTTONS[key])
            if button is not None:
                button.setText(label)
```

Everything downstream already works on `buttons` as a key list, including the validation loop and the result mapping.

- [ ] **Step 4: Run it to verify it passes**

Run: `TPUI tests/ui/test_feedback.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/shared/ui/feedback.py tests/ui/test_feedback.py
git commit -m "Let a Feedback question label its buttons

Callers still pass and receive keys; only the button text changes."
```

---

### Task 10: The two-ended action bar

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/action_bar.py` (rewritten)
- Test: `tests/ui/test_action_bar.py`

**Interfaces:**
- Produces: `DesignerActionBar` with signals `draw_selected_requested`, `draw_all_requested`, `select_requested`, `mirror_requested`, `sync_requested`, `auto_sync_toggled(bool)`, `build_all_requested`; and methods `set_selection_enabled(on: bool)`, `set_pending(stale_selected: bool, stale_any: bool, moved: bool)`, `set_auto_sync(on: bool)`.

- [ ] **Step 1: Write the failing tests**

Rewrite `tests/ui/test_action_bar.py`. Keep its existing `bar` fixture.

```python
def test_the_two_draw_buttons_emit(bar):
    seen = []
    bar.draw_selected_requested.connect(lambda: seen.append("selected"))
    bar.draw_all_requested.connect(lambda: seen.append("all"))
    bar.set_selection_enabled(True)
    bar.draw_selected_button.click()
    bar.draw_all_button.click()
    assert seen == ["selected", "all"]


def test_selection_buttons_disable_with_no_selection(bar):
    bar.set_selection_enabled(False)
    assert bar.draw_selected_button.isEnabled() is False
    assert bar.select_button.isEnabled() is False
    assert bar.mirror_button.isEnabled() is False


def test_pending_colours_each_end_independently(bar):
    bar.set_pending(stale_selected=True, stale_any=True, moved=False)
    assert bar.draw_selected_button.property("alert") is True
    assert bar.draw_all_button.property("alert") is True
    assert bar.sync_button.property("alert") is False

    bar.set_pending(stale_selected=False, stale_any=False, moved=True)
    assert bar.draw_all_button.property("alert") is False
    assert bar.sync_button.property("alert") is True


def test_not_drawn_never_lights_the_bar(bar):
    """Orange means out of date. A freshly opened session is all
    not-drawn, and lighting the whole left end up on open is noise."""
    bar.set_pending(stale_selected=False, stale_any=False, moved=False)
    assert bar.draw_all_button.property("alert") is False


def test_setting_auto_sync_does_not_report_it_back(bar):
    seen = []
    bar.auto_sync_toggled.connect(seen.append)
    bar.set_auto_sync(False)
    assert seen == []
    assert bar.sync_button.property("quiet") is False
```

Delete `test_up_to_date_shows_only_when_auto_is_off_and_drift_is_clean` and every other test referencing `set_selection`, `set_drift`, `drift_pill`, `up_to_date_label` or `build_selected_button`.

- [ ] **Step 2: Run to verify they fail**

Run: `TPUI tests/ui/test_action_bar.py`
Expected: FAIL with `AttributeError: 'DesignerActionBar' object has no attribute 'draw_selected_button'`.

- [ ] **Step 3: Rewrite the bar**

Replace `action_bar.py` entirely:

```python
"""The Guide Designer's bottom bar (spec 8).

Two directions, one at each end, with a rule between them. The caption on
each group names where that group's data *lands*, so "which button writes to
my scene?" is answerable from the bar alone:

    -> SCENE   draws the session into Maya
    -> SESSION reads Maya back into the session

The bar knows nothing about the scene: it emits, the Designer acts.
"""

from __future__ import annotations

from tik.shared.ui.Qt import QtCore, QtWidgets


class DesignerActionBar(QtWidgets.QFrame):
    """The full-width action row under the Designer's four panes."""

    draw_selected_requested = QtCore.Signal()
    draw_all_requested = QtCore.Signal()
    select_requested = QtCore.Signal()
    mirror_requested = QtCore.Signal()
    sync_requested = QtCore.Signal()
    auto_sync_toggled = QtCore.Signal(bool)
    build_all_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # the Session sub-tab's build bar wears the same object name; one
        # look for both sub-tabs is the point
        self.setObjectName("BuildBar")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)

        layout.addWidget(self._caption("→ SCENE"))
        self.draw_selected_button = QtWidgets.QPushButton("Draw selected")
        self.draw_selected_button.setToolTip(
            "Draw the selected modules' guides into the scene"
        )
        self.draw_all_button = QtWidgets.QPushButton("Draw all")
        self.draw_all_button.setToolTip("Draw every module's guides into the scene")
        layout.addWidget(self.draw_selected_button)
        layout.addWidget(self.draw_all_button)

        layout.addWidget(self._rule())
        self.select_button = QtWidgets.QPushButton("Select")
        self.mirror_button = QtWidgets.QPushButton("Mirror")
        layout.addWidget(self.select_button)
        layout.addWidget(self.mirror_button)

        layout.addStretch(1)

        layout.addWidget(self._caption("→ SESSION"))
        self.sync_button = QtWidgets.QPushButton("Sync")
        self.sync_button.setObjectName("SyncButton")
        self.sync_button.setToolTip("Read the guides in the scene into this session")
        layout.addWidget(self.sync_button)
        self.auto_check = QtWidgets.QCheckBox("Auto")
        self.auto_check.setChecked(True)
        self.auto_check.setToolTip(
            "Follow the scene automatically. "
            "Off, the session updates only when you press Sync."
        )
        layout.addWidget(self.auto_check)

        layout.addWidget(self._rule())
        self.build_all_button = QtWidgets.QPushButton("▶  Build all")
        self.build_all_button.setObjectName("PrimaryButton")
        layout.addWidget(self.build_all_button)

        self.draw_selected_button.clicked.connect(self.draw_selected_requested)
        self.draw_all_button.clicked.connect(self.draw_all_requested)
        self.select_button.clicked.connect(self.select_requested)
        self.mirror_button.clicked.connect(self.mirror_requested)
        self.sync_button.clicked.connect(self.sync_requested)
        self.auto_check.toggled.connect(self.auto_sync_toggled)
        self.build_all_button.clicked.connect(self.build_all_requested)

        self.set_selection_enabled(False)
        self.set_pending(False, False, False)

    @staticmethod
    def _caption(text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setObjectName("FieldCaption")
        return label

    @staticmethod
    def _rule() -> QtWidgets.QFrame:
        # a QFrame.VLine here does not paint under QSS `color:` and ignores
        # `max-width`; a plain QFrame with an explicit fixed width is what
        # actually renders a crisp 1px divider
        rule = QtWidgets.QFrame()
        rule.setObjectName("BarRule")
        rule.setMinimumWidth(1)
        rule.setMaximumWidth(1)
        return rule

    # ------------------------------------------------------------- state
    def set_selection_enabled(self, on: bool) -> None:
        """Enable the three controls that act on the selected modules."""
        for button in (
            self.draw_selected_button,
            self.select_button,
            self.mirror_button,
        ):
            button.setEnabled(bool(on))

    def set_pending(
        self, stale_selected: bool, stale_any: bool, moved: bool
    ) -> None:
        """Colour each end for the work waiting in *its* direction.

        Out of date only. Not-drawn deliberately does not light anything: a
        freshly opened session is entirely not-drawn, and that is its resting
        state, not a warning. Out of date means the scene contradicts the
        session; not drawn means the scene is merely silent.
        """
        self._set_alert(self.draw_selected_button, stale_selected)
        self._set_alert(self.draw_all_button, stale_any)
        self._set_alert(self.sync_button, moved)

    def set_auto_sync(self, on: bool) -> None:
        """Reflect the setting without reporting it back as a user action.

        The menu action and this checkbox are one setting with two front
        doors; without the block they would ping-pong.
        """
        self.auto_check.blockSignals(True)
        try:
            self.auto_check.setChecked(bool(on))
        finally:
            self.auto_check.blockSignals(False)
        self.sync_button.setProperty("quiet", bool(on))
        self._repolish(self.sync_button)

    @classmethod
    def _set_alert(cls, button, on: bool) -> None:
        button.setProperty("alert", bool(on))
        cls._repolish(button)

    @staticmethod
    def _repolish(widget) -> None:
        """Qt does not restyle on a property change unless asked."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)
```

- [ ] **Step 4: Run to verify they pass**

Run: `TPUI tests/ui/test_action_bar.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/ui/designer/action_bar.py tests/ui/test_action_bar.py
git commit -m "Put the two directions at opposite ends of the bar

Each caption names where its group's data lands. The selection label and
both count pills come off: the tree, the graph and the status bar
already say all three things."
```

---

### Task 11: The tree paints the three states

**Files:**
- Create: `src/python/tik/trigger/ui/designer/delegates.py`
- Modify: `src/python/tik/trigger/ui/designer/widgets.py` (`GuideTree.__init__`)
- Test: `tests/ui/test_guide_state_delegate.py` (created here)

**Interfaces:**
- Produces: `DrawStateRole` (a `QtCore.Qt.UserRole + n` int), the string constants `NOT_DRAWN = "not_drawn"`, `DRAWN = "drawn"`, `STALE = "stale"`, and `GuideStateDelegate`. Task 13 sets `DrawStateRole` on each tree item.

- [ ] **Step 1: Check the role number is free**

Read `src/python/tik/trigger/ui/model.py` and note the highest `QtCore.Qt.UserRole + N` already used. Use the next free number, in `delegates.py`, not in `model.py` — `model.py` serves the pipeline tree.

- [ ] **Step 2: Write the failing test**

Create `tests/ui/test_guide_state_delegate.py`:

```python
"""The guide tree's draw-state dot."""

from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.ui.designer.delegates import (
    DRAWN,
    NOT_DRAWN,
    STALE,
    DrawStateRole,
    GuideStateDelegate,
)


def _painted(state):
    """Render one row and give back the pixel at the dot's centre."""
    widget = QtWidgets.QTreeWidget()
    widget.setColumnCount(1)
    item = QtWidgets.QTreeWidgetItem(["L_arm"])
    item.setData(0, DrawStateRole, state)
    widget.addTopLevelItem(item)
    delegate = GuideStateDelegate()
    image = QtGui.QImage(200, 20, QtGui.QImage.Format_ARGB32)
    image.fill(QtGui.QColor("#151515"))
    painter = QtGui.QPainter(image)
    option = QtWidgets.QStyleOptionViewItem()
    option.rect = QtCore.QRect(0, 0, 200, 20)
    try:
        delegate.paint(painter, option, widget.model().index(0, 0))
    finally:
        painter.end()
    return image.pixelColor(GuideStateDelegate.GUTTER // 2, 10)


def test_stale_paints_the_accent():
    assert _painted(STALE).name() == "#fe7e00"


def test_drawn_and_not_drawn_are_not_the_accent():
    assert _painted(DRAWN).name() != "#fe7e00"
    assert _painted(NOT_DRAWN).name() != "#fe7e00"


def test_the_three_states_paint_differently():
    assert len({_painted(state).name() for state in (NOT_DRAWN, DRAWN, STALE)}) == 3
```

- [ ] **Step 3: Run to verify it fails**

Run: `TPUI tests/ui/test_guide_state_delegate.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'tik.trigger.ui.designer.delegates'`.

- [ ] **Step 4: Write the delegate**

Create `src/python/tik/trigger/ui/designer/delegates.py`:

```python
"""The guide tree's draw-state dot.

    [dot] [icon] name

One marker per module, in the same three states the graph paints, from the
same diff object -- the two panes must never disagree about what is in the
scene. Follows the gutter-dot idiom ``ui/delegates.PipelineDelegate``
already establishes for the pipeline tree.
"""

from __future__ import annotations

from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets

#: Item role carrying one of the three state constants below.
DrawStateRole = QtCore.Qt.UserRole + 20

NOT_DRAWN = "not_drawn"
DRAWN = "drawn"
STALE = "stale"

#: dot colour per state; NOT_DRAWN is drawn as a ring, not a fill
COLORS = {
    NOT_DRAWN: "#5a5a5a",
    DRAWN: "#3f3f3f",
    STALE: "#FE7E00",
}
DIMMED_TEXT = "#757575"


class GuideStateDelegate(QtWidgets.QStyledItemDelegate):
    """Paints a state dot in a left gutter, then the row as usual."""

    GUTTER = 14
    DOT = 7

    def paint(self, painter: QtGui.QPainter, option, index) -> None:
        state = index.data(DrawStateRole) or DRAWN
        shifted = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(shifted, index)
        shifted.rect = option.rect.adjusted(self.GUTTER, 0, 0, 0)
        if state == NOT_DRAWN:
            # absent from the scene: say so in the text too, so a glance at
            # the tree separates "not there" from "there and wrong"
            shifted.palette.setColor(
                QtGui.QPalette.Text, QtGui.QColor(DIMMED_TEXT)
            )
            shifted.palette.setColor(
                QtGui.QPalette.HighlightedText, QtGui.QColor(DIMMED_TEXT)
            )
        super().paint(painter, shifted, index)

        painter.save()
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            centre = QtCore.QPointF(
                option.rect.left() + self.GUTTER / 2.0,
                option.rect.center().y() + 1,
            )
            color = QtGui.QColor(COLORS.get(state, COLORS[DRAWN]))
            if state == NOT_DRAWN:
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.setPen(QtGui.QPen(color, 1.0))
            else:
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(color)
            radius = self.DOT / 2.0
            painter.drawEllipse(centre, radius, radius)
        finally:
            painter.restore()
```

- [ ] **Step 5: Install it on the tree**

In `widgets.py`, at the end of `GuideTree.__init__`:

```python
        from .delegates import GuideStateDelegate

        self.setItemDelegateForColumn(0, GuideStateDelegate(self))
```

- [ ] **Step 6: Run to verify it passes**

Run: `TPUI tests/ui/test_guide_state_delegate.py`
Expected: PASS. If `test_the_three_states_paint_differently` fails because the ring's centre pixel is the background, sample at the ring's edge instead — `GuideStateDelegate.GUTTER // 2 - GuideStateDelegate.DOT // 2` — and say so in the test's docstring.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/ui/designer/delegates.py src/python/tik/trigger/ui/designer/widgets.py tests/ui/test_guide_state_delegate.py
git commit -m "Paint each module's draw state in the guide tree"
```

---

### Task 12: The graph node paints the same three states

**Files:**
- Modify: `src/python/tik/trigger/ui/graph/items.py:90-104` (`NodeSpec`), `185-205` (`NodeItem.paint`), `src/python/tik/trigger/ui/graph/scene.py`
- Test: `tests/ui/test_graph_draw_state.py` (created here)

**Interfaces:**
- Consumes: `NOT_DRAWN` / `DRAWN` / `STALE` from Task 11.
- Produces: `NodeSpec.draw_state: str = DRAWN`; `GraphScene` sets it from a `GuideDiff`.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_graph_draw_state.py`:

```python
"""The graph node's draw-state stripe: the tree's dot, on a node."""

from tik.trigger.ui.designer.delegates import DRAWN, NOT_DRAWN, STALE


def test_a_node_defaults_to_drawn(node_spec):
    assert node_spec.draw_state == DRAWN


def test_not_drawn_dims_the_node(node_item_for):
    item = node_item_for(NOT_DRAWN)
    assert item.opacity() < 1.0


def test_drawn_and_stale_are_fully_opaque(node_item_for):
    assert node_item_for(DRAWN).opacity() == 1.0
    assert node_item_for(STALE).opacity() == 1.0
```

Write the two fixtures at the top of the file. Read `tests/ui/` for an existing graph test to copy `NodeSpec`'s construction from; if there is none, build the spec by hand from `NodeSpec`'s fields and wrap it with `NodeItem(spec)`.

- [ ] **Step 2: Run to verify it fails**

Run: `TPUI tests/ui/test_graph_draw_state.py`
Expected: FAIL with `AttributeError: 'NodeSpec' object has no attribute 'draw_state'`.

- [ ] **Step 3: Add the field and the stripe**

In `items.py`, add to `NodeSpec`:

```python
    #: NOT_DRAWN / DRAWN / STALE - the same states the guide tree paints
    draw_state: str = DRAWN
```

with `from tik.trigger.ui.designer.delegates import DRAWN, NOT_DRAWN, STALE` at the top.

In `NodeItem.__init__`, after the spec is stored:

```python
        self.draw_state = spec.draw_state
        # absent from the scene: the whole node recedes, which is exactly
        # what "there is nothing here to look at in Maya" should look like
        self.setOpacity(0.45 if self.draw_state == NOT_DRAWN else 1.0)
```

In `NodeItem.paint`, immediately after `painter.drawRoundedRect(body, 4, 4)`:

```python
        # The left edge is the only free surface on a node: the border is
        # already selection, the dash is already `external`, and the header
        # is full of title, subtitle and collapse glyph.
        if self.draw_state != DRAWN:
            painter.save()
            clip = QtGui.QPainterPath()
            clip.addRoundedRect(body, 4, 4)
            painter.setClipPath(clip)
            painter.setPen(QtCore.Qt.NoPen)
            stripe = QtCore.QRectF(0, 0, 3, self._height)
            if self.draw_state == STALE:
                painter.setBrush(QtGui.QColor(theme.ACCENT))
                painter.drawRect(stripe)
            else:
                painter.setBrush(QtGui.QColor("#5a5a5a"))
                step = 6
                offset = 0.0
                while offset < self._height:
                    painter.drawRect(QtCore.QRectF(0, offset, 3, 3))
                    offset += step
            painter.restore()
```

- [ ] **Step 4: Feed it from the diff**

In `graph/scene.py`, find where `NodeSpec` objects are built (grep for `NodeSpec(`) and give the building method a `states: dict` parameter mapping instance id to one of the three constants, defaulting to `None`. Set `draw_state=states.get(instance_id, DRAWN) if states else DRAWN` on each spec. Task 13 supplies the dict.

- [ ] **Step 5: Run to verify it passes**

Run: `TPUI tests/ui/test_graph_draw_state.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/ui/graph/items.py src/python/tik/trigger/ui/graph/scene.py tests/ui/test_graph_draw_state.py
git commit -m "Paint the draw state on graph nodes too

Same three states as the tree, from the same diff: the two panes must
never disagree about what is in the scene."
```

---

### Task 13: One diff, four consumers

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/window.py:52-70` (`diff_summary`), `375-378` (status fields), `425-551` (`refresh`), `687-732` (`_on_scene_event`, `_show_drift`, `showEvent`), `src/python/tik/trigger/ui/designer/commands.py:245-310`
- Test: `tests/ui/test_designer_status.py`, `tests/ui/test_designer_draw.py` (created here), `tests/ui/stub.py`

**Interfaces:**
- Consumes: everything from Tasks 1, 5, 9, 10, 11, 12.
- Produces: `DesignerCommands.draw_selected()`, `draw_all()`, `_draw(ids)`; `GuideDesigner._show_state(diff)`; `StubScene.draw(scope=None, poses="keep")`.

- [ ] **Step 1: Add `draw` to the UI stub**

In `tests/ui/stub.py`, next to the other recorded calls:

```python
    def draw(self, scope=None, poses: str = "keep"):
        """Record the call; there is no scene to draw into."""
        self.calls.append(("draw", None if scope is None else list(scope), poses))
        return GuideDiff()
```

- [ ] **Step 2: Write the failing tests**

Create `tests/ui/test_designer_draw.py`. Copy the `designer` fixture from an existing file in `tests/ui/` that builds a `GuideDesigner` over a `StubScene`.

```python
"""Draw is manual, and it asks before it discards posing."""

from tik.shared.ui import feedback
from tik.trigger.core.reconcile import GuideDiff, ModuleDiff


def test_draw_all_draws_everything(designer):
    designer.draw_all()
    assert ("draw", None, "keep") in designer.guides.calls


def test_draw_selected_scopes_to_the_selection(designer, one_module):
    designer.tree.setCurrentItem(designer.item_for(one_module.instance_id))
    designer.draw_selected()
    assert ("draw", [one_module.instance_id], "keep") in designer.guides.calls


def test_a_clean_scene_is_never_asked_about(designer, monkeypatch):
    asked = []
    feedback.set_handler(lambda *args: asked.append(args) or "cancel")
    try:
        designer.draw_all()
    finally:
        feedback.set_handler(None)
    assert asked == []


def test_drift_asks_and_discard_is_passed_down(designer, monkeypatch, one_module):
    diff = GuideDiff()
    module = ModuleDiff(one_module.instance_id)
    module.drifted = [("root", 0)]
    diff.modules[one_module.instance_id] = module
    monkeypatch.setattr(designer.guides, "diff", lambda: diff)

    feedback.set_handler(lambda *args: "discard")
    try:
        designer.draw_all()
    finally:
        feedback.set_handler(None)
    assert ("draw", None, "discard") in designer.guides.calls


def test_cancel_draws_nothing(designer, monkeypatch, one_module):
    diff = GuideDiff()
    module = ModuleDiff(one_module.instance_id)
    module.drifted = [("root", 0)]
    diff.modules[one_module.instance_id] = module
    monkeypatch.setattr(designer.guides, "diff", lambda: diff)

    feedback.set_handler(lambda *args: "cancel")
    try:
        designer.draw_all()
    finally:
        feedback.set_handler(None)
    assert not [call for call in designer.guides.calls if call[0] == "draw"]
```

- [ ] **Step 3: Run to verify they fail**

Run: `TPUI tests/ui/test_designer_draw.py`
Expected: FAIL with `AttributeError: 'GuideDesigner' object has no attribute 'draw_all'`.

- [ ] **Step 4: Write the commands**

In `commands.py`, replacing nothing, add next to `sync_now`:

```python
    def draw_selected(self) -> None:
        """Draw the selected modules' guides into the scene."""
        self._draw([handle.instance_id for handle in self.selected_handles()])

    def draw_all(self) -> None:
        """Draw every module's guides into the scene."""
        self._draw(None)

    def _draw(self, ids) -> None:
        """Draw ``ids`` (None for all), asking first if posing is at risk.

        The condition is the whole rule: ask if and only if the scoped diff
        reports drift. Both exemptions fall out of it -- an undrawn module
        has no rendered guides so it cannot be drifted, and an already-synced
        one has no drift either.
        """
        if ids is not None and not ids:
            return
        wanted = None if ids is None else set(ids)
        diff = self.guides.diff()
        dirty = [
            key
            for key in diff.drifted
            if wanted is None or key in wanted
        ]
        poses = "keep"
        if dirty:
            answer = Feedback(self).pop_question(
                title="Redraw guides",
                text=(
                    f"{len(dirty)} module(s) have guides that were moved "
                    "since the last sync."
                ),
                details="Redrawing rebuilds them from the session.",
                buttons=[
                    ("yes", "Sync and redraw"),
                    ("discard", "Discard and redraw"),
                    "cancel",
                ],
            )
            if answer not in ("yes", "discard"):
                return
            poses = "keep" if answer == "yes" else "discard"
        with self.watcher.mute():
            try:
                self.guides.draw(ids, poses=poses)
            except TriggerError as error:
                self.events.log(str(error), level="warning")
        self.refresh()
```

Change `sync_now`'s tail from `self._show_drift(...)` to `self._show_state(...)`, and change `test_build` so `all_modules` no longer needs its own draw — `GuideScene.test_build` already syncs and draws (Task 5).

- [ ] **Step 5: Rewrite the window's indicator plumbing**

In `window.py`, replace `diff_summary` (line 52) so it speaks the new vocabulary:

```python
def diff_summary(diff) -> str:
    """One line describing everything pending, for the status field."""
    parts = []
    if diff.stale:
        parts.append(f"{len(diff.stale)} out of date")
    if diff.not_drawn:
        parts.append(f"{len(diff.not_drawn)} not drawn")
    if diff.drifted:
        parts.append(f"{len(diff.drifted)} moved")
    if diff.orphans:
        parts.append(f"{len(diff.orphans)} orphan guide(s)")
    if diff.duplicates:
        parts.append(f"{len(diff.duplicates)} duplicate guide(s)")
    return " · ".join(parts)
```

Add `"guides"` to the status fields tuple at line 376.

Replace `_show_drift` with:

```python
    def _show_state(self, diff) -> None:
        """Drive all four indicators from one diff object.

        One scan, four consumers -- the bar, the tree, the graph and the
        status field -- so the panes cannot disagree about what is in the
        scene.
        """
        selected = {handle.instance_id for handle in self.selected_handles()}
        stale = set(diff.stale)
        self.action_bar.set_pending(
            stale_selected=bool(stale & selected),
            stale_any=bool(stale),
            moved=bool(diff.drifted),
        )
        self.status.set("guides", diff_summary(diff) or "up to date")
```

In `refresh()`, compute the diff once near the top and pass the per-module states to both panes. Where the tree items are built (around line 476, next to `item.setIcon(0, ...)`), add:

```python
            item.setData(0, DrawStateRole, states.get(entry.instance_id, DRAWN))
```

with `states` built from that same diff:

```python
        diff = self.guides.diff()
        states = {}
        for instance_id, module_diff in diff.modules.items():
            if module_diff.absent:
                states[instance_id] = NOT_DRAWN
            elif module_diff.is_stale:
                states[instance_id] = STALE
            else:
                states[instance_id] = DRAWN
```

Pass `states` to the graph's rebuild (the parameter added in Task 12), and end `refresh()` with `self._show_state(diff)`.

Delete the `dismissed` branch at line 523.

In `_on_scene_event`, replace the sync branch so the returned diff is reused:

```python
        if not self.guides.auto_sync:
            self._show_state(self.guides.diff())
            return
        # Muted throughout: draw deletes and recreates joints, which fires
        # the very events we are handling. Sync itself cannot, but the
        # refresh that follows can.
        with self.watcher.mute():
            try:
                self._show_state(self.guides.sync())
            except Exception as error:  # noqa: BLE001 - keep the tool alive
                self.events.log(f"Guide sync failed: {error}", level="warning")
```

In `showEvent` (line ~730), drop the `if ... or self.guides.auto_sync: return` early exit's `auto_sync` half — both indicators now need priming regardless — and call `self._show_state(self.guides.diff())`.

Import `DRAWN`, `NOT_DRAWN`, `STALE`, `DrawStateRole` from `.delegates` at the top of `window.py`.

- [ ] **Step 6: Update the status tests**

`tests/ui/test_designer_status.py` asserts the old `diff_summary` strings. Rewrite each expectation against the new wording, e.g.:

```python
def test_stale_reads_as_out_of_date():
    diff = GuideDiff()
    module = ModuleDiff("id1")
    module.missing = [("root", 0)]
    diff.modules["id1"] = module
    assert diff_summary(diff) == "1 out of date"
```

- [ ] **Step 7: Run the UI suite**

Run: `TPUI tests/ui`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/ui/designer/window.py src/python/tik/trigger/ui/designer/commands.py tests/ui
git commit -m "Wire Draw into the Designer, and drive four indicators from one diff

Draw asks before it discards posing, and the condition is exactly
'the scoped diff reports drift'."
```

---

### Task 14: Menus, and the last of the dead code

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py:286-325` (Guides menu), `902-917` (`_on_sub_tab_changed`)
- Test: `tests/ui/test_main_menus.py` (or the existing menu test file — find it with `grep -rln "guides_menu\|Sync From Scene" tests/ui`)

- [ ] **Step 1: Write the failing test**

In the menu test file, following its existing style:

```python
def test_the_guides_menu_offers_both_draw_scopes(window):
    labels = [action.text() for action in window.guides_menu.actions()]
    assert "Draw Selected Guides" in labels
    assert "Draw All Guides" in labels
    assert "Delete All Modules" in labels
    assert "Clear Scene Guides" not in labels
```

If the window does not keep `guides_menu` as an attribute, store it in `_build_guides_menu` as `self.guides_menu = guides_menu` and say so in the test's docstring.

- [ ] **Step 2: Run to verify it fails**

Run: `TPUI <the menu test file>`
Expected: FAIL — `"Draw Selected Guides" not in labels`.

- [ ] **Step 3: Add the draw actions and fix the misleading label**

In `main.py`'s Guides menu, above the `Sync From Scene` group:

```python
        guides_menu.addSeparator()
        self._action(
            guides_menu,
            "Draw Selected Guides",
            lambda: self._designer_call("draw_selected"),
        )
        self._action(
            guides_menu,
            "Draw All Guides",
            lambda: self._designer_call("draw_all"),
            "F5",
        )
```

Rename the last entry — the action deletes every module from the session document, not just the rendering, and under this design's vocabulary "Clear Scene Guides" reads as "undraw everything":

```python
        self._action(
            guides_menu,
            "Delete All Modules",
            lambda: self._designer_call("clear_guides"),
        )
```

- [ ] **Step 4: Delete the restore-on-tab-change block**

In `_on_sub_tab_changed`, the whole `try:` block that calls `designer.guides.restore()` goes, leaving:

```python
    def _on_sub_tab_changed(self, view, index: int) -> None:
        """The first time a session's Designer opens, its guides get the scene."""
        if index == DESIGNER_TAB:
            self._hand_over_to(view)
        self._sync_menu_state()
        self._update_title()
```

- [ ] **Step 5: Run to verify it passes**

Run: `TPUI tests/ui`
Expected: PASS.

- [ ] **Step 6: Run everything**

Run: `make tests-unit`, then `make tests-integration`, then `make tests-ui`, then `make lint`.
Expected: all PASS. `make lint` was clean before this work and must stay clean.

- [ ] **Step 7: Update `CLAUDE.md`**

In the `tik.trigger` status paragraph, replace the sentence describing lockstep with the new model:

```
**Draw** renders the session into the scene and is always manual -- nothing
draws on create, import, open or checkout, and a drawn module whose settings
change is flagged, never rebuilt. **Sync** reads the scene's poses and guide
attrs back into the session, automatically (`Auto`) or on demand. Neither can
do the other's job.
```

Update the design-spec list to name `2026-09-05-draw-and-sync-separation-design.md` as authoritative for guides, and change the `tests/integration/trigger/test_lockstep_trigger.py` entry to `test_draw_sync_trigger.py`.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/ui/main.py CLAUDE.md tests/ui
git commit -m "Add the Draw menu actions and rename Clear Scene Guides

It deletes every module from the session, not just the rendering, and
the old label reads as 'undraw everything' under the new vocabulary."
```

---

## Self-Review

**Spec coverage**

| Spec section | Task |
|---|---|
| 2 Draw is never automatic | 5, 6, 14 |
| 2.1 drawn-ness is not stored | 1 |
| 3 the state model | 1 |
| 3.1 a rename must show as stale | 2, 3 |
| 4 where the code splits | 5 |
| 4.1 `draw()` takes a decision | 5, 13 |
| 5 the dirty-scene prompt | 13 |
| 5.1 `Feedback` custom labels | 9 |
| 6 Sync | 5, 13 |
| 7 Build | 5 (`test_build`) |
| 7.1 pipeline build syncs first | 8 |
| 7.2 orphans are not built | 7 |
| 8 the action bar | 10 |
| 9.1 the guide tree | 11 |
| 9.2 the graph | 12 |
| 9.3 the status bar | 13 |
| 10 menus | 14 |
| 11 refresh | 13 |
| 12 deletions | 5, 6, 10, 13, 14 |
| 13 tests | every task |

**Naming consistency:** `draw(scope, poses)`, `sync(scope)`, `is_stale`, `not_drawn`, `stale`, `key_stale`, `set_pending`, `set_selection_enabled`, `_show_state`, `DrawStateRole`, `NOT_DRAWN` / `DRAWN` / `STALE` are used identically in every task that mentions them.

**Known ordering constraint:** Tasks 1-9 are backend and can land in order without the UI compiling against them; Tasks 10-14 depend on 1, 5 and 9. Task 12 imports the three state constants from Task 11's new module, so 11 must land before 12.
