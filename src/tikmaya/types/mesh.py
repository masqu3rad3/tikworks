"""Mesh node type wrapper."""

from maya.api import OpenMaya
from maya import cmds

from ..core.shapenode import ShapeNode
from ..core.registry import register

@register("mesh")
class Mesh(ShapeNode):
    """Wrapper for mesh nodes."""
    valid_commands = {"polyCube", "polySphere", "polyPlane", "polyCylinder", "polyCone", "polyTorus"}

    @classmethod
    def create(cls, cmd, name=None, **kwargs):
        """Create a node using a Maya command (e.g. polySphere)."""
        if cmd not in cls.valid_commands:
            raise ValueError(f"Command '{cmd}' is not valid for creating a Mesh. Valid commands: {cls.valid_commands}")
        result = getattr(cmds, cmd)(name=name, **kwargs)
        if isinstance(result, (list, tuple)):
            result = result[0]
        return Mesh(result)

    def get_vertices(self):
        """Return all vertices."""
        selection_ls = OpenMaya.MSelectionList()
        selection_ls.add(self.name)
        sel_obj = selection_ls.getDagPath(0)

        mfn_object = OpenMaya.MFnMesh(sel_obj)
        return mfn_object.getPoints(OpenMaya.MSpace.kWorld)

