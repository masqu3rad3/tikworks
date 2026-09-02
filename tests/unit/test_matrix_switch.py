"""Tests for the MatrixSwitch construct."""

from maya import cmds

import tik.maya as tm
from tik.maya.constructs.matrix_switch import WORLD, MatrixSwitch


def _setup():
    first = tm.Transform.create(name="first")
    second = tm.Transform.create(name="second")
    second.translate = (10, 0, 0)
    driven = tm.Transform.create(name="driven")
    return first, second, driven


def test_default_control_created_on_driven():
    first, second, driven = _setup()
    switch = MatrixSwitch.create([first, second], driven, maintain_offset=False)
    assert switch.control.attr == "switch"
    assert switch.control.node.name == "driven"
    assert len(switch.targets) == 2


def test_switch_selects_driver():
    first, second, driven = _setup()
    switch = MatrixSwitch.create([first, second], driven, maintain_offset=False)
    assert abs(driven.world_translation.x) < 1e-6
    switch.control.value = 1
    assert abs(driven.world_translation.x - 10) < 1e-6
    first.translate = (0, 3, 0)
    switch.control.value = 0
    assert abs(driven.world_translation.y - 3) < 1e-6


def test_maintain_offset_per_target():
    first, second, driven = _setup()
    driven.translate = (1, 1, 0)
    switch = MatrixSwitch.create([first, second], driven, maintain_offset=True)
    assert abs(driven.world_translation.x - 1) < 1e-6
    switch.control.value = 1
    assert abs(driven.world_translation.x - 1) < 1e-6
    second.translate = (11, 0, 0)
    assert abs(driven.world_translation.x - 2) < 1e-6


def test_world_target_is_static():
    first, second, driven = _setup()
    driven.translate = (4, 0, 0)
    switch = MatrixSwitch.create([WORLD, first], driven)
    first.translate = (99, 0, 0)
    assert abs(driven.world_translation.x - 4) < 1e-6
    switch.control.value = 1
    assert abs(driven.world_translation.x - 103) < 1e-6


def test_external_control_plug():
    first, second, driven = _setup()
    holder = tm.Transform.create(name="holder")
    control = tm.attribute.add_enum(holder, "which", ["a", "b"])
    switch = MatrixSwitch.create([first, second], driven, control=control, maintain_offset=False)
    assert switch.control.path == "holder.which"
    control.value = 1
    assert abs(driven.world_translation.x - 10) < 1e-6


def test_delete_removes_network():
    first, second, driven = _setup()
    switch = MatrixSwitch.create([first, second], driven, name="sw")
    switch.delete()
    assert not cmds.ls(type="blendMatrix")
    assert not cmds.ls(type="condition")
    assert not cmds.objExists("sw_multMatrix")
