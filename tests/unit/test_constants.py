"""Unit tests for tik.maya.core.constants module."""

from unittest.mock import patch

from maya import cmds

from tik.maya.core.constants import NodeNames, _NodeNamesConfig


class TestNodeNamesConfig:
    """Tests for _NodeNamesConfig class."""

    def test_maya_version_returns_integer(self):
        """Test maya_version property returns an integer."""
        version = NodeNames.maya_version
        assert isinstance(version, int)
        assert version >= 2024  # Minimum supported version

    def test_maya_version_is_cached(self):
        """Test maya_version property caches the result."""
        # Access twice, should return same value
        version1 = NodeNames.maya_version
        version2 = NodeNames.maya_version
        assert version1 == version2

    def test_maya_version_exception_handling(self):
        """Test maya_version defaults to 2026 when cmds.about raises exception."""
        config = _NodeNamesConfig()
        config._cached_version = None

        # Mock cmds.about to raise RuntimeError
        with patch.object(
            cmds, "about", side_effect=RuntimeError("Maya not initialized")
        ):
            version = config.maya_version

        assert version == 2026
        assert config._cached_version == 2026

    def test_maya_version_attribute_error_handling(self):
        """Test maya_version handles AttributeError."""
        config = _NodeNamesConfig()
        config._cached_version = None

        with patch.object(cmds, "about", side_effect=AttributeError("No attribute")):
            version = config.maya_version

        assert version == 2026

    def test_maya_version_value_error_handling(self):
        """Test maya_version handles ValueError from int conversion."""
        config = _NodeNamesConfig()
        config._cached_version = None

        # Mock cmds.about to return a non-integer string
        with patch.object(cmds, "about", return_value="invalid_version"):
            version = config.maya_version

        assert version == 2026

    def test_mult_double_linear_name(self):
        """Test MULT_DOUBLE_LINEAR returns correct name for Maya version."""
        name = NodeNames.MULT_DOUBLE_LINEAR
        if NodeNames.maya_version >= 2026:
            assert name == "multDL"
        else:
            assert name == "multDoubleLinear"

    def test_add_double_linear_name(self):
        """Test ADD_DOUBLE_LINEAR returns correct name for Maya version."""
        name = NodeNames.ADD_DOUBLE_LINEAR
        if NodeNames.maya_version >= 2026:
            assert name == "addDL"
        else:
            assert name == "addDoubleLinear"

    def test_uses_native_math_nodes(self):
        """Test uses_native_math_nodes returns correct value."""
        uses_native = NodeNames.uses_native_math_nodes
        if NodeNames.maya_version >= 2025:
            assert uses_native is True
        else:
            assert uses_native is False

    def test_ensure_lookdevkit_loaded_when_not_loaded(self):
        """Test ensure_lookdevkit_loaded loads plugin when not already loaded."""
        # Create a fresh config instance to test the loading path
        config = _NodeNamesConfig()
        config._lookdevkit_loaded = False

        # Unload lookdevKit if it's loaded (to test the loading path)
        if cmds.pluginInfo("lookdevKit", query=True, loaded=True):
            cmds.unloadPlugin("lookdevKit", force=True)

        # Now call ensure_lookdevkit_loaded
        config.ensure_lookdevkit_loaded()

        # Plugin should now be loaded
        assert cmds.pluginInfo("lookdevKit", query=True, loaded=True)
        assert config._lookdevkit_loaded is True

    def test_ensure_lookdevkit_loaded_skips_when_already_loaded(self):
        """Test ensure_lookdevkit_loaded skips loading when flag is set."""
        config = _NodeNamesConfig()
        config._lookdevkit_loaded = True

        # This should return early without doing anything
        config.ensure_lookdevkit_loaded()

        # Flag should still be True
        assert config._lookdevkit_loaded is True

    def test_ensure_lookdevkit_loaded_when_plugin_already_loaded(self):
        """Test ensure_lookdevkit_loaded when plugin is already loaded in Maya."""
        config = _NodeNamesConfig()
        config._lookdevkit_loaded = False

        # Make sure the plugin is loaded
        if not cmds.pluginInfo("lookdevKit", query=True, loaded=True):
            cmds.loadPlugin("lookdevKit", quiet=True)

        # Call ensure_lookdevkit_loaded - it should check and set the flag
        config.ensure_lookdevkit_loaded()

        assert config._lookdevkit_loaded is True
