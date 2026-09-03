"""Base Class for Maya Shape Nodes."""

from __future__ import annotations

from maya import cmds
from maya.api import OpenMaya

from ..types.transform import Transform
from .dagnode import DagNode
from .node import Node
from .registry import register, resolve


@register("shape")
class ShapeNode(DagNode):
    """Base for all nodes that have an associated transform + shape relationship."""

    def __init__(self, node_name):
        """Wrap a shape node, resolving from transform when needed."""
        # Determine if the given node is a shape or transform
        if cmds.nodeType(node_name) in {"transform"}:
            shapes = cmds.listRelatives(node_name, shapes=True, fullPath=True)
            if not shapes:
                raise ValueError(f"Transform '{node_name}' has no shape.")
            node_name = shapes[0]
        super().__init__(node_name)

        self._transform = None

    @property
    def long_name(self):
        """Return the full DAG path, respecting the specific instance path if possible.

        Returns:
            str: The full DAG path to this shape node.
        """
        if self._cached_dag_path and self._cached_dag_path.isValid():
            return self._cached_dag_path.fullPathName()
        return super().long_name

    @property
    def transform(self):
        """Return the parent transform as a DagNode.

        Returns:
            Transform: The parent transform node wrapper.
        """
        if self._transform and self._transform.exists():
            return self._transform

        path = OpenMaya.MDagPath(self._dag_path())
        path.pop()
        full_path = path.fullPathName()
        if full_path:
            self._transform = Transform(full_path)
        return self._transform

    @property
    def shape(self):
        """Return the shape node itself (for consistency with transform API).

        Returns:
            ShapeNode: Returns self.
        """
        return self

    @property
    def parent(self):
        """Return the parent as a wrapped node (or None if no parent).

        Returns:
            Node or None: The parent node wrapper.
        """
        path = OpenMaya.MDagPath(self._dag_path())
        path.pop()
        full_path_name = path.fullPathName()
        if not full_path_name:
            return None
        return resolve(full_path_name)

    @parent.setter
    def parent(self, new_parent):
        if new_parent is None:
            raise ValueError(
                "Shape nodes cannot be parented to world; parent the transform instead."
            )

        target_name = (
            new_parent.name if isinstance(new_parent, Node) else str(new_parent)
        )
        target_list = OpenMaya.MSelectionList()
        target_list.add(target_name)
        target_path = target_list.getDagPath(0)
        if target_path.node().hasFn(OpenMaya.MFn.kShape):
            target_path.pop()  # ensure we parent under the transform

        modifier = OpenMaya.MDagModifier()
        modifier.reparentNode(self._dag_path().node(), target_path.node())
        modifier.doIt()

        self._cached_dag_path = None
        self._transform = Transform(target_path.fullPathName())
