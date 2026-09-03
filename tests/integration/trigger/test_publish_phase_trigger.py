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
    # publishing is an act of the top-level session: the base rig this one
    # consumes does not get to decide what gets exported
    assert not cmds.objExists("base_publish")


def test_the_publish_list_survives_a_save_and_reopen(tmp_path):
    _session(tmp_path)
    reopened = trigger.Session.open(str(tmp_path / "hero.tr"))
    assert reopened.paths() == ["build_a", "build_b"]
    assert reopened.publish.paths() == ["export_fbx", "export_maya"]
    reopened.build(publish=True)
    assert cmds.objExists("export_maya")
