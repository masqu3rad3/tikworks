# Kinematics Explicit Scope — Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a `kinematics` action build only the modules it explicitly names, and make a rig built by several kinematics actions connect correctly across those passes.

**Architecture:** `kinematics.guide_roots` (names, empty = all) and `kinematics.guides_file` (build-time `.trg` import) are replaced by `modules` — a list of instance uuids, empty is an error. Draw, clear and afterlife all become scoped to that list, so a second pass cannot erase the first pass's work. `Builder` gains a scene-tag fallback so a module can attach to an output an earlier pass already produced, and raises on a duplicate display key instead of silently overwriting. `Session.validate()` gains the cross-step checks that explicit scope makes possible, and two of them also run at build time.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), pytest. No third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-09-06-module-referencing-design.md` — this plan implements §5, §6, §9 and the §11 deletions. §3, §4, §7 (the `ModuleReference` itself and its views) are Phase 2 and are **out of scope here**.

## Global Constraints

- **No third-party deps.** Stdlib and Maya-bundled modules only.
- **Consume tik.maya.** No raw `maya.cmds` / `OpenMaya` / `pymel` in tool code. The exception, already established in this codebase: `tik/trigger/guides/nodes.py` uses `cmds.ls` directly for whole-scene attribute-qualified scans, and Task 3 extends that existing pattern in that same file.
- **`tik/trigger/core` stays pure** — no Maya, no Qt, no preferences. Enforced by `tests/unit/test_import_boundaries.py`.
- **One dialog surface.** Any user dialog goes through `tik.shared.ui.feedback.Feedback`. This plan adds none.
- **Line length 88** (black, `line-length = 88`), isort profile `black`, flake8 clean.
- **Docstrings on every public function**, imperative mood, matching the surrounding style.
- **Python version floor:** `requires-python = "> 3.10"`.

## Running tests

Baseline at the time of writing: **1398 unit tests pass in ~29s**.

```bash
# from the repo root, all commands use Maya's interpreter
MAYAPY="/c/Program Files/Autodesk/Maya2026/bin/mayapy"
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "$MAYAPY" -m pytest tests/unit -q
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "$MAYAPY" -m pytest tests/integration -q
```

A single test:

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "$MAYAPY" -m pytest tests/unit/test_kinematics_scope_trigger.py::test_empty_modules_raises -q
```

`make tests-unit` / `make tests-integration` do the same when `mayapy` is on PATH.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/python/tik/trigger/actions/kinematics/kinematics.py` | **Rewritten.** The action: a uuid list, scoped draw, scoped afterlife. Loses `guides_file`, `guide_roots`, `_descendants`, `_checkout_session_guides`. | 1 |
| `src/python/tik/trigger/core/document.py` | `SCHEMA_VERSION` 6 → 7 and the document-level migration pass, which needs the guide document the per-action hook cannot see. | 2 |
| `src/python/tik/trigger/core/kinematics_migration.py` | **New.** Pure translation of legacy `guide_roots` names into uuids. Separate file so `document.py` does not grow a second responsibility, and so the tricky name-matching rules are testable on their own. | 2 |
| `src/python/tik/trigger/guides/nodes.py` | **New function** `find_output(instance_id, output_name)` — the scene-tag lookup for an output built in an earlier pass. | 3 |
| `src/python/tik/trigger/maya/build.py` | `Builder.resolve` and `_bind_parent_for` gain the cross-pass fallback; `known_keys` comes from the document; duplicate display keys raise. | 3, 4 |
| `src/python/tik/trigger/session.py` | The `validate()` checks, and running the cross-step ones before a build. | 5 |
| `tests/unit/test_kinematics_scope_trigger.py` | **New.** The action's contract and the migration. | 1, 2 |
| `tests/unit/test_session_trigger.py` | Extended with the validation checks. | 5 |
| `tests/integration/trigger/test_multipass_build_trigger.py` | **New.** Two real passes in a real scene. | 3, 4 |

---

### Task 1: `kinematics` builds exactly what it names

Replaces the action's three settings with one, and scopes every scene effect to it.

**Files:**
- Modify: `src/python/tik/trigger/actions/kinematics/kinematics.py` (whole file)
- Test: `tests/unit/test_kinematics_scope_trigger.py` (create)

**Interfaces:**
- Consumes: `GuideScene.draw(scope=None, poses="keep")` and `GuideScene.clear_rendering()` from `tik/trigger/guides/scene.py`; `Builder(events).build(scope, document, afterlife)` from `tik/trigger/maya/build.py`; `ActionExecutionError` from `tik/trigger/core/exceptions.py`.
- Produces: `Kinematics.modules` — a `ListField(item_type=str)` of instance uuids. `Kinematics.validate(ctx)` returning `list[str]`. Task 2 writes into `settings["modules"]`; Task 5 reads it to find every built uuid.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_kinematics_scope_trigger.py`:

```python
"""The kinematics action builds exactly the modules it names."""

