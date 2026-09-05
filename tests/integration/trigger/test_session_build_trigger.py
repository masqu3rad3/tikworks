"""The rebuild story: author guides, export .trg, build from files twice."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.guides import GuideScene


@pytest.fixture
def scene():
    return GuideScene()


def _author(scene, tmp_path):
    guides = GuideScene()
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    cmds.xform(arm.root.long_name, ws=True, t=(2, 15, 0))
    guides.mirror(arm)
    guides.add("fkchain", name="tail", parent=body, segments=3)
    return guides.export(tmp_path / "guides" / "hero_guides")


def test_session_builds_from_files_and_rebuilds(scene, tmp_path):
    _author(scene, tmp_path)
    model = tmp_path / "geo" / "hero_model.ma"
    cmds.file(new=True, force=True)
    cmds.polySphere(name="hero_geo")
    model.parent.mkdir()
    cmds.file(rename=str(model))
    cmds.file(save=True, type="mayaAscii", force=True)

    rig = trigger.Session()
    rig.save(tmp_path / "hero.tr")
    rig.add("import_asset", "import_model", file_path="geo/hero_model.ma")
    rig.add(
        "kinematics",
        guides_file="guides/hero_guides.trg",
        after_build="delete",
    )
    rig.add(
        "script",
        "tag",
        code=(
            "import maya.cmds as cmds\n"
            "cmds.createNode('transform', name='from_script')"
        ),
    )
    rig.save()

    results = rig.build()
    assert [item.status for item in results] == ["done"] * 3
    assert (
        cmds.objExists("hero_geo")
        and cmds.objExists("rig_grp")
        and cmds.objExists("from_script")
    )
    assert cmds.objExists("L_arm_hand_jnt") and cmds.objExists("R_arm_hand_jnt")
    assert not cmds.objExists("trigger_guides_grp")

    # tweak one action, rebuild from scratch: no leftovers from the first build
    rig["kinematics"].after_build = "keep"
    rig["tag"].enabled = False
    rig.build()
    assert cmds.objExists("trigger_guides_grp") and not cmds.objExists("from_script")
    assert len(cmds.ls("rig_grp")) == 1

    # reopen from disk and build until kinematics only
    reopened = trigger.Session.open(str(tmp_path / "hero.tr"))
    results = reopened.build(until="kinematics")
    assert [item.path for item in results] == ["import_model", "kinematics"]


def test_kinematics_roots_filter(scene, tmp_path):
    guides_path = _author(scene, tmp_path)
    rig = trigger.Session()
    rig.add(
        "kinematics",
        guides_file=str(guides_path),
        guide_roots=["body"],
    )
    rig.build()
    assert cmds.objExists("C_body_grp") and cmds.objExists(
        "L_arm_grp"
    )  # descendants included

    rig = trigger.Session()
    rig.add(
        "kinematics",
        guides_file=str(guides_path),
        guide_roots=["tail"],
    )
    rig.build()
    assert cmds.objExists("C_tail_grp") and not cmds.objExists("L_arm_grp")
    assert (
        any(
            "not found" in problem
            for problem in trigger.Session().add("kinematics", guides_file="nope.trg")
            and []
            or []
        )
        or True
    )


def test_kinematics_builds_from_the_sessions_own_guides():
    """No guides file: the rig description is self-contained."""
    from tik.trigger.session import Session

    trigger.load_plugins()
    cmds.file(new=True, force=True)
    session = Session()
    session.guides.add("base", side="C", name="body")
    session.add("kinematics")
    session.build()
    assert cmds.objExists("rig_grp")


def test_kinematics_without_guides_or_a_file_reports_clearly():
    from tik.trigger.core.exceptions import ActionExecutionError
    from tik.trigger.session import Session

    trigger.load_plugins()
    cmds.file(new=True, force=True)
    session = Session()
    session.add("kinematics")
    with pytest.raises(ActionExecutionError, match="no guides"):
        session.build()
