"""Unit tests for tikmaya.core.node module."""

# python
import pytest
from maya import cmds
from maya import OpenMaya

from tik.maya.core.node import Node, Plug
from tik.maya.core.dagnode import DagNode


def test_create_returns_registered_subclass_for_transform():
    """Test that creating a transform returns a DagNode instance."""
    node = Node.create("transform", name="createdX")
    assert isinstance(node, DagNode)
    assert node.exists()
    assert node.name == "createdX"


def test_create_commands_with_multiple_return_values():
    """Test creating a node with a command that returns multiple values."""
    node = Node.create("polySphere", name="polySphereX")
    assert isinstance(node, Node)
    assert node.exists()
    assert node.name == "polySphereX"


def test_uuid_constant_across_rename():
    """Test that UUID remains constant after renaming a node."""
    transform = cmds.createNode("transform", name="orig")
    node = Node(cmds.ls(transform, long=True)[0])
    old_uuid = node.uuid
    node.rename("renamed")
    assert node.uuid == old_uuid
    assert node.name == "renamed"


def test_name_and_long_name_refresh_after_external_rename():
    """Test that name and long_name properties refresh after external rename."""
    transform = cmds.createNode("transform", name="A")
    node = Node(cmds.ls(transform, long=True)[0])

    _ = node.name
    _ = node.long_name

    cmds.rename("A", "B")

    assert node.name == "B"
    assert node.long_name.endswith("|B")


def test_long_name_shows_full_dag_path():
    """Test that long_name returns the full DAG path."""
    parent = cmds.createNode("transform", name="grp")
    child = cmds.createNode("transform", name="child", parent=parent)
    node = Node(cmds.ls(child, long=True)[0])
    assert node.long_name.endswith("|grp|child")


def test_rename_invalidate_cache_and_returns_self():
    """Test that rename invalidates cache and returns the node instance."""
    transform = cmds.createNode("transform", name="toRename")
    node = Node(cmds.ls(transform, long=True)[0])
    result = node.rename("renamedX")
    assert result is node
    assert node.name == "renamedX"
    assert node.long_name.endswith("|renamedX")


def test_node_and_plug_repr_contain_identifiers():
    """Test __repr__ contains class name and identifiers."""
    transform = cmds.createNode("transform", name="reprTest")
    node = Node(cmds.ls(transform, long=True)[0])
    assert "Node" in repr(node)


def test_adding_and_deleting_attributes_from_node_level():
    """Test adding and deleting attributes from Node methods."""
    transform = cmds.createNode("transform", name="attrDelTest")
    node = Node(cmds.ls(transform, long=True)[0])
    node.add_attr("tempAttr", attributeType="double", keyable=True)
    plug = node["tempAttr"]
    assert plug.get() == 0.0  # default value for double attribute
    node.delete_attr("tempAttr")
    with pytest.raises(ValueError):
        plug.get()


def test_duplicate_node():
    """Test duplicating a node."""
    original = cmds.createNode("transform", name="original")
    node = Node(cmds.ls(original, long=True)[0])
    dup = node.duplicate(name="copy")
    assert dup.exists()
    assert dup.name == "copy"
    assert dup.type == "transform"
    assert dup.uuid != node.uuid


def test_has_attr():
    """Test checking if an attribute exists."""
    transform = cmds.createNode("transform", name="attrTest")
    node = Node(cmds.ls(transform, long=True)[0])
    assert node.has_attr("translateX")
    assert not node.has_attr("nonExistentAttr")


def test_node_str_representation():
    """Test string representation of a node."""
    transform = cmds.createNode("transform", name="strTest")
    node = Node(cmds.ls(transform, long=True)[0])
    assert str(node) == "strTest"


def test_accessing_deleted_node_properties_returns_none():
    """Test accessing name/long_name on deleted node raises ValueError."""
    transform = cmds.createNode("transform", name="toDelete")
    node = Node(cmds.ls(transform, long=True)[0])

    # Ensure it exists first
    assert node.exists()

    cmds.delete(transform)

    # Should report not exists
    assert not node.exists()

    # Accessing name properties should return None
    assert node.name is None
    assert node.long_name is None


