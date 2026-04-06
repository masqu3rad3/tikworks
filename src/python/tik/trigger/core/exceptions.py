"""Custom exception hierarchy for tik.trigger."""

from typing import Optional


class TriggerError(Exception):
    """Base exception for all tik.trigger errors."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self._cause = cause

    @property
    def cause(self) -> Optional[Exception]:
        """Return the underlying cause of this exception."""
        return self._cause

    def __str__(self) -> str:
        if self._cause:
            return f"{self._cause.__class__.__name__}: {str(self._cause)}"
        return super().__str__()


class RegistryError(TriggerError):
    """Raised when action/module registration fails."""

    pass


class DuplicateRegistrationError(RegistryError):
    """Raised when attempting to register an already-registered action or module."""

    def __init__(self, name: str, kind: str) -> None:
        super().__init__(f"{kind} '{name}' is already registered.")
        self._name = name
        self._kind = kind

    @property
    def name(self) -> str:
        """Return the duplicate name."""
        return self._name

    @property
    def kind(self) -> str:
        """Return the registry kind ('action' or 'module')."""
        return self._kind


class NotFoundError(RegistryError):
    """Raised when a requested action or module is not found."""

    def __init__(self, name: str, kind: str) -> None:
        super().__init__(f"{kind} '{name}' not found in registry.")
        self._name = name
        self._kind = kind

    @property
    def name(self) -> str:
        """Return the missing name."""
        return self._name

    @property
    def kind(self) -> str:
        """Return the registry kind ('action' or 'module')."""
        return self._kind


class SessionError(TriggerError):
    """Base exception for session-related errors."""

    pass


class InvalidSessionError(SessionError):
    """Raised when a session is invalid or corrupted."""

    pass


class SessionSaveError(SessionError):
    """Raised when saving a session fails."""

    pass


class SessionLoadError(SessionError):
    """Raised when loading a session fails."""

    pass


class ModuleError(TriggerError):
    """Base exception for module-related errors."""

    pass


class GuideError(ModuleError):
    """Raised when guide operations fail."""

    pass


class BuildError(ModuleError):
    """Raised when rig building fails."""

    pass


class ActionError(TriggerError):
    """Base exception for action-related errors."""

    pass


class ActionFeedError(ActionError):
    """Raised when action feed validation fails."""

    pass


class ActionExecutionError(ActionError):
    """Raised when action execution fails."""

    pass
