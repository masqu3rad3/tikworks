"""DCC-agnostic core of tik.trigger.

Nothing in this package imports Maya or Qt.
"""

from tik.core.fields import (
    BoolField,
    ChoiceField,
    DictField,
    Field,
    FileField,
    FloatField,
    IntField,
    ListField,
    NodeRefField,
    StringField,
    VectorField,
)
from tik.core.side import Side

from . import versioning
from .action import Action, ActionContext
from .document import ActionNode, Document
from .backend import Backend
from .builder import AFTERLIFE_MODES, Builder, BuildReport
from .context import BuildContext, GuideContext, RigGroups
from .events import ERROR, LOG, PROGRESS, EventBus
from .exceptions import (
    ActionError,
    ActionExecutionError,
    AttachError,
    BuildError,
    DuplicateRegistrationError,
    FieldValidationError,
    GuideError,
    ModuleError,
    NotFoundError,
    RegistryError,
    SessionError,
    SessionLoadError,
    SessionSaveError,
    TriggerError,
)
from .manifest import Guides
from .module import Module
from .registry import (
    clear_registries,
    get_action,
    get_module,
    is_action_registered,
    is_module_registered,
    iter_actions,
    iter_modules,
    list_actions,
    list_modules,
    register_action,
    register_module,
    unregister_action,
    unregister_module,
)
from .schemas import (
    SCHEMA_VERSION,
    ActionInstance,
    GuidePose,
    ModuleInstance,
    ParentRef,
    RigDocument,
    order_instances,
)

__all__ = [
    "Action",
    "ActionContext",
    "ActionNode",
    "Document",
    "versioning",
    "Backend",
    "Builder",
    "BuildReport",
    "AFTERLIFE_MODES",
    "BuildContext",
    "GuideContext",
    "RigGroups",
    "EventBus",
    "PROGRESS",
    "LOG",
    "ERROR",
    "Guides",
    "Module",
    "Side",
    "Field",
    "FileField",
    "DictField",
    "IntField",
    "FloatField",
    "BoolField",
    "StringField",
    "ChoiceField",
    "VectorField",
    "ListField",
    "NodeRefField",
    "register_action",
    "register_module",
    "get_action",
    "get_module",
    "list_actions",
    "list_modules",
    "iter_actions",
    "iter_modules",
    "is_action_registered",
    "is_module_registered",
    "unregister_action",
    "unregister_module",
    "clear_registries",
    "SCHEMA_VERSION",
    "GuidePose",
    "ParentRef",
    "ModuleInstance",
    "ActionInstance",
    "RigDocument",
    "order_instances",
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
