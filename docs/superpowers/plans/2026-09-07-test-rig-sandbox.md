# Test Rig Sandbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Guide Designer's Build / Build All their own throwaway rig, so a mock-up never touches the real one and pressing Build repeatedly always yields exactly one copy.

**Architecture:** A second scaffold rooted at `|test_rig_grp`, whose root and per-module groups are Maya `dagContainer`s. A container captures every node created while it is current — DAG *and* DG — so teardown of one module is `cmds.delete(container)`, and teardown of the whole rig is `cmds.delete("test_rig_grp")`. `Builder` sets a module's container current around its build and its own connect wiring; module code and tik.maya are untouched. Scope expansion (which modules a scoped build must tear down and rebuild) is pure Python over the guide document's inputs.

**Tech Stack:** Python 3.10+, Maya 2024+ (verified on 2026), `maya.cmds` via tik.maya wrappers, pytest under `mayapy`.

**Spec:** `docs/superpowers/specs/2026-09-07-test-rig-sandbox-design.md`

## Global Constraints

- **Consume tik.maya** — no raw `maya.cmds` / `OpenMaya` outside `tik/maya`, except where this repo already does so for whole-scene scans (`guides/nodes.py`) and for commands tik.maya does not wrap. `cmds.container` has no tik.maya wrapper; calling it directly from `tik/trigger/maya/sandbox.py` is correct and matches how `scaffold.py` already calls `cmds.objExists`.
- **`tik/trigger/core` is pure Python** — no Maya, no Qt. Enforced by `tests/unit/test_import_boundaries.py`.
- **Preferences never change the rig** — the build path may not import `tik.trigger.config.prefs`. Same enforcing test.
- **No third-party deps** — stdlib and Maya-bundled modules only.
- **One dialog surface** — any user dialog goes through `tik.shared.ui.feedback.Feedback`.
- **Style** — black, isort (profile black), flake8. Run `make lint` before the final commit.
- **Docstrings** — every public function gets one; this repo's docstrings say *why*, not just *what*.
- No file under `src/` may carry a `test_` prefix (pytest collection hazard) — hence `sandbox.py`.

### Commands

Run a single test file (from the repo root):

```bash
PYTHONPATH="D:/dev/tikworks/src/python" MAYA_PLUG_IN_PATH="D:/dev/tikworks/src/plugins/python" \
  "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_build_scope_trigger.py -q
```

Full suites: `make tests-unit`, `make tests-integration`, `make tests-ui`, `make lint`.

### Measured Maya facts this plan relies on

Established by probe on Maya 2026; do not re-derive, and do not "fix" code that depends on them:

1. `container -current` captures nodes created by `cmds`, `MDagModifier` **and** `MDGModifier`.
2. Deleting a container deletes its members, DG nodes included.
3. A `dagContainer` **is** a transform, and **auto-adopts its DAG children as members** even when it is not current. Deleting the root therefore takes nested containers' DG members too — `clear()` is one `cmds.delete`.
4. `container -e -current False` does **not** restore an outer container; it sets current to `""`. The context manager must save and restore the previous value itself.
5. `dagContainer` inherits `transform`, so `tm.resolve` returns a `Transform` with working plugs, `.meta` and `.long_name`. tik.maya needs no change.
6. `cmds.ls(type="container")` does **not** list a `dagContainer`; use `ls(type="dagContainer")` or `ls(containers=True)`.
7. A wildcard `cmds.ls("*.attr")` does not cross namespace boundaries — which is why there is no namespace.

---

### Task 1: Build scope expansion (pure)

**Files:**
- Create: `src/python/tik/trigger/core/build_scope.py`
- Test: `tests/unit/test_build_scope_trigger.py`

**Interfaces:**
- Consumes: `tik.trigger.core.registry.get_module`, `tik.trigger.core.exceptions.NotFoundError`, `tik.trigger.core.schemas.split_source`, `ModuleEntry` (duck-typed: `.instance_id`, `.module_type`, `.settings`, `.inputs`).
- Produces: `expand_build_scope(entries, ids, already_built=()) -> list[str]`.

**Context:** Cross-module parenting is stored *as the primary input*, so `ModuleEntry.inputs` (`{input name: "<producer uuid>.<output>"}`) is the whole graph. Space inputs must be excluded — they are legitimately mutually referential, exactly as `Builder.build`'s `structural_inputs` excludes them.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_build_scope_trigger.py`:

```python
"""Which modules a scoped test build tears down and rebuilds."""

import pytest
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module
from tik.trigger.core.build_scope import expand_build_scope
from tik.trigger.core.guide_document import ModuleEntry


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


def _entry(instance_id, name, inputs=None, module_type="toy_chain", settings=None):
    return ModuleEntry(
        instance_id=instance_id,
        module_type=module_type,
        name=name,
        side="C",
        settings=dict(settings or {}),
        inputs=dict(inputs or {}),
    )


def _chain():
    """body -> arm -> hand, each consuming the one before it."""
    body = _entry("id_body", "body", module_type="toy_root")
    arm = _entry("id_arm", "arm", inputs={"root": "id_body.root"})
    hand = _entry("id_hand", "hand", inputs={"root": "id_arm.tip"})
    return [body, arm, hand]


def test_an_unconnected_module_is_its_own_scope():
    entries = [_entry("id_solo", "solo", module_type="toy_root")]
    assert expand_build_scope(entries, ["id_solo"]) == ["id_solo"]


def test_an_unbuilt_producer_is_pulled_in():
    """Building the arm alone must not fail on a required input."""
    assert expand_build_scope(_chain(), ["id_arm"]) == ["id_body", "id_arm"]


def test_an_already_built_producer_is_left_alone():
    """The common loop: body built, tweak the arm, rebuild the arm only."""
    scope = expand_build_scope(_chain(), ["id_arm"], already_built={"id_body"})
    assert scope == ["id_arm"]


def test_a_built_consumer_is_rebuilt_with_its_producer():
    """Its attach would otherwise point at deleted nodes."""
    scope = expand_build_scope(
        _chain(), ["id_arm"], already_built={"id_body", "id_arm", "id_hand"}
    )
    assert scope == ["id_arm", "id_hand"]


def test_an_unbuilt_consumer_is_left_alone():
    """Nothing dangles, so nothing is built behind the rigger's back."""
    scope = expand_build_scope(_chain(), ["id_arm"], already_built={"id_body", "id_arm"})
    assert scope == ["id_arm"]


def test_downstream_repair_is_transitive():
    scope = expand_build_scope(
        _chain(), ["id_body"], already_built={"id_body", "id_arm", "id_hand"}
    )
    assert scope == ["id_body", "id_arm", "id_hand"]


def test_the_scope_is_returned_in_document_order():
    entries = _chain()
    scope = expand_build_scope(
        entries, ["id_hand"], already_built={"id_body", "id_arm", "id_hand"}
    )
    assert scope == ["id_hand"]
    scope = expand_build_scope(entries, ["id_hand"])
    assert scope == ["id_body", "id_arm", "id_hand"]


def test_space_inputs_do_not_pull_a_module_into_scope():
    """Spaces are mutually referential; only structural inputs are the graph."""
    body = _entry("id_body", "body", module_type="toy_root")
    arm = _entry(
        "id_arm",
        "arm",
        inputs={"ik_world": "id_body.root"},
        settings={"anim_spaces": [{"control": "ik", "label": "world", "mode": "parent"}]},
    )
    assert expand_build_scope([body, arm], ["id_arm"]) == ["id_arm"]


def test_an_unknown_module_type_treats_every_input_as_structural():
    """A module the registry has never heard of must not crash the scope."""
    body = _entry("id_body", "body", module_type="toy_root")
    arm = _entry("id_arm", "arm", inputs={"root": "id_body.root"}, module_type="ghost")
    assert expand_build_scope([body, arm], ["id_arm"]) == ["id_body", "id_arm"]


def test_a_bare_scene_node_source_has_no_producer():
    arm = _entry("id_arm", "arm", inputs={"root": "some_locator"})
    assert expand_build_scope([arm], ["id_arm"]) == ["id_arm"]


def test_a_cycle_terminates():
    one = _entry("id_one", "one", inputs={"root": "id_two.tip"})
    two = _entry("id_two", "two", inputs={"root": "id_one.tip"})
    scope = expand_build_scope([one, two], ["id_one"], already_built={"id_one", "id_two"})
    assert scope == ["id_one", "id_two"]


def test_ids_not_in_the_document_are_ignored():
    assert expand_build_scope(_chain(), ["id_ghost"]) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" \
  -m pytest tests/unit/test_build_scope_trigger.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'tik.trigger.core.build_scope'`.

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/trigger/core/build_scope.py`:

```python
"""Which modules a scoped test build must tear down and rebuild.

Pure Python over the guide document's inputs, so it is unit-testable with no
Maya. Cross-module parenting is stored *as the primary input*, which makes
``ModuleEntry.inputs`` the whole graph.

Space inputs are excluded, exactly as ``Builder.build``'s ``structural_inputs``
excludes them: an arm in head space while the head sits in arm space is a normal
rig, and letting that reach the traversal would drag half the rig into scope.
"""

