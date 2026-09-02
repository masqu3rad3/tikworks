# Optional Sync, the Scope-Split Action Bar, and Snapshot From Scene

**Date:** 2026-09-01
**Status:** approved, not yet implemented
**Amends:** `2026-08-31-guide-ownership-and-lockstep-design.md` (sections 5 and 6) and
`2026-08-31-session-owns-the-guides-design.md`. Where this document and those disagree,
this one wins; everything it does not mention is unchanged.

---

## 1. Why

Three problems, one bar.

**The buttons are in the wrong place.** `Select guides`, `Mirror`, `Build selected` and
`Build all` live at the bottom of the properties panel, a 270px column on the right. Two of
them have nothing to do with the selected module's properties, and all four are cramped into
a quarter of the window's width.

**Sync is invisible and compulsory.** `GuideScene.sync()` runs off a debounced scene watcher
whenever Maya reports a structural change. Riggers who have not read the lockstep spec
experience this as the tool moving things on its own. It should be possible to turn it off
and pull instead of being pushed.

**A session can be lost.** The `.tr` is the only home for the module list. Close without
saving, or receive a Maya file from someone else, and the guides in the scene are unusable —
the joints are right there, tagged, and the tool has nothing to say about them.

## 2. The action bar

A full-width bar at the bottom of the Guide Designer page, above the window's status bar and
below the four-pane splitter. It reuses `#BuildBar` — the same frame, background (`#1e1e1e`),
top rule (`1px #353535`), margins (`10, 7, 10, 7`) and spacing (`8`) as the Session sub-tab's
build bar, so the two sub-tabs are siblings.

The four buttons move out of the properties panel entirely; the panel keeps only the header,
`INPUTS`, `MODULE` and the scene-nodes panel, and its form scroll area takes the freed space.

### 2.1 Three groups

The bar's controls do not share a scope, and that is what the design makes visible. Each group
carries a `#FieldCaption`-styled label (`#7b7b7b`, 10px, 1px letter-spacing):

| Group | Label | Controls | Acts on |
|---|---|---|---|
| Selection | `SELECTION` + the selected key | `Select guides` · `Mirror` · `Build selected` | the selected module(s) |
| Scene | `SCENE` | `Sync` · `Auto` checkbox | the Maya scene |
| Session | `SESSION` | `Build all` (`#PrimaryButton`) | every module |

Selection and Scene are separated by the stretch; Scene and Session by a 1px `#353535`
vertical rule. `Build all` therefore sits alone past a divider, where it cannot be misread as
"build what I picked".

### 2.2 The selection label is the answer to "what will Mirror mirror?"

It shows the selected module's display key (`L_arm`), `2 modules` when several are selected,
and a dimmed `none` when nothing is. When it reads `none` the three selection buttons are
disabled — the label explains the disabling, which today happens with no visible reason.

### 2.3 States

| State | Sync button | Checkbox | Trailing indicator |
|---|---|---|---|
| Auto on | quiet (`#8f8f8f` text) | checked | — |
| Auto off, scene matches | normal | unchecked | `up to date` (`#7b7b7b`, 11px) |
| Auto off, scene has moved on | `#FE7E00` border, `#e0c8a8` text | unchecked | drift pill |

The drift pill reuses the existing `#FilterPill` tokens (`#3a2e1f` on a `#FE7E00` border,
9px radius, `#e0c8a8` label) with a 6px accent dot: `3 modules changed`. It is not a new
visual language — it is the one the filter bar already uses for "there is something active
here".

## 3. Sync becomes explicit

### 3.1 What `Auto` governs — and what it must never govern

`Auto` governs **exactly one thing**: whether a scene event from the `SceneWatcher` triggers
`GuideScene.sync()`.

It does **not** govern capture-before-regenerate. `GuideScene._apply()` captures, touches,
then regenerates on every structural write, and that sequence stays unconditional at every
auto setting. This is not a detail to be tidied up later: it is the fix for the bug where
changing any module property threw the rigger's posing away, because nothing in Maya fires
when a guide is dragged and the document only learns a pose when something goes and reads it.
An `if self.auto_sync:` in front of that capture would put the bug straight back.

