# Module Copies: one module, N repeats of itself

**Date:** 2026-09-10
**Status:** implemented
**Supersedes:** `2026-09-10-module-groups-and-tabs-design.md` **in full.** That design was
implemented, tried, and withdrawn; §1 below says exactly what failed and why. Its two
incidental bug fixes survive (§11). Nothing else in it stands.

---

## 1. Why the group model failed

The problem is unchanged: a hand is five `fkchain` modules, two hands are ten, and with toes
the graph is thirty nodes that differ in one word each. The graph stops being a picture of the
rig and becomes a picture of the repetition in it.

The previous design answered this with a **group**: five real module instances, drawn as one
node, edited through one panel with a tab per member. It shipped, and it did not work. Four
complaints, one cause:

- The tree and the graph disagreed about what existed.
- Adding a tab, clicking into the graph, and clicking back left the panel empty.
- The tree showed group rows with modules nested under them, which is not what nesting means
  there.
- **Draw Selected** did nothing, "because technically they are not selected".

That last one names the cause. The Guide Designer's selection *is* the tree selection —
`selected_handles()` reads `tree.selectedItems()` (`ui/designer/window.py:505`) and every verb
in the app is built on it. The tab bar introduced a second notion of "current" that nothing
outside the properties panel knew about. Draw, the action bar, mirror and the graph all kept
reading the real selection and got a different answer.

The tree row was the same mistake in another form. A parent in that tree means *the primary
input's producer*. A group row put something else entirely in the same column, so the tree was
making two different claims with one piece of visual grammar.

Neither is a bug to be fixed. A group is a thing you select, but it is not a module, so every
verb in the application had to grow a special case — and the previous work grew only some of
them. **The lesson is the governing rule of this document: there must be exactly one kind of
selectable thing, and it must be the module.**

## 2. Decision

**Multiplicity belongs inside a module, not between modules. A module has a list of copies of
itself, the way `fkchain` already has a number of segments.**

One `ModuleEntry`, one uuid, one tree row, one graph node, one entry in
`tree.selectedItems()`. Every complaint in §1 becomes impossible rather than fixed, because
there is nothing new for Draw, mirror, build scope or the tree to know about.

Two consequences carry the design:

**The author writes one copy; the framework repeats it.** For each copy the builder makes a
per-copy view of the module — same class, settings resolved for that copy, guides scoped to
that copy, a `rig` that names after that copy — and calls the ordinary `draw_guides(guides)`
and `build(rig)`. `FkChain.build()` does not change by a line, and neither does any other
module. Repetition lands on every module, the ones that ship and the ones written later, for
free.

**`per_copy=True` declares which settings vary, and only that.** A field says once, in the
module, whether it belongs to a copy or to the set:

```python
class FkChain(Module):
    segments        = IntField(3, min=1, max=50, per_copy=True)
    spacing         = FloatField(5.0, per_copy=True)
    controller_size = FloatField(2.0)                    # one value for the set
```

A per-copy field always renders inside the tabs, even when every copy holds the same value. An
ordinary field always renders above them. The panel never infers and never reflows.

### 2.1 What was rejected, and a correction

**Deriving common-versus-per-copy from the values.** The previous design compared members and
put the fields they agreed on above the tabs. It is what the panel did, and it is wrong for a
reason worth recording: `segments` is not shared because five fingers happen to hold 4 today.
A chain's length is a property of that chain. Asked who decided `segments` was common, the
honest answer was *nobody, the panel inferred it from values* — and an inference that reshuffles
the form as the rigger types is a poor substitute for a fact the module author already knows.

**Groups of separate modules, with the selection fixed.** Making the tab bar drive the tree
selection and dropping the group row would have addressed §1's symptoms. It keeps two
representations of one thing, so every verb still has to decide whether "the selection" means
the tab, the group, or the tree. That decision is what generated the bugs.

