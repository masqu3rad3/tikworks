"""The rebuild story: author guides, export .trg, build from files twice."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.guides import GuideScene


@pytest.fixture
def scene():
    return GuideScene()


def _all_modules(session) -> list:
    """Every module id in ``session``: the scope a whole-rig build names."""
    return [entry.instance_id for entry in session.document.guides.modules]


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
    rig.guides.import_(tmp_path / "guides" / "hero_guides.trg")
    rig.add("import_asset", "import_model", file_path="geo/hero_model.ma")
    rig.add(
        "kinematics",
        modules=_all_modules(rig),
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


def test_kinematics_builds_only_what_it_names(scene, tmp_path):
    """The scope is the list. Everything else stays out of the rig."""
    guides_path = _author(scene, tmp_path)

    rig = trigger.Session()
    rig.guides.import_(guides_path)
    body = rig.guides.find("body")
    arm = rig.guides.find("arm", side="L")
    rig.add("kinematics", modules=[body.instance_id, arm.instance_id])
    rig.build()
    assert cmds.objExists("C_body_grp") and cmds.objExists("L_arm_grp")
    assert not cmds.objExists("C_tail_grp")

    # a different subset: the tail needs its producer, so name that too --
    # naming a consumer without its source is an error, not a silent skip
    cmds.file(new=True, force=True)
    rig = trigger.Session()
    rig.guides.import_(guides_path)
    body = rig.guides.find("body")
    tail = rig.guides.find("tail")
    rig.add("kinematics", modules=[body.instance_id, tail.instance_id])
    rig.build()
    assert cmds.objExists("C_tail_grp") and not cmds.objExists("L_arm_grp")


def test_kinematics_builds_from_the_sessions_own_guides():
    """No guides file: the rig description is self-contained."""
    from tik.trigger.session import Session

    trigger.load_plugins()
    cmds.file(new=True, force=True)
    session = Session()
    session.guides.add("base", side="C", name="body")
    session.add("kinematics", modules=_all_modules(session))
    session.build()
    assert cmds.objExists("rig_grp")


def test_kinematics_naming_nothing_reports_clearly():
    from tik.trigger.core.exceptions import ActionExecutionError
    from tik.trigger.session import Session

    trigger.load_plugins()
    cmds.file(new=True, force=True)
    session = Session()
    session.add("kinematics")
    with pytest.raises(ActionExecutionError, match="names no modules"):
        session.build()


# ------------------------------------------------------------ import model
def _model_file(tmp_path):
    model = tmp_path / "geo" / "hero_model.ma"
    cmds.file(new=True, force=True)
    cmds.polySphere(name="hero_geo")
    cmds.polyCube(name="prop_geo")
    model.parent.mkdir(exist_ok=True)
    cmds.file(rename=str(model))
    cmds.file(save=True, type="mayaAscii", force=True)
    return model


def test_import_model_parents_under_geo_grp(tmp_path):
    _model_file(tmp_path)
    rig = trigger.Session()
    rig.save(tmp_path / "hero.tr")
    rig.add("import_asset", "import_model", file_path="geo/hero_model.ma")
    rig.build()
    assert cmds.ls("hero_geo", long=True) == ["|rig_grp|geo_grp|hero_geo"]
    assert cmds.ls("prop_geo", long=True) == ["|rig_grp|geo_grp|prop_geo"]


def test_import_model_can_leave_geometry_at_world(tmp_path):
    _model_file(tmp_path)
    rig = trigger.Session()
    rig.save(tmp_path / "hero.tr")
    rig.add(
        "import_asset",
        "import_model",
        file_path="geo/hero_model.ma",
        parent_to_geo=False,
    )
    rig.build()
    assert cmds.ls("hero_geo", long=True) == ["|hero_geo"]


def test_referenced_model_is_parented_too(tmp_path):
    _model_file(tmp_path)
    rig = trigger.Session()
    rig.save(tmp_path / "hero.tr")
    rig.add(
        "import_asset",
        "import_model",
        file_path="geo/hero_model.ma",
        reference=True,
        namespace="model",
    )
    rig.build()
    assert cmds.ls("model:hero_geo", long=True) == ["|rig_grp|geo_grp|model:hero_geo"]
