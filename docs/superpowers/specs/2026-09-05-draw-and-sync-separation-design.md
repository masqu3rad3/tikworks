# Draw and Sync: Separating the Two Directions

**Date:** 2026-09-05
**Status:** approved, not yet implemented
**Amends:** `2026-09-01-optional-sync-and-snapshot-design.md` (sections 2 and 3) and
`2026-08-31-guide-ownership-and-lockstep-design.md` (sections 5 and 6). Where this document
and those disagree, this one wins; everything it does not mention is unchanged.

---

## 1. Why

Two different operations are both called "sync", and the tool offers one button and one
checkbox that govern a confusing mixture of the two.

**Direction one — the session into the scene.** The `GuideDocument` owns which modules exist,
their settings and their guide layout. Guide joints are a *rendering* of that, and the
document can rebuild it at any time. Today this happens by itself: `GuideScene._apply()`
regenerates the touched module on every structural write, and `sync()` regenerates whatever
`reconcile` calls structurally stale.

**Direction two — the scene into the session.** Poses and guide attrs are authored by
dragging joints in Maya. Nothing in Maya fires when a guide is dragged, so the document only
learns a pose when something goes and reads it. Today `capture()` runs unconditionally at the
head of both `_apply()` and `sync()`.

The `Sync` button, the `Auto` checkbox and the drift pill nominally govern "whether a scene
event may start a sync" — but `sync()` does both directions, so pressing that one button
moves data both ways, and the rigger has no vocabulary to say which one they wanted.

**The fix is to name them apart and give each its own control.**

| | Direction | Name | Trigger |
|---|---|---|---|
| 1 | document → scene | **Draw** | manual, always |
| 2 | scene → document | **Sync** | `Auto`, or on demand |

There are no backward dependencies. Everything this design makes redundant is deleted, not
deprecated.

## 2. Nothing is *re*drawn unless the rigger asks

**A rendering that already exists is never rebuilt behind the rigger's back, and no session
ever draws itself when it opens.**

- **creating** a module draws it, when `Draw new modules` is on — the default
- importing a `.trg` adds entries and creates **no joints**
- opening a `.tr` session creates no joints
- checking the scene out for a session creates no joints
- changing a drawn module's settings **does not** redraw it — it is *flagged*, and the joints
  stay exactly where the rigger dragged them until Draw is pressed

The last one is the point of the whole design. A redraw that happens on its own is the tool
moving the rigger's work without being asked, and there is no setting that makes that
acceptable — only an explicit press. **`Draw new modules` cannot switch it back on**: the
setting governs creation and nothing else.

### 2.1 Why creation is the exception

Creation is the one moment where the two dangers this design exists to remove are both
absent. The rigger has just said "I want an arm", so the draw is not unsolicited; and there
are no joints for that module yet, so nothing can be moved or discarded. Every other
automatic draw fails one of those tests — a settings change redraws work the rigger did not
ask to have rebuilt, and opening a session floods a scene the rigger may have opened for
something else entirely.

Creation is also where the *poses* come from. `expand_guides` writes **unposed** records; the
module's own `draw_guides` is what decides where its guides sit, and the document only learns
those positions by drawing once and capturing. With `Draw new modules` off, a new module's
records stay unposed until its first Draw — which is still correct, because `regenerate`
leaves an unposed guide wherever `draw_guides` puts it, and Sync captures it from there.

### 2.2 Where the setting lives

`GuideScene.draw_on_create: bool`, defaulting to `True`, mirroring `auto_sync` exactly: a
working preference, persisted per user in `QSettings` (`designer/draw_on_create` under
`tikworks/trigger`), never in the `.tr`. It is surfaced as a checkable `Draw New Modules`
menu action beside `Auto Sync`, and deliberately **not** on the action bar — the bar is the
scarce surface and this is a set-once preference, not a per-operation control.

`GuideScene` reads the attribute, never `QSettings`; the Designer restores it at construction
and writes it back on change, the way it already does for `auto_sync`.

### 2.3 `add()` and `create_guides()`

`GuideScene.create_guides(module)` keeps its name and its behaviour — write the entry, draw
it, capture the first render — because that is honestly what it does, and it is the low-level
call that scripts and tests use to get drawn guides.

`add()` is the authoring entry point (the palette, the shelf, `.trg` import). It writes the
entry through a new `_write_entry()` and then draws **only when `draw_on_create` is set**.
That split is what lets opening a session add entries without touching the scene.

There is no **Undraw**. Drawing again discards the previous rendering, and `Delete All
Modules` or `Reset Scene` covers the rest.

### 2.4 "Is it drawn?" is not stored

