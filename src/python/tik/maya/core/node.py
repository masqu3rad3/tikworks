"""Base Node wrapper around Maya dependency nodes.

This module is also a fallback for all unregistered node types.
"""

import logging

import maya.cmds as cmds
from maya.api import OpenMaya

from .apicommon import undocommit
from .decorators import protected
from .plug import Plug
from .registry import resolve, set_default_factory
from .scene import create_node

LOG = logging.getLogger(__name__)


class Node:
    """Base wrapper around a Maya dependency node or DAG node."""

    is_dag = False

    def __init__(self, long_name, **kwargs):
        """Initialize the Node wrapper."""
        self._sel = OpenMaya.MSelectionList()
        self._sel.add(long_name)
        self._m_obj = self._sel.getDependNode(0)
        self._fn_dep = OpenMaya.MFnDependencyNode(self._m_obj)
        self._uuid = self._fn_dep.uuid().asString()
        self._m_obj_handle = None  # lazy init

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

    def _get_valid_mobject(self) -> OpenMaya.MObject:
        """Re-resolve MObject from UUID if current reference is stale."""
        handle = OpenMaya.MObjectHandle(self._m_obj)
        if handle.isValid() and handle.isAlive():
            # Verify it's still the same logical object
            current_uuid = OpenMaya.MFnDependencyNode(self._m_obj).uuid().asString()
            if current_uuid == self._uuid:
                return self._m_obj

        # Re-resolve from UUID using cmds.ls (MSelectionList doesn't accept UUIDs)
        nodes = cmds.ls(self._uuid, long=True)
        if not nodes:
            # Node no longer exists
            return OpenMaya.MObject.kNullObj

        selection_list = OpenMaya.MSelectionList()
        selection_list.add(nodes[0])
        self._m_obj = selection_list.getDependNode(0)
        return self._m_obj

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
        return self._uuid

    @property
    def type(self):
        """The type of the node."""
        return self._fn_dep.typeName

    # @protected
    def _resolve_long_name(self):
        """Resolve long name from stored MObject or UUID."""
        if not self.exists():
            LOG.warning(f"Node '{self._uuid}' does not exist.")
            return None
        if self.m_obj.hasFn(OpenMaya.MFn.kDagNode):
            dag_path = OpenMaya.MDagPath.getAPathTo(self.m_obj)
            return dag_path.fullPathName()
        return self._fn_dep.name()

    # @protected
    def _resolve_short_name(self):
        """Resolve short name from stored MObject."""
        if not self.exists():
            LOG.warning(f"Node '{self._uuid}' does not exist.")
            return None
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

    def delete_history(self):
        """Delete the construction history of the node."""
        cmds.delete(self.long_name, constructionHistory=True)

    @protected
    def rename(self, new_name):
        """Rename the node."""
        mod = OpenMaya.MDGModifier()
        mod.renameNode(self.m_obj, new_name)
        mod.doIt()
        undocommit(undo=mod.undoIt, redo=mod.doIt)
        return self

    def exists(self) -> bool:
        """Return True if the wrapped node still exists in the scene."""
        m_obj = self._get_valid_mobject()
        return not m_obj.isNull()

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


set_default_factory(Node)