from __future__ import annotations

from typing import Iterable

from . import registry
from .exceptions import NotFoundError
from .schemas import split_source


def _structural_producers(entry) -> list[str]:
    """The instance ids ``entry`` structurally consumes."""
    skip: set = set()
    try:
        module_cls = registry.get_module(entry.module_type)
    except NotFoundError:
        # Unregistered: it cannot build either, but refusing to compute a
        # scope would turn a build error into an unrelated crash here.
        module_cls = None
    if module_cls is not None:
        skip = {item.name for item in module_cls.space_inputs(entry.settings)}
    found = []
    for name, source in (entry.inputs or {}).items():
        if name in skip or not source:
            continue
        producer, _output = split_source(source)
        if producer:
            found.append(producer)
    return found


def expand_build_scope(
    entries: Iterable, ids: Iterable[str], already_built: Iterable[str] = ()
) -> list[str]:
    """The instance ids a scoped test build must tear down and rebuild.

    Downstream, to repair: a consumer that is **already built** is rebuilt, so
    the test rig never holds an attach pointing at deleted nodes. A consumer
    that is not built has nothing to dangle and is left alone rather than built
    behind the rigger's back.

    Upstream, to fill gaps: a producer joins the scope only when it is not
    already built. That keeps the common loop -- body built, tweak the arm,
    rebuild the arm -- from rebuilding the world, while a first build of an arm
    on its own still works instead of failing on a required input.

    Args:
        entries: The guide document's modules, in document order.
        ids: The instance ids the rigger picked.
        already_built: Instance ids that currently have a container in the
            test rig.

    Returns:
        The instance ids to build, in document order.
    """
    entries = list(entries)
    order = [entry.instance_id for entry in entries]
    known = set(order)
    producers: dict = {}
    consumers: dict = {}
    for entry in entries:
        sources = [
            producer
            for producer in _structural_producers(entry)
            if producer in known and producer != entry.instance_id
        ]
        producers[entry.instance_id] = sources
        for producer in sources:
            consumers.setdefault(producer, []).append(entry.instance_id)

    built = set(already_built)
    wanted = {instance_id for instance_id in ids if instance_id in known}

    stack = list(wanted)
    while stack:  # downstream: built consumers only
        for consumer in consumers.get(stack.pop(), ()):
            if consumer in wanted or consumer not in built:
                continue
            wanted.add(consumer)
            stack.append(consumer)

    stack = list(wanted)
    while stack:  # upstream: unbuilt producers only
        for producer in producers.get(stack.pop(), ()):
            if producer in wanted or producer in built:
                continue
            wanted.add(producer)
            stack.append(producer)

    return [instance_id for instance_id in order if instance_id in wanted]
```

- [ ] **Step 4: Run the tests to verify they pass**

Same command as Step 2. Expected: 12 passed.

If `test_space_inputs_do_not_pull_a_module_into_scope` fails, check that `ToyChain` accepts an `anim_spaces` setting; if the toy module has no such field, `Module.space_rows` still reads `settings.get("anim_spaces")` and the test holds — the failure would then be real.

- [ ] **Step 5: Verify the purity boundary still holds**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" \
  -m pytest tests/unit/test_import_boundaries.py -q
```

Expected: PASS. `build_scope.py` imports only from `tik.trigger.core`.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/core/build_scope.py tests/unit/test_build_scope_trigger.py
git commit -m "Add build scope expansion for scoped test builds"
```

---

### Task 2: Scope the output lookup to one rig root

**Files:**
- Modify: `src/python/tik/trigger/guides/nodes.py:45` (`find_output`)
- Modify: `src/python/tik/trigger/maya/build.py` (`Builder._earlier_pass_output`, `Builder.build`)
- Test: `tests/integration/trigger/test_multipass_build_trigger.py` (append)

**Interfaces:**
- Produces: `find_output(instance_id, output_name, under=None)`; `Builder._root_path: str` (long path of the scaffold root being built into, `""` before a build starts).

**Context:** `find_output` scans every tagged node in the scene. Once a real rig and a test rig are both built, the same `trg_instance` answers twice. Every output is a bind joint (a DAG node), so a long-path prefix test is exact. This closes the ambiguity for the real build as well as the test one.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_multipass_build_trigger.py`:

