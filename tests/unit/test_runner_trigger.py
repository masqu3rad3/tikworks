"""Runner: order, nesting, until/only, references, overrides, cycles."""

import pytest

from tik.core.fields import FileField
from tik.trigger.core import (
    Action,
    ActionContext,
    EventBus,
    IntField,
    StringField,
    clear_registries,
    register_action,
)
from tik.trigger.core.document import BUILD, PUBLISH, ActionNode, Document
from tik.trigger.core.exceptions import ActionExecutionError, SessionError
from tik.trigger.maya.runner import STEP_FAILED, STEP_FINISHED, Runner

CALLS: list = []


class Mark(Action):
    label = "Mark"
    tag = StringField("")
    amount = IntField(1)

    def run(self, ctx):
        CALLS.append(("mark", ctx.path, self.tag, self.amount, ctx.base_dir))


class Boom(Action):
    def run(self, ctx):
        raise RuntimeError("boom")


class SeesRig(Action):
    def run(self, ctx):
        CALLS.append(("rig", ctx.rig))


class NeedsFile(Action):
    file = FileField("", extensions=[".txt"])

    def run(self, ctx):
        CALLS.append(("file", str(ctx.resolve(self.file))))


@pytest.fixture(autouse=True)
def _registered():
    CALLS.clear()
    clear_registries()
    register_action("mark", category="build")(Mark)
    register_action("boom")(Boom)
    register_action("needs_file")(NeedsFile)
    register_action("sees_rig")(SeesRig)
    from tik.trigger.actions.reference.reference import Reference

    register_action("reference", category="structure")(Reference)
    yield
    clear_registries()


def _doc():
    doc = Document()
    doc.add(ActionNode("a", "mark", settings={"tag": "A"}))
    doc.add(ActionNode("a1", "mark", settings={"tag": "A1"}), parent="a")
    doc.add(ActionNode("a2", "mark", settings={"tag": "A2"}), parent="a")
    doc.add(ActionNode("b", "mark", settings={"tag": "B"}))
    doc.add(ActionNode("off", "mark", enabled=False))
    doc.add(ActionNode("off_child", "mark"), parent="off")
    doc.add(ActionNode("c", "mark", settings={"tag": "C"}))
    return doc


def _marks():
    return [call[1] for call in CALLS if call[0] == "mark"]


def test_depth_first_order_and_disabled_subtree():
    results = Runner().run(_doc(), "D:/x")
    assert _marks() == ["a", "a/a1", "a/a2", "b", "c"]
    assert [item.status for item in results] == ["done"] * 5


def test_until_and_only():
    Runner().run(_doc(), until="a/a2")
    assert _marks() == ["a", "a/a1", "a/a2"]
    CALLS.clear()
    Runner().run(_doc(), only="b")
    assert _marks() == ["b"]
    with pytest.raises(SessionError):
        Runner().plan(_doc(), until="ghost")
    with pytest.raises(SessionError):
        Runner().plan(_doc(), only="off")  # disabled = not runnable


def test_events_and_failure_wraps():
    doc = _doc()
    doc.add(ActionNode("bad", "boom"), index=1)
    events = EventBus()
    finished, failed = [], []
    events.subscribe(STEP_FINISHED, lambda **kw: finished.append(kw["path"]))
    events.subscribe(STEP_FAILED, lambda **kw: failed.append(kw["path"]))
    with pytest.raises(ActionExecutionError) as info:
        Runner(events).run(doc)
    assert finished == ["a", "a/a1", "a/a2"] and failed == ["bad"]
    assert info.value.action_name == "bad"
    assert _marks() == ["a", "a/a1", "a/a2"]


def test_validation_blocks_missing_file(tmp_path):
    doc = Document()
    doc.add(ActionNode("f", "needs_file", settings={"file": "missing.txt"}))
    with pytest.raises(ActionExecutionError) as info:
        Runner().run(doc, str(tmp_path))
    assert "file not found" in str(info.value)
    (tmp_path / "there.txt").write_text("x")
    doc.find("f").settings["file"] = "there.txt"
    Runner().run(doc, str(tmp_path))
    assert ("file", str(tmp_path / "there.txt")) in CALLS


