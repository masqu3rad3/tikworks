"""Tests for the AngleBetween construct."""

from maya import cmds

import tik.maya as tm


def test_perpendicular_vectors_are_ninety_degrees():
    angle = tm.AngleBetween.create((1, 0, 0), (0, 1, 0), name="perp")
    assert abs(angle.angle.value - 90.0) < 1e-3


def test_parallel_vectors_are_zero():
    angle = tm.AngleBetween.create((1, 0, 0), (2, 0, 0), name="para")
    assert abs(angle.angle.value) < 1e-3


def test_opposite_vectors_are_one_eighty():
    angle = tm.AngleBetween.create((1, 0, 0), (-1, 0, 0), name="opp")
    assert abs(angle.angle.value - 180.0) < 1e-3


def test_a_plug_operand_is_live():
    holder = tm.Transform.create(name="angle_holder")
    holder.translate = (1, 0, 0)
    angle = tm.AngleBetween.create((1, 0, 0), holder["translate"], name="live")
    assert abs(angle.angle.value) < 1e-3
    holder.translate = (0, 1, 0)
    assert abs(angle.angle.value - 90.0) < 1e-3


def test_delete_removes_the_node():
    angle = tm.AngleBetween.create((1, 0, 0), (0, 1, 0), name="gone")
    name = angle.node.long_name
    angle.delete()
    assert not cmds.objExists(name)
