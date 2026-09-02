# tik.trigger Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tik.trigger readable and editable by deleting abstraction that does not pay for itself — the fictional backend/context protocols, the fakes, legacy `.trg` compatibility and the dual wiring path — and replacing the `ctx` god object with an injected `rig` object that owns naming, tagging, placement and registration.

**Architecture:** tik.trigger becomes Maya-only. `core` keeps only what is genuinely pure (document, schemas, registry, fields, events, ordering); everything that touches a scene lives in `maya/` and `guides/` and imports tik.maya directly. Modules build through `ModuleRig`, a single concrete class with no protocol behind it. Sockets are materialized from declared inputs rather than hand-built by each module.

**Tech Stack:** Python 3.10+, Maya 2026 (`mayapy`), pytest, tik.maya, PySide (via `tik.vendor.Qt`).

**Spec:** `docs/superpowers/specs/2026-08-30-trigger-simplification-design.md`

## Global Constraints

- **No raw `maya.cmds` / `maya.api` / `pymel` in tool code.** Go through tik.maya. The exception is inside tik.maya itself, and the documented scene-scanning primitives in `guides/nodes.py` that tik.maya does not expose (`cmds.ls` with `objectsOnly`, `cmds.xform` world queries, `cmds.undoInfo`). Every such call carries a comment saying why.
- **No third-party dependencies.** Stdlib and Maya-bundled modules only.
- **`tik/trigger/core` imports no Maya and no Qt.** Enforced by `tests/unit/test_import_boundaries.py`.
- **Modules never inherit from other modules.** Shared behaviour goes in `tik/trigger/systems/`.
- **Four groups per module** (`socket` / `control` / `rig` / `bind`), two skeletons (puppet in `rig_grp`, deform skeleton in `bind_grp` with live TRS), one bind hierarchy per rig built in final position via `rig.bind_parent`, never reparented.
- **`control_grp` holds nothing but controllers and their offset groups.** Controllers are *driven by* sockets, never parented under them.
- Test commands (paths absolute for Git Bash on this machine):
  - Unit: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit -q`
  - Integration: `PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration -q`
  - UI: `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/ui -q`
- **Baseline (commit `0413d5e`): 962 unit passed / 1 skipped, 97 integration passed, 47 UI passed.** Every task ends with the suites at or above this count, minus tests deliberately deleted by that task (which the task names explicitly).

## A note on TDD in a refactor

Most tasks here move or delete code whose behaviour must not change. For those, **the existing suite is the test**: run it before, make the change, run it after. Do not write new tests asserting that a moved function still exists.

Tasks that add or change behaviour — auto-materialized sockets (Task 9), automatic offset groups (Task 10) — are strict TDD: failing test first.

## File Structure

| File | Responsibility |
|---|---|
| `src/python/tik/trigger/core/` | Pure Python: fields, schemas, document, registry, runner, events, exceptions, module declaration, manifest |
| `src/python/tik/trigger/maya/rig.py` | `ModuleRig`, `GuideDraft`, `RigGroups` — what modules build through |
| `src/python/tik/trigger/maya/build.py` | `Builder`, `BuildReport`, rig root, connect, spaces, afterlife |
| `src/python/tik/trigger/maya/tags.py` | Meta keys and the `tag()` helper |
| `src/python/tik/trigger/maya/observer.py` | Scene observer |
| `src/python/tik/trigger/guides/scene.py` | `GuideScene` + `GuideHandle` — the TD-facing guide API |
| `src/python/tik/trigger/guides/nodes.py` | Guide-joint primitives: create, tag, scan, pose |
| `src/python/tik/trigger/guides/format.py` | `.trg` read/write — pure Python |
| `src/python/tik/trigger/session.py` | `Session`, `ActionHandle` |
| `src/python/tik/trigger/ui/designer/` | Guide Designer: `window`, `tree`, `properties`, `scene_nodes`, `commands` |
| `src/python/tik/trigger/ui/graph/` | Node graph: `items`, `scene`, `view` |

Deleted: `core/backend.py`, `core/context.py`, `core/builder.py`, `backends/` (whole tree), `tests/helpers/trigger_fakes.py`.

---

## Phase 0 — Baseline

### Task 1: Repair the Makefile

`Makefile` has 10 merge-conflict markers committed in HEAD from the `TW-4-deformer-and-weights-workflows` merge, so `make` cannot parse it at all. The whole refactor leans on the test suite, so this is fixed first and alone.

**Files:**
- Modify: `Makefile:6-10, 26-30, 48-54, 62-70, 112-179`

**Interfaces:**
- Consumes: nothing.
- Produces: working `make tests`, `make tests-unit`, `make tests-integration`, `make tests-ui`.

- [ ] **Step 1: Confirm the Makefile is broken**

```bash
make help
```
Expected: a parse error (`*** missing separator` or similar), not a target listing.

- [ ] **Step 2: Resolve every conflict in favour of HEAD**

HEAD is correct in all five regions: sources live at `src/python/tik` (so `SRC_DIR := src/python`), and HEAD carries the CMake and package-script targets the other branch dropped. Delete the `<<<<<<< HEAD`, `=======` and `>>>>>>> TW-4-deformer-and-weights-workflows` lines together with the non-HEAD body of each region, giving:

- line 6-10 → `SRC_DIR := src/python`
- line 26-30 → `SET_PYTHONPATH = set PYTHONPATH=$(CURDIR)/$(SRC_DIR)$(PATH_SEP)%PYTHONPATH% &&`
- line 48-54 → the HEAD `| sort` / `| awk ...` continuation lines
- line 62-70 → `cd $(DOCS_DIR) && make html`
- line 112-179 → keep the entire HEAD block (CMake Build + package-script build/release/dev/add-plugin sections)

- [ ] **Step 3: Fix the misplaced `tests-ui` target**

`tests-ui` currently sits between `.PHONY: tests-integration` and the `tests-integration:` rule, so `tests-integration` is not actually declared phony. Move it below `tests-integration` and give it its own `.PHONY`:

```makefile
.PHONY: tests-integration
tests-integration: ## Run integration tests
	$(SET_PYTHONPATH) $(MAYAPY) $(TESTS_DIR)/integration/invoke.py

.PHONY: tests-ui
tests-ui: ## Run Qt UI tests (no Maya standalone)
	$(SET_PYTHONPATH) set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && $(MAYAPY) -m pytest tests/ui -q
