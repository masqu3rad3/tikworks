"""GuideLayout as an asset: ``.trg`` files and the live-scene ``GuideScene``.

``format`` is pure Python (the file). ``nodes`` and ``scene`` touch Maya, so
they resolve on first use and importing this package stays Maya-free.
"""

from .format import EXTENSION, GuideFile, GuideInstance, make_record
from .handle import GuideHandle

__all__ = [
    "EXTENSION",
    "GuideFile",
    "GuideInstance",
    "GuideHandle",
    "GuideScene",
    "make_record",
]


def __getattr__(name: str):
    if name == "GuideScene":
        from .scene import GuideScene

        return GuideScene
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
