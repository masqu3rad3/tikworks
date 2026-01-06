"""
Conversion rules for maya.cmds → tik.maya transformation.

Rules define how specific maya.cmds patterns should be lifted
into their tik.maya equivalents. Each rule is a deterministic,
testable unit of transformation.

This module mirrors the structure of rules.py but operates
in the reverse direction: compressing cmds into tik.maya.
"""

import ast
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple


@dataclass
class ReverseRuleMatch:
    """Result of a successful reverse rule match."""

    rule_name: str
    original_node: ast.AST
    converted_code: str
    confidence: float = 1.0
    notes: Optional[str] = None
    # Track node name mappings for variable lifting
    node_mappings: Optional[Dict[str, str]] = None


@dataclass
class ReverseRuleContext:
    """Context information available during reverse rule matching.

    Provides access to tracked variable names and their inferred types,
    allowing rules to make informed decisions about conversions.
    """

    variable_types: Dict[str, str]  # Maps variable names to inferred types
    source_lines: List[str]
    imports: Dict[str, str]  # Maps import aliases to full paths
    # Track which string literals map to node variables
    node_variables: Dict[str, str]  # Maps node name strings to variable names

    def get_variable_type(self, name: str) -> Optional[str]:
        """Get the tracked type for a variable name."""
        return self.variable_types.get(name)

    def get_node_variable(self, node_name: str) -> Optional[str]:
        """Get the variable name for a node string literal."""
        return self.node_variables.get(node_name)


class ReverseConversionRule(ABC):
    """Base class for all cmds → tik.maya conversion rules.

    A rule defines:
    - A pattern to match in the AST (cmds calls)
    - A transformation to apply when matched (tik.maya expression)
    - Metadata about the rule (name, category, etc.)
    """

    name: str = "unnamed_reverse_rule"
    category: str = "general"
    description: str = ""

    @abstractmethod
    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Check if this rule applies to the given AST node.

        Args:
            node: AST node to check.
            context: Context with variable type information.

        Returns:
            True if this rule can convert the node.
        """

    @abstractmethod
    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert the matched AST node to tik.maya code.

        Args:
            node: AST node that matched this rule.
            context: Context with variable type information.

        Returns:
            ReverseRuleMatch with the converted code.
        """


# =============================================================================
# Utility Functions
# =============================================================================


def is_cmds_call(node: ast.AST, func_name: str) -> bool:
    """Check if node is a cmds.func_name() call.

    Args:
        node: AST node to check.
        func_name: The cmds function name (e.g., 'createNode').

    Returns:
        True if this is a cmds.func_name() call.
    """
    if not isinstance(node, ast.Call):
        return False

    func = node.func
    # cmds.funcName pattern
    if isinstance(func, ast.Attribute):
        if func.attr == func_name:
            if isinstance(func.value, ast.Name) and func.value.id == "cmds":
                return True
    return False


def extract_string_arg(node: ast.AST, index: int = 0) -> Optional[str]:
    """Extract a string argument from a call node.

    Args:
        node: Call AST node.
        index: Argument index.

    Returns:
        The string value if found, None otherwise.
    """
    if not isinstance(node, ast.Call):
        return None
    if index >= len(node.args):
        return None
    arg = node.args[index]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def extract_kwarg(node: ast.Call, kwarg_name: str) -> Optional[ast.AST]:
    """Extract a keyword argument from a call node.

    Args:
        node: Call AST node.
        kwarg_name: Name of the keyword argument.

    Returns:
        The AST node for the value if found, None otherwise.
    """
    for kw in node.keywords:
        if kw.arg == kwarg_name:
            return kw.value
    return None


def extract_kwarg_value(node: ast.Call, kwarg_name: str) -> Optional[str]:
    """Extract a keyword argument value as a string.

    Args:
        node: Call AST node.
        kwarg_name: Name of the keyword argument.

    Returns:
        The string representation of the value if found.
    """
    kw_node = extract_kwarg(node, kwarg_name)
    if kw_node is None:
        return None
    return ast.unparse(kw_node)


