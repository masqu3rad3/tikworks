# registry.py — handles automatic node-type registration and factory lookup
import maya.cmds as cmds

_NODE_TYPES = {}


def register(node_type):
    """Decorator for registering Maya node wrappers."""
    def inner(cls):
        _NODE_TYPES[node_type] = cls
        return cls
    return inner


def get_node(name):
    """Return an instance of the correct Node subclass based on Maya node type."""
    if not cmds.objExists(name):
        raise ValueError(f"Node '{name}' does not exist.")
    node_type = cmds.nodeType(name)
    cls = _NODE_TYPES.get(node_type)
    if cls:
        return cls(name)
    from .node import Node
    return Node(name)
