# python
import pytest
from maya import cmds

from tik.maya.core.dagnode import DagNode
from tik.maya.core.registry import resolve


def test_parent_none_for_world_transform():
    root = cmds.createNode("transform", name="root")
    root_node = resolve(cmds.ls(root, long=True)[0])

    assert isinstance(root_node, DagNode)
    assert root_node.parent is None


def test_parent_returns_wrapped_node_for_child():
    parent = cmds.createNode("transform", name="parentX")
    child = cmds.createNode("transform", name="childX", parent=parent)

    child_node = resolve(cmds.ls(child, long=True)[0])
    parent_node = child_node.parent

    assert isinstance(parent_node, DagNode)
    assert parent_node.name == "parentX"


def test_parent_set_to_new_parent_node_and_updates_children():
    p1 = cmds.createNode("transform", name="p1")
    p2 = cmds.createNode("transform", name="p2")
    ch = cmds.createNode("transform", name="ch", parent=p1)

    p1_node = resolve(cmds.ls(p1, long=True)[0])
    p2_node = resolve(cmds.ls(p2, long=True)[0])
    ch_node = resolve(cmds.ls(ch, long=True)[0])

    assert ch_node.parent.name == "p1"

    ch_node.parent = p2_node

    assert ch_node.parent.name == "p2"
    assert all(child.name != "ch" for child in p1_node.children)
    assert any(child.name == "ch" for child in p2_node.children)


def test_parent_set_to_new_parent_by_name_and_cache_refresh():
    pA = cmds.createNode("transform", name="pA")
    pB = cmds.createNode("transform", name="pB")
    node = cmds.createNode("transform", name="n", parent=pA)

    n_node = resolve(cmds.ls(node, long=True)[0])

    _ = n_node.parent  # populate the cached dag path
    n_node.parent = "pB"

    assert n_node.parent is not None
    assert n_node.parent.name == "pB"


def test_unparent_to_world_clears_parent():
    grp = cmds.createNode("transform", name="grp")
    item = cmds.createNode("transform", name="item", parent=grp)

    node = resolve(cmds.ls(item, long=True)[0])
    assert node.parent is not None

    node.parent = None

    assert node.parent is None
    assert cmds.listRelatives(item, parent=True) is None


def test_children_return_wrapped_nodes_and_order():
    parent = cmds.createNode("transform", name="rootP")
    c1 = cmds.createNode("transform", name="c1", parent=parent)
    c2 = cmds.createNode("transform", name="c2", parent=parent)

    parent_node = resolve(cmds.ls(parent, long=True)[0])
    children = parent_node.children

    assert all(isinstance(child, DagNode) for child in children)
    assert [child.name for child in children] == ["c1", "c2"]
    assert {child.long_name for child in children} == set(cmds.ls([c1, c2], long=True))


def test_children_empty_on_leaf():
    leaf = cmds.createNode("transform", name="leaf")
    leaf_node = resolve(cmds.ls(leaf, long=True)[0])

    assert leaf_node.children == []


def test_duplicate_child_names_resolve_correct_parent_via_long_name():
    pA = cmds.createNode("transform", name="pA")
    pB = cmds.createNode("transform", name="pB")
    xA = cmds.createNode("transform", name="x", parent=pA)
    xA_long = cmds.ls(xA, long=True)[0]
    xB = cmds.createNode("transform", name="x", parent=pB)
    xB_long = cmds.ls(xB, long=True)[0]

    xA_node = resolve(xA_long)
    xB_node = resolve(xB_long)

    assert xA_node.parent.name == "pA"
    assert xB_node.parent.name == "pB"


def test_getting_and_setting_visibility():
    node = cmds.createNode("transform", name="visNode")
    node_wrapper = resolve(cmds.ls(node, long=True)[0])

    # Default visibility should be True
    assert node_wrapper.visibility is True

    # Set visibility to False
    node_wrapper.visibility = False
    assert node_wrapper.visibility is False
    assert cmds.getAttr(f"{node}.visibility") is False

    # Set visibility back to True
    node_wrapper.visibility = True
    assert node_wrapper.visibility is True
    assert cmds.getAttr(f"{node}.visibility") is True


def test_dag_path_property_returns_mdagpath():
    """Test that dag_path property returns a valid MDagPath."""
    from maya.api import OpenMaya

    node = cmds.createNode("transform", name="dagPathNode")
    node_wrapper = resolve(cmds.ls(node, long=True)[0])

    dag_path = node_wrapper.dag_path
    assert isinstance(dag_path, OpenMaya.MDagPath)
    assert dag_path.isValid()
    assert dag_path.fullPathName() == node_wrapper.long_name


