# Module Referencing: One Rig Downstream of Another

**Date:** 2026-09-06
**Status:** approved, not yet implemented
**Amends:** `2026-08-31-guide-ownership-and-lockstep-design.md` (the guide document gains
references) and the `kinematics` action as described in
`2026-08-29-trigger-ui-v3-and-io-graph-design.md`. Where this document and those disagree,
this one wins; everything it does not mention is unchanged.

---

## 1. Why

A `.tr` session is the rig *and* its guides. The `reference` action already lets one session
run another's **actions**, with an include list and path-keyed overrides. Nothing carries a
referenced session's **modules** across the boundary.

The gap is not cosmetic. A hero rig that wants to be "the base rig plus wings" has no way to
say so: it can run the base rig's pipeline, but its own `L_wing` cannot connect to the base's
`spine`, because the base's modules are not in this session's guide document at all.

There is also a live defect that proves the gap. `Kinematics._checkout_session_guides` reads
`ctx.session.document.guides`, and `ctx.session` is always the **host** session — so a
referenced session's `kinematics`, arriving through a pipeline reference, silently builds the
*host's* modules rather than its own.

## 2. Modules are a set; actions are a sequence

**The module link lives in the `GuideDocument`, never on a pipeline `reference` node.**

This is forced by cardinality, not by taste. An action is a thing that *happens*, and
happening twice is meaningful: referencing `baseRig.tr` once to run its actions 1–3, then
again to run its action 4, is a legitimate and useful pipeline. A module is a thing that
*exists*, with a uuid identity. "This module exists twice" is not a partial run; it is a
duplicate.

If modules rode on the pipeline node, the two-reference case has no good answer:

- *"the first one brings them"* — invisible magic, and disabling that reference silently
  removes modules the second one appears to own;
- *"both bring them"* — two modules with the **same instance uuid**, which makes connections
  ambiguous and is not drawable in the graph.

A weaker but real second reason: a pipeline reference's position in the list *means* something
— it is where those steps run. Modules have no position in that list. Hanging them off a list
node implies an ordering that does not exist.

### 2.1 What referencing is not

- **Not a way to get a second arm from a library.** That is duplication — new uuids — and it
  is already what `.trg` import does. Referencing is for *"this rig is downstream of that
  rig"*, where identity is the point.
- **Not tied to which actions were opted out.** A pipeline split is a pipeline decision; the
  modules are linked either way.
- **Never a write path to its source.** Referencing does not modify the referenced file, ever.
  There is no "push my overrides upstream", and adding one is out of scope.

## 3. Storage

`GuideDocument` gains two fields, `references` and `frames`:

```python
@dataclass
class ModuleReference:
    ref_id: str                  # uuid; the identity of the link itself
    file: str                    # relative to the session dir when possible
    version: str = "latest"      # same vocabulary as the action reference
    overrides: dict = field(default_factory=dict)
    # {instance_uuid: {
    #     "enabled": bool,
    #     "name": str, "side": str,
    #     "settings": {...},
    #     "inputs": {input_name: "<uuid>.<output>" | "<scene node>"},
    #     "guides": {"<role>:<index>": {"position", "rotation", "rotate_order",
    #                                   "joint_orient", "radius", "color", "attrs"}},
    # }}
```

A guide override key is `f"{role}:{index}"`. **`rotate_order` is part of it**: `capture()`
writes it and a Euler triple is order-relative, so a rotation override stored without its
order silently reinterprets the pose.

**There is no `include` list.** The `kinematics` action (§5) already decides what builds, so an
include list would be a second, competing answer to the same question.

**`enabled: False` survives for a different reason.** It separates *"deliberately not part of
this rig"* from *"in no kinematics action yet"*, which is what keeps the unbuilt warning
(§6.2) quiet about the former and loud about the latter. A disabled referenced module is not
offered to kinematics, is not drawn, and renders struck through in the tree.

