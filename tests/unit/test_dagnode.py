# python
import pytest
from maya import cmds

from tikmaya.core.registry import get_node
from tikmaya.core.dagnode import DagNode


def test_parent_none_for_world_transform():
    root = cmds.createNode("transform", name="root")
    root_node = get_node(cmds.ls(root, long=True)[0])

    assert isinstance(root_node, DagNode)
    assert root_node.parent is None


def test_parent_returns_wrapped_node_for_child():
    parent = cmds.createNode("transform", name="parentX")
    child = cmds.createNode("transform", name="childX", parent=parent)

    child_node = get_node(cmds.ls(child, long=True)[0])
    parent_node = child_node.parent

    assert isinstance(parent_node, DagNode)
    assert parent_node.name == "parentX"


def test_parent_set_to_new_parent_node_and_updates_children():
    p1 = cmds.createNode("transform", name="p1")
    p2 = cmds.createNode("transform", name="p2")
    ch = cmds.createNode("transform", name="ch", parent=p1)

    p1_node = get_node(cmds.ls(p1, long=True)[0])
    p2_node = get_node(cmds.ls(p2, long=True)[0])
    ch_node = get_node(cmds.ls(ch, long=True)[0])

    assert ch_node.parent.name == "p1"

    ch_node.parent = p2_node

    assert ch_node.parent.name == "p2"
    assert all(c.name != "ch" for c in p1_node.children)
    assert any(c.name == "ch" for c in p2_node.children)


def test_parent_set_to_new_parent_by_name_and_cache_refresh():
    pA = cmds.createNode("transform", name="pA")
    pB = cmds.createNode("transform", name="pB")
    n = cmds.createNode("transform", name="n", parent=pA)

    n_node = get_node(cmds.ls(n, long=True)[0])

    _ = n_node.parent  # populate the cached dag path
    n_node.parent = "pB"

    assert n_node.parent is not None
    assert n_node.parent.name == "pB"


def test_unparent_to_world_clears_parent():
    grp = cmds.createNode("transform", name="grp")
    item = cmds.createNode("transform", name="item", parent=grp)

    node = get_node(cmds.ls(item, long=True)[0])
    assert node.parent is not None

    node.parent = None

    assert node.parent is None
    assert cmds.listRelatives(item, parent=True) is None


def test_children_return_wrapped_nodes_and_order():
    parent = cmds.createNode("transform", name="rootP")
    c1 = cmds.createNode("transform", name="c1", parent=parent)
    c2 = cmds.createNode("transform", name="c2", parent=parent)

    parent_node = get_node(cmds.ls(parent, long=True)[0])
    children = parent_node.children

    assert all(isinstance(c, DagNode) for c in children)
    assert [c.name for c in children] == ["c1", "c2"]
    assert {c.long_name for c in children} == set(cmds.ls([c1, c2], long=True))


def test_children_empty_on_leaf():
    leaf = cmds.createNode("transform", name="leaf")
    leaf_node = get_node(cmds.ls(leaf, long=True)[0])

    assert leaf_node.children == []


def test_duplicate_child_names_resolve_correct_parent_via_long_name():
    pA = cmds.createNode("transform", name="pA")
    pB = cmds.createNode("transform", name="pB")
    xA = cmds.createNode("transform", name="x", parent=pA)
    xA_long = cmds.ls(xA, long=True)[0]
    xB = cmds.createNode("transform", name="x", parent=pB)
    xB_long = cmds.ls(xB, long=True)[0]

    xA_node = get_node(xA_long)
    xB_node = get_node(xB_long)

    assert xA_node.parent.name == "pA"
    assert xB_node.parent.name == "pB"
