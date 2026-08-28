# Trigger Rebuild on tik.maya — Design Spec

Date: 2026-08-28
Status: approved in brainstorming (Arda Kutlu), execution authorised.
Plan A (tik.maya foundation): completed 2026-08-28.
Plan B (trigger core rebuild): completed 2026-08-28.
Plan C (arm module): completed 2026-08-28.

## 1. Goal

Rebuild the Trigger modular rigging system inside `tikworks` as `tik.trigger`,
using `tik.maya` as the backbone. Not a 1:1 port: keep the proven workflow and
domain knowledge of the old `D:\dev\trigger` repo, re-implement everything on
typed, UUID-backed, undoable `tik.maya` objects, and make adding a module or an
action a small, declarative task for a TD.

Non-goals for this spec: old standalone utilities (shape_transfer, jointify,
mirror_lattice, ROM tools, face_mocap, eyebulge, …) — deferred to `tik.tools`.
UI polish (node-graph views, live validation) — a later spec.

## 2. Findings that drive the design

Old Trigger strengths kept as *ideas*: two-phase guides→build workflow driven by
walking the guide DAG; ordered, serializable action pipeline; compact module
manifest (`LIMB_DATA`); constructs layer (Controller, Ribbon, TwistSpline,
Measure); battle-tested rigging logic (IK/FK, ribbons, matrix constraints,
space switches).

Old Trigger weaknesses fixed: identity by string names; monolithic 1–2.6k line
modules of raw `cmds`; Qt tangled into actions; global singletons; magic joint
type ints; logic/UI duplication.

Current `tik.trigger` scaffold: keep exceptions, config/settings, folder
discovery, the dataclass idea and tests as reference; replace `RigModule` (12
abstract hooks), duplicated `module_registry.py`, deprecated `GuidesCore` /
`ModuleCore`, and all `cmds`-based modules and `guide_session` (which violate
the "consume tik.maya" rule).

`tik.maya` strengths: UUID-backed `Node`, `Plug` with `>>`/`<<` and arithmetic
operators, typed node wrappers, `Controller` role + shape library, registry
with inheritance fallback, deformer/weights layer. Gaps: no metadata/tag API,
no attribute helpers, no naming mechanics, thin `Joint`, no IK handle type, no
constraints/ribbon/twist/measure/space-switch constructs.

## 3. Layering and dependency rules

```
tik.core     pure Python (Color, Axis, Side, fields/schema, naming tokens)
tik.maya     generic Maya wrapper for ANY tikworks project; no Trigger vocabulary
tik.shared   generic Qt/infra (Field -> QWidget generator lives here)
tik.trigger  owns the meaning: guides, modules, plugs/sockets, sessions, actions, UI
```

Rules (enforced by `tests/unit/test_import_boundaries.py`):

- `tik.core` imports no Maya, no Qt, no `tik.maya`, no `tik.trigger`.
- `tik.maya` imports `tik.core` only. Never `tik.trigger`, never Qt.
- `tik.trigger.core` and `tik.trigger.session` import neither `maya`,
  `tik.maya`, nor Qt. They are DCC-agnostic.
- DCC code inside trigger lives in `tik.trigger.backends.<dcc>` and in the
  module/action implementations. Maya is the first backend; the boundary exists
  so `tik.houdini`/`tik.unreal` backends can be added without touching core.
  No speculative abstraction of Maya nodes is built now.

Placement test for rigging code: "Is it Maya-generic with zero Trigger
vocabulary (guide/module/socket/session)?" → `tik.maya` construct/role.
Otherwise → `tik.trigger`.

## 4. Package layout