```

- [ ] **Step 4: Verify**

```bash
make help
grep -c "<<<<<<<\|>>>>>>>" Makefile
```
Expected: the target list prints; grep returns `0`.

- [ ] **Step 5: Commit**

```bash
git add Makefile
git commit -m "fix(build): resolve committed merge conflict markers in Makefile"
```

---

## Phase 1 — Deletions

### Task 2: Delete legacy `.trg` compatibility

**Files:**
- Modify: `src/python/tik/trigger/guides/format.py` (remove `legacy_type`, `legacy_table`, `ROOT_TYPE_ATTRS`, `_settings_from_attrs`, `_module_name`, `_instances_legacy`, `_walk_members`, the bare-list branch in `load`, the legacy user_attributes block in `make_record`)
- Modify: `src/python/tik/trigger/guides/__init__.py` (drop `legacy_table`, `legacy_type` exports)
- Modify: `src/python/tik/trigger/core/module.py` (delete `legacy_types`; rename `output_for_role` → `output_at_role`)
- Modify: `src/python/tik/trigger/modules/base/base.py:18`, `src/python/tik/trigger/modules/fkchain/fkchain.py:22` (delete `legacy_types`)
- Modify: `src/python/tik/trigger/backends/maya/backend.py` (delete `_write_legacy_attrs`, `_tag_legacy_joint`, `_JOINT_SIDES`, `_AXES`, their call sites at lines 201, 236, 356, 388)
- Modify: `src/python/tik/trigger/backends/maya/tags.py:25-26` (delete `PLUG` / `SOCKET` aliases after repointing users)
- Modify: `tests/unit/test_io_trigger.py`, `tests/unit/test_guides_trigger.py` (delete legacy-recovery cases)

**Interfaces:**
- Consumes: nothing.
- Produces: `Module.output_at_role(role) -> Optional[str]` — the output whose name matches the parent's guide role, else the first declared output. Used by `GuideScene.add` to pre-fill a new guide's primary input. `make_record()` loses its `legacy`, `axes` and `inherit_orientation` parameters.

- [ ] **Step 1: Find every legacy reference**

```bash
grep -rn "legacy\|otherType\|useRefOri\|ROOT_TYPE_ATTRS\|output_for_role\|tags.PLUG\|tags.SOCKET" --include="*.py" src/python/tik/trigger tests
```
Record the list; every hit is either deleted or renamed by this task.

- [ ] **Step 2: Delete the legacy reader path in `format.py`**

`GuideFile.load` drops the bare-list branch — a `.trg` is always a dict with `joints`:

```python
    @classmethod
    def load(cls, file_path) -> "GuideFile":
        path = Path(file_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise GuideError(f"Cannot read guides '{path}': {error}") from error
        if isinstance(data, dict) and isinstance(data.get("joints"), list):
            return cls(data["joints"], data.get("connections", []),
                       data.get("meta", {}), data.get("designer", {}))
        raise GuideError(f"'{path}' is not a Trigger guide file.")
```

`classify` no longer falls back to the legacy table:

```python
    def classify(self, record: dict) -> Optional[tuple[str, str, bool]]:
        """``(module_type, role, is_root)`` for a record, or None when unknown."""
        module_type, role = record.get("module"), record.get("role")
        if not module_type or not role or not registry.is_module_registered(module_type):
            return None
        return module_type, role, registry.get_module(module_type).guides.root == role
```

`instances()` loses the branch:

```python
    def instances(self) -> list[GuideInstance]:
        """Group records into module instances."""
        self.unknown = sorted({
            record.get("module", "") for record in self.records if self.classify(record) is None
        })
        instances = self._instances_explicit()
        self._resolve_inputs(instances)
        return instances
```

Delete `_instances_legacy`, `_walk_members`, `_module_name`, `_settings_from_attrs`, `ROOT_TYPE_ATTRS`, `legacy_type`, `legacy_table`.

In `_instances_explicit`, replace `_module_name(record)` with `record.get("module_name") or record.get("name", "")` and `dict(record.get("settings") or _settings_from_attrs(record))` with `dict(record.get("settings") or {})`.

- [ ] **Step 3: Slim `make_record`**

```python
def make_record(
    *,
    name: str,
    position,
    rotation,
    joint_orient,
    parent: Optional[str],
    side: str,
    module: str,
    role: str,
    index: int,
    instance: str,
    radius: float = 1.0,
    color: int = 17,
    settings: Optional[dict] = None,
    module_name: Optional[str] = None,
) -> dict:
    """One joint record in the tikworks ``.trg`` layout."""
    record = {
        "name": name,
        "position": [float(value) for value in position],
        "rotation": [float(value) for value in rotation],
        "joint_orient": [float(value) for value in joint_orient],
        "scale": [1, 1, 1],
        "parent": parent,
        "side": side,
        "color": int(color),
        "radius": float(radius),
        "module": module,
        "role": role,
        "index": int(index),
        "instance": instance,
    }
    if settings is not None:  # root joint
        record["settings"] = dict(settings)
        record["module_name"] = module_name or name
    return record
```

Delete `_attr_type`. Update `backend.py:349` (`export_guide_records`) to drop the `legacy=`, `type` and `user_attributes` arguments.

- [ ] **Step 4: Rename `output_for_role` and delete `legacy_types`**

In `core/module.py`, delete the `legacy_types` class attribute and replace `output_for_role` with:

```python
    @classmethod
    def output_at_role(cls, role: str) -> Optional[str]:
        """Output a child's primary input is pre-filled with when drawn under ``role``.

        The output whose name matches the parent's guide role if there is one,
        else the parent's first output.
        """
        if role in cls.outputs:
            return role
        return cls.outputs[0] if cls.outputs else None
```

Update the three call sites: `backends/maya/backend.py:210`, `guides/format.py:_resolve_inputs`, `core/builder.py:43` (that last one is deleted in Task 3 — leaving it renamed here keeps this task green on its own). Delete `legacy_types` from `modules/base/base.py:18` and `modules/fkchain/fkchain.py:22`.

- [ ] **Step 5: Delete legacy scene writing**

In `backends/maya/backend.py`, delete `_write_legacy_attrs`, `_tag_legacy_joint`, `_JOINT_SIDES` and `_AXES`, plus their call sites at lines 201, 236, 388. `_write_root_meta` becomes:

```python
    @staticmethod
    def _write_root_meta(root, module, attach) -> None:
        root.meta[tags.NAME] = module.name
        root.meta[tags.SETTINGS] = module.values()
        if attach:
            root.meta[tags.ATTACH] = attach
        MayaBackend._sync_setting_attrs(root, module)
```

Give `_sync_setting_attrs` a docstring recording why it survives:

```python
    @staticmethod
    def _sync_setting_attrs(root, module) -> None:
        """Mirror module fields as real Maya attributes on the root guide.

        Not legacy: the Guide Designer binds its property widgets two-way to
        these plugs through ``settings_plug()``. The authoritative storage is
        still the ``trg_settings`` meta dict; non-scalar field kinds have no
        sensible single attribute and live only there.
        """
```

In `tags.py`, delete the `PLUG = OUTPUT` / `SOCKET = INPUT` aliases and repoint any user found in Step 1 to `OUTPUT` / `INPUT`.

- [ ] **Step 6: Delete the legacy tests**

In `tests/unit/test_io_trigger.py` and `tests/unit/test_guides_trigger.py`, delete tests that assert legacy recovery, legacy `type` names, `user_attributes` round-trips, `moduleName` / `useRefOri` / axis attributes, or `otherType` joint labels. Keep every test covering the explicit keys. If a fixture `.trg` under `tests/data/` is a bare joint list, delete it and any test using it.

- [ ] **Step 7: Run all three suites**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit tests/integration -q
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/ui -q
```
Expected: PASS, with the count down only by the tests deleted in Step 6.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(tik.trigger): drop old-Trigger .trg compatibility"
```

### Task 3: Delete the dual wiring path

`instance.inputs` becomes the only thing the builder reads.

**Files:**
- Modify: `src/python/tik/trigger/core/builder.py` (delete `derive_inputs`, use `instance.inputs`)
- Modify: `src/python/tik/trigger/core/schemas.py:65, 91` (delete `ModuleInstance.attach`)
- Modify: `src/python/tik/trigger/backends/maya/backend.py` (`create_guides`/`_write_root_meta` drop `attach`; `_instance_from_nodes` drops `attach=`)
- Modify: `src/python/tik/trigger/backends/maya/tags.py:13` (delete `ATTACH`)
- Modify: `src/python/tik/trigger/guides/handler.py` (drop `attach` from `add`)
- Test: `tests/unit/test_connections_trigger.py`, `tests/integration/trigger/test_session_build_trigger.py`

**Interfaces:**
- Consumes: `Module.output_at_role` from Task 2.
- Produces: `Builder.build()` reads `instance.inputs` directly. `ModuleInstance` no longer has `attach`. `GuideScene.add(..., inputs=...)` still pre-fills the primary input when `parent` is given.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_connections_trigger.py`:

```python
def test_guide_parenting_writes_a_real_input(scene):
    """Parenting pre-fills inputs; the builder derives nothing from the DAG."""
    body = scene.add("base", name="body")
    arm = scene.add("arm", side="L", parent=body)

    assert arm.instance.inputs == {"root": "body.root"}
```

Then, in the same file, a test that a cleared input is honoured rather than re-derived from the parent:

```python
def test_cleared_input_is_not_re_derived_from_the_parent(scene):
    body = scene.add("base", name="body")
    arm = scene.add("arm", side="L", parent=body)
    arm.set_input("root", "")

    assert arm.instance.inputs == {}
```

- [ ] **Step 2: Run to verify the second one fails**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_connections_trigger.py -q
```
Expected: `test_cleared_input_is_not_re_derived_from_the_parent` FAILS — `derive_inputs` falls back to the DAG parent when `inputs` is empty.

- [ ] **Step 3: Delete `derive_inputs`**

In `core/builder.py`, remove the `derive_inputs` function entirely and replace its four call sites (lines 100, 112, 191, and the `structural_inputs` closure) with `dict(instance.inputs)`:

```python
            def structural_inputs(item):
                module_cls = registry.get_module(item.module_type)
                skip = space_input_names(module_cls, item.settings)
                return {
                    name: source
                    for name, source in item.inputs.items()
                    if name not in skip
                }
```

and inside the build loop:

```python
                module_cls = registry.get_module(instance.module_type)
                inputs = dict(instance.inputs)
```

and in `_connect_spaces`, `inputs = dict(instance.inputs)`. Delete the now-unused `by_id` locals where nothing else uses them.

- [ ] **Step 4: Delete `ModuleInstance.attach`**

Remove the field (`schemas.py:65`) and its `from_dict` line (`schemas.py:91`). Remove `attach` parameters and arguments from `MayaBackend.create_guides`, `_write_root_meta`, `_instance_from_nodes`, `GuideScene.add`, and `tags.ATTACH`. Where `create_guides` pre-fills the primary input, `attach or parent_cls.output_at_role(parent.role)` becomes `parent_cls.output_at_role(parent.role)`.

- [ ] **Step 5: Run the tests**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit tests/integration -q
```
Expected: PASS, both new tests included.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(tik.trigger): inputs are the only wiring; drop DAG-derived attach"
```

---

## Phase 2 — Collapse the layers

### Task 4: Move the Maya layer out of `backends/`

Pure file moves plus import rewrites. No behaviour changes.

**Files:**
- Create: `src/python/tik/trigger/maya/__init__.py`, `maya/tags.py`, `maya/observer.py`, `maya/rig.py`, `maya/build.py`
- Delete: `src/python/tik/trigger/backends/` (whole tree), `src/python/tik/trigger/core/backend.py`, `src/python/tik/trigger/core/context.py`, `src/python/tik/trigger/core/builder.py`
- Modify: `src/python/tik/trigger/core/__init__.py`, `src/python/tik/trigger/__init__.py`, every importer found in Step 1

**Interfaces:**
- Consumes: Tasks 2-3.
- Produces: `tik.trigger.maya.rig.ModuleRig` / `GuideDraft` / `RigGroups` (still named `MayaBuildContext` / `MayaGuideContext` at this point — renamed in Task 9), `tik.trigger.maya.build.Builder` / `BuildReport`, `tik.trigger.maya.tags`. `tik.trigger.core` no longer exports `Backend`, `BuildContext`, `GuideContext`, `RigGroups`, `Builder`, `BuildReport`, `AFTERLIFE_MODES`.

- [ ] **Step 1: List every importer**

```bash
grep -rn "backends\|core.builder\|core.context\|core.backend\|from tik.trigger.core import.*Builder\|RigGroups\|BuildContext\|GuideContext" --include="*.py" src/python/tik tests
```

- [ ] **Step 2: Move the files**

```bash
mkdir -p src/python/tik/trigger/maya
git mv src/python/tik/trigger/backends/maya/tags.py     src/python/tik/trigger/maya/tags.py
git mv src/python/tik/trigger/backends/maya/observer.py src/python/tik/trigger/maya/observer.py
git mv src/python/tik/trigger/backends/maya/context.py  src/python/tik/trigger/maya/rig.py
git mv src/python/tik/trigger/core/builder.py           src/python/tik/trigger/maya/build.py
git rm src/python/tik/trigger/core/backend.py src/python/tik/trigger/core/context.py
git rm src/python/tik/trigger/backends/__init__.py src/python/tik/trigger/backends/maya/__init__.py
```

`backends/maya/backend.py` stays put for now — Task 5 dissolves it into `guides/`. Move it aside so the tree is clean:

```bash
git mv src/python/tik/trigger/backends/maya/backend.py src/python/tik/trigger/maya/scene.py
```

- [ ] **Step 3: Write `maya/__init__.py`**

```python
"""The Maya layer of tik.trigger: everything that touches a scene."""

from .build import AFTERLIFE_MODES, Builder, BuildReport
from .rig import GuideDraft, ModuleRig, RigGroups

__all__ = [
    "AFTERLIFE_MODES",
    "Builder",
    "BuildReport",
    "GuideDraft",
    "ModuleRig",
    "RigGroups",
]
```

At this step the classes are still called `MayaGuideContext` / `MayaBuildContext`; alias them here (`ModuleRig = MayaBuildContext`) only if it keeps the step green, and delete the aliases in Task 9. Prefer renaming the classes now if the sweep is small.

- [ ] **Step 4: Move `RigGroups` into `maya/rig.py`**

`RigGroups` was in `core/context.py`. Paste the dataclass at the top of `maya/rig.py`, keeping its docstring verbatim — it documents the four-group rule:

```python
@dataclass
class RigGroups:
    """The four groups created for every module instance, under ``limb``.

    ``socket`` holds input attach transforms driven by parent module outputs.
    ``control`` holds controllers and their offset/space groups, nothing else.
    ``rig`` holds the puppet: IK/FK chains, handles, math, helpers.
    ``bind`` holds deform/export joints only, and is empty when the module is
    connected to a parent (its joints are created in the parent's hierarchy).
    """

    limb: Any = None  # top group of the module
    socket: Any = None
    control: Any = None
    rig: Any = None
    bind: Any = None
```

- [ ] **Step 5: Rewrite the exports**

`core/__init__.py`: delete `Backend`, `BuildContext`, `GuideContext`, `RigGroups`, `Builder`, `BuildReport`, `AFTERLIFE_MODES` from both the imports and `__all__`.

`tik/trigger/__init__.py`: `Builder` now comes from `tik.trigger.maya`; the module docstring's quick start becomes:

```python
"""tik.trigger — modular rigging framework built on tik.maya.

Quick start (Maya)::

    import tik.trigger as trigger

    trigger.load_plugins()
    scene = trigger.GuideScene()
    scene.add("base", name="body")
    trigger.Builder().build()

Importing this package does not import Maya; constructing a ``GuideScene``
or a ``Builder`` does.
"""
```

Keep `maya_backend()` as a deprecated shim returning the scene object until Task 5 lands, then delete it.

- [ ] **Step 6: Rewrite every importer from Step 1**

Mechanical: `tik.trigger.backends.maya` → `tik.trigger.maya`, `from tik.trigger.core import Builder` → `from tik.trigger.maya import Builder`. This includes `tests/integration/trigger/conftest.py`, `tests/unit/test_maya_backend_trigger.py`, `tests/integration/trigger/test_arm_trigger.py`, `test_limb_system.py`, `test_module_ground_rules.py`, `actions/kinematics/kinematics.py`, and the UI modules.

- [ ] **Step 7: Update the import-boundary test**

`tests/unit/test_import_boundaries.py`: delete the `"trigger/session"` entry (that package never existed, so the test silently skipped it) and keep `"trigger/core"`.

```python
FORBIDDEN = {
    "core": ("maya", "tik.maya", "tik.trigger", "tik.shared") + QT,
    "maya": ("tik.trigger", "tik.shared") + QT,
    "trigger/core": ("maya", "tik.maya") + QT,
}
```

- [ ] **Step 8: Run all three suites**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit tests/integration -q
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/ui -q
```
Expected: PASS at the Task 3 counts. `test_import_boundaries` must pass — if `trigger/core` now imports Maya, the Builder move is incomplete.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(tik.trigger): delete backend/context protocols, move Maya layer to trigger/maya"
```

### Task 5: `GuideScene` absorbs the backend

`guides.handler.Guides` holds a `backend` and forwards to it. The two merge; `maya/scene.py` (the old `MayaBackend`) is split by topic into `guides/scene.py` and `guides/nodes.py`.

**Files:**
- Create: `src/python/tik/trigger/guides/nodes.py`
- Create: `src/python/tik/trigger/guides/scene.py` (from `guides/handler.py` + the guide half of `maya/scene.py`)
- Delete: `src/python/tik/trigger/guides/handler.py`, `src/python/tik/trigger/maya/scene.py`
- Modify: `src/python/tik/trigger/maya/build.py` (absorbs `ensure_rig_root`, `finalize`, `connect`, `connect_space`, `afterlife`, `build_context`)
- Modify: `src/python/tik/trigger/guides/__init__.py`, `src/python/tik/trigger/__init__.py`, `actions/kinematics/kinematics.py`, `core/action.py`, `session.py`, UI modules

**Interfaces:**
- Consumes: Task 4's layout.
- Produces:
  - `GuideScene(events=None)` — no backend parameter. Methods: `instances()`, `roots()`, `get(instance_id)`, `find(name, side=None)`, `__getitem__`, `add(module_type, side="C", name=None, parent=None, inputs=None, **settings)`, `remove(handle)`, `clear()`, `unique_name(name, side)`, `import_(path)`, `export(path, instance_ids=None)`, `layout` property, `invalidate()`, `selected_guide()`, `settings_plug(instance_id, field_name)`, `make_observer(callback)`.
  - `GuideHandle` — unchanged public surface, minus `attach`.
  - `guides.nodes` module-level functions: `holder()`, `guide_nodes(instance_id)`, `guide_node(instance_id, role, index=0)`, `find_instances(scope="scene")`, `instance_from_nodes(instance_id, nodes, meta=None)`, `apply_poses(nodes, poses)`, `create_guide_joint(...)`, `undo_chunk(label)`, `scene_node(name)`, `select_nodes(nodes)`, `selected_node_names()`.
  - `Builder(events=None)` — no backend parameter.
  - `ActionContext` without a `backend` field.

- [ ] **Step 1: Split `maya/scene.py` by topic**

Into `guides/nodes.py` (the primitives): `holder`, `guide_nodes`, `guide_node`, `_root_guide`, `_parent_ref`, `_instance_from_nodes` → `instance_from_nodes`, `find_instances`, `_apply_poses` → `apply_poses`, `scene_node`, `undo_chunk`, `select_nodes`, `selected_node_names`, `selected_node_name`, `select_guides`, `selected_guide`, and the guide-joint creation currently inside `MayaGuideContext.joint`.

Into `maya/build.py` (build-time): `ensure_rig_root`, `build_context`, `finalize`, `connect`, `connect_space`, `afterlife`.

Into `guides/scene.py` (authoring, merged with `handler.py`): `create_guides`, `delete_guides`, `write_settings`, `read_settings`, `settings_plug`, `set_inputs`, `rename_instance`, `reparent_guides`, `read_layout`, `write_layout`, `export_guide_records`, `import_guide_instances`, `apply_guide_poses`, `make_observer`, plus everything already in `handler.py`.

These are module-level functions in `guides/nodes.py` (they hold no state) and methods on `GuideScene` in `guides/scene.py`.

- [ ] **Step 2: Collapse the delegation**

Every `self._guides.backend.X(...)` in `GuideHandle` becomes `self._scene.X(...)`, and every `self.backend.X(...)` in `GuideScene` becomes either a local method or a `nodes.X(...)` call. `GuideScene.__init__` becomes:

```python
class GuideScene:
    """The guides in the current Maya scene: author, import/export, test build."""

    def __init__(self, events: Optional[EventBus] = None) -> None:
        self.events = events or EventBus()
        self._cache: Optional[dict[str, ModuleInstance]] = None
```

- [ ] **Step 3: Drop `Builder`'s backend parameter**

```python
class Builder:
    """Turn the guide instances found in the scene into a rig."""

    def __init__(self, events: Optional[EventBus] = None) -> None:
        self.events = events or EventBus()
```

Inside, `self.backend.find_instances(scope)` → `nodes.find_instances(scope)`, `self.backend.undo_chunk(...)` → `nodes.undo_chunk(...)`, and `ensure_rig_root` / `build_context` / `finalize` / `connect` / `connect_space` / `afterlife` become module-level functions in `maya/build.py` called directly.

- [ ] **Step 4: Drop `ActionContext.backend`**

`core/action.py`: delete the `backend: Any` field. `actions/kinematics/kinematics.py`:

```python
    def run(self, ctx) -> None:
        from tik.trigger.guides import GuideScene
        from tik.trigger.maya import Builder

        if not self.guides_file:
            raise ActionExecutionError("kinematics: no guides file set.")
        scene = GuideScene(events=ctx.events)
        handles = scene.import_(ctx.resolve(self.guides_file))
        ...
        report = Builder(events=ctx.events).build(
            scope=scope, rig_name=self.rig_name, afterlife=self.after_build
        )
```

Update the two `ActionContext(...)` constructions at `session.py:410` and `ui/session_view.py:344` to stop passing `backend=`.

- [ ] **Step 5: Update the entry points**

`tik/trigger/__init__.py`: delete `maya_backend()`; export `GuideScene` and `Builder`. `guides/__init__.py` exports `GuideScene`, `GuideHandle`, `GuideFile`, `GuideInstance`, `make_record`, `EXTENSION`.

- [ ] **Step 6: Update the tests**

`tests/integration/trigger/conftest.py`'s `backend` fixture becomes a `scene` fixture returning `GuideScene()`; `tests/unit/test_maya_backend_trigger.py` is renamed `tests/unit/test_guide_scene_trigger.py` and its `MayaBackend()` fixture becomes `GuideScene()`. Method names are unchanged, so the bodies mostly stand.

- [ ] **Step 7: Run all three suites**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit tests/integration -q
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/ui -q
```
Expected: PASS. UI tests will need their fake updated in Task 8 — if they fail here only because `FakeBackend` no longer matches, note it and fix in Task 8 rather than expanding this task.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(tik.trigger): GuideScene absorbs the backend; split by topic"
```

### Task 6: Rename `Guides` → `GuideLayout`, `handler.py` → `session.py`

**Files:**
- Modify: `src/python/tik/trigger/core/manifest.py` (`class Guides` → `class GuideLayout`)
- Modify: `src/python/tik/trigger/core/__init__.py`, `core/module.py`, `modules/*/*.py`
- Rename: `src/python/tik/trigger/handler.py` → `src/python/tik/trigger/session.py`
- Rename: `tests/unit/test_handler_trigger.py` → `tests/unit/test_session_trigger.py`

**Interfaces:**
- Consumes: Task 5.
- Produces: `tik.trigger.core.GuideLayout`; `tik.trigger.session.Session` / `ActionHandle`. `Module.guides` is still the attribute name — only the class it holds is renamed.

- [ ] **Step 1: Rename the manifest class**

In `core/manifest.py`, `class Guides:` → `class GuideLayout:`, and its `__repr__` returns `f"GuideLayout({...})"`. Update its docstring example:

```python
class GuideLayout:
    """Ordered guide roles a module needs.

    Example:
        GuideLayout("collar", "shoulder", "elbow", "hand")
        GuideLayout("root", multi="segment", min=2)   # root + N segment guides
    """
```

- [ ] **Step 2: Sweep the importers**

```bash
grep -rln "import Guides\|Guides(" --include="*.py" src/python/tik/trigger tests
```
In `core/__init__.py`, `core/module.py` (`guides: GuideLayout = GuideLayout("root")`) and the three modules, `Guides(` → `GuideLayout(`. Take care not to touch `GuideScene`, `GuideHandle`, `GuideFile`, `GuideInstance` or `GuidePose`.

- [ ] **Step 3: Rename the session module**

```bash
git mv src/python/tik/trigger/handler.py src/python/tik/trigger/session.py
git mv tests/unit/test_handler_trigger.py tests/unit/test_session_trigger.py
grep -rln "trigger.handler\|trigger import handler" --include="*.py" src/python/tik tests
```
Rewrite each hit to `tik.trigger.session`.

- [ ] **Step 4: Run all three suites**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit tests/integration -q
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/ui -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(tik.trigger): rename manifest Guides to GuideLayout, handler to session"
```

### Task 7: Fix the stale `core/module.py` documentation

`Module`'s class docstring teaches `plugs = ("collar", "hand")` and `sockets = ("root",)` — attributes that do not exist. It is the first thing anyone reads when learning the framework.

**Files:**
- Modify: `src/python/tik/trigger/core/module.py:1-19`

**Interfaces:**
- Consumes: Task 6's names.
- Produces: nothing (documentation only).

- [ ] **Step 1: Rewrite the module docstring**

```python
"""Module base class.

A module declares what it needs (guides, inputs/outputs, settings) and
implements two methods that touch the scene through the objects the builder
hands them::

    @register_module("arm")
    class Arm(Module):
        label = "Arm"
        guides = GuideLayout("collar", "shoulder", "elbow", "hand")
        inputs = (Input("root", primary=True),)
        outputs = ("collar", "upperarm", "lowerarm", "hand")
        stretch = BoolField(True)

        def draw_guides(self, guides): ...
        def build(self, rig): ...

Everything else — the four groups, naming, tagging, side handling, parenting
under the rig root, materializing a socket per declared input and connecting
it to the producer — is done by ``ModuleRig`` and the builder.
"""
```

- [ ] **Step 2: Verify no other stale names**

```bash
grep -rn "plugs\b\|sockets\b" --include="*.py" src/python/tik/trigger
```
Expected: no hits describing module attributes.

- [ ] **Step 3: Run the unit suite**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit -q
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs(tik.trigger): fix Module docstring teaching attributes that do not exist"
```

### Task 8: Delete the fakes

**Files:**
- Delete: `tests/helpers/trigger_fakes.py`
- Create: `tests/ui/stub.py`
- Modify: `tests/unit/test_core_trigger.py`, `tests/unit/test_runner_trigger.py`, `tests/unit/test_session_trigger.py`, `tests/ui/test_guide_designer.py`, `tests/ui/test_pipeline_ui.py`
- Modify: `tests/conftest.py` (drop the `helpers` path insert if nothing else uses it)

**Interfaces:**
- Consumes: Tasks 4-6.
- Produces: `tests/ui/stub.py` exposing `StubScene` with only what the designer and pipeline windows call.

- [ ] **Step 1: Find what each test actually needs**

```bash
grep -n "FakeBackend\|FakeBuildContext\|FakeGuideContext\|ToyRoot\|ToyChain" tests/unit/*.py tests/ui/*.py
```

- [ ] **Step 2: Move build-shaped unit tests to integration**

Tests in `test_core_trigger.py` that build through `FakeBuildContext` (asserting a controller was created, an output registered, `bind_parent` honoured) move to `tests/integration/trigger/test_builder_trigger.py` and run against a real `GuideScene` and `Builder`. `ToyRoot` / `ToyChain` move with them into that file as real registered modules — a real `Module` subclass with a real `draw_guides` and `build`, cleaned up with `unregister_module` in a fixture:

```python
@pytest.fixture
def toy_modules():
    @register_module("toy_root")
    class ToyRoot(Module):
        label = "Toy Root"
        sided = False
        guides = GuideLayout("root")
        inputs = ()
        outputs = ("root",)
        space_controls = ("root",)

        def draw_guides(self, guides):
            guides.joint("root", (0, 0, 0))

        def build(self, rig):
            rig.controller("root")
            rig.output("root", rig.bind_joint("root", match=rig.guide("root")))

    yield
    unregister_module("toy_root")
```

- [ ] **Step 3: Keep the genuinely pure tests as unit tests**

Tests of the document, the registry, field validation, `order_instances` / `order_by_connections`, `ActionHandle` overrides and the runner's step ordering need no scene at all. Where they constructed a `FakeBackend` only to satisfy a parameter, delete the argument — after Task 5, `Session` and `Builder` take no backend.

- [ ] **Step 4: Write the UI stub**

`tests/ui/stub.py`, ~30 lines, exposing only what the two windows call. Start from the failures and add nothing speculative:

```python
"""Minimal GuideScene stand-in for Qt tests.

Maya standalone cannot host a QApplication, so tests/ui runs with
TIK_TESTS_NO_MAYA=1 and never has a scene. This is an ordinary Qt test
double: it holds instances in a list and records calls.
"""


class StubScene:
    def __init__(self, instances=None):
        self.instances_list = list(instances or [])
        self.calls = []
        self.layout = {}
        self.selection = None

    def instances(self):
        return list(self.instances_list)

    def roots(self):
        return [item for item in self.instances_list if item.instance.parent is None]

    # ... only what the windows call, added as tests demand
```

- [ ] **Step 5: Delete the fakes and run everything**

```bash
git rm tests/helpers/trigger_fakes.py
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit tests/integration -q
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/ui -q
```
Expected: PASS. Total count may shift as tests move between suites; the sum must not drop except for tests deleted as duplicates, which the commit message names.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "test(tik.trigger): delete the fake backend; build tests run against Maya"
```

---

## Phase 3 — The `rig` object

### Task 9: `ModuleRig` and `GuideDraft`, with auto-materialized sockets

**Files:**
- Modify: `src/python/tik/trigger/maya/rig.py`
- Test: `tests/integration/trigger/test_module_ground_rules.py`

**Interfaces:**
- Consumes: Task 8's real-module test fixtures.
- Produces:
  - `GuideDraft(module, holder, parent_node=None)` with `.module`, `.side`, `.side_mult`, `.created`, `.root`, `joint(role, position, *, index=0, parent=None, radius=1.0) -> tm.Joint`.
  - `ModuleRig(module, instance, rig_root, guide_nodes, bind_parent=None)` with `.module`, `.instance`, `.side`, `.side_mult`, `.rig_root`, `.groups`, `.bind_parent`, `.outputs`, `.attachments`, `.controllers`, `.deform_joints`, and methods `guide(role, index=0)`, `guides(*roles)`, `chain(role)`, `name(*tokens, suffix=None)`, `group(*tokens, under="rig")`, `socket(input_name, *, match=None)`, `attach(input_name, node)`, `controller(...)`, `tweak_control(...)`, `controller_by_role(role)`, `bind_joint(...)`, `deform_joint(node)`, `output(name, node)`.

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/trigger/test_module_ground_rules.py`:

```python
def test_every_declared_input_gets_a_socket(scene, toy_modules):
    """Declaring an input materializes one tagged Transform in socket_grp."""
    chain = scene.add("toy_chain", name="tail")
    report = Builder().build(afterlife="keep")
    rig = report.rigs[chain.instance_id]

    socket = rig.socket("root")
    assert socket.parent.long_name == rig.groups.socket.long_name
    assert socket.meta.get(tags.KIND) == tags.INPUT
    assert cmds.nodeType(socket.long_name) == "transform"


def test_space_inputs_get_no_socket(scene, toy_modules):
    """Anim-space inputs are consumed by a SpaceSwitch, not a matrix attach."""
    root = scene.add("toy_root", name="body")
    chain = scene.add("toy_chain", name="tail", parent=root,
                      anim_spaces=[{"control": "fk0", "mode": "parent", "label": "world"}])
    report = Builder().build(afterlife="keep")
    rig = report.rigs[chain.instance_id]

    assert "fk0_world" not in rig.attachments
```

- [ ] **Step 2: Run to verify it fails**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration/trigger/test_module_ground_rules.py -q
```
Expected: FAIL — `rig.socket` does not exist.

- [ ] **Step 3: Rename the classes and add the new vocabulary**

In `maya/rig.py`, `MayaGuideContext` → `GuideDraft`, `MayaBuildContext` → `ModuleRig`. Then:

```python
    def __init__(self, module, instance, rig_root, guide_nodes, bind_parent=None) -> None:
        self.module = module
        self.instance = instance
        self.side = module.side
        self.side_mult = module.side.multiplier
        self.rig_root = rig_root
        self._guides = guide_nodes  # (role, index) -> Joint
        self.outputs: dict[str, Any] = {}
        self.attachments: dict[str, Any] = {}
        self.controllers: list[Controller] = []
        self.deform_joints: list[tm.Joint] = []
        self.groups = self._create_groups()
        # Resolved by the builder from the connected input's producer, so bind
        # joints are created in their final hierarchy position.
        self.bind_parent = bind_parent if bind_parent is not None else self.groups.bind
        self._create_sockets()

    def _create_sockets(self) -> None:
        """One Transform per declared input, in socket_grp.

        Declaring an input is what creates its socket, so a module cannot
        forget to. Space inputs are excluded: they are consumed by a
        SpaceSwitch on a controller, not by a matrix attach.
        """
        for declared in self.module.inputs:
            if declared.kind == "space":
                continue
            self.attachments[declared.name] = tm.Transform.create(
                name=self.name(declared.name, suffix="socket"),
                parent=self.groups.socket.long_name,
            )

    def socket(self, input_name: str, *, match=None) -> tm.Transform:
        """The socket for a declared input, optionally aligned to ``match``."""
        try:
            node = self.attachments[input_name]
        except KeyError:
            raise GuideError(
                f"'{self.module.module_type}' does not declare input '{input_name}'."
            ) from None
        if match is not None:
            node.align_to(match)
        return node

    def attach(self, input_name: str, node) -> None:
        """Re-point an input at a node you built yourself."""
        if self.module.get_input(input_name) is None:
            raise GuideError(
                f"'{self.module.module_type}' does not declare input '{input_name}'."
            )
        self.attachments[input_name] = node

    def guides(self, *roles: str) -> list:
        """One guide node per named role, in the order given."""
        return [self.guide(role) for role in roles]

    def chain(self, role: str) -> list:
        """Every guide of a multi role, ordered by index."""
        pairs = sorted(key for key in self._guides if key[0] == role)
        return [self._guides[key] for key in pairs]

    def group(self, *tokens, under="rig") -> tm.Transform:
        """A named, placed group. ``under`` is a group name or a node."""
        parent = getattr(self.groups, under) if isinstance(under, str) else under
        return tm.Transform.create(
            name=self.name(*tokens, suffix="grp"),
            parent=parent.long_name if hasattr(parent, "long_name") else parent,
        )
```

The old single-role `guides(role)` is replaced by `chain(role)`; `guide()`, `name()`, `bind_joint()`, `deform_joint()`, `output()`, `controller_by_role()` keep their current bodies.

- [ ] **Step 4: Tag the sockets at finalize**

`maya/build.py`'s `finalize` already tags `ctx.attachments` with `trg_kind=input`; confirm it still runs for auto-created sockets (it iterates the same dict, so it does) and that its loop reads `rig.attachments`.

- [ ] **Step 5: Run the test**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration -q
```
Expected: the two new tests PASS. Existing module tests may fail because modules still call `ctx.attach("root", socket)` after building their own — that is Task 11's job; if so, stop here with only the two new tests green and note it, or land Tasks 9-11 as one commit.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(tik.trigger): ModuleRig with sockets materialized from declared inputs"
```

### Task 10: Automatic offset groups on controllers

**Files:**
- Modify: `src/python/tik/trigger/maya/rig.py`
- Test: `tests/integration/trigger/test_module_ground_rules.py`

**Interfaces:**
- Consumes: Task 9's `ModuleRig`.
- Produces: `rig.controller(...)` returns a `Controller` with an `.offset` attribute (a `tm.Transform`) unless `offset=False`. `rig.tweak_control(...)` passes `offset=False`.

- [ ] **Step 1: Write the failing test**

```python
def test_controller_comes_with_an_offset_group(scene, toy_modules):
    """Every controller gets its offset group; control_grp holds only those."""
    root = scene.add("toy_root", name="body")
    report = Builder().build(afterlife="keep")
    rig = report.rigs[root.instance_id]

    control = rig.controller_by_role("root")
    assert control.offset is not None
    assert control.parent.long_name == control.offset.long_name
    assert control.offset.parent.long_name == rig.groups.control.long_name
```

- [ ] **Step 2: Run to verify it fails**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration/trigger/test_module_ground_rules.py::test_controller_comes_with_an_offset_group -q
```
Expected: FAIL with `AttributeError` — `Controller.__getattr__` forwards `offset` to the node, which has no such attribute.

- [ ] **Step 3: Create the offset inside `rig.controller`**

```python
    def controller(
        self,
        name: str,
        *,
        shape: str = "Circle",
        size: float = 1.0,
        parent: Any = None,
        color: Any = None,
        match: Any = None,
        mirror: str = "world",
        offset: bool = True,
    ) -> Controller:
        """A tagged controller, with its offset group.

        ``match`` snaps it to a node. ``mirror`` is ``"behaviour"`` (FK-like,
        follows its joint) or ``"world"`` (IK/world-aligned), recorded for a
        pose-mirror tool. ``offset=False`` skips the offset group, for a
        controller parented under another (a tweak).
        """
        parent = parent if parent is not None else self.groups.control
        controller = Controller.create(
            name=self.name(name, suffix="ctrl"),
            shape=shape,
            size=size,
            color=color if color is not None else SIDE_COLORS[self.side],
            parent=parent.long_name if hasattr(parent, "long_name") else parent,
        )
        if match is not None:
            controller.align_to(match)
        tags.tag(
            controller.node,
            **{
                tags.KIND: tags.CONTROLLER,
                tags.INSTANCE: self.instance.instance_id,
                tags.ROLE: name,
                tags.MIRROR: mirror,
            },
        )
        controller.offset = (
            controller.create_offset_group(name=self.name(name, suffix="offset"))
            if offset
            else None
        )
        self.controllers.append(controller)
        return controller
```

`Controller.create_offset_group` reaches the transform through `__getattr__`, and `Transform.create_offset_group` re-parents the offset under the controller's original parent, so the controller stays in `control_grp` via its offset.

`tweak_control` passes `offset=False` and keeps its current body otherwise, with `main.transform` reduced to `main`.

- [ ] **Step 4: Run the test**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration -q
```
Expected: the new test PASSES.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(tik.trigger): rig.controller creates its own offset group"
```

### Task 11: Rewrite the modules against `rig`

**Files:**
- Modify: `src/python/tik/trigger/modules/base/base.py`, `modules/fkchain/fkchain.py`, `modules/arm/arm.py`
- Test: `tests/integration/trigger/test_arm_trigger.py`, `test_module_ground_rules.py`

**Interfaces:**
- Consumes: Tasks 9-10.
- Produces: `draw_guides(self, guides)` and `build(self, rig)` on all three modules.

- [ ] **Step 1: Rewrite `base`**

```python
    def draw_guides(self, guides) -> None:
        guides.joint("root", (0, 0, 0), radius=2.0)

    def build(self, rig) -> None:
        root_guide = rig.guide("root")
        controller = rig.controller(
            "root", shape="Circle", size=self.controller_size,
            match=root_guide, mirror="world",
        )
        joint = rig.bind_joint("root", match=root_guide)
        tm.MatrixConstraint.create(controller, joint, maintain_offset=True)
        rig.output("root", joint)
```

- [ ] **Step 2: Rewrite `fkchain`**

```python
    def draw_guides(self, guides) -> None:
        previous = guides.joint("root", (0, 0, 0))
        for index in range(self.segments):
            offset = self.spacing * (index + 1) * guides.side_mult
            previous = guides.joint("segment", (offset, 0, 0), index=index, parent=previous)

    def build(self, rig) -> None:
        guide_nodes = [rig.guide("root"), *rig.chain("segment")]
        socket = rig.socket("root", match=guide_nodes[0])

        # Bind joints are created in their final hierarchy position: the root
        # falls back to rig.bind_parent, which is the connected producer's bind
        # joint when this chain is attached to another module.
        joints = []
        parent_joint = None
        for index, guide_node in enumerate(guide_nodes):
            joint = rig.bind_joint(str(index), parent=parent_joint, match=guide_node)
            joints.append(joint)
            parent_joint = joint

        # Controllers live in control_grp and are *driven* by the socket, never
        # parented under it: control_grp holds nothing but controllers and their
        # offset groups.
        parent = None
        for index, joint in enumerate(joints[:-1]):
            controller = rig.controller(
                f"fk{index}", size=self.controller_size,
                parent=parent, match=joint, mirror="behaviour",
            )
            if parent is None:
                tm.MatrixConstraint.create(socket, controller.offset, maintain_offset=True)
            tm.MatrixConstraint.create(controller, joint, maintain_offset=True)
            parent = controller

        rig.output("root", joints[0])
        for index, joint in enumerate(joints[1:]):
            rig.output(f"segment{index + 1}", joint)
        rig.output("end", joints[-1])
```

Note `parent=parent` is now passed straight through: `rig.controller` already defaults to `groups.control` when it is `None`.

- [ ] **Step 3: Rewrite `arm`**

```python
    def draw_guides(self, guides) -> None:
        mult = guides.side_mult
        collar = guides.joint("collar", (2 * mult, 0, 0), radius=1.5)
        shoulder = guides.joint("shoulder", (5 * mult, 0, 0), parent=collar)
        elbow = guides.joint("elbow", (9 * mult, 0, -1), parent=shoulder)
        guides.joint("hand", (14 * mult, 0, 0), parent=elbow)

    def build(self, rig) -> None:
        collar_guide = rig.guide("collar")
        limb_guides = rig.guides("shoulder", "elbow", "hand")
        size = _derive_size(limb_guides)

        socket = rig.socket("root", match=collar_guide)

        # deform skeleton — created in final position, never reparented -------
        collar_jnt = rig.bind_joint("collar", match=collar_guide)
        bind_joints = []
        parent_joint = collar_jnt
        for label, guide_node in zip(("upperarm", "lowerarm", "hand"), limb_guides):
            joint = rig.bind_joint(label, parent=parent_joint, match=guide_node)
            bind_joints.append(joint)
            parent_joint = joint

        # collar ---------------------------------------------------------------
        # The controller lives in control_grp and is driven by the socket rather
        # than parented under it: control_grp holds nothing but controllers and
        # their offset groups.
        collar_ctrl = rig.controller(
            "collar", shape="CurvedCircle", size=size,
            match=collar_jnt, mirror="behaviour",
        )
        tm.MatrixConstraint.create(socket, collar_ctrl.offset, maintain_offset=True)
        tm.MatrixConstraint.create(collar_ctrl, collar_jnt, maintain_offset=True)
        attribute.lock_and_hide(collar_ctrl, ("sx", "sy", "sz", "v"))

        # the limb -------------------------------------------------------------
        limb = build_ikfk_limb(
            rig, limb_guides, parent=collar_ctrl, bind_joints=bind_joints,
            soft_ik=True,  # never optional for an IK solution
            stretch=self.stretch, squash=self.squash, pole_pin=self.pole_pin,
            labels=("upper", "lower", "hand"),
        )
        if self.auto_collar:
            auto_grp = rig.group("collar", "auto", under=collar_ctrl.offset)
            auto_grp.snap_to(collar_ctrl)
            # Relative, so set_parent writes no compensation into the channels.
            collar_ctrl.set_parent(auto_grp, relative=True)
            build_reach(
                rig, auto_grp, socket, limb.ik_tweak, limb.ik_control,
                prefix="autoCollar", start_angle=self.auto_collar_start,
                end_angle=self.auto_collar_end,
                interpolation=self.auto_collar_interpolation, name="collar",
            )

        rig.output("collar", collar_jnt)
        rig.output("upperarm", bind_joints[0])
        rig.output("lowerarm", bind_joints[1])
        rig.output("hand", bind_joints[2])
```

- [ ] **Step 4: Run the integration suite**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration -q
```
Expected: FAIL only inside `systems/limb.py` and `systems/reach.py`, which still take `ctx` and use `.transform` — Task 12. If the failures are anywhere else, the module rewrite changed behaviour; fix it here.

- [ ] **Step 5: Commit (after Task 12 is green)**

Modules and systems are one behavioural unit; commit them together at the end of Task 12.

### Task 12: Rewrite the systems against `rig`

**Files:**
- Modify: `src/python/tik/trigger/systems/limb.py`, `systems/reach.py`
- Test: `tests/integration/trigger/test_limb_system.py`, `test_reach_system.py`, `test_arm_trigger.py`

**Interfaces:**
- Consumes: Tasks 9-11.
- Produces: `build_ikfk_limb(rig, guides, *, name="", parent=None, bind_joints=None, controller_size=None, soft_ik=True, stretch=True, squash=True, stretch_limit_default=50.0, pole_pin=False, labels=None) -> LimbResult`; `build_reach(rig, base_group, rest_from, target, control, *, prefix="autoReach", start_angle=0.0, end_angle=90.0, interpolation="smooth", name=None) -> None`. `LimbResult` fields unchanged; its controller fields hold `Controller` objects used without `.transform`.

- [ ] **Step 1: Rename the parameter throughout**

In both files, `ctx` → `rig` in every signature and body (`build_ikfk_limb`, `_build_chains`, `_build_pole_base`, `_build_controls`, `_build_lengths`, `_build_soft_ik`, `_build_stretch`, `_build_pole`, `_build_visibility`, `_blend_to_bind`, `build_reach`). Update the docstring Args entries: `ctx: The module build context.` → `rig: The module's ``ModuleRig``.`, and `parent: ... defaults to ``ctx.groups.socket``.` → `` rig.groups.socket ``.

- [ ] **Step 2: Apply the vocabulary**

- `ctx.groups.rig.long_name` / `ctx.groups.control` as a `parent=` argument → pass the node; `rig.group(...)` where a named group is being created. `limb.py:154` becomes `result.puppet_group = rig.group(name, "puppet", under="rig")`.
- `.transform` drops off every `Controller` use: `result.ik_control.transform` → `result.ik_control`, `fk_control.transform` → `fk_control`, `control.transform` in `reach.py` → `control`.
- The manual offset groups at `limb.py:204, 232, 379` are deleted — `rig.controller` creates them; use `result.ik_control.offset`, `fk_control.offset`, `result.pole_control.offset`.
- `_role()` (limb.py:459) stays: it exists to avoid a doubled underscore once `rig.name` prefixes the instance name.

- [ ] **Step 3: Run the integration suite**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration -q
```
Expected: PASS. `test_arm_trigger.py`, `test_limb_system.py`, `test_reach_system.py` and `test_module_ground_rules.py` are the proof the rewrite preserved behaviour — their assertions must not be weakened, only their API calls updated (`build_context()` helpers in the test files become real builds or `ModuleRig` constructions).

- [ ] **Step 4: Run everything**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit tests/integration -q
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/ui -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(tik.trigger): modules and systems build through rig"
```

### Task 13: Simplify the builder

**Files:**
- Modify: `src/python/tik/trigger/maya/build.py`
- Test: `tests/integration/trigger/test_builder_trigger.py`

**Interfaces:**
- Consumes: Task 9 (sockets always exist).
- Produces: `BuildReport.rigs` (was `.contexts`); `Builder.resolve(source, by_key, report, *, strict=True, where="")`.

- [ ] **Step 1: Rename `BuildReport.contexts` → `rigs`**

```python
@dataclass
class BuildReport:
    """What happened during a build."""

    built: list[str] = field(default_factory=list)  # instance ids in build order
    rigs: dict = field(default_factory=dict)  # instance id -> ModuleRig
    connections: list[tuple[str, str]] = field(default_factory=list)  # ("L_arm.root", "body.root")
    spaces: list[tuple[str, str]] = field(default_factory=list)  # ("L_arm.ik_chest", "body.root")
    rig_root: Any = None
```

Sweep `report.contexts` in `build.py` and the tests.

- [ ] **Step 2: Merge the two resolvers**

```python
    def resolve(self, source: str, by_key: dict, report: BuildReport, *,
                strict: bool = True, where: str = ""):
        """The node a source names, or None when ``strict`` is False and it is missing.

        A source is ``"<module key>.<output>"`` or a bare scene node name.
        """
        key, output = split_source(source)
        if key is not None and key in by_key:
            producer_rig = report.rigs.get(by_key[key].instance_id)
            node = producer_rig.outputs.get(output) if producer_rig else None
            if node is None and strict:
                available = sorted(producer_rig.outputs) if producer_rig else []
                raise AttachError(
                    f"{where}: source '{source}' was not built "
                    f"(available outputs: {available}).",
                )
            return node
        node = nodes.scene_node(source)
        if node is None and strict:
            raise AttachError(
                f"{where}: source '{source}' is neither a built module output "
                f"nor an existing scene node.",
            )
        return node
```

`_connect_one` calls it with `strict=True, where=f"{instance.key}.{declared.name}"`; `_connect_spaces` with `strict=False` and warns on `None`. Delete `_resolve_source` and `_resolve_space_source`. Keep `AttachError`'s `instance_id` / `module_type` kwargs by passing them through from the call sites.

- [ ] **Step 3: Delete the attach check**

In `_connect_one`, remove the block that raises `AttachError: module did not call ctx.attach()` — after Task 9 the socket always exists:

```python
            node = self.resolve(source, by_key, report, where=f"{instance.key}.{declared.name}")
            connect(rig, declared.name, node)
            report.connections.append((f"{instance.key}.{declared.name}", source))
```

- [ ] **Step 4: Run the tests**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit tests/integration -q
```
Expected: PASS. The two ordering passes and the separate space pass are untouched — confirm the comments explaining why spaces stay out of the topological sort are still present.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(tik.trigger): simplify the builder now that sockets are guaranteed"
```

---

## Phase 4 — UI

### Task 14: Split `graph_view.py` into `ui/graph/`

**Files:**
- Create: `src/python/tik/trigger/ui/graph/__init__.py`, `items.py`, `scene.py`, `view.py`
- Delete: `src/python/tik/trigger/ui/graph_view.py`
- Modify: `src/python/tik/trigger/ui/guide_designer.py` (import site)
- Test: `tests/ui/test_guide_designer.py`

**Interfaces:**
- Consumes: Task 8's `StubScene`.
- Produces: `tik.trigger.ui.graph` exporting `GraphView`, `GraphScene`, `NodeItem`, `Port`, `WireItem`, and the mode constants (`MODE_FULL` and its siblings). Import sites keep using `GraphView(...)` unchanged.

- [ ] **Step 1: Move the classes verbatim**

- `items.py` — `Port` (44-89), `NodeItem` (91-216), `WireItem` (218-259), plus the geometry/colour constants they read.
- `scene.py` — `GraphScene` (261-475).
- `view.py` — `GraphView` (477-915).

Module-level constants stay next to their primary user and are imported where needed. No logic changes: this is a cut-and-paste plus imports.

- [ ] **Step 2: Write `ui/graph/__init__.py`**

```python
"""The module I/O node graph."""

from .items import NodeItem, Port, WireItem
from .scene import GraphScene
from .view import GraphView

__all__ = ["GraphScene", "GraphView", "NodeItem", "Port", "WireItem"]
```

Re-export any mode constant the designer imports (check with `grep -n "from .graph_view import\|graph_view\." src/python/tik/trigger/ui/*.py`).

- [ ] **Step 3: Run the UI tests**

```bash
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/ui -q
```
Expected: PASS at the Task 8 count.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(tik.trigger): split graph_view into ui/graph"
```

### Task 15: Split `guide_designer.py` into `ui/designer/`

**Files:**
- Create: `src/python/tik/trigger/ui/designer/__init__.py`, `window.py`, `tree.py`, `properties.py`, `scene_nodes.py`, `commands.py`
- Delete: `src/python/tik/trigger/ui/guide_designer.py`
- Modify: `src/python/tik/trigger/ui/main.py:343` (import site)
- Test: `tests/ui/test_guide_designer.py`

**Interfaces:**
- Consumes: Task 14.
- Produces: `tik.trigger.ui.designer.GuideDesigner`, constructed as `GuideDesigner(parent=None, events=None, file_browser=None, binding_adapter=None)` — the `backend` parameter is gone; it builds its own `GuideScene`.

- [ ] **Step 1: Move the leaf widgets first**

`tree.py` gets `GuideTree` (60-120) and `module_entries()` (49-58). `scene_nodes.py` gets `SceneNodesPanel` (206-294). `properties.py` gets `InputRow` (121-205). Run the UI tests after this step alone — three self-contained classes, no `GuideDesigner` changes yet.

- [ ] **Step 2: Split `GuideDesigner` by method cluster**

`commands.py` holds the verbs as a mixin (`DesignerCommands`): `create_guides`, `reparent`, `connect_dialog`, `sever_current`, `disconnect_primary`, `select_root`, `select_current`, `mirror_current`, `duplicate_current`, `delete_current`, `clear_guides`, `test_build`, `export_file`, `import_file`, `_pick`, `_rename_current`.

`properties.py` gains `DesignerProperties`: `_plug_adapter`, `_on_inherit_toggled`, `_bind_properties`, `_source_choices`, `_selected_scene_nodes`, `_pick_source`, `_on_input_changed`, `_topology`, `_on_setting_changed`, `_on_scene_nodes_changed`.

`window.py` keeps the rest — construction, `_build_central`, `_build_menus`, `_build_status`, refresh, selection sync, `closeEvent` — and composes:

```python
class GuideDesigner(DesignerCommands, DesignerProperties, MayaToolWindow):
```

The mixin-parent ordering matters: `MayaToolWindow` must come last so its `__init__` and Qt metaclass win.

- [ ] **Step 3: Drop the `backend` parameter**

```python
    def __init__(self, parent=None, events=None, file_browser=None, binding_adapter=None) -> None:
        ...
        self.guides = GuideScene(events=self.events)
```

Update `ui/main.py:343` (`open_guide_designer`) accordingly.

- [ ] **Step 4: Run the UI tests**

```bash
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/ui -q
```
Expected: PASS. `tests/ui/test_guide_designer.py` injects `StubScene`; add a `scene=` injection point to `__init__` if the tests need it (`self.guides = scene or GuideScene(events=self.events)`).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(tik.trigger): split guide_designer into ui/designer"
```

### Task 16: Drop the remaining backend parameters from the UI

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py:27, 181, 373`, `ui/session_view.py:344`, `ui/shelf.py` if it takes one
- Test: `tests/ui/test_pipeline_ui.py`

**Interfaces:**
- Consumes: Tasks 5, 15.
- Produces: `show(dockable: bool = True) -> TriggerWindow`; `TriggerWindow(parent=None, file_browser=None)`; `Session.open(path, events=...)` without `backend=`.

- [ ] **Step 1: Rewrite the entry point**

```python
def show(dockable: bool = True) -> TriggerWindow:
```

and `TriggerWindow.__init__(self, parent=None, file_browser=None)`. Inside, `Session.open(path, events=self.events)`.

- [ ] **Step 2: Fix the `ActionContext` construction**

`ui/session_view.py:344` drops `backend=self.session.backend`.

- [ ] **Step 3: Run the UI tests**

```bash
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/ui -q
```
Expected: PASS.

- [ ] **Step 4: Grep for stragglers**

```bash
grep -rn "backend" --include="*.py" src/python/tik/trigger
```
Expected: no hits outside comments describing history. Any survivor is a missed call site.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(tik.trigger): UI constructs its own GuideScene"
```

---

## Phase 5 — Documentation

### Task 17: Update the project documentation

**Files:**
- Modify: `CLAUDE.md`, `AGENTS.md`, `AI/coding_rules.md`
- Modify: `docs/superpowers/specs/2026-08-28-trigger-rebuild-design.md`, `2026-08-29-trigger-ui-v3-and-io-graph-design.md` (status notes pointing at the new spec)

**Interfaces:**
- Consumes: every prior task.
- Produces: documentation matching the code.

- [ ] **Step 1: Update `CLAUDE.md`**

- The tik.trigger structure section: `.tr`/`.trg` unchanged; replace "Backend boundary — `tik/trigger/backends/maya` is the only Maya-touching layer" with "Maya-only: `tik/trigger/core` is pure Python; everything else may use tik.maya."
- The layering rule line: "`tik/trigger/core` imports no Maya/Qt (enforced by `tests/unit/test_import_boundaries.py`)" — drop the `session` mention.
- The tests table: `test_handler_trigger.py` → `test_session_trigger.py`, `test_maya_backend_trigger.py` → `test_guide_scene_trigger.py`; note that build tests live in `tests/integration/trigger/` and shared fakes no longer exist.
- Module ground rules: add that sockets are materialized from declared inputs.

- [ ] **Step 2: Update `AI/coding_rules.md`**

Record the boundary rule verbatim: "`rig` owns naming, tagging, group placement and registration. tik.maya owns mechanism. A helper that does not remove naming, tagging, placement or registration boilerplate does not go on `rig`." Add the module skeleton with `draw_guides(self, guides)` / `build(self, rig)`.

- [ ] **Step 3: Mark the superseded specs**

Add a line under each older spec's `Status:` pointing at `2026-08-30-trigger-simplification-design.md` for the parts it replaces (the backend boundary in the rebuild spec; the UI file layout in the UI v3 spec — its §3 module I/O model still stands).

- [ ] **Step 4: Verify the whole suite one last time**

```bash
make tests
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/ui -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs(tik.trigger): document the Maya-only layering and the rig object"
```
