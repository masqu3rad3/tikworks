"""Tests for the arm module."""

from __future__ import annotations

import pytest


class TestArmGuideCreation:
    """Test guide creation for arm module."""

    def test_create_guides_creates_four_joints(self, arm_module):
        """Guide creation makes four Maya joints."""
        import maya.cmds as cmds

        arm_module.create_guides()
        joints = cmds.ls("*_jInit", type="joint")
        assert len(joints) >= 4

    def test_guide_data_stored(self, arm_module):
        """Guide data is stored in module."""
        arm_module.create_guides()
        assert len(arm_module.guides) == 4

    def test_delete_guides_removes_joints(self, arm_module):
        """Guide deletion removes Maya nodes."""
        import maya.cmds as cmds

        arm_module.create_guides()
        arm_module.delete_guides()
        joints = cmds.ls(f"{arm_module.name}_*_jInit", type="joint")
        assert len(joints) == 0


class TestArmBuild:
    """Test build for arm module."""

    def test_build_creates_groups(self, arm_module):
        """Build creates expected rig groups."""
        arm_module.create_guides()
        arm_module.build()

        import maya.cmds as cmds
        assert cmds.objExists(f"{arm_module.name}_limbGrp")
        assert cmds.objExists(f"{arm_module.name}_scaleGrp")
        assert cmds.objExists(f"{arm_module.name}_controllerGrp")

    def test_build_creates_collar_joint(self, arm_module):
        """Build creates collar joint."""
        arm_module.create_guides()
        arm_module.build()

        import maya.cmds as cmds
        assert cmds.objExists(f"{arm_module.name}_collar_jDef")

    def test_build_defines_plugs(self, arm_module):
        """Build creates plug definitions."""
        arm_module.create_guides()
        arm_module.build()

        assert "limbPlug" in arm_module.plugs

    def test_build_defines_sockets(self, arm_module):
        """Build creates socket definitions."""
        arm_module.create_guides()
        arm_module.build()

        assert "collarSocket" in arm_module.sockets
        assert "elbowSocket" in arm_module.sockets
        assert "handSocket" in arm_module.sockets

    def test_is_built_flag(self, arm_module):
        """is_built returns True after build."""
        arm_module.create_guides()
        assert not arm_module.is_built
        arm_module.build()
        assert arm_module.is_built


class TestArmSettings:
    """Test settings for arm module."""

    def test_localJoints_setting(self, arm_module):
        """Module accepts localJoints setting."""
        arm_module.set_settings({"localJoints": True})
        assert arm_module.get_setting("localJoints") == True

    def test_useRefOrientation_setting(self, arm_module):
        """Module accepts useRefOrientation setting."""
        arm_module.set_settings({"useRefOrientation": False})
        assert arm_module.get_setting("useRefOrientation") == False