"""Tests for Joint chain/orient/mirror helpers and Transform alignment."""

from maya import cmds

import tik.maya as tm


def test_chain_creates_parented_joints():
    joints = tm.Joint.chain([(0, 0, 0), (1, 0, 0), (2, 0, 0)], name_pattern="c_{index}")
    assert [jnt.name for jnt in joints] == ["c_0", "c_1", "c_2"]
    assert joints[1].parent.name == "c_0"
    assert abs(joints[2].world_translation.x - 2) < 1e-6


def test_orient_chain_aims_x_down_chain():
    joints = tm.Joint.chain([(0, 0, 0), (0, 2, 0), (0, 4, 0)], orient=False)
    tm.Joint.orient_chain(joints)
    assert abs(joints[1].translate.x - 2) < 1e-4
    assert abs(joints[1].translate.y) < 1e-4
    assert joints[-1].joint_orient == (0.0, 0.0, 0.0)


def test_joint_orient_property():
    joint = tm.Joint.create(name="jnt")
    joint.joint_orient = (10, 20, 30)
    assert all(
        abs(actual - expected) < 1e-6
        for actual, expected in zip(joint.joint_orient, (10.0, 20.0, 30.0))
    )


def test_mirror_joint():
    joints = tm.Joint.chain([(1, 0, 0), (2, 0, 0)], name_pattern="L_j{index}")
    mirrored = joints[0].mirror(mirror_axis="x", search="L_", replace="R_")
    assert mirrored.name == "R_j0"
    assert abs(mirrored.world_translation.x + 1) < 1e-6
    assert cmds.objExists("R_j1")


def test_transform_world_position_and_distance():
    first = tm.Transform.create(name="a")
    second = tm.Transform.create(name="b")
    second.world_position = (3, 4, 0)
    assert abs(first.distance_to(second) - 5.0) < 1e-6
    mid = tm.Transform.between(first, second)
    assert abs(mid.x - 1.5) < 1e-6 and abs(mid.y - 2.0) < 1e-6


def test_world_position_under_parent():
    parent = tm.Transform.create(name="parent")
    parent.translate = (10, 0, 0)
    child = tm.Transform.create(name="child", parent=parent.name)
    child.world_position = (12, 0, 0)
    assert abs(child.translate.x - 2) < 1e-6


def test_aim_at():
    first = tm.Transform.create(name="a")
    target = tm.Transform.create(name="b")
    target.translate = (0, 0, 5)
    first.aim_at(target, aim_vector=(1, 0, 0), up_vector=(0, 1, 0))
    assert abs(first.rotate.y + 90) < 1e-3
    assert not cmds.ls(type="aimConstraint")


def test_align_to():
    first = tm.Transform.create(name="a")
    target = tm.Transform.create(name="b")
    target.translate = (1, 2, 3)
    target.rotate = (0, 45, 0)
    first.align_to(target)
    assert abs(first.translate.x - 1) < 1e-6
    assert abs(first.rotate.y - 45) < 1e-4
