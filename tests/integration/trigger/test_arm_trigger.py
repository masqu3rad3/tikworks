"""Arm module: build on top of base, exercise IK/FK and ribbons."""

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.core import Builder, ParentRef, get_module


@pytest.fixture
def backend():
    return trigger.maya_backend()


def _build_arm(backend, side="L", **settings):
    body = backend.create_guides(get_module("base")(name="body"))
    cmds.xform(backend.guide_node(body.instance_id, "root").long_name, ws=True, t=(0, 15, 0))
    arm = backend.create_guides(
        get_module("arm")(name="arm", side=side, settings=settings), parent=ParentRef(body.instance_id, "root")
    )
    for role, position in (("collar", (2, 15, 0)), ("shoulder", (5, 15, 0)), ("elbow", (9, 15, -1)), ("hand", (14, 15, 0))):
        mult = -1 if side == "R" else 1
        cmds.xform(backend.guide_node(arm.instance_id, role).long_name, ws=True, t=(position[0] * mult, position[1], position[2]))
    report = Builder(backend).build(rig_name="hero", afterlife="delete")
    return report, arm


def test_arm_builds_expected_nodes(backend):
    report, arm = _build_arm(backend, ribbon_joints=4)
    ctx = report.contexts[arm.instance_id]
    assert set(ctx.outputs) == {"collar", "shoulder", "elbow", "hand"}
    assert list(ctx.attachments) == ["root"]
    assert len(ctx.deform_joints) == 1 + 4 + 4 + 1
    for name in (
        "L_arm_collar_ctrl", "L_arm_fk_upArm_ctrl", "L_arm_fk_lowArm_ctrl", "L_arm_fk_hand_ctrl",
        "L_arm_ik_hand_ctrl", "L_arm_ik_pole_ctrl", "L_arm_switch_ctrl", "L_arm_hand_jnt",
        "L_arm_upArm_ribbon_grp", "L_arm_lowArm_ribbon_grp",
    ):
        assert cmds.objExists(name), name
    assert cmds.attributeQuery("ikFk", node="L_arm_switch_ctrl", exists=True)
    assert not cmds.objExists("trigger_guides_grp")


def test_arm_attaches_to_base_and_follows(backend):
    report, arm = _build_arm(backend)
    hand = tm.Joint("L_arm_hand_jnt")
    before = hand.world_position
    tm.Transform("C_body_root_ctrl").translate = (0, 20, 0)
    assert hand.world_position.y == pytest.approx(before.y + 5, abs=1e-3)


def test_arm_ik_fk_switch(backend):
    report, arm = _build_arm(backend)
    switch = tm.Transform("L_arm_switch_ctrl")["ikFk"]
    hand = tm.Joint("L_arm_hand_jnt")
    ik_ctrl = tm.Transform("L_arm_ik_hand_ctrl")
    switch.value = 1.0
    ik_ctrl.world_position = ik_ctrl.world_position + type(ik_ctrl.world_position)(0, 0, 1.5)
    assert hand.world_position.z == pytest.approx(1.5, abs=1e-2)
    assert tm.Transform("L_arm_fk_upArm_offset").visibility is False
    switch.value = 0.0
    assert hand.world_position.z == pytest.approx(0.0, abs=1e-2)
    fk = tm.Transform("L_arm_fk_upArm_ctrl")
    fk.rotate = (0, 0, -45)
    assert abs(hand.world_position.y - 15.0) > 1.0
    assert tm.Transform("L_arm_ik_grp").visibility is False


def test_arm_right_side_mirrors(backend):
    report, arm = _build_arm(backend, side="R")
    assert cmds.objExists("R_arm_hand_jnt")
    assert tm.Joint("R_arm_hand_jnt").world_position.x < 0
    assert tm.Transform("R_arm_ik_hand_ctrl").color == 13


def test_arm_ribbon_stretch_and_undo(backend):
    report, arm = _build_arm(backend, ribbon_joints=3, stretchy=True)
    joint = tm.Joint("L_arm_lowArm_0_jnt")
    assert joint["scaleX"].value == pytest.approx(1.0, abs=1e-3)
    tm.Transform("L_arm_ik_hand_ctrl").translate = tuple(
        value + offset for value, offset in zip(tm.Transform("L_arm_ik_hand_ctrl").translate, (3, 0, 0))
    )
    assert joint["scaleX"].value > 1.0
    cmds.undo()
    cmds.undo()
    assert not cmds.objExists("hero_rig")