def parse_attr_path(attr_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse a 'node.attribute' path string.

    Args:
        attr_path: Attribute path like 'pCube1.translateX'.

    Returns:
        Tuple of (node_name, attr_name) or (None, None) if invalid.
    """
    if "." not in attr_path:
        return None, None
    parts = attr_path.split(".", 1)
    return parts[0], parts[1]


def extract_attr_path_from_arg(arg: ast.AST) -> Tuple[Optional[str], Optional[str]]:
    """Extract node and attribute from a string argument or f-string.

    Handles:
    - 'nodeName.attrName'
    - f'{var}.attrName'
    - f'{var}.{attr}'

    Args:
        arg: AST node for the argument.

    Returns:
        Tuple of (node_expr, attr_name) or (None, None).
    """
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return parse_attr_path(arg.value)

    if isinstance(arg, ast.JoinedStr):
        # f-string: try to extract pattern
        parts = []
        for value in arg.values:
            if isinstance(value, ast.Constant):
                parts.append(("str", value.value))
            elif isinstance(value, ast.FormattedValue):
                parts.append(("expr", ast.unparse(value.value)))

        # Common pattern: f'{node}.attr'
        if len(parts) == 2:
            if parts[0][0] == "expr" and parts[1][0] == "str":
                attr_part = parts[1][1]
                if attr_part.startswith("."):
                    return parts[0][1], attr_part[1:]

        # Pattern: f'{node}.{attr}'
        if len(parts) == 3:
            if (parts[0][0] == "expr" and parts[1][0] == "str" and
                    parts[1][1] == "." and parts[2][0] == "expr"):
                return parts[0][1], parts[2][1]

    return None, None


# =============================================================================
# Node Creation Rules
# =============================================================================


class CreateNodeToTransformRule(ReverseConversionRule):
    """Convert cmds.createNode('transform', ...) to Transform.create(...)."""

    name = "createnode_to_transform"
    category = "node_creation"
    description = "Convert cmds.createNode('transform') to Transform.create()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.createNode('transform', ...) calls."""
        if not is_cmds_call(node, "createNode"):
            return False
        node_type = extract_string_arg(node, 0)
        return node_type == "transform"

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to Transform.create(...)."""
        call_node = node

        kwargs_parts = []
        for kw in call_node.keywords:
            if kw.arg is not None:
                kwargs_parts.append(f"{kw.arg}={ast.unparse(kw.value)}")

        converted = f"Transform.create({', '.join(kwargs_parts)})" if kwargs_parts else "Transform.create()"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class JointToJointCreateRule(ReverseConversionRule):
    """Convert cmds.joint(...) to Joint.create(...)."""

    name = "joint_to_joint_create"
    category = "node_creation"
    description = "Convert cmds.joint() to Joint.create()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.joint(...) calls."""
        return is_cmds_call(node, "joint")

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to Joint.create(...)."""
        call_node = node

        kwargs_parts = []
        for kw in call_node.keywords:
            if kw.arg is not None:
                kwargs_parts.append(f"{kw.arg}={ast.unparse(kw.value)}")

        converted = f"Joint.create({', '.join(kwargs_parts)})" if kwargs_parts else "Joint.create()"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class PolySphereToMeshCreateRule(ReverseConversionRule):
    """Convert cmds.polySphere(...) to Mesh.create('polySphere', ...)."""

    name = "polysphere_to_mesh_create"
    category = "node_creation"
    description = "Convert cmds.polySphere() to Mesh.create('polySphere')"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.polySphere(...) calls."""
        return is_cmds_call(node, "polySphere")

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to Mesh.create('polySphere', ...)."""
        call_node = node

        kwargs_parts = []
        for kw in call_node.keywords:
            if kw.arg is not None:
                kwargs_parts.append(f"{kw.arg}={ast.unparse(kw.value)}")

        converted = f"Mesh.create('polySphere', {', '.join(kwargs_parts)})" if kwargs_parts else "Mesh.create('polySphere')"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class PolyCubeToMeshCreateRule(ReverseConversionRule):
    """Convert cmds.polyCube(...) to Mesh.create('polyCube', ...)."""

    name = "polycube_to_mesh_create"
    category = "node_creation"
    description = "Convert cmds.polyCube() to Mesh.create('polyCube')"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.polyCube(...) calls."""
        return is_cmds_call(node, "polyCube")

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to Mesh.create('polyCube', ...)."""
        call_node = node

        kwargs_parts = []
        for kw in call_node.keywords:
            if kw.arg is not None:
                kwargs_parts.append(f"{kw.arg}={ast.unparse(kw.value)}")

        converted = f"Mesh.create('polyCube', {', '.join(kwargs_parts)})" if kwargs_parts else "Mesh.create('polyCube')"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class PolyPlaneToMeshCreateRule(ReverseConversionRule):
    """Convert cmds.polyPlane(...) to Mesh.create('polyPlane', ...)."""

    name = "polyplane_to_mesh_create"
    category = "node_creation"
    description = "Convert cmds.polyPlane() to Mesh.create('polyPlane')"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.polyPlane(...) calls."""
        return is_cmds_call(node, "polyPlane")

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to Mesh.create('polyPlane', ...)."""
        call_node = node

        kwargs_parts = []
        for kw in call_node.keywords:
            if kw.arg is not None:
                kwargs_parts.append(f"{kw.arg}={ast.unparse(kw.value)}")

        converted = f"Mesh.create('polyPlane', {', '.join(kwargs_parts)})" if kwargs_parts else "Mesh.create('polyPlane')"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class PolyCylinderToMeshCreateRule(ReverseConversionRule):
    """Convert cmds.polyCylinder(...) to Mesh.create('polyCylinder', ...)."""

    name = "polycylinder_to_mesh_create"
    category = "node_creation"
    description = "Convert cmds.polyCylinder() to Mesh.create('polyCylinder')"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.polyCylinder(...) calls."""
        return is_cmds_call(node, "polyCylinder")

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to Mesh.create('polyCylinder', ...)."""
        call_node = node

        kwargs_parts = []
        for kw in call_node.keywords:
            if kw.arg is not None:
                kwargs_parts.append(f"{kw.arg}={ast.unparse(kw.value)}")

        converted = f"Mesh.create('polyCylinder', {', '.join(kwargs_parts)})" if kwargs_parts else "Mesh.create('polyCylinder')"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class CurveToCurveCreateRule(ReverseConversionRule):
    """Convert cmds.curve(...) to Curve.create(...)."""

    name = "curve_to_curve_create"
    category = "node_creation"
    description = "Convert cmds.curve() to Curve.create()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.curve(...) calls."""
        return is_cmds_call(node, "curve")

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to Curve.create(...)."""
        call_node = node

        # Pass through all args and kwargs
        args_parts = [ast.unparse(arg) for arg in call_node.args]
        kwargs_parts = []
        for kw in call_node.keywords:
            if kw.arg is not None:
                kwargs_parts.append(f"{kw.arg}={ast.unparse(kw.value)}")

        all_parts = args_parts + kwargs_parts
        if all_parts:
            converted = f"Curve.create({', '.join(all_parts)})"
        else:
            converted = "Curve.create()"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class SpaceLocatorToLocatorCreateRule(ReverseConversionRule):
    """Convert cmds.spaceLocator(...) to Locator.create(...)."""

    name = "spacelocator_to_locator_create"
    category = "node_creation"
    description = "Convert cmds.spaceLocator() to Locator.create()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.spaceLocator(...) calls."""
        return is_cmds_call(node, "spaceLocator")

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to Locator.create(...)."""
        call_node = node

        kwargs_parts = []
        for kw in call_node.keywords:
            if kw.arg is not None:
                kwargs_parts.append(f"{kw.arg}={ast.unparse(kw.value)}")

        converted = f"Locator.create({', '.join(kwargs_parts)})" if kwargs_parts else "Locator.create()"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


# =============================================================================
# Attribute Access Rules
# =============================================================================


class SetAttrToPlugSetRule(ReverseConversionRule):
    """Convert cmds.setAttr('node.attr', value) to node['attr'].set(value)."""

    name = "setattr_to_plug_set"
    category = "attribute_access"
    description = "Convert cmds.setAttr() to Plug.set()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.setAttr(...) calls without lock/keyable flags."""
        if not is_cmds_call(node, "setAttr"):
            return False

        # Skip if this is a lock/unlock operation
        call_node = node
        for kw in call_node.keywords:
            if kw.arg in ("lock", "keyable", "channelBox"):
                return False

        return True

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to node['attr'].set(value)."""
        call_node = node

        if not call_node.args:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code="# ERROR: setAttr with no arguments",
            )

        attr_arg = call_node.args[0]
        node_expr, attr_name = extract_attr_path_from_arg(attr_arg)

        if node_expr is None:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code=ast.unparse(node),
                notes="Could not parse attribute path",
            )

        # Substitute node_expr if we know a variable for this node name
        var_name = context.get_node_variable(node_expr)
        node_expr = var_name or node_expr

        value_args = [ast.unparse(arg) for arg in call_node.args[1:]]

        # Handle type kwarg specially
        type_arg = extract_kwarg_value(call_node, "type")
        other_kwargs = []
        for kw in call_node.keywords:
            if kw.arg not in ("type",):
                if kw.arg is not None:
                    other_kwargs.append(f"{kw.arg}={ast.unparse(kw.value)}")

        # Build the set() call
        all_args = value_args + other_kwargs
        if type_arg:
            all_args.append(f"type={type_arg}")

        args_str = ", ".join(all_args)
        converted = f"{node_expr}['{attr_name}'].set({args_str})"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class SetAttrLockToPlugLockRule(ReverseConversionRule):
    """Convert cmds.setAttr('node.attr', lock=True) to node['attr'].lock()."""

    name = "setattr_lock_to_plug_lock"
    category = "attribute_access"
    description = "Convert cmds.setAttr(lock=True) to Plug.lock()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.setAttr(..., lock=True/False) calls."""
        if not is_cmds_call(node, "setAttr"):
            return False

        call_node = node
        lock_kw = extract_kwarg(call_node, "lock")
        return lock_kw is not None

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to node['attr'].lock() or unlock()."""
        call_node = node

        attr_arg = call_node.args[0] if call_node.args else None
        if attr_arg is None:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code="# ERROR: setAttr with no arguments",
            )

        node_expr, attr_name = extract_attr_path_from_arg(attr_arg)

        if node_expr is None:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code=ast.unparse(node),
                notes="Could not parse attribute path",
            )

        var_name = context.get_node_variable(node_expr)
        node_expr = var_name or node_expr

        lock_value = extract_kwarg(call_node, "lock")
        is_lock = True
        if isinstance(lock_value, ast.Constant):
            is_lock = bool(lock_value.value)
        elif isinstance(lock_value, ast.NameConstant):
            is_lock = bool(lock_value.value)

        method = "lock" if is_lock else "unlock"
        converted = f"{node_expr}['{attr_name}'].{method}()"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class GetAttrToPlugGetRule(ReverseConversionRule):
    """Convert cmds.getAttr('node.attr') to node['attr'].get()."""

    name = "getattr_to_plug_get"
    category = "attribute_access"
    description = "Convert cmds.getAttr() to Plug.get()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.getAttr(...) calls."""
        return is_cmds_call(node, "getAttr")

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to node['attr'].get()."""
        call_node = node

        if not call_node.args:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code="# ERROR: getAttr with no arguments",
            )

        attr_arg = call_node.args[0]
        node_expr, attr_name = extract_attr_path_from_arg(attr_arg)

        if node_expr is None:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code=ast.unparse(node),
                notes="Could not parse attribute path",
            )

        var_name = context.get_node_variable(node_expr)
        node_expr = var_name or node_expr

        kwargs_parts = []
        for kw in call_node.keywords:
            if kw.arg is not None:
                kwargs_parts.append(f"{kw.arg}={ast.unparse(kw.value)}")

        if kwargs_parts:
            converted = f"{node_expr}['{attr_name}'].get({', '.join(kwargs_parts)})"
        else:
            converted = f"{node_expr}['{attr_name}'].get()"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


# =============================================================================
# Connection Rules
# =============================================================================


class ConnectAttrToPlugConnectRule(ReverseConversionRule):
    """Convert cmds.connectAttr(src, dst) to src_plug.connect(dst_plug)."""

    name = "connectattr_to_plug_connect"
    category = "connections"
    description = "Convert cmds.connectAttr() to Plug.connect()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.connectAttr(...) calls."""
        return is_cmds_call(node, "connectAttr")

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to src['attr'].connect(dst['attr'])."""
        call_node = node

        if len(call_node.args) < 2:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code="# ERROR: connectAttr requires 2 arguments",
            )

        src_arg = call_node.args[0]
        dst_arg = call_node.args[1]

        src_node, src_attr = extract_attr_path_from_arg(src_arg)
        dst_node, dst_attr = extract_attr_path_from_arg(dst_arg)

        if src_node is None or dst_node is None:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code=ast.unparse(node),
                notes="Could not parse attribute paths",
            )

        src_var = context.get_node_variable(src_node)
        dst_var = context.get_node_variable(dst_node)
        src_expr = src_var or src_node
        dst_expr = dst_var or dst_node

        force_kw = extract_kwarg(call_node, "force")
        if force_kw is not None:
            force_val = ast.unparse(force_kw)
            converted = f"{src_expr}['{src_attr}'].connect({dst_expr}['{dst_attr}'], force={force_val})"
        else:
            converted = f"{src_expr}['{src_attr}'].connect({dst_expr}['{dst_attr}'])"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


# =============================================================================
# Node Operation Rules
# =============================================================================


class RenameToNodeRenameRule(ReverseConversionRule):
    """Convert cmds.rename(node, name) to node.rename(name)."""

    name = "rename_to_node_rename"
    category = "node_operations"
    description = "Convert cmds.rename() to Node.rename()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.rename(...) calls."""
        return is_cmds_call(node, "rename")

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to node.rename(name)."""
        call_node = node

        if len(call_node.args) < 2:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code="# ERROR: rename requires node and name",
            )

        node_expr = ast.unparse(call_node.args[0])
        new_name = ast.unparse(call_node.args[1])

        converted = f"{node_expr}.rename({new_name})"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class DeleteToNodeDeleteRule(ReverseConversionRule):
    """Convert cmds.delete(node) to node.delete()."""

    name = "delete_to_node_delete"
    category = "node_operations"
    description = "Convert cmds.delete() to Node.delete()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.delete(...) calls with single node argument."""
        if not is_cmds_call(node, "delete"):
            return False
        # Only handle single-node delete for now
        call_node = node
        return len(call_node.args) == 1

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to node.delete()."""
        call_node = node
        node_expr = ast.unparse(call_node.args[0])

        converted = f"{node_expr}.delete()"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class DuplicateToNodeDuplicateRule(ReverseConversionRule):
    """Convert cmds.duplicate(node) to node.duplicate()."""

    name = "duplicate_to_node_duplicate"
    category = "node_operations"
    description = "Convert cmds.duplicate() to Node.duplicate()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.duplicate(...) calls."""
        return is_cmds_call(node, "duplicate")

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to node.duplicate()."""
        call_node = node

        if not call_node.args:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code="# ERROR: duplicate requires node argument",
            )

        node_expr = ast.unparse(call_node.args[0])

        # Pass through kwargs
        kwargs_parts = []
        for kw in call_node.keywords:
            if kw.arg is not None:
                kwargs_parts.append(f"{kw.arg}={ast.unparse(kw.value)}")

        if kwargs_parts:
            converted = f"{node_expr}.duplicate({', '.join(kwargs_parts)})"
        else:
            converted = f"{node_expr}.duplicate()"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class SelectToNodeSelectRule(ReverseConversionRule):
    """Convert cmds.select(node, replace=True) to node.select()."""

    name = "select_to_node_select"
    category = "node_operations"
    description = "Convert cmds.select() to Node.select()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.select(...) calls with single node and replace=True."""
        if not is_cmds_call(node, "select"):
            return False
        call_node = node
        # Only handle single-node select with replace
        if len(call_node.args) != 1:
            return False
        replace_kw = extract_kwarg(call_node, "replace")
        if replace_kw is None:
            return False
        if isinstance(replace_kw, ast.Constant):
            return replace_kw.value is True
        return False

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to node.select()."""
        call_node = node
        node_expr = ast.unparse(call_node.args[0])

        converted = f"{node_expr}.select()"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class AddAttrToNodeAddAttrRule(ReverseConversionRule):
    """Convert cmds.addAttr(node, ...) to node.add_attr(...)."""

    name = "addattr_to_node_addattr"
    category = "node_operations"
    description = "Convert cmds.addAttr() to Node.add_attr()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.addAttr(...) calls."""
        return is_cmds_call(node, "addAttr")

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to node.add_attr(name, ...)."""
        call_node = node

        if not call_node.args:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code="# ERROR: addAttr requires node argument",
            )

        node_expr = ast.unparse(call_node.args[0])

        # Extract longName as the attr name
        long_name = extract_kwarg_value(call_node, "longName")
        short_name = extract_kwarg_value(call_node, "shortName")
        attr_name = long_name or short_name

        if not attr_name:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code=ast.unparse(node),
                notes="Could not determine attribute name",
            )

        # Other kwargs (excluding longName/shortName)
        other_kwargs = []
        for kw in call_node.keywords:
            if kw.arg not in ("longName", "shortName") and kw.arg is not None:
                other_kwargs.append(f"{kw.arg}={ast.unparse(kw.value)}")

        if other_kwargs:
            converted = f"{node_expr}.add_attr({attr_name}, {', '.join(other_kwargs)})"
        else:
            converted = f"{node_expr}.add_attr({attr_name})"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


# =============================================================================
# Transform Rules
# =============================================================================


class MakeIdentityToFreezeRule(ReverseConversionRule):
    """Convert cmds.makeIdentity(node, apply=True, ...) to node.freeze(...)."""

    name = "makeidentity_to_freeze"
    category = "transform_operations"
    description = "Convert cmds.makeIdentity() to Transform.freeze()"

    def matches(self, node: ast.AST, context: ReverseRuleContext) -> bool:
        """Match cmds.makeIdentity(..., apply=True) calls."""
        if not is_cmds_call(node, "makeIdentity"):
            return False
        call_node = node
        apply_kw = extract_kwarg(call_node, "apply")
        if apply_kw is None:
            return False
        if isinstance(apply_kw, ast.Constant):
            return apply_kw.value is True
        return False

    def convert(self, node: ast.AST, context: ReverseRuleContext) -> ReverseRuleMatch:
        """Convert to node.freeze(...)."""
        call_node = node

        if not call_node.args:
            return ReverseRuleMatch(
                rule_name=self.name,
                original_node=node,
                converted_code="# ERROR: makeIdentity requires node argument",
            )

        node_expr = ast.unparse(call_node.args[0])
        var_name = context.get_node_variable(node_expr)
        node_expr = var_name or node_expr

        # Extract translate, rotate, scale kwargs
        kwargs_parts = []
        for kw_name in ("translate", "rotate", "scale"):
            kw_val = extract_kwarg_value(call_node, kw_name)
            if kw_val is not None:
                kwargs_parts.append(f"{kw_name}={kw_val}")

        if kwargs_parts:
            converted = f"{node_expr}.freeze({', '.join(kwargs_parts)})"
        else:
            converted = f"{node_expr}.freeze()"

        return ReverseRuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


# =============================================================================
# Unsupported Pattern Detection
# =============================================================================

# List of cmds functions that are explicitly unsupported
UNSUPPORTED_CMDS = {
    "ls": "Selection/query operation - context dependent",
    "listRelatives": "Query operation - requires scene state",
    "listConnections": "Query operation - requires scene state",
    "listAttr": "Query operation - requires scene state",
    "listHistory": "Query operation - requires scene state",
    "xform": "Complex query/set operation - partially supported",
    "parent": "Hierarchy operation - requires careful handling",
    "setParent": "Hierarchy operation - requires careful handling",
    "polyEvaluate": "Query operation - requires scene state",
    "pointPosition": "Query operation - requires scene state",
}


def get_unsupported_cmds_reason(func_name: str) -> Optional[str]:
    """Get the reason why a cmds function is unsupported.

    Args:
        func_name: The cmds function name.

    Returns:
        The reason string if unsupported, None otherwise.
    """
    return UNSUPPORTED_CMDS.get(func_name)


# =============================================================================
# Rule Registry
# =============================================================================


def get_default_reverse_rules() -> List[ReverseConversionRule]:
    """Return the default set of reverse conversion rules.

    Returns:
        List of ReverseConversionRule instances in priority order.
    """
    return [
        # Node creation
        CreateNodeToTransformRule(),
        JointToJointCreateRule(),
        PolySphereToMeshCreateRule(),
        PolyCubeToMeshCreateRule(),
        PolyPlaneToMeshCreateRule(),
        PolyCylinderToMeshCreateRule(),
        CurveToCurveCreateRule(),
        SpaceLocatorToLocatorCreateRule(),
        # Attribute access (lock rule must come before general setattr)
        SetAttrLockToPlugLockRule(),
        SetAttrToPlugSetRule(),
        GetAttrToPlugGetRule(),
        # Connections
        ConnectAttrToPlugConnectRule(),
        # Node operations
        RenameToNodeRenameRule(),
        DeleteToNodeDeleteRule(),
        DuplicateToNodeDuplicateRule(),
        SelectToNodeSelectRule(),
        AddAttrToNodeAddAttrRule(),
        # Transform operations
        MakeIdentityToFreezeRule(),
    ]
