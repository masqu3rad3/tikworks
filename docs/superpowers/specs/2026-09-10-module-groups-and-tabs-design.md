# Module Groups: many copies of one module, one node and one panel

**Date:** 2026-09-10
**Status:** designed
**Amends:** nothing. This is additive. `2026-08-29-trigger-ui-v3-and-io-graph-design.md` (the
module I/O model), `2026-08-31-guide-ownership-and-lockstep-design.md` (the guide document) and
`2026-09-05-draw-and-sync-separation-design.md` (Draw and Sync) all stand unchanged; this
document adds a layer above them that none of them has to know about.

---

## 1. Why

A hand is five `fkchain` modules. Two hands are ten. Add toes and the graph is thirty nodes
that differ in one word each, laid out by hand, connected one at a time, and edited one at a
time. The graph stops being a picture of the rig and becomes a picture of the repetition in
the rig.

The Designer already has half an answer. Selecting several same-type modules writes a setting
to all of them at once — `properties.py:82` is literally

```python
targets = self._multi or [self._current]
```

— so editing five fingers' `segments` in one gesture works today. What it does not do is
survive: the selection is gone the moment you click elsewhere, the graph still shows five
nodes, and nothing records that these five modules are *one thing the rigger thinks about
together*.

The graph also already has the other half. A pipeline `reference` draws as a frame around its
modules and collapses to a single node carrying only the connections that cross its boundary
(`ui/graph/view.py:405`, `FrameItem` in `ui/graph/items.py:131`). That is exactly the picture
wanted here, built and tested, and reachable only by putting the modules in a different file.

So the missing piece is small: a durable name for a set of same-type modules, and permission
for the two mechanisms that exist to point at it.

## 2. Decision

**A group is a set of same-type module instances that the Designer draws as one node and edits
through one panel. It is a document-and-UI fact and nothing else.**

Three consequences, each load-bearing:

**A tab is a real module.** Every member is an ordinary `ModuleEntry` with its own uuid, name,
settings, inputs and guides — precisely what exists today. Nothing about a member is special
because it is a member. This is what keeps build, guides, shapes, anim spaces, pivot presets,
`reconcile`, the `.trg` and the publish set out of the change entirely.

**Grouping never changes the rig.** No group id, label or membership reaches `build()`, a guide
joint, the bind skeleton or a node name. Given the same members, grouped or ungrouped, the
build is identical. This is the same shape of guarantee as *preferences never change the rig*,
and it is enforced the same way (§8).

**Sharing is derived, not declared.** A setting the members agree on is shared; one they
disagree on is not. Nothing in a module class, a manifest or a group record says which is
which. That is what makes the feature land on every module — the five that ship, and every one
written afterwards — with no module author doing anything.

### 2.1 What was rejected

**One instance holding N copies.** One uuid, one entry, guides keyed by `(copy, role, index)`,
outputs and controls multiplied per copy. Truest to "one node", and wrong: every uuid-keyed
assumption in the system — the guide document, `reconcile`, the `.trg`, `expand_guides`, the
shape override table, anim spaces, pivot presets, `build_scope`, `PublishSet` — would grow a
copy axis, to buy a picture the frame mechanism already draws.

**A `shared_settings` declaration on the module class.** Stable panel layout, no rigger setup,
and it is the module author guessing what a rigger wants shared. It also needs a touch in every
module, which is the thing this feature is supposed to avoid.

**Rigger-pinned shared fields.** Explicit and stable, but a fresh group starts with everything
per-tab — the opposite of the intent — and it is setup work before the feature pays anything
back.

**Purely a graph view, nothing stored.** Cheapest by far. Rejected because "common inputs"
stays a manual per-instance chore, which is half of what makes thirty nodes tiring.

## 3. The document object

`ModuleGroup` joins `SceneGroup` and `ModuleReference` in `core/guide_document.py`:

```python
@dataclass
class ModuleGroup:
    """A set of same-type module instances the Designer treats as one."""

    group_id: str
    label: str            # "fingers"; the node reads L_fingers
    members: list         # instance_ids, in tab order

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "ModuleGroup": ...
```

Three fields, and everything else derives:

- `module_type` and `side` come from the members. Both are enforced homogeneous when a module
  joins; there is no second copy of either to fall out of step.
- `key` is `instance_key(label, side)` — the same function `ModuleEntry.key` uses
  (`core/manifest.py`), so a group and a module name themselves by one rule.

`GuideDocument` gains `groups: list`, a `group(group_id)` lookup beside `module()` and
`reference()`, and group keys join `node_ids()` so the graph can address a group the way it
addresses a module or a scene group.

Membership is stored on the group, not on the member. A `group_id` field on `ModuleEntry` would
be a second place for the same fact, and the entry is the thing that gets serialized, diffed
against a reference source and copied by `duplicate` — three chances for the two copies to
disagree.

