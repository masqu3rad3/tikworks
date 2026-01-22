from maya import cmds
from functools import partial

from .core.node import Node
from .core.registry import resolve
from .core.dagnode import DagNode
from .core.shapenode import ShapeNode
from .types.curve import Curve
from .types.joint import Joint
from .types.light import Light
from .types.locator import Locator
from .types.mesh import Mesh
from .types.nurbs import Nurbs
from .types.transform import Transform
from .types.camera import Camera
from .types.blendshape import BlendShape
from . import roles
from . import constructs
from .core.scene import *

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
    "resolve"
]

# --- DYNAMIC WRAPPER CONFIGURATION ---

# Commands that return nodes and should be auto-converted to tik objects.
_NODE_FACTORIES = {
    "listRelatives", "listConnections", "listHistory",
    "duplicate", "instance",
    "polyCube", "polySphere", "polyPlane", "polyCylinder", "polyTorus",
    "polyExtrudeFacet", "polyBevel",
    "spaceLocator", "group", "circle", "curve",
    "rename",
    # We do NOT need "ls" or "createNode" here because
    # these are handled internally in scene module.
}


def _clean_input(data):
    """Recursively converts tik Objects to strings."""
    if hasattr(data, "name"):
        return str(data)
    elif isinstance(data, (list, tuple)):
        return [_clean_input(i) for i in data]
    elif isinstance(data, dict):
        return {k: _clean_input(v) for k, v in data.items()}
    return data


def _wrap_output(result):
    """Recursively converts strings to tik Objects."""
    if isinstance(result, list):
        return [_wrap_output(item) for item in result]
    if isinstance(result, str):
        return resolve(result)
    return result


def _proxy_wrapper(func_name, *args, **kwargs):
    """The function that executes when a user calls a dynamic command."""
    original_func = getattr(cmds, func_name)

    # Sanitize inputs (Object -> String)
    clean_args = _clean_input(args)
    clean_kwargs = _clean_input(kwargs)

    # Run the real maya command
    result = original_func(*clean_args, **clean_kwargs)

    # Wrap output if it's a known factory (String -> Object)
    if func_name in _NODE_FACTORIES and result is not None:
        return _wrap_output(result)

    return result


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