### 3.1 What may be overridden, and what may not

| Overridable | Fixed upstream |
|---|---|
| `enabled` | which modules exist |
| `name`, `side` (to resolve a key collision) | a module's `module_type` |
| `settings` | its `GuideLayout` (which roles it has) |
| `inputs` (including the primary input, i.e. reparenting) | — |
| guide `position`, `rotation`, `rotate_order`, `joint_orient`, `radius`, `color`, `attrs` | — |

Structure is upstream's word; everything a rigger *authors* is local. Deleting a referenced
module is not an override — use `enabled: False`. Adding a module "inside" a reference is not
an override either — add a local module whose input names a referenced uuid.

### 3.2 Deduplication, versions and cycles

**Deduplication is by instance uuid, not by file path.** Referenced modules arrive carrying
their own uuids, so a diamond (`hero → base` and `hero → props → base`) produces literally the
same instance ids twice, and the second arrival is dropped. Path-based dedup would miss the
case that matters: `hero → base (latest, v007)` and `hero → props → base (pinned v006)` are two
different paths carrying the same uuids. When the dropped arrival came from a *different*
resolved file, `validate()` warns and names both versions — the rig is being built against one
of them and the rigger should know which.

A cycle raises `SessionError`. `core/guide_reference.py` implements its own chain check rather
than reusing `Reference.expand`'s: that function lives in `actions/reference/`, and `core` may
not import an action package.

### 3.3 Nested references

A referenced session may itself hold `references`. Resolution recurses, and:

- overrides apply **innermost first** — base's own overrides on what it references, then the
  host's overrides on everything base contributes;
- an entry that arrives through a chain is owned by the **top-level link it came through**, so
  a host override on it is stored on that link. The host never writes into base's overrides.

## 4. Resolution: one document, not two

### 4.1 The rejected model, and why

The first draft of this design had `GuideScene.document` return a *separate* resolved object
built by merging local and referenced entries. That is wrong, and the reason is worth
recording because it is not obvious.

Guide-layer writes do not merely mutate entries — several of them **reassign the document's
lists**:

- `guides/scene.py:308` `_write_entry` appends to `document.modules`
- `guides/scene.py:475` `clear()` and `:524` `remove()` reassign `document.modules`
- `guide_document.py:260` `layout_from_keys` replaces `scene_groups`, `positions` and
  `collapse` wholesale — and every node drag reaches it through `set_layout`
- `guides/exchange.py:246` `_entries_from_import` appends to `document.modules`
- `guides/scene_groups.py:82` pops from `positions` / `collapse`

With a separate resolved object, every one of those lands in the copy and never reaches the
session. Folding it back would require a full two-way merge — local adds and removes detected
by set difference, layout written back section by section — which is a far larger and more
fragile surface than "diff each referenced entry against its source".

### 4.2 The model: referenced entries live in the real document

**Resolution inserts referenced entries directly into `session.document.guides.modules`**,
each carrying two **runtime-only** attributes:

- `origin` — `None` for a local module, the owning `ref_id` otherwise;
- `source` — a **deep copy** of the unoverridden entry, so a diff can be taken and *revert to
  source* has something to revert to.

`source` must never be an object the reference cache owns. `capture()` mutates `GuideRecord`s
in place (`guides/capture.py:94`), and `Reference.apply_overrides` sets attributes on the
cached document's own nodes — so a shallow share would make `source` track the very edits it
exists to be compared against, and would corrupt the cache for the next reader.

Three consequences, and they are the whole argument for this model:

1. **`GuideScene.document` does not change at all.** Every existing read and write works
   untouched, including the reassigning ones above.
2. **`Session._module_problems()` validates referenced modules for free**, because it iterates
   `document.guides.modules`.
3. There is no fold, no write-back, and no rule an implementer can forget to apply at a new
   call site.

### 4.3 Overrides are produced at serialization

