# Modules Build Without Inputs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every tik.trigger module buildable with nothing wired into its inputs, so that anything the rigger can assemble in the Guide Designer is a valid build.

**Architecture:** `Input.optional: bool = False` inverts to `Input.required: bool = False`, so attachment describes a socket another module *may* drive rather than a precondition. `Builder._connect_one` skips an absent source instead of raising (a *wrong* source still raises). Scope expansion loses its upstream half, which existed only to dodge the removed refusal. The ground rules gain a case that builds every shipped module standalone.

**Tech Stack:** Python 3.10+, Maya 2024+, `mayapy` + pytest, black / isort / flake8.

**Spec:** `docs/superpowers/specs/2026-09-09-modules-without-required-inputs-design.md`

## Global Constraints

- **No third-party deps.** Stdlib and Maya-bundled modules only.
- **`tik/trigger/core` is pure Python** — no Maya, no Qt imports. Enforced by `tests/unit/test_import_boundaries.py`.
- **Consume tik.maya** — no raw `maya.cmds` / `OpenMaya` in module or tool code. Tests may use `cmds` (they already do).
- **No schema bump.** The `.tr` stores connections, never input declarations. Nothing in this plan touches `to_dict` / `from_dict` or the schema version (currently 7).
- **Style:** black, isort (profile black), flake8. Run `make lint` before each commit; `make format` fixes the first two.
- **Test commands** (PowerShell, from the repo root):
  - Whole suites: `make tests-unit`, `make tests-integration`, `make tests-ui`
  - One file: `$env:PYTHONPATH = "$PWD/src/python;$env:PYTHONPATH"; mayapy -m pytest tests/unit/test_core_trigger.py -q`
  - UI needs two extra vars: `$env:TIK_TESTS_NO_MAYA = "1"; $env:QT_QPA_PLATFORM = "offscreen"` — Maya standalone cannot host a QApplication, so UI tests never run under the Maya suites.
- **Attribution:** end each commit message with the two lines given at the bottom of this plan.

---

## File Structure

| File | Responsibility after this plan |
|---|---|
| `src/python/tik/trigger/core/manifest.py` | `Input` declares `required: bool = False` |
| `src/python/tik/trigger/core/module.py` | `space_inputs` builds space-kind inputs with no requiredness kwarg |
| `src/python/tik/trigger/maya/build.py` | `_connect_one` skips an absent source unless the input is `required` |
| `src/python/tik/trigger/core/build_scope.py` | Downstream repair only; no upstream gap fill |
| `src/python/tik/trigger/modules/ribbon/ribbon.py`, `.../twist/twist.py` | Manifests drop the redundant `optional=True` |
| `src/python/tik/trigger/ui/designer/widgets.py` | `InputRow` marks the rare *required* input |
| `src/python/tik/trigger/modules/base/base.py` | Docstring states a convention, not a requirement |
| `tests/integration/trigger/test_module_ground_rules.py` | Holds "every shipped module builds standalone" |
| `docs/source/tik_trigger/guides/writing_modules.rst`, `modules_reference.rst`, `CLAUDE.md` | Document the inverted contract |

---

### Task 1: Invert the input contract; an absent source stops failing

This is one task and one commit on purpose: the rename and the behaviour change are the same edit. `declared.optional` has exactly two readers, and translating either one alone leaves the tree broken.

