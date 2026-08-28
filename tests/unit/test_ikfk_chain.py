"""Tests for the IkFkChain construct."""

from maya import cmds

import tik.maya as tm
from tik.maya.constructs.ikfk_chain import IkFkChain


def _chain():
    return tm.Joint.chain([(0, 0, 0), (3, 0, -1), (6, 0, 0)], name_pattern="arm_{index}")


def test_creates_duplicate_chains_and_switch():
    joints = _chain()
    chain = IkFkChain.create(joints, name="arm")
    assert len(chain.ik_joints) == 3 and len(chain.fk_joints) == 3
    assert chain.ik_handle.type == "ikHandle"
    assert chain.switch.attr == "ikFk"
    assert chain.switch.value == 1.0
    assert chain.ik_joints[1].parent.name == chain.ik_joints[0].name
    assert chain.fk_joints[0].parent.name == chain.group.name


def test_copies_match_original_positions():
    joints = _chain()
    chain = IkFkChain.create(joints, name="arm")
    for source, ik_joint, fk_joint in zip(joints, chain.ik_joints, chain.fk_joints):
        assert (source.world_translation - ik_joint.world_translation).length() < 1e-5
        assert (source.world_translation - fk_joint.world_translation).length() < 1e-5


def test_fk_drives_when_switch_zero():
    joints = _chain()
    chain = IkFkChain.create(joints, name="arm")
    chain.switch.value = 0.0
    chain.fk_joints[0].rotate = (0, 0, 45)
    assert abs(joints[0].rotate.z - 45) < 1e-4
    assert (joints[1].world_translation - chain.fk_joints[1].world_translation).length() < 1e-4


def test_ik_drives_when_switch_one():
    joints = _chain()
    chain = IkFkChain.create(joints, name="arm")
    chain.switch.value = 1.0
    chain.ik_handle.translate = (4, 2, 0)
    end = joints[-1].world_translation
    assert abs(end.x - 4) < 1e-3 and abs(end.y - 2) < 1e-3


def test_visibility_plugs_are_inverse():
    joints = _chain()
    chain = IkFkChain.create(joints, name="arm")
    chain.switch.value = 0.25
    assert abs(chain.ik_visibility.value - 0.25) < 1e-6
    assert abs(chain.fk_visibility.value - 0.75) < 1e-6


def test_external_switch_and_parented_root():
    holder = tm.Transform.create(name="holder")
    switch = tm.attribute.add_float(holder, "blend", default=0.0, min=0.0, max=1.0)
    root_parent = tm.Transform.create(name="root_parent")
    root_parent.translate = (0, 5, 0)
    joints = tm.Joint.chain([(0, 5, 0), (3, 5, -1), (6, 5, 0)], name_pattern="leg_{index}", parent=root_parent)
    chain = IkFkChain.create(joints, name="leg", switch=switch, parent=root_parent)
    assert chain.switch.path == "holder.blend"
    assert abs(chain.group.world_translation.y - 5) < 1e-6
    assert (joints[0].world_translation - chain.ik_joints[0].world_translation).length() < 1e-5


def test_pole_vector_and_delete():
    joints = _chain()
    chain = IkFkChain.create(joints, name="arm")
    pole = tm.Transform.create(name="pole")
    pole.translate = (3, 0, -5)
    assert chain.pole_vector(pole).type == "poleVectorConstraint"
    chain.delete()
    assert not cmds.objExists("arm_ikfk_grp")
    assert not cmds.ls(type="blendMatrix")
    assert not cmds.listConnections(f"{joints[0].name}.t", source=True, destination=False)
