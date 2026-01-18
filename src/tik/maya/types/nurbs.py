"""Nurbs surface node type wrapper."""

from maya import cmds
from maya.api import OpenMaya

from ..core.shapenode import ShapeNode
from ..core.registry import register


@register("nurbsSurface")
class Nurbs(ShapeNode):
    """Wrapper for NURBS surface nodes."""

    valid_primitives = {
        "nurbsPlane",
        "sphere",
        "cylinder",
        "cone",
        "torus",
    }
    valid_commands = {"nurbsSurface"}

    @classmethod
    def create(cls, cmd, **kwargs):
        """Create a nurbs surface or primitive (e.g. nurbsPlane)."""
        if cmd in cls.valid_primitives:
            result = getattr(cmds, cmd)(**kwargs)
            if isinstance(result, (list, tuple)):
                result = result[0]
        elif cmd in cls.valid_commands:
            result = cmds.createNode(cmd, **kwargs)
        else:
            raise ValueError(
                f"Command '{cmd}' is not valid for creating a Nurbs Surface. "
                f"Valid "
                f"commands: {cls.valid_primitives.union(cls.valid_commands)}"
            )
        return Nurbs(result)

    def cvs(self, space="world"):
        """Return all control vertex positions.

        Args:
            space : str, optional
                Coordinate space to return the CVs in.
                Accepted values: "world", "object", "transform".
                Default is "world".
        Returns:
            OpenMaya.MPointArray
                Array of CV positions in the requested space.
        """
        # Map simple string options to MSpace enums
        _space_map = {
            "world": OpenMaya.MSpace.kWorld,
            "object": OpenMaya.MSpace.kObject,
            "transform": OpenMaya.MSpace.kTransform,
        }
        if space not in _space_map:
            raise ValueError(
                f"Invalid space '{space}'. Must be one of: "
                f"{', '.join(_space_map.keys())}"
            )

        mfn_object = OpenMaya.MFnNurbsSurface(self.dag_path)
        return mfn_object.cvPositions(_space_map[space])
