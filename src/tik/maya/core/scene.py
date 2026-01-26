"""Module for tikmaya which handles scene-related functions."""

from maya import cmds

from . import apicommon
from .decorators import alias
from .registry import is_registered, resolve

# --- DYNAMIC WRAPPER CONFIGURATION ---

# Commands that return nodes and should be auto-converted to tik objects.
_NODE_FACTORIES = {
    "listRelatives",
    "listConnections",
    "listHistory",
    "duplicate",
    "instance",
    "polyCube",
    "polySphere",
    "polyPlane",
    "polyCylinder",
    "polyTorus",
    "polyExtrudeFacet",
    "polyBevel",
    "spaceLocator",
    "group",
    "circle",
    "curve",
    "joint",
    "rename",
    # We do NOT need "ls" or "createNode" here because
    # these are handled internally in scene module.
}


def _clean_input(data):
    """Recursively converts tik Objects to strings."""
    if hasattr(data, "name"):
        return str(data)
    elif isinstance(data, (list, tuple)):
        return [_clean_input(idx) for idx in data]
    elif isinstance(data, dict):
        return {_key: _clean_input(_val) for _key, _val in data.items()}
    return data


def _wrap_output(result):
    """Recursively converts strings to tik Objects."""
    if isinstance(result, list):
        return [_wrap_output(item) for item in result]
    if isinstance(result, str):
        return resolve(result)
    return result


def _proxy_wrapper(func_name, *args, **kwargs):
    """The function that executes when a user calls a dynamic command."""
    original_func = getattr(cmds, func_name)

    # Sanitize inputs (Object -> String)
    clean_args = _clean_input(args)
    clean_kwargs = _clean_input(kwargs)

    # Run the real maya command
    result = original_func(*clean_args, **clean_kwargs)

    # Wrap output if it's a known factory (String -> Object)
    if func_name in _NODE_FACTORIES and result is not None:
        return _wrap_output(result)

    return result


@alias("ls")
def list_scene_nodes(*args, **kwargs):
    """Wrapper for cmds.ls to list scene nodes of a specific type."""
    return [resolve(node) for node in cmds.ls(*args, **kwargs)]


@alias("select")
def select_nodes(*args, **kwargs):
    """Selects the given nodes in the Maya scene."""
    clean_args = _clean_input(args)
    clean_kwargs = _clean_input(kwargs)
    cmds.select(*clean_args, **clean_kwargs)


@alias("createNode")
def create_node(node_type: str, name=None, parent=None):
    """Create a new node of the specified type and return its wrapper."""
    try:
        full_name = apicommon.create_node_with_dag_modifier(
            node_type, name=name, parent=parent
        )
    except TypeError:
        try:
            full_name = apicommon.create_node_with_dg_modifier(node_type, name=name)
        except (TypeError, RuntimeError):
            # we will only pass the name argument if it is not None
            kwargs = {}
            if name is not None:
                kwargs["name"] = name
            full_name = cmds.createNode(node_type, **kwargs)

    if is_registered(node_type):
        return resolve(full_name, class_name=node_type)
    return resolve(full_name)
