"""Module for tikmaya which handles scene-related functions."""

from maya import cmds
from maya.api import OpenMaya
from .registry import resolve, is_registered
from .decorators import alias
from ...vendor.apiundo import apiundo

@alias("ls")
def list_scene_nodes(*args, **kwargs):
    """Wrapper for cmds.ls to list scene nodes of a specific type."""
    return [resolve(node) for node in cmds.ls(*args, **kwargs)]

@alias("select")
def select_nodes(nodes, **kwargs):
    """Selects the given nodes in the Maya scene."""
    node_names = [str(node) for node in nodes] # make sure to convert to string names
    cmds.select(node_names, **kwargs)

def _normalize_mobject(parent):
    if not isinstance(parent, OpenMaya.MObject):
        sel = OpenMaya.MSelectionList()
        sel.add(str(parent))
        parent = sel.getDependNode(0)
    return parent


def _create_node_with_dag_modifier(node_type: str, parent=None, name=None) -> str:
    # if there is a parent, make sure that it is an MObject

    mod = OpenMaya.MDagModifier()
    if parent:
        parent = _normalize_mobject(parent)
    node_object = mod.createNode(node_type, parent=parent)
    if name:
        mod.renameNode(node_object, name)
    mod.doIt()
    apiundo.commit(undo=mod.undoIt, redo=mod.doIt)
    dag_path = OpenMaya.MDagPath.getAPathTo(node_object)
    return dag_path.fullPathName()

def _create_node_with_dg_modifier(node_type: str, name=None) -> str:
    mod = OpenMaya.MDGModifier()
    node_object = mod.createNode(node_type)
    if name:
        mod.renameNode(node_object, name)
    mod.doIt()
    apiundo.commit(undo=mod.undoIt, redo=mod.doIt)
    return OpenMaya.MFnDependencyNode(node_object).name()

@alias("createNode")
def create_node(node_type: str, name=None, parent=None):
    """Create a new node of the specified type and return its wrapper."""
    try:
        full_name = _create_node_with_dag_modifier(node_type, name=name, parent=parent)
    except TypeError:
        try:
            full_name = _create_node_with_dg_modifier(node_type, name=name)
        except (TypeError, RuntimeError):
            # we will only pass the name argument if it is not None
            kwargs = {}
            if name is not None:
                kwargs["name"] = name
            full_name = cmds.createNode(node_type, **kwargs)

    if is_registered(node_type):
        return resolve(full_name, class_name=node_type)
    return resolve(full_name)
