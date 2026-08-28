"""tik.trigger — modular rigging framework built on tik.maya.

Quick start (Maya)::

    import tik.trigger as trigger

    backend = trigger.maya_backend()
    backend.create_guides(trigger.get_module("base")(name="body"))
    trigger.Builder(backend).build()

Importing this package does not import Maya; ``maya_backend()`` does.
"""

from tik.trigger.core import (  # noqa: F401 - public API
    Action,
    ActionContext,
    BuildError,
    Builder,
    BuildReport,
    EventBus,
    Guides,
    Module,
    Side,
    TriggerError,
    get_action,
    get_module,
    list_actions,
    list_modules,
    register_action,
    register_module,
)
from tik.trigger.session import RigSession  # noqa: F401


def load_plugins() -> None:
    """Discover the built-in modules and actions."""
    import tik.trigger.actions  # noqa: F401
    import tik.trigger.modules  # noqa: F401


def maya_backend():
    """Return a ``MayaBackend`` (imports Maya lazily) with plugins loaded."""
    from tik.trigger.backends.maya import MayaBackend

    load_plugins()
    return MayaBackend()


__all__ = [
    "Action",
    "ActionContext",
    "BuildError",
    "Builder",
    "BuildReport",
    "EventBus",
    "Guides",
    "Module",
    "RigSession",
    "Side",
    "TriggerError",
    "get_action",
    "get_module",
    "list_actions",
    "list_modules",
    "load_plugins",
    "maya_backend",
    "register_action",
    "register_module",
]