def _write_base(tmp_path, name="baseRig_v001.tr"):
    base = Document()
    base.add(ActionNode("kinematics", "mark", settings={"tag": "KIN"}))
    base.add(ActionNode("scripts", "mark", settings={"tag": "S"}))
    base.add(
        ActionNode("head_rotation", "mark", settings={"tag": "HEAD"}), parent="scripts"
    )
    base.add(ActionNode("fingers", "mark", settings={"tag": "FING"}), parent="scripts")
    rigs = tmp_path / "rigs"
    rigs.mkdir(exist_ok=True)
    return base.save(rigs / name)


def test_reference_expands_with_overrides_and_relative_paths(tmp_path):
    _write_base(tmp_path)
    _write_base(tmp_path, "baseRig_v002.tr")
    doc = Document()
    doc.add(ActionNode("import", "mark", settings={"tag": "IMP"}))
    ref = ActionNode(
        "base",
        "reference",
        settings={
            "file": "rigs/baseRig_v001.tr",
            "version": "latest",
            "overrides": {
                "scripts/head_rotation": {"enabled": False},
                "kinematics": {"settings": {"tag": "KIN-OVERRIDE"}},
            },
        },
    )
    doc.add(ref)
    doc.add(ActionNode("local_child", "mark", settings={"tag": "LOCAL"}), parent="base")
    doc.add(ActionNode("weights", "mark", settings={"tag": "W"}))
    plan = Runner().plan(doc, str(tmp_path))
    assert [step.path for step in plan.steps] == [
        "import",
        "base/kinematics",
        "base/scripts",
        "base/scripts/fingers",
        "base/local_child",
        "weights",
    ]
    kin = next(step for step in plan.steps if step.path == "base/kinematics")
    assert kin.linked and kin.base_dir == str(tmp_path / "rigs")
    assert kin.chain[0].endswith("baseRig_v002.tr")  # latest resolved
    assert kin.node.settings["tag"] == "KIN-OVERRIDE"
    CALLS.clear()
    Runner().run(doc, str(tmp_path))
    tags = [call[2] for call in CALLS if call[0] == "mark"]
    assert tags == ["IMP", "KIN-OVERRIDE", "S", "FING", "LOCAL", "W"]


def test_reference_include_and_missing_and_cycle(tmp_path):
    base_path = _write_base(tmp_path)
    doc = Document()
    doc.add(
        ActionNode(
            "base",
            "reference",
            settings={
                "file": str(base_path),
                "version": "pinned",
                "include": ["scripts/fingers"],
            },
        )
    )
    plan = Runner().plan(doc, str(tmp_path))
    assert [step.path for step in plan.steps] == [
        "base/scripts",
        "base/scripts/fingers",
    ]

    doc = Document()
    doc.add(ActionNode("base", "reference", settings={"file": "rigs/nope.tr"}))
    with pytest.raises(SessionError):
        Runner().plan(doc, str(tmp_path))

    # cycle: a.tr references b.tr which references a.tr
    a_doc, b_doc = Document(), Document()
    a_doc.add(
        ActionNode("to_b", "reference", settings={"file": "b.tr", "version": "pinned"})
    )
    b_doc.add(
        ActionNode("to_a", "reference", settings={"file": "a.tr", "version": "pinned"})
    )
    a_doc.save(tmp_path / "a.tr")
    b_doc.save(tmp_path / "b.tr")
    doc = Document()
    doc.add(
        ActionNode("root", "reference", settings={"file": "a.tr", "version": "pinned"})
    )
    with pytest.raises(SessionError) as info:
        Runner().plan(doc, str(tmp_path))
    assert "cycle" in str(info.value)


# ---------------------------------------------------------------- phases


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
    assert [step.path for step in runner.plan(doc, "D:/x", phase=PUBLISH).steps] == [
        "fbx",
        "ma",
    ]
    assert {step.phase for step in runner.plan(doc, "D:/x", phase=PUBLISH).steps} == {
        PUBLISH
    }


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
    events.subscribe(
        "progress",
        lambda current=0, total=0, label="", **_kw: seen.append((current, total)),
    )
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
    events.subscribe(
        STEP_FINISHED, lambda path="", phase="", **_kw: seen.append((phase, path))
    )
    Runner(events).run(_both_phases(), "D:/x", publish=True)
    assert seen == [(BUILD, "a"), (BUILD, "b"), (PUBLISH, "fbx"), (PUBLISH, "ma")]