`GuideDocument.to_dict()` gains the only new rule: it **skips entries whose `origin` is set**,
and emits each reference's `overrides` by diffing its resolved entries against their `source`.

Everything downstream follows without further change. `Session.touch()` compares
`document.to_dict()`, so a pose override marks the session dirty and lands on the undo stack;
`is_modified` and `_saved_state` work unaltered; the `.tr` on disk keeps its shape.

*Revert to source* is `del override[key]` followed by a redraw. And dragging a referenced guide
back to where upstream put it **removes** the override rather than pinning it at a
coincidentally equal value, so the override badge always means something real.

**The diff must be tolerant, or it will mint spurious overrides.** Two rules:

- **Poses** compare through `reconcile.POSE_TOLERANCE` (1e-5), not `!=`. `regenerate` writes
  world-space transforms under a parented joint and `snapshot` reads them back, so a plain
  draw-then-sync round-trip carries float noise. An exact diff would mark every referenced
  module overridden the moment it is drawn, and the self-cleaning property would never fire.
- **Settings** compare after normalizing *both* sides through `module_cls(...).values()`.
  `write_settings` stores a full value dict while an entry loaded from a file may be sparse
  (and becomes sparse whenever a module class gains a field), so a raw dict diff would flag
  every default as an override.

### 4.4 When resolution runs

Resolution needs the session directory to resolve a relative `file`, and `Document.from_dict`
has no `base_dir`. So it is **the session's job, not the document's**, and it runs after every
call that replaces the document:

`load`, `new`, `undo`, `redo`, `__init__`, `snapshot_guides_from_scene`, and any edit to a
`ModuleReference`'s `file` or `version`.

It deliberately does **not** run on plain `touch()`. `Session.touch()` already clears
`_reference_cache` on every edit (`session.py:72`), so joining that list would re-read
`baseRig.tr` from disk on every guide drag. The referenced-document cache is cleared only by
the events above.

One ordering note: `to_dict()` now computes overrides, so in `touch()` the snapshot must be
taken after any in-flight entry mutation — which it already is, since `touch()` is called at
the end of each write.

### 4.5 Structural operations on referenced entries

Because referenced entries now live in the real `modules` list, the operations that reassign
that list must be explicit about them:

- `remove()` on a referenced module → **refused**, with a message pointing at `enabled: False`.
- `clear()` → clears local modules and **preserves** referenced entries; clearing the
  references themselves is unlinking (§8).
- `import_(reset=True)` → same rule as `clear()`.
- `GuideDocument.to_dict()` must keep referenced entries out of the `trg_entry` breadcrumb
  path too (§7.6).

## 5. `kinematics` builds exactly what it names

**A `kinematics` action builds only the modules explicitly listed in it. An empty list is an
error, not "build everything".**

Once that is true, it does not matter whether a module is local, referenced, or was imported
from a `.trg`: if it is named, it builds.

```python
modules = ListField(item_type=str, label="Modules")   # instance uuids
```

- Storage is **instance uuids**; display keys are translated at the read boundary, as
  everywhere else, so a rename can never orphan an entry.
- An entry means **that module only**. Nothing is implied.
- An empty list raises `ActionExecutionError`.

### 5.1 Why exact, and not roots-with-subtree

The old `guide_roots` pulled a named root's whole subtree, and the obvious move was to keep
that. It is wrong here for two reasons.

**Auto-inclusion is the implicitness this design removes.** If a referenced base rig gains a
module upstream, subtree semantics silently start building it in the host rig, which nobody
asked for. That is the same class of magic as "empty means all".

**The subtree is the guide parent hierarchy, and that hierarchy deliberately crosses the
reference boundary.** A local `L_wing` parented under a referenced `spine` is the normal shape
of this feature (§7.1). An entry naming `spine` in the base's pass would therefore drag the
host's local `L_wing` into that pass. The subtree is not the build scope; it merely resembles
it in simple rigs.