```python
def test_find_output_is_scoped_to_one_rig_root():
    """Two rigs can hold the same instance's output; the lookup must not guess."""
    import tik.maya as tm
    from tik.trigger.guides import nodes as guide_nodes
    from tik.trigger.maya import tags

    cmds.file(new=True, force=True)
    made = []
    for root_name in ("rig_grp", "test_rig_grp"):
        root = tm.Transform.create(name=root_name)
        node = tm.Transform.create(name=f"{root_name}_out", parent=root.long_name)
        tags.tag(
            node,
            **{
                tags.KIND: tags.DEFORM,
                tags.INSTANCE: "id_shared",
                tags.OUTPUT_NAME: "root",
            },
        )
        made.append((root.long_name, node.long_name))

    real_root, real_out = made[0]
    test_root, test_out = made[1]

    assert guide_nodes.find_output("id_shared", "root", under=real_root).long_name == real_out
    assert guide_nodes.find_output("id_shared", "root", under=test_root).long_name == test_out
    # unscoped still answers, for callers that have no root
    assert guide_nodes.find_output("id_shared", "root") is not None
    # a root with no such output answers None rather than the other rig's
    assert guide_nodes.find_output("id_shared", "missing", under=real_root) is None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" MAYA_PLUG_IN_PATH="D:/dev/tikworks/src/plugins/python" \
  "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest \
  tests/integration/trigger/test_multipass_build_trigger.py::test_find_output_is_scoped_to_one_rig_root -q
```

Expected: FAIL — `TypeError: find_output() got an unexpected keyword argument 'under'`.

- [ ] **Step 3: Add the parameter to `find_output`**

In `src/python/tik/trigger/guides/nodes.py`, replace the signature and loop head:

```python
def find_output(instance_id: str, output_name: str, under: Optional[str] = None):
    """The built node fulfilling ``instance_id``'s ``output_name``, or None.

    How a later build pass reaches a module an earlier one produced. Outputs
    are looked up by their *output* tag, never by their role tag: ``finalize``
    writes ``trg_role`` on a module's inputs as well as its outputs, so one
    instance can legitimately carry the same role name twice.

    Guides are irrelevant here -- an earlier pass may well have deleted its
    own -- so this scans the built rig, not the guide holder.

    ``under`` is the long path of a rig root. A scene can hold the real rig and
    a test rig at once, and both answer to the same ``trg_instance``; every
    output is a bind joint, so restricting the scan to one root's subtree is
    exact. None scans the whole scene, which is what a caller with no root
    wants.
    """
    pattern = f"*.{tm.META_PREFIX}{tags.OUTPUT_NAME}"
    prefix = f"{under}|" if under else ""
    for name in cmds.ls(pattern, long=True, objectsOnly=True) or []:
        if prefix and not name.startswith(prefix):
            continue
        node = tm.resolve(name)
        ...  # body unchanged
```

- [ ] **Step 4: Run the test to verify it passes**

Same command as Step 2. Expected: PASS.

- [ ] **Step 5: Have the Builder pass its root**

In `src/python/tik/trigger/maya/build.py`, add to `Builder.__init__`:

```python
        #: Long path of the scaffold root this build is building into. A
        #: scene can hold the real rig and a test rig at once, so an
        #: earlier-pass lookup must say which one it means.
        self._root_path: str = ""
```

In `Builder.build`, immediately after `report.scaffold = ensure_rig(self.events)`:

```python
            self._root_path = report.scaffold.root.long_name
```

And in `_earlier_pass_output`:

```python
        return guide_nodes.find_output(instance_id, output, under=self._root_path or None)
```

- [ ] **Step 6: Run the multipass and builder suites**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" MAYA_PLUG_IN_PATH="D:/dev/tikworks/src/plugins/python" \
  "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest \
  tests/integration/trigger/test_multipass_build_trigger.py \
  tests/integration/trigger/test_builder_trigger.py -q
```

Expected: all pass. The multipass tests are the ones that exercise `_earlier_pass_output`; if any fails, `_root_path` is being read before it is set.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/guides/nodes.py src/python/tik/trigger/maya/build.py \
        tests/integration/trigger/test_multipass_build_trigger.py
git commit -m "Scope find_output to one rig root"
```

---

### Task 3: The test scaffold

**Files:**
- Modify: `src/python/tik/trigger/maya/scaffold.py`
- Modify: `src/python/tik/trigger/maya/__init__.py:27` (lazy-import table)
- Test: `tests/integration/trigger/test_test_rig_trigger.py` (create)

**Interfaces:**
- Consumes: nothing from Tasks 1–2.
- Produces: `ScaffoldNames` (frozen dataclass), `REAL_NAMES`, `TEST_NAMES`, `ensure_test_rig(events=None) -> RigScaffold`, `find_test_rig() -> Optional[RigScaffold]`, `RigScaffold.is_test: bool`, `TEST_ROOT = "test_rig_grp"`.

**Context:** `ensure_rig` currently hard-codes the five names. Refactor to one private `_ensure(names, events)` driven by a name table; the only other difference is that the test root is created as a `dagContainer` (a transform subtype, so everything downstream is unchanged).

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/trigger/test_test_rig_trigger.py`:

```python
"""The throwaway rig the Guide Designer builds into.

Spec: docs/superpowers/specs/2026-09-07-test-rig-sandbox-design.md
"""

from maya import cmds

from tik.trigger.maya.scaffold import (
    TEST_ROOT,
    ensure_rig,
    ensure_test_rig,
    find_test_rig,
)


def test_ensure_test_rig_creates_its_own_root():
    cmds.file(new=True, force=True)
    scaffold = ensure_test_rig()

    assert scaffold.is_test is True
    assert scaffold.root.long_name == f"|{TEST_ROOT}"
    assert cmds.objExists("|test_rig_grp|test_trigger_grp")
    assert cmds.objExists("|test_rig_grp|test_geo_grp")
    assert cmds.objExists("|test_rig_grp|test_trigger_grp|test_preferences_ctrl")
    assert cmds.objExists("|test_rig_grp|test_trigger_grp|test_visibilities_ctrl")
    # the real rig is not created as a side effect
    assert not cmds.objExists("|rig_grp")


def test_the_test_root_is_a_dag_container():
    """Membership is what makes teardown complete."""
    cmds.file(new=True, force=True)
    ensure_test_rig()
    assert cmds.nodeType(TEST_ROOT) == "dagContainer"


def test_ensure_test_rig_is_idempotent():
    cmds.file(new=True, force=True)
    first = ensure_test_rig()
    second = ensure_test_rig()
    assert first.root.long_name == second.root.long_name
    assert len(cmds.ls("test_rig_grp") or []) == 1


def test_the_two_rigs_coexist():
    cmds.file(new=True, force=True)
    real = ensure_rig()
    test = ensure_test_rig()
    assert real.root.long_name == "|rig_grp"
    assert test.root.long_name == "|test_rig_grp"
    assert real.is_test is False
    assert cmds.objExists("|rig_grp|trigger_grp|preferences_ctrl")
    assert cmds.objExists("|test_rig_grp|test_trigger_grp|test_preferences_ctrl")


def test_find_test_rig_creates_nothing():
    cmds.file(new=True, force=True)
    assert find_test_rig() is None
    assert not cmds.objExists(TEST_ROOT)
    ensure_test_rig()
    assert find_test_rig() is not None