def test_dg_node_long_name_returns_name():
    """Test long_name property behavior on non-DAG nodes."""
    # "multiplyDivide" is a DG node, not a DAG node.
    # It has no hierarchy, so long_name should be same as name.
    # We use Node.create which should handle DG creation if we pass valid type
    # actually Node.create defaults to generic creation which works for DG.
    dg_node_name = cmds.createNode("multiplyDivide", name="myDGNode")

    node = Node(dg_node_name)
    assert not node.m_obj.hasFn(OpenMaya.MFn.kDagNode)

    assert node.name == "myDGNode"
    # This hits the else block in _resolve_long_name
    assert node.long_name == "myDGNode"


def test_get_valid_mobject_returns_null_for_truly_missing_node_internal():
    """
    Directly test _get_valid_mobject failure case.
    Usually covered by exists() returning False, but we want to ensure coverage
    of the exception handling block internally.
    """
    name = "nodeToVanish"
    cmds.createNode("transform", name=name)
    node = Node(name)
    assert node.exists()

    # Delete it
    cmds.delete(name)

    # Now call internal method to ensure it catches RuntimeError and returns kNullObj
    # We can inspect the returned MObject
    m_obj = node._get_valid_mobject()
    assert m_obj.isNull()


def test_delete_removes_node_from_scene():
    """Test that delete() method removes the node from the scene."""
    name = "nodeToDelete"
    cmds.createNode("transform", name=name)
    node = Node(name)
    assert node.exists()

    node.delete()

    assert not cmds.objExists(name)
    assert not node.exists()


def test_get_valid_mobject_re_resolves_from_uuid_when_handle_stale():
    """Test that _get_valid_mobject re-resolves from UUID when handle is stale.

    This covers lines 69-70 where the MObject is re-resolved from UUID after
    the handle becomes invalid but the node still exists.
    """
    from maya.api import OpenMaya as om

    # Create a node
    name = "staleHandleNode"
    cmds.createNode("transform", name=name)
    node = Node(name)

    # Store the original UUID
    original_uuid = node.uuid

    # Deliberately invalidate the internal MObject reference by assigning kNullObj
    # This simulates a stale handle scenario
    node._m_obj = om.MObject.kNullObj

    # Accessing m_obj property should re-resolve from UUID
    resolved_obj = node.m_obj

    # The object should be valid and refer to our node
    assert not resolved_obj.isNull()
    fn_dep = om.MFnDependencyNode(resolved_obj)
    assert fn_dep.uuid().asString() == original_uuid

def test_node_m_obj_re_resolves_when_stale() -> None:
    """Cover the UUID fallback path in Node._get_valid_mobject.

    We simulate a stale handle by nulling out the private _m_obj.
    The wrapper should re-resolve from its UUID and return a valid MObject.
    """
    cmds.file(new=True, force=True)
    node_name = cmds.createNode("transform", name="staleNode")

    node = Node(node_name)

    # Simulate a broken/stale MObject reference.
    node._m_obj = node._m_obj.__class__()  # pylint: disable=protected-access

    m_object = node.m_obj
    assert not m_object.isNull()
    assert node.exists()
    assert node.name == "staleNode"


def test_delete_history_removes_construction_history():
    """Test delete_history removes construction history from node."""
    # Create a mesh with construction history
    sphere_transform, sphere_history = cmds.polySphere(name="sphereWithHistory")
    node = Node(cmds.ls(sphere_transform, long=True)[0])

    # Verify history exists before deletion
    history = cmds.listHistory(sphere_transform)
    assert sphere_history in history

    # Delete history
    node.delete_history()

    # Verify history is removed (only mesh shape should remain)
    history_after = cmds.listHistory(sphere_transform)
    assert sphere_history not in history_after
