"""Common API functions for Maya node wrappers.

The functions here are optimized versions of commonly used cmds functions,
using the Maya Python API 2.0 for better performance.

ANY FUNCTIONS HERE MUST NOT HAVE ANY DEPENDENCY TO tik.maya NODE WRAPPERS.
"""

from maya.api import OpenMaya as om

def obj_exists(name):
    """
    Faster equivalent of cmds.objExists(name).
    """
    sel = om.MSelectionList()
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
    sel = om.MSelectionList()
    try:
        sel.add(name)
        obj = sel.getDependNode(0)
        return om.MFnDependencyNode(obj).typeName
    except RuntimeError:
        return None
