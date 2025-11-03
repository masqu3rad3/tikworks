from maya.api import OpenMaya
from maya import cmds

from .node import Node
from .registry import get_node

class DagNode(Node):
    """DAG-capable node wrapper with parent/children queries."""
    is_dag = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached_dag_path = None

    def _dag_path(self):
        if not self._cached_dag_path or not self._cached_dag_path.isValid():
            sel = OpenMaya.MSelectionList()
            sel.add(self.long_name)
            self._cached_dag_path = sel.getDagPath(0)
        return self._cached_dag_path

    @property
    def parent(self):
        """Return the parent as a wrapped node (or None if no parent)."""
        return self.get_parent()

    @parent.setter
    def parent(self, new_parent):
        """Set a new parent for this node."""
        self.set_parent(new_parent)

    @property
    def children(self):
        """Return children as wrapped nodes."""
        return self.get_children()

    def get_parent(self):
        """Return the parent as a wrapped node (or None if no parent)."""
        mfn = OpenMaya.MFnDagNode(self._dag_path())
        if mfn.parentCount() == 0:
            return None
        parent_obj = mfn.parent(0)
        parent_name = OpenMaya.MFnDagNode(parent_obj).fullPathName()
        return self._wrap(parent_name)

    def set_parent(self, new_parent):
        """Set a new parent for this node."""
        new_parent_name = new_parent.name if isinstance(new_parent, Node) else new_parent
        cmds.parent(self.name, new_parent_name)

    def get_children(self):
        """Return children as wrapped nodes."""
        mfn = OpenMaya.MFnDagNode(self._dag_path())
        out = []
        for idx in range(mfn.childCount()):
            child_obj = mfn.child(idx)
            child_name = OpenMaya.MFnDagNode(child_obj).fullPathName()
            out.append(self._wrap(child_name))
        return out

    def _wrap(self, name):
        """Wrap a Maya node name using the registry, with safe fallbacks."""
        try:
            return get_node(name)
        except Exception:
            try:
                return Node(name)
            except Exception:
                return name