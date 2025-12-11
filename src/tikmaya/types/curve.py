"""Curve node type wrapper."""

from maya import cmds
from maya.api import OpenMaya

from ..core.shapenode import ShapeNode
from ..core.registry import register


@register("nurbsCurve")
class Curve(ShapeNode):
    """Wrapper for NURBS curve nodes."""

    @classmethod
    def create(cls, *args, **kwargs):
        """Create a NURBS curve node."""
        result = cmds.curve(*args, **kwargs)
        return Curve(result)

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

        selection_ls = OpenMaya.MSelectionList()
        selection_ls.add(self.name)
        sel_obj = selection_ls.getDagPath(0)

        mfn_object = OpenMaya.MFnNurbsCurve(sel_obj)
        return mfn_object.cvPositions(_space_map[space])
