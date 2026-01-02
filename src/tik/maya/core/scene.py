"""Module for tikmaya which handles scene-related functions."""

from maya import cmds
from .registry import resolve, is_registered
from .decorators import alias

@alias("ls")
def list_scene_nodes(*args, **kwargs):
    """Wrapper for cmds.ls to list scene nodes of a specific type."""
    return [resolve(node) for node in cmds.ls(*args, **kwargs)]

@alias("select")
def select_nodes(nodes, **kwargs):
    """Selects the given nodes in the Maya scene."""
    node_names = [str(node) for node in nodes] # make sure to convert to string names
    cmds.select(node_names, **kwargs)

@alias("createNode")
def create_node(node_type, **kwargs):
    """Creates a new node of the specified type and returns its wrapper."""
    node_name = cmds.createNode(node_type, **kwargs)
    if is_registered(node_type):
        return resolve(node_name)
    return node_name
