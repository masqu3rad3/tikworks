"""Kinematics action for tik.trigger.

Builds rigs from guide sessions by reading the Maya DAG hierarchy.
Identifies modules via custom attributes on guide joints.

Workflow:
    1. Load guide session from file
    2. Find root joints (where jointRole == module's root_role)
    3. Traverse DAG hierarchy, identifying module boundaries
    4. Build modules
    5. Connect modules based on DAG parent-child relationships
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import maya.cmds as cmds

from tik.trigger.core import ActionCore, register_action
from tik.trigger.core.module_registry import (
    MODULES,
    MODULE_TYPE_ATTR,
    JOINT_ROLE_ATTR,
    MODULE_INSTANCE_ATTR,
    get_module,
)
from tik.trigger.core.socket_data import Plug
from tik.trigger.session.guide_session import GuideSession

logger = logging.getLogger(__name__)

ACTION_DATA = {
    "guides_file_path": "",
    "guide_roots": [],  # List of root joint names to start building from
    "after_creation": 2,  # 0=nothing, 1=hide, 2=delete
}


@dataclass
class ModuleNode:
    """Represents a module instance in the hierarchy."""
    module_type: str
    instance_name: str
    root_joint: str  # The root joint of this module
    end_joint: Optional[str] = None  # The end joint (for socket connection)
    children: list["ModuleNode"] = field(default_factory=list)
    parent_joint: Optional[str] = None  # Which joint in parent this was parented under
    built_module: Optional[object] = None  # The built RigModule instance


@register_action("kinematics")
class Kinematics(ActionCore):
    """Kinematics action - builds rigs from guide hierarchies.

    Reads guide joints from Maya DAG, identifies modules by their custom
    attributes, builds each module, and connects them via plug/socket.
    """

    action_data = ACTION_DATA

    def __init__(self, name: str = None):
        """Initialize the kinematics action."""
        super().__init__(name)
        self.guides_file_path: str = ""
        self.root_joints: list[str] = []
        self.afterlife: int = 2
        self.session: Optional[GuideSession] = None
        self._hierarchy: list[ModuleNode] = []
        self._built_modules: dict[str, object] = {}

    def feed(self, selection: list) -> dict:
        """Validate and extract data for the action.

        Args:
            selection: List of selected Maya nodes (not used for kinematics).

        Returns:
            Dictionary with validated settings.
        """
        self.guides_file_path = self.get_setting("guides_file_path", "")
        self.root_joints = self.get_setting("guide_roots", [])
        self.afterlife = self.get_setting("after_creation", 2)
        logger.debug("Kinematics feed: file=%s, roots=%s", self.guides_file_path, self.root_joints)
        return {
            "guides_file_path": self.guides_file_path,
            "guide_roots": self.root_joints,
            "after_creation": self.afterlife,
        }

    def action(self, feed_data: dict = None) -> None:
        """Execute the kinematics build.

        Args:
            feed_data: Data from feed() containing guides_file_path, guide_roots, etc.
        """
        # Use settings directly since feed() has already extracted them
        # 1. Load the guide session
        self.session = GuideSession()
        if self.guides_file_path:
            self.session.load(self.guides_file_path, reset_scene=True)

        # 2. Find root joints if not specified
        if not self.root_joints:
            self.root_joints = self._find_root_joints()
            logger.info("Auto-detected root joints: %s", self.root_joints)

        if not self.root_joints:
            logger.error("No root joints specified or detected")
            return

        # 3. Traverse DAG and build module hierarchy
        for root_jnt in self.root_joints:
            module_node = self._traverse_dag(root_jnt)
            if module_node:
                self._hierarchy.append(module_node)

        # 4. Build all modules
        for module_node in self._hierarchy:
            self._build_module_node(module_node)

        # 5. Connect modules based on DAG parent-child
        self._connect_modules()

        # 6. Handle guides (hide/delete)
        self._handle_guides()

        logger.info("Kinematics action completed")

    def _find_root_joints(self) -> list[str]:
        """Find all root joints in the scene.

        A root joint is one where:
        - It has the moduleType attribute
        - Its jointRole equals its module's root_role

        Returns:
            List of root joint names.
        """
        root_joints = []

        # Get all joints with moduleType attribute
        all_joints = cmds.ls(type="joint")
        if not all_joints:
            return []

        for jnt in all_joints:
            if not cmds.objExists(f"{jnt}.{MODULE_TYPE_ATTR}"):
                continue
            if not cmds.objExists(f"{jnt}.{JOINT_ROLE_ATTR}"):
                continue

            module_type = cmds.getAttr(f"{jnt}.{MODULE_TYPE_ATTR}")
            joint_role = cmds.getAttr(f"{jnt}.{JOINT_ROLE_ATTR}")

            # Check if this is a root joint
            registry = get_module(module_type)
            if registry and joint_role == registry.root_role:
                root_joints.append(jnt)

        return root_joints

    def _traverse_dag(self, root_joint: str) -> Optional[ModuleNode]:
        """Traverse DAG from root joint, identifying module hierarchy.

        Args:
            root_joint: The root joint to start from.

        Returns:
            ModuleNode tree representing the hierarchy.
        """
        if not cmds.objExists(root_joint):
            logger.warning("Root joint does not exist: %s", root_joint)
            return None

        # Get this joint's module info
        if not cmds.objExists(f"{root_joint}.{MODULE_TYPE_ATTR}"):
            logger.warning("Joint has no moduleType attribute: %s", root_joint)
            return None

        module_type = cmds.getAttr(f"{root_joint}.{MODULE_TYPE_ATTR}")
        instance_name = cmds.getAttr(f"{root_joint}.{MODULE_INSTANCE_ATTR}") if cmds.objExists(f"{root_joint}.{MODULE_INSTANCE_ATTR}") else root_joint

        registry = get_module(module_type)
        if not registry:
            logger.warning("Unknown module type: %s", module_type)
            return None

        logger.info("_traverse_dag: Processing %s (type=%s, instance=%s)", root_joint, module_type, instance_name)

        # Create this module node
        module_node = ModuleNode(
            module_type=module_type,
            instance_name=instance_name,
            root_joint=root_joint,
            end_joint=self._find_end_joint(root_joint, registry),
        )

        # Recursively process children to find child modules
        children = cmds.listRelatives(root_joint, children=True, type="joint") or []
        logger.info("_traverse_dag: Children of %s: %s", root_joint, children)

        for child_jnt in children:
            child_module = self._identify_module_at_joint(child_jnt, parent_joint=root_joint)
            if child_module:
                logger.info("_traverse_dag: Found child module: %s (parent_joint=%s)", child_module.instance_name, child_module.parent_joint)
                module_node.children.append(child_module)
            else:
                logger.info("_traverse_dag: No module found at child %s, traversing deeper...", child_jnt)
                # Traverse deeper through this child
                deeper = self._traverse_through_joint(child_jnt, root_joint)
                if deeper:
                    module_node.children.append(deeper)

        return module_node

    def _traverse_through_joint(self, joint: str, parent_joint: str) -> Optional[ModuleNode]:
        """Traverse through a joint and its descendants to find module roots.

        Args:
            joint: The joint to traverse through.
            parent_joint: The parent joint this was reached from.

        Returns:
            ModuleNode if found, None otherwise.
        """
        children = cmds.listRelatives(joint, children=True, type="joint") or []
        logger.info("_traverse_through_joint: At %s, children: %s", joint, children)

        for child_jnt in children:
            child_module = self._identify_module_at_joint(child_jnt, parent_joint=joint)
            if child_module:
                logger.info("_traverse_through_joint: Found module at %s: %s", child_jnt, child_module.instance_name)
                return child_module
            else:
                # Recurse deeper
                found = self._traverse_through_joint(child_jnt, joint)
                if found:
                    return found
        return None

    def _identify_module_at_joint(self, joint: str, parent_joint: str = None) -> Optional[ModuleNode]:
        """Identify if a joint starts a module, traversing through non-module joints.

        Args:
            joint: The joint to check.
            parent_joint: The parent joint this was reached from (for tracking hierarchy).

        Returns:
            ModuleNode if this joint starts a module, None otherwise.
        """
        if not cmds.objExists(f"{joint}.{MODULE_TYPE_ATTR}"):
            # Not a guide joint - traverse children to find modules deeper
            children = cmds.listRelatives(joint, children=True, type="joint") or []
            for child_jnt in children:
                found = self._identify_module_at_joint(child_jnt, parent_joint=joint)
                if found:
                    return found
            return None

        module_type = cmds.getAttr(f"{joint}.{MODULE_TYPE_ATTR}")
        registry = get_module(module_type)
        if not registry:
            return None

        joint_role = cmds.getAttr(f"{joint}.{JOINT_ROLE_ATTR}") if cmds.objExists(f"{joint}.{JOINT_ROLE_ATTR}") else ""

        # If this joint's role is the root_role, it's a module start
        if joint_role == registry.root_role:
            instance_name = cmds.getAttr(f"{joint}.{MODULE_INSTANCE_ATTR}") if cmds.objExists(f"{joint}.{MODULE_INSTANCE_ATTR}") else joint

            module_node = ModuleNode(
                module_type=module_type,
                instance_name=instance_name,
                root_joint=joint,
                end_joint=self._find_end_joint(joint, registry),
                parent_joint=parent_joint,  # Track which joint this was parented under
            )

            # Recursively process children to find child modules
            children = cmds.listRelatives(joint, children=True, type="joint") or []
            for child_jnt in children:
                child_module = self._identify_module_at_joint(child_jnt, parent_joint=joint)
                if child_module:
                    module_node.children.append(child_module)

            return module_node

        # Not a root joint - traverse children anyway to find child modules
        children = cmds.listRelatives(joint, children=True, type="joint") or []
        for child_jnt in children:
            found = self._identify_module_at_joint(child_jnt, parent_joint=joint)
            if found:
                return found
        return None

    def _find_end_joint(self, root_joint: str, registry) -> Optional[str]:
        """Find the end joint of a module.

        Args:
            root_joint: The root joint of the module.
            registry: The module registry entry.

        Returns:
            The end joint name, or None.
        """
        if not registry.end_role:
            return None

        end_joint_name = root_joint.replace(f"_{registry.root_role}_jInit", f"_{registry.end_role}_jInit")
        end_joint_name = end_joint_name.replace(f"_{registry.root_role}_jDef", f"_{registry.end_role}_jDef")

        if cmds.objExists(end_joint_name):
            return end_joint_name

        # Try to find by traversing children
        current = root_joint
        while True:
            children = cmds.listRelatives(current, children=True, type="joint") or []
            if not children:
                break

            # Check if the first child is the end joint
            child = children[0]
            if registry.end_role in child:
                return child
            current = child

        return None

    def _build_module_node(self, module_node: ModuleNode) -> None:
        """Build a single module node.

        Args:
            module_node: The module node to build.
        """
        from tik.trigger.modules import get_module_class

        # Get the module class
        module_class = get_module_class(module_node.module_type)
        if not module_class:
            logger.error("Module class not found: %s", module_node.module_type)
            return

        # Use the module from session if available (it's already populated with guides)
        if self.session and module_node.instance_name in self.session.modules:
            module = self.session.modules[module_node.instance_name]
            logger.debug("Using module from session: %s", module_node.instance_name)
        else:
            # Create new module instance
            module = module_class(name=module_node.instance_name)
            logger.debug("Created new module instance: %s", module_node.instance_name)

        # Build the module
        try:
            module.build()
            module_node.built_module = module
            self._built_modules[module_node.instance_name] = module
            logger.info("Built module: %s (%s)", module_node.instance_name, module_node.module_type)
        except Exception as e:
            logger.error("Failed to build module %s: %s", module_node.instance_name, e)
            raise

        # Recursively build children
        for child in module_node.children:
            self._build_module_node(child)

    def _connect_modules(self) -> None:
        """Connect modules based on DAG parent-child relationships.

        When a child module's root was parented under a parent module's joint,
        connect the child's rootPlug to the parent's socket.
        """
        for module_node in self._hierarchy:
            self._connect_module_recursive(module_node)

    def _connect_module_recursive(self, module_node: ModuleNode) -> None:
        """Recursively connect a module and its children.

        Args:
            module_node: The module node to connect.
        """
        if not module_node.built_module:
            return

        # Process children
        for child in module_node.children:
            if not child.built_module:
                continue

            # The child was parented under a specific joint in the parent guide hierarchy
            # Find the parent's socket that corresponds to that joint
            if child.parent_joint:
                parent_module = module_node.built_module
                child_module = child.built_module

                # Find the socket on parent where the child should connect
                for socket_name, socket in parent_module.sockets.items():
                    # The socket is defined on a deformation joint (e.g., chain1_end_jDef)
                    # We need to parent the child's root deformation joint under it
                    if socket.joint_name:
                        try:
                            # Parent child's root joint under parent's socket joint
                            cmds.parent(child_module.plugs.get("rootPlug").joint_name, socket.joint_name)
                            logger.info("Connected %s (%s) -> %s (%s)",
                                       child_module.name, child_module.plugs.get("rootPlug").joint_name,
                                       parent_module.name, socket.joint_name)
                        except Exception as e:
                            logger.warning("Could not parent %s under %s: %s",
                                          child_module.plugs.get("rootPlug").joint_name, socket.joint_name, e)
                        break

            # Recurse to children
            self._connect_module_recursive(child)

    def _handle_guides(self) -> None:
        """Handle guide joints based on afterlife setting."""
        if self.afterlife == 0:
            # Do nothing
            return

        # Find all joints with moduleType attribute (these are guide joints)
        import maya.cmds as cmds
        all_guides = []
        for jnt in cmds.ls(type="joint"):
            if cmds.objExists(f"{jnt}.{MODULE_TYPE_ATTR}"):
                all_guides.append(jnt)

        if self.afterlife == 1:
            # Hide guides
            for jnt in all_guides:
                try:
                    cmds.hide(jnt)
                except:
                    pass
            logger.info("Guides hidden")
        elif self.afterlife == 2:
            # Delete guides - use full paths to avoid ambiguity
            for jnt in all_guides:
                try:
                    if cmds.objExists(jnt):
                        cmds.delete(jnt)
                except:
                    pass
            logger.info("Guides deleted")

    def save_action(self, feed_data: dict = None) -> dict:
        """Save action configuration.

        Kinematics action doesn't have module-specific settings to save.

        Args:
            feed_data: The feed data dictionary.

        Returns:
            Empty dict (no settings to persist).
        """
        return {}

    @staticmethod
    def ui(ctrl, layout, handler, *args, **kwargs):
        """Define UI controls for kinematics action settings.

        Note: UI is not implemented in this phase. This is a placeholder
        for future UI development.

        Args:
            ctrl: The controller object.
            layout: The layout to add controls to.
            handler: The handler object.
            *args: Additional arguments.
            **kwargs: Additional keyword arguments.
        """
        # UI will be implemented in a future phase
        # For now, kinematics settings are set programmatically via feed()
        pass