import pytest

from tik.trigger.core import clear_registries, register_module
from tik.trigger.core.exceptions import ActionExecutionError
from tik.trigger.core.guide_document import GuideDocument, ModuleEntry
from tik.trigger.session import Session

from toy_modules import ToyChain, ToyRoot


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


def _session_with(*entries) -> Session:
    """A session whose guide document holds ``entries``."""
    session = Session()
    session.document.guides = GuideDocument(modules=list(entries))
    return session


def _entry(instance_id, module_type="toy_root", name="thing", side="C"):
    return ModuleEntry(
        instance_id=instance_id, module_type=module_type, name=name, side=side
    )


def test_empty_modules_raises():
    """An empty list is an error, never 'build everything'."""
    session = _session_with(_entry("aaa"))
    handle = session.add("kinematics")
    with pytest.raises(ActionExecutionError, match="names no modules"):
        session.run(handle.path)


def test_unknown_uuid_is_a_validation_problem():
    session = _session_with(_entry("aaa"))
    handle = session.add("kinematics", modules=["nope"])
    problems = session.validate()
    assert any("nope" in item for item in problems)


def test_modules_field_stores_uuids():
    session = _session_with(_entry("aaa"), _entry("bbb", name="other"))
    handle = session.add("kinematics", modules=["aaa", "bbb"])
    assert handle.modules == ["aaa", "bbb"]


def test_guides_file_and_guide_roots_are_gone():
    """The two implicit-scope settings no longer exist."""
    from tik.trigger.core import registry

    fields = registry.get_action("kinematics").fields()
    assert "guides_file" not in fields
    assert "guide_roots" not in fields
    assert "modules" in fields
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_kinematics_scope_trigger.py -q
```

Expected: FAIL. `test_guides_file_and_guide_roots_are_gone` fails because both fields still exist; `test_empty_modules_raises` fails because there is no `modules` field.

- [ ] **Step 3: Rewrite the action**

Replace the whole of `src/python/tik/trigger/actions/kinematics/kinematics.py`:

```python
"""Build the modules this action names. Nothing implicit, nothing else."""

from __future__ import annotations

from tik.trigger.core import (
    AFTERLIFE_MODES,
    Action,
    ChoiceField,
    FieldGroup,
    ListField,
    register_action,
)
from tik.trigger.core.exceptions import ActionExecutionError

BUILD_OPTIONS = FieldGroup("Build Options", collapsed=True)


@register_action("kinematics", category="build", icon="kinematics")
class Kinematics(Action):
    """Build the listed modules into the scene's one rig.

    The list is the whole scope: it does not matter whether a module is local
    to this session, referenced from another, or was imported from a guide
    library. If it is named here, it builds; if it is not, this action does
    not touch it -- not its guides, and not its afterlife.
    """

    label = "Kinematics"

    modules = ListField(
        item_type=str,
        label="Modules",
        help="Instance ids of the modules to build. Never empty.",
    )
    after_build = ChoiceField(
        "delete",
        choices=list(AFTERLIFE_MODES),
        label="GuideLayout after build",
        group=BUILD_OPTIONS,
    )

    def validate(self, ctx) -> list:
        """Report an empty list, and any id this session does not hold."""
        if not self.modules:
            problems = ["kinematics names no modules; nothing would build."]
            return problems
        document = self._document(ctx)
        if document is None:
            return []
        known = {entry.instance_id for entry in document.modules}
        return [
            f"kinematics names a module that is not in this session: '{item}'."
            for item in self.modules
            if item not in known
        ]

    def run(self, ctx) -> None:
        """Draw this action's modules, build them, then apply the afterlife."""
        from tik.trigger.guides import GuideScene
        from tik.trigger.maya.build import Builder

        if not self.modules:
            raise ActionExecutionError("kinematics names no modules; nothing to build.")
        document = self._document(ctx)
        if document is None:
            raise ActionExecutionError("kinematics has no session to build from.")
        scope = list(self.modules)
        known = {entry.instance_id for entry in document.modules}
        missing = [item for item in scope if item not in known]
        if missing:
            raise ActionExecutionError(
                f"kinematics names module(s) not in this session: {missing}."
            )
        guides = GuideScene(ctx.events, session=ctx.session)
        # Scoped, and only scoped: an earlier pass's guides are none of our
        # business, whatever its afterlife was.
        guides.draw(scope=scope)
        report = Builder(ctx.events).build(
            scope=scope, document=document, afterlife=self.after_build
        )
        ctx.log(f"Kinematics built {report.count} module(s).")

    @staticmethod
    def _document(ctx):
        """The guide document of the session being built, or None."""
        session = getattr(ctx, "session", None)
        document = getattr(session, "document", None)
        return getattr(document, "guides", None)

    def summary(self) -> str:
        """How many modules this action builds, for the pipeline list."""
        count = len(self.modules)
        return f"{count} module{'' if count == 1 else 's'}"
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_kinematics_scope_trigger.py -q
```

Expected: PASS (4 tests).

- [ ] **Step 5: Run the whole unit suite and fix the fallout**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit -q
```