List length is an **authoring** problem, and it is solved where it lives: the Designer's
*Add with children* gesture (§7.4) expands a subtree into individual entries **at add time**.
Convenience while authoring, exactness in the file.

### 5.2 Draw, clear and afterlife are all scoped

This is what makes multiple passes safe, and it is the part the first draft left unsaid.
Today `_checkout_session_guides` calls `clear_rendering()` — *every* guide in the scene — and
then `regenerate_all()` on *every* module (`actions/kinematics/kinematics.py:95`). Run that
twice and pass 2 erases pass 1's guides even under `after_build: keep`, redraws modules pass 1
already consumed, and leaves pass 1's guides behind when the mode is `delete`, because
`apply_afterlife` only ever sees pass 2's instances.

So a kinematics action:

- **draws exactly its listed uuids** (`draw(scope=...)`), and skips any that are
  `enabled: False`;
- **never clears outside its own scope**;
- passes **the same scope** to `apply_afterlife`.

Listing a module that is `enabled: False` is a validation error, not a silent skip.

### 5.3 `guides_file` is removed

`kinematics.guides_file` imported a `.trg` at build time and built whatever came out. It cannot
be expressed as a uuid list, because those modules are not in the session at all — so keeping
it would leave one path where the build scope is still implicit. Importing a `.trg` is an
authoring act that puts modules **in** the session; the field goes.

### 5.4 The `ctx.session` defect dissolves

A referenced session's `kinematics` arrives carrying *its own* uuids. Those uuids are in the
host's resolved document precisely when the host module-references that file, so it builds the
right modules by construction, with no notion of "which session do I belong to".

And when the host pipeline-references a session **without** linking its modules, that
kinematics now fails with *"names a module that is not in this session"* instead of silently
building the host's rig. The silent hole becomes a sentence.

## 6. Building across passes

Explicit scopes mean a rig can be built by several `kinematics` actions, with other actions
between them. `Builder` resolves a connection source from a **per-run** `by_key` map, so
anything built in an earlier pass is currently reported as *"outside the build scope; left
unattached"* (`maya/build.py:323`). That branch is what this replaces.

### 6.1 Resolution order

`Builder.resolve` gains one step. The order becomes:

1. `by_key` — built in this pass.
2. key → uuid **from the resolved document**, then the scene node tagged
   `trg_instance=<uuid>` **and `trg_output=<name>`** — built in an earlier pass.
3. a bare scene node name.
4. raise `AttachError`.

Two details that are easy to get wrong:

- **Step 2 resolves the key through the document, not the scene's guides.** With
  `after_build: delete`, an earlier pass's guides are gone by the time a later pass runs, so a
  guide-derived key map would fail exactly when it is needed. The map is built from the
  resolved document, which also means an overridden `name`/`side` gives the key the build
  actually used.
- **The lookup keys on `trg_output`, never `trg_role`.** `finalize()` tags outputs with
  `INSTANCE + ROLE + OUTPUT_NAME` and inputs with `INSTANCE + ROLE + KIND=input`
  (`maya/build.py:135`), so an output and an input on one instance can share a role name.

`_bind_parent_for` gains the same fallback. That is what lets a local module's bind joints be
created in their final position under a referenced module's output rather than reparented
afterwards, keeping the ground rule *"one bind hierarchy per rig, built in final position,
never reparented"* intact across passes.

`known_keys` is likewise computed from the resolved document instead of a scene scan.
`order_by_connections` needs no change: a cross-pass source is simply absent from this pass's
instance list and is ignored by the sort (`core/schemas.py:219`).

### 6.2 Validation

`Session.validate()` gains these checks. Most are only *possible* because build scope is now
explicit.

