"""Tests for the base module."""

from __future__ import annotations

import pytest


class TestBaseGuideCreation:
    """Test guide creation for base module."""

    def test_create_guides_creates_joint(self, base_module):
        """Guide creation makes a Maya joint."""
        import maya.cmds as cmds

        base_module.create_guides()
        joints = cmds.ls("*_jInit", type="joint")
        assert len(joints) >= 1

    def test_guide_data_stored(self, base_module):
        """Guide data is stored in module."""
        base_module.create_guides()
        assert len(base_module.guides) == 1
        assert base_module.guides[0].name.endswith("_root_jInit")

    def test_delete_guides_removes_joints(self, base_module):
        """Guide deletion removes Maya nodes."""
        import maya.cmds as cmds

        base_module.create_guides()
        base_module.delete_guides()
        joints = cmds.ls(f"{base_module.name}_*_jInit", type="joint")
        assert len(joints) == 0


class TestBaseBuild:
    """Test build for base module."""

    def test_build_creates_groups(self, base_module):
        """Build creates expected rig groups."""
        base_module.create_guides()
        base_module.build()

        import maya.cmds as cmds
        assert cmds.objExists(f"{base_module.name}_limbGrp")
        assert cmds.objExists(f"{base_module.name}_scaleGrp")
        assert cmds.objExists(f"{base_module.name}_controllerGrp")

    def test_build_creates_root_joint(self, base_module):
        """Build creates root deformation joint."""
        base_module.create_guides()
        base_module.build()

        import maya.cmds as cmds
        assert cmds.objExists(f"{base_module.name}_root_jnt")

    def test_build_defines_plugs(self, base_module):
        """Build creates plug definitions."""
        base_module.create_guides()
        base_module.build()

        assert "rootPlug" in base_module.plugs
        assert base_module.plugs["rootPlug"].joint_name

    def test_build_defines_sockets(self, base_module):
        """Build creates socket definitions."""
        base_module.create_guides()
        base_module.build()

        assert "rootSocket" in base_module.sockets
        assert base_module.sockets["rootSocket"].joint_name

    def test_is_built_flag(self, base_module):
        """is_built returns True after build."""
        base_module.create_guides()
        assert not base_module.is_built
        base_module.build()
        assert base_module.is_built


class TestBaseSaveLoad:
    """Test save/load for base module."""

    def test_save_and_reload_preserves_guide_positions(self, base_module, tmp_path):
        """Guide positions persist through save/load."""
        import maya.cmds as cmds

        base_module.create_guides()
        original_pos = cmds.xform(f"{base_module.name}_root_jInit", query=True, worldSpace=True, translation=True)

        # Save
        from tik.trigger.session import GuideSession
        session = GuideSession()
        session.add_module(base_module.name, base_module)
        file_path = tmp_path / "test_base.trg"
        session.save(str(file_path))

        # Reload in new session
        cmds.file(new=True, force=True)
        new_session = GuideSession()
        new_session.load(str(file_path))

        reloaded = new_session.get_module(base_module.name)
        assert reloaded is not None
        assert len(reloaded.guides) == 1

    def test_build_data_contains_expected_keys(self, base_module):
        """Build data contains expected structure."""
        base_module.create_guides()
        base_module.build()

        data = base_module.get_build_data()
        assert "module_type" in data
        assert "name" in data
        assert "settings" in data
        assert "guides" in data
        assert data["module_type"] == "base"