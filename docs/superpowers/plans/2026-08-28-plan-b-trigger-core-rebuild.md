# Plan B — tik.trigger Core Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tik.trigger scaffold with the declarative Module/Action contracts, a DCC-agnostic core + Maya backend, the builder, and a single RigSession document; prove it with `base` + `fkchain` modules and `import_asset`/`kinematics`/`script` actions.

**Architecture:** `tik.core.fields` gives typed declarative settings. `tik.trigger.core` (no Maya) defines Module, Action, manifests, contexts (Protocols), Backend protocol, Builder and session schemas. `tik.trigger.backends.maya` implements guides-as-tagged-joints and the build context on tik.maya. Modules compose tik.maya constructs inside `build(ctx)`.

**Tech Stack:** Python 3.10+, tik.maya (Plan A), pytest under mayapy.

**Spec:** `docs/superpowers/specs/2026-08-28-trigger-rebuild-design.md` (§4, §6, §7, §9)

## Global Constraints

- `tik.trigger.core` / `tik.trigger.session` import no `maya`, `tik.maya`, Qt (import-boundary test becomes strict — remove the xfail marks).
- Modules never create groups, apply naming, tag nodes, or handle side multipliers themselves; the context does.
- Identity = uuid meta, never node names.
- Tests: `Set-Location D:\dev\tikworks; $env:PYTHONPATH="src/python"; & "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pytest <paths> -q -p no:cacheprovider`
- Commit trailer as in Plan A.

---

## File map

| File | Responsibility |
|---|---|
| `tik/core/fields.py` | `Field` descriptors, `Schema` mixin, `FieldValidationError` |
| `tik/core/side.py` | `Side` enum (C/L/R), `mirror`, `multiplier` |
| `tik/trigger/core/exceptions.py` | kept; add `FieldValidationError` re-export, `ConnectionError`→`AttachError` |
| `tik/trigger/core/registry.py` | kept; decorators also stamp `module_type`/`action_type` on the class |
| `tik/trigger/core/manifest.py` | `Guides` declaration |
| `tik/trigger/core/schemas.py` | `GuidePose`, `ParentRef`, `ModuleInstance`, `ActionInstance`, `RigDocument` |
| `tik/trigger/core/module.py` | `Module` base |
| `tik/trigger/core/action.py` | `Action` base, `ActionContext` |
| `tik/trigger/core/context.py` | `GuideContext`, `BuildContext`, `RigGroups` protocols |
| `tik/trigger/core/backend.py` | `Backend` protocol |
| `tik/trigger/core/events.py` | `EventBus` |
| `tik/trigger/core/builder.py` | `Builder`, `BuildReport`, topo ordering |
| `tik/trigger/core/discovery.py` | folder discovery for modules/actions (+ `defaults.json`) |
| `tik/trigger/session/rig_session.py` | `RigSession` (.trg document) |
| `tik/trigger/backends/maya/tags.py` | meta key constants + tag/read helpers |
| `tik/trigger/backends/maya/context.py` | `MayaGuideContext`, `MayaBuildContext` |
| `tik/trigger/backends/maya/backend.py` | `MayaBackend` |
| `tik/trigger/modules/base/base.py`, `modules/fkchain/fkchain.py` | first modules |
| `tik/trigger/actions/{import_asset,kinematics,script}/*.py` | first actions |
| `tik/trigger/__init__.py` | public API (`trigger.modules`, `trigger.actions`, `RigSession`, `MayaBackend`) |
| removed | `core/module_core.py`, `core/rig_module.py`, `core/socket_data.py`, `core/module_registry.py`, `core/action_core.py`, `core/io.py`, `session/guide_session.py`, `session/action_session.py`, `session/io.py`, `modules/{arm,pushpull,connector}`, old tests |

---

### Task 1: `tik.core.fields` + `tik.core.side`

**Produces:**
```python
class Field:            # descriptor; subclasses: IntField, FloatField, BoolField, StringField, ChoiceField, VectorField, ListField, NodeRefField
    type_name: str
    def __init__(self, default, *, label=None, help="", min=None, max=None, choices=None, hidden=False, group=None)
    name: str           # set by __set_name__
    def validate(self, value)      # returns coerced value or raises FieldValidationError(field, value, reason)
    def to_schema(self) -> dict    # {"type", "default", "label", "help", "min", "max", "choices", "hidden", "group"}
class Schema:
    @classmethod fields(cls) -> dict[str, Field]   # MRO order, base first
    def values(self) -> dict
    def apply(self, mapping: dict, strict=True)    # strict: unknown key raises KeyError
    def reset(self)
    @classmethod schema(cls) -> dict
class Side(str, Enum): CENTER="C"; LEFT="L"; RIGHT="R"; mirror -> Side; multiplier -> 1|-1; from_value(str|Side)
```
Tests (`tests/unit/test_fields.py`, no Maya): defaults per instance are copies; validation int/float/bool/choice/vector size/list; min/max clamp → error; `apply` strict; `schema()` JSON-serializable; inheritance order; `Side.mirror`.

