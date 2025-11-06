# python
import pytest
from maya import cmds

from tikmaya.core.shapenode import ShapeNode
from tikmaya.types.transform import Transform


def test_init_with_transform_without_shape_raises():
    empty = cmds.createNode("transform", name="emptyX")
    with pytest.raises(ValueError):
        ShapeNode(empty)


def test_construct_with_shape_name_returns_same_shape_and_transform():
    t, s = cmds.polyCube(name="boxX")
    # initially the shape name is not getting the <name>Shape suffix. Probably a Maya bug.
    s = cmds.listRelatives(t, shapes=True, fullPath=True)[0]
    shape_long = cmds.ls(s, long=True)[0]
    sn = ShapeNode(shape_long)
    assert sn.name == "boxXShape"
    assert sn.long_name.endswith("|boxX|boxXShape")
    tr = sn.transform
    assert isinstance(tr, Transform)
    assert tr.name == "boxX"


def test_construct_with_transform_name_uses_first_shape():
    tr = cmds.createNode("transform", name="multiT")
    sh1 = cmds.createNode("mesh", name="shOneShape", parent=tr)
    _ = cmds.createNode("mesh", name="shTwoShape", parent=tr)
    sn = ShapeNode(tr)
    assert sn.name == "shOneShape"
    assert sn.long_name.endswith(f"|{tr}|{sh1}")


def test_transform_property_cached_and_refreshes_after_transform_rename():
    t, s = cmds.polyCube(name="geoA")
    # initially the shape name is not getting the <name>Shape suffix. Probably a Maya bug.
    s = cmds.listRelatives(t, shapes=True, fullPath=True)[0]
    sn = ShapeNode(cmds.ls(s, long=True)[0])
    first = sn.transform
    second = sn.transform
    assert first is second
    cmds.rename(t, "geoB")
    refreshed = sn.transform
    assert refreshed.name == "geoB"


def test_shape_property_returns_self():
    t, s = cmds.polyCube(name="selfS")
    sn = ShapeNode(cmds.ls(s, long=True)[0])
    assert sn.shape is sn


def test_transform_property_returns_transform_with_full_long_name_in_hierarchy():
    grp = cmds.createNode("transform", name="GRP")
    t, s = cmds.polyCube(name="childT")
    # initially the shape name is not getting the <name>Shape suffix. Probably a Maya bug.
    s = cmds.listRelatives(t, shapes=True, fullPath=False)[0]
    cmds.parent(t, grp)
    sn = ShapeNode(cmds.ls(s, long=True)[0])
    tr = sn.transform
    assert tr.long_name.endswith("|GRP|childT")


def test_construct_with_transform_long_name_works():
    t, s = cmds.polyCube(name="longT")
    t_long = cmds.ls(t, long=True)[0]
    sn = ShapeNode(t_long)
    assert sn.name == "longTShape"
    assert sn.transform.name == "longT"
