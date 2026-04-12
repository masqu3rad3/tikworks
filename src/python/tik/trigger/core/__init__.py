"""Core framework for tik.trigger.

This package contains the DCC-agnostic foundation for the trigger system:
- ActionCore: Base class for actions
- ModuleCore/GuidesCore: Base classes for modules
- Registry decorators: @register_action, @register_module
- Schemas: Dataclasses for typed data
- Exceptions: Custom exception hierarchy
- IO: Session file I/O handler extending tik.shared.io.IO
"""

from tik.trigger.core.action_core import ActionCore
from tik.trigger.core.exceptions import (
    ActionError,
    ActionExecutionError,
    ActionFeedError,
    BuildError,
    DuplicateRegistrationError,
    GuideError,
    InvalidSessionError,
    ModuleError,
    NotFoundError,
    RegistryError,
    SessionError,
    SessionLoadError,
    SessionSaveError,
    TriggerError,
)
from tik.trigger.core.io import IO, GUIDE_SESSION_EXT, ACTION_SESSION_EXT
from tik.trigger.core.module_core import GuidesCore, ModuleCore
from tik.trigger.core.registry import (
    clear_registries,
    get_action,
    get_module,
    is_action_registered,
    is_module_registered,
    list_actions,
    list_modules,
    register_action,
    register_module,
)
from tik.trigger.core.schemas import (
    ActionDefinition,
    ActionInstanceData,
    GuideData,
    ModuleDefinition,
    ModuleInstanceData,
    SessionData,
    SessionMetadata,
    UIDefinition,
)

__all__ = [
    # Base classes
    "ActionCore",
    "ModuleCore",
    "GuidesCore",
    # IO
    "IO",
    "GUIDE_SESSION_EXT",
    "ACTION_SESSION_EXT",
    # Registry
    "register_action",
    "register_module",
    "get_action",
    "get_module",
    "list_actions",
    "list_modules",
    "is_action_registered",
    "is_module_registered",
    "clear_registries",
    # Schemas
    "GuideData",
    "ModuleInstanceData",
    "ActionInstanceData",
    "SessionData",
    "SessionMetadata",
    "UIDefinition",
    "ActionDefinition",
    "ModuleDefinition",
    # Exceptions
    "TriggerError",
    "RegistryError",
    "DuplicateRegistrationError",
    "NotFoundError",
    "SessionError",
    "InvalidSessionError",
    "SessionSaveError",
    "SessionLoadError",
    "ModuleError",
    "GuideError",
    "BuildError",
    "ActionError",
    "ActionFeedError",
    "ActionExecutionError",
]
