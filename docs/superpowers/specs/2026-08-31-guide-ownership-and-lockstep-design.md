# Guide Ownership, Lockstep and Guides-in-Session — Design Spec

Date: 2026-08-31
Status: brainstormed with Arda Kutlu; awaiting spec review.

Revises `2026-08-29-trigger-ui-v3-and-io-graph-design.md` (the I/O graph stays;
its storage changes) and supersedes the window-level Designer mode in
`2026-08-30-designer-as-mode-tab-design.md` (the Designer becomes a per-session
view). Retires the standalone `.trg` document; `.trg` survives as an
import/export format.

## 1. Goal

Guides have no owner. Deleting a guide joint in the outliner does not reach the
Guide Designer until the next launch, and it is not clear from which side any
given fact should be updated. This spec gives every guide fact exactly one
durable home, makes the scene a rebuildable rendering of that home, and puts
the whole thing inside the session document so the question "whose guides are
these?" has an answer.

### 1.1 Why the old model cannot simply be restored

The previous Trigger's guide tab had no ownership problem because guides had no
state that joints could not express. Parenting was the only relation between
modules, and DAG parenting *is* the joints; settings were attributes on the root
joint. A scene scan was lossless, so `populate_guides()` could discard the tree
and rebuild it from the scene on every `SelectionChanged` — which is exactly what
it did (`trigger/ui/main.py:196` in the old repo, its only callback).

The current Designer introduced state that joints cannot express: a connection
graph with named ports, scene-node groups referencing arbitrary Maya nodes, node
positions, collapse modes. That state is *stored* in the scene (`trg_inputs` on
root guides, a `trg_designer` JSON blob on the holder) but not *expressed* by it.
The scene became a container rather than a representation, and a container
cannot validate its contents, repair them, or notice Maya mutating them.

### 1.2 The five concrete defects

1. **No delete signal exists.** `SceneWatcher.DEFAULT_EVENTS`
   (`shared/ui/scene_watcher.py:21`) is `SelectionChanged`, `DagObjectCreated`,
   `SceneOpened`, `NewSceneOpened`, `Undo`, `Redo`. Maya's `scriptJob` offers no
   generic node-deleted event and nothing in the repo uses the API callbacks that
   do. `designer/window.py:_on_scene_event` additionally early-returns on
   `SelectionChanged`, deliberately dropping the old tool's accidental catch-all
   without replacing it.

2. **Identity is uuid in principle, name-string in practice.** Guide joints carry
   `trg_instance` uuids, but everything the Designer authors is keyed by `key`
   (`L_arm`): connection sources are `"L_arm.hand"` strings in `trg_inputs`, and
   `positions` / `collapse` / `scene_nodes` in `trg_designer` use the same key.
   `_rename_key` and `_forget_key` (`guides/scene.py:478`, `:489`) patch these up
   only when the edit goes through the UI.

3. **Two unreconciled hierarchies.** `create_guides(parent=)` DAG-parents the
   joints *and* pre-fills the primary input. The tree's drop handler
   (`designer/commands.py:reparent`) then rewires **only the connection**, while
   `reparent_guides` moves **only the DAG**. After the first edit the joint
   hierarchy and the connection graph mean different things, and the tree shows
   the second.

4. **Drift is bidirectional.** Setting `fkchain.segments` from 3 to 5 updates the
   settings meta and `output_names()`; `_topology`
   (`designer/properties.py:113`) sees the port list change and redraws the graph
   with five segment ports — and no joints are drawn. You can wire `segment5`,
   export it, and fail at build time. Watching the scene harder fixes half the
   problem at most.

5. **Partial destruction has no representation.** Deleting one non-root joint
   leaves `find_instances` rebuilding a malformed instance that only fails at
   build. Deleting the root destroys the module's name, settings and every
   connection into it, because that data lives on the joint; its remaining joints
   persist tagged with a dead instance id. Maya-duplicating a guide hierarchy
   copies `trg_instance`, and `find_instances` silently merges the copy into the
   original.

Related, and part of the same feeling: `is_modified` and `versioning` exist for
`.tr` sessions only (`session.py:241`, `main.py:417`, `:471`). The Designer has a
filename label, no dirty flag and no close guard, so guide work is discarded
silently on window close. And `main.py:_ensure_designer` builds **one** Designer
for a window that holds **N** session tabs, so with two sessions open the guides
in the scene belong to neither.

## 2. Decisions (from brainstorming, 2026-08-31)