The scene answers it. `reconcile()` already computes `absent` per module, so drawn-ness is
derived on every diff and never persisted. Deleting guide joints by hand therefore becomes a
legitimate way to undraw, rather than damage the tool tries to repair.

## 3. The state model

`reconcile` computes everything already; only the reading changes.

| `ModuleDiff` field | State | Resolved by | Winner |
|---|---|---|---|
| `absent` | **not drawn** | Draw | the document |
| `missing` / `unexpected` / `parent_wrong` / `key_stale` | **out of date** | Draw | the document |
| `drifted` | **moved** | Sync | the scene |
| orphans, duplicates | reported | nothing | nothing |

`absent` is no longer staleness and no longer damage: it is the normal state of a new module.

`GuideDiff.structural` is replaced by two properties, `not_drawn` and `stale`.
`ModuleDiff.needs_regenerate` becomes `is_stale` and no longer counts `absent`.

### 3.1 A rename must show up as stale

`reconcile` matches guides on the `trg_instance` uuid tag, never on names. Today a rename
renames the joints only because `_apply()` regenerates immediately. Once it does not, renaming
`L_arm` to `L_frontLeg` leaves joints called `L_arm_*` in the scene and **nothing flags it**.

Fix: `regenerate` stamps the display key it drew under as a guide tag (`tags.KEY`),
`RenderedGuide` carries it, and `reconcile` reports a mismatch against `entry.key` as
`key_stale` — which reads as out of date like any other structural staleness. This keeps
`reconcile` pure: it compares two recorded strings and never constructs a name.

## 4. Where the code splits

`GuideScene` gets one method per direction, and **nothing does both**.

| | today | after |
|---|---|---|
| `_apply(entry)` | `capture(all)` → `touch` → `regenerate(entry)` | `touch` **only** |
| `sync(scope=None)` | `capture(all)` → `diff` → `regenerate(stale)` | `capture(scope)` → `touch` if it changed → return diff. **Never regenerates.** |
| `draw(scope, poses=)` | — | optional `capture(scope)` → `regenerate(scope)`. **Never captures unless told to.** |

`sync()`'s `regenerate_stale` parameter is deleted along with the branch it guarded. The two
call sites that pass `regenerate_stale=False` (`session.py`, `GuideScene.test_build`) become
plain `sync()`.

`_apply` dropping its capture is safe *because* it also drops its regenerate. The capture was
there to stop a redraw from rebuilding on stale records and throwing the rigger's posing away.
With no redraw, there is nothing to protect against, and capture becomes what it should be: a
deliberate act.

### 4.1 `draw()` takes a decision, it does not ask for one

```python
def draw(self, scope=None, poses: str = "keep") -> GuideDiff
```

`poses="keep"` captures the scoped drift before regenerating; `poses="discard"` skips it.
The default is the safe one.

`GuideScene` must not open a dialog — `tik/trigger/guides` may use Maya but not Qt. The
Designer command asks the question and passes the answer down, which also keeps `draw()`
scriptable and headless-testable.

## 5. The dirty-scene prompt

Pressing Draw on a module whose guides have been posed since the last Sync must not discard
that posing silently. The condition is one line:

> **Ask if and only if the scoped diff reports any `drifted` guide.**

Both exemptions fall out of that for free, with no special cases:

- a module that is **not drawn** has no rendered guides, so it cannot be drifted — no prompt
  on the first draw
- a module whose changes are **already captured** has no drift — no prompt when clean

```
Redraw L_arm?
The guides in the scene have been moved since the last sync.

[ Sync and redraw ]   [ Discard and redraw ]   [ Cancel ]
```

`Sync and redraw` calls `draw(scope, poses="keep")`; `Discard and redraw` calls
`draw(scope, poses="discard")`.

### 5.1 `Feedback` needs custom button labels

`feedback.BUTTONS` has no key whose `QMessageBox` text reads "Sync and redraw".
`pop_question` gains support for `("key", "Label")` tuples in its `buttons` list, calling
`setText` on the standard button it maps to. Plain string keys behave exactly as now, so
every existing call site is untouched and `tests/unit/test_dialog_boundaries.py` still passes.

## 6. Sync

`Sync`, `Auto`, the `F6` shortcut, the menu action and the `designer/auto_sync` `QSettings`
key all keep their names. Only their reach narrows: they now govern **one** direction.

