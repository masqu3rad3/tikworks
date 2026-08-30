"""Metadata keys used to tag Trigger nodes in Maya (via ``Node.meta``)."""

from __future__ import annotations

KIND = "trg_kind"  # "guide" | "rig" | "deform" | "controller" | "output" | "input" | "rig_root"
MODULE = "trg_module"  # module type name
INSTANCE = "trg_instance"  # instance uuid
ROLE = "trg_role"  # guide role / output name / input name
INDEX = "trg_index"  # guide index for multi roles
SIDE = "trg_side"
NAME = "trg_name"  # user facing instance name (root guide only)
SETTINGS = "trg_settings"  # settings dict (root guide only)
DESIGNER = "trg_designer"  # Guide Designer layout dict (guide holder only)
MIRROR = "trg_mirror"  # "behaviour" | "world" - how a pose-mirror tool treats it
OUTPUT_NAME = "trg_output"  # declared output this node fulfils

GUIDE = "guide"
RIG = "rig"
RIG_ROOT = "rig_root"
DEFORM = "deform"
CONTROLLER = "controller"
OUTPUT = "output"
INPUT = "input"

BEHAVIOUR = "behaviour"  # FK-like: follows its joint, equal values mirror
WORLD = "world"  # IK/world: world-aligned, mirroring is tool logic

GUIDE_HOLDER = "trigger_guides_grp"


def tag(node, **values) -> None:
    """Write several meta keys at once."""
    node.meta.update(values)
