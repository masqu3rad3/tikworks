"""The Maya layer of tik.trigger: everything that touches a scene.

``tik.trigger.core`` stays pure Python; this package is where tik.maya is
used. There is no backend protocol behind these classes — tik.trigger
targets Maya.

Submodules are resolved lazily so that importing ``tik.trigger.maya.tags``
(which ``tik.trigger.guides.nodes`` needs) does not pull in the builder, and
the guides and build layers can import each other freely.
"""

from __future__ import annotations

_LAZY = {
    "AFTERLIFE_MODES": ".build",
    "Builder": ".build",
    "BuildReport": ".build",
    "apply_afterlife": ".build",
    "build_context": ".build",
    "connect": ".build",
    "connect_space": ".build",
    "ensure_rig_root": ".build",
    "finalize": ".build",
    "MayaBuildContext": ".rig",
    "MayaGuideContext": ".rig",
    "RigGroups": ".rig",
}

__all__ = ["tags", *sorted(_LAZY)]


def __getattr__(name: str):
    import importlib

    if name == "tags":
        return importlib.import_module(".tags", __name__)
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module, __name__), name)
