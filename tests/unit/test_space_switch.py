"""Tests for the SpaceSwitch construct."""

from maya import cmds

import tik.maya as tm
from tik.maya.constructs.space_switch import SpaceSwitch


def _setup():
    ctrl = tm.Transform.create(name="ctrl")
    ctrl.translate = (1, 0, 0)
    space_a = tm.Transform.create(name="A")
    space_b = tm.Transform.create(name="B")
    space_b.translate = (10, 0, 0)
    return ctrl, space_a, space_b


def test_creates_enum_and_offset():
    ctrl, space_a, space_b = _setup()
    switch = SpaceSwitch.create(ctrl, [space_a, space_b])
    assert switch.attr.attr == "space"
    assert cmds.attributeQuery("space", node=ctrl.name, listEnum=True) == ["world:A:B"]
    assert ctrl.parent.name == switch.offset.name
    assert switch.labels == ["world", "A", "B"]


def test_world_space_keeps_position():
    ctrl, space_a, space_b = _setup()
    SpaceSwitch.create(ctrl, [space_a, space_b])
    assert abs(ctrl.world_translation.x - 1) < 1e-6
    space_b.translate = (20, 0, 0)
    assert abs(ctrl.world_translation.x - 1) < 1e-6


def test_switching_follows_target_keeping_offset():
    ctrl, space_a, space_b = _setup()
    switch = SpaceSwitch.create(ctrl, [space_a, space_b])
    switch.attr.value = 2
    assert abs(ctrl.world_translation.x - 1) < 1e-6
    space_b.translate = (12, 0, 0)
    assert abs(ctrl.world_translation.x - 3) < 1e-6
    switch.attr.value = 1
    space_a.translate = (0, 5, 0)
    assert abs(ctrl.world_translation.y - 5) < 1e-6
    assert abs(ctrl.world_translation.x - 1) < 1e-6


def test_orient_mode_skips_translate():
    ctrl, space_a, space_b = _setup()
    switch = SpaceSwitch.create(ctrl, [space_a, space_b], mode="orient")
    switch.attr.value = 2
    space_b.translate = (50, 0, 0)
    assert abs(ctrl.world_translation.x - 1) < 1e-6
    space_b.rotate = (0, 0, 90)
    assert abs(switch.offset.rotate.z - 90) < 1e-4
    assert abs(ctrl.world_translation.x - 1) < 1e-6


def test_point_mode_skips_rotate():
    ctrl, space_a, space_b = _setup()
    switch = SpaceSwitch.create(ctrl, [space_a, space_b], mode="point")
    switch.attr.value = 2
    space_b.translate = (11, 0, 0)
    assert abs(ctrl.world_translation.x - 2) < 1e-6
    space_b.rotate = (0, 0, 90)
    assert abs(switch.offset.rotate.z) < 1e-6


def test_add_space_extends_enum():
    ctrl, space_a, space_b = _setup()
    switch = SpaceSwitch.create(ctrl, [space_a], labels=["a_space"])
    switch.add_space(space_b, label="hand")
    assert cmds.attributeQuery("space", node=ctrl.name, listEnum=True) == [
        "world:a_space:hand"
    ]
    switch.attr.value = 2
    space_b.translate = (15, 0, 0)
    assert abs(ctrl.world_translation.x - 6) < 1e-6


def test_control_on_other_node():
    ctrl, space_a, space_b = _setup()
    holder = tm.Transform.create(name="holder")
    switch = SpaceSwitch.create(ctrl, [space_a], control=holder, attr_name="follow")
    assert switch.attr.node.name == "holder"
    assert cmds.attributeQuery("follow", node="holder", exists=True)


def test_delete_restores_hierarchy():
    ctrl, space_a, space_b = _setup()
    switch = SpaceSwitch.create(ctrl, [space_a, space_b])
    switch.delete()
    assert ctrl.parent is None
    assert not cmds.attributeQuery("space", node=ctrl.name, exists=True)
    assert not cmds.ls(type="blendMatrix")


def test_world_can_be_excluded():
    """Nothing should appear in the enum that was not defined."""
    node = tm.Transform.create(name="switched_noworld")
    first = tm.Transform.create(name="target_a")
    second = tm.Transform.create(name="target_b")
    switch = tm.SpaceSwitch.create(
        node, [first, second], labels=["a", "b"], world=False, name="noworld"
    )
    assert switch.labels == ["a", "b"]


def test_world_is_included_by_default():
    node = tm.Transform.create(name="switched_default")
    target = tm.Transform.create(name="target_default")
    switch = tm.SpaceSwitch.create(node, [target], labels=["a"], name="withworld")
    assert switch.labels == ["world", "a"]