Expected: failures in tests that add a `kinematics` action without `modules`, and in any test setting `guides_file` / `guide_roots`. Grep for them first:

```bash
grep -rn "guides_file\|guide_roots\|\"kinematics\"\|'kinematics'" tests/ --include=*.py
```

Update each to pass explicit uuids. Do **not** reintroduce a default-to-all shortcut to keep an old test passing — that is the behaviour this task removes.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/actions/kinematics/kinematics.py tests/
git commit -m "Make kinematics build only the modules it names

An empty list is an error rather than 'build everything', and draw and
afterlife are scoped to the list, so a second pass cannot erase or
re-consume the first pass's work.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015xVfPaN3fdKbLNYdVWYS5n"
```

---

### Task 2: Migrate existing `.tr` files

Old sessions must keep building exactly as they do today. The per-action `migrate_settings` hook cannot see the guide document, so this runs at document level, gated on the stored schema.

**Files:**
- Create: `src/python/tik/trigger/core/kinematics_migration.py`
- Modify: `src/python/tik/trigger/core/document.py` (`SCHEMA_VERSION`, `Document.from_dict`)
- Test: `tests/unit/test_kinematics_scope_trigger.py` (extend)

**Interfaces:**
- Consumes: `GuideDocument.modules` (each `ModuleEntry` has `.instance_id`, `.name`, `.side`, `.key`, `.inputs`), `ModuleEntry` from `tik/trigger/core/guide_document.py`.
- Produces: `migrate_kinematics(actions, guides) -> None`, mutating `ActionNode.settings` in place. Sets `settings["modules"]` and, for anything unresolvable, `settings["legacy_roots"]`; removes `guide_roots`. Task 5 reads `legacy_roots` and `guides_file` to report them.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_kinematics_scope_trigger.py`:

```python
def _legacy_document(roots, entries, guides_file=""):
    """A schema-6 .tr dict with one kinematics action."""
    settings = {"guide_roots": list(roots), "after_build": "delete"}
    if guides_file:
        settings["guides_file"] = guides_file
    return {
        "schema": 6,
        "meta": {},
        "actions": [
            {
                "name": "kinematics",
                "type": "kinematics",
                "enabled": True,
                "settings": settings,
                "children": [],
            }
        ],
        "publish": [],
        "guides": {"schema": 1, "modules": [entry.to_dict() for entry in entries]},
    }


def test_empty_roots_migrates_to_every_module():
    """The old 'empty means all' keeps building the same rig."""
    from tik.trigger.core.document import Document

    entries = [_entry("aaa", name="spine"), _entry("bbb", name="arm", side="L")]
    document = Document.from_dict(_legacy_document([], entries))
    assert document.actions[0].settings["modules"] == ["aaa", "bbb"]
    assert "guide_roots" not in document.actions[0].settings


def test_named_root_matches_every_side():
    """'arm' selected L_arm and R_arm alike, and still does."""
    from tik.trigger.core.document import Document

    entries = [
        _entry("aaa", name="spine"),
        _entry("bbb", name="arm", side="L"),
        _entry("ccc", name="arm", side="R"),
    ]
    document = Document.from_dict(_legacy_document(["arm"], entries))
    assert sorted(document.actions[0].settings["modules"]) == ["bbb", "ccc"]


def test_named_root_pulls_its_subtree():
    """The old semantics included everything parented under the root."""
    from tik.trigger.core.document import Document

    spine = _entry("aaa", name="spine")
    arm = _entry("bbb", "toy_chain", name="arm", side="L")
    arm.inputs = {"root": "aaa.root"}
    document = Document.from_dict(_legacy_document(["spine"], [spine, arm]))
    assert sorted(document.actions[0].settings["modules"]) == ["aaa", "bbb"]


def test_unresolvable_root_is_kept_not_dropped():
    """A root joint name cannot be resolved headlessly; it must not vanish."""
    from tik.trigger.core.document import Document

    document = Document.from_dict(
        _legacy_document(["base_c"], [])  # no modules at all
    )
    settings = document.actions[0].settings
    assert settings["modules"] == []
    assert settings["legacy_roots"] == ["base_c"]


def test_migration_does_not_rerun_on_current_schema():
    """undo/redo/copy round-trip through from_dict and must not re-migrate."""
    from tik.trigger.core.document import Document

    entries = [_entry("aaa", name="spine")]
    document = Document.from_dict(_legacy_document([], entries))
    document.actions[0].settings["modules"] = ["aaa"]
    again = Document.from_dict(document.to_dict())
    assert again.actions[0].settings["modules"] == ["aaa"]
    assert "legacy_roots" not in again.actions[0].settings
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_kinematics_scope_trigger.py -q
```