| Condition | Level |
|---|---|
| a listed uuid no longer resolves | error |
| a listed uuid is `enabled: False` | error |
| the same uuid listed in two kinematics actions | error — double build |
| a module in no kinematics action, not `enabled: False` | warning — *"L_wing is built by no kinematics action"* |
| a display-key collision among modules that actually build | error — names both sides and their origin |
| a connection whose source module builds in no pass | error |
| a connection whose source builds in a **later** pass | error — *"L_wing needs spine, which builds in a later kinematics action"* |
| a reference whose file cannot be resolved | error, naming the link |
| a diamond resolved from two different versions | warning, naming both |
| a `kinematics` still carrying `guides_file` or unresolved `legacy_roots` | error, with the migration instruction |

The later-pass check is the most valuable. Ordering used to be implicit and unstatable; now it
is a property of the pipeline, so getting it backwards is a checkable mistake rather than a
mysteriously unattached limb.

**Two of these must also run at build time, not only on demand.** Nothing calls
`Session.validate()` before a build — `Runner.run` only calls each step's own
`action.validate(ctx)` (`maya/runner.py:193`) — so the cross-step checks (double build,
later-pass source) run in `Session.build()` before the runner starts. An action's own
`validate()` reaches the resolved document through `ctx.session.document.guides`, which is pure
data and keeps `validate()` headless; it must **not** reach for `ctx.session.guides`, which
imports `maya.cmds`.

### 6.3 Naming: no namespace

A referenced module keeps the exact name it would have standalone. `base`'s `L_arm` builds
`L_arm_*` nodes whether built directly or through a reference.

A key collision is resolved by a local `name`/`side` override or upstream. It is not
auto-prefixed: node names must not depend on what else happens to be in the rig, or adding an
unrelated local module would silently rename referenced joints, and skin weights, caches and
every name-based downstream script would follow them.

**`Builder.build` raises on a duplicate key**, in addition to the validate check. `by_key` is a
plain dict (`maya/build.py:277`), so a collision currently overwrites in silence and consumers
attach to the wrong producer — a validate-only check would leave that live for anyone who
presses Build without validating. `GuideDocument.by_key` returns first-match
(`guide_document.py:203`), so the Designer's `source_as_id` is ambiguous under a collision too.

Provenance is shown as a badge and a colour in the tree and graph. It is never in the name.

## 7. The views

### 7.1 Tree — interleaved

The Designer tree **is** the guide parent hierarchy, so a "reference" folder in it would become
a lie the moment a local module parents under a referenced one — which is the normal shape of
this feature. Referenced modules therefore appear in their true hierarchical position, and
this needs no new mechanism: the hierarchy already derives from the primary input
(`guides/handle.py:118`).

```
▸ root            [base]
  ▸ spine         [base]
    ▸ L_arm       [base]  ◆ 3 overridden
    ▸ L_wing              (local, under a referenced parent)
  ▸ L_leg         [base]
```

A referenced row carries an origin badge and a dimmed foreground; a resolved entry that differs
from its source carries an override diamond and a count. `enabled: False` rows render struck
through and sort last among their siblings, so *deliberately not mine* reads differently from
*not drawn*. A module in no kinematics action gets its own marker.

### 7.2 Graph — a collapsible frame per reference

The graph is spatial, so a frame there claims nothing about hierarchy.

```
╭─ baseRig.tr (v007) ────╮
│  [spine]──▶[L_arm]     │
╰────────┬───────────────╯
         └──▶[L_wing]  (local)

collapsed:  [▸ baseRig.tr]──▶[L_wing]
```

**Frames need their own storage section**, not `positions` / `collapse`. Those two are id-keyed
in the document but are read and written exclusively through `layout_as_keys` /
`layout_from_keys`, which project through `node_ids()` — modules and scene groups only — and
`layout_from_keys` is a *replacement*. A frame stored under `ref_id` would survive a file
round-trip and then be silently deleted by the first node drag. `collapse` also holds a 0–2
node mode (`ui/graph/items.py:177`), not a boolean.

So `GuideDocument` gains:

```python
frames: dict = field(default_factory=dict)
# {ref_id: {"position": [x, y], "collapsed": bool}}
```

