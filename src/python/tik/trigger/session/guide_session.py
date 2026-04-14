"""Guide session management for tik.trigger.

Manages the guide creation workflow including:
- Creating module instances with guides
- Collecting guide data from the scene
- Saving/loading guide sessions
- Building rigs from guides
- Connecting modules via socket/plug relationships
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..core.schemas import GuideData, ConnectionData
from tik.trigger.core.io import IO, GUIDE_SESSION_EXT
from tik.shared.io import ensure_extension

if TYPE_CHECKING:
    from tik.trigger.core.rig_module import RigModule

logger = logging.getLogger(__name__)


class GuideSession:
    """Manages guide creation and persistence for a rigging session.

    GuideSession handles the workflow of:
    1. Creating module instances with guide joints
    2. Collecting guide data from the scene
    3. Saving guide sessions to disk
    4. Loading and rebuilding guides from saved sessions
    5. Building rigs from guides
    6. Connecting modules via socket/plug relationships

    Example:
        session = GuideSession()
        session.create_module("arm", "right_arm", side="R")
        session.save("my_character.trg")

        # Later...
        session.load("my_character.trg")
        session.build_all()
    """

    def __init__(self, file_path: Optional[str] = None) -> None:
        """Initialize the guide session.

        Args:
            file_path: Optional default file path for save/load operations.
        """
        self._io = IO()
        self._file_path = Path(file_path) if file_path else None
        self._modules: dict[str, RigModule] = {}
        self._connections: list[ConnectionData] = []
        if file_path:
            self._io.file_path = self._file_path

    @property
    def file_path(self) -> Optional[Path]:
        """Return the current session file path."""
        return self._file_path

    @property
    def modules(self) -> dict[str, RigModule]:
        """Return the registered modules."""
        return self._modules.copy()

    @property
    def connections(self) -> list[ConnectionData]:
        """Return the module connections."""
        return self._connections.copy()

    def create_module(
        self, module_type: str, name: Optional[str] = None, **kwargs
    ) -> RigModule:
        """Create a module instance with guides.

        Args:
            module_type: The module type to create (e.g., 'arm', 'connector').
            name: Optional custom name for this module instance.
            **kwargs: Additional arguments passed to the module constructor.

        Returns:
            The created RigModule instance.

        Raises:
            ValueError: If the module type is not found.
        """
        from tik.trigger.modules import get_module_class

        module_class = get_module_class(module_type)
        if not module_class:
            raise ValueError(f"Unknown module type: {module_type}")

        instance_name = name or f"{module_type}_{len(self._modules)}"
        module = module_class(name=instance_name, **kwargs)
        module.create_guides()
        self._modules[instance_name] = module

        logger.info("Created module %s: %s", module_type, instance_name)
        return module

    def add_module(self, instance_id: str, module: RigModule) -> None:
        """Add an existing module to the session.

        Args:
            instance_id: Unique identifier for this module instance.
            module: The RigModule instance to add.
        """
        self._modules[instance_id] = module
        logger.debug("Added module: %s", instance_id)

    def get_module(self, instance_id: str) -> Optional[RigModule]:
        """Get a module by instance ID.

        Args:
            instance_id: The instance identifier.

        Returns:
            The RigModule instance or None if not found.
        """
        return self._modules.get(instance_id)

    def remove_module(self, instance_id: str) -> None:
        """Remove a module from the session.

        Args:
            instance_id: The instance identifier to remove.
        """
        if instance_id in self._modules:
            module = self._modules[instance_id]
            if module.is_built:
                module.delete()
            else:
                module.delete_guides()
            del self._modules[instance_id]
            # Clean up any connections involving this module
            self._connections = [
                c for c in self._connections
                if c.parent_module != instance_id and c.child_module != instance_id
            ]
            logger.info("Removed module: %s", instance_id)

    def clear(self) -> None:
        """Clear all modules from the session."""
        for instance_id, module in self._modules.items():
            if module.is_built:
                module.delete()
            else:
                module.delete_guides()
        self._modules.clear()
        self._connections.clear()
        logger.info("Cleared all modules")

    def connect(
        self, parent_module_id: str, parent_plug: str, child_module_id: str, child_socket: str
    ) -> None:
        """Connect a child module's socket to a parent module's plug.

        Args:
            parent_module_id: The parent module instance ID.
            parent_plug: The plug name on the parent module.
            child_module_id: The child module instance ID.
            child_socket: The socket name on the child module.

        Raises:
            ValueError: If either module or connection point is not found.
        """
        parent = self._modules.get(parent_module_id)
        if not parent:
            raise ValueError(f"Parent module not found: {parent_module_id}")

        child = self._modules.get(child_module_id)
        if not child:
            raise ValueError(f"Child module not found: {child_module_id}")

        # Get the plug from parent
        plug = parent.plugs.get(parent_plug)
        if not plug:
            raise ValueError(f"Plug '{parent_plug}' not found on module '{parent_module_id}'")

        # Connect child socket to parent plug
        child.connect_to(child_socket, plug)

        # Track the connection
        self._connections.append(ConnectionData(
            parent_module=parent_module_id,
            parent_plug=parent_plug,
            child_module=child_module_id,
            child_socket=child_socket,
        ))
        logger.info("Connected %s:%s -> %s:%s", parent_module_id, parent_plug, child_module_id, child_socket)

    def _collect_guides(self) -> list[dict]:
        """Collect all guide data from the scene.

        Returns guide data for all modules including position, rotation,
        side, parent relationships, and any custom user attributes.

        Returns:
            List of guide data dictionaries suitable for JSON serialization.
        """
        all_guide_data = []

        for instance_id, module in self._modules.items():
            # Get fresh guide data from scene
            scene_guides = module.get_guide_data_from_scene()

            module_instance_data = {
                "module_type": module.module_name,
                "instance_id": instance_id,
                "guides": [self._guide_data_to_dict(gd) for gd in scene_guides],
                "settings": module.settings,
            }
            all_guide_data.append(module_instance_data)

        logger.debug("Collected guide data for %d modules", len(all_guide_data))
        return all_guide_data

    def _guide_data_to_dict(self, guide_data: GuideData) -> dict:
        """Convert GuideData to a serializable dictionary.

        Args:
            guide_data: The GuideData instance.

        Returns:
            Dictionary representation of the guide data.
        """
        return {
            "name": guide_data.name,
            "position": guide_data.position,
            "rotation": guide_data.rotation,
            "side": guide_data.side,
            "parent": guide_data.parent,
            "children": guide_data.children,
        }

    def rebuild_modules(self, modules_data: list[dict]) -> None:
        """Rebuild modules from saved session data.

        Args:
            modules_data: List of module instance dictionaries
                from a previously saved session.
        """
        from maya import cmds

        # Clear existing modules first
        self.clear()

        from tik.trigger.modules import get_module_class

        # First pass: create all module instances and guides
        for module_data in modules_data:
            module_type = module_data["module_type"]
            instance_id = module_data["instance_id"]
            guides_list = module_data.get("guides", [])
            settings = module_data.get("settings", {})

            # Get the module class and create new instance
            module_class = get_module_class(module_type)
            if not module_class:
                logger.warning("Unknown module type: %s, skipping", module_type)
                continue

            module = module_class(name=instance_id)
            module.set_settings(settings)

            # Rebuild each guide
            for gd in guides_list:
                guide_data = GuideData(
                    name=gd["name"],
                    position=tuple(gd["position"]),
                    rotation=tuple(gd["rotation"]),
                    side=gd.get("side", "C"),
                    parent=gd.get("parent"),
                    children=gd.get("children", []),
                )
                module.add_guide(guide_data)

            # Create the actual Maya nodes
            module.create_guides()
            # Sync saved positions to scene
            module.sync_guides_to_scene()
            self._modules[instance_id] = module

            logger.info("Rebuilt guides for module: %s (%s)", instance_id, module_type)

        # Second pass: apply parent relationships from saved data
        for module_data in modules_data:
            guides_list = module_data.get("guides", [])
            for gd in guides_list:
                if gd.get("parent") and cmds.objExists(gd["name"]):
                    parent_name = gd["parent"]
                    if cmds.objExists(parent_name):
                        # Check if already parented correctly
                        current_parent = cmds.listRelatives(gd["name"], parent=True, type="joint")
                        if not current_parent or current_parent[0] != parent_name:
                            cmds.parent(gd["name"], parent_name)
                            logger.debug("Re-parented %s under %s", gd["name"], parent_name)

    def _restore_connections(self, connections_data: list[dict]) -> None:
        """Restore module connections from saved data.

        Args:
            connections_data: List of connection dictionaries.
        """
        for conn_data in connections_data:
            # Directly restore connection data without validation
            # Modules may not be built yet during guide restore
            self._connections.append(ConnectionData(
                parent_module=conn_data["parent_module"],
                parent_plug=conn_data["parent_plug"],
                child_module=conn_data["child_module"],
                child_socket=conn_data["child_socket"],
            ))

    def save(self, file_path: Optional[str] = None) -> Optional[Path]:
        """Save the guide session to a file.

        Args:
            file_path: Optional override file path.

        Returns:
            The path the session was saved to, or None on failure.
        """
        target = Path(file_path) if file_path else self._file_path
        if not target:
            logger.error("No file path specified for saving")
            return None

        target = ensure_extension(target, GUIDE_SESSION_EXT)
        self._io.file_path = target

        session_data = {
            "version": "3.0",
            "modules": self._collect_guides(),
            "connections": [
                {
                    "parent_module": c.parent_module,
                    "parent_plug": c.parent_plug,
                    "child_module": c.child_module,
                    "child_socket": c.child_socket,
                }
                for c in self._connections
            ],
        }

        result = self._io.write(session_data)
        if result:
            self._file_path = target
            logger.info("Guide session saved: %s", target)

        return result

    def load(self, file_path: str, reset_scene: bool = False) -> bool:
        """Load a guide session from a file.

        Args:
            file_path: Path to the session file to load.
            reset_scene: If True, clear existing modules before loading.

        Returns:
            True if the session was loaded successfully, False otherwise.
        """
        target = Path(file_path)
        self._io.file_path = target

        data = self._io.read()
        if not data:
            logger.error("Failed to load guide session from: %s", target)
            return False

        if reset_scene:
            self.clear()

        # Rebuild modules
        modules_data = data.get("modules", [])
        self.rebuild_modules(modules_data)

        # Restore connections
        connections_data = data.get("connections", [])
        self._connections.clear()
        self._restore_connections(connections_data)

        self._file_path = target
        logger.info("Guide session loaded: %s", target)
        return True

    def build_all(self) -> None:
        """Build all modules in the session."""
        for instance_id, module in self._modules.items():
            if not module.is_built:
                module.build()
                logger.info("Built module: %s", instance_id)

    def get_scene_roots(self) -> list[dict]:
        """Get all root guide joints in the current scene.

        Returns:
            List of dictionaries containing root joint information.
        """
        roots = []
        for instance_id, module in self._modules.items():
            scene_guides = module.get_guide_data_from_scene()
            if scene_guides:
                # First guide is typically the root
                root_guide = scene_guides[0]
                roots.append({
                    "instance_id": instance_id,
                    "module_type": module.module_name,
                    "root_joint": root_guide.name,
                    "side": root_guide.side,
                })
        return roots

    def get_module_build_data(self, instance_id: str) -> Optional[dict]:
        """Get the build data for a module.

        Args:
            instance_id: The module instance identifier.

        Returns:
            The build data dictionary, or None if module not found.
        """
        module = self._modules.get(instance_id)
        if not module:
            return None
        return module.get_build_data()

    def load_from_dag(self, root_joint: str, reset_scene: bool = False) -> list[dict]:
        """Load module hierarchy from existing Maya DAG starting at root_joint.

        This reads guide joints from an existing Maya hierarchy (created manually
        or from another source) and reconstructs the module hierarchy.

        The guides must already exist in Maya with proper module identification
        attributes (moduleType, jointRole, moduleInstance).

        Args:
            root_joint: Name of the root joint to start from.
            reset_scene: If True, clear existing modules before loading.

        Returns:
            List of module instance dictionaries representing the hierarchy.
        """
        from maya import cmds
        from tik.trigger.core.module_registry import (
            MODULE_TYPE_ATTR,
            JOINT_ROLE_ATTR,
            MODULE_INSTANCE_ATTR,
            get_module,
        )

        if reset_scene:
            self.clear()

        hierarchy = []

        def traverse(joint: str) -> Optional[dict]:
            """Recursively traverse DAG and identify modules."""
            if not cmds.objExists(joint):
                return None

            # Check if this joint has module identification attributes
            if not cmds.objExists(f"{joint}.{MODULE_TYPE_ATTR}"):
                return None

            module_type = cmds.getAttr(f"{joint}.{MODULE_TYPE_ATTR}")
            instance_name = cmds.getAttr(f"{joint}.{MODULE_INSTANCE_ATTR}") if cmds.objExists(f"{joint}.{MODULE_INSTANCE_ATTR}") else joint

            registry = get_module(module_type)
            if not registry:
                logger.warning("Unknown module type: %s", module_type)
                return None

            joint_role = cmds.getAttr(f"{joint}.{JOINT_ROLE_ATTR}") if cmds.objExists(f"{joint}.{JOINT_ROLE_ATTR}") else ""

            # Only process if this is a module root
            if joint_role != registry.root_role:
                return None

            # Collect guides for this module
            guides = []
            _collect_module_guides(joint, module_type, guides)

            # Recursively process children
            children_data = []
            children = cmds.listRelatives(joint, children=True, type="joint") or []
            for child in children:
                child_data = traverse(child)
                if child_data:
                    children_data.append(child_data)

            module_data = {
                "module_type": module_type,
                "instance_id": instance_name,
                "guides": guides,
                "children": children_data,
            }

            return module_data

        def _collect_module_guides(joint: str, module_type: str, guides: list) -> None:
            """Collect all guide joints belonging to a module."""
            registry = get_module(module_type)
            if not registry:
                return

            # Start from the root joint and traverse down
            current = joint
            visited = set()

            while current and current not in visited:
                visited.add(current)

                if cmds.objExists(current):
                    pos = cmds.xform(current, query=True, worldSpace=True, translation=True)
                    rot = cmds.xform(current, query=True, worldSpace=True, rotation=True)

                    guides.append({
                        "name": current,
                        "position": tuple(pos),
                        "rotation": tuple(rot),
                        "side": "C",
                    })

                # Move to first child that belongs to the same module
                children = cmds.listRelatives(current, children=True, type="joint") or []
                next_joint = None
                for child in children:
                    if cmds.objExists(f"{child}.{MODULE_TYPE_ATTR}"):
                        child_type = cmds.getAttr(f"{child}.{MODULE_TYPE_ATTR}")
                        if child_type == module_type:
                            next_joint = child
                            break
                current = next_joint

        # Start traversal
        module_data = traverse(root_joint)
        if module_data:
            hierarchy.append(module_data)

        return hierarchy

    def _find_roots_in_scene(self) -> list[str]:
        """Find all root joints in the current scene.

        Returns:
            List of root joint names.
        """
        from maya import cmds

        root_joints = []
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

            from tik.trigger.core.module_registry import get_module
            registry = get_module(module_type)
            if registry and joint_role == registry.root_role:
                root_joints.append(jnt)

        return root_joints