def test_a_reference_contributes_build_actions_only(tmp_path):
    inner = Document()
    inner.add(ActionNode("inner_build", "mark", settings={"tag": "IB"}))
    inner.add(
        ActionNode("inner_publish", "mark", settings={"tag": "IP"}), phase=PUBLISH
    )
    inner.save(tmp_path / "base.tr")

    outer = Document()
    outer.add(ActionNode("ref", "reference", settings={"file": "base.tr"}))
    outer.add(ActionNode("own", "mark", settings={"tag": "OWN"}), phase=PUBLISH)

    Runner().run(outer, str(tmp_path), publish=True)
    assert _marks() == ["ref/inner_build", "own"]


# ---------------------------------------------------------------- scaffold
def test_every_step_receives_the_scaffold():
    from maya import cmds

    from tik.trigger.maya.scaffold import RigScaffold

    doc = Document()
    doc.add(ActionNode("first", "sees_rig"))
    doc.add(ActionNode("second", "sees_rig"))
    Runner().run(doc, "D:/x")
    rigs = [call[1] for call in CALLS if call[0] == "rig"]
    assert len(rigs) == 2 and all(isinstance(rig, RigScaffold) for rig in rigs)
    assert rigs[0].root.long_name == rigs[1].root.long_name == "|rig_grp"
    assert len(cmds.ls("rig_grp")) == 1


def test_a_script_can_extend_the_preferences_control():
    from maya import cmds

    from tik.trigger.actions.script.script import Script

    register_action("script", category="structure", scope="both")(Script)
    doc = Document()
    doc.add(
        ActionNode(
            "extend",
            "script",
            settings={
                "code": (
                    "plug = ctx.rig.preferences.transform['exportLod']\n"
                    "plug.create('int', default=0, keyable=False)\n"
                    "plug.visible = True\n"
                )
            },
        )
    )
    Runner().run(doc, "D:/x")
    assert cmds.attributeQuery("exportLod", node="preferences_ctrl", exists=True)


def test_the_runner_enters_one_script_space_per_run_and_tears_it_down():
    import sys

    seen = []

    class Peek(Action):
        def run(self, ctx):
            seen.append((ctx.scripts, "trigger_build" in sys.modules))
            ctx.scripts.add_path(ctx.base_dir + "/scripts")

    register_action("peek", category="build")(Peek)
    doc = Document()
    doc.add(ActionNode("a", "peek"))
    doc.add(ActionNode("b", "peek"))
    Runner().run(doc, "D:/nowhere")
    assert len(seen) == 2
    assert seen[0][0] is seen[1][0]  # one space for the run
    assert seen[0][1] and seen[1][1]
    assert "trigger_build" not in sys.modules


# ------------------------------------------------------------ script action
def _script_session(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "general_rig_utils_v001.py").write_text(
        "def tag():\n    return 'gen'\n", encoding="utf-8"
    )
    (scripts / "cfx_utils_v001.py").write_text(
        "import gen_rig\n\ndef tag():\n    return 'cfx+' + gen_rig.tag()\n",
        encoding="utf-8",
    )
    (scripts / "hero_build_v001.py").write_text(
        "import cfx_utils\n\n"
        "def finalize(ctx):\n"
        "    from maya import cmds\n"
        "    cmds.createNode('transform', "
        "name='mark_' + cfx_utils.tag().replace('+', '_'))\n",
        encoding="utf-8",
    )
    return tmp_path


def _register_script():
    from tik.trigger.actions.script.script import Script

    register_action("script", category="structure", scope="both")(Script)