Expected: FAIL — `settings["modules"]` is absent; `guide_roots` is still there.

- [ ] **Step 3: Write the migration module**

Create `src/python/tik/trigger/core/kinematics_migration.py`:

```python
"""Translate a pre-schema-7 ``kinematics`` scope into explicit instance ids.

The old action took *root names* and pulled each root's whole subtree; the new
one takes exactly the instance ids it builds. Both approximations this module
makes are deliberate and reported rather than hidden:

* a name matched either a module's name (side-less, so ``"arm"`` selected both
  ``L_arm`` and ``R_arm``) **or** a root guide *joint* name such as
  ``L_arm_root_guide``. Only the first is resolvable without a Maya scene.
* the old subtree walk followed the scene DAG. The document has no DAG, so the
  walk here follows the primary input, which ``regenerate`` derives the DAG
  from -- identical unless somebody reparented guides without reconnecting.

Anything that does not resolve is preserved in ``legacy_roots`` for
``Session.validate`` to report. It is never silently dropped: a root that
quietly resolved to nothing would turn a session that builds today into one
that builds an empty rig.
"""

from __future__ import annotations

from typing import Iterable

from .schemas import split_source

KINEMATICS = "kinematics"


def _children_of(instance_id: str, entries: list) -> list:
    """Entries whose primary-ish input names ``instance_id``."""
    found = []
    for entry in entries:
        for source in entry.inputs.values():
            key, _output = split_source(source)
            if key == instance_id:
                found.append(entry)
                break
    return found


def _subtree(roots: Iterable, entries: list) -> list:
    """``roots`` plus everything reachable from them through inputs."""
    wanted = {entry.instance_id for entry in roots}
    changed = True
    while changed:
        changed = False
        for instance_id in list(wanted):
            for child in _children_of(instance_id, entries):
                if child.instance_id not in wanted:
                    wanted.add(child.instance_id)
                    changed = True
    return [entry.instance_id for entry in entries if entry.instance_id in wanted]


def resolve_roots(roots: list, entries: list) -> tuple:
    """Return ``(instance ids, unresolved root names)``.

    An empty ``roots`` means the old "build everything", so every module is
    returned.
    """
    if not roots:
        return [entry.instance_id for entry in entries], []
    resolved, unresolved = [], []
    for name in roots:
        matched = [
            entry for entry in entries if entry.name == name or entry.key == name
        ]
        if matched:
            resolved.extend(matched)
        else:
            unresolved.append(name)
    return _subtree(resolved, entries), unresolved


def migrate_kinematics(actions: list, guides) -> None:
    """Rewrite every ``kinematics`` node's scope in place. Depth first."""
    entries = list(getattr(guides, "modules", []))
    for node in actions:
        if node.type == KINEMATICS and "guide_roots" in node.settings:
            roots = list(node.settings.pop("guide_roots") or [])
            modules, unresolved = resolve_roots(roots, entries)
            node.settings["modules"] = modules
            if unresolved:
                node.settings["legacy_roots"] = unresolved
        migrate_kinematics(node.children, guides)
```

Note: `split_source` is already exported from `tik/trigger/core/schemas.py` and splits `"<id>.<output>"`, returning `(None, source)` for a bare scene node name.

- [ ] **Step 4: Wire it into `Document.from_dict`**

In `src/python/tik/trigger/core/document.py`, change `SCHEMA_VERSION` from `6` to `7`, then in `Document.from_dict` build the document first and run the migration before returning:

