"""Tests for tik.trigger.core.registry module."""

import pytest


class TestRegistryDecorators:
    """Tests for register_action and register_module decorators."""

    def setup_method(self):
        """Clear registries before each test."""
        from tik.trigger.core.registry import clear_registries

        clear_registries()

    def teardown_method(self):
        """Clear registries after each test."""
        from tik.trigger.core.registry import clear_registries

        clear_registries()

    def test_register_action_decorator(self):
        """Test that @register_action decorates and registers a class."""
        from tik.trigger.core.action_core import ActionCore
        from tik.trigger.core.registry import register_action

        @register_action("test_action")
        class TestAction(ActionCore):
            def feed(self, selection):
                return {}

            def action(self, feed_data):
                pass

        from tik.trigger.core.registry import get_action

        retrieved = get_action("test_action")
        assert retrieved is TestAction

    def test_register_module_decorator(self):
        """Test that @register_module decorates and registers a class."""
        from tik.trigger.core.module_core import GuidesCore, ModuleCore
        from tik.trigger.core.registry import register_module

        # Define the guide class first
        @register_module("test_module_guide")
        class TestGuides(GuidesCore):
            def create_guides(self):
                pass

            def update_guide(self, index, guide_data):
                pass

            def delete_guides(self):
                pass

        # Define the module class - it references the guide via _guide_class
        @register_module("test_module")
        class TestModule(ModuleCore):
            _guide_class = TestGuides

            def build(self):
                pass

            def delete(self):
                pass

            def mirror(self, source_guide_names):
                pass

        from tik.trigger.core.registry import get_module

        # Should return the module class
        retrieved = get_module("test_module")
        assert retrieved is TestModule

    def test_duplicate_action_raises(self):
        """Test that registering duplicate action raises error."""
        from tik.trigger.core.action_core import ActionCore
        from tik.trigger.core.exceptions import DuplicateRegistrationError
        from tik.trigger.core.registry import register_action

        @register_action("dup_action")
        class FirstAction(ActionCore):
            def feed(self, selection):
                return {}

            def action(self, feed_data):
                pass

        with pytest.raises(DuplicateRegistrationError) as exc_info:

            @register_action("dup_action")
            class SecondAction(ActionCore):
                def feed(self, selection):
                    return {}

                def action(self, feed_data):
                    pass

        assert exc_info.value.name == "dup_action"
        assert exc_info.value.kind == "action"

    def test_duplicate_module_raises(self):
        """Test that registering duplicate module raises error."""
        from tik.trigger.core.module_core import GuidesCore, ModuleCore
        from tik.trigger.core.exceptions import DuplicateRegistrationError
        from tik.trigger.core.registry import register_module

        @register_module("dup_module")
        class FirstGuides(GuidesCore):
            def create_guides(self):
                pass

            def update_guide(self, index, guide_data):
                pass

            def delete_guides(self):
                pass

        with pytest.raises(DuplicateRegistrationError) as exc_info:

            @register_module("dup_module")
            class SecondGuides(GuidesCore):
                def create_guides(self):
                    pass

                def update_guide(self, index, guide_data):
                    pass

                def delete_guides(self):
                    pass

        assert exc_info.value.name == "dup_module"
        assert exc_info.value.kind == "module"


class TestRegistryGetters:
    """Tests for get_action and get_module functions."""

    def setup_method(self):
        """Clear registries before each test."""
        from tik.trigger.core.registry import clear_registries

        clear_registries()

    def teardown_method(self):
        """Clear registries after each test."""
        from tik.trigger.core.registry import clear_registries

        clear_registries()

    def test_get_action_success(self):
        """Test successful action retrieval."""
        from tik.trigger.core.action_core import ActionCore
        from tik.trigger.core.registry import get_action, register_action

        @register_action("my_action")
        class MyAction(ActionCore):
            def feed(self, selection):
                return {}

            def action(self, feed_data):
                pass

        result = get_action("my_action")
        assert result is MyAction

    def test_get_module_success(self):
        """Test successful module retrieval."""
        from tik.trigger.core.module_core import GuidesCore, ModuleCore
        from tik.trigger.core.registry import get_module, register_module

        @register_module("my_guide")
        class MyGuides(GuidesCore):
            def create_guides(self):
                pass

            def update_guide(self, index, guide_data):
                pass

            def delete_guides(self):
                pass

        @register_module("my_module")
        class MyModule(ModuleCore):
            _guide_class = MyGuides

            def build(self):
                pass

            def delete(self):
                pass

            def mirror(self, source_guide_names):
                pass

        result = get_module("my_module")
        assert result is MyModule

    def test_get_action_not_found(self):
        """Test that getting nonexistent action raises NotFoundError."""
        from tik.trigger.core.exceptions import NotFoundError
        from tik.trigger.core.registry import get_action

        with pytest.raises(NotFoundError) as exc_info:
            get_action("nonexistent_action")

        assert exc_info.value.name == "nonexistent_action"
        assert exc_info.value.kind == "action"

    def test_get_module_not_found(self):
        """Test that getting nonexistent module raises NotFoundError."""
        from tik.trigger.core.exceptions import NotFoundError
        from tik.trigger.core.registry import get_module

        with pytest.raises(NotFoundError) as exc_info:
            get_module("nonexistent_module")

        assert exc_info.value.name == "nonexistent_module"
        assert exc_info.value.kind == "module"


