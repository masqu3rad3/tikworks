"""Tests for Joint.preferred_angle, duplicate_chain and mirrored orientation."""

import tik.maya as tm


def _chain(name="arm"):
    return tm.Joint.chain(
        [(0, 0, 0), (4, 0, -1), (8, 0, 0)], name_pattern=name + "_{index}"
    )


def test_preferred_angle_round_trips():
    """Must hit the real Maya plug, not just a Python attribute."""
    joint = tm.Joint.create(name="single")
    joint.preferred_angle = (0.0, 0.0, -15.0)
    assert abs(joint["preferredAngleZ"].value - (-15.0)) < 1e-4
    joint["preferredAngleZ"].value = -40.0
    assert abs(joint.preferred_angle[2] - (-40.0)) < 1e-4


def test_duplicate_chain_matches_positions():
    joints = _chain()
    copies = tm.Joint.duplicate_chain(joints, prefix="arm_ik")
    assert len(copies) == 3
    assert copies[0].name == "arm_ik_0_jnt"
    for source, copy in zip(joints, copies):
        assert (source.world_translation - copy.world_translation).length() < 1e-5


def test_duplicate_chain_is_parented_as_a_chain():
    joints = _chain()
    parent = tm.Transform.create(name="chain_parent")
    copies = tm.Joint.duplicate_chain(joints, prefix="arm_fk", parent=parent)
    assert copies[0].parent.name == parent.name
    assert copies[1].parent.name == copies[0].name
    assert copies[2].parent.name == copies[1].name


def test_duplicate_chain_carries_preferred_angle_and_scale():
    joints = _chain()
    joints[1].preferred_angle = (0.0, 0.0, -20.0)
    joints[1].scale = (2.0, 2.0, 2.0)
    copies = tm.Joint.duplicate_chain(joints, prefix="arm_pa")
    assert abs(copies[1].preferred_angle[2] - (-20.0)) < 1e-4
    assert abs(copies[1].scale.x - 2.0) < 1e-5


def test_orient_chain_aims_x_down_the_chain():
    joints = _chain("plain")
    tm.Joint.orient_chain(joints)
    axis = joints[0].world_matrix_axis_x()
    to_child = joints[1].world_translation - joints[0].world_translation
    to_child.normalize()
    assert axis * to_child > 0.99


def test_reverse_aim_points_x_back_up_the_chain():
    joints = _chain("mirrored")
    tm.Joint.orient_chain(joints, reverse_aim=True, reverse_up=True)
    axis = joints[0].world_matrix_axis_x()
    to_child = joints[1].world_translation - joints[0].world_translation
    to_child.normalize()
    assert axis * to_child < -0.99


def test_reverse_aim_keeps_positions_and_negates_tx():
    """Mirrored behaviour must not move the joints; ChainLengths reads the sign."""
    joints = _chain("mirrored_tx")
    before = [tuple(joint.world_position) for joint in joints]
    tm.Joint.orient_chain(joints, reverse_aim=True, reverse_up=True)
    for joint, position in zip(joints, before):
        assert abs(joint.world_position[0] - position[0]) < 1e-4
        assert abs(joint.world_position[1] - position[1]) < 1e-4
        assert abs(joint.world_position[2] - position[2]) < 1e-4
    assert joints[1].translate.x < 0
    assert joints[2].translate.x < 0