**Files:**
- Modify: `src/python/tik/trigger/core/manifest.py:14-30`
- Modify: `src/python/tik/trigger/core/module.py:144-152`
- Modify: `src/python/tik/trigger/maya/build.py:399-415`
- Modify: `src/python/tik/trigger/modules/ribbon/ribbon.py:36-40`
- Modify: `src/python/tik/trigger/modules/twist/twist.py:60-69`
- Modify: `src/python/tik/trigger/ui/designer/widgets.py:124-129`
- Test: `tests/unit/test_core_trigger.py:292-305`
- Test: `tests/integration/trigger/test_builder_trigger.py:49-56,198-224`
- Test: `tests/unit/test_connections_trigger.py:112-125`
- Test: `tests/helpers/toy_modules.py:31`
- Test: `tests/ui/test_trigger_widgets.py` (new class)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Input(name, kind="transform", primary=False, required=False, help="")` — the frozen dataclass every later task reads. `Module.space_inputs(settings) -> list[Input]` keeps its signature; the derived inputs now carry `required=False` implicitly. `Builder._connect_one` keeps its signature and raises `AttachError` only for a required-and-absent or a wrong source.

- [ ] **Step 1: Write the failing unit tests for the flag**

In `tests/unit/test_core_trigger.py`, add next to the other manifest tests:

```python
def test_an_input_is_not_required_by_default():
    """Attachment is a connection, not a precondition.

    Spec: 2026-09-09-modules-without-required-inputs-design.md, section 2.
    """
    assert Input("root", primary=True).required is False
    assert Input("anchor", required=True).required is True
```

and change the last assertion of `test_space_inputs_derive_one_port_per_row` (line 304) from

```python
    assert all(item.optional for item in derived)
```

to

```python
    assert not any(item.required for item in derived)
```

`Input` is **not** currently imported by that file — add it to the alphabetical `from tik.trigger.core import (...)` list at line 9, between `GuideLayout` and `Module`.

- [ ] **Step 2: Run the unit tests to verify they fail**

```powershell
$env:PYTHONPATH = "$PWD/src/python;$env:PYTHONPATH"; mayapy -m pytest tests/unit/test_core_trigger.py -q
```

Expected: FAIL — `TypeError: Input.__init__() got an unexpected keyword argument 'required'`.

- [ ] **Step 3: Write the failing integration test for the build**

In `tests/integration/trigger/test_builder_trigger.py`, replace the last paragraph of `test_scene_node_sources_must_exist_and_optional_inputs_may_be_empty` (lines 219-224, the `"required input"` branch) with the opposite assertion, and rename the test:

```python
def test_scene_node_sources_must_exist_and_an_unwired_input_builds(pair):
    scene, _body, tail = pair
    tail.set_input("space", "some_jnt")
    with pytest.raises(AttachError) as info:
        Builder().build(
            document=scene.document,
        )
    assert "some_jnt" in str(info.value) and "L_tail.space" in str(info.value)

    tm.Transform.create(name="some_jnt")
    report = Builder().build(document=scene.document, afterlife="keep")
    assert ("L_tail.space", "some_jnt") in report.connections

    tail.set_input("root", "body.nope")
    with pytest.raises(AttachError) as info:
        Builder().build(
            document=scene.document,
        )
    assert "not built" in str(info.value)

    # Nothing wired: the module builds, its socket free-standing at the guide,
    # and nothing is logged about it -- an unwired input is not a complaint.
    tail.set_input("root", "")
    tail.set_input("space", "")
    events = EventBus()
    logged = []
    events.subscribe("log", lambda **kw: logged.append(kw))

    report = Builder(events).build(document=scene.document, afterlife="keep")

    assert report.connections == []
    assert logged == []
    rig = report.rigs[tail.instance_id]
    assert rig.socket("root").parent.long_name == rig.groups.socket.long_name
```

`EventBus` is already imported at line 17 of that file, and `"log"` is the correct topic (`core/events.py:10`, emitted by `EventBus.log` at line 45 as `level=`/`message=`). The `logged == []` assertion is what holds spec section 5: no log, no chip, no note.

Also update `ToyChain`'s docstring and manifest in the same file (lines 49-56):

```python
class ToyChain(Module):
    """A root plus N segments, neither input required."""

    label = "Toy Chain"
    guides = GuideLayout("root", multi="segment", min=1)
    inputs = (Input("root", primary=True), Input("space"))
