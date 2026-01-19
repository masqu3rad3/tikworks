"""
Blessed helper expansion registry.

Blessed helpers are tik.maya methods that represent stable, well-understood
semantic operations that can be safely expanded into known sequences of
cmds (or OpenMaya) calls.

Each helper expansion must:
- Declare the tik.maya method name
- Declare its cmds expansion
- Be testable in isolation
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class HelperExpansion:
    """Definition of a blessed helper expansion.

    Attributes:
        method_name: The tik.maya method name (e.g., "unlock_normals").
        type_name: The tik.maya type this method belongs to (e.g., "Mesh").
        description: Human-readable description of what this helper does.
        cmds_template: Template or callable for generating cmds code.
        requires_openmaya: Whether the expansion uses OpenMaya calls.
        notes: Additional notes about the expansion.
    """

    method_name: str
    type_name: str
    description: str
    cmds_template: str
    requires_openmaya: bool = False
    notes: Optional[str] = None

    def expand(self, node_expr: str, args: List[str], kwargs: Dict[str, str]) -> str:
        """Expand this helper into cmds code.

        Args:
            node_expr: The expression for the node (e.g., "my_mesh").
            args: Positional arguments passed to the method.
            kwargs: Keyword arguments passed to the method.

        Returns:
            The expanded cmds code string.
        """
        return self.cmds_template.format(
            node=node_expr,
            args=", ".join(args),
            kwargs=kwargs,
        )


class HelperRegistry:
    """Registry for blessed helper expansions.

    The registry maintains a collection of helper expansions that have been
    explicitly approved for automatic conversion. Only helpers registered
    here will be expanded; all others will be flagged as unsupported.
    """

    def __init__(self) -> None:
        """Initialize an empty helper registry."""
        self._helpers: Dict[str, HelperExpansion] = {}

    def register(
        self,
        method_name: str,
        type_name: str,
        description: str,
        cmds_template: str,
        requires_openmaya: bool = False,
        notes: Optional[str] = None,
    ) -> "HelperRegistry":
        """Register a new blessed helper expansion.

        Args:
            method_name: The tik.maya method name.
            type_name: The tik.maya type this method belongs to.
            description: Human-readable description.
            cmds_template: Template for generating cmds code.
            requires_openmaya: Whether OpenMaya is used.
            notes: Additional notes.

        Returns:
            Self for method chaining.
        """
        key = f"{type_name}.{method_name}"
        self._helpers[key] = HelperExpansion(
            method_name=method_name,
            type_name=type_name,
            description=description,
            cmds_template=cmds_template,
            requires_openmaya=requires_openmaya,
            notes=notes,
        )
        return self

    def get(self, type_name: str, method_name: str) -> Optional[HelperExpansion]:
        """Get a helper expansion by type and method name.

        Args:
            type_name: The tik.maya type name.
            method_name: The method name.

        Returns:
            The HelperExpansion if registered, None otherwise.
        """
        key = f"{type_name}.{method_name}"
        return self._helpers.get(key)

    def is_blessed(self, type_name: str, method_name: str) -> bool:
        """Check if a method is a blessed helper.

        Args:
            type_name: The tik.maya type name.
            method_name: The method name.

        Returns:
            True if the method is registered as a blessed helper.
        """
        key = f"{type_name}.{method_name}"
        return key in self._helpers

    def list_helpers(self) -> List[HelperExpansion]:
        """List all registered helpers.

        Returns:
            List of all registered HelperExpansion instances.
        """
        return list(self._helpers.values())

    def __len__(self) -> int:
        """Return the number of registered helpers."""
        return len(self._helpers)


def create_default_registry() -> HelperRegistry:
    """Create and populate the default helper registry.

    This contains the initial set of blessed helpers that are safe
    for automatic expansion.

    Returns:
        A populated HelperRegistry instance.
    """
    registry = HelperRegistry()

    # =========================================================================
    # Joint helpers
    # =========================================================================

    registry.register(
        method_name="orient",
        type_name="Joint",
        description="Orient the joint using XYZ values",
        cmds_template="cmds.joint({node}, edit=True, orientation={args})",
        notes="Direct mapping to cmds.joint with -orientation flag",
    )

    # =========================================================================
    # Transform helpers
    # =========================================================================

    registry.register(
        method_name="freeze",
        type_name="Transform",
        description="Freeze transformations",
        cmds_template=(
            "cmds.makeIdentity({node}, apply=True, "
            "translate=True, rotate=True, scale=True)"
        ),
        notes="Default freezes all transform channels",
    )

    # =========================================================================
    # DagNode helpers
    # =========================================================================

    registry.register(
        method_name="select",
        type_name="DagNode",
        description="Select this node in Maya",
        cmds_template="cmds.select({node}, replace=True)",
    )

    # =========================================================================
    # Curve helpers
    # =========================================================================

    # scale_points is NOT blessed - it uses OpenMaya and has complex behavior

    # =========================================================================
    # Mesh helpers
    # =========================================================================

    # unlock_normals is NOT blessed by default - uses OpenMaya extensively
    # get_vertex_colors is NOT blessed - returns OpenMaya types
    # set_vertex_colors is NOT blessed - uses OpenMaya types

    # Note: These mesh helpers could be blessed in future iterations if
    # we define cmds-only equivalents, but the current implementations
    # rely heavily on OpenMaya for performance and correctness.

    # =========================================================================
    # Node helpers
    # =========================================================================

    registry.register(
        method_name="exists",
        type_name="Node",
        description="Check if node exists in scene",
        cmds_template="cmds.objExists({node})",
    )

    registry.register(
        method_name="has_attr",
        type_name="Node",
        description="Check if node has an attribute",
        cmds_template="cmds.attributeQuery({args}, node={node}, exists=True)",
    )

    # =========================================================================
    # Plug helpers
    # =========================================================================

    registry.register(
        method_name="exists",
        type_name="Plug",
        description="Check if attribute exists",
        cmds_template="cmds.attributeQuery({attr}, node={node}, exists=True)",
    )

    registry.register(
        method_name="disconnect",
        type_name="Plug",
        description="Disconnect attribute from source",
        cmds_template=(
            "# Disconnect {node}.{attr}\n"
            "_sources = cmds.listConnections('{node}.{attr}', plugs=True, source=True)\n"
            "if _sources:\n"
            "    cmds.disconnectAttr(_sources[0], '{node}.{attr}')"
        ),
        notes="Expanded to multi-line to handle source lookup",
    )

    return registry


# Global default registry instance
_default_registry: Optional[HelperRegistry] = None


def get_default_registry() -> HelperRegistry:
    """Get the default helper registry (lazy initialization).

    Returns:
        The default HelperRegistry instance.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = create_default_registry()
    return _default_registry