```
src/python/tik/
├── core/
│   ├── fields.py            # Field descriptors + Schema mixin (see §6)
│   └── side.py              # Side enum (C/L/R), mirror helpers (pure)
├── maya/
│   ├── core/meta.py         # Meta/tag API on Node (typed metadata attrs)
│   ├── core/attribute.py    # separator, lock/hide sets, proxy attrs, drive()
│   ├── core/naming.py       # unique_name, token formatting (mechanics only)
│   ├── types/ikhandle.py
│   ├── types/joint.py       # extended
│   └── constructs/          # matrix_constraint, matrix_switch, space_switch,
│                            # measure, ribbon, twist_spline, ikfk_chain
├── shared/ui/fields.py      # Field -> QWidget factory, FormBuilder
└── trigger/
    ├── core/
    │   ├── exceptions.py    # kept
    │   ├── registry.py      # kept, single registry for modules & actions
    │   ├── manifest.py      # Guides(), plug/socket declarations
    │   ├── module.py        # Module base (DCC-agnostic)
    │   ├── action.py        # Action base (DCC-agnostic)
    │   ├── context.py       # BuildContext / ActionContext protocols
    │   ├── backend.py       # Backend protocol
    │   ├── builder.py       # build orchestration (order, connect, afterlife)
    │   ├── events.py        # plain callback bus (progress, log, errors)
    │   └── schemas.py       # session document dataclasses (versioned)
    ├── session/rig_session.py     # single .trg document (guides + actions)
    ├── backends/maya/       # guide_io.py, context.py, groups.py, tags.py
    ├── modules/<name>/<name>.py  [+ defaults.json optional]
    ├── actions/<name>/<name>.py
    ├── config/              # kept
    └── ui/                  # main window, guides panel, actions panel, models
```

## 5. tik.maya additions (Spec A)

All classes: `create(...)` classmethod or constructor wrapping an existing node,
typed properties for produced nodes, undoable, tested under `mayapy`.

| Area | Addition | Reference in old repo |
|---|---|---|
| core | `Node.meta` — `MetaStore` mapping-like: `node.meta["key"] = value` for str/int/float/bool/list/dict (JSON-encoded string attr with `tik_` prefix), `node.meta.get`, `in`, `del`, `keys()`. `tm.find_by_meta(key, value=None, type=None)` scans scene. | joint type ints, `moduleName` attrs |
| core | `attribute.py`: `add_separator(node, name)`, `lock_and_hide(node, attrs)`, `unlock(node, attrs)`, `add_proxy(node, source_plug, name)`, `drive(source_plug, target_plugs)`, `add_enum`, `add_float/bool/int` convenience returning `Plug` | `library/attribute.py` |
| core | `naming.py`: `unique_name(base)`, `format_name(tokens, side=None, prefix=None, suffix=None, sep="_")` — mechanics only; conventions belong to callers | `library/naming.py` |
| types | `Joint`: `orient_to(aim_vector, up_vector)`, `orient_chain(joints, ...)`, `chain_from(...)`, `mirror_joint`, `side`/`type` enums via meta or Maya attrs | `library/joint.py` |
| types | `IkHandle` (`create(start, end, solver="ikRPsolver"|"ikSCsolver")`, `pole_vector(node)`, `start_joint`, `end_effector`) | cmds.ikHandle usage |
| constructs | `MatrixConstraint.create(driver, driven, maintain_offset=True, skip_translate=(), skip_rotate=(), skip_scale=())` using `multMatrix` + `decomposeMatrix` (+ `pickMatrix` for skips) | `connection.matrixConstraint` |
| constructs | `MatrixSwitch.create(drivers, driven, control_plug)` blended by `wtAddMatrix`/`blendMatrix` | `connection.matrix_switch` |
| constructs | `SpaceSwitch.create(target, spaces, control_plug_name="space", mode="parent"|"point"|"orient")` | `utils/space_switcher` |
| constructs | `Measure.create(start, end)` → `distance` plug; `Measure.between(start, end, ratio)` | `objects/measure.py` |
| constructs | `Ribbon.create(start, end, name, joint_count, controller_count, up_vector, scaleable)` → `deformer_joints`, `controllers`, `start_plug`, `end_plug`, `scale_grp`, `nonscale_grp` | `objects/ribbon.py` |
| constructs | `IkFkChain.create(joints, name, ik_solver, switch_plug)` → duplicates chain into ik/fk/blend, wires blend via `blendMatrix`/pairBlend, exposes `ik_handle`, `ik_joints`, `fk_joints`, `blend_joints`, `switch` plug | arm/leg IK-FK code |
| constructs | `TwistSpline` — deferred to Spec E (needed by spine/tail, not by V1) | `objects/twist_spline.py` |
| utils | `Transform.align_to(target, position, rotation)`, `aim_at(target, up)`, `Transform.between(a, b, ratio)` | `library/functions.py` |

