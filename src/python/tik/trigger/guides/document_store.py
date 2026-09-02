"""The two labels the Maya scene carries about the guides it renders.

Everything else about the guides lives in the session. The scene holds guide
joints and these two facts about them, and nothing that is read as authority.
"""

from __future__ import annotations

import tik.maya as tm
from maya import cmds
from tik.trigger.maya import tags

from . import nodes


def read_stamp() -> str:
    """The id of the session whose guides the scene is drawing, or ``""``."""
    if not cmds.objExists(tags.GUIDE_HOLDER):
        return ""
    return str(tm.Transform(tags.GUIDE_HOLDER).meta.get(tags.SESSION, "") or "")


def write_stamp(session_id: str) -> None:
    """Record whose guides the scene is drawing."""
    nodes.holder().meta[tags.SESSION] = str(session_id)