written directly, bypassing the display-key projection entirely.

### 7.3 Properties

A referenced module's panel opens with a provenance line — *from `baseRig.tr` (v007)* — and
every overridden field shows the diamond plus a revert affordance, with *Revert all* on the
module.

### 7.4 Gestures

These are the only ways in:

1. **Reference Modules…** in the Designer creates a `ModuleReference`.
2. Adding a pipeline `reference` to a `.tr` that has modules **offers** to link them too — one
   gesture, two objects. A second pipeline reference to the same file offers nothing, and says
   why.
3. Designer selection → **Add to kinematics ▸ *(action)***, with **Add with children**
   expanding the subtree into individual entries at add time.
4. The kinematics settings panel gets a module-list widget using the same chooser: a
   `ListField` of uuids cannot be typed by hand.

### 7.5 Draw and Sync

Referenced modules are ordinary entries of the document, so `draw()` renders them exactly like
local ones and needs no special case. `sync()` likewise treats them uniformly: a moved
referenced guide becomes a pose override at serialization (§4.3), with no opt-in gesture.

The risk is not the override — it is *not knowing you made one*, because an override pins the
guide and an upstream proportion fix then stops arriving. So the override is never invisible.

**"Overridden" is not a reconcile state.** `reconcile` compares the document to the *scene* and
is pure (`core/reconcile.py`); overridden compares the resolved entry to its *source* and never
touches the scene. `GuideDiff` must not grow the field — a referenced module can legitimately
be `not_drawn` **and** overridden at once. The Designer computes the override count separately
from the document and passes both to the status strip and to a second tree item role:

```
STATUS  2 out of date · 3 not drawn · 3 overridden
```

**Revert must draw before anything syncs.** `main.py:811` runs `guides.sync()` after undo/redo;
after a revert the joint is still at the moved pose in Maya, so a sync arriving first would
re-derive the override and push a fresh undo step. The redraw runs with the scene watcher
muted, before any sync.

Sync never writes to the referenced `.tr`.

### 7.6 Snapshot From Scene refuses when references exist

`regenerate` stamps a serialized `ModuleEntry` breadcrumb on each root guide
(`guides/regenerate.py:83`) and `scene_recovery.document_from_scene` builds a fresh
`GuideDocument()` with no `references` (`core/scene_recovery.py:103`). Snapshot would therefore
turn every referenced module into a **local** entry carrying base's uuid — and re-linking base
afterwards produces exactly the duplicate-uuid state §3.2 says cannot happen.

Snapshot From Scene is refused while the document holds references, with a message pointing at
unlinking (§8), which already offers the bake-in path.

## 8. Smaller decisions

- **`.trg` export resolves references** and writes plain modules. It is a copy format; a link
  inside it would dangle.
- **Unlinking a reference asks** whether to discard its overrides or bake the referenced
  modules in as local copies (**new uuids**, so a later re-link cannot collide). Silently
  discarding authored proportions would be the one genuinely destructive act in this design.
- **A reference whose file cannot be resolved does not stop the session opening.** Resolution
  is tolerant: local modules load, the link is marked broken, its entries are absent, and
  `validate()` reports it. The Designer must render a document with a broken link rather than
  raise. A relative `file` in an unsaved session (`Session.directory == ""`) is one such
  unresolvable link, not a crash.
- **Schema:** `Document` 6 → 7, `GuideDocument` 1 → 2.

## 9. Migration

Handled at `Document.from_dict`, gated on `schema < 7` — the per-action
`Action.migrate_settings` hook cannot see the guide document, and this migration needs it.
Gating matters because `undo`, `redo` and `copy` all round-trip through `from_dict` with the
schema already stamped current, and must not re-run it.

- **empty `guide_roots`** → expands to every module uuid in the session, so existing `.tr`
  files build exactly as they do today.
