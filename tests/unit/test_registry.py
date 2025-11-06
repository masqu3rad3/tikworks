import pytest

import tikmaya

try:
    from maya import cmds
except ImportError:
    pytest.skip('Maya is not installed.', allow_module_level=True)

import pytest
from tikmaya.core.node import Node
from tikmaya.core.registry import get_node, set_default_factory, register

class TestRegistry:
    def test_register_and_get_node(self):

        # Set default factory to Transform
        set_default_factory(Node)

        # Register Joint class
        @register("joint")
        class TestJoint(Node):
            pass

        # Create a joint node in Maya
        joint_name = cmds.joint(name="test_joint")

        # Retrieve the node using get_node
        node = get_node(joint_name)

        # Check that the returned node is an instance of TestJoint
        assert isinstance(node, TestJoint)

        # Clean up
        cmds.delete(joint_name)

    def test_get_node_with_no_registration(self):
        # Set default factory to Transform
        set_default_factory(Node)

        # Create a transform node in Maya
        transform_name = cmds.createNode("transform", name="test_transform")

        # Retrieve the node using get_node
        node = get_node(transform_name)

        # Check that the returned node is an instance of Transform
        assert isinstance(node, Node)

        # Clean up
        cmds.delete(transform_name)

    def test_get_node_with_nonexistent_node(self):
        """Test that get_node raises ValueError for a non-existing node."""
        with pytest.raises(ValueError,
                           match="Node 'nonexistent_node' does not exist."):
            get_node("nonexistent_node")

    def test_get_node_with_default_factory(self):
        """Test that get_node uses the default factory when no specific type is registered."""
        # Create a Transform node
        node_name = cmds.createNode("multiplyDivide", name="test_transform")

        # Use get_node to retrieve it
        node = get_node(node_name)

        # Ensure it returns a Node instance
        assert isinstance(node, Node)
        assert node.name == node_name

    def test_get_node_with_inherited_type(self, monkeypatch):
        """Test get_node with inherited types."""

        # Patch the _NODE_TYPES to clear any previous registrations for this test
        monkeypatch.setattr('tikmaya.core.registry._NODE_TYPES', {})

        @register("dagNode")
        class CustomDagNode(Node):
            pass
        # Create a transform node (inherits 'transform')
        transform_name = cmds.createNode("transform", name="test_transform")



        # Retrieve the node using get_node
        node = get_node(transform_name)

        # Ensure the returned node uses the inherited CustomDagNode type
        assert isinstance(node, CustomDagNode)
        assert node.name == transform_name

    def test_get_node_no_type_and_no_factory_registered(self):
        """Test get_node raises LookupError when no factory is registered."""
        # Clear default factory
        set_default_factory(None)

        # Create a transform node
        node_name = cmds.createNode("multiplyDivide", name="test_transform")

        # Expect a LookupError when no default factory is set
        with pytest.raises(LookupError,
                           match="No wrapper registered for 'multiplyDivide' and no default factory set."):
            get_node(node_name)