```

- [ ] **Step 4: Run the integration test to verify it fails**

```powershell
$env:PYTHONPATH = "$PWD/src/python;$env:PYTHONPATH"; mayapy -m pytest tests/integration/trigger/test_builder_trigger.py -q
```

Expected: FAIL — `TypeError` on the `Input(...)` construction, or `AttachError: L_tail.root: required input has no source.`

- [ ] **Step 5: Invert the flag on `Input`**

In `src/python/tik/trigger/core/manifest.py`, replace the `Input` dataclass:

```python
@dataclass(frozen=True)
class Input:
    """An attachment point another module (or a scene node) can drive.

    Leaving an input unwired is a legal, ordinary state: the socket is created
    either way and simply stands still at its matched guide, so a module built
    alone is a rig root of its own. ``required`` is for the rare module that
    genuinely cannot build without a driver -- nothing this repo ships sets it.

    Args:
        name: Input name (unique per module).
        kind: ``transform`` | ``joint`` | ``attribute`` (graph validation).
        primary: The input the tree view shows as parenting (one per module).
        required: Build fails without a source. Almost never true.
        help: Tooltip text.
    """

    name: str
    kind: str = "transform"
    primary: bool = False
    required: bool = False
    help: str = ""
```

- [ ] **Step 6: Update the derived space inputs**

In `src/python/tik/trigger/core/module.py`, in `space_inputs` (lines 144-152), change the docstring and drop the kwarg:

```python
    @classmethod
    def space_inputs(cls, settings=None) -> list[Input]:
        """One space-kind Input per row: ``<control>_<label>``."""
        found = []
        for row in cls.space_rows(settings):
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            found.append(Input(f"{control}_{label}", kind="space"))
        return found
```

- [ ] **Step 7: Stop the builder refusing an absent source**

In `src/python/tik/trigger/maya/build.py`, in `_connect_one` (lines 399-415), invert the guard:

```python
    def _connect_one(self, instance, module_cls, inputs, by_key, report) -> None:
        """Attach every declared input of one already-built instance.

        An input with no source is left alone: its socket stands free at its
        matched guide and the module works in place. A source that is *named
        but wrong* still fails -- silence is for "I did not wire this", never
        for a typo.
        """
        rig = report.rigs[instance.instance_id]
        for declared in module_cls.inputs:
            source = inputs.get(declared.name)
            if not source:
                if not declared.required:
                    continue
                raise AttachError(
                    f"{instance.key}.{declared.name}: required input has no source.",
                    instance_id=instance.instance_id,
                    module_type=instance.module_type,
                )
            node = self.resolve(
                source,
                by_key,
                report,
                where=f"{instance.key}.{declared.name}",
                instance=instance,
            )
            connect(rig, declared.name, node)
            report.connections.append((f"{instance.key}.{declared.name}", source))
```

Leave `resolve` (lines 490-522) and the anim-space warning (line 446) exactly as they are.

- [ ] **Step 8: Drop the now-redundant `optional=True` from the two module manifests**

`src/python/tik/trigger/modules/ribbon/ribbon.py`, line 39:

```python
        Input("reference", help="Frame the start twist is read against"),
```

`src/python/tik/trigger/modules/twist/twist.py`, lines 63-68:

```python
        Input(
            "reference",
            help="What a start-sourced twist is measured against; "
            "defaults to the base socket's parent",
        ),
```

- [ ] **Step 9: Invert the Designer's placeholder**

In `src/python/tik/trigger/ui/designer/widgets.py`, lines 125-129:

```python
        self.line.setPlaceholderText(
            "module.output or scene node"
            + ("  (required)" if input_decl.required else "")
        )
```

- [ ] **Step 10: Update the remaining fixtures that assert the old rule**

`tests/helpers/toy_modules.py`, line 31:

```python
    inputs = (Input("root", primary=True), Input("space"))
```

`tests/unit/test_connections_trigger.py`, `test_cleared_input_is_not_re_derived_from_the_parent` (lines 112-125) — the clearing still clears, but the build now succeeds:

```python
def test_cleared_input_is_not_re_derived_from_the_parent(guides):
    """Clearing an input means unconnected, even while the guides stay parented.

    Unconnected is not an error: the arm builds standing on its own.
    """
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    arm.set_input("root", "")

    assert arm.inputs == {}
    report = Builder().build(document=guides.document, afterlife="keep")
    assert report.connections == []