```python
        document = cls(
            schema=SCHEMA_VERSION,
            meta=dict(data.get("meta", {})),
            actions=[ActionNode.from_dict(item) for item in data.get("actions", [])],
            publish=[ActionNode.from_dict(item) for item in data.get("publish", [])],
            guides=GuideDocument.from_dict(data.get("guides") or {}),
        )
        if schema < 7:
            # The per-action hook cannot see the guides; this scope can only be
            # translated with them in hand. Gated on the *stored* schema, so
            # undo, redo and copy -- which all round-trip through here with the
            # schema already current -- never re-run it.
            from .kinematics_migration import migrate_kinematics

            migrate_kinematics(document.actions, document.guides)
            migrate_kinematics(document.publish, document.guides)
        return document
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_kinematics_scope_trigger.py tests/unit/test_document_trigger.py -q
```

Expected: PASS.

- [ ] **Step 6: Verify the real legacy session in test data migrates without crashing**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -c "
from tik.trigger.core.document import Document
d = Document.load('tests/data/crabMonster_main_session_v002.tr')
for path, node, _p in d.walk():
    if node.type == 'kinematics':
        print(path, node.settings.get('modules'), node.settings.get('legacy_roots'))
"
```

Expected: prints the action with `modules == []` and `legacy_roots == ['base_c']` — preserved, not silently emptied.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/core/kinematics_migration.py src/python/tik/trigger/core/document.py tests/unit/test_kinematics_scope_trigger.py
git commit -m "Migrate pre-schema-7 kinematics scopes to explicit ids

Empty guide_roots expands to every module, named roots expand through
their subtree, and anything unresolvable is preserved in legacy_roots for
validate() to report rather than silently dropped.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015xVfPaN3fdKbLNYdVWYS5n"
```

---

### Task 3: Attach to an output an earlier pass built

Today a source outside the current pass produces a warning and an unattached limb (`maya/build.py`, `_connect_one`). With several passes that is the normal case, so it has to resolve instead.

**Files:**
- Modify: `src/python/tik/trigger/guides/nodes.py` (add `find_output`)
- Modify: `src/python/tik/trigger/maya/build.py` (`Builder.resolve`, `_bind_parent_for`, `known_keys`)
- Test: `tests/integration/trigger/test_multipass_build_trigger.py` (create)

**Interfaces:**
- Consumes: `tags.INSTANCE` (`"trg_instance"`), `tags.OUTPUT_NAME` (`"trg_output"`) from `tik/trigger/maya/tags.py`; `tm.META_PREFIX` and `tm.resolve` from `tik.maya`.
- Produces: `guide_nodes.find_output(instance_id: str, output_name: str)` returning a `tm` node or `None`. `Builder.resolve` keeps its signature; it gains an internal `keys_to_ids` map built from the document.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/trigger/test_multipass_build_trigger.py`:

```python
"""Two kinematics passes build one rig, and the second attaches to the first."""

import pytest
from maya import cmds

from tik.trigger.core import clear_registries, register_module
from tik.trigger.core.guide_document import GuideDocument, ModuleEntry
from tik.trigger.session import Session

from toy_modules import ToyChain, ToyRoot


@pytest.fixture(autouse=True)
def _scene():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    cmds.file(new=True, force=True)
    yield
    clear_registries()


def _two_module_session() -> Session:
    """``root`` (a producer) and ``chain`` consuming its output."""
    root = ModuleEntry(
        instance_id="aaa", module_type="toy_root", name="body", side="C"
    )
    chain = ModuleEntry(
        instance_id="bbb", module_type="toy_chain", name="arm", side="L"
    )
    chain.inputs = {"root": "aaa.root"}
    session = Session()
    session.document.guides = GuideDocument(modules=[root, chain])
    return session


def test_second_pass_attaches_to_first_pass_output():
    session = _two_module_session()
    session.add("kinematics", name="pass_one", modules=["aaa"], after_build="delete")
    session.add("kinematics", name="pass_two", modules=["bbb"], after_build="delete")
    session.build()
    # the chain's socket is driven by the root module's output, across passes
    socket = "L_arm_root_socket_grp"
    assert cmds.objExists(socket), cmds.ls("*socket*")
    assert cmds.listConnections(socket, source=True, destination=False)


def test_first_pass_guides_survive_a_second_pass_with_keep():
    session = _two_module_session()
    session.add("kinematics", name="pass_one", modules=["aaa"], after_build="keep")
    session.add("kinematics", name="pass_two", modules=["bbb"], after_build="delete")
    session.build()
    remaining = [
        name
        for name in cmds.ls(type="joint", long=True) or []
        if "guide" in name.lower()
    ]
    assert remaining, "pass one asked to keep its guides; pass two deleted them"
