"""Tests for tik.maya.core.naming mechanics."""

from maya import cmds

from tik.maya.core import naming


def test_unique_name_free():
    assert naming.unique_name("arm") == "arm"


def test_unique_name_increments():
    cmds.createNode("transform", name="arm")
    assert naming.unique_name("arm") == "arm1"
    cmds.createNode("transform", name="arm1")
    assert naming.unique_name("arm") == "arm2"


def test_unique_name_with_padding():
    cmds.createNode("transform", name="arm01")
    assert naming.unique_name("arm01") == "arm02"


def test_unique_name_with_separator():
    cmds.createNode("transform", name="arm")
    assert naming.unique_name("arm", separator="_") == "arm_1"


def test_format_name():
    assert naming.format_name("upArm", 0, suffix="jnt", side="L") == "L_upArm_0_jnt"
    assert naming.format_name("root", prefix="trg") == "trg_root"
    assert naming.format_name("a", "", None, "b", sep="-") == "a-b"