Stated as an invariant, to be quoted in the code:

> **A write always captures first. `Auto` only decides whether the *scene* may start a sync.**

### 3.2 Where the setting lives

`GuideScene.auto_sync: bool`, defaulting to `True` — today's behaviour is the default, and
nobody who does not touch the checkbox sees a change.

It is a working preference, not rig data: it persists per user in `QSettings`
(`designer/auto_sync` under `tikworks/trigger`), never in the `.tr`. A session handed to a
colleague does not carry your sync habits, and switching session tabs does not reset the
checkbox.

This is the tool's first persisted preference — even `recent_files` is in-memory today — so the
mechanism stays two lines at the point of use. No preferences framework, no settings file
format, until there is a second preference to justify one.

### 3.3 Auto off

The watcher stays installed. On a scene event with `Auto` off the designer calls
`GuideScene.diff()` — read-only, no capture, no regenerate — and feeds the result to the
drift indicator. The document is untouched until `Sync` is pressed, at which point the normal
`sync()` runs.

`diff()` is what `sync()` already calls internally, so an auto-off event costs strictly less
than an auto-on one.

### 3.4 The drift count

The pill counts `len(diff.structural) + len(diff.drifted)` distinct instances — structural
staleness *and* pose drift. Pose drift is deliberately included here and deliberately excluded
from `diff_summary()`: that helper describes a redraw that is about to happen, while the pill
describes work the rigger has done that the document has not been told about yet.

## 4. The scene breadcrumb

For Snapshot to recover a session, the joints have to carry more than they do today. Guide
joints are tagged with `trg_kind`, `trg_module`, `trg_instance`, `trg_role`, `trg_index` and
`trg_side` (`guides/nodes.py`); names, settings and connections live only in the document.

`regenerate()` will additionally write the module's `ModuleEntry` onto its **root guide** as
`trg_entry` — a tag `maya/tags.py` already reserves.

### 4.1 The rule that keeps this from undoing the ownership model

Writing document data into the scene is exactly what the session-owns-the-guides work removed,
so the breadcrumb is fenced by a rule that must be quoted wherever it is written or read:

> **`trg_entry` is WRITTEN by `regenerate` and READ only by Snapshot.**
> Capture, reconcile, build, the Designer and the Builder never consult it. It is a recovery
> breadcrumb, not a store, and the document remains the sole authority.

Nothing in the normal flow can therefore be corrupted by a stale or hand-edited tag: the only
code that reads it runs when there is no document to be authoritative in the first place.

### 4.2 The breadcrumb carries no poses

`trg_entry` stores `entry.to_dict()` **with the `guides` list removed**.

This is the load-bearing half of the design. A pose changes when a rigger drags a joint —
without any document write, and therefore without any regenerate to refresh the tag. A tag
holding poses would go stale within seconds and a snapshot would restore positions the rigger
had already moved away from. Everything the tag *does* carry (name, side, settings, inputs)
can only change through a document write, and every document write ends in a regenerate. So:

> **The breadcrumb carries only what a document write can change. Poses come from the joints.**

The joints are the live record of where things are; the tag is the live record of what they
mean. Neither can go stale relative to the other.

### 4.3 Cost

One extra `setAttr` of a small JSON string per module per regenerate. Regenerate already
deletes and recreates every joint in the module, so this is not measurable.

## 5. Snapshot Guides From Scene

An explicit, user-invoked recovery command: read the guide joints in the scene and rebuild the
session's modules from them.

### 5.1 Behaviour

1. Scan the scene with `snapshot()` and read `trg_entry` from each instance's root guide.
2. Build a `GuideDocument`: entries from the breadcrumbs, poses and guide attrs from the
   joints, connections from the breadcrumbs' `inputs`.