```

If `AttachError` is now unused in that file's imports, flake8 will say so — remove it from the import list only if nothing else in the file raises it (`test_build_connects_to_scene_node_and_errors` at line 119 still does, so it most likely stays).

- [ ] **Step 11: Add the UI test for the placeholder**

Append to `tests/ui/test_trigger_widgets.py`:

```python
class TestInputRowPlaceholder:
    """The rare required input is what gets marked, not the common one."""

    def test_an_unrequired_input_is_unmarked(self, qapp):
        from tik.trigger.core import Input
        from tik.trigger.ui.designer.widgets import InputRow

        row = InputRow(Input("root", primary=True))
        assert row.line.placeholderText() == "module.output or scene node"

    def test_a_required_input_says_so(self, qapp):
        from tik.trigger.core import Input
        from tik.trigger.ui.designer.widgets import InputRow

        row = InputRow(Input("anchor", required=True))
        assert row.line.placeholderText().endswith("(required)")
```

`qapp` is the QApplication fixture defined at `tests/ui/conftest.py:84`; it is not autouse, so the parameter above is required.

- [ ] **Step 12: Run every affected suite**

```powershell
make tests-unit
make tests-integration
$env:TIK_TESTS_NO_MAYA = "1"; $env:QT_QPA_PLATFORM = "offscreen"; make tests-ui
```

Expected: PASS. If a *shipping* module fails to build standalone here, stop and report it — that is a real finding about that module, not something to paper over by re-wiring the test.

- [ ] **Step 13: Lint and commit**

```powershell
make format
make lint
git add src/python/tik/trigger/core/manifest.py src/python/tik/trigger/core/module.py src/python/tik/trigger/maya/build.py src/python/tik/trigger/modules/ribbon/ribbon.py src/python/tik/trigger/modules/twist/twist.py src/python/tik/trigger/ui/designer/widgets.py tests/
git commit
```

Message:

```
TW-21 an input is a connection, not a precondition

Input.optional inverts to Input.required=False and the builder skips an
absent source instead of raising. A wrong source -- an output that does not
exist, a scene node that does not exist -- still fails the build.
```

---

### Task 2: Build scope loses its upstream half

**Files:**
- Modify: `src/python/tik/trigger/core/build_scope.py:45-105`
- Test: `tests/unit/test_build_scope_trigger.py:44-46,63-80,101-106`

**Interfaces:**
- Consumes: `Input.required` from Task 1 (indirectly — `_structural_producers` reads `space_inputs`, unchanged).
- Produces: `expand_build_scope(entries, ids, already_built=()) -> list` — same signature, same return type, narrower result. `maya/build.py:337` calls it unchanged.

- [ ] **Step 1: Rewrite the tests that assert upstream pull**

In `tests/unit/test_build_scope_trigger.py`, replace `test_an_unbuilt_producer_is_pulled_in` (lines 44-46) with its inverse:

```python
def test_an_unbuilt_producer_is_left_alone():
    """Building the arm alone builds the arm alone: its socket stands free."""
    assert expand_build_scope(_chain(), ["id_arm"]) == ["id_arm"]
```

Replace `test_the_scope_is_returned_in_document_order` (lines 76-84) — its second half relied on the upstream pull, so make the order assertion carry its weight downstream instead:

```python
def test_the_scope_is_returned_in_document_order():
    entries = _chain()
    scope = expand_build_scope(
        entries, ["id_hand"], already_built={"id_body", "id_arm", "id_hand"}
    )
    assert scope == ["id_hand"]
    scope = expand_build_scope(
        entries,
        ["id_hand", "id_body"],
        already_built={"id_body", "id_arm", "id_hand"},
    )
    assert scope == ["id_body", "id_arm", "id_hand"]
```

Replace `test_an_unknown_module_type_treats_every_input_as_structural` (lines 101-106) — it proved its point through the upstream walk, so walk downstream instead:

```python
def test_an_unknown_module_type_treats_every_input_as_structural():
    """A module the registry has never heard of must not crash the scope."""
    body = _entry("id_body", "body", module_type="toy_root")
    arm = _entry("id_arm", "arm", inputs={"root": "id_body.root"}, module_type="ghost")
    scope = expand_build_scope(
        [body, arm], ["id_body"], already_built={"id_body", "id_arm"}
    )
    assert scope == ["id_body", "id_arm"]
