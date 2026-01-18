from maya import cmds
from maya.api import OpenMaya

from tik.core.color import Color
from .decorators import add_aliases
from .node import Node
from .registry import register, resolve
from .scene import _create_node_with_dag_modifier
from ...vendor.apiundo import apiundo


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
        full_name = _create_node_with_dag_modifier(cmd, parent=parent, name=name)
        return resolve(full_name)

    @property
    def visibility(self):
        """Get or set the visibility of this transform node."""
        return self["visibility"].get()

    @visibility.setter
    def visibility(self, value):
        self["visibility"].set(value)

    @property
    def dag_path(self):
        """Return the MDagPath for this node."""
        return self._dag_path()

    def _dag_path(self):
        """Resolve and cache this node's MDagPath using the long name for
        disambiguation."""
        if not self._cached_dag_path or not self._cached_dag_path.isValid():
            self._cached_dag_path = self._sel.getDagPath(0)
        return self._cached_dag_path

    @property
    def parent(self):
        """Return the parent as a wrapped node (or None if no parent)."""
        mfn = OpenMaya.MFnDagNode(self._dag_path())
        parent_obj = mfn.parent(0)
        parent_path = OpenMaya.MDagPath.getAPathTo(parent_obj)
        full_path_name = parent_path.fullPathName()
        if not full_path_name:
            return None
        return resolve(parent_path.fullPathName())

    # @parent.setter
    # def parent(self, new_parent):
    #     """Set a new parent for this node. Pass None to unparent to world."""
    #     if new_parent is None:
    #         cmds.parent(self.long_name, world=True)
    #     else:
    #         new_parent_name = (
    #             new_parent.name if isinstance(new_parent, Node) else str(new_parent)
    #         )
    #         cmds.parent(self.long_name, new_parent_name)
    #     # Invalidate cached path since parenting can change the full path.
    #     self._cached_dag_path = None

    # TODO: Revisit the parent.setter with OpenMaya -Needs Undo support-
    @parent.setter
    def parent(self, new_parent):
        """Set a new parent for this node. Pass None to unparent to world."""
        mod = OpenMaya.MDagModifier()
        if new_parent is None:
            # Reparent to world
            mod.reparentNode(self._m_obj)
        else:
            parent_obj = new_parent._m_obj if isinstance(new_parent,
                                                         Node) else None
            if parent_obj is None:
                # Resolve by name if string was passed
                sel = OpenMaya.MSelectionList()
                sel.add(str(new_parent))
                parent_obj = sel.getDependNode(0)
            mod.reparentNode(self._m_obj, parent_obj)
        mod.doIt()
        apiundo.commit(
            undo=mod.undoIt,
            redo=mod.doIt
        )
        # Invalidate cached path since parenting can change the full path.
        self._cached_dag_path = None

    @property
    def children(self):
        """Return children as wrapped nodes."""
        mfn = OpenMaya.MFnDagNode(self._dag_path())
        children_list = []
        for idx in range(mfn.childCount()):
            child_obj = mfn.child(idx)
            child_path = OpenMaya.MDagPath.getAPathTo(child_obj)
            children_list.append(resolve(child_path.fullPathName()))
        return children_list

    @property
    def bounding_box(self):
        """Return the world axis-aligned bounding box of this node."""
        mfn = OpenMaya.MFnDagNode(self._dag_path())
        return mfn.boundingBox

    @property
    def color(self):
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

    def rename(self, new_name):
        """Rename the node."""
        if self.exists():
            mod = OpenMaya.MDagModifier()
            mod.renameNode(self._m_obj, new_name)
            mod.doIt()
            apiundo.commit(
                undo=mod.undoIt,
                redo=mod.doIt
            )
        else:
            raise ValueError(f"Node '{self.name}' does not exist.")
        return self