- **The `.trg` is not the master document; the session is.** Guide data moves
  into the `.tr` file. `.trg` demotes to an import/export format for guide
  libraries and for the kinematics action's external-file case.
- **The Maya scene is a working tree, not a store.** It holds a complete working
  copy — so Maya undo covers everything uniformly and a TD can script against it
  — and the session file is the commit. Structure never lives only in Python
  memory; that would mean two interleaved undo stacks.
- **Every guide fact has exactly one durable home**, and guide joints are a
  rendering the document owns and can rebuild.
- **Lockstep** is the authoring policy: the scene and document are never
  knowingly apart. Checkpointed behaviour (visible staleness, deferred redraw) is
  the same substrate with a different subscriber, and is the documented fallback.
- **The scene is a checkout of exactly one guide document at a time.** Switching
  session tabs captures, swaps, and regenerates.
- **The Guide Designer becomes a per-session view**, below the session tabs.
- **No backward compatibility.** The tool is unreleased. There is no migration
  shim for scenes carrying `trg_settings` / `trg_inputs` on root guides and no
  `.trg` version negotiation.
- **Guide overrides across references are deferred**, not foreclosed.

## 3. Ownership model

| Fact | Durable home | Rationale |
|---|---|---|
| Module exists, type, side, name, settings | Document, keyed by uuid | Authorable only from the UI; must survive any scene edit |
| Connections, scene-node groups, graph positions, collapse | Document, keyed by uuid | Same; today's name-keyed strings are the main fragility |
| Guide pose — translate / rotate / rotate order | Document, captured from joints | Authorable only in the viewport, but must survive joint deletion |
| Guide attrs (`guide_attrs`, `useRefOri`), radius, colour, intra-module parent | Document, captured from joints | Same |
| Guide joints | A rendering the document owns and rebuilds | Not a store — an editable projection |

Joints remain where poses and guide attrs are *authored*. Capture moves that
authoring into the document; nothing is stored **only** on a joint.

### 3.1 Module settings versus guide attrs

These are distinct and must not be conflated:

- **Module settings** — one value per module (`fkchain.segments`, twist's
  `extraction`, `controller_size`). Edited in the properties panel.
- **Guide attrs** — one value per *guide joint*, declared via `guide_attrs` and
  created by `GuideDraft` (`maya/rig.py:104`). Twist's `position` and
  `twistWeight`, and `useRefOri`.

For twist, guide attrs are the entire interface, not a convenience: the module
locks the guide's transform channels and drives them from `position`, so the
channel box is the only way to author it. **Guide attrs stay on their joints.**
Nothing in this spec changes them; they are captured and restored like poses.

### 3.2 Where module settings live

Each module instance gets its **own document node** in the scene, carrying its
scalar settings as real Maya attributes and its document entry as meta. This
keeps a clean channel-box surface per module (rather than one blob node holding
`L_arm_segments`, `R_arm_segments`, … in a single soup), gives per-module undo
granularity, and makes the node the module's durable identity — what the root
guide joint is today, minus being deletable as a side effect of editing guides.

`settings_plug()` returns a plug on the module node instead of the root guide.
`_bind_properties` and `MayaAttributeAdapter` are otherwise unchanged.

### 3.3 What the working copy is, physically

The durable home is the session file, but the *working copy* lives in the Maya
scene so that undo, scripting and overnight work all behave. Concretely the scene
carries:

- **One module node per module instance** — settings as attributes, the module's
  document entry (name, side, connections, stored poses, guide attrs, layout) as
  meta, keyed by its uuid.
- **One checkout node** (the guide holder) — the scene-node groups, and the stamp
  identifying which session document this checkout belongs to (§6.3).
- **Guide joints** — the rendering, owned by the module nodes.

Saving the session serialises the module nodes into the `.tr`; opening a session
projects them back. Nothing in this arrangement is Python-memory-only, which is
what keeps Maya's undo authoritative over the whole document.

### 3.4 Consequences

- Deleting any guide joint, including a root, never destroys a module. It makes
  the module's rendering stale; lockstep redraws it. Removing a module is a
  Designer operation.
- Maya-duplicating a guide hierarchy produces joints claiming a
  `(uuid, role, index)` that is already rendered. Reconcile reports them as
  orphans instead of merging them into a malformed instance.