```

The exact socket name comes from the `rig` object's naming; if it differs, read it from the build report instead of guessing — but keep the assertion on a *connection existing*, which is the behaviour under test.

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration/trigger/test_multipass_build_trigger.py -q
```

Expected: FAIL. `test_second_pass_attaches_to_first_pass_output` fails with the socket unconnected, and the log carries "outside the build scope; left unattached".

- [ ] **Step 3: Add the scene lookup**

In `src/python/tik/trigger/guides/nodes.py`, after `scene_node`:

```python
def find_output(instance_id: str, output_name: str):
    """The built node fulfilling ``instance_id``'s ``output_name``, or None.

    How a later build pass reaches a module an earlier one produced. It reads
    the output tag rather than the role tag on purpose: ``finalize`` writes
    ``trg_role`` on inputs as well as outputs, so one instance can carry the
    same role name twice.
    """
    pattern = f"*.{tm.META_PREFIX}{tags.OUTPUT_NAME}"
    for name in cmds.ls(pattern, long=True, objectsOnly=True) or []:
        node = tm.resolve(name)
        data = node.meta.as_dict()
        if (
            data.get(tags.INSTANCE) == instance_id
            and data.get(tags.OUTPUT_NAME) == output_name
        ):
            return node
    return None
```

- [ ] **Step 4: Use it in the Builder**

In `src/python/tik/trigger/maya/build.py`:

Give `Builder.__init__` a `self._keys_to_ids: dict = {}` so `resolve` can always reach it, then fill it in `Builder.build`, right after `instances = self.order(...)`:

```python
        # Display key -> instance id, from the *document*: a pass that deleted
        # its guides is invisible to a scene scan, which is exactly when a
        # later pass needs to find its outputs.
        self._keys_to_ids = {
            entry.key: entry.instance_id for entry in (document.modules if document else [])
        }
```

Then in `Builder.resolve`, between the `by_key` branch and the bare-scene-node fallback:

```python
        instance_id = self._keys_to_ids.get(key) if key else None
        if instance_id is not None:
            earlier = guide_nodes.find_output(instance_id, output)
            if earlier is not None:
                return earlier
```

In `_connect_one`, delete the "outside the build scope; left unattached" branch — `resolve` now answers, and a genuinely missing source raises `AttachError` as it already does.

In `_bind_parent_for`, after the existing `by_key` lookup returns nothing, fall back the same way:

```python
        if key not in by_key:
            instance_id = self._keys_to_ids.get(key)
            if instance_id is not None:
                return guide_nodes.find_output(instance_id, output)
```

Replace the `known_keys` computation in `build()` with `known_keys = set(self._keys_to_ids)`.

- [ ] **Step 5: Run the test to verify it passes**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration/trigger/test_multipass_build_trigger.py -q
```

Expected: PASS (2 tests).

- [ ] **Step 6: Run the full integration suite**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/guides/nodes.py src/python/tik/trigger/maya/build.py tests/integration/trigger/test_multipass_build_trigger.py
git commit -m "Resolve build inputs against earlier passes

A source outside the current pass is looked up by its trg_instance and
trg_output tags instead of warning and leaving the limb unattached, so a
rig split across several kinematics actions connects.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015xVfPaN3fdKbLNYdVWYS5n"
```

---

### Task 4: A duplicate display key stops the build

`by_key` is a plain dict, so two modules resolving to the same key silently overwrite and consumers attach to the wrong producer. Validation alone is not enough — nothing forces a rigger to validate before pressing Build.

**Files:**
- Modify: `src/python/tik/trigger/maya/build.py` (`Builder.build`)
- Test: `tests/integration/trigger/test_multipass_build_trigger.py` (extend)

**Interfaces:**
- Consumes: `BuildError` from `tik/trigger/core/exceptions.py`.
- Produces: nothing new; `Builder.build` raises `BuildError` earlier than before.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/trigger/test_multipass_build_trigger.py`:

```python
def test_duplicate_display_key_raises():
    """Two modules that resolve to one key would silently overwrite by_key."""
    from tik.trigger.core.exceptions import BuildError

    one = ModuleEntry(instance_id="aaa", module_type="toy_root", name="body", side="C")
    two = ModuleEntry(instance_id="bbb", module_type="toy_root", name="body", side="C")
    session = Session()
    session.document.guides = GuideDocument(modules=[one, two])
    session.add("kinematics", modules=["aaa", "bbb"])
    with pytest.raises(BuildError, match="body"):
        session.build()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration/trigger/test_multipass_build_trigger.py::test_duplicate_display_key_raises -q
