"""Exception hierarchy for tik.trigger."""

from __future__ import annotations

from tik.core.fields import FieldValidationError  # re-exported for convenience


class TriggerError(Exception):
    """Base class for all trigger errors."""


class RegistryError(TriggerError):
    """Registry related errors."""


class DuplicateRegistrationError(RegistryError):
    """A module/action name is registered twice."""

    def __init__(self, name: str, kind: str = "item") -> None:
        self.name = name
        self.kind = kind
        super().__init__(f"{kind} '{name}' is already registered.")


class NotFoundError(RegistryError):
    """A module/action name is not registered."""

    def __init__(self, name: str, kind: str = "item") -> None:
        self.name = name
        self.kind = kind
        super().__init__(f"{kind} '{name}' is not registered.")


class SessionError(TriggerError):
    """Session document errors."""


class SessionLoadError(SessionError):
    """The session file could not be read or is invalid."""


class SessionSaveError(SessionError):
    """The session file could not be written."""


class ModuleError(TriggerError):
    """Module related errors."""


class GuideError(ModuleError):
    """Guide creation / reading errors."""


class BuildError(ModuleError):
    """Raised when a module fails to build.

    Attributes:
        instance_id: The failing module instance, when known.
        module_type: The failing module type, when known.
    """

    def __init__(
        self, message: str, instance_id: str = "", module_type: str = ""
    ) -> None:
        self.instance_id = instance_id
        self.module_type = module_type
        super().__init__(message)


class AttachError(BuildError):
    """A socket could not be attached to a plug."""


class ActionError(TriggerError):
    """Action related errors."""


class ActionExecutionError(ActionError):
    """Raised when an action fails while running."""

    def __init__(self, message: str, action_name: str = "") -> None:
        self.action_name = action_name
        super().__init__(message)


__all__ = [
    "TriggerError",
    "RegistryError",
    "DuplicateRegistrationError",
    "NotFoundError",
    "SessionError",
    "SessionLoadError",
    "SessionSaveError",
    "ModuleError",
    "GuideError",
    "BuildError",
    "AttachError",
    "ActionError",
    "ActionExecutionError",
    "FieldValidationError",
]