- `trg_name`, `trg_settings` and `trg_inputs` leave the root guide.
- Renames stop mattering. Connections are uuid-keyed, joint names are part of the
  rendering, and a rename in the outliner is drift that regenerate quietly fixes.
  **No rename callback is needed.**

## 4. The three operations

### 4.1 Reconcile — pure, no Maya

Takes the document plus a scene snapshot; returns a diff. No writes.

Per module: rendering absent · roles missing · multi-count mismatch · pose drift ·
DAG parent wrong.
Scene-wide: orphan joints — a uuid the document does not know, or a second set
claiming an already-rendered `(uuid, role, index)`.

**Each kind of drift has exactly one resolution, and they must never be
confused:**

| Drift | Resolved by | Winner |
|---|---|---|
| Pose or guide-attr differs from the document | **Capture** | The scene |
| Rendering absent, roles missing, count mismatch, DAG parent wrong | **Regenerate** | The document |
| Orphan joints | Reported only; never touched automatically | — |

Regenerate is for *structural* mismatch alone. A regenerate triggered by pose
drift would teleport a guide away from where the rigger just dragged it, which
would be the worst bug this tool could have. Orphans are never deleted
automatically: they may be a rigger's scratch work, and destroying untracked
scene content is not a repair.

Expected shape comes from the manifest: document settings →
`GuideLayout.guide_pairs(count)` (`core/manifest.py:102`) → compare with what is
rendered. `GuideLayout.validate` (`:117`) already phrases the problems in English
and is currently called by nothing.

Reconcile is **pure Python — no Maya, no Qt** — so it lives in `core`, satisfies
`tests/unit/test_import_boundaries.py` by construction, and is unit-testable
without `mayapy`. This is how we get confidence in the subtlest part of the
system.

### 4.2 Capture — scene → document

Reads pose, rotate order, guide attrs, radius, colour and intra-module parent.
Cheap: `nodes.instance_from_nodes` (`guides/nodes.py:167`) already reads world
position, rotation and rotate order for every guide on every scan, so this
persists a read that already happens.

Three rules, all load-bearing:

1. **Additive.** Only updates entries for joints that exist. A missing joint
   leaves its stored pose alone. This single rule is what makes deleting a joint
   lossless rather than a race.
2. **Undo-safe.** Capture writes are non-undoable, or folded into the chunk of
   the operation that triggered them. Otherwise a refresh on `Undo` pushes tool
   bookkeeping onto the undo queue and the next Ctrl+Z undoes the wrong thing.
3. **Never inside a regenerate**, or it captures a half-built rendering.

Capture runs on scene-event refreshes, before save, before build, before
regenerate, on tab switch and on close.

### 4.3 Regenerate — document → scene, scoped to one module

Never global. If changing one field redraws the whole character, lockstep is not
viable.

1. Capture survivors.
2. Delete that module's guide joints.
3. Rebuild the `Module` with its **stored uuid** — `Module(instance_id=…)`
   already accepts one (`core/module.py:67`).
4. `draw_guides`, then apply stored poses per role. Roles the document has no
   pose for (newly added by a settings change) land at their `draw_guides`
   position.
5. Re-apply guide attrs, radius, colour.
6. `wire_guides`.
7. Parent the root guide under its producer's output guide.

Step 4 is the one that decides whether lockstep feels helpful or hostile:
`segments 3→5` must keep segments 0–2 exactly where the rigger put them and draw
only the new ones.

`create_guides(module, poses=…, inputs=…)` already applies poses, so this is
close to expressible with today's primitives.

### 4.4 The DAG becomes derived

Step 7 resolves defect 3. Each module's root guide is parented under its
**primary input's** producer output guide because the document says so, rebuilt
on every regenerate. Dragging the shoulder moves the arm, and the two hierarchies
cannot diverge because the DAG is no longer an independent fact. Secondary inputs
(spaces, reach targets) stay data-only, which is already how the tree reads them
(`window.py:parent_key`).

The document refuses primary-input cycles, since they would describe an
impossible DAG.

## 5. Lockstep

**After a document write:** reconcile the affected modules → regenerate those
whose rendering is *structurally* stale → all in one undo chunk with the
originating edit, so one Ctrl+Z takes back both the setting and the joints.

**After a scene event:** capture → reconcile → regenerate anything structurally
stale → refresh the views.

Capture comes first on the scene path, so pose drift is absorbed before
reconcile runs and can never be mistaken for a reason to redraw (§4.1).

### 5.1 Re-entrancy

