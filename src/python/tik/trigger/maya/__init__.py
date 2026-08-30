"""The Maya layer of tik.trigger: everything that touches a scene.

``tik.trigger.core`` stays pure Python; this package is where tik.maya is
used. There is no backend protocol behind these classes — tik.trigger
targets Maya.
"""

from . import tags
from .build import AFTERLIFE_MODES, Builder, BuildReport
from .rig import MayaBuildContext, MayaGuideContext, RigGroups
from .scene import MayaBackend

__all__ = [
    "AFTERLIFE_MODES",
    "Builder",
    "BuildReport",
    "MayaBackend",
    "MayaBuildContext",
    "MayaGuideContext",
    "RigGroups",
    "tags",
]
