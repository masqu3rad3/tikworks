"""tik.trigger — modular rigging framework built on tik.maya.

Quick start (Maya)::

    import tik.trigger as trigger

    trigger.load_plugins()
    scene = trigger.GuideScene()
    scene.add("base", name="body")
    trigger.Builder().build()

Importing this package does not import Maya; constructing a ``GuideScene``
or a ``Builder`` does.
"""

from tik.trigger.core import (  # noqa: F401 - public API
    Action,
    ActionContext,
    BuildError,
    EventBus,
    GuideLayout,
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


def load_plugins() -> None:
    """Discover (and re-register if needed) the built-in modules and actions."""
    import tik.trigger.actions as actions_pkg
    import tik.trigger.modules as modules_pkg
    from tik.trigger.core.discovery import discover

    discover(modules_pkg.__name__, modules_pkg.__path__)
    discover(actions_pkg.__name__, actions_pkg.__path__)


_MAYA_NAMES = {
    "Builder": "tik.trigger.maya.build",
    "BuildReport": "tik.trigger.maya.build",
    "AFTERLIFE_MODES": "tik.trigger.maya.build",
    "GuideScene": "tik.trigger.guides",
    "GuideHandle": "tik.trigger.guides",
    "Session": "tik.trigger.session",
    "ActionHandle": "tik.trigger.session",
}


def __getattr__(name: str):
    """Resolve the Maya-touching names on first use, so importing is cheap."""
    import importlib

    module = _MAYA_NAMES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module), name)


__all__ = [
    "Action",
    "ActionContext",
    "ActionHandle",
    "AFTERLIFE_MODES",
    "BuildError",
    "Builder",
    "BuildReport",
    "EventBus",
    "GuideHandle",
    "GuideScene",
    "GuideLayout",
    "Module",
    "Session",
    "Side",
    "TriggerError",
    "get_action",
    "get_module",
    "list_actions",
    "list_modules",
    "load_plugins",
    "register_action",
    "register_module",
]