```

Expected: FAIL — the build succeeds, or fails for an unrelated reason (duplicate Maya node names), not with a `BuildError` naming the key.

- [ ] **Step 3: Raise on the collision**

In `Builder.build`, immediately after `self._keys_to_ids` is built:

```python
        seen: dict = {}
        for entry in document.modules if document else []:
            if entry.key in seen:
                raise BuildError(
                    f"two modules share the display key '{entry.key}': "
                    f"{seen[entry.key]} and {entry.instance_id}. Rename one.",
                    instance_id=entry.instance_id,
                    module_type=entry.module_type,
                )
            seen[entry.key] = entry.instance_id
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/integration/trigger/test_multipass_build_trigger.py -q
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/maya/build.py tests/integration/trigger/test_multipass_build_trigger.py
git commit -m "Raise when two modules share a display key

by_key is a plain dict, so a collision silently overwrote the producer and
consumers attached to the wrong module.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015xVfPaN3fdKbLNYdVWYS5n"
```

---

### Task 5: The checks explicit scope makes possible

**Files:**
- Modify: `src/python/tik/trigger/session.py` (`validate`, `build`)
- Test: `tests/unit/test_session_trigger.py` (extend)

**Interfaces:**
- Consumes: `Document.walk(phase)` yielding `(path, node, parent)`; `BUILD` from `tik/trigger/core/document.py`; `split_source` from `tik/trigger/core/schemas.py`.
- Produces: `Session._scope_problems() -> list[str]`, called by both `validate()` and `build()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_session_trigger.py` (it already imports `Session` and `pytest`; add `GuideDocument`, `ModuleEntry` and the toy modules to its imports):

```python
def _scoped_session(entries, scopes):
    """A session with ``entries`` and one kinematics action per scope list."""
    from tik.trigger.core.guide_document import GuideDocument

    session = Session()
    session.document.guides = GuideDocument(modules=list(entries))
    for index, scope in enumerate(scopes):
        session.add("kinematics", name=f"pass{index}", modules=list(scope))
    return session


def test_double_build_is_an_error(_kinematics_registered):
    entries = [_module_entry("aaa", "spine")]
    session = _scoped_session(entries, [["aaa"], ["aaa"]])
    assert any("more than one" in item for item in session.validate())


def test_module_in_no_pass_is_a_warning(_kinematics_registered):
    entries = [_module_entry("aaa", "spine"), _module_entry("bbb", "wing")]
    session = _scoped_session(entries, [["aaa"]])
    problems = session.validate()
    assert any("built by no kinematics action" in item for item in problems)
    assert all(item.startswith("warning:") for item in problems if "wing" in item)


def test_source_built_in_a_later_pass_is_an_error(_kinematics_registered):
    spine = _module_entry("aaa", "spine")
    wing = _module_entry("bbb", "wing")
    wing.inputs = {"root": "aaa.root"}
    session = _scoped_session([spine, wing], [["bbb"], ["aaa"]])
    assert any("later kinematics action" in item for item in session.validate())


def test_source_in_no_pass_is_an_error(_kinematics_registered):
    spine = _module_entry("aaa", "spine")
    wing = _module_entry("bbb", "wing")
    wing.inputs = {"root": "aaa.root"}
    session = _scoped_session([spine, wing], [["bbb"]])
    assert any("no kinematics action builds" in item for item in session.validate())


def test_key_collision_among_built_modules_is_an_error(_kinematics_registered):
    one = _module_entry("aaa", "spine")
    two = _module_entry("bbb", "spine")
    session = _scoped_session([one, two], [["aaa", "bbb"]])
    assert any("display key" in item for item in session.validate())


def test_build_runs_the_cross_step_checks(_kinematics_registered):
    """Nothing calls validate() before a build, so build must check itself."""
    from tik.trigger.core.exceptions import SessionError

    entries = [_module_entry("aaa", "spine")]
    session = _scoped_session(entries, [["aaa"], ["aaa"]])
    with pytest.raises(SessionError, match="more than one"):
        session.build()
```

Add these helpers near the top of the file:

```python
def _module_entry(instance_id, name, module_type="toy_root", side="C"):
    from tik.trigger.core.guide_document import ModuleEntry

    return ModuleEntry(
        instance_id=instance_id, module_type=module_type, name=name, side=side
    )


@pytest.fixture
def _kinematics_registered():
    """The real kinematics action plus a toy module, on top of this file's registry."""
    from tik.trigger.core import register_module
    from tik.trigger.core.discovery import load_builtin_actions

    load_builtin_actions()
    register_module("toy_root")(ToyRoot)
    yield