One rule holds it together: **every scene write the tool makes is muted, and
reconcile never runs inside a regenerate.** Without it, regenerate's own delete
step fires the delete callback, which reconciles, which regenerates. The existing
`SceneWatcher.mute()` and `_refreshing` guard are the right primitives and need
extending to the new paths.

### 5.2 Callbacks

- **Node removal** — `MDGMessage.addNodeRemovedCallback` filtered to DAG nodes:
  one scene-wide callback that needs no re-registration as guides come and go,
  unlike per-node `scriptJob(nodeDeleted=…)`. It fires for every node removal, so
  it filters cheaply and relies on `SceneWatcher`'s zero-timer coalescing for
  bursts. It must survive firing during undo/redo and file-new, and **must be
  deregistered on teardown** — a live OpenMaya callback into a destroyed widget
  crashes Maya on shutdown.
- **Parent changed** — `MDagMessage.addParentAddedCallback`. Without it,
  re-parenting a guide in the outliner is not noticed until some other event
  fires, and a guide that snaps back several seconds later is worse than one that
  snaps back at once.
- **`SelectionChanged` stays ignored.** It was the old tool's accidental
  catch-all; with real callbacks we do not want a scene scan on every click.

### 5.3 Falling back to checkpointed

Lockstep and checkpointed share the entire substrate; they differ only in who
consumes the reconcile result. Lockstep acts on it immediately and therefore has
nothing to display. Checkpointed displays it ("3 modules need redraw") and defers
regenerate to an explicit verb. Switching is a policy change, not a rewrite — the
substrate lands as its own commit (§9) so the alternative can be branched from it
rather than reverted to.

## 6. Guides in the session

### 6.1 Schema

Guide data becomes a field on `Document` (`core/document.py`), schema 4 → 5. The
existing "newer than supported" guard (`document.py:78`) covers forward
compatibility. The payload is what `GuideFile` already carries — records,
connections, designer layout — so `guides/format.py` is adopted rather than
replaced, and `make_record` (`guides/scene.py:238`) already describes a guide
joint completely: name, position, rotation, joint orient, parent, radius, colour,
attrs, settings, module name.

### 6.2 What this eliminates

- **Version skew.** The kinematics action points at a `.trg` path
  (`actions/kinematics/kinematics.py:26`), so a session can build against a
  guides file from a different version than it was authored with, undetected. The
  field becomes optional — default to this session's guides, keep the path as an
  override for a shared library.
- **A parallel document type.** Guides inherit `Session`'s `is_modified`,
  versioning, dirty title and close guard rather than growing their own.
- **The unanswerable question.** With guides in the `.tr` and the Designer under
  the tab, "whose guides are these?" is well-formed.

A `.tr` also becomes a self-contained rig description, which composes correctly
with the reference action: referencing `baseRig.tr` brings its guides along.

### 6.3 The checkout model

N session documents, one render surface. The rule:

> **The Maya scene is a checkout of exactly one guide document at a time.**

Switching session tabs captures the current tab's guides, swaps the document, and
regenerates. This only works because regenerate is scoped, lossless and real.

Requirements:

- The scene's working copy is **stamped with the session it belongs to**, so
  opening a scene whose guides came from a different `.tr` is reported rather
  than silently adopted.
- Which document is checked out is **visible at all times**. If answering "which
  session's guides am I looking at?" ever requires inference, the original problem
  has been rebuilt one level up.
- Checkout is lazy — performed when the Designer view for a tab is first
  activated, not on every tab switch.

### 6.4 UI placement

The Designer stops being a window-level mode (`main.py:_build_designer_mode`,
`_ensure_designer`) and becomes a view owned by `SessionView`, one per tab.
Tear-off is preserved; it is torn off from a tab. This supersedes the mode-tab
placement in `2026-08-30-designer-as-mode-tab-design.md`.

### 6.5 `.trg` as an exchange format

Export is unchanged in spirit. **Import** needs care it does not currently get:
imported modules take fresh uuids, names are uniquified against what is present
(`unique_name` exists), connections internal to the file are remapped onto the
new uuids, and connections pointing outside it are dropped rather than left
dangling. Today `import_(path, reset=False)` merges without any of that — import
the same file twice and you get two modules called `L_arm`.

## 7. Code map

Rewritten:

- `guides/nodes.py` — `instance_from_nodes` stops reading name / settings /
  inputs from root meta; gains the capture read.
