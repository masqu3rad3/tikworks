# Build / Publish Pipeline Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the `.tr` session's single action list into a `build` list and a `publish` list, so publishing becomes composable actions run only as the tail of a full clean build.

**Architecture:** `Document` grows a second root list (`publish`) alongside `actions`, and every tree method takes a `phase` argument resolved through one `roots(phase)` helper. The `Runner` plans each phase separately and, for Build & Publish, concatenates them into a single run with one scene reset. `Session` keeps its whole current surface pointing at the build list and exposes the publish list through a `PhaseView` namespace. The pipeline pane becomes two trees, each with its own phase-parameterised `PipelineModel`.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), Qt via `tik.shared.ui.Qt`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-03-build-publish-split-design.md`

## Global Constraints

- **No third-party dependencies.** Stdlib and Maya-bundled modules only.
- **`tik/trigger/core` is pure Python** — no Maya, no Qt imports. Enforced by `tests/unit/test_import_boundaries.py`. Tasks 1 and 2 touch `core`; they must not import Maya or Qt.
- **Never call `maya.cmds` / `OpenMaya` / `pymel` directly** in tool code — consume `tik.maya`. (No task here writes new Maya code; the integration test in Task 8 uses `cmds` for assertions only, matching the existing tests in that directory.)
- **Phase vocabulary, exact strings:** `BUILD = "build"`, `PUBLISH = "publish"`, `PHASES = (BUILD, PUBLISH)`. Action scopes: `"build"`, `"publish"`, `"both"` (`BOTH = "both"`).
- **`SCHEMA_VERSION` goes 5 → 6** in `src/python/tik/trigger/core/document.py`. Note `core/schemas.py` has its own unrelated `SCHEMA_VERSION = 3` (the guide document) — do not touch it.
- **`actions` keeps its name and meaning** — it is the build list. Renaming it would break every stored `.tr` and every reference override.
- **Action paths are per-phase and unprefixed.** The phase is always an explicit argument, never a path segment.
- **The runner never checks scope.** Scope is a placement rule enforced by the UI and `Session.add()` only.
- **Publish actions are never individually runnable.** No `run()`, no `until`, no double-click, no context-menu run.

**Test commands:**
- Unit + integration: `make tests` (or `make tests-unit` / `make tests-integration`) — runs under `mayapy`.
- Single unit file: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_document_trigger.py -q`
- UI: `make tests-ui` (sets `TIK_TESTS_NO_MAYA=1` and `QT_QPA_PLATFORM=offscreen`)
- Single UI test: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_pipeline_ui.py -q`

All source paths below are relative to `src/python/tik/trigger/` unless they start with `tests/` or `docs/`.

---

### Task 1: Phase-aware `Document`

**Files:**
- Modify: `src/python/tik/trigger/core/document.py`
- Modify: `src/python/tik/trigger/core/__init__.py`
- Test: `tests/unit/test_document_trigger.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `BUILD: str = "build"`, `PUBLISH: str = "publish"`, `PHASES: tuple = ("build", "publish")` in `core/document.py`, re-exported from `core/__init__.py`.
  - `Document.publish: list[ActionNode]`
  - `Document.roots(phase: str = BUILD) -> list[ActionNode]` — public; raises `SessionError` on an unknown phase.
  - Every `Document` tree method gains a trailing keyword `phase: str = BUILD`: `walk`, `paths`, `find`, `require`, `parent_of`, `siblings`, `path_of`, `unique_name`, `add`, `remove`, `move`, `rename`, `duplicate`.
  - `SCHEMA_VERSION = 6`

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/unit/test_document_trigger.py`:

```python
from tik.trigger.core.document import BUILD, PHASES, PUBLISH


def _mixed():
    doc = Document()
    doc.add(ActionNode("import_model", "import_asset"))
    doc.add(ActionNode("kinematics", "kinematics"))
    doc.add(ActionNode("export_fbx", "script"), phase=PUBLISH)
    doc.add(ActionNode("export_maya", "script"), phase=PUBLISH)
    return doc


def test_phase_constants():
    assert (BUILD, PUBLISH) == ("build", "publish")
    assert PHASES == (BUILD, PUBLISH)


def test_publish_list_is_separate_from_build():
    doc = _mixed()
    assert doc.paths() == ["import_model", "kinematics"]
    assert doc.paths(phase=PUBLISH) == ["export_fbx", "export_maya"]
    assert doc.find("export_fbx") is None
    assert doc.find("export_fbx", phase=PUBLISH).type == "script"
    assert [node.name for node in doc.roots(PUBLISH)] == ["export_fbx", "export_maya"]


def test_same_name_in_both_phases_does_not_collide():
    doc = Document()
    assert doc.add(ActionNode("export", "script")) == "export"
    assert doc.add(ActionNode("export", "script"), phase=PUBLISH) == "export"
    assert doc.paths() == ["export"]
    assert doc.paths(phase=PUBLISH) == ["export"]


def test_publish_tree_operations_mirror_build():
    doc = _mixed()
    doc.add(ActionNode("cleanup", "script"), parent="export_fbx", phase=PUBLISH)
    assert doc.paths(phase=PUBLISH) == ["export_fbx", "export_fbx/cleanup", "export_maya"]
    assert doc.move("export_maya", index=0, phase=PUBLISH) == "export_maya"
    assert doc.paths(phase=PUBLISH)[0] == "export_maya"
    assert doc.rename("export_fbx", "fbx", phase=PUBLISH) == "fbx"
    assert doc.duplicate("fbx", phase=PUBLISH) == "fbx1"
    doc.remove("fbx1", phase=PUBLISH)
    assert doc.paths(phase=PUBLISH) == ["export_maya", "fbx", "fbx/cleanup"]
    assert doc.parent_of("fbx/cleanup", phase=PUBLISH).name == "fbx"
    # the build list is untouched throughout
    assert doc.paths() == ["import_model", "kinematics"]


def test_unknown_phase_raises():
    with pytest.raises(SessionError):
        Document().roots("nope")
    with pytest.raises(SessionError):
        Document().paths(phase="nope")


def test_an_action_is_invisible_from_the_other_phase():
    doc = _mixed()
    with pytest.raises(SessionError):
        doc.move("kinematics", index=0, phase=PUBLISH)
    with pytest.raises(SessionError):
        doc.rename("export_fbx", "x")  # build phase, where it does not exist


def test_schema_6_round_trip(tmp_path):
    doc = _mixed()
    loaded = Document.load(doc.save(tmp_path / "s.tr"))
    assert SCHEMA_VERSION == 6
    assert loaded.schema == 6
    assert loaded.paths() == ["import_model", "kinematics"]
    assert loaded.paths(phase=PUBLISH) == ["export_fbx", "export_maya"]


