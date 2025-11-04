"""Curve node type wrapper."""

from maya.api import OpenMaya
from maya import cmds

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

    def get_cvs(self):
        """Return all control vertex positions."""
        selection_ls = OpenMaya.MSelectionList()
        selection_ls.add(self.name)
        sel_obj = selection_ls.getDagPath(0)

        mfn_object = OpenMaya.MFnNurbsCurve(sel_obj)
        cvs = mfn_object.cvPositions(OpenMaya.MSpace.kWorld)
        return cvs