def test_ensure_rig_is_unchanged():
    """The real scaffold keeps its exact names and shape."""
    cmds.file(new=True, force=True)
    scaffold = ensure_rig()
    assert scaffold.root.long_name == "|rig_grp"
    assert scaffold.is_test is False
    assert cmds.nodeType("rig_grp") == "transform"
    assert cmds.objExists("|rig_grp|trigger_grp|visibilities_ctrl")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" MAYA_PLUG_IN_PATH="D:/dev/tikworks/src/plugins/python" \
  "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest \
  tests/integration/trigger/test_test_rig_trigger.py -q
```

Expected: collection error — `ImportError: cannot import name 'TEST_ROOT'`.

- [ ] **Step 3: Refactor `scaffold.py` onto a name table**

Replace the five module-level name constants and `ensure_rig` in `src/python/tik/trigger/maya/scaffold.py`. Keep `RIG_GRP`, `TRIGGER_GRP`, `GEO_GRP`, `PREFERENCES_CTRL`, `VISIBILITIES_CTRL` exported — other modules and tests import them.

```python
RIG_GRP = "rig_grp"
TRIGGER_GRP = "trigger_grp"
GEO_GRP = "geo_grp"
PREFERENCES_CTRL = "preferences_ctrl"
VISIBILITIES_CTRL = "visibilities_ctrl"

TEST_ROOT = "test_rig_grp"


@dataclass(frozen=True)
class ScaffoldNames:
    """The fixed names of one scaffold, and whether it is the throwaway one."""

    root: str
    trigger: str
    geo: str
    preferences: str
    visibilities: str
    is_test: bool = False


REAL_NAMES = ScaffoldNames(
    RIG_GRP, TRIGGER_GRP, GEO_GRP, PREFERENCES_CTRL, VISIBILITIES_CTRL
)
#: The Guide Designer's throwaway rig. Its root is a ``dagContainer`` so that
#: deleting it takes every module container's DG nodes with it.
TEST_NAMES = ScaffoldNames(
    TEST_ROOT,
    "test_trigger_grp",
    "test_geo_grp",
    "test_preferences_ctrl",
    "test_visibilities_ctrl",
    is_test=True,
)
```

Add `is_test` to `RigScaffold`:

```python
@dataclass
class RigScaffold:
    """The fixed nodes of one rig in the scene."""

    root: Any  # rig_grp
    trigger: Any  # trigger_grp
    geo: Any  # geo_grp
    preferences: Controller
    visibilities: Controller
    #: True for the Guide Designer's throwaway rig, which is never published.
    is_test: bool = False
```

Teach `_ensure_group` to make a container root:

```python
def _ensure_group(name: str, parent, kind: str, events, container: bool = False):
    """The transform ``name`` under ``parent`` (None = world), tagged ``kind``.

    ``container`` creates it as a ``dagContainer`` -- a transform subtype that
    also owns the DG nodes created while it is current, which is what makes the
    test rig's teardown complete.
    """
    path = f"{parent.long_name}|{name}" if parent is not None else f"|{name}"
    if cmds.objExists(path):
        node = tm.Transform(path)
        if node.meta.get(tags.KIND) != kind:
            _log(events, f"Adopted existing '{name}' as the rig's {kind}.")
            node.meta[tags.KIND] = kind
    elif container:
        node = tm.resolve(cmds.container(type="dagContainer", name=name))
        node.meta[tags.KIND] = kind
    else:
        node = tm.Transform.create(
            name=name, parent=parent.long_name if parent is not None else None
        )
        node.meta[tags.KIND] = kind
    _lock_channels(node)
    return node
```

Replace `ensure_rig` and `find_rig` with the shared body plus four public entries:

```python
def _ensure(names: ScaffoldNames, events: Optional[Any] = None) -> RigScaffold:
    """The scaffold ``names`` describes, created or healed."""
    root = _ensure_group(names.root, None, tags.RIG_ROOT, events, container=names.is_test)
    trigger = _ensure_group(names.trigger, root, tags.RIG_TRIGGER, events)
    geo = _ensure_group(names.geo, root, tags.RIG_GEO, events)
    preferences = _ensure_control(
        names.preferences, trigger, tags.PREFERENCES, "P", events, size=1.0
    )
    visibilities = _ensure_control(
        names.visibilities, trigger, tags.VISIBILITIES, "Cog", events, size=0.5
    )
    # move the preferences a bit higher
    visibilities.transform["translateX"].set(1)
    _ensure_preference_attrs(preferences)
    _wire_geo(preferences, geo)
    return RigScaffold(
        root=root,
        trigger=trigger,
        geo=geo,
        preferences=preferences,
        visibilities=visibilities,
        is_test=names.is_test,
    )


def ensure_rig(events: Optional[Any] = None) -> RigScaffold:
    """The one real scaffold, created or healed. Safe before every step."""
    return _ensure(REAL_NAMES, events)


def ensure_test_rig(events: Optional[Any] = None) -> RigScaffold:
    """The Guide Designer's throwaway scaffold, created or healed.

    A second rig, deliberately: a mock-up must never land its module groups in
    the real ``trigger_grp`` or its tier enums on the real ``visibilities_ctrl``.
    It is created lazily by the first test build and is not in the session
    document.
    """
    return _ensure(TEST_NAMES, events)


def find_rig() -> Optional[RigScaffold]:
    """The real scaffold if the scene has one, without creating anything."""
    if not cmds.objExists(f"|{RIG_GRP}|{TRIGGER_GRP}|{PREFERENCES_CTRL}"):
        return None
    return ensure_rig()


def find_test_rig() -> Optional[RigScaffold]:
    """The test scaffold if the scene has one, without creating anything."""
    path = f"|{TEST_NAMES.root}|{TEST_NAMES.trigger}|{TEST_NAMES.preferences}"
    if not cmds.objExists(path):
        return None
    return ensure_test_rig()
```

- [ ] **Step 4: Export the new names**

In `src/python/tik/trigger/maya/__init__.py`, add beside the existing `"ensure_rig": ".scaffold"` entry:

```python
    "ensure_test_rig": ".scaffold",
    "find_test_rig": ".scaffold",
```

- [ ] **Step 5: Run the tests to verify they pass**

Same command as Step 2. Expected: 6 passed.

- [ ] **Step 6: Run every suite that touches the scaffold**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" MAYA_PLUG_IN_PATH="D:/dev/tikworks/src/plugins/python" \
  "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration/trigger -q
```

Expected: all pass. `ensure_rig`'s behaviour is unchanged; a failure here means the refactor altered the real path.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/maya/scaffold.py src/python/tik/trigger/maya/__init__.py \
        tests/integration/trigger/test_test_rig_trigger.py
