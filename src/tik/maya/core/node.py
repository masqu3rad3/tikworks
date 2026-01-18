# node.py — base Node and Plug wrappers
import logging
import maya.cmds as cmds
from maya.api import OpenMaya

from .decorators import protected
from .registry import resolve, resolve_node_class, set_default_factory, undocommit
from .scene import create_node

LOG = logging.getLogger(__name__)

class Node:
    """Base wrapper around a Maya dependency node or DAG node."""
    is_dag = False

    def __new__(cls, name, resolve_type=False, **kwargs):
        """Instantiate the correct node subclass if requested."""
        if cls is not Node:
            return super().__new__(cls)

        # Resolve the node class dynamically if resolve_class is True
        node_cls = resolve_node_class(name) if resolve_type else cls
        instance = object.__new__(node_cls)
        # Only pass the class type to object.__new__()
        return instance

    def __init__(self, long_name, **kwargs):
        """Initialize the Node wrapper."""
        if not cmds.objExists(long_name):
            raise ValueError(f"Node '{long_name}' does not exist.")
        self._sel = OpenMaya.MSelectionList()
        self._sel.add(long_name)
        self._m_obj = self._sel.getDependNode(0)
        self._fn_dep = OpenMaya.MFnDependencyNode(self._m_obj)
        # self._uuid = None # lazy init
        self._uuid = self._fn_dep.uuid().asString()
        self._m_obj_handle = None # lazy init

    @classmethod
    def create(cls, cmd, name=None, parent=None):
        """Create a node using a maya.cmds command name.

        Example: 'joint', 'polySphere'.
        """
        return create_node(cmd, name=name, parent=parent)

    @property
    def m_obj(self):
        """Return valid MObject, re-resolving from UUID if stale."""
        return self._get_valid_mobject()

    # @_m_obj.setter
    # def m_obj(self, value):
    #     self._m_obj = value

    def _get_valid_mobject(self) -> OpenMaya.MObject:
        """Re-resolve MObject from UUID if current reference is stale."""
        handle = OpenMaya.MObjectHandle(self._m_obj)
        if handle.isValid() and handle.isAlive():
            # Verify it's still the same logical object
            current_uuid = OpenMaya.MFnDependencyNode(self._m_obj).uuid().asString()
            if current_uuid == self._uuid:
                return self._m_obj

        # Re-resolve from UUID
        selection_list = OpenMaya.MSelectionList()
        try:
            selection_list.add(self._uuid)
            self._m_obj = selection_list.getDependNode(0)
            return self._m_obj
        except RuntimeError:
            # Node no longer exists
            return OpenMaya.MObject.kNullObj

    @property
    def long_name(self):
        """The full DAG path of the node."""
        return self._resolve_long_name()

    @property
    def name(self):
        """The name of the node."""
        return self._resolve_short_name()

    @property
    def uuid(self):
        """The UUID of the node."""
        # return self._uuid or self._fn_dep.uuid().asString()
        return self._uuid

    @property
    def type(self):
        """The type of the node."""
        return self._fn_dep.typeName

    # @protected
    def _resolve_long_name(self):
        """Resolve long name from stored MObject or UUID."""
        if not self.exists():
            # LOG.warning(f"Node '{self._uuid}' does not exist.")
            # return None
            raise ValueError(f"Node '{self._uuid}' does not exist.")
        if self.m_obj.hasFn(OpenMaya.MFn.kDagNode):
            dag_path = OpenMaya.MDagPath.getAPathTo(self.m_obj)
            return dag_path.fullPathName()
        return self._fn_dep.name()

    # @protected
    def _resolve_short_name(self):
        """Resolve short name from stored MObject."""
        if not self.exists():
            # LOG.warning(f"Node '{self._uuid}' does not exist.")
            # return None
            raise ValueError(f"Node '{self._uuid}' does not exist.")
        return self._fn_dep.name()

    def duplicate(self, **kwargs):
        """Duplicate the node in the scene.

        Returns:
            Node: A new Node instance representing the duplicated node.
        """
        result = cmds.duplicate(self.long_name, **kwargs)[0]
        return resolve(result, class_name=self.type)

    def delete(self):
        """Delete the node from the scene."""
        cmds.delete(self.long_name)

    @protected
    def rename(self, new_name):
        """Rename the node."""
        # if self.exists():
        mod = OpenMaya.MDGModifier()
        mod.renameNode(self.m_obj, new_name)
        mod.doIt()
        undocommit(
            undo=mod.undoIt,
            redo=mod.doIt
        )
        # else:
        #     raise ValueError(f"Node '{self.name}' does not exist.")
        return self

    def exists(self) -> bool:
        """Return True if the wrapped node still exists in the scene."""
        m_obj = self._get_valid_mobject()
        return not m_obj.isNull()

    # def exists(self):
    #     """Check if the node still exists in the scene."""
    #     if not self._m_obj_handle:
    #         self._m_obj_handle = OpenMaya.MObjectHandle(self._m_obj)
    #     return self._m_obj_handle.isValid()

    def add_attr(self, attr_name, **kwargs):
        """Add a new attribute to the node.

        Args:
            attr_name (str): The name of the attribute to add.
            **kwargs: Additional keyword arguments to pass to cmds.addAttr.

        Returns:
            Plug: A Plug instance representing the newly added attribute.
        """
        cmds.addAttr(self.long_name, longName=attr_name, **kwargs)
        return Plug(self, attr_name)

    def delete_attr(self, attr_name):
        """Delete an attribute from the node.

        Args:
            attr_name (str): The name of the attribute to delete.
        """
        cmds.deleteAttr(f"{self.long_name}.{attr_name}")

    def has_attr(self, attr_name):
        """Check if the node has the given attribute.

        Args:
            attr_name (str): The name of the attribute to check.
        Returns:
            bool: True if the attribute exists, False otherwise.
        """
        return self._fn_dep.hasAttribute(attr_name)

    def __getitem__(self, attr):
        """Get a Plug for the given attribute name."""
        return Plug(self, attr)

    def __str__(self):
        """Return the node's name as its string representation."""
        return self.name

    def __repr__(self):
        """Return a debug-friendly representation."""
        return f"<{self.__class__.__name__} '{self.name}'>"


