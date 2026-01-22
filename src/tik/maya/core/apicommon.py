"""Common API functions for Maya node wrappers.

The functions here are optimized versions of commonly used cmds functions,
using the Maya Python API 2.0 for better performance.

ANY FUNCTIONS HERE MUST NOT HAVE ANY DEPENDENCY TO tik.maya NODE WRAPPERS.
"""

from maya.api import OpenMaya
from tik.vendor.apiundo import apiundo
undocommit = apiundo.commit

# def mockup_undo_redo(undo=None, redo=None):
#     """Mockup function for undocommit to avoid circular imports."""
#     pass
#
# undocommit = mockup_undo_redo

def obj_exists(name):
    """
    Faster equivalent of cmds.objExists(name).
    """
    sel = OpenMaya.MSelectionList()
    try:
        # Try to add the object to the selection list by string name
        sel.add(name)
        return True
    except RuntimeError:
        # If the object is not found, an exception is raised
        return False


def node_type(name):
    """
    Faster equivalent of cmds.nodeType(name) (without inherited=True).
    """
    sel = OpenMaya.MSelectionList()
    try:
        sel.add(name)
        obj = sel.getDependNode(0)
        return OpenMaya.MFnDependencyNode(obj).typeName
    except RuntimeError:
        return None

def normalize_mobject(parent):
    if not isinstance(parent, OpenMaya.MObject):
        sel = OpenMaya.MSelectionList()
        sel.add(str(parent))
        parent = sel.getDependNode(0)
    return parent

def create_node_with_dag_modifier(node_type: str, parent=None, name=None) -> str:
    # if there is a parent, make sure that it is an MObject

    mod = OpenMaya.MDagModifier()
    if parent:
        node_object = mod.createNode(node_type, parent=normalize_mobject(parent))
    else:
        node_object = mod.createNode(node_type)
    if name:
        mod.renameNode(node_object, name)
    mod.doIt()
    undocommit(undo=mod.undoIt, redo=mod.doIt)
    dag_path = OpenMaya.MDagPath.getAPathTo(node_object)
    return dag_path.fullPathName()

def create_node_with_dg_modifier(node_type: str, name=None) -> str:
    mod = OpenMaya.MDGModifier()
    node_object = mod.createNode(node_type)
    if name:
        mod.renameNode(node_object, name)
    mod.doIt()
    undocommit(undo=mod.undoIt, redo=mod.doIt)
    return OpenMaya.MFnDependencyNode(node_object).name()