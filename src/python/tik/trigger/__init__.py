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

from tik.trigger.core import (
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

VERSION = "0.2.0"


def load_plugins() -> None:
    """Discover the built-in modules and actions, then every external plugin root."""
    import tik.trigger.actions as actions_pkg
    import tik.trigger.modules as modules_pkg
    from tik.trigger.core import discovery

    discovery.discover(modules_pkg.__name__, modules_pkg.__path__)
    discovery.discover(actions_pkg.__name__, actions_pkg.__path__)
    _register_reference_vcs()
    discovery.discover_external(discovery.plugin_paths())


def _register_reference_vcs() -> None:
    """Register the shipped folder provider (registering twice is a no-op).

    It is inert unless ``TRIGGER_FOLDER_VCS`` names a folder that exists, so a
    studio with a real system never notices it; without one it is the working
    example the integrator's guide quotes.
    """
    from tik.trigger.vcs import register_provider
    from tik.trigger.vcs.folder import FolderProvider

    register_provider("folder")(FolderProvider)


def add_plugin_path(path) -> None:
    """Register an external plugin root (``<root>/<name>/<name>.py``)."""
    from tik.trigger.core import discovery

    discovery.add_plugin_path(path)


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
    "add_plugin_path",
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
    "VERSION",
    "get_action",
    "get_module",
    "list_actions",
    "list_modules",
    "load_plugins",
    "register_action",
    "register_module",
]
