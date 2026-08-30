"""Session / ActionHandle API (no Maya)."""

import pytest
from maya import cmds

from tik.core.fields import FieldValidationError, FileField
from tik.trigger.core import Action, IntField, StringField, clear_registries, register_action
from tik.trigger.core.exceptions import SessionError, SessionSaveError
from tik.trigger.handler import Session


CALLS: list = []


class Mark(Action):
    tag = StringField("")
    amount = IntField(1, min=0)

    def run(self, ctx):
        CALLS.append(("mark", ctx.path, self.tag, self.amount))


class Weights(Action):
    file = FileField("", extensions=[".trw"])

    def run(self, ctx):
        CALLS.append(("weights", ctx.path, self.file))


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_action("mark", category="build")(Mark)
    register_action("weights", category="deform")(Weights)
    from tik.trigger.actions.reference.reference import Reference

    register_action("reference", category="structure")(Reference)
    yield
    clear_registries()


def test_add_nest_after_and_attribute_settings():
    rig = Session()
    imp = rig.add("mark", "import", tag="IMP")
    rig.add("mark", "rename", parent=imp, tag="REN")
    kin = rig.add("mark", "kinematics", tag="KIN")
    rig.add("mark", "shapes", after=imp, tag="SHP")
    assert rig.paths() == ["import", "import/rename", "shapes", "kinematics"]
    assert rig["import/rename"].tag == "REN"
    kin.amount = 3
    assert rig["kinematics"].settings == {"tag": "KIN", "amount": 3}
    with pytest.raises(FieldValidationError):
        kin.amount = -1
    with pytest.raises(AttributeError):
        kin.nope = 1
    with pytest.raises(FieldValidationError):
        rig.add("mark", amount=-5)
    assert rig.is_modified
    assert repr(kin).startswith("<Action kinematics")


def test_tree_edits_and_run():
    CALLS.clear()
    rig = Session()
    rig.add("mark", "a", tag="A")
    rig.add("mark", "b", tag="B")
    rig.add("mark", "c", tag="C")
    rig.move("c", index=0)
    assert rig.paths() == ["c", "a", "b"]
    rig.move("a", after="b")
    assert rig.paths() == ["c", "b", "a"]
    rig.move("b", parent="c")
    assert rig.paths() == ["c", "c/b", "a"]
    rig.rename("c", "root")
    assert "root/b" in rig
    dup = rig.duplicate("root")
    assert dup.path == "root1" and "root1/b" in rig
    rig.remove(dup)
    rig["root/b"].enabled = False
    leftover = cmds.spaceLocator(name="stale_from_a_previous_build")[0]
    results = rig.build()
    assert [item.path for item in results] == ["root", "a"]
    # build() starts from a fresh scene, so anything left over is gone
    assert not cmds.objExists(leftover)
    kept = cmds.spaceLocator(name="built_by_an_earlier_step")[0]
    rig.run("a")
    marks = [call for call in CALLS if call[0] == "mark"]
    # running one action is not a rebuild, so the scene survives
    assert marks[-1][1] == "a" and cmds.objExists(kept)
    assert [step.path for step in rig.steps(until="root")] == ["root"]
    assert Session().build() == []  # an empty session builds nothing


def test_save_open_increment(tmp_path):
    rig = Session()
    rig.add("mark", "a")
    with pytest.raises(SessionSaveError):
        rig.save()
    path = rig.save(tmp_path / "hero")
    assert path.name == "hero.tr" and not rig.is_modified
    assert rig.directory == str(tmp_path)
    inc = rig.increment()
    assert inc.name == "hero_v001.tr"
    assert rig.increment().name == "hero_v002.tr"
    other = Session.open(str(inc))
    assert other.paths() == ["a"] and other.name == "hero_v001.tr"
    other.new()
    assert other.file_path is None and other.actions == []


def test_reference_handles_and_overrides(tmp_path):
    base = Session()
    base.add("mark", "kinematics", tag="KIN")
    scripts = base.add("mark", "scripts", tag="S")
    scripts.add("mark", "head_rotation", tag="HEAD")
    scripts.add("mark", "fingers", tag="FING")
    (tmp_path / "rigs").mkdir()
    base.save(tmp_path / "rigs" / "baseRig_v001.tr")

    CALLS.clear()
    rig = Session()
    rig.save(tmp_path / "hero.tr")
    ref = rig.add("reference", "base", file="rigs/baseRig_v001.tr")
    linked = ref["scripts/head_rotation"]
    assert linked.is_linked and linked.enabled and linked.tag == "HEAD"
    linked.enabled = False
    ref["kinematics"].tag = "KIN-OVERRIDE"
    assert ref.node.settings["overrides"] == {
        "scripts/head_rotation": {"enabled": False},
        "kinematics": {"settings": {"tag": "KIN-OVERRIDE"}},
    }
    assert ref["kinematics"].tag == "KIN-OVERRIDE" and not linked.enabled
    assert [handle.path for handle in ref.children] == ["base/kinematics", "base/scripts"]
    assert [handle.path for handle in rig.walk()] == [
        "base", "base/kinematics", "base/scripts", "base/scripts/head_rotation", "base/scripts/fingers",
    ]
    with pytest.raises(SessionError):
        linked.add("mark")
    (tmp_path / "hero.trw").write_text("{}")
    rig.add("weights", "w", file="hero.trw")
    rig.build()
    tags = [call[2] for call in CALLS if call[0] == "mark"]
    assert tags == ["KIN-OVERRIDE", "S", "FING"]
    ref["kinematics"].reset("tag")
    assert ref["kinematics"].tag == "KIN"
    linked.reset()
    assert linked.enabled
    # missing referenced file: handle still usable, children empty, validate reports it
    ref.file = "rigs/missing.tr"
    assert ref.children == []
    assert any("not found" in problem for problem in rig.validate())