`Auto` still governs exactly one thing — whether a `SceneWatcher` event may start a sync — but
because `sync()` can no longer regenerate, **Auto can only ever capture**. It cannot move a
joint under any circumstances. The original complaint that made sync optional ("the tool moves
things on its own") is answered by construction rather than by a checkbox.

With `Auto` off, a scene event calls `diff()` only, exactly as before.

## 7. Build

`find_instances` is driven entirely by tagged joints in the scene. Under "nothing draws unless
asked", a freshly opened session's `Build all` would therefore build **nothing at all**,
silently; and an out-of-date module would build the document's settings against stale joints.

> **Build all = Sync → Draw everything not drawn or out of date → build.**

It never prompts: the sync in step one makes the discard question moot.

### 7.1 A pipeline build syncs before it resets the scene

A `Build` / `Build & Publish` run resets the scene, and the `kinematics` action then calls
`clear_rendering()` + `regenerate_all()` to put the guides back. Today that is harmless
because `_apply`'s unconditional capture kept the document current. With that net removed, a
rigger who poses guides with `Auto` off and presses Build loses the posing at the scene reset,
silently.

The runner therefore captures before the reset. This is the one place this design *adds* code.

### 7.2 Orphan guides must not be built

`instance_from_nodes` does not skip a joint set with no document entry — it builds it as a
phantom module named after its module type, with default settings and no connections:

```python
name=entry.name if entry is not None else module_type,
settings=dict(entry.settings) if entry is not None else {},
```

This hazard predates this design, but this design makes it load-bearing: "not drawn" stops
being an anomaly, so orphan detection becomes the only thing separating "guides this session
owns" from "joints that happen to be tagged".

`find_instances` skips instances with no entry **when a document was actually passed**
(guarded on `document is not None`, so the default empty-document call is unaffected). Orphans
are reported by `reconcile` and never built, which is what the reconcile contract already
says about them.

## 8. The action bar

```
→ SCENE  [Draw selected][Draw all] │ [Select][Mirror]  ····  → SESSION  [Sync][×]Auto │ [▶ Build all]
```

The captions name **where each group's data lands**, so "which button writes to my scene?" is
answerable from the bar alone, without reading a spec. The 1px `#BarRule` between the groups
is what says the two ends are opposites.

### 8.1 What comes off the bar

- **the selection label** (`SELECTION  L_arm`) — the tree and graph already show the
  selection; only the greying survives
- **both count pills** — the button's colour says there is work pending in that direction; the
  tree and graph say *which* modules; the status bar carries the numbers. Nothing on the bar
  repeats what a panel already shows.
- **`Build selected`** — it keeps its menu entry and its `test_build(*handles)` API, but
  test-building one module in isolation is rarer than drawing one, and the bar is the scarce
  surface

### 8.2 Colour

| State | Control | Property |
|---|---|---|
| out of date, in the selection | `Draw selected` | `alert` |
| out of date, anywhere | `Draw all` | `alert` |
| something moved | `Sync` | `alert` |
| `Auto` on | `Sync` | `quiet` |

> **Orange means out of date. It never means not-drawn.**

Otherwise a freshly opened session lights its whole left end up, which is precisely the
resting state. Out of date means the scene *contradicts* the session; not drawn means the
scene is merely silent, and silence does not earn colour.

### 8.3 API

`DesignerActionBar` gains `draw_selected_requested` and `draw_all_requested`, and loses
`build_selected_requested`.

- `set_selection(keys)` → `set_selection_enabled(bool)`
- `set_drift(count)` → `set_pending(stale_selected, stale_any, moved)` — three booleans
- `set_auto_sync(on)` unchanged

## 9. The two panels say the same thing

One diff object, two painters, so the panes can never disagree.

### 9.1 The guide tree

`GuideTree` is a plain `QTreeWidget` today. A new `GuideStateDelegate` on column 0 follows
`PipelineDelegate`'s existing gutter-dot idiom: reserve 14px and paint a 7px dot immediately
left of the module icon, so it indents with the row.

| State | Dot | Row |
|---|---|---|
| not drawn | hollow ring `#5a5a5a` | text dimmed to `#757575` |
| drawn and true | filled `#3f3f3f` | normal |
| out of date | filled `#FE7E00` | normal |

State arrives on a `DrawStateRole`, the way `ui/model.py` already does `StatusRole`. The
tooltip says it in words. No text column: four columns is already enough, and the count lives
in the status bar.

### 9.2 The graph

`NodeSpec` gains `draw_state`. In `NodeItem.paint`, a 3px stripe down the node's left edge,
clipped to the body's rounded rect:

- **out of date** — `#FE7E00`
- **not drawn** — dashed `#5a5a5a`, plus `setOpacity(0.45)` on the item
- **drawn and true** — no stripe

The left edge is the only free surface on the node: the border is already selection, the dash
is already `external`, and the 22px header is full of title, subtitle and collapse glyph.

### 9.3 The status bar

The Designer's `StatusFields` gains a `guides` field:

- at rest → `up to date`
- otherwise → `3 out of date · 2 not drawn · 1 moved`, zero terms dropped

## 10. Menus

Guides menu:

- **add** `Draw Selected Guides`, `Draw All Guides` (`F5`, beside Sync's `F6`)
- **add** `Draw New Modules`, checkable, default on (section 2.2)
- `Sync From Scene` (`F6`) and `Auto Sync` keep their names and checkable state
- `Build Selected Guides` keeps its entry
- **rename** `Clear Scene Guides` → `Delete All Modules`

The rename fixes a live naming bug: that action calls `guides.clear()`, which deletes every
module from the *session document*, not just the rendering. Under this design's vocabulary a
rigger would read the old label as "undraw everything" and lose their session.

## 11. Refresh

`refresh()` computes `self.guides.diff()` **once** and feeds four consumers: the tree
delegate, the graph, the bar and the status field. `_show_drift` becomes `_show_state(diff)`.

`_on_scene_event`:

- `Auto` **on** → `sync()`, then repaint from the diff it returns
- `Auto` **off** → `diff()` only

Both are now a single `snapshot()` scan, and **neither can touch the scene**. That property is
what makes the whole redesign safe.

`refresh()` now scans the scene every time, where before it only did on sync. It is the same
walk `sync()` already did on every scene event, so the ceiling is unchanged — but it should be
measured on a heavy scene before this is called done rather than assumed.

## 12. Deletions

Nothing is deprecated. Everything below is removed.

### 12.1 Dead once nothing auto-redraws

| File | Goes |
|---|---|
| `core/guide_document.py` | `GuideDocument.dismissed` — runtime-only and never serialized, so **no schema bump** |
| `guides/scene.py` | the `dismissed` property and setter, and `restore()` |
| `guides/scene.py` | the `dismissed` guard inside `sync()` |
| `guides/scene.py` | `self.dismissed = False` in `create_guides` |
| `maya/tags.py` | `DISMISSED` — defined and read nowhere; already dead |
| `maya/build.py` | `apply_afterlife`'s `document` parameter and the flag it set |
| `ui/main.py` | the restore-on-Designer-tab block in `_on_sub_tab_changed` |

### 12.2 Dead once the directions separate

| File | Goes |
|---|---|
| `guides/scene.py` | `sync(regenerate_stale=)` and its regenerate branch |
| `core/reconcile.py` | `ModuleDiff.needs_regenerate`, `GuideDiff.structural` |
| `ui/designer/action_bar.py` | `build_selected_requested`, `selection_label`, `drift_pill`, `up_to_date_label`, `build_selected_button`, `set_selection`, `set_drift`, `_update_up_to_date` |
| `ui/designer/window.py` | `_show_drift` |

### 12.3 Changed, not deleted

- `_apply()` → `touch` only
- `session.py: checkout_guides` drops its `regenerate_all`; the `clear_rendering()` stays, so
  taking the scene over still clears the previous session's drawing
- `find_instances` gains the orphan guard
- `commands.test_build` gains the sync-then-draw preamble

## 13. Tests

**Pure — `tests/unit/test_reconcile_trigger.py`**

- `absent` lands in `not_drawn`, never in `stale`
- `missing` / `unexpected` / `parent_wrong` land in `stale`
- a renamed entry with correctly-tagged joints reports `stale` through `key_stale` — the
  regression the auto-redraw used to hide
- `drifted` appears in neither

**Maya — `tests/unit/test_guide_scene_trigger.py`**

- adding a module writes the entry and creates no joints
- changing a setting on a drawn module leaves every joint untouched and reports `stale`
- `draw(poses="keep")` preserves a dragged pose across a segment-count change
- `draw(poses="discard")` rebuilds at the document's stored poses
- `sync()` captures and never creates or deletes a joint — assert the node set is identical
  before and after
- deleting a module still takes its joints

**Renamed** — `tests/integration/trigger/test_lockstep_trigger.py` becomes
`test_draw_sync_trigger.py`. Lockstep is gone as a concept; its `dismissed` / `restore` tests
go with it.

**Regressions**

- `test_session_checkout_trigger.py`, `test_session_guides_trigger.py` — checkout clears and
  stamps, and draws nothing
- `test_builder_trigger.py` — an orphan joint set with no document entry is not built
- new — a build syncs before the scene reset, so posing survives with `Auto` off

**UI** (`TIK_TESTS_NO_MAYA=1`, `QT_QPA_PLATFORM=offscreen`)

- the bar emits the two new signals
- `set_pending` colours only what it should, and never lights on not-drawn
- the delegate paints three distinct states
- the graph and the tree consume the same diff object
- `tests/ui/stub.py` gains `draw()`