@dataclass
class UnsupportedMethod:
    """Represents an unsupported method that cannot be converted."""

    type_name: Optional[str]
    method_name: str
    reason: str
    original_code: str
    line_number: int


def check_method_support(
    type_name: Optional[str],
    method_name: str,
    registry: Optional[HelperRegistry] = None,
) -> bool:
    """Check if a method call is supported for conversion.

    A method is supported if:
    1. It's handled by a built-in rule, OR
    2. It's registered as a blessed helper

    Args:
        type_name: The tik.maya type name (if known).
        method_name: The method name.
        registry: Helper registry to check (uses default if None).

    Returns:
        True if the method is supported for conversion.
    """
    registry = registry or get_default_registry()

    # Built-in methods handled by rules (always supported)
    BUILTIN_METHODS = frozenset({
        # Node methods
        "create",
        "rename",
        "delete",
        "duplicate",
        "add_attr",
        "delete_attr",
        "has_attr",
        "exists",
        # Plug methods
        "get",
        "set",
        "connect",
        "disconnect",
        "lock",
        "unlock",
        "get_input",
        "list_outputs",
        # DagNode methods
        "select",
        # Transform methods
        "freeze",
        # Type-specific create methods are handled by rules
    })

    if method_name in BUILTIN_METHODS:
        return True

    if type_name and registry.is_blessed(type_name, method_name):
        return True

    return False


# List of methods known to be unsupported with reasons
UNSUPPORTED_METHODS: Dict[str, str] = {
    # Complex OpenMaya operations
    "unlock_normals": "Uses OpenMaya MFnMesh; no direct cmds equivalent",
    "get_vertex_colors": "Returns OpenMaya MColorArray; no direct cmds equivalent",
    "set_vertex_colors": "Uses OpenMaya MFnMesh; performance-critical",
    "vertices": "Returns OpenMaya MPointArray; no direct cmds equivalent",
    "vertices_in_radius": "Uses OpenMaya spatial queries",
    "cvs": "Returns OpenMaya MPointArray; no direct cmds equivalent",
    "scale_points": "Uses OpenMaya MFnNurbsCurve; modifies CV positions directly",
    # State-dependent operations
    "snap_to": "Uses OpenMaya MFnTransform; complex world-space operations",
    "collect_hierarchy": "Recursive traversal with type filtering",
    "collect_shape_transforms": "Hierarchical shape collection",
    # Properties that return OpenMaya types
    "world_translation": "Returns OpenMaya MVector",
    "world_matrix": "Returns OpenMaya MMatrix",
    "matrix": "Returns OpenMaya MMatrix",
    "parent_matrix": "Returns OpenMaya MMatrix",
    "dag_path": "Returns OpenMaya MDagPath",
    "mdag_path": "Returns OpenMaya MDagPath",
    "bounding_box": "Returns OpenMaya MBoundingBox",
}


def get_unsupported_reason(method_name: str) -> Optional[str]:
    """Get the reason why a method is unsupported.

    Args:
        method_name: The method name.

    Returns:
        The reason string if known, None otherwise.
    """
    return UNSUPPORTED_METHODS.get(method_name)

