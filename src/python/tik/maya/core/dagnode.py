"""DAG (Directed Acyclic Graph) node wrapper for Maya."""

from __future__ import annotations

from typing import Any

from maya import cmds
from maya.api import OpenMaya

from tik.core.color import Color

from .apicommon import create_node_with_dag_modifier, undocommit
from .decorators import add_aliases, protected
from .node import Node
from .registry import register, resolve


@add_aliases(
    {
        "visibility": "v",
        "bounding_box": "bb",
    }
)
@register("dagNode")
class DagNode(Node):
    """DAG-capable node wrapper with parent/children queries."""

    is_dag = True

    def __init__(self, *args, **kwargs):
        """Initialize the DagNode wrapper."""
        super().__init__(*args, **kwargs)
        self._cached_dag_path = self._sel.getDagPath(0)

    @classmethod
    def create(cls, cmd, name=None, parent=None):
        """Create a node using a maya.cmds command name.

        Example: 'joint', 'polySphere'.
        """
        full_name = create_node_with_dag_modifier(cmd, parent=parent, name=name)
        return cls(full_name)

    @property
    def visibility(self):
        """Get or set the visibility of this transform node."""
        return self["visibility"].get()

    @visibility.setter
    def visibility(self, value):
        self["visibility"].set(value)

    @property
    def dag_path(self):
        """Return the MDagPath for this node.

        Returns:
            OpenMaya.MDagPath: The DAG path of this node.
        """
        return self._dag_path()

    def _dag_path(self):
        """Resolve and cache this node's MDagPath using the long name for
        disambiguation."""
        if not self._cached_dag_path or not self._cached_dag_path.isValid():
            self._cached_dag_path = self._sel.getDagPath(0)
        return self._cached_dag_path

    @property
    def parent(self):
        """Return the parent as a wrapped node (or None if no parent).

        Returns:
            Node wrapper or None: The parent node, or None for a world-level
                node.
        """
        return self.get_parent()

    @parent.setter
    def parent(self, new_parent):
        """Set a new parent for this node. Pass None to unparent to world."""
        self.set_parent(new_parent)

    def get_parent(self):
        """Return the parent as a wrapped node (or None if no parent)."""
        mfn = OpenMaya.MFnDagNode(self._dag_path())
        parent_obj = mfn.parent(0)
        parent_path = OpenMaya.MDagPath.getAPathTo(parent_obj)
        full_path_name = parent_path.fullPathName()
        if not full_path_name:
            return None
        return resolve(parent_path.fullPathName())

    @protected
    def set_parent(self, new_parent: Any, relative: bool = False) -> None:
        """Set a new parent for this node.

        Args:
            new_parent: New parent node (str, Node wrapper, or None for world).
            relative: If True, keep local transforms (no world-space compensation).
                If False (default), preserve world-space placement by compensating
                transforms after parenting (similar to cmds.parent(relative=False)).
        """
        world_matrix_before: OpenMaya.MMatrix | None = None
        if not relative:
            # Get the WORLD matrix via inclusiveMatrix(), not local transformation
            world_matrix_before = self._dag_path().inclusiveMatrix()

        dag_modifier = OpenMaya.MDagModifier()
        if new_parent is None:
            dag_modifier.reparentNode(self._m_obj)
        else:
            new_parent_node = resolve(new_parent)
            if not new_parent_node.exists():
                raise ValueError(
                    f"New parent node '{new_parent_node.uuid}' does not exist."
                )
            dag_modifier.reparentNode(self._m_obj, new_parent_node._m_obj)

        dag_modifier.doIt()

        # Invalidate cached path since parenting changes the full path
        self._cached_dag_path = None

        if world_matrix_before is not None:
            # Get fresh dag path after reparenting
            new_dag_path = self._dag_path()
            # Get new parent's world matrix (or identity if parented to world)
            parent_inverse_matrix = new_dag_path.exclusiveMatrixInverse()
            # Compute new local matrix to maintain world position
            new_local_matrix = world_matrix_before * parent_inverse_matrix
            # Apply the new local transformation
            transform_fn = OpenMaya.MFnTransform(new_dag_path)
            transform_fn.setTransformation(
                OpenMaya.MTransformationMatrix(new_local_matrix)
            )

        undocommit(undo=dag_modifier.undoIt, redo=dag_modifier.doIt)

    @property
    def children(self):
        """Return children as wrapped nodes.

        Returns:
            list: List of child node wrappers.
        """
        mfn = OpenMaya.MFnDagNode(self._dag_path())
        children_list = []
        for idx in range(mfn.childCount()):
            child_obj = mfn.child(idx)
            child_path = OpenMaya.MDagPath.getAPathTo(child_obj)
            children_list.append(resolve(child_path.fullPathName()))
        return children_list

    @property
    def bounding_box(self):
        """Return the world axis-aligned bounding box of this node.

        Returns:
            OpenMaya.MBoundingBox: The bounding box in world space.
        """
        mfn = OpenMaya.MFnDagNode(self._dag_path())
        return mfn.boundingBox

    @property
    def color(self):
        """Get or set the display color of the node.

        Can be set to:
            - int: Maya index color (0-31)
            - tuple/list: RGB values (0.0-1.0)
            - Color: tik.core.Color object
            - None: Disable color override
        """
        return self.get_color()

    @color.setter
    def color(self, value):
        self.set_color(value)

    def select(self):
        """Select this node in the Maya scene."""
        cmds.select(self.long_name, replace=True)

    def get_color(self, as_color=False):
        """Get the display color of the controller shapes.

        Args:
            as_color (bool, optional): If True, and if its RGB colors,
                 return a tik.core.color.Color obj.
        """

        if not self.has_attr("overrideEnabled"):
            return None

        if not self["overrideEnabled"].value:
            return None

        if self["overrideRGBColors"].value:
            if not as_color:
                return self["overrideColorRGB"].value[0]
            return Color(self["overrideColorRGB"].value[0])
        else:
            return self["overrideColor"].value

    def set_color(self, color):
        """
        Set the display color of the controller shapes.

        Args:
            color (int | tuple | list | Color):
                - int: Maya index color (0-31)
                - tuple/list: RGB values (0.0 - 1.0)
                - tik.core.Color: Color object
                - None: Disable color override
        """
        if isinstance(color, Color):
            color = color.rgb

        is_rgb = isinstance(color, (list, tuple))

        # Ensure attributes exist (usually do on shapes)
        if not self.has_attr("overrideEnabled"):
            return
        if not color:
            self["overrideEnabled"].value = False
            return
        self["overrideEnabled"].value = True

        if is_rgb:
            self["overrideRGBColors"].value = True
            self["overrideColorRGB"].value = color
        else:
            self["overrideRGBColors"].value = False
            self["overrideColor"].value = int(color)

    def is_deformable(self):
        """Check if this node is a deformable geometry type."""
        deformable_types = (
            OpenMaya.MFn.kMesh,
            OpenMaya.MFn.kNurbsCurve,
            OpenMaya.MFn.kNurbsSurface,
            OpenMaya.MFn.kLattice,
        )
        return any(self._m_obj.hasFn(d_type) for d_type in deformable_types)

    @protected
    def rename(self, new_name):
        """Rename the node."""
        mod = OpenMaya.MDagModifier()
        mod.renameNode(self._m_obj, new_name)
        mod.doIt()
        undocommit(undo=mod.undoIt, redo=mod.doIt)
        return self
