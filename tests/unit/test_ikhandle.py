"""Tests for the IkHandle type wrapper."""

import tik.maya as tm
from tik.maya.types.ikhandle import IkHandle


def _chain():
    return tm.Joint.chain([(0, 0, 0), (2, 0, -1), (4, 0, 0)], name_pattern="ik_{index}")


def test_create_rp_handle():
    joints = _chain()
    handle = IkHandle.create(joints[0], joints[-1], name="arm_ikh")
    assert handle.type == "ikHandle"
    assert handle.name == "arm_ikh"
    assert handle.solver == "ikRPsolver"
    assert handle.start_joint.name == joints[0].name
    assert handle.end_effector.type == "ikEffector"


def test_create_sc_handle_and_export():
    joints = _chain()
    handle = tm.IkHandle.create(joints[0], joints[-1], solver="ikSCsolver")
    assert handle.solver == "ikSCsolver"


def test_pole_vector():
    joints = _chain()
    handle = IkHandle.create(joints[0], joints[-1], solver="ikRPsolver")
    pole = tm.Transform.create(name="pole")
    pole.translate = (2, 0, -5)
    constraint = handle.pole_vector(pole)
    assert constraint.type == "poleVectorConstraint"


def test_moving_handle_moves_chain():
    joints = _chain()
    handle = IkHandle.create(joints[0], joints[-1])
    handle.translate = (3, 1, 0)
    end_pos = joints[-1].world_translation
    assert abs(end_pos.x - 3) < 1e-3 and abs(end_pos.y - 1) < 1e-3