git commit -m "Add the test rig scaffold beside the real one"
```

---

### Task 4: The sandbox — module containers

**Files:**
- Create: `src/python/tik/trigger/maya/sandbox.py`
- Test: `tests/integration/trigger/test_test_rig_trigger.py` (append)

**Interfaces:**
- Consumes: `scaffold.TEST_ROOT`, `scaffold.TEST_NAMES`, `scaffold.find_test_rig`, `build.tier_attr_name` (Task 5 also uses it; it already exists at `build.py:83`).
- Produces:
  - `module_container(instance_id: str, key: str, parent) -> tm.Transform`
  - `find_module_container(instance_id: str) -> Optional[tm.Transform]`
  - `built_instance_ids() -> set[str]`
  - `current(container)` — context manager
  - `teardown(instance_ids: Iterable[str], scaffold=None) -> list[str]`
  - `clear() -> bool`

**Context:** Measured facts 1–4 and 6 in Global Constraints govern this file. In particular `current` must save and restore the previous container itself, and `clear()` is a single delete.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_test_rig_trigger.py`:

```python
import pytest

import tik.maya as tm
from tik.trigger.maya import sandbox
from tik.trigger.maya.scaffold import ensure_test_rig


def _module_container(instance_id="id_arm", key="L_arm"):
    scaffold = ensure_test_rig()
    return scaffold, sandbox.module_container(instance_id, key, scaffold.trigger)


def test_a_module_container_is_tagged_and_parented():
    cmds.file(new=True, force=True)
    scaffold, container = _module_container()
    assert cmds.nodeType(container.long_name) == "dagContainer"
    assert container.long_name.startswith(scaffold.trigger.long_name + "|")
    assert sandbox.find_module_container("id_arm").long_name == container.long_name
    assert sandbox.built_instance_ids() == {"id_arm"}


def test_current_captures_dag_and_dg_nodes():
    """The whole point: the utility nodes go in too."""
    cmds.file(new=True, force=True)
    _scaffold, container = _module_container()
    with sandbox.current(container):
        group = tm.Transform.create(name="L_arm_grp", parent=container.long_name)
        node = cmds.createNode("multMatrix", name="L_arm_mmx")
    members = cmds.container(container.long_name, q=True, nodeList=True) or []
    assert group.name in members
    assert node in members


def test_current_restores_the_previous_container():
    """Nesting does not restore by itself; the context manager must."""
    cmds.file(new=True, force=True)
    scaffold, one = _module_container("id_a", "a")
    two = sandbox.module_container("id_b", "b", scaffold.trigger)
    with sandbox.current(one):
        with sandbox.current(two):
            assert cmds.container(q=True, current=True) == two.name
        assert cmds.container(q=True, current=True) == one.name
    assert (cmds.container(q=True, current=True) or "") == ""


def test_current_clears_when_the_body_raises():
    cmds.file(new=True, force=True)
    _scaffold, container = _module_container()
    with pytest.raises(RuntimeError):
        with sandbox.current(container):
            raise RuntimeError("boom")
    assert (cmds.container(q=True, current=True) or "") == ""


def test_teardown_removes_a_module_and_nothing_else():
    cmds.file(new=True, force=True)
    scaffold, arm = _module_container("id_arm", "L_arm")
    body = sandbox.module_container("id_body", "body", scaffold.trigger)
    with sandbox.current(arm):
        tm.Transform.create(name="L_arm_grp", parent=arm.long_name)
        cmds.createNode("multMatrix", name="L_arm_mmx")
    with sandbox.current(body):
        tm.Transform.create(name="body_grp", parent=body.long_name)
        cmds.createNode("multMatrix", name="body_mmx")

    removed = sandbox.teardown(["id_arm"], scaffold)

    assert removed == ["id_arm"]
    assert not cmds.objExists("L_arm_grp")
    assert not cmds.objExists("L_arm_mmx")  # the DG node goes too
    assert cmds.objExists("body_grp")
    assert cmds.objExists("body_mmx")
    assert sandbox.built_instance_ids() == {"id_body"}


def test_teardown_drops_the_modules_tier_enum():
    cmds.file(new=True, force=True)
    scaffold, _arm = _module_container("id_arm", "L_arm")
    enum = scaffold.visibilities.transform["L_arm"]
    enum.create("enum", items=["primary", "all"], default=1, keyable=False)
    assert enum.exists()

    sandbox.teardown(["id_arm"], scaffold)

    assert not scaffold.visibilities.transform["L_arm"].exists()


def test_teardown_of_an_unbuilt_module_is_a_no_op():
    cmds.file(new=True, force=True)
    scaffold = ensure_test_rig()
    assert sandbox.teardown(["id_ghost"], scaffold) == []


def test_clear_removes_the_whole_test_rig():
    cmds.file(new=True, force=True)
    scaffold, arm = _module_container()
    with sandbox.current(arm):
        cmds.createNode("multMatrix", name="L_arm_mmx")
    from tik.trigger.maya.scaffold import ensure_rig

    ensure_rig()  # the real rig must survive

    assert sandbox.clear() is True

    assert not cmds.objExists(sandbox.TEST_ROOT)
    assert not cmds.objExists("L_arm_mmx")
    assert cmds.objExists("rig_grp")
    assert sandbox.clear() is False  # nothing left to clear
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" MAYA_PLUG_IN_PATH="D:/dev/tikworks/src/plugins/python" \
  "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest \
  tests/integration/trigger/test_test_rig_trigger.py -q
```

Expected: collection error — `No module named 'tik.trigger.maya.sandbox'`.

- [ ] **Step 3: Write `sandbox.py`**

Create `src/python/tik/trigger/maya/sandbox.py`:

