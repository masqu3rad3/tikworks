"""Mesh node type wrapper."""

from maya import cmds
from maya.api import OpenMaya

from ..core.dagnode import DagNode
from ..core.registry import register

@register("mesh")
class Mesh(DagNode):
    """Wrapper for mesh nodes."""

    def get_vertices(self):
        """Return all vertices."""
        selection_ls = OpenMaya.MSelectionList()
        selection_ls.add(self.name)
        sel_obj = selection_ls.getDagPath(0)

        mfn_object = OpenMaya.MFnMesh(sel_obj)
        return mfn_object.getPoints(OpenMaya.MSpace.kWorld)

