"""Tests for the connector module."""

from __future__ import annotations

import pytest


class TestConnectorGuideCreation:
    """Test guide creation for connector module."""

    def test_create_guides_creates_joint(self, connector_module):
        """Guide creation makes a Maya joint."""
        import maya.cmds as cmds

        connector_module.create_guides()
        joints = cmds.ls("*_jInit", type="joint")
        assert len(joints) >= 1

    def test_guide_data_stored(self, connector_module):
        """Guide data is stored in module."""
        connector_module.create_guides()
        assert len(connector_module.guides) == 1

    def test_delete_guides_removes_joints(self, connector_module):
        """Guide deletion removes Maya nodes."""
        import maya.cmds as cmds

        connector_module.create_guides()
        connector_module.delete_guides()
        joints = cmds.ls(f"{connector_module.name}_*_jInit", type="joint")
        assert len(joints) == 0


class TestConnectorBuild:
    """Test build for connector module."""

    def test_build_creates_groups(self, connector_module):
        """Build creates expected rig groups."""
        connector_module.create_guides()
        connector_module.build()

        import maya.cmds as cmds
        assert cmds.objExists(f"{connector_module.name}_limbGrp")

    def test_build_creates_root_joint(self, connector_module):
        """Build creates root joint."""
        connector_module.create_guides()
        connector_module.build()

        import maya.cmds as cmds
        assert cmds.objExists(f"{connector_module.name}_root_jnt")

    def test_build_defines_plugs(self, connector_module):
        """Build creates plug definitions."""
        connector_module.create_guides()
        connector_module.build()

        assert "rootPlug" in connector_module.plugs
        assert connector_module.plugs["rootPlug"].joint_name

    def test_build_defines_sockets(self, connector_module):
        """Build creates socket definitions."""
        connector_module.create_guides()
        connector_module.build()

        assert "rootSocket" in connector_module.sockets

    def test_is_built_flag(self, connector_module):
        """is_built returns True after build."""
        connector_module.create_guides()
        assert not connector_module.is_built
        connector_module.build()
        assert connector_module.is_built


class TestConnectorSettings:
    """Test settings for connector module."""

    def test_useRefOrientation_setting(self, connector_module):
        """Module accepts useRefOrientation setting."""
        connector_module.set_settings({"useRefOrientation": False})
        assert connector_module.get_setting("useRefOrientation") == False

    def test_curveAsShape_setting(self, connector_module):
        """Module accepts curveAsShape setting."""
        connector_module.set_settings({"curveAsShape": True})
        assert connector_module.get_setting("curveAsShape") == True