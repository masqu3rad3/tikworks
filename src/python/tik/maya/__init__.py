"""TikWorks Maya package - Object-oriented wrapper for Maya API."""

from functools import partial

from maya import cmds

from .constructs import (
    AimFrame,
    AngleBetween,
    ChainLengths,
    MatrixBlend,
    MatrixConstraint,
    MatrixSpline,
    MatrixSwitch,
    Measure,
    Remap,
    Ribbon,
    SoftIk,
    SpaceSwitch,
)
from .core import naming
from .core.constants import (
    ALL_CHANNELS,
    ROTATE_CHANNELS,
    SCALE_CHANNELS,
    TRANSFORM_CHANNELS,
    TRANSLATE_CHANNELS,
)
from .core.dagnode import DagNode
from .core.meta import META_PREFIX, find_by_meta
from .core.node import Node
from .core.plug import Plug
from .core.registry import resolve
from .core.scene import (
    create_node,
    createNode,
    ensure_plugin,
    list_scene_nodes,
    ls,
    proxy_wrapper,
    reset_scene,
    select,
    select_nodes,
)
from .core.shapenode import ShapeNode
from .types.blendshape import BlendShape
from .types.camera import Camera
from .types.curve import Curve
from .types.ikhandle import IkHandle
from .types.joint import Joint
from .types.light import Light
from .types.locator import Locator
from .types.mesh import Mesh
from .types.nurbs import Nurbs
from .types.skincluster import SkinCluster
from .types.transform import Transform

__all__ = [
    "Node",
    "DagNode",
    "Plug",
    "ShapeNode",
    "Joint",
    "IkHandle",
    "Transform",
    "Mesh",
    "Curve",
    "Nurbs",
    "Locator",
    "Light",
    "Camera",
    "BlendShape",
    "SkinCluster",
    "resolve",
    "find_by_meta",
    "naming",
    "TRANSLATE_CHANNELS",
    "ROTATE_CHANNELS",
    "SCALE_CHANNELS",
    "TRANSFORM_CHANNELS",
    "ALL_CHANNELS",
    "AimFrame",
    "AngleBetween",
    "ChainLengths",
    "MatrixBlend",
    "MatrixConstraint",
    "MatrixSpline",
    "MatrixSwitch",
    "Measure",
    "SpaceSwitch",
    "Remap",
    "Ribbon",
    "SoftIk",
    "META_PREFIX",
    "create_node",
    "createNode",
    "ensure_plugin",
    "list_scene_nodes",
    "ls",
    "proxy_wrapper",
    "reset_scene",
    "select",
    "select_nodes",
]

# --- MODULE LEVEL GETATTR (PEP 562) ---


def __getattr__(name):
    """
    Called implicitly when user asks for tm.something that isn't imported above.
    """
    # If the name exists in maya.cmds, create a wrapper for it
    if hasattr(cmds, name):
        return partial(proxy_wrapper, name)

    # Otherwise, it really doesn't exist
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