```

If `load_builtin_actions` is not the discovery entry point in this codebase, import the action module directly — `import tik.trigger.actions.kinematics.kinematics  # noqa: F401` — which registers it as a side effect. Check `tik/trigger/core/discovery.py` first and use whichever exists.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_session_trigger.py -q -k "pass or double or collision or later"
```

Expected: FAIL — none of the messages exist yet.

- [ ] **Step 3: Implement the checks**

In `src/python/tik/trigger/session.py`, add:

```python
    def _kinematics_scopes(self) -> list:
        """``[(path, [instance ids])]`` for every enabled kinematics, in run order."""
        scopes = []
        for path, node, _parent in self.document.walk(BUILD):
            if node.type == "kinematics" and node.enabled:
                scopes.append((path, list(node.settings.get("modules") or [])))
        return scopes

    def _scope_problems(self) -> list:
        """Problems that span several actions, which no single action can see."""
        from tik.trigger.core.schemas import split_source

        problems: list[str] = []
        entries = list(self.document.guides.modules)
        by_id = {entry.instance_id: entry for entry in entries}
        scopes = self._kinematics_scopes()

        pass_of: dict = {}
        for index, (path, scope) in enumerate(scopes):
            for instance_id in scope:
                if instance_id in pass_of:
                    problems.append(
                        f"'{by_id[instance_id].key if instance_id in by_id else instance_id}'"
                        f" is built by more than one kinematics action "
                        f"({pass_of[instance_id][1]} and {path})."
                    )
                    continue
                pass_of[instance_id] = (index, path)

        for entry in entries:
            if entry.instance_id not in pass_of:
                problems.append(
                    f"warning: {entry.key} is built by no kinematics action."
                )

        keys: dict = {}
        for instance_id in pass_of:
            entry = by_id.get(instance_id)
            if entry is None:
                continue
            if entry.key in keys:
                problems.append(
                    f"two modules that build share the display key "
                    f"'{entry.key}'. Rename one."
                )
            keys[entry.key] = entry.instance_id

        for entry in entries:
            here = pass_of.get(entry.instance_id)
            if here is None:
                continue
            for source in entry.inputs.values():
                source_id, _output = split_source(source)
                if source_id is None or source_id not in by_id:
                    continue
                there = pass_of.get(source_id)
                if there is None:
                    problems.append(
                        f"{entry.key} needs {by_id[source_id].key}, but no "
                        f"kinematics action builds it."
                    )
                elif there[0] > here[0]:
                    problems.append(
                        f"{entry.key} needs {by_id[source_id].key}, which "
                        f"builds in a later kinematics action."
                    )
        return problems
```

Call it from `validate()` — append `problems.extend(self._scope_problems())` next to the existing `problems.extend(self._module_problems())` — and enforce the errors in `build()`, immediately before `self.capture_guides()`:

```python
        blocking = [
            item for item in self._scope_problems() if not item.startswith("warning:")
        ]
        if blocking:
            raise SessionError("; ".join(blocking))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_session_trigger.py -q
```

Expected: PASS.

- [ ] **Step 5: Report `legacy_roots` and `guides_file` too**

Add to `_scope_problems`, iterating the same walk:

```python
        for path, node, _parent in self.document.walk(BUILD):
            if node.type != "kinematics":
                continue
            if node.settings.get("legacy_roots"):
                    problems.append(
                        f"{path}: guide roots {node.settings['legacy_roots']} could "
                        "not be migrated to module ids; open the session and list "
                        "its modules."
                    )
                if node.settings.get("guides_file"):
                    problems.append(
                        f"{path}: 'guides_file' is no longer built at build time; "
                        "import the .trg into this session and list its modules."
                    )
```

Add a test for each alongside the others, following the same shape as `test_double_build_is_an_error`.

- [ ] **Step 6: Run the whole suite and lint**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit tests/integration -q
make lint
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/session.py tests/unit/test_session_trigger.py
git commit -m "Check what explicit build scope makes checkable

Double builds, modules in no pass, key collisions and a source that builds
in a later pass are all now statable mistakes. The blocking ones run in
build() too, since nothing calls validate() first.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015xVfPaN3fdKbLNYdVWYS5n"
```

---

## Done when

- [ ] `tests/unit` and `tests/integration` are green, and the count has grown by the new tests rather than shrunk by deleted ones.
- [ ] `make lint` is clean.
- [ ] `grep -rn "guide_roots\|guides_file" src/` returns only the migration module and the `validate()` report.
- [ ] `tests/data/crabMonster_main_session_v002.tr` loads and reports its unresolved root rather than silently building nothing.
- [ ] Phase 2 (the `ModuleReference` itself, resolution, and the views — spec §3, §4, §7) has its own plan and has not been started here.
