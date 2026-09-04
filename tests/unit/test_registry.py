import pytest

try:
    from maya import cmds
except ImportError:
    pytest.skip("Maya is not installed.", allow_module_level=True)

import pytest

from tik.maya.core.node import Node
from tik.maya.core.registry import register, resolve, set_default_factory


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
        node = resolve(joint_name)

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
        node = resolve(transform_name)

        # Check that the returned node is an instance of Transform
        assert isinstance(node, Node)

        # Clean up
        cmds.delete(transform_name)

    def test_get_node_with_nonexistent_node(self):
        """Test that get_node raises ValueError for a non-existing node."""
        with pytest.raises(ValueError, match="Node 'nonexistent_node' does not exist."):
            resolve("nonexistent_node")

    def test_get_node_with_default_factory(self):
        """get_node uses the default factory when no specific type is registered."""
        # Create a Transform node
        node_name = cmds.createNode("multiplyDivide", name="test_transform")

        # Use get_node to retrieve it
        node = resolve(node_name)

        # Ensure it returns a Node instance
        assert isinstance(node, Node)
        assert node.name == node_name

    def test_get_node_with_inherited_type(self, monkeypatch):
        """Test get_node with inherited types."""

        # Patch the _NODE_TYPES to clear any previous registrations for this test
        monkeypatch.setattr("tik.maya.core.registry._NODE_TYPES", {})

        @register("dagNode")
        class CustomDagNode(Node):
            pass

        # Create a transform node (inherits 'transform')
        transform_name = cmds.createNode("transform", name="test_transform")

        # Retrieve the node using get_node
        node = resolve(transform_name)

        # Ensure the returned node uses the inherited CustomDagNode type
        assert isinstance(node, CustomDagNode)
        assert node.name == transform_name

    def test_get_node_no_type_and_no_factory_registered(self):
        """Test get_node raises LookupError when no factory is registered."""
        # Clear default factory
        set_default_factory(None)

        try:
            # Create a transform node
            node_name = cmds.createNode("multiplyDivide", name="test_transform")

            # Expect a LookupError when no default factory is set
            with pytest.raises(
                LookupError,
                match=(
                    "No wrapper registered for 'multiplyDivide' "
                    "and no default factory set."
                ),
            ):
                resolve(node_name)
        finally:
            # Restore the default factory for other tests
            set_default_factory(Node)

    def test_resolve_with_class_name_success(self):
        """Test resolve with explicit class_name."""

        @register("mySpecialNode")
        class MySpecialNode(Node):
            pass

        node_name = cmds.createNode("transform", name="special")
        # Even though it's a transform, we force it to be wrapped as MySpecialNode (if
        # compatible or just forced)
        # The resolve function just instantiates cls(name). Node.__init__ checks
        # existence.

        # We need to register it by name so we can look it up by class_name string?
        # Wait, _NODE_TYPES keys are node types (strings).
        # resolve(name, class_name="...") looks up _NODE_TYPES.get(class_name).
        # But _NODE_TYPES keys are usually maya node types like "transform", "joint".
        # If I register with @register("mySpecialNode"), then class_name should be
        # "mySpecialNode".

        node = resolve(node_name, class_name="mySpecialNode")
        assert isinstance(node, MySpecialNode)
        assert node.name == "special"

    def test_resolve_with_class_name_failure(self):
        """Test resolve raises LookupError for unknown class_name."""
        node_name = cmds.createNode("transform", name="unknown")
        with pytest.raises(
            LookupError, match="No wrapper registered for class name 'UnknownType'"
        ):
            resolve(node_name, class_name="UnknownType")

    def test_resolve_returns_instance_if_already_wrapper(self):
        """resolve returns an already-wrapped instance unchanged."""

        @register("knownType")
        class KnownType(Node):
            pass

        # We need an instance of KnownType.
        # Since Node.__init__ checks for existence, we need a real node.
        real_node = cmds.createNode("transform", name="known")
        wrapper = KnownType(real_node)

        # Now pass the wrapper to resolve
        result = resolve(wrapper)
        assert result is wrapper

    def test_is_registered(self):
        """Test is_registered function."""
        from tik.maya.core.registry import is_registered

        @register("registeredType")
        class RegisteredType(Node):
            pass

        assert is_registered("registeredType")
        assert not is_registered("unregisteredType")
