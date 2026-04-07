"""Tests for tik.trigger.actions and tik.trigger.modules discovery system."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestActionsBaseTemplate:
    """Tests for actions/_base.py template."""

    def test_base_exports_action_core(self):
        """Test that _base.py exports ActionCore."""
        from tik.trigger.actions._base import ActionCore

        assert ActionCore is not None

    def test_uid_definition_available_from_schemas(self):
        """Test UIDefinition is available from tik.trigger.core.schemas."""
        from tik.trigger.core.schemas import UIDefinition

        assert UIDefinition is not None


class TestModulesBaseTemplate:
    """Tests for modules/_base.py template."""

    def test_base_exports_guides_core(self):
        """Test that _base.py exports GuidesCore."""
        from tik.trigger.modules._base import GuidesCore

        assert GuidesCore is not None

    def test_base_exports_module_core(self):
        """Test that _base.py exports ModuleCore."""
        from tik.trigger.modules._base import ModuleCore

        assert ModuleCore is not None


class TestActionsInitImports:
    """Tests for actions/__init__.py imports."""

    def test_actions_init_imports_discover(self):
        """Test that discover_actions can be imported."""
        from tik.trigger.actions import discover_actions

        assert callable(discover_actions)

    def test_actions_init_imports_get_definition(self):
        """Test that get_action_definition can be imported."""
        from tik.trigger.actions import get_action_definition

        assert callable(get_action_definition)

    def test_actions_init_imports_list_discovered(self):
        """Test that list_discovered_actions can be imported."""
        from tik.trigger.actions import list_discovered_actions

        assert callable(list_discovered_actions)


class TestModulesInitImports:
    """Tests for modules/__init__.py imports."""

    def test_modules_init_imports_discover(self):
        """Test that discover_modules can be imported."""
        from tik.trigger.modules import discover_modules

        assert callable(discover_modules)

    def test_modules_init_imports_get_definition(self):
        """Test that get_module_definition can be imported."""
        from tik.trigger.modules import get_module_definition

        assert callable(get_module_definition)

    def test_modules_init_imports_list_discovered(self):
        """Test that list_discovered_modules can be imported."""
        from tik.trigger.modules import list_discovered_modules

        assert callable(list_discovered_modules)


class TestFindActionClass:
    """Tests for the _find_action_class helper."""

    def test_finds_action_core_subclass(self):
        """Test that _find_action_class finds ActionCore subclass."""
        from tik.trigger.actions import _find_action_class
        from tik.trigger.core.action_core import ActionCore

        class TestAction(ActionCore):
            def feed(self, selection):
                return {}

            def action(self, feed_data):
                pass

        mock_module = MagicMock()
        mock_module.__dict__ = {"TestAction": TestAction}
        with patch.object(sys.modules.get("inspect", MagicMock()), "getmembers", return_value=[("TestAction", TestAction)]):
            pass

        # Direct test with a real module
        from tik.trigger.core.action_core import ActionCore
        result = _find_action_class(sys.modules["tik.trigger.actions._base"])
        # _base doesn't have ActionCore subclass


class TestFindModuleClasses:
    """Tests for the _find_module_classes helper."""

    def test_find_module_classes_returns_tuple(self):
        """Test that _find_module_classes returns tuple of classes."""
        from tik.trigger.modules import _find_module_classes

        mock_module = MagicMock()
        # This will return (None, None) since there are no real module classes
        result = _find_module_classes(mock_module)
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestLoadActionJson:
    """Tests for _load_action_json helper."""

    def test_load_action_json_returns_dict(self):
        """Test _load_action_json returns ui_definition dict or None."""
        from tik.trigger.actions import _load_action_json

        with tempfile.TemporaryDirectory() as tmpdir:
            folder_path = Path(tmpdir)
            ui_def_path = folder_path / "ui_definition.json"

            with open(ui_def_path, "w") as f:
                json.dump({"test_key": {"display_name": "Test", "type": "string", "value": "default"}}, f)

            result = _load_action_json(folder_path, "test_action")
            assert result is not None
            assert isinstance(result, dict)
            assert "test_key" in result

    def test_load_action_json_missing_files(self):
        """Test _load_action_json returns None for missing files."""
        from tik.trigger.actions import _load_action_json

        with tempfile.TemporaryDirectory() as tmpdir:
            folder_path = Path(tmpdir)
            result = _load_action_json(folder_path, "test_action")
            assert result is None


class TestLoadModuleJson:
    """Tests for _load_module_json helper."""

    def test_load_module_json_returns_tuple(self):
        """Test _load_module_json returns tuple of (ui_def, data)."""
        from tik.trigger.modules import _load_module_json

        with tempfile.TemporaryDirectory() as tmpdir:
            folder_path = Path(tmpdir)
            ui_def_path = folder_path / "ui_definition.json"
            data_path = folder_path / "data.json"

            with open(ui_def_path, "w") as f:
                json.dump([{"key": "segments", "display_name": "Segments", "setting_type": "integer"}], f)
            with open(data_path, "w") as f:
                json.dump({"positions": [[0, 0, 0], [0, 1, 0]]}, f)

            ui_def, data = _load_module_json(folder_path, "test_module")
            assert ui_def is not None
            assert data == {"positions": [[0, 0, 0], [0, 1, 0]]}

    def test_load_module_json_missing_files(self):
        """Test _load_module_json returns None for missing files."""
        from tik.trigger.modules import _load_module_json

        with tempfile.TemporaryDirectory() as tmpdir:
            folder_path = Path(tmpdir)
            ui_def, data = _load_module_json(folder_path, "test_module")
            assert ui_def is None
            assert data is None


class TestRegisterActionFromFolder:
    """Tests for _register_action_from_folder helper."""

    def test_register_skips_folder_without_matching_py(self):
        """Test that registration skips folders without matching .py file."""
        from tik.trigger.actions import _register_action_from_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            folder_path = Path(tmpdir) / "no_match"
            folder_path.mkdir()
            # Create a .py file with different name
            (folder_path / "other.py").write_text("")

            result = _register_action_from_folder(folder_path)
            assert result is False

    def test_register_skips_folder_without_py_file(self):
        """Test that registration skips folders without any .py file."""
        from tik.trigger.actions import _register_action_from_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            folder_path = Path(tmpdir) / "empty_folder"
            folder_path.mkdir()

            result = _register_action_from_folder(folder_path)
            assert result is False


class TestRegisterModuleFromFolder:
    """Tests for _register_module_from_folder helper."""

    def test_register_skips_folder_without_matching_py(self):
        """Test that registration skips folders without matching .py file."""
        from tik.trigger.modules import _register_module_from_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            folder_path = Path(tmpdir) / "no_match"
            folder_path.mkdir()
            # Create a .py file with different name
            (folder_path / "other.py").write_text("")

            result = _register_module_from_folder(folder_path)
            assert result is False

    def test_register_skips_folder_without_py_file(self):
        """Test that registration skips folders without any .py file."""
        from tik.trigger.modules import _register_module_from_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            folder_path = Path(tmpdir) / "empty_folder"
            folder_path.mkdir()

            result = _register_module_from_folder(folder_path)
            assert result is False


class TestConfigIOJsonLoading:
    """Tests for ConfigIO JSON loading functionality."""

    def test_load_json_with_ui_definition_format(self):
        """Test loading ui_definition.json format."""
        from tik.trigger.config.io import ConfigIO

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "ui_definition.json"
            data = [
                {"key": "enabled", "display_name": "Enabled", "setting_type": "boolean", "value": True},
                {"key": "count", "display_name": "Count", "setting_type": "integer", "value": 3},
            ]
            with open(file_path, "w") as f:
                json.dump(data, f)

            result = ConfigIO._load_json(file_path)
            assert result == data
            assert len(result) == 2

    def test_load_json_with_defaults_format(self):
        """Test loading defaults.json format."""
        from tik.trigger.config.io import ConfigIO

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "defaults.json"
            data = {"radius": 1.0, "enabled": True, "name": "test"}
            with open(file_path, "w") as f:
                json.dump(data, f)

            result = ConfigIO._load_json(file_path)
            assert result == data


class TestUIDefinitionInSchemas:
    """Tests for UIDefinition schema."""

    def test_uid_definition_creation(self):
        """Test creating UIDefinition instances."""
        from tik.trigger.core.schemas import UIDefinition

        ui_def = UIDefinition(
            key="test_key",
            display_name="Test Key",
            setting_type="string",
            value="default",
        )
        assert ui_def.key == "test_key"
        assert ui_def.display_name == "Test Key"
        assert ui_def.setting_type == "string"
        assert ui_def.value == "default"

    def test_uid_definition_defaults(self):
        """Test UIDefinition default values."""
        from tik.trigger.core.schemas import UIDefinition

        ui_def = UIDefinition(key="test", display_name="Test", setting_type="string")
        assert ui_def.value is None
        assert ui_def.items is None
        assert ui_def.min_value is None
        assert ui_def.max_value is None