def test_bounding_box_property_returns_mboundingbox():
    """Test that bounding_box property returns a valid MBoundingBox."""
    from maya.api import OpenMaya

    node = cmds.createNode("transform", name="bbNode")
    node_wrapper = resolve(cmds.ls(node, long=True)[0])

    bb = node_wrapper.bounding_box
    assert isinstance(bb, OpenMaya.MBoundingBox)
    # Default transform has empty bounding box at origin
    assert bb.min.x == 0.0 and bb.min.y == 0.0 and bb.min.z == 0.0
    assert bb.max.x == 0.0 and bb.max.y == 0.0 and bb.max.z == 0.0


def test_select_method_selects_node():
    """Test that select() method selects the node in the scene."""
    node = cmds.createNode("transform", name="selectNode")
    node_wrapper = resolve(cmds.ls(node, long=True)[0])

    cmds.select(clear=True)
    assert not cmds.ls(selection=True)

    node_wrapper.select()
    assert cmds.ls(selection=True) == [node_wrapper.name]


def test_color_property_none_when_no_override():
    """Test color property returns None when override is not enabled."""
    node = cmds.createNode("transform", name="colorNodeNoOverride")
    node_wrapper = resolve(cmds.ls(node, long=True)[0])

    # By default overrideEnabled is false
    assert node_wrapper.color is None


def test_color_property_none_when_override_disabled():
    """Test color property returns None when overrideEnabled is False."""
    node = cmds.createNode("transform", name="colorNodeDisabled")
    node_wrapper = resolve(cmds.ls(node, long=True)[0])

    cmds.setAttr(f"{node}.overrideEnabled", True)
    cmds.setAttr(f"{node}.overrideEnabled", False)

    assert node_wrapper.color is None


def test_set_and_get_index_color():
    """Test setting and getting index color."""
    node = cmds.createNode("transform", name="colorNodeIndex")
    node_wrapper = resolve(cmds.ls(node, long=True)[0])

    # Set index color 17 (yellowish)
    node_wrapper.color = 17

    assert cmds.getAttr(f"{node}.overrideEnabled") is True
    assert cmds.getAttr(f"{node}.overrideRGBColors") is False
    assert cmds.getAttr(f"{node}.overrideColor") == 17
    assert node_wrapper.color == 17


def test_set_and_get_rgb_color():
    """Test setting and getting RGB color."""
    node = cmds.createNode("transform", name="colorNodeRGB")
    node_wrapper = resolve(cmds.ls(node, long=True)[0])

    rgb = (1.0, 0.0, 0.5)
    node_wrapper.color = rgb

    assert cmds.getAttr(f"{node}.overrideEnabled") is True
    assert cmds.getAttr(f"{node}.overrideRGBColors") is True
    # Maya stores RGB as float, so use approx
    stored_rgb = cmds.getAttr(f"{node}.overrideColorRGB")[0]
    assert pytest.approx(stored_rgb, rel=1e-5) == rgb

    retrieved_rgb = node_wrapper.color
    assert pytest.approx(retrieved_rgb, rel=1e-5) == rgb


def test_set_color_none_disables_override():
    """Test setting color to None disables override."""
    node = cmds.createNode("transform", name="colorNodeNone")
    node_wrapper = resolve(cmds.ls(node, long=True)[0])

    node_wrapper.color = 17
    assert cmds.getAttr(f"{node}.overrideEnabled") is True

    node_wrapper.color = None
    assert cmds.getAttr(f"{node}.overrideEnabled") is False
    assert node_wrapper.color is None


def test_color_methods_handle_missing_attributes():
    """Test get_color and set_color handle missing attributes gracefully."""
    node = cmds.createNode("transform", name="noAttrNode")
    node_wrapper = resolve(cmds.ls(node, long=True)[0])

    # Mock has_attr to return False for overrideEnabled
    # We do this because overrideEnabled is a built-in attribute on DAG nodes
    # and cannot be deleted, but we want to test the safety check.
    original_has_attr = node_wrapper.has_attr
    node_wrapper.has_attr = lambda attr: (
        False if attr == "overrideEnabled" else original_has_attr(attr)
    )

    try:
        # Test get_color
        assert node_wrapper.color is None

        # Test set_color (should not raise error)
        node_wrapper.color = 17
    finally:
        # Restore just in case
        del node_wrapper.has_attr


def test_dagnode_create_method():
    """Test DagNode.create class method."""
    node = DagNode.create("transform", name="dagCreateMethod")
    assert isinstance(node, DagNode)
    assert node.name == "dagCreateMethod"


def test_dagnode_rename_uses_dag_modifier():
    """Test renaming a DagNode using its rename method."""
    node = DagNode.create("transform", name="dagRename")
    # Verify it is DagNode
    assert isinstance(node, DagNode)

    # Rename
    node.rename("dagRenamed")
    assert node.name == "dagRenamed"
    assert node.long_name.endswith("|dagRenamed")


