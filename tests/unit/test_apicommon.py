"""Unit tests for tik.maya.core.apicommon."""

from maya import cmds

from tik.maya.core import apicommon


class TestApiCommon:
    def test_obj_exists(self):
        """Test obj_exists function."""
        node = cmds.createNode("transform", name="testExists")
        assert apicommon.obj_exists("testExists")
        assert apicommon.obj_exists(node)
        assert not apicommon.obj_exists("nonExistentNode")

    def test_node_type(self):
        """Test node_type function."""
        node = cmds.createNode("transform", name="testType")
        assert apicommon.node_type("testType") == "transform"
        assert apicommon.node_type(node) == "transform"

        cmds.createNode("mesh", name="testMesh", parent=node)
        assert apicommon.node_type("testMesh") == "mesh"

        assert apicommon.node_type("nonExistentNode") is None
