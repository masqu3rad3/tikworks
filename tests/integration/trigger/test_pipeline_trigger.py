"""End-to-end: guides -> session snapshot -> new scene -> restore -> actions build."""

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.core import ParentRef, get_module


@pytest.fixture
def backend():
    return trigger.maya_backend()


def _author_guides(backend):
    body = backend.create_guides(get_module("base")(name="body"))
    cmds.xform(backend.guide_node(body.instance_id, "root").long_name, ws=True, t=(0, 12, 0))
    tail = backend.create_guides(
        get_module("fkchain")(name="tail", side="L", settings={"segments": 3, "spacing": 3.0}),
        parent=ParentRef(body.instance_id, "root"),
    )
    cmds.xform(backend.guide_node(tail.instance_id, "segment", 2).long_name, ws=True, t=(9, 14, -2))
    return body, tail


def test_session_roundtrip_and_build(backend, tmp_path):
    body, tail = _author_guides(backend)
    session = trigger.RigSession(backend)
    session.snapshot_guides()
    session.add_action("kinematics")
    session.update_action_settings("kinematics", {"rig_name": "hero", "afterlife": "keep"})
    session.add_action("script")
    session.update_action_settings(
        "script", {"code": "import maya.cmds as cmds\ncmds.createNode('transform', name='from_script')"}
    )
    path = session.save(tmp_path / "hero")

    backend.new_scene()
    assert backend.find_instances() == []

    loaded = trigger.RigSession(backend, file_path=str(path))
    restored = loaded.restore_guides()
    assert [item.name for item in restored] == ["body", "tail"]
    assert restored[1].parent.instance_id == restored[0].instance_id
    tip = backend.guide_node(restored[1].instance_id, "segment", 2)
    assert tuple(round(value, 3) for value in tip.world_position) == (9.0, 14.0, -2.0)

    executed = loaded.run_all()
    assert executed == ["kinematics", "script"]
    assert cmds.objExists("hero_rig") and cmds.objExists("from_script")
    assert cmds.objExists("L_tail_3_jnt")
    assert tm.Joint("L_tail_3_jnt").world_position.x == pytest.approx(9.0, abs=1e-3)
    assert cmds.objExists("trigger_guides_grp")


def test_run_until_and_reset(backend, tmp_path):
    _author_guides(backend)
    session = trigger.RigSession(backend)
    session.snapshot_guides()
    session.add_action("script", name="first")
    session.update_action_settings("first", {"code": "ctx.log('hello')"})
    session.add_action("script", name="second")
    session.update_action_settings("second", {"code": "raise RuntimeError('never')"})
    assert session.run_all(until="first") == ["first"]
    session.restore_guides(clear_existing=True)
    assert len(backend.find_instances()) == 2
