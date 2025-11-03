# node.py — base Node and Plug wrappers
import maya.cmds as cmds
from .registry import _NODE_TYPES
from .registry import set_default_factory

class Node:
    """Base wrapper around a Maya dependency node or DAG node."""
    is_dag = False

    def __init__(self, long_name):
        if not cmds.objExists(long_name):
            raise ValueError(f"Node '{long_name}' does not exist.")
        self._uuid = cmds.ls(long_name, uuid=True)[0]
        self._cached_long_name = None
        self._cached_short_name = None

    @property
    def long_name(self):
        """The full DAG path of the node."""
        if not self._cached_long_name or not cmds.objExists(self._cached_long_name):
            result = cmds.ls(self.uuid, long=True)
            self._cached_long_name = result[0] if result else None
        return self._cached_long_name

    @property
    def name(self):
        """The name of the node."""
        if not self._cached_short_name or not cmds.objExists(self._cached_short_name):
            result = cmds.ls(self.uuid, long=False)
            self._cached_short_name = result[0] if result else None
        return self._cached_short_name

    @property
    def uuid(self):
        """The UUID of the node."""
        return self._uuid

    @classmethod
    def create(cls, cmd, **kwargs):
        """Create a node using a maya.cmds command name (e.g., 'joint', 'polySphere')."""
        result = cmds.createNode(cmd, **kwargs)
        if isinstance(result, (list, tuple)):
            result = result[0]

        node_type = cmds.nodeType(result)
        subclass = _NODE_TYPES.get(node_type, Node)
        return subclass(result)

    def delete(self):
        """Delete the node from the scene."""
        cmds.delete(self.uuid)
        self._invalidate_cache()

    def rename(self, new_name):
        """Rename the node."""
        cmds.rename(self.name, new_name)
        self._invalidate_cache()
        return self

    def exists(self):
        """Check if the node still exists in the scene."""
        return cmds.objExists(self.uuid)

    def _invalidate_cache(self):
        self._cached_long_name = None
        self._cached_short_name = None

    def __getitem__(self, attr):
        """Get a Plug for the given attribute name."""
        return Plug(self.name, attr)

    def __repr__(self):
        return f"<{self.__class__.__name__} '{self.name}'>"


class Plug:
    """Represents an attribute plug on a Maya node."""

    def __init__(self, node: Node, attr: str):
        """Initialize a Plug for the given node and attribute name."""
        self._uuid = node.uuid
        self._attr = attr

    @property
    def attr(self):
        """The attribute name."""
        return self._attr

    @property
    def path(self):
        """The full attribute path."""
        node_name = cmds.ls(self._uuid, long=True)[0]
        return f"{node_name}.{self._attr}"

    def get(self):
        """Get the value of the attribute."""
        return cmds.getAttr(self.path)

    def set(self, value):
        """Set the value of the attribute."""
        if isinstance(value, (list, tuple)):
            cmds.setAttr(self.path, *value)
        elif isinstance(value, (float, int, bool)):
            cmds.setAttr(self.path, value)
        elif isinstance(value, str):
            cmds.setAttr(self.path, value, type="string")
        else:
            raise TypeError(f"Unsupported type for setting attribute: {type(value)}")

    def connect(self, other, force=True):
        """Connect this plug to another plug."""
        cmds.connectAttr(self.path, other.path, force=force)

    def disconnect(self, other=None):
        """Disconnect this plug from another plug, or from its source if no plug is given."""
        if other:
            cmds.disconnectAttr(self.path, other.path)
        else:
            sources = cmds.listConnections(self.path, plugs=True, source=True)
            if sources:
                cmds.disconnectAttr(sources[0], self.path)

    def __repr__(self):
        return f"<Plug '{self.path}'>"

set_default_factory(Node)
