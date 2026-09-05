# The rig scaffold and the two master controls

**Date:** 2026-09-05
**Status:** Design approved, ready for an implementation plan
**Area:** `tik.trigger` — Maya layer (build, runner, rig object), actions,
module ground rules

## 1. The problem

The previous Trigger had a `master` action: a silent, name-based scaffold that
Kinematics ran whenever `trigger_grp` was missing. It made three groups by
hard-coded name, a `pref_cont` with four attributes, and daisy-chained those
attributes into every module's scale group. It worked, but it was implicit
(nowhere in the pipeline could a TD see it run), it was name-only (an imported
asset that happened to ship a `rig_grp` was silently the rig), and every
rig-wide switch landed on one control, which does not scale once modules start
adding their own.

tik.trigger today has less than that. `ensure_rig_root(rig_name)` creates a
bare, tagged `<rig_name>_rig` transform, and only the Kinematics action calls
it, with the name coming from that action's own `rig_name` field. Two
Kinematics actions with different names produce two roots. No other action
knows the root exists: Import Model drops geometry at world level. Every module
limb group already carries `controlVisibility`, `rigVisibility` and
`bindVisibility` booleans driving its four groups, but nothing above the
module drives them. Controllers are tagged with kind, instance, role and
mirror; there is no notion of a control's tier.

This spec gives every rig one scaffold, ensured before any build or action
runs, and two persistent controls: **preferences** for rig-wide switches and
**visibilities** for per-module control tiers.

## 2. Decisions

1. **One rig per scene, and it has no name.** The scaffold is addressed by
   fixed names and confirmed by tags. The `rig_name` field on Kinematics and
   the `rig_name` argument on `Builder.build` are removed. There is no
   backwards compatibility to keep: old keys are simply gone.
2. **The scaffold is ensured, never placed.** It is not an action in the
   pipeline and it is not in the session document. The runner ensures it
   before every step; the builder ensures it at the start of every build.
   `ensure_rig()` is idempotent and heals a partial scaffold.
3. **Two controls, split by audience.** `preferences_ctrl` holds a fixed set
   of rig-wide switches that modules cannot extend. `visibilities_ctrl` holds
   one enum per module instance and is where modules land their attributes.
4. **Visibility and display mode are independent.** Rig, joints and geometry
   each get a `bool` for visibility and a separate enum for
   normal / template / reference, so parking geometry in reference mode
   survives toggling it off and on.
5. **Tiers are exclusive.** `primary` shows only primary controls,
   `secondary` only secondary, `tertiary` only tertiary, `all` shows all
   three. Tweak controls are outside the tier system: `tweakVis` on the main
   control keeps owning them.
6. **Tier is a build-time argument with a module default.**
   `rig.controller(name, tier=...)` defaults to `primary`. A module that wants
   rigger choice adds an ordinary `ChoiceField` and feeds it in. No manifest
   change, no generic tier UI.
7. **Tier wiring drives shapes, not transforms.** FK chains parent the next
   controller under the previous one; hiding a transform would take its
   children with it.

## 3. The scaffold

```
rig_grp                       trg_kind = rig_root
├── trigger_grp               trg_kind = rig_trigger   ← every module's <side>_<name>_grp
│   ├── preferences_ctrl      controller, trg_kind = preferences
│   └── visibilities_ctrl     controller, trg_kind = visibilities
└── geo_grp                   trg_kind = rig_geo
```

`ensure_rig()` lives in a new `tik/trigger/maya/scaffold.py` and returns:

```python
@dataclass
class RigScaffold:
    root: tm.Transform          # rig_grp
    trigger: tm.Transform       # trigger_grp
    geo: tm.Transform           # geo_grp
    preferences: Controller
    visibilities: Controller
```

For each node it looks up the fixed name at its expected parent:

- **Found and tagged:** reuse.
- **Found but untagged** (an imported asset shipped a `rig_grp`): adopt it,
  tag it, log a warning. Two roots is worse than one shared one.
- **Missing:** create.

