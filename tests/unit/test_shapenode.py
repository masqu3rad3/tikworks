# python
import pytest
from unittest.mock import patch
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
    t, _ = cmds.polyCube(name="selfS")
    s = cmds.listRelatives(t, shapes=True, fullPath=True)[0]
    sn = ShapeNode(s)
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


def test_parent_getter_returns_transform_wrapper():
    t, _ = cmds.polyCube(name="parentGetter")
    s = cmds.listRelatives(t, shapes=True, fullPath=True)[0]
    sn = ShapeNode(s)

    p = sn.parent
    assert isinstance(p, Transform)
    assert p.name == "parentGetter"
    assert p.long_name == "|parentGetter"


def test_parent_setter_raises_value_error_when_none():
    t, _ = cmds.polyCube(name="parentNone")
    s = cmds.listRelatives(t, shapes=True, fullPath=True)[0]
    sn = ShapeNode(s)

    with pytest.raises(ValueError, match="Shape nodes cannot be parented to world"):
        sn.parent = None


def test_parent_setter_reparents_shape_to_new_transform():
    # Create a shape
    t1, _ = cmds.polyCube(name="cube1")
    s1 = cmds.listRelatives(t1, shapes=True, fullPath=True)[0]
    sn = ShapeNode(s1)

    # Create a second transform (empty)
    t2 = cmds.createNode("transform", name="targetTransform")

    # Reparent shape to t2
    sn.parent = t2

    # Check if shape is now under t2
    assert sn.transform.name == "targetTransform"
    children = cmds.listRelatives(t2, shapes=True)
    assert children and children[0] == sn.name

    # Verify old parent is empty
    old_children = cmds.listRelatives(t1, shapes=True)
    assert not old_children


def test_parent_setter_accepts_transform_wrapper():
    t1, _ = cmds.polyCube(name="cubeWrapper")
    s1 = cmds.listRelatives(t1, shapes=True, fullPath=True)[0]
    sn = ShapeNode(s1)

    t2 = cmds.createNode("transform", name="targetWrapper")
    t2_node = Transform(t2)

    sn.parent = t2_node
    assert sn.transform.name == "targetWrapper"


def test_parent_setter_handles_shape_as_target_by_using_its_transform():
    t1, _ = cmds.polyCube(name="cubeSource")
    s1 = cmds.listRelatives(t1, shapes=True, fullPath=True)[0]
    sn = ShapeNode(s1)

    t2, _ = cmds.polyCube(name="cubeTarget")
    s2 = cmds.listRelatives(t2, shapes=True, fullPath=True)[0]
    target_sn = ShapeNode(s2)

    # Set parent to another shape -> should parent to that shape's transform
    sn.parent = target_sn

    assert sn.transform.name == "cubeTarget"
    children = cmds.listRelatives(t2, shapes=True)
    # t2 should now have two shapes: s2 and s1
    assert len(children) == 2
    assert sn.name in children


def test_init_with_mesh_node_name_directly():
    t, _ = cmds.polyCube(name="directShape")
    shapes = cmds.listRelatives(t, shapes=True)
    s = shapes[0]
    sn = ShapeNode(s)
    assert sn.name == s
    assert sn.transform.name == "directShape"


def test_parent_setter_accepts_string_name():
    t1, _ = cmds.polyCube(name="cubeStringParent")
    s1 = cmds.listRelatives(t1, shapes=True, fullPath=True)[0]
    sn = ShapeNode(s1)

    t2 = cmds.createNode("transform", name="targetString")

    sn.parent = "targetString"
    assert sn.transform.name == "targetString"


def test_shapenode_with_instanced_shape_resolves_correct_transform_robust():
    # Create a shape
    t1, _ = cmds.polyCube(name="cubeOriginal")
    shapes = cmds.listRelatives(t1, shapes=True, fullPath=True)
    s_long = shapes[0]  # |cubeOriginal|cubeOriginalShape

    # Create a second group
    g2 = cmds.createNode("transform", name="group2")

    # Instance the shape under g2
    # cmds.parent(shape, new_parent, add=True, shape=True)
    cmds.parent(s_long, g2, add=True, shape=True)

    # Now we have two paths to the shape.
    # We need to find them.
    # cmds.ls(s_long, allPaths=True) might help, but s_long is one specific path.
    # We know the new path should be under g2.

    # Get all paths for the shape node
    # We can use the shape name (short name) to list all paths
    # But listing relatives of the new parent is more reliable to find the specific path we just created
    children = cmds.listRelatives(g2, shapes=True, fullPath=True)
    if not children:
        pytest.fail(f"Group2 has no children. Instancing failed. s_long: {s_long}, g2: {g2}")

    path2 = children[0]

    # path1 is the original path
    path1 = s_long

    sn1 = ShapeNode(path1)
    assert sn1.transform.name == "cubeOriginal"

    sn2 = ShapeNode(path2)
    assert sn2.transform.name == "group2"


def test_shapenode_parent_property_respects_instance_path():
    # Create a shape
    t1, _ = cmds.polyCube(name="cubeParent1")
    shapes = cmds.listRelatives(t1, shapes=True, fullPath=True)
    s_long = shapes[0]

    # Create a second group
    g2 = cmds.createNode("transform", name="groupParent2")

    # Instance the shape under g2
    cmds.parent(s_long, g2, add=True, shape=True)

    # Get path to second instance
    children = cmds.listRelatives(g2, shapes=True, fullPath=True)
    path2 = children[0]

    sn2 = ShapeNode(path2)

    # The parent of the second instance should be groupParent2
    assert sn2.parent.name == "groupParent2"


def test_long_name_fallback_after_reparent():
    t1, _ = cmds.polyCube(name="cubeReparent")
    shapes = cmds.listRelatives(t1, shapes=True, fullPath=True)
    s_long = shapes[0]

    sn = ShapeNode(s_long)

    # Reparent to new transform
    t2 = cmds.createNode("transform", name="targetReparent")
    sn.parent = t2

    # After reparenting, _cached_dag_path is cleared.
    # Accessing long_name should trigger the fallback (super().long_name)
    # and it should still resolve correctly.
    assert sn.long_name.endswith(f"|{t2}|{sn.name}")
    assert sn.transform.name == "targetReparent"


def test_parent_property_returns_none_when_fullpath_empty():
    t, _ = cmds.polyCube(name="mockTestCube")
    shapes = cmds.listRelatives(t, shapes=True, fullPath=True)
    s_long = shapes[0]
    sn = ShapeNode(s_long)

    # Patch OpenMaya.MDagPath in the module where it is used
    with patch("tikmaya.core.shapenode.OpenMaya.MDagPath") as MockMDagPath:
        # Configure the mock instance returned by the constructor
        mock_instance = MockMDagPath.return_value
        # When fullPathName() is called, return empty string
        mock_instance.fullPathName.return_value = ""

        assert sn.parent is None

