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

def _create_node_with_dag_modifier(node_type: str) -> str:
    modifier = OpenMaya.MDagModifier()
    node_object = modifier.createNode(node_type)
    modifier.doIt()
    apiundo.commit(undo=modifier.undoIt, redo=modifier.doIt)
    dag_path = OpenMaya.MDagPath.getAPathTo(node_object)
    return dag_path.fullPathName()


def _create_node_with_dg_modifier(node_type: str) -> str:
    modifier = OpenMaya.MDGModifier()
    node_object = modifier.createNode(node_type)
    modifier.doIt()
    apiundo.commit(undo=modifier.undoIt, redo=modifier.doIt)
    return OpenMaya.MFnDependencyNode(node_object).name()

@alias("createNode")
def create_node(node_type: str):
    """Create a new node of the specified type and return its wrapper."""
    try:
        full_name = _create_node_with_dag_modifier(node_type)
    except TypeError:
        try:
            full_name = _create_node_with_dg_modifier(node_type)
        except (TypeError, RuntimeError):
            full_name = cmds.createNode(node_type)

    if is_registered(node_type):
        return resolve(full_name, class_name=node_type)
    return resolve(full_name)
