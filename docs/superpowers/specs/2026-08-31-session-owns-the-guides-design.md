# The Session Owns the Guides — Design Spec

Date: 2026-08-31
Status: brainstormed with Arda Kutlu; awaiting spec review.

Revises `2026-08-31-guide-ownership-and-lockstep-design.md` §3.2, §3.3 and §6.3:
the guide document moves out of the Maya scene and into the session. Everything
else in that spec — reconcile, capture, regenerate, lockstep, the id keying —
stands unchanged.

## 1. Goal

Scene operations destroy the Designer's contents. Deleting `trigger_modules_grp`
takes the modules with it; File > New Scene empties the Designer. Both feel
arbitrary, because the rule behind them is invisible: the guide *document* lives
in the scene, so anything that clears the scene clears the rig description.

This spec moves the document into the session and leaves the scene holding only
a rendering.

### 1.1 What is actually wrong

The data is not being lost. A session keeps its guides in memory across a New
Scene — verified: `session.document.guides` still lists every module after
`file(new=True)`. The Designer simply reads the wrong source. It asks the scene
for the document, and the scene has just been emptied.

So this is not a rescue. It is a change of **which source the Designer trusts**,
and the smaller half of the work is deleting the source it should stop trusting.

### 1.2 Why the original decision went the other way

`2026-08-31-guide-ownership-and-lockstep-design.md` §2 put the working copy in
the scene for one reason: Maya's undo would then cover structural edits for
free. That was a real benefit and it was bought at a price nobody could see —
that scene operations quietly own the rig description.

The price is not worth it, and the benefit turns out to be replaceable: the
session already carries a 50-level undo stack that restores the whole `Document`
(`session.py:207`), and the guides live in that `Document`.

## 2. Decisions (from brainstorming, 2026-08-31)

- **The session document is the only store.** Nothing in the Maya scene is read
  as authority.
- **The scene holds guides and nothing else.** `trigger_modules_grp` and
  `guides/module_node.py` are deleted.
- **Undo splits along a line that can be said in one sentence:** the tool undoes
  tool edits (add, connect, delete, settings — Trigger's Ctrl+Z, via the session
  stack); Maya undoes scene edits (moving a guide, with focus in the viewport).
- **New Scene redraws.** Lockstep already says the scene and document are never
  knowingly apart; a cleared scene is structural staleness like any other. The
  one exception stays: guides a build dismissed on purpose.
