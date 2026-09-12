# Guide Kinds: a guide says what it is, and the framework decides how it looks

**Date:** 2026-09-12
**Status:** implemented
**Corrected during implementation:** §4.4's claim that the `.trg` needs no change, and
§11's "the kind is not stored in the file", are both **withdrawn**. A pivot preset guide
belongs to no `GuideLayout` -- its role comes from a settings table -- so there is nothing to
ask on the way back in, and it would have re-imported as a joint. The record carries a `kind`
field; `color` and `radius` become advisory. Export needed the same branch: a transform has no
`jointOrient` and no `radius`. The *document* schema is unchanged, as §4.4 also says.
**Amends:** `2026-09-07-movable-pivots-and-pivot-presets-design.md` — preset guides stop being
joints styled as markers and become reference guides; they fan along the anchor's chain
direction instead of stacking on it. The declaration, the anchor addressing and the switch
compensation all stand.
`2026-09-05-draw-and-sync-separation-design.md` — Draw now renders a guide according to its
kind, and a reference guide is a `transform`, not a `joint`. Draw and Sync keep their
directions and neither gains a job.

---

## 1. Why

Draw an `arm` and look at what the rigger is given. Five joints in a T-pose, all but one the
same size, none of them labelled, and a bone streaking from the collar out past the hand to a
guide called `neutral` that looks exactly like a link in the chain and is not one. Ask for
pivot presets and three more joints appear stacked on top of each other at the wrist, occupying
one pixel.

Every one of those is a symptom of the same absence: **a guide's appearance has no declaration
anywhere.**

```python
collar   = guides.joint("collar",   (2 * mult, 0, 0), radius=1.5)
shoulder = guides.joint("shoulder", (5 * mult, 0, 0), parent=collar)
...
guides.joint("neutral", (18 * mult, 0, 0), parent=collar, radius=0.8)
```

`radius=1.5` is not an aesthetic preference. It is the sentence *"this is the module root"*,
written in the wrong language — in a number, at a call site, where nothing can read it and no
other module is obliged to agree. `radius=0.8` on `neutral` is the sentence *"this is not
really part of the chain"*, written in a language too weak to say it: the guide still draws a
bone, still looks like a joint, still invites the rigger to treat it as one.

`marker=True` on a pivot preset is the same sentence again, said a third way, and it does not
work — §4 shows the measurement.

So the numbers drift. `base` says `radius=2.0` for its root where `arm` says `1.5`. `twist`
says `1.5` for its base and `0.5` for its twist guides. Nobody is wrong, because there is
nothing to be wrong about.

### 1.1 What the module author was never choosing

The temptation is to give module authors a display API — radius, colour, shape, label, per
role — and let them express themselves. That is the wrong trade, and it is worth being precise
about why.

A module author has no opinion about how big a sphere should be. They have an opinion about
**what the guide is for**. Every existing magic number is an encoding of such an opinion, and
the encoding is lossy. Handing authors a richer display vocabulary does not give them something
they wanted; it hands them a decision they would rather not make, and guarantees that the sixth
module re-litigates what the first five settled.

This is the Animator-Opinion Rule pointed at a different audience. The rule says tik.maya owns
mechanism and tik.trigger owns policy, because an animator might have an opinion about policy.
The same test applied here: **a rigger has an opinion about what a guide is; nobody has an
opinion about its radius.** So the module declares the former and the framework derives the
latter.

## 2. The vocabulary

A guide has a **kind**. There are four, and the kind is always a statement about the guide's
role in the rig — never about its look.

| Kind | Meaning | How it is known |
|---|---|---|
| `ROOT` | The module's anchor; everything else hangs off it | **Derived** — the first guide a copy draws |
| `JOINT` | A joint in the rig. Move it, a bone moves | **Derived** — the default for everything else |
| `REFERENCE` | Only its *position* is read. Nothing in the rig is shaped like it | **Declared** |
| `DRIVEN` | A real rig joint, but the module places it, not the rigger | **Declared** |

The look is a pure function of the kind:

| Kind | Node | Size | Bone | Label |
|---|---|---|---|---|
| `ROOT` | `joint` | radius 1.5 | yes | native `drawLabel` |
| `JOINT` | `joint` | radius 1.0 | yes | native `drawLabel` |
| `REFERENCE` | `transform` + locator shape | localScale 0.6 | **none, in or out** | annotation |
| `DRIVEN` | `joint` | radius 0.5 | yes | native `drawLabel` |

