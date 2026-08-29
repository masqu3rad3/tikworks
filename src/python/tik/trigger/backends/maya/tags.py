"""Metadata keys used to tag Trigger nodes in Maya (via ``Node.meta``)."""

from __future__ import annotations

KIND = "trg_kind"  # "guide" | "rig" | "deform" | "controller" | "plug" | "socket" | "rig_root"
MODULE = "trg_module"  # module type name
INSTANCE = "trg_instance"  # instance uuid
ROLE = "trg_role"  # guide role / plug name / socket name
INDEX = "trg_index"  # guide index for multi roles
SIDE = "trg_side"
NAME = "trg_name"  # user facing instance name (root guide only)
SETTINGS = "trg_settings"  # settings dict (root guide only)
ATTACH = "trg_attach"  # plug override (root guide only)
DESIGNER = "trg_designer"  # Guide Designer layout dict (guide holder only)

GUIDE = "guide"
RIG = "rig"
RIG_ROOT = "rig_root"
DEFORM = "deform"
CONTROLLER = "controller"
OUTPUT = "output"
INPUT = "input"
PLUG = OUTPUT  # legacy aliases
SOCKET = INPUT

GUIDE_HOLDER = "trigger_guides_grp"


def tag(node, **values) -> None:
    """Write several meta keys at once."""
    node.meta.update(values)
