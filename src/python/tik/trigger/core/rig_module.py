"""Unified RigModule base class for tik.trigger.

This module provides a unified base class that combines guide creation
and rig building into a single cohesive unit. It manages the complete
lifecycle: guide phase (user positioning) and build phase (rig construction).

Uses tik.maya (tm) for all DCC operations:
- tm.Joint for joint creation/manipulation
- tm.Transform for group creation
- tm.resolve() to wrap existing nodes
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from maya import cmds

from tik.trigger.core.socket_data import JointType, ModuleConnectors, Plug, Socket
from tik.trigger.core.schemas import GuideData
from tik.trigger.core.module_registry import MODULES, ModuleRegistry, MODULE_TYPE_ATTR, JOINT_ROLE_ATTR, MODULE_INSTANCE_ATTR

if TYPE_CHECKING:
    import tik.maya as tm

logger = logging.getLogger(__name__)


class RigModule(ABC):
    """Unified base class for guide creation and rig building.

    This class manages the complete lifecycle of a rig module:

    **Guide Phase:**
    - User positions guide joints in the DCC scene
    - Guides are stored as GuideData and synced with scene

    **Build Phase:**
    - Rig structure is created from guide positions
    - Plugs and sockets are defined for inter-module connection

    **Connection Phase:**
    - Modules can be wired together via socket/plug connections

    Subclasses must implement all `_create_*_impl()` methods.

    Attributes:
        _module_name: The module type identifier (e.g., "bipedArm", "spine")
    """

    _module_name: str = ""

    def __init__(self, name: Optional[str] = None) -> None:
        """Initialize the rig module.

        Args:
            name: Optional custom name for this module instance.
        """
        self._name = name or self.__class__.__name__
        self._guides: list[GuideData] = []
        self._selected_guide: Optional[int] = None
        self._settings: dict = {}
        self._built: bool = False
        self._connectors = ModuleConnectors()
        logger.debug("Initialized RigModule: %s", self._name)

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def name(self) -> str:
        """Return the module instance name."""
        return self._name

    @property
    def module_name(self) -> str:
        """Return the module type name."""
        return self._module_name

    @property
    def guides(self) -> list[GuideData]:
        """Return a copy of the list of guide data."""
        return self._guides.copy()

    @property
    def settings(self) -> dict:
        """Return a copy of the current settings."""
        return self._settings.copy()

    @property
    def is_built(self) -> bool:
        """Return whether the rig has been built."""
        return self._built

    @property
    def connectors(self) -> ModuleConnectors:
        """Return the module's plugs and sockets container."""
        return self._connectors

    @property
    def plugs(self) -> dict[str, Plug]:
        """Return a dict of plugs by name."""
        return self._connectors.plugs

    @property
    def sockets(self) -> dict[str, Socket]:
        """Return a dict of sockets by name."""
        return self._connectors.sockets

    @property
    def selected_guide(self) -> Optional[int]:
        """Return the currently selected guide index."""
        return self._selected_guide

    # =========================================================================
    # Guide Phase Methods
    # =========================================================================

    def create_guides(self) -> None:
        """Create all guide joints in the DCC scene.

        Calls the subclass implementation to create Maya guide nodes
        based on stored guide data, then syncs the guide data.

        If guides have already been added (e.g., from loading a session),
        their data is preserved and synced to scene. Otherwise, guides
        are collected fresh from the scene.
        """
        self._create_guides_impl()

        # Only refresh from scene if we don't already have saved guide data
        if not self._guides:
            # Sync guide data from scene to internal list
            self._guides = self._get_guide_data_impl()
        else:
            # We have saved guide data - sync positions to scene
            self.sync_guides_to_scene()

    def update_guide(self, index: int, guide_data: GuideData) -> None:
        """Update a guide at the given index.

        Args:
            index: The index of the guide to update.
            guide_data: The new guide data.
        """
        if 0 <= index < len(self._guides):
            self._guides[index] = guide_data
            self._update_guide_impl(index, guide_data)

    def delete_guides(self) -> None:
        """Delete all guide nodes from the DCC scene and clear the guides list."""
        self._delete_guides_impl()
        self._guides.clear()
        self._selected_guide = None

    def get_guide_data_from_scene(self) -> list[GuideData]:
        """Query current guide positions from the DCC scene.

        Subclasses should implement this to sync guide data with
        actual Maya node positions after user manipulation.

        Returns:
            List of current guide data.
        """
        return self._get_guide_data_impl()

    def sync_guides_to_scene(self) -> None:
        """Sync stored guide data to DCC scene positions.

        Updates Maya guide nodes to match the stored guide data.
        """
        for index, guide_data in enumerate(self._guides):
            self._update_guide_impl(index, guide_data)

    def add_guide(self, guide_data: GuideData) -> None:
        """Add a guide to this module's guide list.

        Args:
            guide_data: The guide data to add.
        """
        self._guides.append(guide_data)
        logger.debug("Added guide: %s", guide_data.name)

    def remove_guide(self, index: int) -> GuideData:
        """Remove a guide by index.

        Args:
            index: The index of the guide to remove.

        Returns:
            The removed guide data.
        """
        return self._guides.pop(index)

    def clear_guides(self) -> None:
        """Remove all guides from the internal list."""
        self._guides.clear()
        self._selected_guide = None

    def select_guide(self, index: Optional[int]) -> None:
        """Set the currently selected guide.

        Args:
            index: The guide index to select, or None to deselect.
        """
        self._selected_guide = index

    def get_selected_guide_data(self) -> Optional[GuideData]:
        """Return the currently selected guide data, if any."""
        if self._selected_guide is not None and 0 <= self._selected_guide < len(self._guides):
            return self._guides[self._selected_guide]
        return None

    # =========================================================================
    # Build Phase Methods
    # =========================================================================

    def build(self) -> None:
        """Build the rig from the guides.

        Executes the build pipeline in order:
        1. _pre_build() - Prepare data from guides
        2. _create_groups_impl() - Create essential rig groups
        3. _create_joints_impl() - Create deformation joints
        4. _create_controllers_impl() - Create control objects
        5. _create_setup_impl() - Create IK/FK/setup connections
        6. _finalize_impl() - Finalize visibility and constraints
        7. _define_connectors() - Populate plugs and sockets

        Raises:
            BuildError: If the build process fails.
        """
        self._validate_for_build()
        self._pre_build()
        self._create_groups_impl()
        self._create_joints_impl()
        self._create_controllers_impl()
        self._create_setup_impl()
        self._finalize_impl()
        self._define_connectors()
        self._built = True
        logger.info("Built rig module: %s", self._name)

    def delete(self) -> None:
        """Delete the built rig from the scene.

        Subclasses should implement _delete_impl() to remove all
        rig nodes created during build().
        """
        self._delete_impl()
        self._built = False
        logger.info("Deleted rig module: %s", self._name)

    def mirror(self, source_guide_names: list[str]) -> None:
        """Mirror the rig from source guides.

        Args:
            source_guide_names: Names of source guides to mirror from.
        """
        self._mirror_impl(source_guide_names)

    def get_build_data(self) -> dict:
        """Return data describing the built rig for serialization.

        Returns:
            A dictionary suitable for serialization.
        """
        return {
            "module_type": self._module_name,
            "name": self._name,
            "settings": self._settings.copy(),
            "guides": [gd.__dict__ for gd in self._guides],
            "connectors": {
                "plugs": {
                    name: {"joint_name": p.joint_name, "joint_type": p.joint_type.value}
                    for name, p in self._connectors.plugs.items()
                },
                "sockets": {
                    name: {"joint_name": s.joint_name, "joint_type": s.joint_type.value}
                    for name, s in self._connectors.sockets.items()
                },
            },
        }

    def validate_guides(self) -> bool:
        """Validate that guides are properly configured for building.

        Returns:
            True if guides are valid, False otherwise.
        """
        return len(self._guides) > 0

    def _validate_for_build(self) -> None:
        """Validate prerequisites before building.

        Raises:
            ValueError: If guides are not valid for building.
        """
        if not self.validate_guides():
            raise ValueError(f"Module '{self._name}' has no guides to build from.")

    # =========================================================================
    # Settings Methods
    # =========================================================================

    def set_settings(self, settings: dict) -> None:
        """Update the module settings.

        Args:
            settings: Dictionary of settings to apply.
        """
        self._settings = settings.copy()

    def get_setting(self, key: str, default=None):
        """Get a specific setting value.

        Args:
            key: The setting key.
            default: Default value if key is not found.
        """
        return self._settings.get(key, default)

    def reset_settings(self) -> None:
        """Reset settings to empty dict."""
        self._settings = {}

    # =========================================================================
    # Connection Management Methods
    # =========================================================================

    def connect_to(self, socket_name: str, plug: Plug) -> None:
        """Connect this module's socket to another module's plug.

        Args:
            socket_name: The socket to connect.
            plug: The plug to connect to.

        Raises:
            ValueError: If socket doesn't exist or is already connected.
        """
        if socket_name not in self._connectors.sockets:
            raise ValueError(f"Socket '{socket_name}' not found in module '{self._name}'")

        socket = self._connectors.sockets[socket_name]
        if socket.connected_plug:
            raise ValueError(f"Socket '{socket_name}' is already connected")

        socket.connected_plug = f"{plug.joint_name}"
        self._on_socket_connected(socket_name, plug)
        logger.info("Connected socket '%s' to plug '%s'", socket_name, plug.joint_name)

    def get_plugs(self) -> list[Plug]:
        """Return list of output plugs for connection."""
        return list(self._connectors.plugs.values())

    def get_sockets(self) -> list[Socket]:
        """Return list of input sockets for connection."""
        return list(self._connectors.sockets.values())

    def _on_socket_connected(self, socket_name: str, plug: Plug) -> None:
        """Hook for subclasses to handle socket connection logic.

        Override this method to implement module-specific connection behavior
        such as creating constraints between joints.

        Args:
            socket_name: The socket that was connected.
            plug: The plug it was connected to.
        """
        pass

    # =========================================================================
    # Abstract Methods - Guide Phase
    # =========================================================================

    @abstractmethod
    def _create_guides_impl(self) -> None:
        """Create all guide joints in the DCC scene.

        Subclasses should implement this to create Maya guide nodes
        based on stored guide data.
        """
        raise NotImplementedError

    @abstractmethod
    def _update_guide_impl(self, index: int, guide_data: GuideData) -> None:
        """Update a guide at the given index in the DCC scene.

        Args:
            index: The index of the guide to update.
            guide_data: The new guide data.
        """
        raise NotImplementedError

    @abstractmethod
    def _delete_guides_impl(self) -> None:
        """Delete all guide nodes from the DCC scene."""
        raise NotImplementedError

    @abstractmethod
    def _get_guide_data_impl(self) -> list[GuideData]:
        """Query current guide positions from the DCC scene.

        Returns:
            List of current guide data.
        """
        raise NotImplementedError

    # =========================================================================
    # Abstract Methods - Build Pipeline
    # =========================================================================

    @abstractmethod
    def _pre_build(self) -> None:
        """Prepare data from guides before building.

        Extract positions, orientations, and settings from the guides
        to prepare for rig construction.
        """
        raise NotImplementedError

    @abstractmethod
    def _create_groups_impl(self) -> None:
        """Create essential rig groups.

        Create groups like limbGrp, scaleGrp, nonScaleGrp, controllerGrp,
        and any other structural groups needed by this module.
        """
        raise NotImplementedError

    @abstractmethod
    def _create_joints_impl(self) -> None:
        """Create the deformation joints for this module.

        Create the joints that will be skinned to and driven by controllers.
        These are typically the 'definitive' joints stored in sockets.
        """
        raise NotImplementedError

    @abstractmethod
    def _create_controllers_impl(self) -> None:
        """Create the control objects for this module.

        Create the controllers that animators will manipulate to control the rig.
        """
        raise NotImplementedError

    @abstractmethod
    def _create_setup_impl(self) -> None:
        """Create the IK/FK setup and connections.

        Create the internal rig wiring - constraints, IK handles,
        node networks, etc.
        """
        raise NotImplementedError

    @abstractmethod
    def _finalize_impl(self) -> None:
        """Finalize the rig build.

        Set up visibility connections, lock/hide attributes,
        and any other finalization steps.
        """
        raise NotImplementedError

    @abstractmethod
    def _delete_impl(self) -> None:
        """Delete the built rig from the DCC scene.

        Remove all rig nodes created during build().
        """
        raise NotImplementedError

    @abstractmethod
    def _mirror_impl(self, source_guide_names: list[str]) -> None:
        """Mirror the rig from source guides.

        Args:
            source_guide_names: Names of source guides to mirror from.
        """
        raise NotImplementedError

    @abstractmethod
    def _define_connectors(self) -> None:
        """Populate the plugs and sockets after joint creation.

        This is called at the end of build() to register the module's
        connection points based on the created joints.
        """
        raise NotImplementedError

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def _set_guide_attributes(self, joint: str, role_name: str) -> None:
        """Set identification attributes on a guide joint.

        This should be called for each guide joint created by a module.
        These attributes are used by the kinematics action to identify
        modules when reading the DAG hierarchy.

        Args:
            joint: The Maya joint node name.
            role_name: The joint role name (e.g., "root", "mid", "end").
        """
        # Add string attributes first, then set their values
        cmds.addAttr(joint, longName=MODULE_TYPE_ATTR, dataType="string")
        cmds.addAttr(joint, longName=JOINT_ROLE_ATTR, dataType="string")
        cmds.addAttr(joint, longName=MODULE_INSTANCE_ATTR, dataType="string")

        cmds.setAttr(f"{joint}.{MODULE_TYPE_ATTR}", self._module_name, type="string")
        cmds.setAttr(f"{joint}.{JOINT_ROLE_ATTR}", role_name, type="string")
        cmds.setAttr(f"{joint}.{MODULE_INSTANCE_ATTR}", self._name, type="string")

    def _get_module_registry(self) -> ModuleRegistry:
        """Get the registry entry for this module type.

        Returns:
            The ModuleRegistry entry for this module type.

        Raises:
            KeyError: If the module type is not registered.
        """
        registry = MODULES.get(self._module_name)
        if registry is None:
            raise KeyError(f"Module type '{self._module_name}' is not registered in MODULES")
        return registry

    def get_joint_by_role(self, role_name: str) -> Optional[str]:
        """Get a guide joint name by its role.

        Args:
            role_name: The joint role name (e.g., "root", "end").

        Returns:
            The joint name if found, None otherwise.
        """
        joint_name = f"{self._name}_{role_name}_jInit"
        if cmds.objExists(joint_name):
            return joint_name
        return None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self._name}')"