It then adds any preference attribute that is missing, without touching the
values of attributes already present, so a rigger's channel-box changes survive
a rerun. Transform channels on the three groups are locked and hidden, as on
module groups today. The guide holder `trigger_guides_grp` stays outside
`rig_grp`; it is not part of the rig.

Callers:

- `Runner._run_step` calls `ensure_rig()` inside the step's undo chunk, before
  `action.run`, and passes the result as `ctx.rig`.
- `Builder.build` calls it once at the top of its undo chunk, replacing
  `ensure_rig_root`, and hands `scaffold.trigger` to each `ModuleRig` as
  `rig_root`. `ModuleRig` also keeps the whole object as `rig.scaffold`.
- Session and scene reset do nothing extra. A fresh scene has no scaffold
  until the first step runs.

## 4. The preferences control

`preferences_ctrl` carries only rig-wide, animator-neutral switches. All are
non-keyable and shown in the channel box. A separator row (the existing
`rig.separator` convention) heads the three display pairs.

| Attribute | Type | Default | Drives |
|---|---|---|---|
| `cacheMode` | bool | off | nothing; the pipeline reads it |
| `controls` | bool | on | every module's `control_grp` visibility |
| `rig` | bool | off | every module's `rig_grp` visibility |
| `rigDisplay` | enum normal / template / reference | normal | every module's `rig_grp` override |
| `joints` | bool | on | every module's `bind_grp` visibility |
| `jointsDisplay` | enum normal / template / reference | normal | every module's `bind_grp` override |
| `geo` | bool | on | `geo_grp` visibility |
| `geoDisplay` | enum normal / template / reference | normal | `geo_grp` override |

The geometry pair is named `geo`, not `geometry`: every Maya transform already
owns a generic `geometry` attribute, and an ensure that reuses attributes by
name would silently adopt it.

Wiring. The module limb group keeps its three visibility attributes, because
they are what makes a module testable on its own. `finalize` connects the
three preference bools into them and then locks them, so the preference is the
single place to change them. For display mode, `finalize` sets
`overrideEnabled` on the module's `rig_grp` and `bind_grp` and connects the
matching preference enum straight into `overrideDisplayType`; the enum indices
of normal, template and reference match Maya's own. `geo_grp` is wired the same
way once, by `ensure_rig` itself.

Modules cannot add attributes to the preferences control through the `rig`
object. Scripts and actions reach it as `ctx.rig.preferences` and add
attributes deliberately, the ordinary tik.maya way, when the pipeline needs
something. That is the door for "anything the pipeline adds", and it is a door
walked through on purpose.

## 5. The visibilities control and control tiers

`visibilities_ctrl` holds one enum per built module instance, named by the
module's display key (`L_arm`, `base`), with items
`primary / secondary / tertiary / all`. It defaults to `all`, so a rebuilt rig
looks the same as today. A module that declares no controls (twist) adds
nothing. The rig-wide `controls` bool on preferences sits above all of this:
off hides every control group regardless of tiers.

The three tier names live as `TIERS = ("primary", "secondary", "tertiary")` in
`core/manifest.py`, next to the other manifest constants, so a module that
wants rigger choice writes `ChoiceField("primary", choices=TIERS)` and passes
its value in.

`rig.controller(name, tier="primary")` accepts one of the three names,
defaults to `primary`, and tags the controller with a new `trg_tier` meta key
so mirror and picker tools can read it. `tweak_control` passes `tier=None`:
tweaks are neither tagged nor wired. The existing modules keep building
unchanged, all primary.

Wiring happens in `finalize`, once the module's controllers exist. For each
tier the module actually used, one small network answers "enum equals this
tier, or enum equals `all`", built from tik.maya plug helpers rather than
expressions. That boolean drives the `visibility` of every **shape** under the
controllers of that tier. Hiding shapes leaves the hierarchy, the offset
groups and the tweaks alone.

## 6. API surfaces and changes to existing code

The scaffold object is the same class for modules and actions. Actions get it
as `ctx.rig`; modules get it as `rig.scaffold`, mostly for reading. The one
write path a module has is the tier argument on `rig.controller`.

- `maya/scaffold.py` (new): `RigScaffold`, `ensure_rig()`, the fixed names,
  the preference attribute table, the `geo_grp` wiring.
