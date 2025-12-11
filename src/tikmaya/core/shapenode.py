"""Base Class for Maya Shape Nodes."""

from maya import cmds

from .dagnode import DagNode
from .registry import register
from ..types.transform import Transform

@register("shape")
class ShapeNode(DagNode):
    """Base for all nodes that have an associated transform + shape relationship."""

    def __init__(self, node_name):
        # Determine if the given node is a shape or transform
        if cmds.nodeType(node_name) in {"transform"}:
            shapes = cmds.listRelatives(node_name, shapes=True, fullPath=True)
            if not shapes:
                raise ValueError(f"Transform '{node_name}' has no shape.")
            node_name = shapes[0]
        super().__init__(node_name)
        self._transform = None

    @property
    def transform(self):
        """Return the parent transform as a DagNode."""
        if not self._transform or not cmds.objExists(self._transform.name):
            parent = cmds.listRelatives(self.name, parent=True, fullPath=True)
            if parent:
                self._transform = Transform(parent[0])
        return self._transform

    @property
    def shape(self):
        """Return the shape node itself (for consistency)."""
        return self