class TestRegistryListers:
    """Tests for list_actions and list_modules functions."""

    def setup_method(self):
        """Clear registries before each test."""
        from tik.trigger.core.registry import clear_registries

        clear_registries()

    def teardown_method(self):
        """Clear registries after each test."""
        from tik.trigger.core.registry import clear_registries

        clear_registries()

    def test_list_actions_empty(self):
        """Test listing actions when none registered."""
        from tik.trigger.core.registry import list_actions

        assert list_actions() == []

    def test_list_modules_empty(self):
        """Test listing modules when none registered."""
        from tik.trigger.core.registry import list_modules

        assert list_modules() == []

    def test_list_actions_after_registration(self):
        """Test listing actions after registration."""
        from tik.trigger.core.action_core import ActionCore
        from tik.trigger.core.registry import list_actions, register_action

        @register_action("action_one")
        class ActionOne(ActionCore):
            def feed(self, selection):
                return {}

            def action(self, feed_data):
                pass

        @register_action("action_two")
        class ActionTwo(ActionCore):
            def feed(self, selection):
                return {}

            def action(self, feed_data):
                pass

        actions = list_actions()
        assert "action_one" in actions
        assert "action_two" in actions
        assert len(actions) == 2

    def test_list_modules_after_registration(self):
        """Test listing modules after registration."""
        from tik.trigger.core.module_core import GuidesCore, ModuleCore
        from tik.trigger.core.registry import list_modules, register_module

        @register_module("mod_one_guide")
        class ModOneGuides(GuidesCore):
            def create_guides(self):
                pass

            def update_guide(self, index, guide_data):
                pass

            def delete_guides(self):
                pass

        @register_module("mod_one")
        class ModOne(ModuleCore):
            _guide_class = ModOneGuides

            def build(self):
                pass

            def delete(self):
                pass

            def mirror(self, source_guide_names):
                pass

        @register_module("mod_two_guide")
        class ModTwoGuides(GuidesCore):
            def create_guides(self):
                pass

            def update_guide(self, index, guide_data):
                pass

            def delete_guides(self):
                pass

        @register_module("mod_two")
        class ModTwo(ModuleCore):
            _guide_class = ModTwoGuides

            def build(self):
                pass

            def delete(self):
                pass

            def mirror(self, source_guide_names):
                pass

        modules = list_modules()
        assert "mod_one_guide" in modules
        assert "mod_two_guide" in modules
        assert "mod_one" in modules
        assert "mod_two" in modules


class TestRegistryCheckers:
    """Tests for is_action_registered and is_module_registered functions."""

    def setup_method(self):
        """Clear registries before each test."""
        from tik.trigger.core.registry import clear_registries

        clear_registries()

    def teardown_method(self):
        """Clear registries after each test."""
        from tik.trigger.core.registry import clear_registries

        clear_registries()

    def test_is_action_registered_false(self):
        """Test is_action_registered returns False for unregistered."""
        from tik.trigger.core.registry import is_action_registered

        assert is_action_registered("not_registered") is False

    def test_is_action_registered_true(self):
        """Test is_action_registered returns True for registered."""
        from tik.trigger.core.action_core import ActionCore
        from tik.trigger.core.registry import is_action_registered, register_action

        @register_action("registered_action")
        class RegisteredAction(ActionCore):
            def feed(self, selection):
                return {}

            def action(self, feed_data):
                pass

        assert is_action_registered("registered_action") is True

    def test_is_module_registered_false(self):
        """Test is_module_registered returns False for unregistered."""
        from tik.trigger.core.registry import is_module_registered

        assert is_module_registered("not_registered") is False

    def test_is_module_registered_true(self):
        """Test is_module_registered returns True for registered."""
        from tik.trigger.core.module_core import GuidesCore, ModuleCore
        from tik.trigger.core.registry import is_module_registered, register_module

        @register_module("registered_guide")
        class RegGuides(GuidesCore):
            def create_guides(self):
                pass

            def update_guide(self, index, guide_data):
                pass

            def delete_guides(self):
                pass

        @register_module("registered_module")
        class RegModule(ModuleCore):
            _guide_class = RegGuides

            def build(self):
                pass

            def delete(self):
                pass

            def mirror(self, source_guide_names):
                pass

        assert is_module_registered("registered_guide") is True
        assert is_module_registered("registered_module") is True


class TestClearRegistries:
    """Tests for clear_registries function."""

    def setup_method(self):
        """Clear registries before each test."""
        from tik.trigger.core.registry import clear_registries

        clear_registries()

    def teardown_method(self):
        """Clear registries after each test."""
        from tik.trigger.core.registry import clear_registries

        clear_registries()

    def test_clear_registries_removes_all(self):
        """Test that clear_registries removes all registrations."""
        from tik.trigger.core.action_core import ActionCore
        from tik.trigger.core.module_core import GuidesCore, ModuleCore
        from tik.trigger.core.registry import (
            clear_registries,
            list_actions,
            list_modules,
            register_action,
            register_module,
        )

        @register_action("temp_action")
        class TempAction(ActionCore):
            def feed(self, selection):
                return {}

            def action(self, feed_data):
                pass

        @register_module("temp_guide")
        class TempGuides(GuidesCore):
            def create_guides(self):
                pass

            def update_guide(self, index, guide_data):
                pass

            def delete_guides(self):
                pass

        @register_module("temp_module")
        class TempModule(ModuleCore):
            _guide_class = TempGuides

            def build(self):
                pass

            def delete(self):
                pass

            def mirror(self, source_guide_names):
                pass

        assert len(list_actions()) == 1
        assert len(list_modules()) == 2

        clear_registries()

        assert len(list_actions()) == 0
        assert len(list_modules()) == 0
