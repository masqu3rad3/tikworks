"""Central module registry for tik.trigger.

This module defines all known module types and their joint roles.
It provides a single source of truth for module identification.

Usage:
    from tik.trigger.core.module_registry import MODULES, get_module, MODULE_TYPE_ATTR

    # Check if a module type exists
    if "fkchain" in MODULES:
        ...

    # Get a module's registry entry
    fkchain_reg = MODULES["fkchain"]
    for role in fkchain_reg.joint_roles:
        print(role.name)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# Attribute Names (Constants)
# =============================================================================

# Custom attribute names added to guide joints for identification
MODULE_TYPE_ATTR = "moduleType"       # Module type name (e.g., "fkchain", "arm")
JOINT_ROLE_ATTR = "jointRole"         # Joint role within module (e.g., "root", "end")
MODULE_INSTANCE_ATTR = "moduleInstance"  # Instance name (e.g., "chain1", "my_arm_L")


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass(frozen=True)
class JointRole:
    """Defines a joint role within a module.

    Attributes:
        name: The role name (e.g., "root", "collar", "shoulder", "end")
        is_root: True if this is the root (start) joint of the module
        is_socket: True if this joint can accept child connections (any joint can be a socket)
    """
    name: str
    is_root: bool = False
    is_socket: bool = False


@dataclass(frozen=True)
class ModuleRegistry:
    """Registry entry for a module type.

    Attributes:
        module_type: Unique identifier for the module type (e.g., "fkchain", "arm")
        joint_roles: Tuple of JointRole definitions in order (root to end)
        root_role: Name of the root joint role
        socket_role: Name of the primary socket joint role (where children typically connect)
    """
    module_type: str
    joint_roles: tuple[JointRole, ...]
    root_role: str
    socket_role: Optional[str] = None

    def get_role(self, role_name: str) -> Optional[JointRole]:
        """Get a joint role by name.

        Args:
            role_name: The role name to find.

        Returns:
            The JointRole if found, None otherwise.
        """
        for role in self.joint_roles:
            if role.name == role_name:
                return role
        return None

    @property
    def root_joint_role(self) -> JointRole:
        """Get the root joint role."""
        return self.get_role(self.root_role)

    @property
    def socket_joint_role(self) -> Optional[JointRole]:
        """Get the socket joint role, if any."""
        if self.socket_role:
            return self.get_role(self.socket_role)
        return None


# =============================================================================
# Module Registry (runtime-populated from data.json)
# =============================================================================

MODULES: dict[str, ModuleRegistry] = {}


# =============================================================================
# Helper Functions
# =============================================================================

def get_module(module_type: str) -> Optional[ModuleRegistry]:
    """Get the registry entry for a module type.

    Args:
        module_type: The module type name.

    Returns:
        The ModuleRegistry if found, None otherwise.
    """
    return MODULES.get(module_type)


def is_registered(module_type: str) -> bool:
    """Check if a module type is registered.

    Args:
        module_type: The module type name.

    Returns:
        True if registered, False otherwise.
    """
    return module_type in MODULES


def register_module_type(
    module_type: str,
    joint_roles: list[JointRole],
    root_role: str,
    socket_role: Optional[str] = None,
) -> None:
    """Register a new module type at runtime.

    This allows dynamic module registration from data.json files.

    Args:
        module_type: Unique identifier for the module type
        joint_roles: List of JointRole definitions
        root_role: Name of the root joint role
        socket_role: Name of the primary socket joint role, if any
    """
    # Skip if already registered (idempotent)
    if module_type in MODULES:
        return

    MODULES[module_type] = ModuleRegistry(
        module_type=module_type,
        joint_roles=tuple(joint_roles),
        root_role=root_role,
        socket_role=socket_role,
    )