```

Leave every other test in the file alone: the already-built-producer, unbuilt-consumer, downstream-transitive, space-input, bare-scene-node, cycle and unknown-id cases all still assert what they say.

- [ ] **Step 2: Run to verify they fail**

```powershell
$env:PYTHONPATH = "$PWD/src/python;$env:PYTHONPATH"; mayapy -m pytest tests/unit/test_build_scope_trigger.py -q
```

Expected: FAIL — `assert ['id_body', 'id_arm'] == ['id_arm']` on the first, and the reworked order/unknown cases still passing or failing on the extra ids.

- [ ] **Step 3: Delete the upstream walk**

In `src/python/tik/trigger/core/build_scope.py`, remove the second `while stack:` loop entirely (the one commented `# upstream: unbuilt producers only`) so the function ends:

```python
    stack = list(wanted)
    while stack:  # downstream: built consumers only
        for consumer in consumers.get(stack.pop(), ()):
            if consumer in wanted or consumer not in built:
                continue
            wanted.add(consumer)
            stack.append(consumer)

    return [instance_id for instance_id in order if instance_id in wanted]
```

`producers` is still needed — it is what `consumers` is built from — so leave the mapping loop above untouched.

- [ ] **Step 4: Rewrite the docstring's second paragraph**

Replace the "Upstream, to fill gaps" paragraph with:

```
    Nothing upstream: an unbuilt producer is left alone and the consumer's
    socket simply stands free at its guide, which is a legal build since
    2026-09-09. Build the producer later and the downstream half rebuilds the
    consumer, which attaches then. This is the ``kinematics`` rule -- a pass
    builds only the modules it names.
```

- [ ] **Step 5: Run the test file to verify it passes**

```powershell
$env:PYTHONPATH = "$PWD/src/python;$env:PYTHONPATH"; mayapy -m pytest tests/unit/test_build_scope_trigger.py -q
```

Expected: PASS, all cases.

- [ ] **Step 6: Run the test-rig integration suite**

```powershell
$env:PYTHONPATH = "$PWD/src/python;$env:PYTHONPATH"; mayapy -m pytest tests/integration/trigger/test_test_rig_trigger.py -q
```

Expected: PASS. Any case there that asserts a producer was built behind the rigger's back is now wrong by decision — update it to assert the narrower scope, and say so in the commit message.

- [ ] **Step 7: Lint and commit**

```powershell
make format
make lint
git add src/python/tik/trigger/core/build_scope.py tests/
git commit
```

Message:

```
TW-21 a scoped test build builds only what it names

The upstream gap fill existed so a first build of an arm on its own would
not fail on a required input. Required inputs are gone, so the workaround
goes with them. Downstream repair is unchanged.
```

---

### Task 3: The ground rules hold every shipped module to a standalone build

**Files:**
- Modify: `tests/integration/trigger/test_module_ground_rules.py:24-40,67-80,239-256`

**Interfaces:**
- Consumes: `Input.required` (Task 1), the narrower `expand_build_scope` (Task 2, not used here).
- Produces: nothing other tasks read. `_solo(module_type)` keeps its name and return type (`ModuleRig` context).

- [ ] **Step 1: Add the standalone case**

Add near the other manifest-level tests, using the existing `_shipped_module_types()` helper (line 54) rather than the narrower `MODULE_TYPES` tuple:

```python
@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_every_shipped_module_builds_standalone(module_type):
    """Anything buildable in the Designer is a valid build.

    No parent, no inputs wired. The module's sockets stand free at their
    guides and it must still produce exactly what its manifest declares.

    Spec: 2026-09-09-modules-without-required-inputs-design.md, section 8.
    """
    cmds.file(new=True, force=True)
    scene = GuideScene()
    module_cls = get_module(module_type)
    instance = scene.create_guides(module_cls(name=module_type))
    report = Builder().build(document=scene.document, afterlife="keep")

    ctx = report.rigs[instance.instance_id]
    assert not instance.inputs, "an unparented module must start unwired"
    assert _built_control_roles(ctx) == sorted(
        module_cls.control_names(instance.settings)
    )
    for output in module_cls.output_names(instance.settings):
        assert output in ctx.outputs
```