- **named `guide_roots`** → resolved against `entry.name`, which selects **every side**
  (`"arm"` → `L_arm` *and* `R_arm`), then expanded through the subtree using the primary input.
  Both are approximations of the old behaviour and must be stated as such: the old code matched
  `handle.name` **or** `handle.root.name` (the root *joint* name, e.g. `L_arm_root_guide`), and
  `_descendants` walked the **scene DAG** via `instance.parent`, which a headless migration
  cannot see. The primary input is usually identical because `regenerate` derives the DAG from
  it, but `reparent_guides` can set the DAG alone.
- **anything unresolvable** — a root joint name, or a name matching no module — is preserved in
  a `legacy_roots` field and reported by `validate()`. It is never silently dropped, and never
  migrated into an empty list: `tests/data/crabMonster_main_session_v002.tr` has
  `guide_roots == ["base_c"]` and zero guides, which would otherwise turn a session that
  validates today into a hard error.
- **`guides_file` set** → cannot be migrated, because it names modules that are not in the
  session. Settings are left intact and `validate()` reports it with an instruction to import
  the `.trg` and list its modules.
- **A host override of a referenced kinematics' `guide_roots`** cannot be migrated at
  `Document.from_dict`: it lives in the host's reference node as an opaque settings payload
  (`handles.py:116`) applied by a blind `target.settings[key] = value`
  (`actions/reference/reference.py:99`), and the host document does not know the target's type.
  It is migrated **lazily in `Reference.apply_overrides`**, which does have the target node. An
  unmigrated override left in place would otherwise become a dead key and the host would
  silently build a different scope.

## 10. Tests

| File | Covers |
|---|---|
| `tests/unit/test_guide_reference_trigger.py` | resolution, override application, `to_dict` diffing with pose tolerance and settings normalization, uuid dedup, version-mismatch warning, cycles, nested references, broken links — all pure |
| `tests/unit/test_kinematics_scope_trigger.py` | explicit `modules`, empty → error, disabled → error, scoped draw/clear/afterlife, `legacy_roots`, `guides_file` reported |
| `tests/unit/test_document_trigger.py` (extend) | schema 7, `GuideDocument` schema 2, `frames` round-trip, migration gated on `schema < 7`, undo/redo/copy do not re-migrate |
| `tests/unit/test_session_trigger.py` (extend) | the `validate()` checks of §6.2; resolution reruns on load/new/undo/redo; `touch()` does **not** reload referenced files |
| `tests/integration/trigger/test_module_reference_build.py` | two-pass build, cross-pass input resolution by `trg_output`, `bind_parent` across passes, duplicate-key raise, `after_build: keep` on pass 1 surviving pass 2 |
| `tests/integration/trigger/test_draw_sync_trigger.py` (extend) | draw-then-sync mints **no** override (tolerance); a real move does; moving back removes it; revert draws before sync |
| `tests/ui/test_designer_references.py` | badges, override markers, frame position surviving a node drag, collapse, the four gestures |
| `tests/unit/test_import_boundaries.py` | `core/guide_reference.py` stays pure — no Maya, no Qt, no prefs, no `actions` import |

## 11. Deletions

Nothing here is deprecated in place; what this design makes redundant is removed.

- `kinematics.guides_file` and its `.trg` import branch.
- `kinematics.guide_roots` and `actions/kinematics/kinematics.py::_descendants`.
- `Kinematics._checkout_session_guides`' unscoped `clear_rendering()` + `regenerate_all()`,
  and its fallback to "build every module in this session". It still reaches the document
  through `ctx.session`; what goes is the implicit scope.
- `Builder._connect_one`'s *"outside the build scope; left unattached"* warning branch,
  replaced by step 2 of §6.1.

## 12. Suggested phasing

The `kinematics` rewrite (§5, §6, §9) stands on its own, is independently valuable, and is a
hard prerequisite for the rest. It is the natural first phase; §3–4 and §7 follow.