### Task 2: trigger core contracts

`manifest.Guides(*roles, multi=None, min=None, max=None)`: `.roles`, `.multi`, `.min_count`, `.max_count`, `.root` (roles[0]), `.expand(count) -> list[(role, index)]`, `.validate(pairs)`.

`schemas`: dataclasses with `to_dict()`/`from_dict()`; `RigDocument.SCHEMA = 3`.

`module.Module(Schema)`: class attrs `label`, `sided`, `guides`, `plugs`, `sockets`, `module_type` (stamped by registry); `__init__(instance_id=None, name=None, side="C", settings=None)`; `validate()`; abstract `draw_guides(ctx)`, `build(ctx)`; `to_instance() -> ModuleInstance`; `classmethod from_instance(inst)`.

`action.Action(Schema)`: `label`, `action_type`; `run(ctx)` abstract; `save_assets(directory)` no-op; `to_instance(name, enabled)`. `ActionContext` dataclass `(backend, session, events, paths: dict)`.

`events.EventBus`: `subscribe(event, callback)`, `unsubscribe`, `emit(event, **payload)`; constants `PROGRESS, LOG, ERROR`.

`backend.Backend` Protocol (methods listed in spec §7) + `context` Protocols.

`builder.Builder(backend, events=None)`: `order(instances) -> list[ModuleInstance]` (parents first, stable), `build(scope="scene", rig_name="trigger", afterlife="delete") -> BuildReport(built: list[str], failed: Optional[str])`.

`registry` update: `register_module(name)` sets `cls.module_type = name`; `register_action` sets `cls.action_type`. Add `iter_modules()`/`iter_actions()` returning classes.

`discovery.discover(package_path, kind)`: import `<pkg>.<folder>.<folder>`; load `defaults.json` into `cls.fields()[k].default`.

Tests with a `FakeBackend` (records calls, returns instances): `test_manifest_trigger.py`, `test_module_trigger.py`, `test_builder_trigger.py` (ordering, events, afterlife, failure path), `test_schemas_trigger.py` (roundtrip), `test_registry_trigger.py` (adapt).

### Task 3: RigSession

`RigSession(backend=None, file_path=None)`: `document: RigDocument`, `file_path`, `EXTENSION=".trg"`, `new()`, `save(path=None)`, `load(path)`, `is_modified`, `snapshot_guides(scope="scene")`, `restore_guides(clear_existing=False)`, action CRUD: `add_action(action_type, name=None, index=None) -> ActionInstance`, `remove_action(name)`, `rename_action(name,new)`, `move_action(name,index)`, `set_enabled(name,bool)`, `duplicate_action(name)`, `action_settings(name)`/`update_action_settings(name, mapping)`, `run_action(name)`, `run_all(until=None, reset_scene=False)`, `export_actions(path)`, `import_actions(path, index=None)`, `export_guides(path)`, `import_guides(path)`.

Tests `test_rig_session_trigger.py` with FakeBackend + tmp files.

### Task 4: Maya backend

`tags.py`: `KIND="trg_kind"`, `MODULE="trg_module"`, `INSTANCE="trg_instance"`, `ROLE="trg_role"`, `INDEX="trg_index"`, `SIDE="trg_side"`, `SETTINGS="trg_settings"`, `NAME="trg_name"`, `ATTACH="trg_attach"`; `GUIDE="guide"`, `RIG="rig"`.

`MayaBackend` implements: `find_instances`, `create_guides(module, parent=None)` (draws via `MayaGuideContext`, holder group `trigger_guides_grp`, root guide parented under parent guide node if `parent`), `delete_guides`, `read_settings/write_settings`, `apply_guide_poses`, `undo_chunk`, `ensure_rig_root`, `guide_context`, `build_context`, `finalize`, `connect_all`, `afterlife`, `guide_node(instance_id, role, index=0)`.

`MayaBuildContext`: `guide(role, index=0) -> Joint`, `guides(role) -> list[Joint]`, `groups: RigGroups`, `name(*tokens, suffix=None)`, `controller(name, shape="Circle", size=1.0, parent=None, color=None) -> Controller`, `deform_joint(joint)`, `plug(name, node)`, `socket(name, node)`, `side`, `side_mult`, `module`, `rig_root`, `outputs: dict`. Groups naming `{side}_{name}_{token}_grp`; scale group gets `controlVisibility/jointVisibility/rigVisibility` bools driving `controllers`/`joints`/`rig` groups.

Tests `tests/unit/test_maya_backend_trigger.py`.

### Task 5: modules `base`, `fkchain`; actions `import_asset`, `kinematics`, `script`; public API; cleanup

Integration tests `tests/integration/trigger/test_build_pipeline.py`: base + fkchain guides → build → connection constraint exists → session snapshot → new scene → restore → rebuild; kinematics action via RigSession.run_all.

Remove superseded files; import-boundary test strict; full suite green; docs `docs/source/tik_trigger/index.rst` "Write a module in 50 lines".