3. Present the report dialog (5.3). Nothing has touched the session yet.
4. On confirm, replace `Document.guides` wholesale and push one undo step, so a snapshot is
   `Ctrl+Z`-able like any other structural edit.
5. Refresh the Designer. No regenerate: the joints in the scene are already the rendering, and
   redrawing them would be a teleport for no reason.

### 5.2 Scope for this pass: replace only

The dialog offers **Replace** and nothing else. Both cases the feature exists for — an unsaved
session, and a Maya file from someone else — are replace cases. Merging a scene into a session
that already has modules ("adopt only what I do not know") is a genuinely harder reconcile and
is deliberately deferred until the replace flow has been used in anger.

### 5.3 The report dialog

Snapshot is destructive to the current module list, so it reports before it acts. It shows
what was found (`7 modules · 34 guide joints`), then a recovered list. With the breadcrumb in
place, a scene drawn by this build of Trigger recovers everything — module type, side, names,
settings, connections, poses, guide attrs and hierarchy — and the dialog says so.

A scene drawn by an **older** build has no `trg_entry`. The dialog must degrade honestly
rather than pretend: for those instances it reports the same "not stored in the scene" list
that the design canvas shows — names falling back to the module type, settings reset to
defaults, connections lost — counted per instance, so a mixed scene reports a mixed result.
This is not a transitional nicety to be dropped; a scene is a file and old files arrive
forever.

### 5.4 Where it lives

`Guides ▸ Snapshot Guides From Scene…`, with the ellipsis, grouped with the other three verbs
that cross the session/scene boundary, immediately above `Clear Scene Guides`. Not in the
action bar: it is a recovery command, not part of the working loop.

## 6. Menu changes

The Guides menu grows a scene-boundary group between `Build All Guides` and
`Clear Scene Guides`:

```
Sync From Scene                 F6
Auto Sync                       (checkable, mirrors the bar's checkbox)
Snapshot Guides From Scene…
────────
Clear Scene Guides
```

`Auto Sync` and the bar's checkbox are one setting with two front doors; each updates the
other without re-entering.

### 6.1 The F5 clash

`Guides ▸ Layout ▸ Refresh` is bound to `F5` and rebuilds the UI from the document.
`Sync From Scene` runs the other way — scene into the document. Two adjacent commands that
both read as "update" is precisely the ambiguity this work exists to remove, so:

- `Refresh` is renamed **`Redraw Views`** and keeps `F5`.
- `Sync From Scene` takes `F6`.

## 7. What this does not change

- Lockstep's guarantees (capture resolves drift, regenerate resolves structure, never confused).
- The `.tr` schema. `auto_sync` is a user preference; `trg_entry` lives in the Maya scene.
  No version bump.
- `.trg` import/export.
- The Session sub-tab and its build bar.
- `core/` staying pure: the report model is pure Python, the scene reader is not.

## 8. Testing

- **Pure** (`tests/unit/`) — the snapshot report model; building a `GuideDocument` from
  breadcrumb dictionaries plus rendered records, including the no-breadcrumb fallback.
- **Maya** (`tests/unit/`, `tests/integration/trigger/`) — `regenerate` writes `trg_entry` on
  the root guide and never writes poses into it; a round trip through
  draw → snapshot → replace → compare; a scene with the tags stripped degrading correctly.
- **Lockstep** (`tests/integration/trigger/test_lockstep_trigger.py`) — the existing tests
  that deliberately never call `sync()` must still pass **with `auto_sync = False`**. That is
  the regression fence for section 3.1: if capture ever moves behind the flag, they fail.
- **UI** (`tests/ui/`) — the bar's three groups, the selection label's three states, the
  checkbox round-tripping with the menu action, and the buttons being gone from the properties
  panel.

`tests/ui/stub.py` gains whatever `GuideScene` gains. It currently still carries
`settings_plug`, which the real `GuideScene` no longer has — a stub outliving its original is
how the unbound-`GuideScene` bug stayed hidden, so that method goes in the same pass.