```python
"""The Guide Designer's throwaway rig, and the containers that make it tidy.

Spec: docs/superpowers/specs/2026-09-07-test-rig-sandbox-design.md

A test build is a mock-up: the rigger changes a setting, looks, and changes it
again. That needs two things the real build path does not give -- somewhere to
build that is not the real rig, and a teardown so pressing Build twice does not
stack a second copy.

Both come from one Maya feature. A ``dagContainer`` is a transform that also
*owns* the nodes created while it is current, DG nodes included, so a module's
``multMatrix`` chain is as much a member as its joints are. Teardown of one
module is deleting its container; teardown of the whole rig is deleting the
root, which owns the module containers in turn.

Named ``sandbox`` rather than ``test_rig`` so that no file under ``src/`` carries
a ``test_`` prefix that pytest might collect.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Optional

from maya import cmds

import tik.maya as tm

from . import tags
from .scaffold import TEST_ROOT, find_test_rig

__all__ = [
    "TEST_ROOT",
    "module_container",
    "find_module_container",
    "built_instance_ids",
    "current",
    "teardown",
    "clear",
]


def _containers() -> list:
    """Every ``dagContainer`` in the scene.

    ``ls(type="container")`` does not list a ``dagContainer`` -- it is its own
    node type -- so this asks for the type by name.
    """
    return cmds.ls(type="dagContainer", long=True) or []


def module_container(instance_id: str, key: str, parent) -> tm.Transform:
    """The container one module builds into, created if it is not there yet.

    Tagged with the instance uuid rather than found by name, so renaming a
    module cannot strand its container.
    """
    found = find_module_container(instance_id)
    if found is not None:
        return found
    name = cmds.container(type="dagContainer", name=f"{key}_con")
    node = tm.resolve(cmds.parent(name, parent.long_name)[0])
    # The display key is tagged, not parsed back off the container's name: a
    # rename changes the name and the enum is addressed by the key.
    tags.tag(
        node,
        **{tags.KIND: tags.RIG, tags.INSTANCE: instance_id, tags.NAME: key},
    )
    return node


def find_module_container(instance_id: str) -> Optional[Any]:
    """The container tagged with ``instance_id``, or None."""
    for name in _containers():
        node = tm.resolve(name)
        if node.meta.get(tags.INSTANCE) == instance_id:
            return node
    return None


def built_instance_ids() -> set:
    """The instance ids that currently have a container in the test rig.

    A fact about the scene, read fresh: the alternative is a cached list that
    drifts the moment anyone deletes a group by hand.
    """
    prefix = f"|{TEST_ROOT}|"
    found = set()
    for name in _containers():
        if not name.startswith(prefix):
            continue
        instance_id = tm.resolve(name).meta.get(tags.INSTANCE)
        if instance_id:
            found.add(instance_id)
    return found


@contextmanager
def current(container):
    """Make ``container`` the current one for the duration of the block.

    Maya does not restore an outer container when an inner one is cleared --
    it sets the current container to nothing -- so the previous value is saved
    and put back by hand. The ``finally`` matters: a build that raises must not
    leave a container current for whatever runs next.
    """
    previous = cmds.container(q=True, current=True) or ""
    cmds.container(container.long_name, edit=True, current=True)
    try:
        yield container
    finally:
        if previous and cmds.objExists(previous):
            cmds.container(previous, edit=True, current=True)
        else:
            cmds.container(container.long_name, edit=True, current=False)


def teardown(instance_ids: Iterable[str], scaffold=None) -> list:
    """Remove each module's container from the test rig; report what went.

    The container takes the module's nodes, DG ones included. Its tier enum
    lives on ``test_visibilities_ctrl`` -- an attribute on the scaffold, not a
    node in the container -- so that is removed separately.
    """
    from .build import tier_attr_name

    scaffold = scaffold if scaffold is not None else find_test_rig()
    removed = []
    for instance_id in instance_ids:
        container = find_module_container(instance_id)
        if container is None:
            continue
        key = container.meta.get(tags.NAME)
        if scaffold is not None and key:
            control = scaffold.visibilities.transform
            enum = control[tier_attr_name(key)]
            if enum.exists():
                enum.locked = False
                cmds.deleteAttr(f"{control.long_name}.{tier_attr_name(key)}")
        cmds.delete(container.long_name)
        removed.append(instance_id)
    return removed


def clear() -> bool:
    """Delete the whole test rig. True when there was one to delete.

    One call is enough: a ``dagContainer`` adopts its DAG children as members,
    so the root owns the module containers, which own their own DG nodes.
    """
    if not cmds.objExists(f"|{TEST_ROOT}"):
        return False
    cmds.delete(f"|{TEST_ROOT}")
    return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Same command as Step 2. Expected: 14 passed (6 from Task 3, 8 new).

One likely failure and its cause: `test_teardown_drops_the_modules_tier_enum` needs `cmds.deleteAttr` to accept the node-qualified name. If `tm.Plug` already exposes a delete, prefer it over the raw `cmds` call — check `src/python/tik/maya/core/plug.py` before reaching for `cmds`.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/maya/sandbox.py tests/integration/trigger/test_test_rig_trigger.py
git commit -m "Add the sandbox: one dagContainer per test-built module"
```

---

### Task 5: Build into the test rig

**Files:**
- Modify: `src/python/tik/trigger/maya/build.py` (`Builder.build`, `Builder._build_one`, `Builder._connect_one`, `Builder._connect_spaces`)
- Test: `tests/integration/trigger/test_test_rig_trigger.py` (append)

**Interfaces:**
- Consumes: `expand_build_scope` (Task 1), `find_output(..., under=)` (Task 2), `ensure_test_rig` (Task 3), the whole `sandbox` module (Task 4).
- Produces: `Builder.build(scope="scene", afterlife="delete", document=None, test=False) -> BuildReport`; `BuildReport.torn_down: list[str]`.

**Context:** `test=True` changes four things and nothing else: which scaffold is ensured, that the scope is expanded and torn down first, that each module builds inside its container, and that `Build All` (`scope == "scene"`) clears the whole test rig instead of expanding.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/trigger/test_test_rig_trigger.py`:

```python
from tik.trigger.session import Session


def _body_and_arm():
    """A base with an arm connected to it, drawn in a fresh scene."""
    cmds.file(new=True, force=True)
    session = Session()
    scene = session.guides
    body = scene.add("base", side="C", name="body")
    arm = scene.add("arm", side="L", name="arm", parent=body)
    scene.draw(None)
    return session, body, arm


def test_a_test_build_leaves_the_real_rig_absent():
    session, _body, _arm = _body_and_arm()
    session.guides.test_build()
    assert cmds.objExists(sandbox.TEST_ROOT)
    assert not cmds.objExists("rig_grp")


def test_a_test_build_does_not_touch_a_built_real_rig():
    session, _body, _arm = _body_and_arm()
    session.guides.build()  # the real rig
    before = sorted(cmds.ls("|rig_grp", dag=True, long=True) or [])
    real_enums = sorted(cmds.listAttr("visibilities_ctrl", userDefined=True) or [])

    session.guides.test_build()

    assert sorted(cmds.ls("|rig_grp", dag=True, long=True) or []) == before
    assert sorted(cmds.listAttr("visibilities_ctrl", userDefined=True) or []) == real_enums


def test_building_the_same_selection_three_times_leaves_one_copy():
    """The bug this whole feature exists to kill."""
    session, _body, arm = _body_and_arm()
    counts = []
    for _ in range(3):
        session.guides.test_build(arm)
        counts.append(len(cmds.ls("L_arm_grp", long=True) or []))
    assert counts == [1, 1, 1]


def test_build_all_wipes_the_test_rig_first():
    session, _body, _arm = _body_and_arm()
    session.guides.test_build()
    with sandbox.current(sandbox.find_module_container(_arm.instance_id)):
        cmds.createNode("transform", name="stray_marker")
    session.guides.test_build()
    assert not cmds.objExists("stray_marker")


def test_a_scoped_build_pulls_in_an_unbuilt_producer():
    session, body, arm = _body_and_arm()
    report = session.guides.test_build(arm)
    assert body.instance_id in report.built
    assert arm.instance_id in report.built