## 6. Fields / schema (tik.core.fields)

Descriptors that are pure data and validate on set:

```python
class IntField(Field[int]):  # also FloatField, BoolField, StringField,
    ...                      # ChoiceField, VectorField, ListField, NodeRefField
```

- `Field(default, *, label=None, help="", min=None, max=None, choices=None, hidden=False, group=None)`.
- A class using fields mixes in `Schema`: `cls.fields()` (ordered dict),
  `instance.values()`, `instance.apply(dict)`, `cls.schema()` → JSON-serializable
  dict (`{"segments": {"type": "int", "default": 3, "min": 1, ...}}`).
- Values are stored per instance; `apply()` raises `FieldValidationError` with
  the field name on bad input.
- Optional `defaults.json` next to a module/action overrides `default` values
  only; loaded by discovery.
- `tik.shared.ui.fields.FormBuilder(schema_obj)` turns fields into Qt widgets
  and writes back through `apply`.

## 7. Trigger core contracts

### Module

```python
@register_module("arm")
class Arm(Module):
    label = "Arm"
    sided = True
    guides = Guides("collar", "shoulder", "elbow", "hand")
    plugs = ("collar",)          # outputs: where children attach
    sockets = ("root",)          # inputs: what this attaches to
    segments = IntField(3, min=1, max=20)
    local = BoolField(False, label="Local Joints")

    def draw_guides(self, ctx: GuideContext) -> None: ...
    def build(self, ctx: BuildContext) -> None: ...
```

- `Guides(*roles, multi=None, min=None, max=None)`: ordered roles; `multi`
  names the repeating role for chains (`Guides("root", multi="segment", min=2)`).
- `Module` (DCC-agnostic) holds `instance_id` (uuid4 hex), `side: Side`,
  `name`, settings (fields), and exposes `validate()` hook.
- Module authors never create groups, never apply naming convention, never tag
  nodes, never handle side multipliers manually, never parent under rig root.

### Contexts (protocols in core, implemented in backends/maya)

`GuideContext`: `ctx.joint(role, position, parent=None, radius=)` creates and
tags a guide joint; `ctx.side_mult`, `ctx.up/look/mirror` vectors.

`BuildContext`: `ctx.guide(role)` → `tm.Joint`; `ctx.guides(role)` for multi;
`ctx.groups.limb/scale/nonscale/controllers/joints/rig`; `ctx.name(*tokens,
suffix=)` applying the Trigger convention (`{side}_{instance}_{tokens}_{suffix}`);
`ctx.controller(name, shape, size, parent, color=None)` creating a tagged
`Controller`; `ctx.deform_joint(node)`; `ctx.plug(name, node)`;
`ctx.socket(name, node)`; `ctx.axes`; `ctx.side`; `ctx.settings` (the module).

### Guides, tags, identity (backend maya)

- Guide = `tm.Joint` with meta: `trg.kind="guide"`, `trg.module`,
  `trg.instance` (uuid), `trg.role`, `trg.side`; root guide also carries
  `trg.settings` (JSON) and `trg.name` (user-facing instance name).