Colour follows the same rule — a consequence of the kind, never a choice. `ROOT` and `JOINT`
take the existing `SIDE_COLORS` entry for the module's side. `REFERENCE` takes `MARKER_COLOR`
(14, green), which is what pivot markers already use, so "not a chain link" reads as one class
whatever module drew it. `DRIVEN` takes the side colour at a dimmed index (`overrideColor` one
step darker), so a railed guide reads as subordinate to the chain it sits in rather than as a
different species.

`ROOT` at 1.5 against `JOINT` at 1.0 reproduces the arm's present collar-versus-rest
relationship exactly — the difference the rigger already relies on — without the arm naming a
number. `base` drops from 2.0 to 1.5 and becomes consistent with every other root.

### 2.0b Chains, and modules that are not one

`drawStyle` is a look, so no module names it. What a module names is whether **a bone runs
between its guides**:

```python
# twist.py -- the rails are siblings on a segment, not links in it
guides = GuideLayout("base", "end", multi="twist", driven=("twist",), chain=False)

# ribbon.py -- the two ends span a surface
guides = GuideLayout("start", "end", chain=False)
```

`chain` defaults True, so `arm`, `fkchain`, `base` and `control` say nothing and keep their
bones. False renders every joint guide of that module with Maya's `drawStyle = 3` ("Joint"):
the marker, and no bones to any child.

The measurement that makes it worth having: Maya draws one bone from a joint to *every* child,
so `twist`'s base -- which parents its `end` and all N rails -- drew N+1 bones to collinear
points, stacked into a single unreadable smear. It is also a lie, because no bone joins those
guides in the rig.

