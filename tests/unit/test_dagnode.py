# python
import pytest
from maya import cmds

from tikmaya.core.registry import resolve
from tikmaya.core.dagnode import DagNode


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
    assert all(c.name != "ch" for c in p1_node.children)
    assert any(c.name == "ch" for c in p2_node.children)


def test_parent_set_to_new_parent_by_name_and_cache_refresh():
    pA = cmds.createNode("transform", name="pA")
    pB = cmds.createNode("transform", name="pB")
    n = cmds.createNode("transform", name="n", parent=pA)

    n_node = resolve(cmds.ls(n, long=True)[0])

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

    assert all(isinstance(c, DagNode) for c in children)
    assert [c.name for c in children] == ["c1", "c2"]
    assert {c.long_name for c in children} == set(cmds.ls([c1, c2], long=True))


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
    node_wrapper.has_attr = lambda attr: False if attr == "overrideEnabled" else original_has_attr(attr)

    try:
        # Test get_color
        assert node_wrapper.color is None

        # Test set_color (should not raise error)
        node_wrapper.color = 17
    finally:
        # Restore just in case
        del node_wrapper.has_attr

