from maya.api import OpenMaya
from maya import cmds

from .node import Node
from .registry import resolve

class DagNode(Node):
    """DAG-capable node wrapper with parent/children queries."""
    is_dag = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached_dag_path = None

    def _dag_path(self):
        """Resolve and cache this node's MDagPath using the long name for disambiguation."""
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
            new_parent_name = new_parent.name if isinstance(new_parent, Node) else str(new_parent)
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