**A correction to the superseded spec.** Its §2.1 rejected this design because "every
uuid-keyed assumption in the system — the guide document, `reconcile`, the `.trg`,
`expand_guides`, the shape override table, anim spaces, pivot presets, `build_scope`,
`PublishSet` — would grow a copy axis". That was wrong, and the mistake is instructive.
`output_names`, `control_names`, `control_shape_defaults` and `control_orient_defaults` are
**already** settings-driven and already return N names — `fkchain` returns one output and one
control per segment today. Roles and control names are strings the document never inspects, so
a copy index can live inside them. There is no axis to add.

The estimate was right about exactly one thing: the *guide key*. `.pair`/`.pairs` has 13 uses
across 7 files, and `tags.ROLE`/`tags.INDEX` are read in 6 more, including `maya/build.py`,
`maya/rig.py` and the animator-facing `anim/context.py`. Adding a third component there is
genuinely invasive, which is why §4 puts the copy in the role name instead.

## 3. The copy list

`copies` is a field on `Module`, hidden from the generated form because the tab bar is its
editor — the same arrangement `filterable` already uses for the `<name>_only_selected` field it
injects. It is deliberately *not* `last=True` like the base tables beside it: `last` decides
where a field renders, and a hidden field renders nowhere, so marking it would only have pushed
the three visible tables out of the trailing group. Each row is one copy: its identity, its name, and its per-copy values.

```python
settings = {
    "controller_size": 2.0,                                       # ordinary field
    "copies": [
        {"slug": "",   "name": "index", "segments": 4, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 3, "spacing": 5.0},
    ],
}
```

The list **is** the count. `[+]` appends, closing a tab removes one; there is no separate
number to keep in step with it.

`[+]` **duplicates the current copy** — its per-copy values and its guide poses — rather than
seeding from the field defaults. A fifth finger wants the fourth finger's settings, not the
module's. The new copy's guides therefore land exactly on the copy they were made from, and
the rigger drags them into place: the same answer as the pivot-preset rule that an unplaced
thing should look unplaced, and the same answer the superseded design reached for `[+]`.

A per-copy view is `{**settings, **row}`, which is the whole trick: inside `build()`,
`self.segments` is a plain int, and the module author never learns that copies exist.

Every row carries an explicit value for every per-copy field. There is no inheritance and no
sparse override, because a per-copy field has no module-level value to inherit from -- it lives
in the tabs by declaration, so there is nothing above to revert to.

**A one-copy module stores no list at all.** Found in implementation, and the right rule rather
than a shortcut. Writing a per-copy value used to materialise a single-row `copies` list, which
stranded the module-level field: `handle.segments` read 2 while the rig built 4, and every
existing reader of `settings["segments"]` was quietly wrong. So the list appears only from the
second copy onward, and removing that copy returns the module to exactly its prior state —
which is also what keeps the scripting API (`handle.segments = 4`) meaning what it always meant.
The implicit row is seeded from the module's *current* value, never the field default, and that
is the whole of the migration: a `.tr` written before copies existed is already a valid one-copy
module.

## 4. Slugs, roles, and why the first one is empty

A copy has two identities and they must not be the same thing:

- a **slug**, minted at creation and never reused, which keys its guides;
- a **name**, edited freely by the rigger, which reaches the rig (§5).

Guide roles are `<slug>_<role>`. Keying on the slug is what lets a rigger rename `finger1` to
`thumb`, or drag a tab, without orphaning a pose — the same trap the pivot-preset spec called
out when it keyed preset guides by label rather than by row index, avoided the same way. The
slug never appears in the scene: guide joints are named from the copy *name*, and reconcile
matches on `tags.ROLE`, not on names.

**The first copy's slug is the empty string.** Its roles are therefore `root` and `segment`,
exactly what every module writes today, and the second copy's are `c1_root` and `c1_segment`.
This is not symmetry for its own sake — it is what makes the feature free:

- every existing `.tr` is already a valid one-copy module, so there is no migration and no
  guide-document schema bump;
