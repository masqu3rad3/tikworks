"""Author guides in the Designer, then build them from a session action."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.guides import GuideScene
from tik.trigger.session import Session


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def author_base_and_arm():
    """What the Designer leaves behind: a base with an arm connected to it."""
    scene = GuideScene()
    body = scene.add("base", side="C", name="body")
    arm = scene.add("arm", side="L", name="arm", parent=body)
    return scene, body, arm


def test_building_an_unsaved_session_uses_the_guides_in_the_scene():
    """The build must not lag the viewport any more than the file does."""
    author_base_and_arm()
    session = Session()
    session.add("kinematics", rig_name="hero")
    session.build()
    assert cmds.objExists("hero_rig")


def test_building_a_saved_session_builds_both_modules(tmp_path):
    _scene, _body, _arm = author_base_and_arm()
    session = Session()
    session.add("kinematics", rig_name="hero")
    session.save(tmp_path / "hero.tr")
    session.build()
    assert cmds.objExists("hero_rig")


def test_the_arm_survives_the_round_trip_through_the_document(tmp_path):
    """The failure was in the arm, so assert its rig actually appears."""
    _scene, _body, arm = author_base_and_arm()
    session = Session()
    session.add("kinematics", rig_name="hero", after_build="keep")
    session.save(tmp_path / "hero.tr")
    session.build()
    built = cmds.ls("*arm*", long=True) or []
    assert any("hero_rig" in name for name in built), built


def test_posed_guides_survive_the_round_trip(tmp_path):
    """Closer to real use: the guides get moved before the rig is built."""
    scene, body, arm = author_base_and_arm()
    cmds.xform(scene.guide_nodes(arm.instance_id)[("shoulder", 0)].long_name,
               worldSpace=True, translation=(5.0, 14.0, 0.0))
    cmds.xform(scene.guide_nodes(arm.instance_id)[("elbow", 0)].long_name,
               worldSpace=True, translation=(9.0, 14.0, -1.0))
    scene.sync()
    session = Session()
    session.add("kinematics", rig_name="hero")
    session.save(tmp_path / "hero.tr")
    session.build()
    assert cmds.objExists("hero_rig")


def test_a_designer_test_build_first_does_not_break_the_session_build(tmp_path):
    """The reported flow: test build in the Designer, then build the session."""
    scene, body, arm = author_base_and_arm()
    scene.test_build()
    session = Session()
    session.add("kinematics", rig_name="hero")
    session.save(tmp_path / "hero.tr")
    session.build()
    assert cmds.objExists("hero_rig")


def test_connecting_in_the_designer_then_building(tmp_path):
    """The arm is wired after both modules exist, as the graph does it."""
    scene = GuideScene()
    body = scene.add("base", side="C", name="body")
    arm = scene.add("arm", side="L", name="arm")
    scene.connect(f"{arm.key}.root", f"{body.key}.root")
    session = Session()
    session.add("kinematics", rig_name="hero")
    session.save(tmp_path / "hero.tr")
    session.build()
    assert cmds.objExists("hero_rig")


def test_building_the_same_session_twice(tmp_path):
    author_base_and_arm()
    session = Session()
    session.add("kinematics", rig_name="hero")
    session.save(tmp_path / "hero.tr")
    session.build()
    session.build()
    assert cmds.objExists("hero_rig")


def test_reopening_a_saved_session_and_building_in_a_fresh_scene(tmp_path):
    """Nothing in the scene to fall back on: the document is all there is."""
    author_base_and_arm()
    session = Session()
    session.add("kinematics", rig_name="hero")
    path = session.save(tmp_path / "hero.tr")
    cmds.file(new=True, force=True)
    reopened = Session.open(str(path))
    reopened.build()
    assert cmds.objExists("hero_rig")