`output_names(settings)` is the settings-driven output manifest (`core/module.py:180`) and `control_names(settings)` its control counterpart (`core/module.py:188`); both return `tuple[str, ...]`, which is why the control assertion wraps its right-hand side in `sorted()`.

- [ ] **Step 2: Run it to see where each module stands**

```powershell
$env:PYTHONPATH = "$PWD/src/python;$env:PYTHONPATH"; mayapy -m pytest tests/integration/trigger/test_module_ground_rules.py -k standalone -q
```

Expected: PASS for all of `base`, `fkchain`, `arm`, `ribbon`, `twist`. A failure here is a **finding, not a test bug** — report which module, the traceback, and what it needed, and stop rather than weakening the assertion.

- [ ] **Step 3: Simplify `_solo` — it no longer needs a parent**

Replace `_solo` (lines 24-40) with the thing its name always claimed:

```python
def _solo(module_type):
    """Build one unconnected instance and return its context."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    instance = scene.create_guides(get_module(module_type)(name=module_type))
    report = Builder().build(document=scene.document, afterlife="keep")
    return report.rigs[instance.instance_id]
```

- [ ] **Step 4: Drop the same branch from the world-root test**

In `test_module_parents_everything_it_creates` (lines 239-256), replace the `if get_module(module_type).primary_input() is not None:` branch and its `else` with the unconditional single line:

```python
    scene.create_guides(get_module(module_type)(name=module_type))
```

- [ ] **Step 5: Make `_built_with`'s wiring conditional on `required`**

In `_built_with` (lines 67-80), the loop at lines 78-80 wires every non-primary, non-optional input. Change the docstring and the guard:

```python
def _built_with(module_type, settings):
    """Build one instance under a base, with every required input wired."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    body = scene.create_guides(get_module("base")(name="body"))
    module_cls = get_module(module_type)
    primary = module_cls.primary_input()
    instance = scene.create_guides(
        module_cls(name=module_type),
        parent=ParentRef(body.instance_id, "root") if primary is not None else None,
    )
    for declared in module_cls.inputs:
        if not declared.required or (
            primary is not None and declared.name == primary.name
        ):
            continue
        scene.set_input(instance.instance_id, declared.name, f"{body.key}.root")
```

Leave the rest of the function (the `write_settings` / `draw` / build tail) untouched. Note this makes the loop a no-op today, since nothing declares `required=True` — that is correct and deliberate; the loop stays so a future required input is wired without anyone remembering to add it back.

- [ ] **Step 6: Run the whole ground rules file**

```powershell
$env:PYTHONPATH = "$PWD/src/python;$env:PYTHONPATH"; mayapy -m pytest tests/integration/trigger/test_module_ground_rules.py -q
```

Expected: PASS. `test_every_declared_input_gets_a_socket` in particular now proves its point on a genuinely unconnected module, which is what it always meant.

- [ ] **Step 7: Run the full integration suite**

```powershell
make tests-integration
```

Expected: PASS.

- [ ] **Step 8: Lint and commit**

```powershell
make format
make lint
git add tests/integration/trigger/test_module_ground_rules.py
git commit
```

Message:

```
TW-21 ground rules: every shipped module builds standalone

_solo is now genuinely solo -- it no longer plants a base to hang the
module from -- and a new case builds every module in tik.trigger.modules
with nothing wired, asserting its declared controls and outputs.
```

---

### Task 4: Documentation

**Files:**
- Modify: `docs/source/tik_trigger/guides/writing_modules.rst:90-105`
- Modify: `docs/source/tik_trigger/guides/modules_reference.rst:267-268`
- Modify: `src/python/tik/trigger/modules/base/base.py:9-12`
- Modify: `CLAUDE.md` (the "Module Ground Rules" section)
- Modify: `docs/superpowers/specs/2026-09-09-modules-without-required-inputs-design.md:4`

**Interfaces:**
- Consumes: the finished behaviour from Tasks 1-3.
- Produces: nothing code reads.

- [ ] **Step 1: Update the module-author guide**