def test_a_scoped_build_leaves_a_sibling_alone():
    session, body, arm = _body_and_arm()
    session.guides.test_build()
    body_container = sandbox.find_module_container(body.instance_id)
    marker = body_container.long_name

    session.guides.test_build(arm)

    assert cmds.objExists(marker)
    assert sandbox.find_module_container(arm.instance_id) is not None


def test_a_scoped_build_rebuilds_a_built_consumer():
    """The arm's attach must not be left pointing at deleted nodes."""
    session, body, arm = _body_and_arm()
    session.guides.test_build()
    session.guides.test_build(body)

    socket = cmds.ls("L_arm_*socket*", long=True, type="transform") or []
    assert socket
    drivers = cmds.listConnections(socket[0], source=True, destination=False) or []
    assert drivers, "the rebuilt arm lost its attach"


def test_a_test_build_keeps_the_guides():
    session, _body, _arm = _body_and_arm()
    session.guides.test_build()
    assert cmds.objExists("trigger_guides_grp")


def test_a_module_s_dg_nodes_are_in_its_container():
    session, _body, arm = _body_and_arm()
    session.guides.test_build()
    container = sandbox.find_module_container(arm.instance_id)
    members = cmds.container(container.long_name, q=True, nodeList=True) or []
    assert any(cmds.objectType(name) == "multMatrix" for name in members), members
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" MAYA_PLUG_IN_PATH="D:/dev/tikworks/src/plugins/python" \
  "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest \
  tests/integration/trigger/test_test_rig_trigger.py -q -k "test_build or wipes or scoped or copy"
```

Expected: failures — the builds land in `rig_grp` and repeated builds stack copies.

- [ ] **Step 3: Add `torn_down` to the report**

In `src/python/tik/trigger/maya/build.py`, add to `BuildReport`:

```python
    #: Instance ids removed from the test rig before this build, so a caller
    #: can say what a scoped rebuild actually replaced.
    torn_down: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Teach `Builder.build` about the test rig**

Change the signature and the scaffold/teardown block. Add the import at the top of the file:

```python
from .scaffold import RigScaffold, ensure_rig, ensure_test_rig
```

Then:

```python
    def build(
        self,
        scope: Any = "scene",
        afterlife: str = "delete",
        document=None,
        test: bool = False,
    ) -> BuildReport:
        """Build every guide instance in ``scope`` into a rig.

        ``test`` builds into the Guide Designer's throwaway rig instead of the
        real one, one ``dagContainer`` per module, tearing down whatever it is
        about to rebuild first. A test build is a mock-up the rigger repeats
        while changing settings, so it has to be idempotent; the real build
        path is unchanged.
        """
        if afterlife not in AFTERLIFE_MODES:
            raise ValueError(f"afterlife must be one of {AFTERLIFE_MODES}.")
        report = BuildReport()
        if test:
            scope = self._prepare_test_scope(scope, document, report)
        instances = self.order(guide_nodes.find_instances(scope, document))
        ...  # the _keys_to_ids block is unchanged
```

Note the one structural change: `report = BuildReport()` moves **above** the `find_instances` call so the teardown can record into it. Delete the later `report = BuildReport()` line.

Inside the `with guide_nodes.undo_chunk("Trigger build"):` block, replace the scaffold line:

```python
            report.scaffold = ensure_test_rig(self.events) if test else ensure_rig(self.events)
            self._root_path = report.scaffold.root.long_name
            self._test = test
```

and add `self._test = False` to `__init__` beside `_root_path`.

- [ ] **Step 5: Add the scope preparation**

Add to `Builder`, after `build`:

```python
    def _prepare_test_scope(self, scope, document, report: BuildReport):
        """Clear or tear down the test rig, and return the scope to build.

        ``"scene"`` is Build All: the whole test rig goes, because rebuilding
        everything is exactly what wiping it leaves behind. A picked scope is
        expanded first -- downstream to repair built consumers, upstream to
        fill in producers that are not built -- and only those modules are torn
        down.
        """
        from . import sandbox

        if scope == "scene" or document is None:
            sandbox.clear()
            return scope
        ids = list(scope) if scope != "selection" else scope
        if ids == "selection":
            return scope
        scope = expand_build_scope(document.modules, ids, sandbox.built_instance_ids())
        report.torn_down = sandbox.teardown(scope)
        return scope
```

and import it at the top of `build.py`:

```python
from tik.trigger.core.build_scope import expand_build_scope
```

- [ ] **Step 6: Build each module inside its container**

In `Builder.build`'s per-instance loop, wrap the build and the connect. Replace:

```python
                ctx = self._build_one(instance, report.scaffold, bind_parent)
                report.rigs[instance.instance_id] = ctx
                report.built.append(instance.instance_id)
                by_key[instance.key] = instance
                self._connect_one(instance, module_cls, inputs, by_key, report)
```

with:

```python
                with self._module_scope(instance, report.scaffold):
                    ctx = self._build_one(instance, report.scaffold, bind_parent)
                    report.rigs[instance.instance_id] = ctx
                    report.built.append(instance.instance_id)
                    by_key[instance.key] = instance
                    self._connect_one(instance, module_cls, inputs, by_key, report)
```

and add the helper:

```python
    @contextmanager
    def _module_scope(self, instance, scaffold):
        """Build this module inside its own container, on a test build.

        The connect wiring is inside the block deliberately: an attach
        constraint belongs to the *consumer*, so tearing the consumer down
        takes it too. On a real build this does nothing at all.
        """
        if not self._test:
            yield
            return
        from . import sandbox

        container = sandbox.module_container(
            instance.instance_id, instance.key, scaffold.trigger
        )
        with sandbox.current(container):
            yield
```

with `from contextlib import contextmanager` at the top of the file.

`_connect_spaces` runs after the loop and needs the same treatment. In `_connect_spaces`, wrap the per-instance body:

```python
        for instance in instances:
            module_cls = registry.get_module(instance.module_type)
            ctx = report.rigs.get(instance.instance_id)
            if ctx is None:
                continue
            with self._module_scope(instance, report.scaffold):
                ...  # the rest of the loop body, indented one level
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" MAYA_PLUG_IN_PATH="D:/dev/tikworks/src/plugins/python" \
  "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest \
  tests/integration/trigger/test_test_rig_trigger.py -q
```

Expected: all pass. Note some of these tests need Task 6's `test_build` pass-through to be green — if `test_a_test_build_leaves_the_real_rig_absent` still builds into `rig_grp`, finish Task 6 and re-run.

- [ ] **Step 8: Run the whole integration suite**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" MAYA_PLUG_IN_PATH="D:/dev/tikworks/src/plugins/python" \
  "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration -q