Applied module-wide rather than per role. A leaf draws no bones anyway, so targeting only the
parents behaves identically, and per-role would raise a question ("which of my guides draw
bones?") that no module author has an opinion about.

### 2.1 The declaration

Two new keyword arguments on `GuideLayout`, both tuples of roles:

```python
# arm.py
guides = GuideLayout("collar", "shoulder", "elbow", "hand", reference=("neutral",))

# twist.py
guides = GuideLayout("base", "end", multi="twist", driven=("twist",))

# fkchain.py, control.py, ribbon.py, base.py  -- unchanged
```

`GuideLayout` gains `kind_for(role) -> Kind`. A role named in both `reference` and `driven`, or
named in either but absent from the layout, is a `ValueError` at class-definition time.

### 2.2 Why derivation covers the rest

`GuideDraft` already watches the structure `draw_guides` builds — it tracks `self.root` per
copy, and it resolves every `parent=` argument. Which guide is the root is therefore already
known, exactly, at the moment it is created; the module does not need to restate it, and
restating it would open the possibility of disagreeing with it.

`REFERENCE` and `DRIVEN` are the two facts structure genuinely cannot reveal. Whether a guide's
position is *read* or *built from* lives inside `build()`, which the framework cannot inspect;
whether a guide is railed is decided in `wire_guides`, which runs after Draw. Both are
declared, and the declaration is one word in one place.

The alternative — inferring `REFERENCE` by guessing which guides `build()` only reads — was
rejected. It is a guess about code the framework cannot see, it cannot be verified, and it
would change a module's appearance silently when its `build()` changed.

## 3. What `GuideDraft.joint` loses

```python
def joint(self, role, position, *, index=0, parent=None) -> tm.Transform:
```

`radius` and `marker` are gone. No call site anywhere picks a number or a shape any more, which
is what makes consistency structural rather than conventional. A module author who needs a look
that does not exist adds a kind to the vocabulary — one place, every module benefits — rather
than a number in their own file.

The return type widens to `tm.Transform`, since a reference guide is not a joint. Every present
caller either ignores the return or uses it as a `parent=`, both of which are unaffected.

## 4. Reference guides stop being joints

### 4.1 The measurements

Three facts, measured in Maya 2024 rather than recalled, because the whole section rests on
them.

**The bone belongs to the parent.** `drawStyle = None` on a *child* joint changes nothing about
the bone leading into it. On the *parent* it removes that joint's bones — **all of them**. So
hiding the `collar → neutral` bone by `drawStyle` costs the `collar → shoulder` bone too. There
is no per-child control.

**Transforms are transparent to bone drawing.** Inserting a plain transform between the collar
and the neutral joint does *not* break the bone. Maya walks through non-joint transforms to
find descendant joints and draws to them anyway. Re-parenting the neutral out of the collar's
subtree entirely is what removes the bone — which would require a constraint to keep it
following its anchor.

**A non-joint child of a joint draws no bone at all.** A locator parented under the collar, ten
units away, draws nothing but its own cross.

The third fact is the design. A reference guide is a `transform` carrying a locator shape,
parented normally under its anchor: no bone, no constraint, no `drawStyle` trickery, and it
still follows its anchor and still drags freely.

### 4.2 What this deletes

`_style_as_marker`, the `marker` parameter through `GuideDraft.joint` and `create_guide_joint`,
and the `joint["drawStyle"].value = 2` line all go. The pivot-preset marker stops being a joint
pretending not to be one and becomes the thing it was describing.

### 4.3 What it costs

`create_guide_joint` is renamed `create_guide_node` and branches on kind. Beyond that, the cost
is five filters:

| Site | Change |
|---|---|
| `guides/nodes.py:172` `find_by_meta(node_type="joint")` | to `"transform"` |
| `guides/nodes.py:281` `cmds.ls(type="joint")` | to `"transform"` |
| `guides/nodes.py:362` selection scan | to `"transform"` |
| `guides/nodes.py:363` `tm.Joint(name)` | to `tm.resolve(name)` |
| `guides/snapshot.py:48` `cmds.ls(type="joint")` | to `"transform"` |

The comment in `_style_as_marker` presents these as a wall — *"It stays a joint so `guide_nodes`,
`scan`, `snapshot` and the selection sync — all of which filter `type="joint"` — keep working
on it unchanged"*. They are not. `joint` inherits from `transform` in Maya's node hierarchy
(`containerBase -> entity -> dagNode -> transform -> joint`), so each is a **widening** that
cannot lose a node it used to find. And every one of the five already re-checks
`KIND == GUIDE` on the next line: the joint filter was a performance narrowing, never a
correctness one.

`guides/exchange.py` branches on kind when rebuilding guides from a `.trg`, reading the kind
from the module class it already looks up through `registry.get_module`.

### 4.4 What does not change

**The document schema.** `GuidePose` is `(role, index, position, rotation, rotate_order)`; a
transform has all four, and `apply_poses` already writes through `cmds.xform`. No schema bump,
no migration.

**Capture and Sync.** Both read world poses through `cmds.xform` and key on the `trg_*` meta,
neither of which cares what node type carries them.

**Reconcile.** Its five states are unchanged. A reference guide that is missing, unexpected,
parented wrong or drifted reports exactly as before.

## 5. Labels

`drawLabel` is a joint attribute, so the two node types need two mechanisms. The module declares
nothing either way.

| Kind | Mechanism |
|---|---|
| `ROOT`, `JOINT`, `DRIVEN` | `drawLabel = 1`, `type = 18` (Other), `otherType = <label text>`, `side` from the module's side |
| `REFERENCE` | An `annotation` shape parented **at** the guide, at zero offset |

**The label text is the qualified role, not the bare one.** A guide's tag role is already
qualified per copy (`c1_root`) while its node is named after the copy (`L_thumb_root_guide`);
the label follows the *name*, not the tag, so a five-copy `fingers` reads `index_root`,
`thumb_root`, and so on. A one-copy module has an empty slug and reads exactly as it does
today — `collar`, `shoulder` — so nothing regresses for the common case. Labelling every
finger `root` would be worse than no label at all.

Three details, all measured:

1. **Maya appends the side itself for joint labels** — the viewport reads `collar (L)` from
   `otherType = "collar"` plus `side = 1`. It does *not* do this for annotations, so the
   reference label's text is assembled by us as `"neutral (L)"`.
2. **The annotation transform sits at zero offset on the guide**, which collapses its leader
   line to a stub arrow pointing at the locator rather than a line across the scene. Anything
   else would reintroduce the streak this design exists to remove.
3. **The annotation must be unselectable.** `overrideEnabled = 1`, `overrideDisplayType = 2`
   leaves it visible and unpickable; without it, riggers grab the label instead of the guide.
   Its `overrideColor` is set to the marker colour, so a reference guide reads as its own class
   at a glance.

The annotation transform needs **no scan exclusion**. It carries no `trg_kind` meta, and every
scan site gates on `KIND == GUIDE`, so `guide_nodes`, `find_instances`, `snapshot` and the
selection sync ignore it for free.

The label is **derived, never serialized**. Draw rebuilds it; the `.tr` and the `.trg` carry
nothing about it.

Labels collide on dense modules — a five-copy `fingers`, a twenty-segment `fkchain`. That is
what §9 is for.

## 6. The `DRIVEN` kind

`twist` rails its twist guides: `wire_guides` drives them off a `multiplyDivide` and locks
every channel, so the rigger authors their position through the `position` attribute and can
never drag them. They are real rig joints — they become twist bones — but they are the module's
to place, not the rigger's.

Derivation alone would render them as ordinary `JOINT`s at radius 1.0, losing a distinction
`twist` had deliberately built with `radius=0.5`, and inviting a rigger to try dragging a locked
guide. `DRIVEN` restores it as a declaration: smaller, dimmed, still boned so the twist chain
still reads as a chain.

Deriving it from the locked channels instead was rejected: locking happens in `wire_guides`,
which runs *after* Draw, so the look would need a second pass — and it would fire on any module
that locked a channel for an unrelated reason.

`twist` is the only module using `DRIVEN` today. It earns its place because it is a statement
about the rig ("the module places this"), not about a look, and because the alternative is a
silent regression.

## 7. The A-pose

The collar stays put — a clavicle is roughly horizontal in every pose. The A starts at the
shoulder: `shoulder -> elbow -> hand` rotates 45 degrees down about world Z.

| Guide | Today | A-pose |
|---|---|---|
| `collar` | `(2m, 0, 0)` | unchanged |
| `shoulder` | `(5m, 0, 0)` | unchanged |
| `elbow` | `(9m, 0, -1)` | `(7.8m, -2.8, -1)` |
| `hand` | `(14m, 0, 0)` | `(11.4m, -6.4, 0)` |
| `neutral` | `(18m, 0, 0)` | `(15.2m, -9.0, 0)` |

Two consequences worth recording. The elbow's `-1` in Z survives untouched, because a rotation
about Z does not change Z — the pole direction stays behind the arm for free, and no
compensation is needed. And `neutral` stays on the collar-to-hand ray, extended past the hand,
which keeps its docstring true (*"where the wrist sits when the collar is at rest"*) instead of
leaving it quietly describing a pose the module no longer draws.

**The neutral is derived from the hand, not typed as a triple.** `build_reach` aims a frame
from the collar at the neutral and measures the wrist against it, so at the guide pose that
angle must be *exactly* zero or no scalar value leaves the bind pose alone. Rounding the
A-pose to one decimal left the neutral 0.006 off the collar-to-hand ray -- 60x the tolerance
`test_bind_pose_is_exact_with_the_automation_full_on` allows. `NEUTRAL_REACH` is the multiple
of the collar-to-hand distance it sits at. The comment claiming "the
default guide arm is already a T-pose, so the default neutral is the T-pose" is replaced.

No setting, no angle field, no rig-wide rest-pose concept. The guides are draggable; a field
that sets an angle you could equally drag is a control nobody needs, and it becomes a lie the
moment the rigger drags one.

## 8. The preset fan

`Module._draw_pivot_guides` stacks every preset marker on its anchor, with a comment defending
it: *"an unplaced preset should look unplaced, and moving the anchor carries its presets
along."* The second half stays true — parenting is unchanged. The first half loses: three
markers in one pixel are not selectable, and unselectable is worse than unplaced.

Marker *i* is placed at:

```
anchor + direction * (i + 1) * step
```

`direction` is the anchor's incoming chain direction (parent to anchor), which the draft already
holds. `step` is 25% of that bone's length. When the anchor is a root and has no incoming bone,
`direction` falls back to the module's aim axis (`side_mult` along X) and `step` to a fixed
fraction of the root radius.

For the arm's hand, the incoming direction is elbow to hand, which is the hand's forward axis —
so the fan lands along the direction a foot or hand roll actually travels, and reads as
meaningful rather than arbitrary.

That only holds if the rows are in anatomical order, and today's default is not — `arm` ships
`("tip", "ball", "wrist")`, which would fan the wrist furthest from the wrist. The new default:

```python
pivot_presets = Module.pivot_presets.with_default(
    [{"control": "ik", "label": label} for label in ("wrist", "ball", "tip")]
)
```

Proximal to distal, which is the order the fan walks.

## 9. The Labels toggle, and the preferences boundary

Labels are drawn unconditionally by Draw. Turning them off is a **view** operation, and it has
to be, because of an existing rule: `tests/unit/test_import_boundaries.py` forbids
`trigger/guides` from importing the preferences packages at all. A "show labels" preference
cannot be read at draw time, and should not be — a preference can never change what Draw
renders.

So the toggle lives in the Guide Designer's action bar, in `trigger/ui`, which *may* read
preferences. Its default is a preference; its effect is a scene operation over the guides that
are currently drawn:

```
Designer bar:   [ Draw ]  [ Sync ]   ...   [ Labels ]
```

One function, two node kinds: flip `drawLabel` on joint guides, flip `visibility` on annotation
transforms.

Rejected: a per-module label opt-out. That is the module author guessing on the rigger's behalf
about viewport clutter in a scene they have never seen — exactly the kind of opinion §1.1 says
they should not be holding.

## 10. Blast radius

| File | Change |
|---|---|
| `core/manifest.py` | `GuideLayout` takes `reference=` / `driven=`; `kind_for(role)`; validation |
| `core/module.py` | `_draw_pivot_guides` fans instead of stacking; `marker=True` dropped |
| `maya/rig.py` | `GuideDraft.joint()` loses `radius` / `marker`; resolves the kind per role |
| `guides/nodes.py` | `create_guide_joint` to `create_guide_node`; kind dispatch; labels; three filter widenings and one `resolve`; `_style_as_marker` deleted |
| `guides/snapshot.py` | one filter widening |
| `guides/exchange.py` | `.trg` import branches on kind |
| `modules/arm/arm.py` | A-pose positions; `reference=("neutral",)`; preset rows reordered; four magic numbers removed |
| `modules/twist/twist.py` | `driven=("twist",)`; three magic numbers removed |
| `modules/base/base.py` | `radius=2.0` removed |
| `modules/control`, `fkchain`, `ribbon` | **nothing** — and they gain labels and grading |
| `trigger/ui` | the `Labels` toggle in the Designer's action bar |

That last row is the test of the design: three modules change nothing and improve anyway,
because none of them was ever making a choice about how their guides looked.

## 11. Testing

**New, pure (`tests/unit/test_guide_kinds_trigger.py`)** — the first guide a copy draws is
`ROOT` and the rest are `JOINT`; `reference=` and `driven=` override that; a role in both, or
in neither the layout nor the tuple, raises; a copy's second slug gets its own `ROOT`.

**New, Maya (`tests/integration/trigger/test_guide_kinds_trigger.py`)** — a reference guide is a
`transform` with a locator shape and is not of type `joint`; it is a child of its anchor; its
annotation exists, is unselectable, and carries the side-suffixed text; joint guides carry
`drawLabel` with `otherType` set to the bare role; radii match the kind table; no two pivot
preset markers share a world position.

**Extended** — `test_guides_trigger.py`: a `.trg` round-trip rebuilds a reference guide as a
locator and a driven guide as a joint. `test_draw_sync_trigger.py`: Sync captures a reference
guide's pose, and still creates, deletes and moves nothing. `test_pivot_build_trigger.py`: the
fan does not disturb which pivots get built. `tests/ui/`: the `Labels` toggle.

**Unchanged and load-bearing** — `test_module_ground_rules.py` builds every module standalone
through the change; `test_import_boundaries.py` is untouched, since the toggle lives in
`trigger/ui`.

## 12. What this does not do

No schema bump and no migration — the document already stores everything a transform can carry,
and there are no sessions to keep compatible.

No per-role display attributes, no colour API, no user-facing guide-appearance settings. A look
that does not exist is added to the vocabulary in §2, deliberately, once, for everyone.

No leg module, and therefore no rig-wide rest-pose concept. When a second module wants to draw
against a shared rest pose, that is the moment to design one — not before.
