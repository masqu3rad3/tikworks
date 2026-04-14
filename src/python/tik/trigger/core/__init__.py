"""Core framework for tik.trigger.

This package contains the DCC-agnostic foundation for the trigger system:
- ActionCore: Base class for actions
- RigModule: Unified base class for modules (guide + build)
- Registry decorators: @register_action, @register_module
- Schemas: Dataclasses for typed data
- Socket/Plug: Connection point data classes
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
from tik.trigger.core.rig_module import RigModule
from tik.trigger.core.schemas import (
    ActionDefinition,
    ActionInstanceData,
    ConnectionData,
    GuideData,
    ModuleDefinition,
    ModuleInstanceData,
    SessionData,
    SessionMetadata,
    UIDefinition,
)
from tik.trigger.core.socket_data import JointType, ModuleConnectors, Plug, Socket
from tik.trigger.core import module_registry

# Alias module_registry items to avoid name conflicts with registry module
MODULES = module_registry.MODULES
MODULE_TYPE_ATTR = module_registry.MODULE_TYPE_ATTR
JOINT_ROLE_ATTR = module_registry.JOINT_ROLE_ATTR
MODULE_INSTANCE_ATTR = module_registry.MODULE_INSTANCE_ATTR
JointRole = module_registry.JointRole
ModuleRegistry = module_registry.ModuleRegistry
is_registered = module_registry.is_registered
register_module_type = module_registry.register_module_type

__all__ = [
    # Base classes
    "ActionCore",
    "ModuleCore",
    "GuidesCore",
    "RigModule",
    # Connection points
    "Plug",
    "Socket",
    "ModuleConnectors",
    "JointType",
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
    "ConnectionData",
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
