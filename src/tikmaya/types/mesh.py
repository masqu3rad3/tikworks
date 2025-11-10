"""Mesh node type wrapper."""

from maya.api import OpenMaya
from maya import cmds

from ..core.shapenode import ShapeNode
from ..core.registry import register


@register("mesh")
class Mesh(ShapeNode):
    """Wrapper for mesh nodes."""
    valid_primitives = {"polyCube", "polySphere", "polyPlane", "polyCylinder",
                        "polyCone", "polyTorus"}
    valid_commands = {'mesh'}

    @classmethod
    def create(cls, cmd, **kwargs):
        """Create a node using a Maya command (e.g. polySphere)."""
        if cmd in cls.valid_primitives:
            result = getattr(cmds, cmd)(**kwargs)
            if isinstance(result, (list, tuple)):
                result = result[0]
        elif cmd in cls.valid_commands:
            result = cmds.createNode(cmd, **kwargs)
        else:
            raise ValueError(
                f"Command '{cmd}' is not valid for creating a Mesh. Valid "
                f"commands: {cls.valid_primitives.union(cls.valid_commands)}")
        return Mesh(result)

    def vertices(self, space="world"):
        """Return all vertex positions.

        Args:
            space : str, optional
                Coordinate space to return the vertices in.
                Accepted values: "world", "object", "transform".
                Default is "world".

        Returns:
            OpenMaya.MPointArray
                Array of vertex positions in the requested space.
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

        selection_ls = OpenMaya.MSelectionList()
        selection_ls.add(self.name)
        dag_path = selection_ls.getDagPath(0)

        mfn_mesh = OpenMaya.MFnMesh(dag_path)
        return mfn_mesh.getPoints(_space_map[space])