- `guides/scene.py` — `_write_root_meta`, `_sync_setting_attrs`,
  `read_settings` / `write_settings`, `set_inputs`, `settings_plug`, the layout
  accessors, `import_` / `export`.
- `guides/handle.py` — reads and writes go to the document.
- `designer/properties.py` — `_plug_adapter` / `_bind_properties` point at the
  module node.
- `designer/window.py` — refresh becomes capture → reconcile → regenerate →
  redraw views; the Designer is constructed per session.
- `ui/main.py` — Designer moves under `SessionView`; the guide mode holders go.
- `core/document.py` — schema 5, guides field.
- `actions/kinematics/kinematics.py` — `guides_file` optional.

New:

- `core/guide_document.py` — the guide document schema and **reconcile** (pure).
- `guides/capture.py`, `guides/regenerate.py` — the two Maya-side operations.
- `maya/observer.py` — extended with the OpenMaya removal and parent callbacks.

Deleted:

- `_rename_key` and `_forget_key` (`guides/scene.py:478`, `:489`) — they exist
  only to patch name-keyed layout entries; uuid keying leaves nothing to patch.
- The `trg_designer` blob on the holder, folded into the document.

Also noted for the same pass: `_descendants` in `kinematics.py` walks
`instance.parent` (the DAG-derived `ParentRef`) rather than the connection graph.
With the DAG derived from the primary input this still gives the right answer,
but it should read the connection graph directly.

## 8. Testing

- **Reconcile is pure, so it is unit-tested without Maya** — the missing-role,
  count-mismatch, orphan and duplicate-uuid cases as plain data. This is the main
  correctness lever.
- `tests/unit/test_import_boundaries.py` must keep passing: reconcile and the
  document schema import no Maya and no Qt.
- Maya-side tests (`tests/unit/test_guides_trigger.py`,
  `test_guide_scene_trigger.py`, `tests/integration/trigger/`) cover: capture is
  additive across a joint delete; regenerate preserves surviving poses on
  `segments 3→5`; a structural change and its regenerate undo as one chunk;
  Maya-duplicating a module reports orphans instead of merging; the derived DAG
  is rebuilt from the primary input.
- A round-trip test that a session saved, reloaded and regenerated produces the
  same guide poses it started with — the guarantee the whole design rests on.
- UI tests (`tests/ui/`, `TIK_TESTS_NO_MAYA=1`) cover the per-tab Designer and
  the checkout stamp, against `tests/ui/stub.py`.

## 9. Build order

Each numbered item is a commit; item 4 is the substrate boundary and the point to
branch from if lockstep is rejected.

This is large enough to split into **two implementation plans**: items 1–5
(ownership and lockstep, entirely within the guide layer) and items 6–7 (session
integration and the UI restructure). The first is independently valuable and
shippable — it fixes every defect in §1.2 — and the second can be planned once
the substrate has been lived with.

1. **Guide document schema + reconcile**, pure, with unit tests. No behaviour
   change.
2. **Move structure off the guides.** `trg_name` / `trg_settings` / `trg_inputs` →
   module document nodes; connections and layout uuid-keyed; `_rename_key` /
   `_forget_key` deleted; bindings repointed. Designer still refreshes as today.
3. **Capture and regenerate**, with the delete and parent callbacks. Regenerate
   exposed as an explicit verb only.
4. **Substrate complete.** Reconcile is computed and available; nothing consumes
   it automatically yet.
5. **Lockstep policy** — auto-regenerate on document write and on scene event,
   one undo chunk, re-entrancy guards.
6. **Guides into the `.tr`** — schema 5, kinematics `guides_file` optional,
   `.trg` import hardened with uuid reassignment.
7. **Designer under the session tabs** — per-tab construction, checkout model,
   checkout stamp and its indicator.

## 10. Non-goals

- Guide overrides across references. Once guides live in the `.tr` and sessions
  reference sessions with overrides, "reference `baseRig.tr` with my character's
  proportions" becomes an obvious and powerful feature. The schema should not
  foreclose it. None of it is built now.
- Teardown-and-rebuild on every test build. The capability is delivered by
  regenerate; wiring it into every build is a toggle, defaulted on while the
  system is young for its integrity-check value, and turned off for heavy rigs —
  `create_guides` calls `module.wire_guides`, so modules with live guide rigs
  re-run their guide construction on every rebuild.
- New modules, new actions, rig features, UI visual redesign.
- Selection sync between the Designer and Maya. It remains explicit
  (*Select guides*), as decided in the I/O graph spec.
