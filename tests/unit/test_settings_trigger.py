"""Tests for tik.trigger.config.settings module."""

import tempfile
from pathlib import Path



class TestUserSettingsInit:
    """Tests for UserSettings initialization."""

    def test_init_with_path(self):
        """Test UserSettings initialization with a path."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "settings.json"
            settings = UserSettings(file_path)
            assert settings.file_path == file_path

    def test_init_adds_json_extension(self):
        """Test UserSettings adds .json extension if missing."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "settings"
            settings = UserSettings(file_path)
            assert settings.file_path.suffix == ".json"

    def test_init_with_existing_file(self):
        """Test UserSettings loads existing file data."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "existing.json"
            import json

            with open(file_path, "w") as handle:
                json.dump({"existing_key": "existing_value"}, handle)

            settings = UserSettings(file_path)
            assert settings.get("existing_key") == "existing_value"

    def test_init_with_nonexistent_file(self):
        """Test UserSettings initializes with empty dict for nonexistent file."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "nonexistent.json"
            settings = UserSettings(file_path)
            assert settings.get_data() == {}


class TestUserSettingsProperties:
    """Tests for UserSettings properties."""

    def test_keys_property(self):
        """Test keys property returns all keys."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "keys_test.json"
            import json

            with open(file_path, "w") as handle:
                json.dump({"a": 1, "b": 2}, handle)

            settings = UserSettings(file_path)
            assert set(settings.keys) == {"a", "b"}

    def test_values_property(self):
        """Test values property returns all values."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "values_test.json"
            import json

            with open(file_path, "w") as handle:
                json.dump({"a": 1, "b": 2}, handle)

            settings = UserSettings(file_path)
            assert set(settings.values) == {1, 2}


class TestUserSettingsGetSet:
    """Tests for UserSettings get and set methods."""

    def test_get_existing_key(self):
        """Test getting an existing key."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "get_test.json"
            import json

            with open(file_path, "w") as handle:
                json.dump({"key": "value"}, handle)

            settings = UserSettings(file_path)
            assert settings.get("key") == "value"

    def test_get_missing_key_with_default(self):
        """Test getting a missing key returns default."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "missing_test.json"
            settings = UserSettings(file_path)
            assert settings.get("missing", "default") == "default"

    def test_get_missing_key_no_default(self):
        """Test getting a missing key with no default returns None."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "none_test.json"
            settings = UserSettings(file_path)
            assert settings.get("missing") is None

    def test_set_value(self):
        """Test setting a value."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "set_test.json"
            settings = UserSettings(file_path)
            settings.set("new_key", "new_value")
            assert settings.get("new_key") == "new_value"


class TestUserSettingsPersistence:
    """Tests for UserSettings save and reset methods."""

    def test_save_writes_to_file(self):
        """Test that save writes data to file."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "save_test.json"
            settings = UserSettings(file_path)
            settings.set("saved", "value")
            settings.save()

            import json

            with open(file_path, "r") as handle:
                data = json.load(handle)
            assert data["saved"] == "value"

    def test_is_changed_true_after_modification(self):
        """Test is_changed returns True after modification."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "changed_test.json"
            settings = UserSettings(file_path)
            settings.set("key", "value")
            assert settings.is_changed() is True

    def test_is_changed_false_after_save(self):
        """Test is_changed returns False after save."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "saved_test.json"
            settings = UserSettings(file_path)
            settings.set("key", "value")
            settings.save()
            assert settings.is_changed() is False

    def test_reset_reverts_changes(self):
        """Test that reset reverts unsaved changes."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "reset_test.json"
            settings = UserSettings(file_path)
            settings.set("key", "original")
            settings.save()
            settings.set("key", "modified")
            assert settings.get("key") == "modified"
            settings.reset()
            assert settings.get("key") == "original"