In `docs/source/tik_trigger/guides/writing_modules.rst`, the `Input` block (lines 90-105):

```rst
   inputs = (
       Input("start", primary=True, help="What the ribbon start pins to"),
       Input("end", help="What the ribbon end pins to"),
       Input("reference", help="Frame the twist is read against"),
   )

- ``primary``: one per module. The tree shows it as parenting, and drawing a
  module under another pre-fills it.
- ``required``: the build *fails* with nothing connected. Almost never wanted
  -- an unwired input simply leaves its socket standing free at its guide, and
  the module builds and works in place. Nothing tik.trigger ships sets it.
- ``kind``: ``transform`` (default), ``joint`` or ``attribute``; ``space`` is
  reserved for the inputs the anim-spaces table generates.
```

- [ ] **Step 2: Update the ribbon row in the module reference**

In `docs/source/tik_trigger/guides/modules_reference.rst`, lines 267-268:

```rst
   * - Inputs
     - ``start`` (primary), ``end``, ``reference`` (the frame the start twist
       is read against)
```

- [ ] **Step 3: Soften the base module's docstrings**

In `src/python/tik/trigger/modules/base/base.py`, the module and class docstrings:

```python
"""Base module: a single root controller + joint a rig conventionally starts from."""
```

```python
class Base(Module):
    """Root of a rig, by convention rather than by rule.

    Modules attach to its ``root`` output, but none of them require it: a rig
    may have several bases for different purposes, or none at all.
    """
```

- [ ] **Step 4: Add the rule to CLAUDE.md**

In the **Module Ground Rules** section, after the sentence ending "A **socket per declared input** is created for you in `socket_grp` — declaring the input is what makes it.", add:

```markdown
An input is a
connection, not a precondition: leaving one unwired is legal, the socket simply
stands free at its guide, and the module builds and works in place — **anything
buildable in the Guide Designer is a valid build**. `Input(..., required=True)`
exists for a module that genuinely cannot; nothing ships one, and
`tests/integration/trigger/test_module_ground_rules.py` builds every module
standalone to keep it that way.
```

Also add the new spec to the **Design specs** list in the tik.trigger section, in date order at the front:

```markdown
`docs/superpowers/specs/2026-09-09-modules-without-required-inputs-design.md`
(attachment is a connection, not a precondition: the inverted `Input.required`,
what stays a build error, and why scope expansion lost its upstream half;
**amends the test-rig sandbox spec's scope expansion**),
```

- [ ] **Step 5: Flip the spec's status**

In `docs/superpowers/specs/2026-09-09-modules-without-required-inputs-design.md`, line 4:

```markdown
**Status:** implemented
```

- [ ] **Step 6: Check nothing else still teaches the old rule**

```powershell
Select-String -Path AI/*.md, CLAUDE.md, docs/source -Pattern "optional" -Recurse | Select-String -NotMatch "defaults.json|optional: overrides"
```

Fix any remaining prose that says an input is required or that `optional` exists. Ignore `docs/superpowers/plans/` and older `docs/superpowers/specs/` — those are historical records of what was decided then, and are not rewritten.

- [ ] **Step 7: Build the docs to confirm the RST still parses**

```powershell
make docs
```

Expected: no new warnings about the two edited files. If Sphinx is not installed in this environment, say so and skip — do not claim it passed.

- [ ] **Step 8: Commit**

```powershell
git add docs CLAUDE.md src/python/tik/trigger/modules/base/base.py
git commit
```

Message:

```
TW-21 document that an input is a connection, not a precondition
```

---

## Final verification

- [ ] `make tests-unit` — PASS
- [ ] `make tests-integration` — PASS
- [ ] `$env:TIK_TESTS_NO_MAYA = "1"; $env:QT_QPA_PLATFORM = "offscreen"; make tests-ui` — PASS
- [ ] `make lint` — clean
- [ ] `git log --oneline main..HEAD` shows four commits, each with a green suite behind it
- [ ] Paste the actual command output when reporting. Evidence before assertions.

## Commit attribution

End every commit message in this plan with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01YHtVfpawfPpnPu4ZGwTKn1
```