- `maya/build.py`: `ensure_rig_root` is deleted. `Builder.build` loses
  `rig_name`, calls `ensure_rig()`, and hands `scaffold.trigger` to
  `ModuleRig` as `rig_root`. `finalize` gains the preference and tier wiring.
  `BuildReport.rig_root` becomes `BuildReport.scaffold`.
- `maya/rig.py`: `ModuleRig` takes a `scaffold` argument and keeps `rig_root`
  pointing at `trigger_grp`. `controller` gains `tier` and validates it
  against `TIERS`. `tweak_control` passes `tier=None`.
- `maya/tags.py`: new kinds `rig_trigger`, `rig_geo`, `preferences`,
  `visibilities`; new key `TIER = "trg_tier"`. `RIG_ROOT` stays and now means
  `rig_grp`.
- `maya/runner.py`: `_run_step` calls `ensure_rig()` inside the undo chunk
  before `action.run` and passes it through `ActionContext.rig`.
- `maya/__init__.py`: lazy exports for `RigScaffold` and `ensure_rig`.
- `core/action.py`: one new field, `rig: Any = None`, on `ActionContext`.
  `core` stays pure; it only stores whatever it is given.
- `core/manifest.py`: `TIERS`.
- `actions/kinematics`: the `rig_name` field and its use are removed.
- `actions/import_asset`: after import, the top-level transforms the import
  created are parented under `geo_grp`. A referenced file is parented the
  same way, which Maya records as a reference edit. A new `parent_to_geo`
  bool, default on, lets a rigger opt out when a file brings its own
  structure.
- `systems/limb_lock.py`: untouched. It reads `rig.rig_root`, which is still
  the world-space anchor above every module.
- `modules/base`: untouched. The root controller stays a module concern; the
  scaffold has no master transform controller by design.
- `AI/coding_rules.md` and `CLAUDE.md`: the group taxonomy gains the scaffold
  above the module groups and the tier rule for controllers.

## 7. Scope of this spec

Not in scope: a global tier override above the per-module enums, a picker,
any UI for the scaffold in the pipeline window, and any attribute a module
could add to the preferences control. The scaffold is invisible to the session
document and needs no schema bump.

## 8. Testing

All new tests run under mayapy, matching the existing split.

- **`tests/unit/test_scaffold_trigger.py`** for `ensure_rig` on its own. A
  fresh scene produces the five nodes with the right names, parents, tags and
  attributes. A second call creates nothing new and leaves changed attribute
  values alone. A scene with a bare untagged `rig_grp` is adopted and tagged
  with a warning. A scene missing only `geo_grp`, or only one attribute, is
  healed. Transform channels on the groups are locked. `geo` and
  `geoDisplay` drive `geo_grp`.
- **`tests/integration/trigger/test_builder_trigger.py`** gains the wiring
  cases. Every built module's group lands under `trigger_grp`. Toggling
  `controls`, `rig`, `joints` on preferences changes every module's group
  visibility, and the module-level attributes are locked. Setting
  `rigDisplay` to reference changes every `rig_grp` override. The
  visibilities control has one enum per module with controls, none for twist,
  and each enum value shows exactly the shapes of that tier, with `all`
  showing all three. A tweak's shapes ignore the enum.
- **`tests/integration/trigger/test_module_ground_rules.py`** gains two
  enforcement points: every non-tweak controller carries a valid `trg_tier`,
  and the visibilities enum count matches the modules that declare controls.
- **`tests/unit/test_runner_trigger.py`** checks that an action receives
  `ctx.rig` with the scaffold present, and that a script action can add an
  attribute to the preferences control.
- **Import Model** gets a test that an imported file's top nodes end up under
  `geo_grp`, and that `parent_to_geo` off leaves them at world.
- **Existing tests** that pass `rig_name` or look for `trigger_rig` are
  updated to the fixed names. `tests/unit/test_import_boundaries.py` keeps
  guarding that `core` gained nothing from Maya.

A toy module in `tests/helpers/toy_modules.py` builds one controller per tier,
so the tier tests do not wait for a real module to grow secondary controls.