**Schema.** The guide document goes 2 → 3. The `.tr` stays at 7: the guide document carries its
own version inside it. Old files load with `groups: []`; there is no migration.

## 4. Graph placement reuses reference frames

A group writes `{position, collapsed}` into the existing `frames` dict under its `group_id`.
That section exists for exactly this reason — its docstring says so:

> Deliberately *not* `positions`/`collapse`: those are projected through `node_ids()` and
> replaced wholesale by `layout_from_keys`, so a frame stored there would be deleted by the
> first node drag.

Members keep their own `positions` entries, which is how the expanded view places them — the
same arrangement a reference already has.

`FrameSpec.ref_id` and `FrameItem.ref_id` become `frame_id`, and the two signals
(`frame_toggle_requested`, `frame_selected`) carry a frame id rather than a reference id.
`ui/graph/view.py` reads frames from the document at lines 180, 290 and 353 and builds them at
405; each of those learns that a frame may come from a group as well as a reference. `FrameItem`
itself is untouched.

## 5. The properties panel

A tab bar sits above the generated form on **every** module, grouped or not: one tab and a
`[+]`. Above it a `Common` fold; below it the per-tab form.

```
L_fingers  ── 5 members
┌─ Common ────────────────────────────┐
│ root      ◀── L_hand.hand           │
│ stretch   [x]                       │
└─────────────────────────────────────┘
[index][middle][ring][pinky][thumb][+]
┌─────────────────────────────────────┐
│ name      [index]                   │
│ segments  [3]        ◇ varies       │
└─────────────────────────────────────┘
```

### 5.1 Which side a field lands on

Recomputed on every write. A setting or input whose value is equal across all members renders
in `Common`; one that differs renders inside each tab, carrying a `◇ varies` mark. The mark
explains why the field dropped out of `Common` — it is not an override flag, and must not be
drawn like the reference override diamond, which means something else.

Two fields are fixed rather than derived. `name` is always per-tab, because member names must
stay unique. `side` is always common, because §3 enforces it.

The panel reflows when a value diverges: change one finger's `segments` and `segments` drops
from `Common` into the tabs. That is honest — the panel is a picture of what the members agree
on, and they no longer agree — and it is the price of declaring nothing anywhere.

### 5.2 The write path is the one that ships today

`Common` and the tabs are both on screen at once, so the target set is a property of the
*field*, not of the panel's state: a field rendered in `Common` writes to every member, a field
rendered in a tab writes to `_current`. `_on_setting_changed` gains that one decision —

```python
targets = self._members if self._is_common(name) else [self._current]
```

— replacing today's `self._multi or [self._current]` (`properties.py:82`). Everything after it
is unchanged: the same loop under `watcher.mute()`, the same per-handle `_topology` snapshot,
the same refresh when a change moved a port or a guide. Multi-select across ungrouped modules
keeps using `_multi` exactly as it does now.

### 5.3 Tab bar verbs

- `[+]` — `guides.duplicate(current)` (`guides/scene.py:821`, which copies type, side, settings,
  inputs and poses, and names `index` → `index1`), then join the group. If the module was
  alone, the group springs into existence around both.
- Double-click a tab — rename that member.
- Drag a tab — reorder `members`.
- Right-click a tab — *Remove from group*, *Delete module*, *Ungroup*.

Selecting a tab makes that member `_current`, so Select Current, Mirror, Delete and the guide
selection keep acting on exactly one module.

### 5.4 New copies stack

`[+]` produces an exact duplicate, guide poses included, so the new copy's joints sit precisely
on the original's and the rigger drags them into place. This matches `duplicate` today, and it
matches the pivot-preset rule already in the codebase — *an unplaced preset should look
unplaced*. One rule for all three.

Fanning new copies along an axis was considered and dropped: the offset direction is a policy
with no clean home. World X is wrong for a rotated hand, and the module's own axis is not
something the base class can know without a new declaration — which §2 spends its budget
avoiding.

## 6. The graph

Collapsed by default when the group is created. The node carries the type icon, the group key
and a member count; its ports are the union of the members' ports.

**Inputs fan in.** Wiring a collapsed group's input port gives every member's input of that
name that source. This is what makes a `Common` input real rather than a display trick, and it
is the single most repetitive thing about thirty nodes.

**Outputs do not fan out.** Dragging from a collapsed group's output port pops the member list
to pick one.

The asymmetry is deliberate and worth stating plainly: *all of these attach to the same place*
is a meaningful thing to say, and *which one of these drives that* is a question with no
default answer. Fanning an output out would silently create five wires where the rigger
intended one.

Expanded, the group is a frame around its member nodes, each with its own ports, wired
individually — the reference-frame behaviour, unchanged.