```

Expected: all pass. `test=False` is the default, so every existing build test must be unaffected.

- [ ] **Step 9: Commit**

```bash
git add src/python/tik/trigger/maya/build.py tests/integration/trigger/test_test_rig_trigger.py
git commit -m "Build test builds into the test rig, one container per module"
```

---

### Task 6: Wire it to the Guide Designer

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py:824` (`GuideScene.test_build`)
- Modify: `src/python/tik/trigger/ui/designer/commands.py:287` (`test_build`), add `clear_test_rig`
- Modify: `src/python/tik/trigger/ui/main.py:330` (Guides menu)
- Test: `tests/ui/test_menus.py` (append)

**Interfaces:**
- Consumes: `Builder.build(..., test=True)` (Task 5), `sandbox.clear` (Task 4).
- Produces: `GuideScene.test_build(*handles)` unchanged in signature; `DesignerCommands.clear_test_rig()`.

- [ ] **Step 1: Pass the flag through `GuideScene.test_build`**

In `src/python/tik/trigger/guides/scene.py`, in `test_build`, extend the docstring and the call:

```python
    def test_build(self, *handles: GuideHandle) -> Any:
        """Build the given modules (or every module) into a throwaway rig.

        Draws first, and has to: ``find_instances`` reads tagged joints, so a
        module nobody has drawn contributes nothing and would be skipped in
        silence. The sync before it makes that draw lossless, which is why
        this path never has to ask about discarding poses.

        The rig it builds is the *test* rig -- its own root, one container per
        module -- so a mock-up never lands in the real ``rig_grp``, and the
        build tears down whatever it is about to rebuild.
        """
        ids = [handle.instance_id for handle in handles]
        scope = ids or "scene"
        from tik.trigger.maya.build import Builder

        self.sync()
        self.draw(ids or None)
        return Builder(self.events).build(
            scope=scope, document=self.document, afterlife="keep", test=True
        )
```

- [ ] **Step 2: Add the `clear_test_rig` command**

In `src/python/tik/trigger/ui/designer/commands.py`, after `test_build`:

```python
    def clear_test_rig(self) -> None:
        """Delete the throwaway rig the Designer's Build made."""
        from tik.trigger.maya import sandbox

        with self.watcher.mute():
            cleared = sandbox.clear()
        self.status.set_activity(
            "Test rig cleared." if cleared else "No test rig to clear."
        )
        self.refresh()
```

- [ ] **Step 3: Add the menu item**

In `src/python/tik/trigger/ui/main.py`, after the "Build All Guides" action (line ~330):

```python
        self._action(
            guides_menu,
            "Clear Test Rig",
            lambda: self._designer_call("clear_test_rig"),
        )
```

- [ ] **Step 4: Write the menu test**

Append to `tests/ui/test_menus.py` — match the file's existing fixture and helper names; if it exposes a helper that lists a menu's action texts, use it rather than the loop below:

```python
def test_the_guides_menu_offers_clearing_the_test_rig(qtbot):
    from tik.trigger.ui.main import TriggerWindow

    window = TriggerWindow()
    qtbot.addWidget(window)
    labels = []
    for menu in window.menuBar().findChildren(type(window.menuBar().addMenu("x"))):
        labels.extend(action.text() for action in menu.actions())
    assert "Clear Test Rig" in labels
```

- [ ] **Step 5: Run the UI and guide suites**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen \
  "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/ui -q
```

Expected: all pass.

- [ ] **Step 6: Run Task 5's tests, which need this pass-through**

```bash
PYTHONPATH="D:/dev/tikworks/src/python" MAYA_PLUG_IN_PATH="D:/dev/tikworks/src/plugins/python" \
  "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest \
  tests/integration/trigger/test_test_rig_trigger.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/guides/scene.py src/python/tik/trigger/ui/designer/commands.py \
        src/python/tik/trigger/ui/main.py tests/ui/test_menus.py
git commit -m "Point the Guide Designer's Build at the test rig"
```

---

### Task 7: Full suites, lint and documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-09-07-test-rig-sandbox-design.md` (status line)

- [ ] **Step 1: Run everything**

```bash
make tests-unit && make tests-integration && make tests-ui
```

Expected: all green. Investigate any failure rather than adjusting the test to match the code.

- [ ] **Step 2: Lint**

```bash
make lint
```

Fix with `make format` if black or isort complain; fix flake8 findings by hand.

- [ ] **Step 3: Update `CLAUDE.md`**

In the `tik.trigger` **Status** paragraph, after the sentence about the `notes` TextField, add:

```
The Guide Designer's **Build** builds into its own throwaway rig (`test_rig_grp`), never the real `rig_grp`: one Maya `dagContainer` per module, so teardown of a module is deleting its container and teardown of the rig is deleting the root. A scoped build expands downstream to rebuild consumers that are already built and upstream to fill in producers that are not, then tears those modules down before rebuilding them — so pressing Build repeatedly while changing settings always leaves exactly one copy. **Guides > Clear Test Rig** removes it.
```

Add to the **Design specs** list, first entry:

```
`docs/superpowers/specs/2026-09-07-test-rig-sandbox-design.md` (the test rig: the second scaffold, dagContainers as the unit of teardown, scope expansion, and the measured Maya behaviour it all rests on),
```

Add to the **tik.trigger Tests** list:

```
- `tests/unit/test_build_scope_trigger.py` — scope expansion (pure); `tests/integration/trigger/test_test_rig_trigger.py` — the test rig, its containers and their teardown
```

- [ ] **Step 4: Mark the spec implemented**

Change its `**Status:**` line to `implemented`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-09-07-test-rig-sandbox-design.md
git commit -m "Document the test rig"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §2.1 own rig / §4 test scaffold | Task 3 |
| §2.2 dagContainer per module / §5 | Task 4, Task 5 step 6 |
| §2.3 no namespace | Nothing to build — the design is the absence |
| §2.4 teardown follows scope / §6 | Task 1, Task 5 step 5 |
| §2.5 downstream repair, upstream gaps | Task 1 |
| §2.6 pipeline run does not inherit | Nothing to build — `Runner.run` already resets; **Clear Test Rig** is the `only=` remedy (Task 6) |
| §3 measured facts | Encoded as the Global Constraints list and in `sandbox.py`'s docstrings |
| §7 scoping the output lookups | Task 2 |
| §9 entry points | Task 6 |
| §10 tests | Tasks 1–6 |
| §11 what does not change | Task 5 step 8 and Task 3 step 6 guard it |

**Type consistency:** `expand_build_scope(entries, ids, already_built)` is called once, in `Builder._prepare_test_scope`, with `document.modules`, the id list and `sandbox.built_instance_ids()` — matching the Task 1 signature. `sandbox.teardown(scope)` is called with the expanded list and defaults its scaffold via `find_test_rig()`. `find_output(..., under=)` is passed `self._root_path or None`. `RigScaffold.is_test` is set in `_ensure` and read in tests only.

**Resolved during review:** `teardown` originally recovered the tier-enum name by stripping `"_con"` off the container's name, which a module rename would break. `module_container` now tags the display key (`tags.NAME`) and `teardown` reads it — identity by tag, names for humans, which is the rule the rest of this codebase already follows.
