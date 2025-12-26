from maya import cmds
from maya.api import OpenMaya

from .decorators import add_aliases
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
        self._cached_dag_path = None

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
            sel = OpenMaya.MSelectionList()
            sel.add(self.long_name)
            self._cached_dag_path = sel.getDagPath(0)
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

    @parent.setter
    def parent(self, new_parent):
        """Set a new parent for this node. Pass None to unparent to world."""
        if new_parent is None:
            cmds.parent(self.long_name, world=True)
        else:
            new_parent_name = (
                new_parent.name if isinstance(new_parent, Node) else str(new_parent)
            )
            cmds.parent(self.long_name, new_parent_name)
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
        self.get_color()

    @color.setter
    def color(self, value):
        self.set_color(value)

    def select(self):
        """Select this node in the Maya scene."""
        cmds.select(self.long_name, replace=True)

    def get_color(self):
        """Get the display color of the controller shapes."""

        if not self.has_attr("overrideEnabled"):
            return None

        if not self["overrideEnabled"].value:
            return None

        if self["overrideRGBColors"].value:
            return self["overrideColorRGB"].value
        else:
            return self["overrideColor"].value

    def set_color(self, color):
        """
        Set the display color of the controller shapes.

        Args:
            color (int | tuple | list):
                - int: Maya index color (0-31)
                - tuple/list: RGB values (0.0 - 1.0)
                - None: Disable color override
        """

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