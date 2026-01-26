"""TikWorks Maya package - Object-oriented wrapper for Maya API."""

from functools import partial

from maya import cmds

from .core.dagnode import DagNode
from .core.node import Node
from .core.registry import resolve
from .core.scene import *  # noqa: F401, F403
from .core.scene import _proxy_wrapper
from .core.shapenode import ShapeNode
from .types.blendshape import BlendShape
from .types.camera import Camera
from .types.curve import Curve
from .types.joint import Joint
from .types.light import Light
from .types.locator import Locator
from .types.mesh import Mesh
from .types.nurbs import Nurbs
from .types.transform import Transform

__all__ = [
    "Node",
    "DagNode",
    "ShapeNode",
    "Joint",
    "Transform",
    "Mesh",
    "Curve",
    "Nurbs",
    "Locator",
    "Light",
    "Camera",
    "BlendShape",
    "resolve",
]

# --- MODULE LEVEL GETATTR (PEP 562) ---


def __getattr__(name):
    """
    Called implicitly when user asks for tm.something that isn't imported above.
    """
    # If the name exists in maya.cmds, create a wrapper for it
    if hasattr(cmds, name):
        return partial(_proxy_wrapper, name)

    # Otherwise, it really doesn't exist
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
