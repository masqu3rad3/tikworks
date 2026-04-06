"""Tests for tik.trigger.core.exceptions module."""

import pytest


class TestTriggerError:
    """Tests for the base TriggerError exception."""

    def test_trigger_error_basic(self):
        """Test basic TriggerError instantiation."""
        from tik.trigger.core.exceptions import TriggerError

        err = TriggerError("test message")
        assert str(err) == "test message"
        assert err.cause is None

    def test_trigger_error_with_cause(self):
        """Test TriggerError with underlying cause."""
        from tik.trigger.core.exceptions import TriggerError

        original = ValueError("original error")
        err = TriggerError("contextual message", cause=original)
        assert str(err) == "ValueError: original error"
        assert err.cause is original

    def test_trigger_error_str_without_cause(self):
        """Test TriggerError string representation without cause."""
        from tik.trigger.core.exceptions import TriggerError

        err = TriggerError("simple message")
        assert str(err) == "simple message"


class TestRegistryErrors:
    """Tests for registry-related exceptions."""

    def test_duplicate_registration_error(self):
        """Test DuplicateRegistrationError properties."""
        from tik.trigger.core.exceptions import DuplicateRegistrationError

        err = DuplicateRegistrationError("my_action", "action")
        assert "my_action" in str(err)
        assert err.name == "my_action"
        assert err.kind == "action"

    def test_not_found_error(self):
        """Test NotFoundError properties."""
        from tik.trigger.core.exceptions import NotFoundError

        err = NotFoundError("nonexistent", "module")
        assert "nonexistent" in str(err)
        assert err.name == "nonexistent"
        assert err.kind == "module"


class TestSessionErrors:
    """Tests for session-related exceptions."""

    def test_invalid_session_error(self):
        """Test InvalidSessionError instantiation."""
        from tik.trigger.core.exceptions import InvalidSessionError

        err = InvalidSessionError("Session file is corrupted")
        assert "corrupted" in str(err)

    def test_session_save_error(self):
        """Test SessionSaveError instantiation."""
        from tik.trigger.core.exceptions import SessionSaveError

        err = SessionSaveError("Could not write file")
        assert "write" in str(err)

    def test_session_load_error(self):
        """Test SessionLoadError instantiation."""
        from tik.trigger.core.exceptions import SessionLoadError

        err = SessionLoadError("File not found")
        assert "not found" in str(err)


class TestModuleErrors:
    """Tests for module-related exceptions."""

    def test_module_error(self):
        """Test ModuleError instantiation."""
        from tik.trigger.core.exceptions import ModuleError

        err = ModuleError("Module error occurred")
        assert "occurred" in str(err)

    def test_guide_error(self):
        """Test GuideError instantiation."""
        from tik.trigger.core.exceptions import GuideError

        err = GuideError("Guide not found")
        assert "not found" in str(err)

    def test_build_error(self):
        """Test BuildError instantiation."""
        from tik.trigger.core.exceptions import BuildError

        err = BuildError("Build failed")
        assert "failed" in str(err)


class TestActionErrors:
    """Tests for action-related exceptions."""

    def test_action_error(self):
        """Test ActionError instantiation."""
        from tik.trigger.core.exceptions import ActionError

        err = ActionError("Action error")
        assert "error" in str(err)

    def test_action_feed_error(self):
        """Test ActionFeedError instantiation."""
        from tik.trigger.core.exceptions import ActionFeedError

        err = ActionFeedError("Invalid selection")
        assert "Invalid" in str(err)

    def test_action_execution_error(self):
        """Test ActionExecutionError instantiation."""
        from tik.trigger.core.exceptions import ActionExecutionError

        err = ActionExecutionError("Execution failed")
        assert "failed" in str(err)


class TestExceptionHierarchy:
    """Tests for exception class hierarchy."""

    def test_trigger_error_is_base(self):
        """Test that TriggerError is the base exception."""
        from tik.trigger.core.exceptions import (
            TriggerError,
            RegistryError,
            SessionError,
            ModuleError,
            ActionError,
        )

        assert issubclass(RegistryError, TriggerError)
        assert issubclass(SessionError, TriggerError)
        assert issubclass(ModuleError, TriggerError)
        assert issubclass(ActionError, TriggerError)

    def test_registry_error_hierarchy(self):
        """Test RegistryError hierarchy."""
        from tik.trigger.core.exceptions import (
            RegistryError,
            DuplicateRegistrationError,
            NotFoundError,
        )

        assert issubclass(DuplicateRegistrationError, RegistryError)
        assert issubclass(NotFoundError, RegistryError)

    def test_session_error_hierarchy(self):
        """Test SessionError hierarchy."""
        from tik.trigger.core.exceptions import (
            SessionError,
            InvalidSessionError,
            SessionSaveError,
            SessionLoadError,
        )

        assert issubclass(InvalidSessionError, SessionError)
        assert issubclass(SessionSaveError, SessionError)
        assert issubclass(SessionLoadError, SessionError)

    def test_module_error_hierarchy(self):
        """Test ModuleError hierarchy."""
        from tik.trigger.core.exceptions import ModuleError, GuideError, BuildError

        assert issubclass(GuideError, ModuleError)
        assert issubclass(BuildError, ModuleError)

    def test_action_error_hierarchy(self):
        """Test ActionError hierarchy."""
        from tik.trigger.core.exceptions import (
            ActionError,
            ActionFeedError,
            ActionExecutionError,
        )

        assert issubclass(ActionFeedError, ActionError)
        assert issubclass(ActionExecutionError, ActionError)
