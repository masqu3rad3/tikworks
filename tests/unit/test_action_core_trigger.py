"""Tests for tik.trigger.core.action_core module."""

import pytest

from tik.trigger.core.action_core import ActionCore


class ConcreteAction(ActionCore):
    """Concrete implementation of ActionCore for testing."""

    def __init__(self, name=None):
        super().__init__(name)
        self.feed_called = False
        self.action_called = False
        self.last_feed_data = None

    def feed(self, selection):
        self.feed_called = True
        self.last_feed_data = {"selection": selection, "count": len(selection)}
        return self.last_feed_data

    def action(self, feed_data):
        self.action_called = True
        self.last_feed_data = feed_data


class TestActionCoreInit:
    """Tests for ActionCore initialization."""

    def test_action_core_default_name(self):
        """Test ActionCore uses class name as default name."""
        action = ConcreteAction()
        assert action.name == "ConcreteAction"

    def test_action_core_custom_name(self):
        """Test ActionCore accepts custom name."""
        action = ConcreteAction(name="my_custom_action")
        assert action.name == "my_custom_action"

    def test_action_core_default_settings(self):
        """Test ActionCore initializes with empty settings."""
        action = ConcreteAction()
        assert action.settings == {}

    def test_action_core_repr(self):
        """Test ActionCore string representation."""
        action = ConcreteAction(name="test_action")
        assert "ConcreteAction" in repr(action)
        assert "test_action" in repr(action)


class TestActionCoreProperties:
    """Tests for ActionCore properties."""

    def test_action_type_uses_class_name(self):
        """Test action_type property returns class name when _action_name not set."""
        action = ConcreteAction()
        assert action.action_type == "ConcreteAction"

    def test_action_type_uses_custom_name(self):
        """Test action_type property returns custom _action_name when set."""
        from tik.trigger.core.action_core import ActionCore

        class NamedAction(ActionCore):
            _action_name = "my_named_action"

            def feed(self, selection):
                return {}

            def action(self, feed_data):
                pass

        action = NamedAction()
        assert action.action_type == "my_named_action"

    def test_ui_definition_empty_by_default(self):
        """Test ui_definition property returns empty list by default."""
        action = ConcreteAction()
        assert action.ui_definition == []

    def test_defaults_empty_by_default(self):
        """Test defaults property returns empty dict by default."""
        action = ConcreteAction()
        assert action.defaults == {}


class TestActionCoreSettings:
    """Tests for ActionCore settings management."""

    def test_set_settings(self):
        """Test set_settings updates instance settings."""
        action = ConcreteAction()
        action.set_settings({"key1": "value1", "key2": 42})
        assert action.settings["key1"] == "value1"
        assert action.settings["key2"] == 42

    def test_set_settings_returns_copy(self):
        """Test set_settings doesn't return the internal dict."""
        action = ConcreteAction()
        action.set_settings({"key": "value"})
        # Modifying returned dict shouldn't affect internal state
        settings = action.settings
        settings["key"] = "modified"
        assert action.settings["key"] == "value"

    def test_get_setting_existing(self):
        """Test get_setting returns existing key."""
        action = ConcreteAction()
        action.set_settings({"radius": 1.5})
        assert action.get_setting("radius") == 1.5

    def test_get_setting_default(self):
        """Test get_setting returns default when key missing."""
        action = ConcreteAction()
        assert action.get_setting("missing", "default_value") == "default_value"

    def test_get_setting_no_default(self):
        """Test get_setting returns None when key missing and no default."""
        action = ConcreteAction()
        assert action.get_setting("missing") is None

    def test_reset_settings(self):
        """Test reset_settings restores defaults."""
        action = ConcreteAction()
        action.set_settings({"key": "value"})
        action.reset_settings()
        assert action.settings == {}

    def test_settings_returns_copy(self):
        """Test settings property returns a copy."""
        action = ConcreteAction()
        action.set_settings({"key": "value"})
        settings = action.settings
        settings["key"] = "modified"
        assert action.settings["key"] == "value"


class TestActionCoreFeed:
    """Tests for ActionCore feed method."""

    def test_feed_is_called(self):
        """Test that feed method is called and returns data."""
        action = ConcreteAction()
        result = action.feed(["node1", "node2"])
        assert action.feed_called is True
        assert result["count"] == 2
        assert result["selection"] == ["node1", "node2"]

    def test_feed_data_stored(self):
        """Test that feed stores data for action to use."""
        action = ConcreteAction()
        action.feed(["node1"])
        assert action.last_feed_data["count"] == 1


class TestActionCoreAction:
    """Tests for ActionCore action method."""

    def test_action_is_called_with_feed_data(self):
        """Test that action method is called with feed data."""
        action = ConcreteAction()
        feed_data = {"selection": ["node1"], "count": 1}
        action.action(feed_data)
        assert action.action_called is True
        assert action.last_feed_data == feed_data


class TestActionCoreSaveLoad:
    """Tests for ActionCore save_action and load_action methods."""

    def test_save_action_basic(self):
        """Test save_action returns basic structure."""
        action = ConcreteAction(name="test_action")
        action.set_settings({"setting1": "value1"})
        feed_data = {"key": "data"}
        saved = action.save_action(feed_data)

        assert saved["action_type"] == "ConcreteAction"
        assert saved["settings"]["setting1"] == "value1"
        assert saved["feed_data"]["key"] == "data"

    def test_load_action(self):
        """Test load_action restores state."""
        action = ConcreteAction()
        data = {
            "settings": {"loaded_key": "loaded_value"},
        }
        action.load_action(data)
        assert action.settings["loaded_key"] == "loaded_value"


class TestActionCoreValidate:
    """Tests for ActionCore validate method."""

    def test_validate_returns_true_by_default(self):
        """Test validate returns True when not overridden."""
        action = ConcreteAction()
        assert action.validate() is True


class TestActionCoreAbstract:
    """Tests for ActionCore abstract method enforcement."""

    def test_cannot_instantiate_directly(self):
        """Test that ActionCore cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            ActionCore()
        assert "abstract" in str(exc_info.value).lower()

    def test_must_implement_feed(self):
        """Test that subclass without feed raises TypeError on instantiation."""
        from tik.trigger.core.action_core import ActionCore

        class IncompleteAction(ActionCore):
            def action(self, feed_data):
                pass

        with pytest.raises(TypeError):
            IncompleteAction()

    def test_must_implement_action(self):
        """Test that subclass without action raises TypeError on instantiation."""
        from tik.trigger.core.action_core import ActionCore

        class IncompleteAction(ActionCore):
            def feed(self, selection):
                return {}

        with pytest.raises(TypeError):
            IncompleteAction()