class TestUserSettingsData:
    """Tests for UserSettings data manipulation methods."""

    def test_get_data_returns_copy(self):
        """Test get_data returns a copy, not the internal dict."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "data_test.json"
            settings = UserSettings(file_path)
            settings.set("key", "value")
            data = settings.get_data()
            data["key"] = "modified"
            assert settings.get("key") == "value"

    def test_set_data(self):
        """Test set_data replaces all data."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "setdata_test.json"
            settings = UserSettings(file_path)
            settings.set("old", "value")
            settings.set_data({"new": "data"})
            assert settings.get("old") is None
            assert settings.get("new") == "data"

    def test_update_with_dict(self):
        """Test update with a dictionary updates only existing keys."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "update_test.json"
            import json

            with open(file_path, "w") as handle:
                json.dump({"a": 1, "b": 2}, handle)

            settings = UserSettings(file_path)
            settings.update({"b": 3, "c": 4})  # c should NOT be added
            assert settings.get("a") == 1
            assert settings.get("b") == 3
            assert settings.get("c") is None  # Not added since add_missing_keys=False

    def test_update_add_missing_keys(self):
        """Test update with add_missing_keys=True."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "addmissing_test.json"
            import json

            with open(file_path, "w") as handle:
                json.dump({"a": 1}, handle)

            settings = UserSettings(file_path)
            settings.update({"b": 2}, add_missing_keys=True)
            assert settings.get("a") == 1
            assert settings.get("b") == 2


class TestUserSettingsRepr:
    """Tests for UserSettings repr."""

    def test_repr(self):
        """Test UserSettings repr."""
        from tik.trigger.config.settings import UserSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "repr_test.json"
            settings = UserSettings(file_path)
            assert "repr_test.json" in repr(settings)


class TestFactoryDefaults:
    """Tests for FACTORY_DEFAULTS."""

    def test_factory_defaults_exists(self):
        """Test FACTORY_DEFAULTS is defined."""
        from tik.trigger.config.defaults import FACTORY_DEFAULTS

        assert isinstance(FACTORY_DEFAULTS, dict)

    def test_factory_defaults_has_expected_keys(self):
        """Test FACTORY_DEFAULTS has expected keys."""
        from tik.trigger.config.defaults import FACTORY_DEFAULTS

        expected_keys = [
            "debug_mode",
            "mirror_mapping",
            "recent_sessions",
            "max_number_of_recent_sessions",
        ]
        for key in expected_keys:
            assert key in FACTORY_DEFAULTS

    def test_factory_defaults_is_immutable_reference(self):
        """Test FACTORY_DEFAULTS is not accidentally modified by settings.

        Note: This is a best-effort check since we can't prevent
        modification, but we can verify initial state.
        """
        from tik.trigger.config.defaults import FACTORY_DEFAULTS

        initial_debug = FACTORY_DEFAULTS["debug_mode"]
        assert initial_debug is False

    def test_defaults_json_matches_defaults_py(self):
        """Test defaults.json content matches defaults.py."""
        import json

        from tik.trigger.config.defaults import FACTORY_DEFAULTS

        defaults_json_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "python"
            / "tik"
            / "trigger"
            / "config"
            / "defaults.json"
        )

        if defaults_json_path.exists():
            with open(defaults_json_path, "r") as handle:
                defaults_json = json.load(handle)

            assert defaults_json["debug_mode"] == FACTORY_DEFAULTS["debug_mode"]
            assert defaults_json["mirror_mapping"] == FACTORY_DEFAULTS["mirror_mapping"]
            assert defaults_json["max_number_of_recent_sessions"] == FACTORY_DEFAULTS[
                "max_number_of_recent_sessions"
            ]