class Plug:
    """Represents an attribute plug on a Maya node."""

    def __init__(self, node, attr: str):
        """Initialize a Plug for the given node and attribute name."""
        self._node = node
        self._attr = attr

    @property
    def attr(self):
        """The attribute name."""
        return self._attr

    @property
    def path(self):
        """The full attribute path."""
        return f"{self._node.name}.{self._attr}"

    @property
    def value(self):
        """Get the value of the attribute."""
        return self.get()

    @value.setter
    def value(self, new_value):
        """Set the value of the attribute."""
        self.set(new_value)

    @property
    def visible(self) -> bool:
        """Check if the attribute is visible in the channelbox."""
        # An attribute is considered visible if it is either keyable or in the channel
        # box.
        _keyable = cmds.getAttr(self.path, keyable=True)
        _channelbox = cmds.getAttr(self.path, channelBox=True)
        return _keyable or _channelbox

    @visible.setter
    def visible(self, state: bool) -> None:
        """Set the visibility of the attribute in the channelbox.

        Args:
            state (bool): True to show the attribute, False to hide.
        """
        _keyable = cmds.getAttr(self.path, keyable=True)
        if not state:
            cmds.setAttr(self.path, edit=True, keyable=False, channelBox=False)
            return
        cmds.setAttr(self.path, edit=True, keyable=_keyable, channelBox=state)

    @property
    def keyable(self) -> bool:
        """Check if the attribute is keyable."""
        return self.as_api_plug().isKeyable

    @keyable.setter
    def keyable(self, state: bool) -> None:
        """Set the keyable state of the attribute.

        Args:
            state (bool): True to make the attribute keyable,
                False to make it non-keyable.
        """
        # if its not explicitly hidden, we expose it in the channel box when making it
        # keyable
        if cmds.getAttr(self.path, channelBox=True):
            cmds.setAttr(self.path, edit=True, keyable=state)
        else:
            cmds.setAttr(self.path, edit=True, keyable=state, channelBox=not state)

    @property
    def locked(self) -> bool:
        """Check if the attribute is locked."""
        return self.as_api_plug().isLocked

    @locked.setter
    def locked(self, state: bool) -> None:
        """Set the lock state of the attribute.

        Args:
            state (bool): True to lock the attribute, False to unlock.
        """
        cmds.setAttr(self.path, edit=True, lock=state)

    @property
    def children(self):
        """If the plug is a compund attribute, return its child plugs."""
        children = cmds.listAttr(self.path, multi=True)
        if not children:
            return []
        return [Plug(self._node, f"{child}") for child in children[1:]]

    def exists(self):
        """Check if the attribute exists."""
        return cmds.attributeQuery(self.attr, node=self._node.name, exists=True)

    def create(self, **kwargs):
        """Add a new attribute to the node.

        Args:
            **kwargs: Additional keyword arguments to pass to cmds.addAttr.
        """
        cmds.addAttr(self._node.long_name, longName=self.attr, **kwargs)

    def delete(self):
        """Delete an attribute from the node."""
        cmds.deleteAttr(f"{self._node.long_name}.{self.attr}")

    def get(self, **kwargs):
        """Get the value of the attribute.

        Args:
            **kwargs: Additional keyword arguments to pass to cmds.getAttr.
        """
        return cmds.getAttr(self.path, **kwargs)

    def set(self, value, **kwargs):
        """Set the value of the attribute.

        Args:
            value: The value to set. Can be a single value or a list/tuple for
                multi-value attributes.
            **kwargs: Additional keyword arguments to pass to cmds.setAttr.
        """
        _type = kwargs.pop("type", None)
        if isinstance(value, (list, tuple)):
            # if there are 16 values, and the type not explicit assume it's a 4x4 matrix
            if len(value) == 16 and not _type:
                cmds.setAttr(self.path, *value, type="matrix", **kwargs)
            else:
                cmds.setAttr(self.path, *value, **kwargs)
        elif isinstance(value, (float, int, bool)):
            cmds.setAttr(self.path, value, **kwargs)
        elif isinstance(value, str):
            _type = _type or "string"
            cmds.setAttr(self.path, value, type=_type, **kwargs)
        else:
            raise TypeError(f"Unsupported type for setting attribute: {type(value)}")

    def as_api_plug(self):
        """Get the attribute as an OpenMaya MPlug."""
        selection_list = OpenMaya.MSelectionList()
        selection_list.add(self.path)
        return selection_list.getPlug(0)

    def rename(self, new_attr_name):
        """Rename the attribute.

        Args:
            new_attr_name (str): The new name for the attribute.
        """
        cmds.renameAttr(self.path, new_attr_name)
        self._attr = new_attr_name

    def connect(self, other: "Plug", force: bool = True) -> None:
        """Connect this plug to another plug.

        Args:
            other (Plug): The plug to connect to.
            force (bool): Whether to force the connection, breaking existing
                connections if necessary.
        """
        cmds.connectAttr(self.path, other.path, force=force)

    def disconnect(self, other=None):
        """Disconnect this plug from another plug, or from its source if no
        plug is given.

        Args:
            other (Plug, optional): The plug to disconnect from. If None,
                disconnects from the source connection.
        """
        if other:
            cmds.disconnectAttr(self.path, other.path)
        else:
            sources = cmds.listConnections(self.path, plugs=True, source=True)
            if sources:
                cmds.disconnectAttr(sources[0], self.path)

    def get_input(self, plug=False):
        """List incoming connections to this plug.

        Returns:
            list of Plug: A list of Plug instances representing the incoming
                connections.
        """
        connections = cmds.listConnections(
            self.path, plugs=True, source=True, destination=False
        )
        if not connections:
            return None

        input_plug = connections[0]
        # input_plugs = raw_inputs[::2] if raw_inputs else []
        splits = input_plug.split(".")
        node = resolve(splits[0])
        if not plug:
            return node
        plug_parts = splits[1:]
        return Plug(node, ".".join(plug_parts))

        # return [Plug(self._node, src.split('.', 1)[1]) for src in sources]

    def list_outputs(self, plugs=False):
        """List outgoing connections from this plug.

        Returns:
            list of Plug: A list of Plug instances representing the outgoing
                connections.
        """
        output_plugs = cmds.listConnections(
            self.path, plugs=True, source=False, destination=True
        )
        outputs = []
        if not output_plugs:
            return outputs

        for plug in output_plugs:
            splits = plug.split(".")
            node = resolve(splits[0])
            if not plugs:
                outputs.append(node)
            else:
                plug_parts = splits[1:]
                outputs.append(Plug(node, ".".join(plug_parts)))
        return outputs

    def lock(self):
        """Lock the attribute."""
        self.locked = True

    def unlock(self):
        """Unlock the attribute."""
        self.locked = False

    def __getitem__(self, attr):
        """Get a child plug (for compound attributes).

        Args:
            attr (str): The child attribute name.
        """
        return Plug(self._node, f"{self.attr}.{attr}")

    def __rshift__(self, other: "Plug") -> "Plug":
        """Connect self to other using `>>` operator and return the
        right‑hand side for chaining.

        Args:
            other (Plug): The plug to connect to.
        """
        if not isinstance(other, Plug):
            raise TypeError(f"Right operand must be a Plug, got {type(other)}")
        self.connect(other, force=True)
        return other

    def __repr__(self):
        """Return a debug-friendly representation."""
        return f"<Plug '{self.path}'>"


set_default_factory(Node)
