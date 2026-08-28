"""Plug paths must stay valid when short names are not unique."""

from maya import cmds
from maya.api import OpenMaya

import tik.maya as tm


def test_plug_path_disambiguates_duplicate_short_names():
    first_parent = tm.Transform.create(name="rig_a")
    first = tm.Transform.create(name="limb", parent=first_parent.long_name)
    second_parent = tm.Transform.create(name="rig_b")
    second = tm.Transform.create(name="tmp", parent=second_parent.long_name)
    OpenMaya.MFnDependencyNode(second.m_obj).setName("limb")  # no uniquifying
    assert second.name == "limb"
    assert first.partial_name == "rig_a|limb"
    first["tx"].value = 3.0
    second["tx"].value = 5.0
    assert cmds.getAttr("rig_a|limb.tx") == 3.0
    assert cmds.getAttr("rig_b|limb.tx") == 5.0
    assert first["tx"].path == "rig_a|limb.tx"


def test_plug_path_stays_short_for_unique_names():
    node = tm.Transform.create(name="unique")
    assert node["tx"].path == "unique.tx"
    dg_node = tm.create_node("multiplyDivide", name="mult")
    assert dg_node["input1X"].path == "mult.input1X"