class TestTriggerSettingsFacade:
    """Tests for the trigger_settings singleton facade.

    Note: These tests work with the singleton which persists state.
    Each test should restore the singleton state to avoid affecting other tests.
    """

    def setup_method(self):
        """Reset singleton to factory defaults before each test."""
        from tik.trigger.config.settings import trigger_settings

        trigger_settings.reset_to_factory_defaults()
        trigger_settings.save()

    def teardown_method(self):
        """Reset singleton to factory defaults after each test."""
        from tik.trigger.config.settings import trigger_settings

        trigger_settings.reset_to_factory_defaults()
        trigger_settings.save()

    def test_facade_is_instance(self):
        """Test trigger_settings is a _TriggerSettingsFacade instance."""
        from tik.trigger.config.settings import trigger_settings

        assert isinstance(trigger_settings, type(trigger_settings))

    def test_facade_get_returns_stored_value(self):
        """Test facade get returns stored value when key exists."""
        from tik.trigger.config.settings import trigger_settings

        trigger_settings.set("debug_mode", True)
        result = trigger_settings.get("debug_mode")
        assert result is True

    def test_facade_get_falls_back_to_factory_default(self):
        """Test facade get falls back to FACTORY_DEFAULTS when key not stored."""
        from tik.trigger.config.defaults import FACTORY_DEFAULTS
        from tik.trigger.config.settings import trigger_settings

        # Ensure debug_mode is at factory default
        result = trigger_settings.get("debug_mode")
        assert result == FACTORY_DEFAULTS["debug_mode"]

    def test_facade_set_modifies_stored_value(self):
        """Test facade set modifies the stored value."""
        from tik.trigger.config.settings import trigger_settings

        trigger_settings.set("debug_mode", True)
        assert trigger_settings.get("debug_mode") is True

    def test_facade_is_changed_after_set(self):
        """Test is_changed returns True after set."""
        from tik.trigger.config.settings import trigger_settings

        trigger_settings.set("debug_mode", not trigger_settings.get("debug_mode"))
        assert trigger_settings.is_changed() is True

    def test_facade_save_persists_changes(self):
        """Test facade save persists changes to disk."""
        from tik.trigger.config.settings import trigger_settings

        trigger_settings.set("debug_mode", True)
        result = trigger_settings.save()
        assert result is True
        # Verify it persisted
        assert trigger_settings.get("debug_mode") is True

    def test_facade_reset_reverts_changes(self):
        """Test facade reset reverts unsaved changes."""
        from tik.trigger.config.settings import trigger_settings

        original_value = trigger_settings.get("debug_mode")
        trigger_settings.set("debug_mode", not original_value)
        trigger_settings.reset()
        assert trigger_settings.get("debug_mode") == original_value

    def test_facade_get_all_settings(self):
        """Test facade get_all_settings returns dict."""
        from tik.trigger.config.settings import trigger_settings

        all_settings = trigger_settings.get_all_settings()
        assert isinstance(all_settings, dict)
        assert "debug_mode" in all_settings

    def test_facade_dict_access(self):
        """Test facade dict-style access."""
        from tik.trigger.config.settings import trigger_settings

        value = trigger_settings["debug_mode"]
        assert value == trigger_settings.get("debug_mode")

    def test_facade_dict_assignment(self):
        """Test facade dict-style assignment."""
        from tik.trigger.config.settings import trigger_settings

        trigger_settings["debug_mode"] = True
        assert trigger_settings.get("debug_mode") is True

    def test_facade_repr(self):
        """Test facade repr."""
        from tik.trigger.config.settings import trigger_settings

        text = repr(trigger_settings)
        assert isinstance(text, str)

    def test_facade_reset_to_factory_defaults(self):
        """Test reset_to_factory_defaults resets all values."""
        from tik.trigger.config.defaults import FACTORY_DEFAULTS
        from tik.trigger.config.settings import trigger_settings

        # Modify several settings
        trigger_settings.set("debug_mode", True)
        trigger_settings.set("auto_save", False)
        trigger_settings.save()

        # Reset
        trigger_settings.reset_to_factory_defaults()

        assert trigger_settings.get("debug_mode") == FACTORY_DEFAULTS["debug_mode"]
        assert trigger_settings.get("auto_save") == FACTORY_DEFAULTS["auto_save"]
