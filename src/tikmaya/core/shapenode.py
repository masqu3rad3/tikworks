"""Base Class for Maya Shape Nodes."""

from maya import cmds

from .dagnode import DagNode
from ..types.transform import Transform
from .registry import register

@register("shape")
class ShapeNode(DagNode):
    """Represent nodes that have an associated transform and shape relationship."""

    def __init__(self, node_name):
        """Initialize the shape node wrapper.

        Args:
            node_name (str): Name of the shape or transform.

        Raises:
            ValueError: If the provided transform has no shape.
        """
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
        """Return the parent transform as a DagNode.

        Returns:
            Transform | None: Parent transform or None if not found.
        """
        if not self._transform or not cmds.objExists(self._transform.name):
            parent = cmds.listRelatives(self.name, parent=True, fullPath=True)
            if parent:
                self._transform = Transform(parent[0])
        return self._transform

    @property
    def shape(self):
        """Return the shape node itself (for consistency).

        Returns:
            ShapeNode: This instance.
        """
        return self