def test_set_parent_raises_if_parent_not_exists():
    """Test setting parent to a non-existent node raises ValueError."""
    child = DagNode.create("transform", name="childNode")
    parent_node = DagNode.create("transform", name="parentNodeToDelete")

    # Ensure it exists
    assert parent_node.exists()

    # Delete the parent node from Maya
    cmds.delete(parent_node.long_name)
    assert not parent_node.exists()

    # Try to set parent to the deleted node wrapper
    with pytest.raises(ValueError, match="does not exist"):
        child.parent = parent_node


def test_is_deformable():
    """Test is_deformable method."""
    # Transform is not deformable
    transform = DagNode.create("transform", name="notDeformable")
    assert not transform.is_deformable()

    # Mesh is deformable
    # Create a mesh using cmds.createNode("mesh") which creates transform+mesh
    # Node.create("mesh") -> creates mesh node properly.
    mesh_node = DagNode.create("mesh", name="deformableShape", parent=transform)

    # mesh_node is the ShapeNode (DagNode of type mesh)
    assert mesh_node.type == "mesh"
    assert mesh_node.is_deformable()


def test_get_color_returns_raw_tuple_when_as_color_is_false():
    """Test get_color(as_color=False) returns raw RGB tuple."""
    node = DagNode.create("transform", name="colorRGBRaw")
    rgb = (0.2, 0.3, 0.4)
    node.color = rgb

    # Check default (Color object)
    # node.color returns a Color object which might behave like a tuple or have .rgb,
    # but exact equality fails due to float precision.
    # Assuming Color object is iterable or comparable to tuple, we use approx on elements.
    retrieved_color = node.color
    # If it's a Color object, get its rgb component or cast to tuple if logical
    if hasattr(retrieved_color, "rgb"):
        vals = retrieved_color.rgb
    else:
        vals = retrieved_color

    assert pytest.approx(vals, rel=1e-5) == rgb

    # Check raw
    raw = node.get_color(as_color=False)
    assert isinstance(raw, tuple)
    assert pytest.approx(raw, rel=1e-5) == rgb


def test_set_color_returns_early_if_attr_missing():
    """Test set_color returns early if overrideEnabled attribute is missing."""
    node = DagNode.create("transform", name="noOverrideAttr")

    # Mock has_attr to return False ONLY for overrideEnabled check
    # We need to be careful as set_color calls has_attr("overrideEnabled")

    original_has_attr = node.has_attr

    def mock_has_attr(attr_name):
        if attr_name == "overrideEnabled":
            return False
        return original_has_attr(attr_name)

    node.has_attr = mock_has_attr

    # Should not raise error and should return None (implicit)
    node.set_color(17)

    # Verify no crash, and no effect (hard to verify no effect on missing attr, but
    # ensuring it ran the check path is the goal)


def test_get_color_as_color_returns_color_object():
    """Test get_color(as_color=True) returns a Color object when RGB mode."""
    from tik.core.color import Color

    node = DagNode.create("transform", name="colorAsColorObj")
    rgb = (0.5, 0.6, 0.7)
    node.color = rgb

    # Get as Color object
    color_obj = node.get_color(as_color=True)
    assert isinstance(color_obj, Color)
    assert pytest.approx(color_obj.rgb, rel=1e-5) == rgb


def test_set_color_with_color_object():
    """Test set_color accepts a Color object and extracts its rgb."""
    from tik.core.color import Color

    node = DagNode.create("transform", name="colorObjInput")
    color_obj = Color((0.2, 0.8, 0.4))

    # Set using Color object
    node.color = color_obj

    # Verify it was applied correctly
    assert cmds.getAttr(f"{node.name}.overrideEnabled") is True
    assert cmds.getAttr(f"{node.name}.overrideRGBColors") is True
    stored_rgb = cmds.getAttr(f"{node.name}.overrideColorRGB")[0]
    assert pytest.approx(stored_rgb, rel=1e-5) == color_obj.rgb


def test_dagnode_get_color_returns_none_when_override_disabled() -> None:
    cmds.file(new=True, force=True)
    transform_name = cmds.createNode("transform", name="colorTest")
    node = DagNode(transform_name)

    # Default is no override.
    assert node.get_color() is None


def test_dagnode_get_color_rgb_and_index_paths() -> None:
    cmds.file(new=True, force=True)
    transform_name = cmds.createNode("transform", name="colorTestRGB")
    node = DagNode(transform_name)

    # RGB override path
    node["overrideEnabled"].value = True
    node["overrideRGBColors"].value = True
    node["overrideColorRGB"].value = (0.25, 0.5, 0.75)

    rgb = node.get_color(as_color=False)
    assert rgb == (0.25, 0.5, 0.75)

    # Index override path
    node["overrideRGBColors"].value = False
    node["overrideColor"].value = 17

    color_index = node.get_color(as_color=False)
    assert color_index == 17
