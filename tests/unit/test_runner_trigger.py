"""Runner: order, nesting, until/only, references, overrides, cycles (no Maya)."""

import json

import pytest

from trigger_fakes import FakeBackend
from tik.trigger.core import Action, EventBus, IntField, StringField, clear_registries, register_action
from tik.trigger.core.document import ActionNode, Document
from tik.trigger.core.exceptions import ActionExecutionError, SessionError
from tik.trigger.core.runner import STEP_FAILED, STEP_FINISHED, Runner
from tik.core.fields import FileField


class Mark(Action):
    label = "Mark"
    tag = StringField("")
    amount = IntField(1)

    def run(self, ctx):
        ctx.backend.calls.append(("mark", ctx.path, self.tag, self.amount, ctx.base_dir))


class Boom(Action):
    def run(self, ctx):
        raise RuntimeError("boom")


class NeedsFile(Action):
    file = FileField("", extensions=[".txt"])

    def run(self, ctx):
        ctx.backend.calls.append(("file", str(ctx.resolve(self.file))))


@pytest.fixture(autouse=True)
def _registered():
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


def _marks(backend):
    return [call[1] for call in backend.calls if call[0] == "mark"]


def test_depth_first_order_and_disabled_subtree():
    backend = FakeBackend()
    results = Runner(backend).run(_doc(), "D:/x")
    assert _marks(backend) == ["a", "a/a1", "a/a2", "b", "c"]
    assert [item.status for item in results] == ["done"] * 5
    assert backend.calls[0] == ("new_scene",)
    assert ("undo_open", "Trigger: a/a1") in backend.calls


def test_until_and_only():
    backend = FakeBackend()
    Runner(backend).run(_doc(), until="a/a2")
    assert _marks(backend) == ["a", "a/a1", "a/a2"]
    backend = FakeBackend()
    Runner(backend).run(_doc(), only="b")
    assert _marks(backend) == ["b"] and ("new_scene",) not in backend.calls
    with pytest.raises(SessionError):
        Runner(FakeBackend()).plan(_doc(), until="ghost")
    with pytest.raises(SessionError):
        Runner(FakeBackend()).plan(_doc(), only="off")  # disabled = not runnable


def test_events_and_failure_wraps():
    backend = FakeBackend()
    doc = _doc()
    doc.add(ActionNode("bad", "boom"), index=1)
    events = EventBus()
    finished, failed = [], []
    events.subscribe(STEP_FINISHED, lambda **kw: finished.append(kw["path"]))
    events.subscribe(STEP_FAILED, lambda **kw: failed.append(kw["path"]))
    with pytest.raises(ActionExecutionError) as info:
        Runner(backend, events).run(doc)
    assert finished == ["a", "a/a1", "a/a2"] and failed == ["bad"]
    assert info.value.action_name == "bad"
    assert _marks(backend) == ["a", "a/a1", "a/a2"]


def test_validation_blocks_missing_file(tmp_path):
    doc = Document()
    doc.add(ActionNode("f", "needs_file", settings={"file": "missing.txt"}))
    with pytest.raises(ActionExecutionError) as info:
        Runner(FakeBackend()).run(doc, str(tmp_path))
    assert "file not found" in str(info.value)
    (tmp_path / "there.txt").write_text("x")
    doc.find("f").settings["file"] = "there.txt"
    backend = FakeBackend()
    Runner(backend).run(doc, str(tmp_path))
    assert ("file", str(tmp_path / "there.txt")) in backend.calls


def _write_base(tmp_path, name="baseRig_v001.tr"):
    base = Document()
    base.add(ActionNode("kinematics", "mark", settings={"tag": "KIN"}))
    base.add(ActionNode("scripts", "mark", settings={"tag": "S"}))
    base.add(ActionNode("head_rotation", "mark", settings={"tag": "HEAD"}), parent="scripts")
    base.add(ActionNode("fingers", "mark", settings={"tag": "FING"}), parent="scripts")
    rigs = tmp_path / "rigs"
    rigs.mkdir(exist_ok=True)
    return base.save(rigs / name)


def test_reference_expands_with_overrides_and_relative_paths(tmp_path):
    _write_base(tmp_path)
    _write_base(tmp_path, "baseRig_v002.tr")
    doc = Document()
    doc.add(ActionNode("import", "mark", settings={"tag": "IMP"}))
    ref = ActionNode("base", "reference", settings={
        "file": "rigs/baseRig_v001.tr", "version": "latest",
        "overrides": {"scripts/head_rotation": {"enabled": False},
                      "kinematics": {"settings": {"tag": "KIN-OVERRIDE"}}},
    })
    doc.add(ref)
    doc.add(ActionNode("local_child", "mark", settings={"tag": "LOCAL"}), parent="base")
    doc.add(ActionNode("weights", "mark", settings={"tag": "W"}))
    backend = FakeBackend()
    plan = Runner(backend).plan(doc, str(tmp_path))
    assert [step.path for step in plan.steps] == [
        "import", "base/kinematics", "base/scripts", "base/scripts/fingers", "base/local_child", "weights",
    ]
    kin = next(step for step in plan.steps if step.path == "base/kinematics")
    assert kin.linked and kin.base_dir == str(tmp_path / "rigs")
    assert kin.chain[0].endswith("baseRig_v002.tr")  # latest resolved
    assert kin.node.settings["tag"] == "KIN-OVERRIDE"
    Runner(backend).run(doc, str(tmp_path))
    tags = [call[2] for call in backend.calls if call[0] == "mark"]
    assert tags == ["IMP", "KIN-OVERRIDE", "S", "FING", "LOCAL", "W"]


def test_reference_include_and_missing_and_cycle(tmp_path):
    base_path = _write_base(tmp_path)
    doc = Document()
    doc.add(ActionNode("base", "reference", settings={"file": str(base_path), "version": "pinned", "include": ["scripts/fingers"]}))
    plan = Runner(FakeBackend()).plan(doc, str(tmp_path))
    assert [step.path for step in plan.steps] == ["base/scripts", "base/scripts/fingers"]

    doc = Document()
    doc.add(ActionNode("base", "reference", settings={"file": "rigs/nope.tr"}))
    with pytest.raises(SessionError):
        Runner(FakeBackend()).plan(doc, str(tmp_path))

    # cycle: a.tr references b.tr which references a.tr
    a_doc, b_doc = Document(), Document()
    a_doc.add(ActionNode("to_b", "reference", settings={"file": "b.tr", "version": "pinned"}))
    b_doc.add(ActionNode("to_a", "reference", settings={"file": "a.tr", "version": "pinned"}))
    a_doc.save(tmp_path / "a.tr")
    b_doc.save(tmp_path / "b.tr")
    doc = Document()
    doc.add(ActionNode("root", "reference", settings={"file": "a.tr", "version": "pinned"}))
    with pytest.raises(SessionError) as info:
        Runner(FakeBackend()).plan(doc, str(tmp_path))
    assert "cycle" in str(info.value)