def test_schema_5_file_loads_with_an_empty_publish_list(tmp_path):
    path = tmp_path / "old.tr"
    path.write_text(
        json.dumps(
            {
                "schema": 5,
                "meta": {},
                "guides": {},
                "actions": [
                    {"name": "kinematics", "type": "kinematics",
                     "enabled": True, "settings": {}, "children": []}
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded = Document.load(path)
    assert loaded.paths() == ["kinematics"]
    assert loaded.publish == []
    assert loaded.schema == SCHEMA_VERSION


def test_copy_carries_both_lists():
    clone = _mixed().copy()
    assert clone.paths() == ["import_model", "kinematics"]
    assert clone.paths(phase=PUBLISH) == ["export_fbx", "export_maya"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_document_trigger.py -q`
Expected: FAIL — `ImportError: cannot import name 'BUILD'`.

- [ ] **Step 3: Add the phase vocabulary and the `publish` list**

In `core/document.py`, replace the module constants block:

```python
SCHEMA_VERSION = 6
EXTENSION = ".tr"
SEPARATOR = "/"

#: The two action lists a session holds. ``build`` makes the rig; ``publish``
#: runs only as the tail of a full build (see the 2026-09-03 design).
BUILD = "build"
PUBLISH = "publish"
PHASES = (BUILD, PUBLISH)
```

In the `Document` dataclass, add the field after `actions` and before `guides`:

```python
    #: Post-build actions. Never run on their own: a publish action only ever
    #: executes as the tail of a fresh build, so it is guaranteed to see a
    #: scene that build just produced.
    publish: list[ActionNode] = field(default_factory=list)
```

Add `"publish"` to `to_dict` and `from_dict`:

```python
    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "meta": dict(self.meta),
            "actions": [node.to_dict() for node in self.actions],
            "publish": [node.to_dict() for node in self.publish],
            "guides": self.guides.to_dict(),
        }
```

and inside `from_dict`'s `return cls(...)`, after the `actions=` line:

```python
            publish=[ActionNode.from_dict(item) for item in data.get("publish", [])],
```

- [ ] **Step 4: Add `roots()` and thread `phase` through every tree method**

Add `roots()` at the top of the `# --------------- tree` section of `Document`:

```python
    # --------------------------------------------------------------- tree
    def roots(self, phase: str = BUILD) -> list[ActionNode]:
        """The top-level actions of one phase. The single seam between the
        two lists: everything below resolves its root through this."""
        if phase == BUILD:
            return self.actions
        if phase == PUBLISH:
            return self.publish
        raise SessionError(f"Unknown phase '{phase}'.")
```

Then give each method a trailing `phase: str = BUILD` keyword and swap its root
lookup. The complete set of edits:

```python
    def walk(self, phase: str = BUILD) -> Iterator[tuple[str, ActionNode, Optional[ActionNode]]]:
        """Yield ``(path, node, parent)`` depth-first."""

        def _walk(nodes, parent, prefix):
            for node in nodes:
                path = join_path(prefix, node.name)
                yield path, node, parent
                yield from _walk(node.children, node, path)

        yield from _walk(self.roots(phase), None, "")

    def paths(self, phase: str = BUILD) -> list[str]:
        return [path for path, _node, _parent in self.walk(phase)]

    def find(self, path: str, phase: str = BUILD) -> Optional[ActionNode]:
        nodes = self.roots(phase)
        node = None
        for part in split_path(path):
            node = next((item for item in nodes if item.name == part), None)
            if node is None:
                return None
            nodes = node.children
        return node

    def require(self, path: str, phase: str = BUILD) -> ActionNode:
        node = self.find(path, phase)
        if node is None:
            raise SessionError(f"No action at '{path}'.")
        return node

    def parent_of(self, path: str, phase: str = BUILD) -> Optional[ActionNode]:
        parts = split_path(path)
        return self.find(join_path(*parts[:-1]), phase) if len(parts) > 1 else None

    def siblings(self, parent_path: Optional[str], phase: str = BUILD) -> list[ActionNode]:
        if not parent_path:
            return self.roots(phase)
        return self.require(parent_path, phase).children

    def path_of(self, node: ActionNode, phase: str = BUILD) -> Optional[str]:
        for path, candidate, _parent in self.walk(phase):
            if candidate is node:
                return path
        return None

    def unique_name(self, parent_path: Optional[str], base: str, phase: str = BUILD) -> str:
        names = {node.name for node in self.siblings(parent_path, phase)}
        ...  # body unchanged below this line
```

`add`, `remove`, `move`, `rename`, `duplicate` follow the same pattern —
`phase` is the last keyword argument, and every internal call to
`self.actions`, `siblings`, `require`, `parent_of`, `unique_name` or `find`
passes it through:

```python
    def add(self, node: ActionNode, parent: Optional[str] = None,
            index: Optional[int] = None, phase: str = BUILD) -> str:
        """Insert ``node`` and return its path (name made unique among siblings)."""
        siblings = self.siblings(parent, phase)
        node.name = self.unique_name(parent, node.name, phase)
        if index is None:
            siblings.append(node)
        else:
            siblings.insert(index, node)
        return join_path(parent or "", node.name)

    def remove(self, path: str, phase: str = BUILD) -> ActionNode:
        node = self.require(path, phase)
        parent = self.parent_of(path, phase)
        siblings = parent.children if parent is not None else self.roots(phase)
        siblings.remove(node)
        return node

    def move(self, path: str, parent: Optional[str] = None, index: Optional[int] = None,
             after: Optional[str] = None, phase: str = BUILD) -> str:
        """Move an action (and its subtree) *within one phase*.

        There is no cross-phase move: the caller removes from one list and adds
        to the other, which is what a drag between the two trees performs.
        """
        node = self.require(path, phase)
        if after is not None:
            after_node = self.require(after, phase)
            parts = split_path(after)
            parent = join_path(*parts[:-1]) or None
        if parent and (parent == path or parent.startswith(path + SEPARATOR)):
            raise SessionError("Cannot move an action under itself.")
        old_parent = self.parent_of(path, phase)
        old_siblings = old_parent.children if old_parent is not None else self.roots(phase)
        old_index = old_siblings.index(node)
        old_siblings.pop(old_index)
        new_siblings = self.siblings(parent, phase)
        if after is not None:
            index = new_siblings.index(after_node) + 1
        elif index is None:
            index = len(new_siblings)
        elif new_siblings is old_siblings and index > old_index:
            index -= 1
        if new_siblings is not old_siblings:
            node.name = self.unique_name(parent, node.name, phase)
        new_siblings.insert(index, node)
        return join_path(parent or "", node.name)

    def rename(self, path: str, new_name: str, phase: str = BUILD) -> str:
        node = self.require(path, phase)
        if SEPARATOR in new_name or not new_name.strip():
            raise SessionError(f"Invalid action name '{new_name}'.")
        parent = self.parent_of(path, phase)
        siblings = parent.children if parent is not None else self.roots(phase)
        if any(item is not node and item.name == new_name for item in siblings):
            raise SessionError(f"An action named '{new_name}' already exists here.")
        node.name = new_name
        parent_path = join_path(*split_path(path)[:-1])
        return join_path(parent_path, new_name)

    def duplicate(self, path: str, phase: str = BUILD) -> str:
        node = self.require(path, phase)
        parent = self.parent_of(path, phase)
        siblings = parent.children if parent is not None else self.roots(phase)
        clone = node.copy()
        parent_path = join_path(*split_path(path)[:-1])
        return self.add(clone, parent=parent_path or None,
                        index=siblings.index(node) + 1, phase=phase)
```

- [ ] **Step 5: Export the phase constants from `core/__init__.py`**

Change the document import line and the `__all__` list:

```python
from .document import BUILD, PHASES, PUBLISH, ActionNode, Document
```

and add `"BUILD"`, `"PUBLISH"`, `"PHASES"` to `__all__` right after `"Document"`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_document_trigger.py -q`
Expected: PASS, all tests in the file (the pre-existing ones must still pass — they call every method with no `phase`, which defaults to `BUILD`).

- [ ] **Step 7: Run the wider unit suite for regressions**

Run: `make tests-unit`
Expected: PASS. `test_import_boundaries.py` must still pass — nothing added here imports Maya or Qt.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/core/document.py src/python/tik/trigger/core/__init__.py tests/unit/test_document_trigger.py
git commit -m "feat(trigger): phase-aware Document with a publish action list"
```

---

### Task 2: Action scope in the registry

**Files:**
- Modify: `src/python/tik/trigger/core/registry.py`
- Modify: `src/python/tik/trigger/core/action.py`
- Modify: `src/python/tik/trigger/actions/script/script.py`
- Test: `tests/unit/test_core_trigger.py`

**Interfaces:**
- Consumes: `BUILD`, `PUBLISH` from `core/document.py` (Task 1).
- Produces:
  - `BOTH: str = "both"`, `SCOPES: tuple = ("build", "publish", "both")` in `core/registry.py`.
  - `register_action(name, category="utility", icon="", scope=BUILD)` — stamps `cls.scope`; raises `RegistryError` on an unknown scope.
  - `registry.iter_actions(scope: Optional[str] = None) -> list[type]`
  - `registry.allows(action_type: str, phase: str) -> bool` — `False` for an unregistered type.
  - `Action.scope: str = "build"` class attribute.

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/unit/test_core_trigger.py`:

```python
def test_action_scope_defaults_to_build_and_is_stamped():
    from tik.trigger.core import Action, clear_registries, register_action
    from tik.trigger.core.document import BUILD, PUBLISH
    from tik.trigger.core.registry import BOTH, allows, iter_actions

    clear_registries()

    class Plain(Action):
        def run(self, ctx):
            pass

    class Exporter(Action):
        def run(self, ctx):
            pass

    class Either(Action):
        def run(self, ctx):
            pass

    register_action("plain")(Plain)
    register_action("exporter", scope=PUBLISH)(Exporter)
    register_action("either", scope=BOTH)(Either)

    assert Plain.scope == BUILD
    assert Exporter.scope == PUBLISH
    assert Either.scope == BOTH

    assert allows("plain", BUILD) and not allows("plain", PUBLISH)
    assert allows("exporter", PUBLISH) and not allows("exporter", BUILD)
    assert allows("either", BUILD) and allows("either", PUBLISH)
    assert not allows("ghost", BUILD)

    assert {cls.action_type for cls in iter_actions()} == {"plain", "exporter", "either"}
    assert {cls.action_type for cls in iter_actions(scope=BUILD)} == {"plain", "either"}
    assert {cls.action_type for cls in iter_actions(scope=PUBLISH)} == {"exporter", "either"}

    clear_registries()


def test_unknown_action_scope_is_rejected():
    import pytest as _pytest

    from tik.trigger.core import Action, clear_registries, register_action
    from tik.trigger.core.exceptions import RegistryError

    clear_registries()

    class Nope(Action):
        def run(self, ctx):
            pass

    with _pytest.raises(RegistryError):
        register_action("nope", scope="sideways")(Nope)

    clear_registries()


def test_base_action_declares_a_scope():
    from tik.trigger.core import Action
    from tik.trigger.core.document import BUILD

    assert Action.scope == BUILD


def test_script_action_is_usable_in_both_lists():
    from tik.trigger.core.discovery import discover
    from tik.trigger.core.document import BUILD, PUBLISH
    from tik.trigger.core.registry import allows

    discover()
    assert allows("script", BUILD) and allows("script", PUBLISH)
    assert allows("kinematics", BUILD) and not allows("kinematics", PUBLISH)
    assert not allows("reference", PUBLISH)
```

> **Note for the implementer:** check how `tests/unit/test_core_trigger.py` already
> populates the registry before writing `test_script_action_is_usable_in_both_lists`.
> If `tik.trigger.core.discovery.discover()` is not the helper that file uses,
> use whatever it does use (e.g. `import tik.trigger` then `registry.get_action`)
> — the assertion is what matters, not the import route. If the file has an
> autouse fixture that calls `clear_registries()`, drop the local
> `clear_registries()` calls from the first two tests and rely on it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_core_trigger.py -q`
Expected: FAIL — `TypeError: register_action() got an unexpected keyword argument 'scope'`.

- [ ] **Step 3: Add scope to the registry**

In `core/registry.py`, add the import and the scope vocabulary after the existing
`_ACTIONS` declaration:

```python
from .document import BUILD, PUBLISH
from .exceptions import DuplicateRegistrationError, NotFoundError, RegistryError

...

#: An action's scope says which list it may be placed in. This is a *placement*
#: rule for the UI and ``Session.add``; the runner never checks it.
BOTH = "both"
SCOPES = (BUILD, PUBLISH, BOTH)
```

Widen the decorator:

```python
def register_action(
    name: str, category: str = "utility", icon: str = "", scope: str = BUILD
) -> Callable[[Type[T]], Type[T]]:
    """Register an ``Action`` subclass under ``name``.

    Args:
        category: Shelf/palette group (``structure``, ``build``, ``deform``...).
        icon: Icon name (defaults to ``name``).
        scope: Which action list this may live in -- ``build`` (default),
            ``publish`` or ``both``.
    """
    if scope not in SCOPES:
        raise RegistryError(f"Unknown action scope '{scope}'; expected one of {SCOPES}.")

    def inner(cls: Type[T]) -> Type[T]:
        ...  # existing body
        cls.category = category  # type: ignore[attr-defined]
        cls.icon = icon or name  # type: ignore[attr-defined]
        cls.scope = scope  # type: ignore[attr-defined]
        ...
```

Replace `iter_actions` and add `allows`:

```python
def iter_actions(scope: Optional[str] = None) -> list[type]:
    """Return registered action classes, optionally only those fitting ``scope``."""
    classes = [_ACTIONS[name] for name in list_actions()]
    if scope is None:
        return classes
    return [cls for cls in classes if _scope_allows(getattr(cls, "scope", BUILD), scope)]


def _scope_allows(scope: str, phase: str) -> bool:
    return scope == BOTH or scope == phase


def allows(action_type: str, phase: str) -> bool:
    """Whether ``action_type`` may be placed in the ``phase`` list.

    ``False`` for an unregistered type, so callers can use this as a plain
    guard without catching :class:`NotFoundError`.
    """
    try:
        cls = get_action(action_type)
    except NotFoundError:
        return False
    return _scope_allows(getattr(cls, "scope", BUILD), phase)
```

Add `from typing import Callable, Optional, Type, TypeVar` at the top (the module
currently imports `Callable, Type, TypeVar`).

> **Import-cycle check:** `core/document.py` imports only `.exceptions` and
> `.guide_document`, and `.guide_document` imports nothing from this package —
> so `registry -> document` adds no cycle.

- [ ] **Step 4: Declare the scope on `Action` and widen `script`**

In `core/action.py`, in the `Action` class attribute block:

```python
    label: str = ""
    action_type: str = ""  # stamped by @register_action
    category: str = "utility"  # stamped by @register_action
    scope: str = "build"  # stamped by @register_action: build | publish | both
    icon: str = ""  # stamped by @register_action
    info: str = ""  # shown by the "?" button; defaults to the class docstring
```

In `actions/script/script.py`, widen the decorator:

```python
@register_action("script", category="structure", icon="script", scope="both")
```

- [ ] **Step 5: Export `allows` from `core/__init__.py`**

Add `allows` to the `from .registry import (...)` list and to `__all__`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_core_trigger.py -q`
Expected: PASS.

- [ ] **Step 7: Run the wider unit suite for regressions**

Run: `make tests-unit`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/core/registry.py src/python/tik/trigger/core/action.py src/python/tik/trigger/core/__init__.py src/python/tik/trigger/actions/script/script.py tests/unit/test_core_trigger.py
git commit -m "feat(trigger): action scope declares which list an action may live in"
```

---

### Task 3: Runner phases and the single Build & Publish run

**Files:**
- Modify: `src/python/tik/trigger/core/steps.py`
- Modify: `src/python/tik/trigger/maya/runner.py`
- Test: `tests/unit/test_runner_trigger.py`

**Interfaces:**
- Consumes: `Document.roots(phase)`, `BUILD`, `PUBLISH` (Task 1).
- Produces:
  - `Step(path, node, base_dir, chain=(), depth=0, linked=False, phase=BUILD)` — `phase` is the seventh positional field.
  - `Step.display_chain` prefixes non-build phases: `"publish: export_fbx"`.
  - `StepResult(path, status, seconds=0.0, error=None, phase=BUILD)`.
  - `Runner.plan(document, base_dir="", until=None, only=None, phase=BUILD) -> Plan`
  - `Runner.run(document, base_dir="", until=None, only=None, reset_scene=True, session=None, publish=False) -> list[StepResult]`
  - `STEP_STARTED` / `STEP_FINISHED` / `STEP_FAILED` events now carry a `phase=` keyword.

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/unit/test_runner_trigger.py`:

```python
from tik.trigger.core.document import BUILD, PUBLISH
from tik.trigger.core.steps import Plan


def _both_phases():
    doc = Document()
    doc.add(ActionNode("a", "mark", settings={"tag": "A"}))
    doc.add(ActionNode("b", "mark", settings={"tag": "B"}))
    doc.add(ActionNode("fbx", "mark", settings={"tag": "FBX"}), phase=PUBLISH)
    doc.add(ActionNode("ma", "mark", settings={"tag": "MA"}), phase=PUBLISH)
    return doc


def test_plan_is_per_phase():
    doc = _both_phases()
    runner = Runner()
    assert [step.path for step in runner.plan(doc, "D:/x").steps] == ["a", "b"]
    assert [step.path for step in runner.plan(doc, "D:/x", phase=PUBLISH).steps] == ["fbx", "ma"]
    assert {step.phase for step in runner.plan(doc, "D:/x", phase=PUBLISH).steps} == {PUBLISH}


def test_build_alone_never_runs_publish():
    Runner().run(_both_phases(), "D:/x")
    assert _marks() == ["a", "b"]


def test_build_and_publish_runs_one_continuous_sequence():
    results = Runner().run(_both_phases(), "D:/x", publish=True)
    assert _marks() == ["a", "b", "fbx", "ma"]
    assert [item.path for item in results] == ["a", "b", "fbx", "ma"]
    assert [item.phase for item in results] == [BUILD, BUILD, PUBLISH, PUBLISH]


def test_build_and_publish_resets_the_scene_exactly_once(monkeypatch):
    resets = []
    monkeypatch.setattr("tik.trigger.maya.runner.new_scene", lambda: resets.append(1))
    Runner().run(_both_phases(), "D:/x", publish=True)
    assert len(resets) == 1


def test_progress_spans_both_phases():
    seen = []
    events = EventBus()
    events.subscribe("progress", lambda current=0, total=0, label="", **_kw: seen.append((current, total)))
    Runner(events).run(_both_phases(), "D:/x", publish=True)
    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_until_cannot_be_combined_with_publish():
    with pytest.raises(SessionError):
        Runner().run(_both_phases(), "D:/x", until="a", publish=True)
    assert _marks() == []


def test_a_failing_publish_step_aborts_and_names_its_phase():
    doc = _both_phases()
    doc.add(ActionNode("bad", "boom"), phase=PUBLISH, index=0)
    with pytest.raises(ActionExecutionError) as caught:
        Runner().run(doc, "D:/x", publish=True)
    assert "publish: bad" in str(caught.value)
    assert _marks() == ["a", "b"]  # the build half completed, publish stopped at 'bad'


def test_step_events_carry_their_phase():
    seen = []
    events = EventBus()
    events.subscribe(STEP_FINISHED, lambda path="", phase="", **_kw: seen.append((phase, path)))
    Runner(events).run(_both_phases(), "D:/x", publish=True)
    assert seen == [(BUILD, "a"), (BUILD, "b"), (PUBLISH, "fbx"), (PUBLISH, "ma")]


def test_a_reference_contributes_build_actions_only(tmp_path):
    inner = Document()
    inner.add(ActionNode("inner_build", "mark", settings={"tag": "IB"}))
    inner.add(ActionNode("inner_publish", "mark", settings={"tag": "IP"}), phase=PUBLISH)
    inner.save(tmp_path / "base.tr")

    outer = Document()
    outer.add(ActionNode("ref", "reference", settings={"file": "base.tr"}))
    outer.add(ActionNode("own", "mark", settings={"tag": "OWN"}), phase=PUBLISH)

    Runner().run(outer, str(tmp_path), publish=True)
    assert _marks() == ["ref/inner_build", "own"]
```

> **Note for the implementer:** `_marks()` and the `Mark` / `Boom` actions
> already exist at the top of this file, as does the autouse `_registered`
> fixture that registers `mark`, `boom` and `reference`. `EventBus`,
> `SessionError` and `STEP_FINISHED` are already imported there;
> add `Plan`, `BUILD` and `PUBLISH` to the imports as shown.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_runner_trigger.py -q`
Expected: FAIL — `TypeError: plan() got an unexpected keyword argument 'phase'`.

- [ ] **Step 3: Add `phase` to `Step` and `StepResult`**

In `core/steps.py`, change the import and the two dataclasses:

```python
from .document import BUILD, ActionNode
```

```python
@dataclass
class Step:
    """A runnable action with its resolved context."""

    path: str
    node: ActionNode
    base_dir: str
    chain: tuple[str, ...] = ()  # referenced files leading here
    depth: int = 0
    linked: bool = False
    phase: str = BUILD

    @property
    def display_chain(self) -> str:
        text = " > ".join([*(Path(item).name for item in self.chain), self.path])
        # the build list is the unmarked case; naming it would only add noise
        return text if self.phase == BUILD else f"{self.phase}: {text}"


@dataclass
class StepResult:
    path: str
    status: str  # "done" | "failed" | "skipped"
    seconds: float = 0.0
    error: Optional[str] = None
    phase: str = BUILD
```

- [ ] **Step 4: Plan per phase and concatenate in `run`**

In `maya/runner.py`, update the imports:

```python
from tik.trigger.core.document import BUILD, PUBLISH, Document, join_path
```

Replace `plan`, `_collect`, `_collect_reference` and `run`:

```python
    def plan(
        self,
        document: Document,
        base_dir: str = "",
        until: Optional[str] = None,
        only: Optional[str] = None,
        phase: str = BUILD,
    ) -> Plan:
        """Flatten one phase of ``document`` depth-first, expanding references."""
        plan = Plan()
        self._collect(document.roots(phase), "", base_dir, (), 0, False, plan, phase)
        if only is not None:
            plan.steps = [step for step in plan.steps if step.path == only]
            if not plan.steps:
                raise SessionError(f"No runnable action at '{only}'.")
        elif until is not None:
            if not any(step.path == until for step in plan.steps):
                raise SessionError(f"No runnable action at '{until}'.")
            kept = []
            for step in plan.steps:
                kept.append(step)
                if step.path == until:
                    break
            plan.steps = kept
        return plan

    def _collect(self, nodes, prefix, base_dir, chain, depth, linked, plan, phase) -> None:
        for node in nodes:
            path = join_path(prefix, node.name)
            if not node.enabled:
                continue
            if node.type == REFERENCE_TYPE:
                self._collect_reference(node, path, base_dir, chain, depth, plan, phase)
                continue
            plan.steps.append(Step(path, node, base_dir, chain, depth, linked, phase))
            self._collect(node.children, path, base_dir, chain, depth + 1, linked, plan, phase)

    def _collect_reference(self, node, path, base_dir, chain, depth, plan, phase) -> None:
        from tik.trigger.actions.reference.reference import Reference  # local: avoids cycle

        try:
            expanded, ref_dir, ref_file = Reference.expand(node, base_dir, self.loader, chain)
        except SessionError as error:
            plan.problems.append(f"{path}: {error}")
            self.events.log(f"{path}: {error}", level="error")
            raise
        # ``expanded.actions`` only, never ``expanded.publish``: publishing is
        # an act of the top-level session. The hero rig decides what gets
        # exported; the base rig it consumes does not.
        self._collect(expanded.actions, path, ref_dir, chain + (ref_file,), depth + 1, True, plan, phase)
        # a reference may also carry its own (local) children, run after the referenced ones
        self._collect(node.children, path, base_dir, chain, depth + 1, False, plan, phase)

    # -------------------------------------------------------------- running
    def run(
        self,
        document: Document,
        base_dir: str = "",
        until: Optional[str] = None,
        only: Optional[str] = None,
        reset_scene: bool = True,
        session: Any = None,
        publish: bool = False,
    ) -> list[StepResult]:
        """Run the build list, and -- with ``publish`` -- the publish list after it.

        One scene reset, one continuous sequence: a publish action is only ever
        reached through a full clean build, so it always sees a scene this run
        just produced.
        """
        if publish and until is not None:
            raise SessionError(
                "'until' cannot be combined with publish: a partial build must not publish."
            )
        steps = list(self.plan(document, base_dir, until=until, only=only, phase=BUILD).steps)
        if publish:
            steps += self.plan(document, base_dir, phase=PUBLISH).steps
        if reset_scene and only is None:
            new_scene()
        results: list[StepResult] = []
        total = len(steps)
        for number, step in enumerate(steps, start=1):
            self.events.progress(number, total, step.path)
            results.append(self._run_step(step, session))
        return results
```

- [ ] **Step 5: Carry the phase through step events and results**

In `_run_step`, add `phase=step.phase` to all three `emit` calls and to the
returned `StepResult`:

```python
        self.events.emit(STEP_STARTED, path=step.path, phase=step.phase)
        started = time.perf_counter()
        problems = action.validate(ctx)
        if problems:
            message = "; ".join(problems)
            self.events.emit(STEP_FAILED, path=step.path, phase=step.phase, error=message)
            raise ActionExecutionError(f"{step.display_chain}: {message}", action_name=step.path)
        try:
            with undo_chunk(f"Trigger: {step.display_chain}"):
                action.run(ctx)
        except Exception as error:  # noqa: BLE001 - report then wrap
            seconds = time.perf_counter() - started
            self.events.emit(STEP_FAILED, path=step.path, phase=step.phase,
                             error=str(error), seconds=seconds)
            self.events.error(error, context=step.display_chain)
            raise ActionExecutionError(f"{step.display_chain}: {error}", action_name=step.path) from error
        seconds = time.perf_counter() - started
        self.events.emit(STEP_FINISHED, path=step.path, phase=step.phase, seconds=seconds)
        self.events.log(f"{step.display_chain} done in {seconds:.2f} s")
        return StepResult(step.path, "done", seconds, phase=step.phase)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_runner_trigger.py -q`
Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 7: Run the wider unit suite for regressions**

Run: `make tests-unit`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/python/tik/trigger/core/steps.py src/python/tik/trigger/maya/runner.py tests/unit/test_runner_trigger.py
git commit -m "feat(trigger): runner plans per phase and runs build then publish in one pass"
```

---

### Task 4: `Session.publish` and `build(publish=True)`

**Files:**
- Modify: `src/python/tik/trigger/session.py`
- Test: `tests/unit/test_session_trigger.py`

**Interfaces:**
- Consumes: `Document` phase methods (Task 1), `registry.allows` (Task 2), `Runner.run(..., publish=)` (Task 3).
- Produces:
  - `ActionHandle(session, node, path, ref_handle=None, ref_path="", phase=BUILD)` with a read-only `phase` property.
  - `PhaseView` with `.phase`, `.actions`, `[path]`, `.find`, `.paths`, `.walk`, `.add`, `.remove`, `.move`, `.rename`, `.duplicate`, `__contains__`, `__len__`, `__iter__`.
  - `Session.view(phase=BUILD) -> PhaseView` (cached per phase).
  - `Session.publish -> PhaseView` — the publish list.
  - `Session.handle(path, phase=BUILD) -> ActionHandle`.
  - `Session.add(..., phase=BUILD)`, `remove/move/rename/duplicate(..., phase=BUILD)`.
  - `Session.build(until=None, reset_scene=True, publish=False)`.
  - `Session.steps(until=None, phase=BUILD)`.

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/unit/test_session_trigger.py`:

```python
def test_publish_namespace_is_a_separate_list():
    from tik.trigger.core.document import BUILD, PUBLISH

    rig = Session()
    rig.add("mark", "kine")
    rig.publish.add("mark", "fbx")
    rig.publish.add("mark", "ma")

    assert rig.paths() == ["kine"]
    assert rig.publish.paths() == ["fbx", "ma"]
    assert rig.publish["fbx"].phase == PUBLISH
    assert rig["kine"].phase == BUILD
    assert "fbx" not in rig
    assert "fbx" in rig.publish
    assert rig.find("fbx") is None
    assert len(rig.publish) == 2
    assert [handle.name for handle in rig.publish] == ["fbx", "ma"]


def test_publish_settings_and_tree_edits_go_through_the_view():
    rig = Session()
    rig.publish.add("mark", "fbx", tag="FBX")
    assert rig.publish["fbx"].tag == "FBX"
    rig.publish["fbx"].tag = "changed"
    assert rig.publish["fbx"].tag == "changed"
    rig.publish["fbx"].enabled = False
    assert rig.publish["fbx"].enabled is False
    assert rig.publish.duplicate("fbx").path == "fbx1"
    assert rig.publish.rename("fbx1", "copy").path == "copy"
    rig.publish.remove("copy")
    assert rig.publish.paths() == ["fbx"]


def test_publish_edits_are_undoable_and_dirty_the_session():
    rig = Session()
    rig.add("mark", "kine")
    assert rig.is_modified
    rig.publish.add("mark", "fbx")
    assert rig.publish.paths() == ["fbx"]
    assert rig.undo()
    assert rig.publish.paths() == []
    assert rig.paths() == ["kine"]
    assert rig.redo()
    assert rig.publish.paths() == ["fbx"]


def test_scope_is_enforced_when_adding():
    from tik.trigger.core.exceptions import SessionError as _SessionError

    rig = Session()
    # 'mark' is registered build-only by this module's fixture
    with pytest.raises(_SessionError):
        rig.publish.add("mark_build_only")
    with pytest.raises(_SessionError):
        rig.add("mark_publish_only")


def test_publish_actions_are_never_individually_runnable():
    rig = Session()
    rig.publish.add("mark", "fbx")
    with pytest.raises(SessionError):
        rig.run("fbx")


def test_until_cannot_be_combined_with_publish():
    rig = Session()
    rig.add("mark", "kine")
    rig.publish.add("mark", "fbx")
    with pytest.raises(SessionError):
        rig.build(until="kine", publish=True)


def test_build_and_publish_runs_both_lists():
    rig = Session()
    rig.add("mark", "kine")
    rig.publish.add("mark", "fbx")
    assert [item.path for item in rig.build()] == ["kine"]
    assert [item.path for item in rig.build(publish=True)] == ["kine", "fbx"]


def test_steps_and_validate_cover_both_phases():
    from tik.trigger.core.document import PUBLISH

    rig = Session()
    rig.add("mark", "kine")
    rig.publish.add("mark", "fbx")
    assert [step.path for step in rig.steps()] == ["kine"]
    assert [step.path for step in rig.steps(phase=PUBLISH)] == ["fbx"]
    assert rig.validate() == []


def test_publish_survives_a_save_and_reopen(tmp_path):
    rig = Session()
    rig.add("mark", "kine")
    rig.publish.add("mark", "fbx", tag="FBX")
    rig.save(tmp_path / "hero.tr")
    reopened = Session.open(str(tmp_path / "hero.tr"))
    assert reopened.paths() == ["kine"]
    assert reopened.publish.paths() == ["fbx"]
    assert reopened.publish["fbx"].tag == "FBX"
```

> **Note for the implementer:** this file has an autouse fixture registering
> its toy actions. Extend it so the scope test has something to assert
> against — register `mark` with the default (build) scope, plus:
>
> ```python
> register_action("mark_build_only")(Mark)
> register_action("mark_publish_only", scope="publish")(Mark)
> ```
>
> If `mark` in this file is registered under a different name, adapt the test
> bodies to it. `pytest` and `SessionError` are already imported there.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_session_trigger.py -q`
Expected: FAIL — `AttributeError: 'Session' object has no attribute 'publish'` (or the `PhaseView` name error).

- [ ] **Step 3: Give `ActionHandle` a phase**

In `session.py`, update the imports:

```python
from tik.trigger.core.document import (
    BUILD,
    EXTENSION,
    PHASES,
    PUBLISH,
    ActionNode,
    Document,
    join_path,
    split_path,
)
```

and add `"_phase"` to `_SETTINGS_ONLY`.

Widen `ActionHandle.__init__` and add the property:

```python
    def __init__(self, session: "Session", node: ActionNode, path: str,
                 ref_handle: Optional["ActionHandle"] = None, ref_path: str = "",
                 phase: str = BUILD) -> None:
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "_node", node)
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "_ref_handle", ref_handle)
        object.__setattr__(self, "_ref_path", ref_path)
        object.__setattr__(self, "_phase", phase)
        object.__setattr__(self, "_linked", ref_handle is not None)

    @property
    def phase(self) -> str:
        """Which of the session's two lists this handle came from."""
        return self._phase
```

Update `__repr__` to name a non-build phase:

```python
    def __repr__(self) -> str:
        flag = " linked" if self._linked else ""
        where = "" if self._phase == BUILD else f" [{self._phase}]"
        return f"<Action {self._path} ({self._node.type}){flag}{where}>"
```

Propagate the phase everywhere a child handle is built — in `children`,
`_referenced_children` and `add`:

```python
    @property
    def children(self) -> list["ActionHandle"]:
        if self._linked:
            return [
                ActionHandle(self._session, child, join_path(self._path, child.name),
                             self._ref_handle, join_path(self._ref_path, child.name),
                             phase=self._phase)
                for child in self._node.children
            ]
        own = [
            ActionHandle(self._session, child, join_path(self._path, child.name),
                         phase=self._phase)
            for child in self._node.children
        ]
        if self._node.type == REFERENCE_TYPE:
            return self._referenced_children() + own
        return own

    def _referenced_children(self) -> list["ActionHandle"]:
        try:
            document = self._session._referenced_document(self)
        except SessionError:
            return []
        return [
            ActionHandle(self._session, child, join_path(self._path, child.name),
                         self, child.name, phase=self._phase)
            for child in document.actions
        ]

    def add(self, action_type: str, name: Optional[str] = None,
            index: Optional[int] = None, **settings) -> "ActionHandle":
        if self._linked:
            raise SessionError("Cannot add actions inside a referenced session; open it instead.")
        return self._session.add(action_type, name, parent=self._path, index=index,
                                 phase=self._phase, **settings)
```

- [ ] **Step 4: Add `PhaseView`**

Insert this class between `ActionHandle` and `Session` in `session.py`:

```python
class PhaseView:
    """The tree API of one of a session's two action lists.

    ``session.publish`` is one of these. It holds no state of its own -- every
    verb delegates to the session with its phase attached -- so undo, the dirty
    flag and the reference cache behave identically in both lists.
    """

    def __init__(self, session: "Session", phase: str) -> None:
        self._session = session
        self._phase = phase

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def actions(self) -> list[ActionHandle]:
        return self._session.root_handles(self._phase)

    def __getitem__(self, path: str) -> ActionHandle:
        return self._session.handle(path, phase=self._phase)

    def find(self, path: str) -> Optional[ActionHandle]:
        try:
            return self[path]
        except SessionError:
            return None

    def __contains__(self, path: str) -> bool:
        return self.find(path) is not None

    def __iter__(self):
        return iter(self.actions)

    def __len__(self) -> int:
        return len(self._session.document.roots(self._phase))

    def paths(self) -> list[str]:
        return self._session.document.paths(self._phase)

    def walk(self) -> list[ActionHandle]:
        return self._session.walk(phase=self._phase)

    def add(self, action_type: str, name: Optional[str] = None, *,
            parent: Optional[str | ActionHandle] = None,
            after: Optional[str | ActionHandle] = None,
            index: Optional[int] = None, **settings) -> ActionHandle:
        return self._session.add(action_type, name, parent=parent, after=after,
                                 index=index, phase=self._phase, **settings)

    def remove(self, path: str | ActionHandle) -> None:
        self._session.remove(path, phase=self._phase)

    def move(self, path: str | ActionHandle, *, parent: Optional[str] = None,
             index: Optional[int] = None, after: Optional[str] = None) -> ActionHandle:
        return self._session.move(path, parent=parent, index=index, after=after,
                                  phase=self._phase)

    def rename(self, path: str | ActionHandle, new_name: str) -> ActionHandle:
        return self._session.rename(path, new_name, phase=self._phase)

    def duplicate(self, path: str | ActionHandle) -> ActionHandle:
        return self._session.duplicate(path, phase=self._phase)

    def __repr__(self) -> str:
        return f"<PhaseView {self._phase}: {len(self)} actions>"
```

- [ ] **Step 5: Thread the phase through `Session`**

In `Session.__init__`, add the view cache after `self._reference_cache`:

```python
        self._views: dict[str, PhaseView] = {}
```

Replace the tree section of `Session` (from the `actions` property down to
`duplicate`) with the phase-aware version:

```python
    # -------------------------------------------------------------- tree
    def view(self, phase: str = BUILD) -> PhaseView:
        """The tree API of one phase. ``session.publish`` is the publish one."""
        if phase not in PHASES:
            raise SessionError(f"Unknown phase '{phase}'.")
        if phase not in self._views:
            self._views[phase] = PhaseView(self, phase)
        return self._views[phase]

    @property
    def publish(self) -> PhaseView:
        """This session's publish list. Runs only as the tail of a full build."""
        return self.view(PUBLISH)

    def root_handles(self, phase: str = BUILD) -> list[ActionHandle]:
        return [ActionHandle(self, node, node.name, phase=phase)
                for node in self.document.roots(phase)]

    @property
    def actions(self) -> list[ActionHandle]:
        return self.root_handles(BUILD)

    def walk(self, phase: str = BUILD) -> list[ActionHandle]:
        """Every handle depth-first, including referenced (linked) ones."""
        found: list[ActionHandle] = []

        def _visit(handle: ActionHandle) -> None:
            found.append(handle)
            for child in handle.children:
                _visit(child)

        for handle in self.root_handles(phase):
            _visit(handle)
        return found

    def handle(self, path: str, phase: str = BUILD) -> ActionHandle:
        parts = split_path(path)
        if not parts:
            raise SessionError("Empty action path.")
        root = next((item for item in self.root_handles(phase) if item.name == parts[0]), None)
        if root is None:
            raise SessionError(f"No action at '{parts[0]}'.")
        return root[join_path(*parts[1:])] if len(parts) > 1 else root

    def __getitem__(self, path: str) -> ActionHandle:
        return self.handle(path, BUILD)

    def find(self, path: str) -> Optional[ActionHandle]:
        try:
            return self[path]
        except SessionError:
            return None

    def __contains__(self, path: str) -> bool:
        return self.find(path) is not None

    def paths(self, phase: str = BUILD) -> list[str]:
        return self.document.paths(phase)

    def add(
        self,
        action_type: str,
        name: Optional[str] = None,
        *,
        parent: Optional[str | ActionHandle] = None,
        after: Optional[str | ActionHandle] = None,
        index: Optional[int] = None,
        phase: str = BUILD,
        **settings,
    ) -> ActionHandle:
        """Add an action; ``after`` places it next to a sibling, ``parent`` nests it."""
        action_cls = registry.get_action(action_type)  # raises for an unknown type
        if not registry.allows(action_type, phase):
            raise SessionError(
                f"'{action_type}' cannot be placed in the {phase} list "
                f"(its scope is '{getattr(action_cls, 'scope', BUILD)}')."
            )
        action = action_cls(settings=settings)  # validates
        parent_path = parent.path if isinstance(parent, ActionHandle) else parent
        if after is not None:
            after_path = after.path if isinstance(after, ActionHandle) else after
            parts = split_path(after_path)
            parent_path = join_path(*parts[:-1]) or None
            siblings = self.document.siblings(parent_path, phase)
            index = [node.name for node in siblings].index(parts[-1]) + 1
        node = ActionNode(name=name or action_type, type=action_type, settings=action.values())
        path = self.document.add(node, parent=parent_path, index=index, phase=phase)
        self.touch()
        return self.handle(path, phase)

    def remove(self, path: str | ActionHandle, phase: str = BUILD) -> None:
        self.document.remove(path.path if isinstance(path, ActionHandle) else path, phase=phase)
        self.touch()

    def move(self, path: str | ActionHandle, *, parent: Optional[str] = None,
             index: Optional[int] = None, after: Optional[str] = None,
             phase: str = BUILD) -> ActionHandle:
        path = path.path if isinstance(path, ActionHandle) else path
        new_path = self.document.move(path, parent=parent, index=index, after=after, phase=phase)
        self.touch()
        return self.handle(new_path, phase)

    def rename(self, path: str | ActionHandle, new_name: str, phase: str = BUILD) -> ActionHandle:
        path = path.path if isinstance(path, ActionHandle) else path
        new_path = self.document.rename(path, new_name, phase=phase)
        self.touch()
        return self.handle(new_path, phase)

    def duplicate(self, path: str | ActionHandle, phase: str = BUILD) -> ActionHandle:
        path = path.path if isinstance(path, ActionHandle) else path
        new_path = self.document.duplicate(path, phase=phase)
        self.touch()
        return self.handle(new_path, phase)
```

> Note `remove` takes `phase` positionally-or-by-keyword (not keyword-only),
> because `PhaseView.remove` calls it as `remove(path, phase=self._phase)` and
> `ui/model.py` will too.

- [ ] **Step 6: Widen `validate`, `build`, `run` and `steps`**

Replace the running section of `Session`:

```python
    def validate(self) -> list[str]:
        """Pre-flight problems for every runnable step, in both lists."""
        from tik.trigger.core.action import ActionContext

        runner = self._runner()
        problems: list[str] = []
        for phase in PHASES:
            prefix = "" if phase == BUILD else f"{phase}: "
            try:
                plan = runner.plan(self.document, self.directory, phase=phase)
            except SessionError as error:
                problems.append(f"{prefix}{error}")
                continue
            problems.extend(f"{prefix}{item}" for item in plan.problems)
            for step in plan.steps:
                action = registry.get_action(step.node.type)(settings=step.node.settings)
                ctx = ActionContext(session=self, events=self.events,
                                    base_dir=step.base_dir, path=step.path)
                problems.extend(f"{prefix}{step.path}: {item}" for item in action.validate(ctx))
        return problems

    def build(self, until: Optional[str | ActionHandle] = None, reset_scene: bool = True,
              publish: bool = False) -> list[StepResult]:
        """Reset the scene and run the build list; with ``publish``, the publish list after it.

        ``until`` stops after that build action -- and forbids ``publish``,
        because a partial build is not a rig anyone should be exporting.
        """
        until = until.path if isinstance(until, ActionHandle) else until
        if publish and until is not None:
            raise SessionError(
                "'until' cannot be combined with publish: a partial build must not publish."
            )
        self.events.log(f"Building{' and publishing' if publish else ''} {self.name}")
        # The runner resets the scene, so the guides have to be in the document
        # before it does. Saving already captures; building must too, or a rig
        # built from an unsaved session has no guides at all.
        self.capture_guides()
        return self._runner().run(self.document, self.directory, until=until,
                                  reset_scene=reset_scene, session=self, publish=publish)

    def run(self, path: str | ActionHandle) -> StepResult:
        """Run a single build action in the current scene (no reset).

        Publish actions are deliberately excluded: the only way one executes is
        as the tail of a full clean build, so no partial or hand-edited rig can
        produce a published artifact.
        """
        path = path.path if isinstance(path, ActionHandle) else path
        if self.document.find(path, phase=PUBLISH) is not None:
            raise SessionError(
                f"'{path}' is a publish action; publish actions run only with Build & Publish."
            )
        self.capture_guides()
        return self._runner().run(self.document, self.directory, only=path,
                                  reset_scene=False, session=self)[0]

    def steps(self, until: Optional[str] = None, phase: str = BUILD):
        """The planned steps of one phase (what Build would run)."""
        return self._runner().plan(self.document, self.directory, until=until, phase=phase).steps

    def __repr__(self) -> str:
        return (f"Session({self.name}, {len(self.document.actions)} actions, "
                f"{len(self.document.publish)} publish)")
```

Also clear the view cache nowhere — `PhaseView` holds no snapshot, so `new()`,
`load()`, `undo()` and `redo()` need no change.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_session_trigger.py -q`
Expected: PASS.

- [ ] **Step 8: Run the wider unit suite for regressions**

Run: `make tests-unit`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/python/tik/trigger/session.py tests/unit/test_session_trigger.py
git commit -m "feat(trigger): session.publish namespace and build(publish=True)"
```

---

### Task 5: Phase-aware `PipelineModel` and cross-phase drag

**Files:**
- Modify: `src/python/tik/trigger/ui/model.py`
- Test: `tests/ui/test_pipeline_ui.py`

**Interfaces:**
- Consumes: `Session.view(phase)`, `Session.document.roots/find/remove/add`, `registry.allows` (Tasks 1, 2, 4).
- Produces:
  - `PipelineModel(session, parent=None, phase=BUILD)` with a `phase` attribute.
  - `MIME_PATH` payload format changes to `"<phase>:<path>"` items joined by `";"`.
  - `PipelineModel.cross_phase_moved` — a `QtCore.Signal()` emitted after a drop that moved an action out of another phase, so the view can rebuild the other model.

- [ ] **Step 1: Write the failing tests**

Add to `tests/ui/test_pipeline_ui.py`. Register a publish-scoped toy action by
extending the file's autouse `_registered` fixture with:

```python
    register_action("export", category="utility", scope="publish")(Mark)
    register_action("either", category="utility", scope="both")(Mark)
```

Then add these tests:

```python
def test_model_can_be_built_on_the_publish_phase(qapp):
    from tik.trigger.core.document import BUILD, PUBLISH
    from tik.trigger.ui.model import PipelineModel

    session = Session()
    session.add("mark", "kine")
    session.publish.add("export", "fbx")

    build_model = PipelineModel(session)
    publish_model = PipelineModel(session, phase=PUBLISH)
    assert build_model.phase == BUILD
    assert publish_model.phase == PUBLISH
    assert build_model.rowCount() == 1
    assert publish_model.rowCount() == 1
    assert publish_model.data(publish_model.index(0, 0)) == "fbx"


def test_shelf_drop_of_a_build_only_action_is_refused_by_the_publish_model(qapp):
    from tik.trigger.core.document import PUBLISH
    from tik.trigger.ui.model import MIME_TYPE, PipelineModel

    session = Session()
    model = PipelineModel(session, phase=PUBLISH)
    data = QtCore.QMimeData()
    data.setData(MIME_TYPE, b"mark")  # build-only
    assert not model.canDropMimeData(data, QtCore.Qt.CopyAction, -1, -1, QtCore.QModelIndex())
    assert not model.dropMimeData(data, QtCore.Qt.CopyAction, -1, -1, QtCore.QModelIndex())
    assert session.publish.paths() == []

    ok = QtCore.QMimeData()
    ok.setData(MIME_TYPE, b"export")
    assert model.canDropMimeData(ok, QtCore.Qt.CopyAction, -1, -1, QtCore.QModelIndex())
    assert model.dropMimeData(ok, QtCore.Qt.CopyAction, -1, -1, QtCore.QModelIndex())
    assert session.publish.paths() == ["export"]


def test_mime_paths_carry_their_phase(qapp):
    from tik.trigger.ui.model import MIME_PATH, PipelineModel

    session = Session()
    session.add("mark", "kine")
    model = PipelineModel(session)
    data = model.mimeData([model.index(0, 0)])
    assert bytes(data.data(MIME_PATH)).decode("utf-8") == "build:kine"


def test_dragging_a_both_scoped_action_between_the_two_trees(qapp):
    from tik.trigger.core.document import PUBLISH
    from tik.trigger.ui.model import MIME_PATH, PipelineModel

    session = Session()
    session.add("either", "hook")
    build_model = PipelineModel(session)
    publish_model = PipelineModel(session, phase=PUBLISH)

    data = build_model.mimeData([build_model.index(0, 0)])
    assert publish_model.dropMimeData(data, QtCore.Qt.MoveAction, -1, -1, QtCore.QModelIndex())
    assert session.paths() == []
    assert session.publish.paths() == ["hook"]


def test_dragging_a_build_only_action_into_publish_is_refused_and_changes_nothing(qapp):
    from tik.trigger.core.document import PUBLISH
    from tik.trigger.ui.model import PipelineModel

    session = Session()
    session.add("mark", "kine")
    build_model = PipelineModel(session)
    publish_model = PipelineModel(session, phase=PUBLISH)

    data = build_model.mimeData([build_model.index(0, 0)])
    assert not publish_model.dropMimeData(data, QtCore.Qt.MoveAction, -1, -1, QtCore.QModelIndex())
    assert session.paths() == ["kine"]
    assert session.publish.paths() == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_pipeline_ui.py -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'phase'`.

- [ ] **Step 3: Parameterise the model by phase**

In `ui/model.py`, update the imports and the constructor:

```python
from tik.trigger.core.document import BUILD
```

```python
class PipelineModel(QtCore.QAbstractItemModel):
    """Tree of ``ActionHandle`` snapshots for one phase; rebuilt on every edit."""

    edited = QtCore.Signal()
    #: emitted when a drop pulled an action out of the *other* phase, so the
    #: view knows the other model is now stale
    cross_phase_moved = QtCore.Signal()

    def __init__(self, session: Session, parent=None, phase: str = BUILD) -> None:
        super().__init__(parent)
        self.session = session
        self.phase = phase
        self._root = _Item(None, None)
        self._status: dict[str, str] = {}
        self._errors: dict[str, str] = {}
        self.rebuild()

    @property
    def view(self):
        """The session's tree API for this model's phase."""
        return self.session.view(self.phase)

    # ------------------------------------------------------------ building
    def rebuild(self) -> None:
        self.beginResetModel()
        self._root = _Item(None, None)
        self._populate(self._root, self.view.actions)
        self.endResetModel()
```

In `setData`'s `EditRole` branch, replace `self.session.rename(...)` with
`self.view.rename(...)`:

```python
            try:
                self.view.rename(handle.path, new_name)
            except SessionError:
                return False
```

- [ ] **Step 4: Carry the phase in the drag payload and honour scope on drop**

Replace `mimeData`, `canDropMimeData` and `dropMimeData`:

```python
    def mimeData(self, indexes):  # noqa: N802
        data = QtCore.QMimeData()
        # the phase travels with the path so a drop into the other tree knows
        # where the action is coming from
        tokens = [f"{self.phase}:{self.handle(index).path}"
                  for index in indexes if index.isValid()]
        data.setData(MIME_PATH, ";".join(tokens).encode("utf-8"))
        return data

    def canDropMimeData(self, data, action, row, column, parent):  # noqa: N802
        target = self.handle(parent) if parent.isValid() else None
        if target is not None and target.is_linked:
            return False
        if data.hasFormat(MIME_TYPE):
            action_type = bytes(data.data(MIME_TYPE)).decode("utf-8")
            return registry.allows(action_type, self.phase)
        return data.hasFormat(MIME_PATH)

    def dropMimeData(self, data, action, row, column, parent) -> bool:  # noqa: N802
        target = self.handle(parent) if parent.isValid() else None
        parent_path = target.path if target is not None else None
        index = None if row < 0 else row
        crossed = False
        try:
            if data.hasFormat(MIME_PATH):
                for token in bytes(data.data(MIME_PATH)).decode("utf-8").split(";"):
                    if not token:
                        continue
                    source_phase, _, path = token.partition(":")
                    if source_phase == self.phase:
                        self.view.move(path, parent=parent_path, index=index)
                    elif self._move_across(source_phase, path, parent_path, index):
                        crossed = True
                    else:
                        return False
                    if index is not None:
                        index += 1
            elif data.hasFormat(MIME_TYPE):
                action_type = bytes(data.data(MIME_TYPE)).decode("utf-8")
                self.view.add(action_type, parent=parent_path, index=index)
            else:
                return False
        except SessionError:
            return False
        self.rebuild()
        self.edited.emit()
        if crossed:
            self.cross_phase_moved.emit()
        return True

    def _move_across(self, source_phase: str, path: str,
                     parent_path: Optional[str], index: Optional[int]) -> bool:
        """Move one action from another phase into this one.

        There is no cross-phase ``move``: the document removes it from one list
        and adds it to the other. Scope is checked *before* the remove, so a
        refused drop leaves both lists exactly as they were.
        """
        document = self.session.document
        node = document.find(path, phase=source_phase)
        if node is None or not registry.allows(node.type, self.phase):
            return False
        document.remove(path, phase=source_phase)
        document.add(node, parent=parent_path, index=index, phase=self.phase)
        self.session.touch()
        return True
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_pipeline_ui.py -q`
Expected: PASS, including the file's pre-existing DnD tests.

> If a pre-existing test asserts the old bare-path `MIME_PATH` payload, update
> it to the `"build:<path>"` form — the payload change is intentional.

- [ ] **Step 6: Run the whole UI suite**

Run: `make tests-ui`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/ui/model.py tests/ui/test_pipeline_ui.py
git commit -m "feat(trigger-ui): phase-aware pipeline model with scope-checked cross-phase drops"
```

---

### Task 6: Split pipeline pane and the wired Build & Publish button

**Files:**
- Modify: `src/python/tik/trigger/ui/session_view.py`
- Modify: `src/python/tik/trigger/ui/settings_panel.py`
- Test: `tests/ui/test_pipeline_ui.py`

**Interfaces:**
- Consumes: `PipelineModel(session, phase=...)` and `cross_phase_moved` (Task 5), `Session.build(publish=True)` (Task 4), `registry.iter_actions(scope=)` (Task 2).
- Produces on `SessionView`:
  - `self.model` (build) and `self.publish_model`; `self.models: dict[str, PipelineModel]`
  - `self.tree` (build) and `self.publish_tree`; `self.trees: dict[str, PipelineTree]`
  - `self.focus_phase -> str` and `set_focus_phase(phase: str) -> None`
  - `current_phase -> str`, `current_handle()`, `current_path() -> Optional[str]` (of the focused tree)
  - `build_and_publish() -> bool`
  - `self.publish_button` enabled

> **Deviation from the spec, deliberate:** the spec said `current_path()` would
> return a `(phase, path)` pair. It stays `Optional[str]` (the focused tree's
> path) and a separate `current_phase` property carries the phase, because
> `ui/main.py`'s `_current_path()` feeds a bare path to `build_until` and
> `run_step`. Same information, no churn at the call sites.

- [ ] **Step 1: Write the failing tests**

Add to `tests/ui/test_pipeline_ui.py`:

```python
def test_session_view_has_two_trees(qapp):
    from tik.trigger.core.document import BUILD, PUBLISH

    session = Session()
    session.add("mark", "kine")
    session.publish.add("export", "fbx")
    view = SessionView(session)

    assert view.trees[BUILD] is view.tree
    assert view.trees[PUBLISH] is view.publish_tree
    assert view.models[PUBLISH].rowCount() == 1
    assert view.focus_phase == BUILD


def test_focus_phase_drives_the_current_row_and_the_until_button(qapp):
    from tik.trigger.core.document import BUILD, PUBLISH

    session = Session()
    session.add("mark", "kine")
    session.publish.add("export", "fbx")
    view = SessionView(session)

    view.tree.setCurrentIndex(view.model.index(0, 0))
    view.set_focus_phase(BUILD)
    assert view.current_path() == "kine"
    assert view.current_phase == BUILD
    assert view.until_button.isEnabled()

    view.publish_tree.setCurrentIndex(view.publish_model.index(0, 0))
    view.set_focus_phase(PUBLISH)
    assert view.current_path() == "fbx"
    assert view.current_phase == PUBLISH
    assert not view.until_button.isEnabled()


def test_the_shelf_offers_only_actions_that_fit_the_focused_phase(qapp):
    from tik.trigger.core.document import BUILD, PUBLISH

    view = SessionView(Session())
    build_keys = set(view.shelves[BUILD].tiles)
    publish_keys = set(view.shelves[PUBLISH].tiles)
    assert "mark" in build_keys and "mark" not in publish_keys
    assert "export" in publish_keys and "export" not in build_keys
    assert "either" in build_keys and "either" in publish_keys

    view.set_focus_phase(PUBLISH)
    assert view.shelf_stack.currentWidget() is view.shelves[PUBLISH]
    assert {entry.key for entry in view.palette.entries} == publish_keys


def test_adding_from_the_shelf_lands_in_the_focused_phase(qapp):
    from tik.trigger.core.document import PUBLISH

    session = Session()
    view = SessionView(session)
    view.set_focus_phase(PUBLISH)
    view.add_action("export")
    assert session.publish.paths() == ["export"]
    assert session.paths() == []


def test_publish_rows_offer_no_run_affordance(qapp):
    from tik.trigger.core.document import BUILD, PUBLISH

    session = Session()
    session.publish.add("export", "fbx")
    view = SessionView(session)
    handle = view.models[PUBLISH].handle(view.publish_model.index(0, 0))

    view.settings.set_handle(handle)
    assert not view.settings.run_button.isVisible()
    assert not view.settings.until_button.isVisible()

    assert view.run_step("fbx") is False  # refused by the session, reported not raised

    labels = [item.text() for item in view.context_menu_actions(PUBLISH, handle)]
    assert "Run step" not in labels
    assert "Build until here" not in labels

    session.add("mark", "kine")
    view.refresh()
    build_handle = view.models[BUILD].handle(view.model.index(0, 0))
    view.settings.set_handle(build_handle)
    assert view.settings.run_button.isVisible()
    build_labels = [item.text() for item in view.context_menu_actions(BUILD, build_handle)]
    assert "Run step" in build_labels


def test_build_and_publish_button_is_wired(qapp):
    session = Session()
    session.add("mark", "kine")
    session.publish.add("export", "fbx")
    view = SessionView(session)

    assert view.publish_button.isEnabled()
    CALLS.clear()
    view.publish_button.click()
    assert [item[1] for item in CALLS if item[0] == "mark"] == ["kine", "fbx"]


def test_statuses_are_routed_to_the_right_tree(qapp):
    from tik.trigger.core.document import BUILD, PUBLISH
    from tik.trigger.ui.model import StatusRole

    session = Session()
    session.add("mark", "kine")
    session.publish.add("export", "fbx")
    view = SessionView(session)
    view.build_and_publish()

    assert view.models[BUILD].data(view.model.index(0, 0), StatusRole) == "done"
    assert view.models[PUBLISH].data(view.publish_model.index(0, 0), StatusRole) == "done"
    view.clear_statuses()
    assert view.models[PUBLISH].data(view.publish_model.index(0, 0), StatusRole) == ""
```

> `SessionView` runs `session.build(...)` for real in these tests. The UI suite
> runs with `TIK_TESTS_NO_MAYA=1`, and `tests/ui/conftest.py` already stubs
> `Session.guides`; `Runner.new_scene()` imports `tik.trigger.guides.nodes`
> lazily. If that import fails without Maya, monkeypatch
> `tik.trigger.maya.runner.new_scene` and `tik.trigger.maya.runner.undo_chunk`
> in these two tests the way the file's existing build tests do — check how
> `test_pipeline_ui.py`'s current build test handles it and copy that.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_pipeline_ui.py -q`
Expected: FAIL — `AttributeError: 'SessionView' object has no attribute 'trees'`.

- [ ] **Step 3: Hide the run buttons for publish rows**

In `ui/settings_panel.py`, add the import and set visibility in `set_handle`:

```python
from tik.trigger.core.document import BUILD
```

In `set_handle`, right after `enabled = handle is not None`:

```python
        # Publish actions never run on their own: the only way one executes is
        # as the tail of a full clean build.
        runnable = enabled and getattr(handle, "phase", BUILD) == BUILD
        self.run_button.setVisible(runnable)
        self.until_button.setVisible(runnable)
```

- [ ] **Step 4: Build the split pipeline pane**

In `ui/session_view.py`, update the imports and the entry helpers:

```python
from tik.trigger.core.document import BUILD, PHASES, PUBLISH
```

```python
def action_entries(scope: str = BUILD) -> list[PaletteEntry]:
    return [
        PaletteEntry(cls.action_type, cls.display_label(), getattr(cls, "category", "utility"), [cls.description()[:40]])
        for cls in registry.iter_actions(scope=scope)
    ]


def tile_entries(scope: str = BUILD) -> list[TileEntry]:
    return [
        TileEntry(cls.action_type, cls.display_label(), getattr(cls, "category", "utility"), cls.description()[:80])
        for cls in registry.iter_actions(scope=scope)
    ]
```

In `SessionView.__init__`, replace the model line:

```python
        self.model = PipelineModel(session, self, phase=BUILD)
        self.publish_model = PipelineModel(session, self, phase=PUBLISH)
        self.models = {BUILD: self.model, PUBLISH: self.publish_model}
        self._focus_phase = BUILD
```

In `_build_ui`, replace the shelf construction with a stack of two grids:

```python
        self.shelves = {
            BUILD: TileGrid(tile_entries(BUILD), MIME_TYPE),
            PUBLISH: TileGrid(tile_entries(PUBLISH), MIME_TYPE),
        }
        self.shelf_stack = QtWidgets.QStackedWidget()
        for phase in PHASES:
            self.shelves[phase].activated.connect(lambda key: self.add_action(key, as_child=False))
            self.shelf_stack.addWidget(self.shelves[phase])
        self.shelf = self.shelves[BUILD]  # kept: menus and tests reach for it
        self.shelf_pane = pane("Actions", self.shelf_stack)
        self.splitter.addWidget(self.shelf_pane)
```

Replace the single-tree block with a factory and a vertical splitter:

```python
        self.tree = self._make_tree(self.model)
        self.publish_tree = self._make_tree(self.publish_model)
        self.trees = {BUILD: self.tree, PUBLISH: self.publish_tree}

        self.pipeline_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.pipeline_splitter.setHandleWidth(6)
        self.pipeline_splitter.addWidget(pane("Build", self.tree))
        self.pipeline_splitter.addWidget(pane("Publish", self.publish_tree))
        self.pipeline_splitter.setStretchFactor(0, 3)
        self.pipeline_splitter.setStretchFactor(1, 1)
        self.pipeline_splitter.setCollapsible(0, False)
        self.pipeline_splitter.setCollapsible(1, True)
        self.pipeline_splitter.setSizes([360, 120])
        self.splitter.addWidget(self.pipeline_splitter)
```

Add the factory next to `_build_ui`:

```python
    def _make_tree(self, model: PipelineModel) -> PipelineTree:
        tree = PipelineTree()
        tree.setObjectName("PipelineTree")
        tree.setModel(model)
        tree.setItemDelegate(PipelineDelegate(tree))
        tree.setHeaderHidden(True)
        tree.setIndentation(18)
        tree.setMouseTracking(True)
        tree.setDragEnabled(True)
        tree.setAcceptDrops(True)
        tree.setDropIndicatorShown(True)
        tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop)
        tree.setDefaultDropAction(QtCore.Qt.MoveAction)
        tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        tree.setEditTriggers(
            QtWidgets.QAbstractItemView.EditKeyPressed | QtWidgets.QAbstractItemView.SelectedClicked
        )
        tree.setUniformRowHeights(True)
        tree.expandAll()
        tree.installEventFilter(self)
        return tree
```

- [ ] **Step 5: Wire both trees, focus tracking and the publish button**

Replace the signal-connection block at the end of `_build_ui`:

```python
        self.palette = SearchPalette(action_entries(BUILD), self)
        self.palette.chosen.connect(self.add_action)

        for phase in PHASES:
            tree = self.trees[phase]
            model = self.models[phase]
            tree.selectionModel().currentChanged.connect(
                lambda current, _previous, phase=phase: self._on_current_changed(phase, current)
            )
            tree.customContextMenuRequested.connect(
                lambda point, phase=phase: self._context_menu(phase, point)
            )
            tree.doubleClicked.connect(
                lambda index, phase=phase: self._on_double_clicked(phase, index)
            )
            tree.palette_requested.connect(self.show_palette)
            model.edited.connect(self._after_edit)
            model.cross_phase_moved.connect(self._rebuild_all)

        self.settings.edited.connect(self._on_settings_edited)
        self.settings.run_requested.connect(self.run_step)
        self.settings.run_until_requested.connect(self.build_until)
        self.settings.save_requested.connect(self.save_from_scene)
        self.settings.open_file_requested.connect(lambda path, _ext: self.open_guides_requested.emit(path))
        self.build_button.clicked.connect(self.build)
        self.until_button.clicked.connect(lambda: self.build_until(self.current_path()))
        self.publish_button.clicked.connect(self.build_and_publish)

        QtWidgets.QShortcut(QtGui.QKeySequence("Delete"), self.tree, self.remove_current)
        QtWidgets.QShortcut(QtGui.QKeySequence("Delete"), self.publish_tree, self.remove_current)
        QtWidgets.QShortcut(QtGui.QKeySequence("F5"), self, self.refresh)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+D"), self.tree, self.duplicate_current)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+D"), self.publish_tree, self.duplicate_current)
```

and the build bar's publish button:

```python
        self.publish_button = QtWidgets.QPushButton("Build && Publish")
        self.publish_button.setToolTip("Build the rig from scratch, then run the publish actions")
```

(delete the `setEnabled(False)` line).

Add the focus machinery and the phase-aware helpers:

```python
    # ------------------------------------------------------------- focus
    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() == QtCore.QEvent.FocusIn:
            for phase, tree in self.trees.items():
                if watched is tree:
                    self.set_focus_phase(phase)
                    break
        return super().eventFilter(watched, event)

    @property
    def focus_phase(self) -> str:
        return self._focus_phase

    @property
    def current_phase(self) -> str:
        return self._focus_phase

    def set_focus_phase(self, phase: str) -> None:
        """Point the shelf, the palette, the properties panel and the build bar
        at one of the two lists."""
        if phase not in PHASES:
            return
        self._focus_phase = phase
        self.shelf_stack.setCurrentWidget(self.shelves[phase])
        self.shelf = self.shelves[phase]
        self.palette.entries = action_entries(phase)
        self.palette.refilter()
        # ``until`` is a build-list debugging tool: a partial build must not publish
        self.until_button.setEnabled(phase == BUILD)
        self.settings.set_handle(self.current_handle())

    @property
    def current_model(self) -> PipelineModel:
        return self.models[self._focus_phase]

    @property
    def current_tree(self) -> PipelineTree:
        return self.trees[self._focus_phase]

    def current_handle(self) -> Optional[ActionHandle]:
        return self.current_model.handle(self.current_tree.currentIndex())

    def current_path(self) -> Optional[str]:
        handle = self.current_handle()
        return handle.path if handle else None

    def _on_current_changed(self, phase: str, current) -> None:
        self.set_focus_phase(phase)
        self.settings.set_handle(self.models[phase].handle(current))

    def _on_double_clicked(self, phase: str, index) -> None:
        # publish actions are never individually runnable
        if phase != BUILD:
            return
        handle = self.models[phase].handle(index)
        if handle is not None:
            self.run_step(handle.path)

    def _rebuild_all(self) -> None:
        for tree_phase in PHASES:
            self.models[tree_phase].rebuild()
            self.trees[tree_phase].expandAll()
```

- [ ] **Step 6: Make the remaining view methods phase-aware**

Replace `select_path`, `refresh`, `add_action`, the edit verbs, the context menu
and the run/status methods:

```python
    def select_path(self, path: Optional[str], phase: Optional[str] = None) -> None:
        if not path:
            return
        phase = phase or self._focus_phase
        index = self.models[phase].index_for_path(path)
        if index.isValid():
            self.trees[phase].setCurrentIndex(index)
            self.trees[phase].scrollTo(index)

    def refresh(self, keep: Optional[str] = None) -> None:
        keep = keep or self.current_path()
        phase = self._focus_phase
        self._rebuild_all()
        self.select_path(keep, phase)
        self.settings.set_handle(self.current_handle())
        self.title_changed.emit()

    def _after_edit(self) -> None:
        for tree in self.trees.values():
            tree.expandAll()
        self.title_changed.emit()

    def _on_settings_edited(self, path: str) -> None:
        phase = self._focus_phase
        handle = self.models[phase].handle(self.trees[phase].currentIndex())
        # a reference gained/changed its file: its children changed too
        if handle is not None and handle.type == "reference":
            self.refresh(path)
        else:
            index = self.models[phase].index_for_path(path)
            self.models[phase].dataChanged.emit(index, index)
            self.title_changed.emit()

    def add_action(self, action_type: str, as_child: bool = False) -> Optional[ActionHandle]:
        phase = self._focus_phase
        view = self.session.view(phase)
        current = self.current_handle()
        try:
            if current is None:
                handle = view.add(action_type)
            elif as_child:
                if current.is_linked:
                    raise SessionError("Cannot add inside a referenced session.")
                handle = view.add(action_type, parent=current.path)
            else:
                target = current
                while target.is_linked:
                    target = view[target.path.rsplit("/", 1)[0]]
                handle = view.add(action_type, after=target.path)
        except TriggerError as error:
            self.session.events.log(str(error), level="warning")
            return None
        self.refresh(handle.path)
        return handle

    def remove_current(self) -> None:
        handle = self.current_handle()
        if handle is None or handle.is_linked:
            return
        self.session.view(self._focus_phase).remove(handle.path)
        self.refresh(None)

    def duplicate_current(self) -> None:
        handle = self.current_handle()
        if handle is None or handle.is_linked:
            return
        self.refresh(self.session.view(self._focus_phase).duplicate(handle.path).path)

    def rename_current(self) -> None:
        tree = self.current_tree
        index = tree.currentIndex()
        if index.isValid() and not self.current_model.handle(index).is_linked:
            tree.edit(index)

    def toggle_current(self) -> None:
        index = self.current_tree.currentIndex()
        if index.isValid():
            self.current_model.toggle(index)

    def context_menu_actions(self, phase: str, handle: Optional[ActionHandle]) -> list:
        """The menu entries for one row. Split out so tests can read them."""
        menu = QtWidgets.QMenu(self)
        if handle is not None:
            # publish actions are never individually runnable
            if phase == BUILD:
                menu.addAction("Run step", lambda: self.run_step(handle.path))
                menu.addAction("Build until here", lambda: self.build_until(handle.path))
                menu.addSeparator()
            menu.addAction("Disable" if handle.enabled else "Enable", self.toggle_current)
            if not handle.is_linked:
                menu.addAction("Rename", self.rename_current)
                menu.addAction("Duplicate", self.duplicate_current)
                menu.addAction("Delete", self.remove_current)
            menu.addSeparator()
        menu.addAction("Add action…  (Tab)", self.show_palette)
        child = menu.addAction("Add child action…", self.add_child_via_palette)
        child.setEnabled(handle is not None and not handle.is_linked)
        self._menu = menu  # keep it alive for the caller
        return menu.actions()

    def _context_menu(self, phase: str, point) -> None:
        tree = self.trees[phase]
        index = tree.indexAt(point)
        handle = self.models[phase].handle(index)
        if handle is not None:
            tree.setCurrentIndex(index)
        self.set_focus_phase(phase)
        self.context_menu_actions(phase, handle)
        self._menu.exec_(tree.viewport().mapToGlobal(point))

    def show_palette(self) -> None:
        tree = self.current_tree
        anchor = tree.visualRect(tree.currentIndex()) if tree.currentIndex().isValid() else tree.rect()
        point = tree.viewport().mapToGlobal(anchor.bottomLeft() + QtCore.QPoint(20, 4))
        self.palette.popup(point)

    # ------------------------------------------------------------ running
    def _step(self, path: str, status: str, error: str = "", phase: str = BUILD) -> None:
        self.models.get(phase, self.model).set_status(path, status, error)
        self.activity.emit(f"{status}: {path}" + (f" — {error}" if error else ""))
        QtWidgets.QApplication.processEvents()

    def _run(self, callback) -> bool:
        if self._running:
            return False
        self._running = True
        for model in self.models.values():
            model.clear_status()
        self.build_button.setEnabled(False)
        self.publish_button.setEnabled(False)
        try:
            callback()
            return True
        except (ActionExecutionError, TriggerError) as error:
            self.session.events.log(str(error), level="error")
            return False
        finally:
            self._running = False
            self.build_button.setEnabled(True)
            self.publish_button.setEnabled(True)

    def build(self) -> bool:
        return self._run(lambda: self.session.build())

    def build_and_publish(self) -> bool:
        return self._run(lambda: self.session.build(publish=True))

    def build_until(self, path: Optional[str]) -> bool:
        return bool(path) and self._run(lambda: self.session.build(until=path))

    def run_step(self, path: Optional[str]) -> bool:
        return bool(path) and self._run(lambda: self.session.run(path))

    def clear_statuses(self) -> None:
        for model in self.models.values():
            model.clear_status()
        self.progress.setValue(0)
        self.counter.setText("")
```

Update `_connect_events` so the status lambdas forward the phase:

```python
        events.subscribe(STEP_STARTED, lambda path="", phase=BUILD, **_kw: self._step(path, "running", phase=phase))
        events.subscribe(STEP_FINISHED, lambda path="", phase=BUILD, **_kw: self._step(path, "done", phase=phase))
        events.subscribe(STEP_FAILED, lambda path="", error="", phase=BUILD, **_kw: self._step(path, "failed", error, phase))
```

`shelf_visible` / `set_shelf_visible` keep working — they act on
`self.splitter` index 0, which is now the shelf stack's pane.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_pipeline_ui.py -q`
Expected: PASS.

- [ ] **Step 8: Run the whole UI suite**

Run: `make tests-ui`
Expected: PASS. `test_session_subtabs.py`, `test_menus.py` and
`test_designer_per_session.py` all construct a `SessionView`; fix any that
reach for `view.tree`-only assumptions by pointing them at the right tree.

- [ ] **Step 9: Commit**

```bash
git add src/python/tik/trigger/ui/session_view.py src/python/tik/trigger/ui/settings_panel.py tests/ui/test_pipeline_ui.py
git commit -m "feat(trigger-ui): split the pipeline pane into build and publish trees"
```

---

### Task 7: Menu entry and project docs

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py:160-165`
- Modify: `CLAUDE.md`
- Test: `tests/ui/test_menus.py`

**Interfaces:**
- Consumes: `SessionView.build_and_publish()` (Task 6).
- Produces: a **Build & Publish** entry in the Session menu with shortcut `Ctrl+Shift+P`.

- [ ] **Step 1: Write the failing test**

Add to `tests/ui/test_menus.py`:

```python
def test_session_menu_has_build_and_publish(qapp):
    from tik.trigger.ui.main import TriggerWindow

    window = TriggerWindow()
    session_menu = window._menus["&Session"]
    entries = {item.text(): item for item in session_menu.actions()}
    assert "Build & Publish" in entries
    assert entries["Build & Publish"].shortcut().toString() == "Ctrl+Shift+P"
```

> Match this file's existing style for constructing the window — if the other
> tests there use a fixture rather than `TriggerWindow()` directly, use it.

- [ ] **Step 2: Run the test to verify it fails**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_menus.py -q`
Expected: FAIL — `AssertionError: 'Build & Publish' not in {...}`.

- [ ] **Step 3: Add the menu entry**

In `ui/main.py`, in `_build_menus`, insert after the "Build Rig" line:

```python
        self._action(session_menu, "Build Rig", lambda: self._view_call("build"), "Ctrl+B")
        self._action(session_menu, "Build & Publish", lambda: self._view_call("build_and_publish"), "Ctrl+Shift+P")
        self._action(session_menu, "Build Until Here", lambda: self._view_call("build_until", self._current_path()), "Ctrl+Shift+B")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_menus.py -q`
Expected: PASS.

- [ ] **Step 5: Update `CLAUDE.md`**

Three edits in the tik.trigger section:

1. In the **Status** paragraph, after "…and actions `import_asset`/`kinematics`/`script`/`reference`.", add:
   > The pipeline is split in two: a **build** list and a **publish** list. `Build` runs the first; `Build & Publish` runs both in one continuous run with a single scene reset. Publish actions are never individually runnable, and a `reference` contributes build actions only.
2. In **Design specs**, add at the front of the list:
   `docs/superpowers/specs/2026-09-03-build-publish-split-design.md` (the build/publish split — the second action list, action `scope`, and the run semantics)
3. In **Key decisions**, replace the "One session document" bullet:
   > - **One session document** (`.tr`, schema 6): guides + two ordered action lists (`actions` is the build list, `publish` the post-build one). The scene is a checkout of exactly one session at a time, stamped on the guide holder (`Session.capture_guides` / `checkout_guides`)

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/ui/main.py CLAUDE.md tests/ui/test_menus.py
git commit -m "feat(trigger-ui): Build & Publish menu entry; document the split"
```

---

### Task 8: End-to-end build and publish against Maya

**Files:**
- Create: `tests/integration/trigger/test_publish_phase_trigger.py`

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: no source changes — this is the integration proof.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/trigger/test_publish_phase_trigger.py`:

```python
"""Build & Publish end to end: order, one reset, and no publish without it."""

import pytest
from maya import cmds

import tik.trigger as trigger


MARK = "import maya.cmds as cmds\ncmds.createNode('transform', name='{name}')"


def _session(tmp_path):
    rig = trigger.Session()
    rig.save(tmp_path / "hero.tr")
    rig.add("script", "build_a", code=MARK.format(name="build_a"))
    rig.add("script", "build_b", code=MARK.format(name="build_b"))
    rig.publish.add("script", "export_fbx", code=MARK.format(name="export_fbx"))
    rig.publish.add("script", "export_maya", code=MARK.format(name="export_maya"))
    rig.save()
    return rig


def test_build_alone_leaves_the_publish_list_untouched(tmp_path):
    rig = _session(tmp_path)
    results = rig.build()
    assert [item.path for item in results] == ["build_a", "build_b"]
    assert cmds.objExists("build_a") and cmds.objExists("build_b")
    assert not cmds.objExists("export_fbx")


def test_build_and_publish_runs_both_in_order_with_one_reset(tmp_path):
    from tik.trigger.core.document import BUILD, PUBLISH

    rig = _session(tmp_path)
    results = rig.build(publish=True)
    assert [item.path for item in results] == ["build_a", "build_b", "export_fbx", "export_maya"]
    assert [item.phase for item in results] == [BUILD, BUILD, PUBLISH, PUBLISH]
    # one reset only: the build's nodes are still there when publish runs
    assert cmds.objExists("build_a") and cmds.objExists("export_maya")
    assert len(cmds.ls("build_a")) == 1


def test_a_publish_action_cannot_be_run_on_its_own(tmp_path):
    from tik.trigger.core.exceptions import SessionError

    rig = _session(tmp_path)
    with pytest.raises(SessionError):
        rig.run("export_fbx")
    with pytest.raises(SessionError):
        rig.build(until="build_a", publish=True)


def test_a_reference_contributes_build_actions_only(tmp_path):
    base = trigger.Session()
    base.add("script", "base_build", code=MARK.format(name="base_build"))
    base.publish.add("script", "base_publish", code=MARK.format(name="base_publish"))
    base.save(tmp_path / "base.tr")

    hero = trigger.Session()
    hero.save(tmp_path / "hero_ref.tr")
    hero.add("reference", "base", file="base.tr")
    hero.publish.add("script", "hero_publish", code=MARK.format(name="hero_publish"))
    hero.save()

    hero.build(publish=True)
    assert cmds.objExists("base_build")
    assert cmds.objExists("hero_publish")
    assert not cmds.objExists("base_publish")


def test_the_publish_list_survives_a_save_and_reopen(tmp_path):
    _session(tmp_path)
    reopened = trigger.Session.open(str(tmp_path / "hero.tr"))
    assert reopened.paths() == ["build_a", "build_b"]
    assert reopened.publish.paths() == ["export_fbx", "export_maya"]
    reopened.build(publish=True)
    assert cmds.objExists("export_maya")
```

> **Note for the implementer:** confirm the `script` action's field is named
> `code` (`tests/integration/trigger/test_session_build_trigger.py` uses
> `rig.add("script", "tag", code=...)`). If the reference action's file field
> is not `file`, match `actions/reference/reference.py`.

- [ ] **Step 2: Run the test to verify it passes**

Run: `set PYTHONPATH=D:/dev/tikworks/src/python;%PYTHONPATH% && mayapy -m pytest tests/integration/trigger/test_publish_phase_trigger.py -q`
Expected: PASS. (This test is written last, so it should pass immediately — if
it fails, that is a real defect in Tasks 1-4, not a missing implementation.)

- [ ] **Step 3: Run the full suite**

Run: `make tests` then `make tests-ui`
Expected: PASS, both.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/trigger/test_publish_phase_trigger.py
git commit -m "test(trigger): end-to-end build and publish against a real scene"
```

---

## Verification checklist

Before calling the work done, confirm with actual command output:

- [ ] `make tests-unit` passes
- [ ] `make tests-integration` passes
- [ ] `make tests-ui` passes
- [ ] `tests/unit/test_import_boundaries.py` passes (core stayed pure)
- [ ] An existing schema-5 `.tr` (`tests/data/crabMonster_main_session_v002.tr`) still opens and builds
