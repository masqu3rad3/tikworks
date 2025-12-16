"""Module for tikmaya which handles scene-related functions."""

from maya import cmds
from .registry import resolve
from .decorators import alias

@alias("ls")
def list_scene_nodes(*args, **kwargs):
    """Wrapper for cmds.ls to list scene nodes of a specific type."""
    return [resolve(node) for node in cmds.ls(*args, **kwargs)]