- adding a second copy cannot disturb the guides of the first;
- a one-copy module is byte-identical to today at every layer, which §10 makes a test.

Nothing requires the empty slug to exist. Deleting the first copy leaves the others with their
prefixes, and that is fine.

## 5. Names in the rig

**The copy name is the naming unit; the module name never reaches the rig.** A module called
`fingers` with copies `index`, `middle`, `thumb` builds `L_index_fk0`, `L_middle_fk0`,
`L_thumb_fk0` — precisely what five separate `fkchain` modules build today. An existing rig
rebuilt this way keeps every control name, so animation, published caches and anything
referencing a control name survive.

`fingers` is a label: the graph node, the tree row and the panel header. It is not a prefix.

Two rules follow. A copy name must be unique among the module's copies, and — because the
module name is absent from the rig — unique against other modules of the same side, which the
existing `unique_name` check is extended to cover. And when a module has exactly one copy whose
name is blank, the module's own name is used, which is what keeps today's rigs unchanged.

## 6. Expansion, in the base class

Everything below is `Module` and the builder. No module author writes any of it.

| What | Becomes |
|------|---------|
| `output_names(settings)` | the author's names, qualified per copy: `index_end`, `thumb_end` |
| `control_names(settings)` | likewise: `index_fk0`, `thumb_fk0` |
| `control_shape_defaults` / `control_orient_defaults` | likewise, keyed by the qualified names |
| `expected_guides()` | the layout expanded once per copy, roles prefixed by slug |
| `validate()` | accepts the expanded roles |
| `expand_guides(...)` | takes the expanded pairs rather than layout-plus-count |

`expand_guides` (`core/guide_document.py:434`) is the only signature change, and it has four
call sites: `guides/exchange.py:239` and `guides/scene.py` at 324, 499 and 797.

Implementation added two more pieces. A per-copy view is handed its own *slice* of the
control-keyed tables, de-qualified, or it re-qualifies an already qualified name and derives
roles like `c1_pivot_c1_fk0_heel`. And `report.rigs` holds a `ModuleBuild` — a `ModuleRig` per
copy plus the merged output map — which delegates every other attribute to the first copy, so a
one-copy module behaves exactly as it did when that slot held a `ModuleRig` outright and no
caller had to learn the type.

**The build loop.** `Builder` iterates the copies of each module and, per copy, constructs the
per-copy view and a `rig` carrying that copy's name, then calls `build(rig)`. Copies of one
module build in list order, and a module's copies build together — a copy is not independently
schedulable and nothing outside the module can wire to "copy 3" as a unit.

## 7. The panel

```
name [fingers]   side [L]
root ◀── L_hand.hand
┌─ Module ────────────────────────────┐
│ controller_size  [2.0]              │
└─────────────────────────────────────┘
[index][middle][ring][pinky][thumb][+]
┌─────────────────────────────────────┐
│ name      [thumb]                   │
│ segments  [3]                       │
│ spacing   [5.0]                     │
└─────────────────────────────────────┘
```

Ordinary fields above, per-copy fields inside, both by declaration. Double-click a tab to
rename, drag to reorder, `[+]` to duplicate the current copy (§3), right-click to remove. With one copy the bar is a
single tab and a `[+]`, and the panel reads as it does today.

**The tab bar edits a settings field. It is not a selection surface.** Switching tabs must not
change `_current`, must not touch the tree, and must leave `selected_handles()` untouched. That
is the rule §1 was written to enforce, and §10 tests it directly.

## 8. What stays module-level

The module name and side; the input connections; and the three tables the base class
declares — `anim_spaces`, `pivot_presets` and `control_shape_overrides`.

Those three are keyed by control name, and control names are already copy-qualified (§6), so
one module-level table addresses any copy's control without becoming per-copy itself. A space
on `thumb_fk0` and a shape override on `index_fk2` are ordinary rows.

