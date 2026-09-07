"""Animator tools for a built trigger rig.

An animator tool reads the rig, never the session: everything a switch needs is
already on the built nodes -- the ``pivotPreset`` enum, the ``trg_*`` tags -- so
this package may not import ``trigger.session``, the documents, the guides or
``trigger.ui`` (``tests/unit/test_import_boundaries.py``). The rigger's
application and the animator's tools cannot entangle, whatever either grows into.
"""

from .context import Control, SwitchContext
from .registry import (
    clear_switches,
    get_switch,
    iter_switches,
    register_switch,
    unregister_switch,
)
from .switch import Switch

__all__ = [
    "Control",
    "Switch",
    "SwitchContext",
    "clear_switches",
    "get_switch",
    "iter_switches",
    "register_switch",
    "unregister_switch",
    "show",
]


def show(dockable: bool = True):
    """Open (or re-open) the single Switches window.

    Imports live inside the function: this package is imported by tests that
    run without a ``QApplication``, and reaching Qt at module scope would make
    that impossible.
    """
    from tik.shared.ui.scene_watcher import SceneWatcher

    from . import switches  # noqa: F401 - importing is what registers them
    from .window import SwitchesWindow

    # A previous instance's watchers are still registered with Maya, and after
    # a module reload they fire into stale code.
    SceneWatcher.uninstall_all()
    SwitchesWindow.teardown_workspace_control()
    window = SwitchesWindow()
    window.show_tool(dockable=dockable)
    return window