def test_script_actions_load_libraries_that_call_each_other(tmp_path):
    import sys

    from maya import cmds

    _register_script()
    base = _script_session(tmp_path)
    doc = Document()
    doc.add(
        ActionNode(
            "gen",
            "script",
            settings={
                "file_path": "scripts/general_rig_utils_v001.py",
                "import_as": "gen_rig",
            },
        )
    )
    doc.add(
        ActionNode("cfx", "script", settings={"file_path": "scripts/cfx_utils_v001.py"})
    )
    doc.add(
        ActionNode(
            "hero", "script", settings={"file_path": "scripts/hero_build_v001.py"}
        )
    )
    doc.add(
        ActionNode("finalize", "script", settings={"code": "hero_build.finalize(ctx)"})
    )
    Runner().run(doc, str(base))
    assert cmds.objExists("mark_cfx_gen")
    # build lifetime: nothing survives the run
    assert not {"gen_rig", "cfx_utils", "hero_build", "trigger_build"} & set(
        sys.modules
    )
    assert str(base / "scripts") not in sys.path


def test_maya_lifetime_keeps_the_module_until_the_next_run(tmp_path):
    import sys

    _register_script()
    base = _script_session(tmp_path)
    doc = Document()
    doc.add(
        ActionNode(
            "gen",
            "script",
            settings={
                "file_path": "scripts/general_rig_utils_v001.py",
                "import_as": "gen_rig",
                "lifetime": "maya",
            },
        )
    )
    Runner().run(doc, str(base))
    import trigger_build  # noqa: E402 - the point of the test

    assert trigger_build.gen_rig.tag() == "gen"
    assert trigger_build.ctx is None
    assert sys.modules["gen_rig"] is trigger_build.gen_rig
    # a second run with build lifetime replaces and then drops it
    doc.find("gen").settings["lifetime"] = "build"
    Runner().run(doc, str(base))
    assert "gen_rig" not in sys.modules and "trigger_build" not in sys.modules


def test_a_missing_alias_fails_with_an_ordering_hint(tmp_path):
    _register_script()
    base = _script_session(tmp_path)
    doc = Document()
    doc.add(
        ActionNode("cfx", "script", settings={"file_path": "scripts/cfx_utils_v001.py"})
    )
    with pytest.raises(ActionExecutionError) as info:
        Runner().run(doc, str(base))
    assert "gen_rig is not loaded yet" in str(info.value)


def test_script_validation_rejects_bad_aliases_and_missing_files(tmp_path):
    from tik.trigger.actions.script.script import Script

    ctx = ActionContext(base_dir=str(tmp_path))
    assert "file not found" in Script({"file_path": "nope.py"}).validate(ctx)[0]
    (tmp_path / "x.py").write_text("", encoding="utf-8")
    bad = Script({"file_path": "x.py", "import_as": "my alias"}).validate(ctx)
    assert "not a valid module name" in bad[0]
    assert Script({"file_path": "x.py", "import_as": "sys"}).validate(ctx)
    assert Script({"file_path": "x.py"}).validate(ctx) == []
    assert Script({}).validate(ctx) == []
    assert Script({"file_path": "scripts/hero_build_v001.py"}).alias() == "hero_build"
    assert (
        Script({"file_path": "a_v002.py", "import_as": "b"}).summary()
        == "a_v002.py as b"
    )
    assert Script({"file_path": "a_v002.py"}).summary() == "a_v002.py"


def test_a_referenced_session_loads_scripts_from_its_own_folder(tmp_path):
    from maya import cmds

    _register_script()
    ref_dir = tmp_path / "base"
    (ref_dir / "scripts").mkdir(parents=True)
    (ref_dir / "scripts" / "base_lib_v001.py").write_text(
        "def mark():\n"
        "    from maya import cmds\n"
        "    cmds.createNode('transform', name='from_ref')\n",
        encoding="utf-8",
    )
    base = Document()
    base.add(
        ActionNode("lib", "script", settings={"file_path": "scripts/base_lib_v001.py"})
    )
    base.add(ActionNode("call", "script", settings={"code": "base_lib.mark()"}))
    base.save(ref_dir / "base_v001.tr")
    hero_dir = tmp_path / "hero"
    hero_dir.mkdir()
    hero = Document()
    hero.add(ActionNode("base", "reference", settings={"file": "../base/base_v001.tr"}))
    Runner().run(hero, str(hero_dir))
    assert cmds.objExists("from_ref")