Inputs are shared deliberately. Five fingers attach to one hand; that is the common case and
the whole reason the graph collapses. A copy that genuinely needs its own parent is a separate
module, which remains available and is the right answer for it.

## 9. What this gives up

Five `fkchain` modules that already exist cannot be folded into one node. The unit is the
module, so a rigger would add copies to one and delete the other four, losing their guide
poses.

A **Merge into copies** command — take N same-type modules, re-key each one's guide records
under a fresh slug, and fold them into one module — is straightforward, and is deliberately not
in this design. It is a migration convenience for rigs built before copies existed, and it
should be built once the copy model has been used in anger, not before.

## 10. Proof

Two integration tests carry the design, and each one makes a decision above falsifiable:

**A one-copy module builds what it builds today**, node for node, name for name. This is §4's
empty slug and §5's blank-name fallback, and it is what licenses "no migration, no schema
bump".

**A five-copy `fkchain` builds what five separate `fkchain` modules build**, node for node.
This is §5's naming decision, and it is the promise that an existing rig can be rebuilt this
way without renaming a single control.

Plus unit tests for the per-copy view, role expansion, manifest qualification, copy-name
uniqueness, and an existing `.tr` loading as a one-copy module unchanged.

And one UI test that is really an assertion about §1: **switching tabs does not change
`selected_handles()`**, and Draw Selected acts on the module while any tab is showing.

## 11. Disposition of the group work

Nineteen of the twenty commits serve the group model and come out as a single revert of the
range — history intact, nothing rewritten. Two were independent bug fixes and are re-applied
fresh, because neither has anything to do with groups:

- **`StubScene.find_instances` honouring its `scope`.** It ignored it and returned every
  instance, so `GuideHandle.instance` — which asks for one id and takes `found[0]` — handed
  back the first module in the scene for *every* handle. Any Qt test reading `handle.instance`
  against more than one module was asserting about the wrong module. The bug predates this
  feature.
- **`Feedback.ask_choice` going through the `set_handler` seam.** It was the one dialog a
  headless test could not answer, a hole in the one-dialog-surface guarantee.

Everything else goes: `core/module_group.py`, `GuideDocument.module_groups`, the `GuideScene`
group verbs, the graph frames for groups, the tab bar as a selection surface, the tree group
rows, the `.trg` `module_groups` section. So do four things that existed only to serve them —
the `FrameSpec.ref_id` → `frame_id` rename, `worst_state`, `FormBuilder.mark_varying`, and the
picker's `set_groups`/`tick_group`. Five fingers are one entry in the kinematics picker now, so
the picker needs nothing.

## 12. Files touched

| File | Change |
|------|--------|
| `core/fields.py` | `per_copy` on `Field` |
| `core/module.py` | the `copies` field, the per-copy view, manifest qualification, `expected_guides`, `validate` |
| `core/guide_document.py` | `expand_guides` takes pairs |
| `guides/scene.py` | copy-aware `expand_guides` calls; `unique_name` across copies |
| `guides/exchange.py` | copy-aware `expand_guides` call |
| `maya/build.py` | the per-copy build loop |
| `maya/rig.py` | the copy name as the naming unit |
| `shared/ui/fields.py` | render per-copy fields into the tab form |
| `ui/designer/window.py` | the tab bar over `copies` |
| `ui/designer/properties.py` | writes go to the current copy's row |

## 13. Tests

| File | Covers |
|------|--------|
| `tests/unit/test_module_copies_trigger.py` | the copy list, the per-copy view, slugs, role expansion, manifest qualification, name uniqueness, `[+]` duplicating values and poses |
| `tests/unit/test_guide_document_trigger.py` | `expand_guides` over pairs; an existing `.tr` loads as one copy |
| `tests/integration/trigger/test_module_copies_trigger.py` | one copy builds today's rig; five copies build what five modules build |
| `tests/ui/test_copy_tabs.py` | the tab bar edits settings and never touches `selected_handles()` |