## 7. The tree, and the rest of the app

**Tree.** The group is a parent row carrying the type icon and its member count; members are
children. It aggregates its members' Draw/Sync state to the worst one — *out of date* over
*drifted* over *absent* — using the existing colours from the Draw/Sync spec. Selecting the
group row shows the group's panel with no tab preferred; selecting a member row shows the same
panel with that member's tab active. `Common` is present either way — it is derived per field
(§5.1), never a mode the selection switches on.

**Mirror.** `mirror_group` wraps the per-module `guides.mirror` (`guides/scene.py:739`): mirror
every member, create the opposite group with the mirrored side and the same label, carry the
connections. Re-mirroring updates in place, as module mirroring does. Both halves draw, per the
existing rule that mirroring draws the copy it creates and the source it read.

**References.** Groups live in the guide document, so a referenced session's groups arrive with
its modules and draw as groups. Structure is upstream's word: a borrowed group refuses `[+]`,
remove and ungroup, exactly as `remove` is refused on a borrowed module. Per-member setting
overrides keep working untouched — a member is still an ordinary entry being diffed against its
source. A group is wholly local or wholly borrowed, enforced on join; a half-borrowed group
would have a membership list that is partly this file's word and partly upstream's, with no
answer for what happens when upstream drops a member.

**Kinematics picker.** `CheckListEditor` (`shared/ui/check_list.py:36`) gains group parent rows;
ticking a group ticks its members. Storage is unchanged — the scope still holds member uuids —
so the picker is the only thing in the action layer that learns the concept.

**`.trg`.** The exchange format carries an optional `groups` section, so an exported hand comes
back as a hand. A reader that does not know the section ignores it and gets five modules, which
is the correct degraded result.

### 7.1 Deliberately untouched

A group is **not a build unit**. Build scope expansion follows connections
(`core/build_scope.py`), `PublishSet` follows dependencies, the test rig follows modules,
`reconcile` follows guides. None of them gains a group branch. "Build this group" means "build
these members", resolved at the picker before anything downstream sees it.

## 8. Enforcing the invariant

Two tests, because the guarantee has two halves.

**Nothing downstream may read it.** `tests/unit/test_import_boundaries.py` gains a case
forbidding `trigger/maya`, `trigger/modules`, `trigger/systems` and `trigger/guides` from
reading `document.groups` or importing the group object. This is the mechanical half, and it is
the one that keeps the guarantee true a year from now.

**The build is identical.** `tests/integration/trigger/test_group_invariant_trigger.py` builds
five modules, groups them, builds again, and diffs the resulting scene — node names, hierarchy,
connections. Grouping and ungrouping between builds changes nothing.

## 9. Lifecycle edges

- Removing a member down to one **dissolves** the group. A group of one is a module.
- Deleting a group asks *Ungroup* or *Delete members*, through `Feedback`.
- Deleting a member removes it from `members` first, then deletes.
- Joining enforces same type and same side, and refuses a module that is already in a group.
- All four structural edits — create, join, leave, dissolve — go on the session undo stack, per
  the existing rule that structural edits undo with Trigger's Ctrl+Z while moving a guide undoes
  with Maya's.

## 10. Tests

| File | Covers |
|------|--------|
| `tests/unit/test_module_group_trigger.py` | The pure object: join, leave, dissolve, homogeneity refusals, schema 3 round-trip, `node_ids()` projection, shared-value derivation |
| `tests/ui/test_group_tabs.py` | The tab bar, the `Common`/per-tab split, reflow on divergence, `[+]`, rename, reorder |
| `tests/ui/test_graph_groups.py` | Collapse and expand, the port union, input fan-in, the output member picker |
| `tests/integration/trigger/test_group_invariant_trigger.py` | Grouped vs ungrouped build diff |
| `tests/unit/test_import_boundaries.py` | Added case: the build path never reads `document.groups` |

## 11. Files touched

| File | Change |
|------|--------|
| `core/guide_document.py` | `ModuleGroup`, `GuideDocument.groups`, `group()`, `node_ids()`, schema 3 |
| `guides/scene.py` | `group`, `ungroup`, `join`, `leave`, `mirror_group` |
| `ui/graph/items.py` | `FrameSpec.ref_id` → `frame_id` |
| `ui/graph/scene.py` | Signals carry a frame id |
| `ui/graph/view.py` | Frames may come from groups; input fan-in; output member picker |
| `ui/designer/properties.py` | The `Common`/per-tab split and its derivation |
| `ui/designer/window.py` | The tab bar and its verbs |
| `ui/designer/commands.py` | Group, ungroup, mirror group |
| `ui/model.py` | Group parent rows in the tree |
| `shared/ui/check_list.py` | Group parent rows in the picker |
| `guides/exchange.py` | The optional `.trg` `groups` section |
