"""Tests for the pushpull module."""

from __future__ import annotations

import pytest


class TestPushPullGuideCreation:
    """Test guide creation for pushpull module."""

    def test_create_guides_creates_two_joints(self, pushpull_module):
        """Guide creation makes two Maya joints."""
        import maya.cmds as cmds

        pushpull_module.create_guides()
        joints = cmds.ls("*_jInit", type="joint")
        assert len(joints) >= 2

    def test_guide_data_stored(self, pushpull_module):
        """Guide data is stored in module."""
        pushpull_module.create_guides()
        assert len(pushpull_module.guides) == 2

    def test_delete_guides_removes_joints(self, pushpull_module):
        """Guide deletion removes Maya nodes."""
        import maya.cmds as cmds

        pushpull_module.create_guides()
        pushpull_module.delete_guides()
        joints = cmds.ls(f"{pushpull_module.name}_*_jInit", type="joint")
        assert len(joints) == 0


class TestPushPullBuild:
    """Test build for pushpull module."""

    def test_build_creates_groups(self, pushpull_module):
        """Build creates expected rig groups."""
        pushpull_module.create_guides()
        pushpull_module.build()

        import maya.cmds as cmds
        assert cmds.objExists(f"{pushpull_module.name}_limbGrp")

    def test_build_creates_start_and_end_joints(self, pushpull_module):
        """Build creates start and end joints."""
        pushpull_module.create_guides()
        pushpull_module.build()

        import maya.cmds as cmds
        assert cmds.objExists(f"{pushpull_module.name}_base_jDef")
        assert cmds.objExists(f"{pushpull_module.name}_end_jDef")

    def test_build_defines_plugs(self, pushpull_module):
        """Build creates plug definitions."""
        pushpull_module.create_guides()
        pushpull_module.build()

        assert "basePlug" in pushpull_module.plugs

    def test_build_defines_sockets(self, pushpull_module):
        """Build creates socket definitions."""
        pushpull_module.create_guides()
        pushpull_module.build()

        assert "endSocket" in pushpull_module.sockets

    def test_is_built_flag(self, pushpull_module):
        """is_built returns True after build."""
        pushpull_module.create_guides()
        assert not pushpull_module.is_built
        pushpull_module.build()
        assert pushpull_module.is_built


class TestPushPullSettings:
    """Test settings for pushpull module."""

    def test_extractAxis_setting(self, pushpull_module):
        """Module accepts extractAxis setting."""
        pushpull_module.set_settings({"extractAxis": "Y"})
        assert pushpull_module.get_setting("extractAxis") == "Y"

    def test_translateAxis_setting(self, pushpull_module):
        """Module accepts translateAxis setting."""
        pushpull_module.set_settings({"translateAxis": "Z"})
        assert pushpull_module.get_setting("translateAxis") == "Z"

    def test_extractMultiplier_setting(self, pushpull_module):
        """Module accepts extractMultiplier setting."""
        pushpull_module.set_settings({"extractMultiplier": 1.0})
        assert pushpull_module.get_setting("extractMultiplier") == 1.0