- **Module settings lose their channel-box surface.** `settings_plug` and the
  settings half of the properties binding go. Per-guide data (`guide_attrs` —
  twist's `position` and `twistWeight`) is untouched: it lives on the joints,
  which is where a per-guide fact belongs.
- **`useRefOri` is removed outright.** Nothing creates it since the structure
  moved off the guides, so the "Inherit orientation" checkbox already binds to a
  plug that does not exist. No module or build code reads it; its only test
  asserts the fake adapter's store rather than any rig behaviour.

## 3. The object model

`Document.guides` stops being a `dict` and becomes a live `GuideDocument`,
serialized in `to_dict` / `from_dict` exactly as now. `session.document.guides`
*is* the document — no copy, no second representation, and `is_modified` and the
undo stack keep working unchanged because they compare and restore
`Document.to_dict()`.

`GuideScene` binds to a session instead of reading the scene:

```python
class GuideScene:
    def __init__(self, events=None, session=None):
        self.events = events or EventBus()
        self._session = session
        self._own = None if session else GuideDocument()  # standalone scripting

    @property
    def document(self) -> GuideDocument:
        return self._session.document.guides if self._session else self._own

    def _touch(self) -> None:
        if self._session is not None:
            self._session.touch()
```

`Session._touch` becomes public as `Session.touch()` — it is the undo push, and
reaching across modules for a private method to record an edit is exactly the
kind of coupling that rots.

It holds the **session**, not the document object: session undo replaces
`Document` wholesale, so a cached `GuideDocument` would leave the Designer
pointing at a discarded one.

`Session.guides` returns a `GuideScene` bound to that session, built once and
reused. `SessionView` hands it to its Designer, so each tab's Designer edits its
own session's guides by construction rather than by bookkeeping.

A bare `GuideScene()` still works for scripting, owning a free-standing document
no session sees.

## 4. What is left in the scene

Guide joints, the guide holder, and two labels on the holder:

- `trg_session` — which session's guides are currently drawn.
- `trg_dismissed` — a build cleared them on purpose (§5 of the previous spec).

`snapshot`, `capture`, `regenerate` and `reconcile` keep their shape. Capture
writes into the session's document rather than the scene's.

### 4.1 Capture becomes structurally safe

Capture only ever updates the poses and guide attrs of modules the document
already holds. It cannot add or remove a module.

This matters more than it sounds. Two bugs during the previous implementation
were the same bug — capture reading a *document* out of the scene and writing
emptiness over the session's:

- adding capture-before-build wiped a session's guides when the scene was empty;
- reopening a saved `.tr` in a fresh scene and building destroyed its guides.

Both were guarded against. Under this design they cannot be expressed, so the
guard (`capture declines an unstamped, guide-less scene`) is deleted rather than
kept.

### 4.2 The Builder is handed the document

`Builder.build` currently calls `guide_nodes.find_instances(scope)`, which reads
the document out of the scene. With no document in the scene, the caller has to
supply it:

```python
Builder(events).build(scope=..., document=..., rig_name=..., afterlife=...)
```

`GuideScene.test_build` passes `self.document`; the kinematics action passes
`ctx.session.document.guides`. `find_instances(scope, document)` takes it as an
argument rather than fetching it, which also makes it testable without a
session.

This is the one interface outside the guide layer that this design changes.

## 5. The edit path

One route for every guide edit:

1. mutate `session.document.guides`
2. `session.touch()` — the undo push
3. regenerate the affected module

No commit step, no cache to invalidate, no second store to keep in step.
`GuideScene.commit()`, `reload()` and `invalidate()` are deleted; `document` is
the session's and is always current.

### 5.1 Undo

Trigger's Ctrl+Z (the Edit menu action, already dispatching per active view)
calls `session.undo()` on the Designer tab, which restores the whole `Document`
— guides included. The change from today is one line: it currently calls Maya's
undo there.

Moving a guide is a joint move and stays on Maya's stack, undone with focus in
the viewport. Poses reach the document through capture, so an undone move is
picked up by the next sync like any other scene edit.

### 5.2 Checkout and the hand-off

`checkout_guides` clears the guide joints and draws this session's;
`capture_guides` reads poses back. The stamp now labels a rendering rather than
guarding a store, but `hand_over` keeps its shape and its rule: force only after
the outgoing session's work has actually been captured.

## 6. Scene events

New Scene, Open Scene, and undoing a delete are all "the rendering changed".
Lockstep redraws, exactly as it does for a deleted joint — no prompt and no
special case.

One consequence to accept deliberately: opening another Maya file with a session
open draws that session's guides into it. That is usually what is wanted (fitting
guides to a model); when it is not, the build-dismissal path or closing the
session tab covers it.

## 7. Code map

Deleted:

- `guides/module_node.py`
- `document_store.read_document` / `write_document` / `read_entry` /
  `write_entry` / `remove_entry` — the module leaves only `read_stamp`,
  `write_stamp`, `read_dismissed`, `write_dismissed`
- `GuideScene.commit` / `reload` / `invalidate` / `settings_plug`
- `Session.capture_guides`'s empty-scene guard
- `useRefOri`: the checkbox, `_on_inherit_toggled`, its binding, its test

Changed:

- `core/document.py` — `guides` becomes a `GuideDocument`
- `session.py` — `guides` property; `capture_guides` / `checkout_guides` against
  the session's document
- `guides/scene.py` — bound to a session; writes end in `_touch()` + regenerate
- `guides/nodes.py` — `find_instances(scope, document)` takes the document as an
  argument rather than reading it from the scene
- `maya/build.py` — `Builder.build(..., document=...)`; `actions/kinematics`
  passes `ctx.session.document.guides`
- `ui/designer/properties.py`, `window.py` — settings binding and `useRefOri` out
- `ui/session_view.py` — the Designer gets `session.guides`
- `ui/main.py` — Ctrl+Z on the Designer tab goes to `session.undo()`

## 8. Testing

The existing lockstep and session-guides suites are written against
`GuideScene`'s API rather than its storage, so they carry over nearly unchanged
— which is itself the check that the API boundary was drawn in the right place.

New tests, both of them failures actually hit in use:

- New Scene leaves every module in the Designer and redraws its guides.
- A structural edit undoes with `session.undo()`, and the guides follow.

Plus one that pins the class of bug this design removes: capture against an
empty scene leaves the document's modules alone.

## 9. Build order

1. `Document.guides` becomes a `GuideDocument`; session undo covers it.
2. `GuideScene` binds to a session; writes `_touch()`; `commit`/`reload`/
   `invalidate` go.
3. `module_node.py` and the document half of `document_store.py` deleted.
4. `useRefOri` and the settings binding removed.
5. Ctrl+Z on the Designer tab routed to `session.undo()`.
6. New Scene redraw test; scene-event path confirmed against lockstep.

## 10. Non-goals

- Guide overrides across references. Still deferred, still not foreclosed.
- Restoring a channel-box surface for module settings.
- Any change to reconcile, regenerate, the id keying, or the `.trg` exchange
  format.
