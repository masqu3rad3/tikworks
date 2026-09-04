"""Runner: order, nesting, until/only, references, overrides, cycles."""

import pytest

from tik.core.fields import FileField
from tik.trigger.core import (
    Action,
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