- Identity is the uuid meta, never the node name.
- Hierarchy is DAG parenting of a root guide under a guide of another instance.
  Attachment = child socket `root` ← parent plug chosen by the role of the guide
  it is parented under (plug named after that role if the parent declares it,
  else the parent's first plug). Overridable via `trg.attach` meta on the root.
- Built nodes are tagged `trg.kind="rig"`, `trg.instance`, `trg.role` (for
  plugs/sockets/def joints) so a rig can be introspected after build.

### Builder (core, DCC-agnostic)

```
instances = backend.find_instances(scope)          # reads scene
order = topo_sort(instances by guide parenting)
with backend.undo_chunk("Trigger build"):
    backend.ensure_rig_root(rig_name)
    for inst in order:
        module = registry.get_module(inst.module)(instance=inst)
        module.validate()
        ctx = backend.build_context(module, inst)  # creates groups, resolves guides
        module.build(ctx)
        backend.finalize(ctx)                      # tag outputs, parent groups, vis attrs
    backend.connect_all(order)                     # socket <- plug (MatrixConstraint)
    backend.afterlife(instances, mode)             # keep | hide | delete guides
```

Events (`core/events.py`): `progress(i, n, label)`, `log(level, msg)`,
`error(exc, instance)`. Core emits; UI subscribes. Failure raises `BuildError`
carrying module/instance/role; the undo chunk unwinds partial work.

### Session

One `RigSession` document (`.trg`, JSON):

```json
{"schema": 3, "meta": {...}, "guides": [ModuleInstance...], "actions": [ActionInstance...]}
```

`guides` is a *snapshot* exported from the scene (`session.snapshot_guides()`)
and can be re-applied (`session.restore_guides()`); the scene stays the truth
while editing. `actions` is the ordered pipeline. `import_guides`/`export_guides`
and `import_actions`/`export_actions` operate on the sections. Old
`GuideSession`/`ActionSession` are removed.

### Actions

```python
@register_action("kinematics")
class Kinematics(Action):
    label = "Kinematics"
    guide_scope = ChoiceField("scene", choices=["scene", "selection"])
    afterlife = ChoiceField("delete", choices=["keep", "hide", "delete"])
    def run(self, ctx: ActionContext) -> None: ...
    def save_assets(self, directory) -> None: ...   # optional
```

`ActionContext` gives `backend`, `session`, `events`, `paths`. Actions are run
in order, each in its own undo chunk, `enabled` respected; `run_until(name)`.
V1 actions: `import_asset`, `kinematics`, `script`.

## 8. UI (Spec D, minimal)

PySide via vendored Qt shim, `tik.shared.ui.qtmaya.get_main_window()`.
Main window with two tabs:

- **Guides**: module palette (from registry, with side picker L/R/C/both),
  instance tree read from scene meta (refresh on demand + on selection change),
  property editor from `FormBuilder(module)` writing to `trg.settings`.
- **Actions**: ordered list (add/remove/duplicate/enable/reorder), property
  editor from `FormBuilder(action)`, Run / Run Until / Build All, progress bar
  + log fed by the event bus. File menu: new/open/save/save-as/import/export.

Model: `SessionModel(QAbstractItemModel)` over `RigSession`. No Qt in core.

## 9. Testing

- `mayapy` pytest, existing `tests/conftest.py` fixtures.
- `tests/unit/`: `test_fields.py` (no Maya), `test_import_boundaries.py`,
  `test_meta.py`, `test_attribute.py`, `test_naming.py`, `test_ikhandle.py`,
  constructs (`test_matrix_constraint.py`, `test_ribbon.py`, `test_ikfk_chain.py`,
  `test_measure.py`, `test_space_switch.py`), trigger core with a `FakeBackend`
  (`test_module_trigger.py`, `test_builder_trigger.py`, `test_rig_session_trigger.py`).
- `tests/integration/trigger/`: per module guides→build→connect round trip,
  session snapshot/restore round trip, kinematics action end to end.
- Acceptance: "write a module in ~50 lines" doc example (`FkChain`) passes its
  integration test.

## 10. Decomposition and order

- **A** tik.maya rigging foundation (meta, attribute, naming, Joint, IkHandle,
  MatrixConstraint, MatrixSwitch, Measure, SpaceSwitch, Ribbon, IkFkChain).
- **B** trigger core rebuild (fields, Module/Action, backend protocol + Maya
  backend, builder, RigSession, discovery; modules `base`, `fkchain`; actions
  `import_asset`, `kinematics`, `script`; removal of superseded code).
- **C** Arm module on the constructs, connected to base.
- **D** minimal UI.
- Housekeeping done first: Makefile/make.bat/invoke.py conflict markers, CLAUDE.md
  paths, remove deprecated core classes.
- Later specs: remaining modules (leg, spine, head, eye, finger, tail, tentacle,
  hindleg, pushpull, surface, singleton, connector), remaining actions, TwistSpline,
  UI polish, utilities → tik.tools.
