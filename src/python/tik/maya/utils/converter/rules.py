"""
Conversion rules for tik.maya → maya.cmds transformation.

Rules define how specific tik.maya patterns should be expanded
into their maya.cmds equivalents. Each rule is a deterministic,
testable unit of transformation.

Rule categories:
1. Language-level expressions (always convertible)
2. Blessed helpers (explicitly registered, opt-in)
"""

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class RuleMatch:
    """Result of a successful rule match."""

    rule_name: str
    original_node: ast.AST
    converted_code: str
    confidence: float = 1.0
    notes: Optional[str] = None


@dataclass
class RuleContext:
    """Context information available during rule matching.

    Provides access to tracked variable names and their types,
    allowing rules to make informed decisions about conversions.
    """

    variable_types: Dict[str, str]  # Maps variable names to tik types
    source_lines: List[str]
    imports: Dict[str, str]  # Maps import aliases to full paths

    def get_variable_type(self, name: str) -> Optional[str]:
        """Get the tracked type for a variable name."""
        return self.variable_types.get(name)


class ConversionRule(ABC):
    """Base class for all conversion rules.

    A rule defines:
    - A pattern to match in the AST
    - A transformation to apply when matched
    - Metadata about the rule (name, category, etc.)
    """

    name: str = "unnamed_rule"
    category: str = "general"
    description: str = ""

    @abstractmethod
    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Check if this rule applies to the given AST node.

        Args:
            node: AST node to check.
            context: Context with variable type information.

        Returns:
            True if this rule can convert the node.
        """

    @abstractmethod
    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert the matched AST node to maya.cmds code.

        Args:
            node: AST node that matched this rule.
            context: Context with variable type information.

        Returns:
            RuleMatch with the converted code.
        """


# =============================================================================
# Node Creation Rules
# =============================================================================


class TransformCreateRule(ConversionRule):
    """Convert Transform.create() to cmds.createNode('transform', ...)."""

    name = "transform_create"
    category = "node_creation"
    description = "Convert Transform.create() to cmds.createNode"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match Transform.create(...) calls."""
        if not isinstance(node, ast.Call):
            return False

        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr == "create" and isinstance(func.value, ast.Name):
                return func.value.id == "Transform"
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.createNode('transform', ...)."""
        call_node = node  # type: ast.Call
        kwargs = self._extract_kwargs(call_node)

        args_str = self._format_kwargs(kwargs)
        if args_str:
            converted = f"cmds.createNode('transform', {args_str})"
        else:
            converted = "cmds.createNode('transform')"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_kwargs(self, call_node: ast.Call) -> Dict[str, str]:
        """Extract keyword arguments from a call node."""
        kwargs = {}
        for keyword in call_node.keywords:
            if keyword.arg is not None:
                kwargs[keyword.arg] = ast.unparse(keyword.value)
        return kwargs

    def _format_kwargs(self, kwargs: Dict[str, str]) -> str:
        """Format kwargs dict as Python argument string."""
        if not kwargs:
            return ""
        return ", ".join(f"{key}={value}" for key, value in kwargs.items())


class JointCreateRule(ConversionRule):
    """Convert Joint.create() to cmds.joint(...)."""

    name = "joint_create"
    category = "node_creation"
    description = "Convert Joint.create() to cmds.joint"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match Joint.create(...) calls."""
        if not isinstance(node, ast.Call):
            return False

        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr == "create" and isinstance(func.value, ast.Name):
                return func.value.id == "Joint"
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.joint(...)."""
        call_node = node  # type: ast.Call
        kwargs = self._extract_kwargs(call_node)

        args_str = self._format_kwargs(kwargs)
        if args_str:
            converted = f"cmds.joint({args_str})"
        else:
            converted = "cmds.joint()"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_kwargs(self, call_node: ast.Call) -> Dict[str, str]:
        """Extract keyword arguments from a call node."""
        kwargs = {}
        for keyword in call_node.keywords:
            if keyword.arg is not None:
                kwargs[keyword.arg] = ast.unparse(keyword.value)
        return kwargs

    def _format_kwargs(self, kwargs: Dict[str, str]) -> str:
        """Format kwargs dict as Python argument string."""
        if not kwargs:
            return ""
        return ", ".join(f"{key}={value}" for key, value in kwargs.items())


class MeshCreateRule(ConversionRule):
    """Convert Mesh.create() to cmds.poly* or cmds.createNode('mesh', ...)."""

    name = "mesh_create"
    category = "node_creation"
    description = "Convert Mesh.create() to cmds.poly* commands"

    POLY_PRIMITIVES = {
        "polyCube",
        "polySphere",
        "polyPlane",
        "polyCylinder",
        "polyCone",
        "polyTorus",
    }

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match Mesh.create(...) calls."""
        if not isinstance(node, ast.Call):
            return False

        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr == "create" and isinstance(func.value, ast.Name):
                return func.value.id == "Mesh"
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to appropriate cmds call."""
        call_node = node  # type: ast.Call

        # First positional arg is the command name
        cmd_name = None
        if call_node.args:
            first_arg = call_node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                cmd_name = first_arg.value

        kwargs = self._extract_kwargs(call_node)
        args_str = self._format_kwargs(kwargs)

        if cmd_name and cmd_name in self.POLY_PRIMITIVES:
            if args_str:
                converted = f"cmds.{cmd_name}({args_str})[0]"
            else:
                converted = f"cmds.{cmd_name}()[0]"
        else:
            if args_str:
                converted = f"cmds.createNode('mesh', {args_str})"
            else:
                converted = "cmds.createNode('mesh')"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_kwargs(self, call_node: ast.Call) -> Dict[str, str]:
        """Extract keyword arguments from a call node."""
        kwargs = {}
        for keyword in call_node.keywords:
            if keyword.arg is not None:
                kwargs[keyword.arg] = ast.unparse(keyword.value)
        return kwargs

    def _format_kwargs(self, kwargs: Dict[str, str]) -> str:
        """Format kwargs dict as Python argument string."""
        if not kwargs:
            return ""
        return ", ".join(f"{key}={value}" for key, value in kwargs.items())


class CurveCreateRule(ConversionRule):
    """Convert Curve.create() to cmds.curve(...)."""

    name = "curve_create"
    category = "node_creation"
    description = "Convert Curve.create() to cmds.curve"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match Curve.create(...) calls."""
        if not isinstance(node, ast.Call):
            return False

        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr == "create" and isinstance(func.value, ast.Name):
                return func.value.id == "Curve"
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.curve(...)."""
        call_node = node  # type: ast.Call

        args = [ast.unparse(arg) for arg in call_node.args]
        kwargs = self._extract_kwargs(call_node)

        all_args = args + [f"{key}={value}" for key, value in kwargs.items()]
        args_str = ", ".join(all_args)

        if args_str:
            converted = f"cmds.curve({args_str})"
        else:
            converted = "cmds.curve()"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_kwargs(self, call_node: ast.Call) -> Dict[str, str]:
        """Extract keyword arguments from a call node."""
        kwargs = {}
        for keyword in call_node.keywords:
            if keyword.arg is not None:
                kwargs[keyword.arg] = ast.unparse(keyword.value)
        return kwargs


class LocatorCreateRule(ConversionRule):
    """Convert Locator.create() to cmds.spaceLocator(...)."""

    name = "locator_create"
    category = "node_creation"
    description = "Convert Locator.create() to cmds.spaceLocator"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match Locator.create(...) calls."""
        if not isinstance(node, ast.Call):
            return False

        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr == "create" and isinstance(func.value, ast.Name):
                return func.value.id == "Locator"
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.spaceLocator(...)."""
        call_node = node  # type: ast.Call
        kwargs = self._extract_kwargs(call_node)

        args_str = self._format_kwargs(kwargs)
        if args_str:
            converted = f"cmds.spaceLocator({args_str})[0]"
        else:
            converted = "cmds.spaceLocator()[0]"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_kwargs(self, call_node: ast.Call) -> Dict[str, str]:
        """Extract keyword arguments from a call node."""
        kwargs = {}
        for keyword in call_node.keywords:
            if keyword.arg is not None:
                kwargs[keyword.arg] = ast.unparse(keyword.value)
        return kwargs

    def _format_kwargs(self, kwargs: Dict[str, str]) -> str:
        """Format kwargs dict as Python argument string."""
        if not kwargs:
            return ""
        return ", ".join(f"{key}={value}" for key, value in kwargs.items())


# =============================================================================
# Attribute Access Rules
# =============================================================================


class PlugGetRule(ConversionRule):
    """Convert node["attr"].get() to cmds.getAttr('node.attr')."""

    name = "plug_get"
    category = "attribute_access"
    description = "Convert Plug.get() to cmds.getAttr"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match node["attr"].get() or node["attr"].value patterns."""
        if isinstance(node, ast.Call):
            # node["attr"].get()
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "get":
                if isinstance(func.value, ast.Subscript):
                    return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.getAttr(...)."""
        call_node = node  # type: ast.Call
        subscript = call_node.func.value  # type: ast.Subscript

        node_expr = ast.unparse(subscript.value)
        attr_name = self._extract_attr_name(subscript.slice)

        # Handle kwargs passed to get()
        kwargs = {}
        for keyword in call_node.keywords:
            if keyword.arg is not None:
                kwargs[keyword.arg] = ast.unparse(keyword.value)

        kwargs_str = ", ".join(f"{key}={value}" for key, value in kwargs.items())

        if kwargs_str:
            converted = f"cmds.getAttr(f'{{{node_expr}}}.{attr_name}', {kwargs_str})"
        else:
            converted = f"cmds.getAttr(f'{{{node_expr}}}.{attr_name}')"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_attr_name(self, slice_node: ast.AST) -> str:
        """Extract attribute name from subscript slice."""
        if isinstance(slice_node, ast.Constant):
            return str(slice_node.value)
        return ast.unparse(slice_node)


class PlugSetRule(ConversionRule):
    """Convert node["attr"].set(value) to cmds.setAttr('node.attr', value)."""

    name = "plug_set"
    category = "attribute_access"
    description = "Convert Plug.set() to cmds.setAttr"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match node["attr"].set(value) patterns."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "set":
                if isinstance(func.value, ast.Subscript):
                    return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.setAttr(...)."""
        call_node = node  # type: ast.Call
        subscript = call_node.func.value  # type: ast.Subscript

        node_expr = ast.unparse(subscript.value)
        attr_name = self._extract_attr_name(subscript.slice)

        # Get the value argument
        value_args = [ast.unparse(arg) for arg in call_node.args]

        # Handle kwargs
        kwargs = {}
        for keyword in call_node.keywords:
            if keyword.arg is not None:
                kwargs[keyword.arg] = ast.unparse(keyword.value)

        all_args = value_args + [f"{key}={value}" for key, value in kwargs.items()]
        args_str = ", ".join(all_args)

        if args_str:
            converted = f"cmds.setAttr(f'{{{node_expr}}}.{attr_name}', {args_str})"
        else:
            converted = f"cmds.setAttr(f'{{{node_expr}}}.{attr_name}')"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_attr_name(self, slice_node: ast.AST) -> str:
        """Extract attribute name from subscript slice."""
        if isinstance(slice_node, ast.Constant):
            return str(slice_node.value)
        return ast.unparse(slice_node)


class PlugValueGetRule(ConversionRule):
    """Convert node["attr"].value (read) to cmds.getAttr('node.attr')."""

    name = "plug_value_get"
    category = "attribute_access"
    description = "Convert Plug.value property read to cmds.getAttr"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match node["attr"].value read patterns."""
        if isinstance(node, ast.Attribute) and node.attr == "value":
            if isinstance(node.value, ast.Subscript):
                return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.getAttr(...)."""
        attr_node = node  # type: ast.Attribute
        subscript = attr_node.value  # type: ast.Subscript

        node_expr = ast.unparse(subscript.value)
        attr_name = self._extract_attr_name(subscript.slice)

        converted = f"cmds.getAttr(f'{{{node_expr}}}.{attr_name}')"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_attr_name(self, slice_node: ast.AST) -> str:
        """Extract attribute name from subscript slice."""
        if isinstance(slice_node, ast.Constant):
            return str(slice_node.value)
        return ast.unparse(slice_node)


class PlugValueSetRule(ConversionRule):
    """Convert node["attr"].value = x to cmds.setAttr('node.attr', x)."""

    name = "plug_value_set"
    category = "attribute_access"
    description = "Convert Plug.value property assignment to cmds.setAttr"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match node["attr"].value = x assignment patterns.

        Note: This matches Assign nodes where target is attr.value on subscript.
        """
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Attribute) and target.attr == "value":
                    if isinstance(target.value, ast.Subscript):
                        return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.setAttr(...)."""
        assign_node = node  # type: ast.Assign
        target = assign_node.targets[0]  # type: ast.Attribute
        subscript = target.value  # type: ast.Subscript

        node_expr = ast.unparse(subscript.value)
        attr_name = self._extract_attr_name(subscript.slice)
        value_expr = ast.unparse(assign_node.value)

        converted = f"cmds.setAttr(f'{{{node_expr}}}.{attr_name}', {value_expr})"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_attr_name(self, slice_node: ast.AST) -> str:
        """Extract attribute name from subscript slice."""
        if isinstance(slice_node, ast.Constant):
            return str(slice_node.value)
        return ast.unparse(slice_node)


# =============================================================================
# Connection Rules
# =============================================================================


class PlugConnectRule(ConversionRule):
    """Convert plug.connect(other) to cmds.connectAttr(src, dst)."""

    name = "plug_connect"
    category = "connections"
    description = "Convert Plug.connect() to cmds.connectAttr"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match plug.connect(other) patterns."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "connect":
                # Check if it's on a subscript (plug access)
                if isinstance(func.value, ast.Subscript):
                    return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.connectAttr(...)."""
        call_node = node  # type: ast.Call
        src_subscript = call_node.func.value  # type: ast.Subscript

        src_node = ast.unparse(src_subscript.value)
        src_attr = self._extract_attr_name(src_subscript.slice)

        # Get destination from first argument
        if call_node.args:
            dst_arg = call_node.args[0]
            if isinstance(dst_arg, ast.Subscript):
                dst_node = ast.unparse(dst_arg.value)
                dst_attr = self._extract_attr_name(dst_arg.slice)
                dst_expr = f"f'{{{dst_node}}}.{dst_attr}'"
            else:
                # Might be a Plug variable
                dst_expr = f"{ast.unparse(dst_arg)}.path"
        else:
            dst_expr = "# ERROR: missing destination"

        # Handle force kwarg
        force = "True"  # default
        for keyword in call_node.keywords:
            if keyword.arg == "force":
                force = ast.unparse(keyword.value)

        converted = (
            f"cmds.connectAttr(f'{{{src_node}}}.{src_attr}', {dst_expr}, force={force})"
        )

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_attr_name(self, slice_node: ast.AST) -> str:
        """Extract attribute name from subscript slice."""
        if isinstance(slice_node, ast.Constant):
            return str(slice_node.value)
        return ast.unparse(slice_node)


class PlugRshiftRule(ConversionRule):
    """Convert src_plug >> dst_plug to cmds.connectAttr(...)."""

    name = "plug_rshift_connect"
    category = "connections"
    description = "Convert >> operator connection to cmds.connectAttr"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match plug >> other_plug patterns."""
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.RShift):
            # Check if operands are subscripts (plug access)
            return isinstance(node.left, ast.Subscript)
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.connectAttr(...)."""
        binop = node  # type: ast.BinOp

        src_subscript = binop.left  # type: ast.Subscript
        src_node = ast.unparse(src_subscript.value)
        src_attr = self._extract_attr_name(src_subscript.slice)

        dst = binop.right
        if isinstance(dst, ast.Subscript):
            dst_node = ast.unparse(dst.value)
            dst_attr = self._extract_attr_name(dst.slice)
            dst_expr = f"f'{{{dst_node}}}.{dst_attr}'"
        else:
            dst_expr = f"{ast.unparse(dst)}.path"

        converted = (
            f"cmds.connectAttr(f'{{{src_node}}}.{src_attr}', {dst_expr}, force=True)"
        )

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_attr_name(self, slice_node: ast.AST) -> str:
        """Extract attribute name from subscript slice."""
        if isinstance(slice_node, ast.Constant):
            return str(slice_node.value)
        return ast.unparse(slice_node)


# =============================================================================
# Property Assignment Rules
# =============================================================================


class TransformPropertySetRule(ConversionRule):
    """Convert transform property assignment to cmds.setAttr."""

    name = "transform_property_set"
    category = "properties"
    description = "Convert transform property assignment to cmds.setAttr"

    # Maps tik property names to Maya attribute names
    PROPERTY_MAP = {
        "translate": "translate",
        "translate_x": "translateX",
        "translate_y": "translateY",
        "translate_z": "translateZ",
        "rotate": "rotate",
        "rotate_x": "rotateX",
        "rotate_y": "rotateY",
        "rotate_z": "rotateZ",
        "scale": "scale",
        "scale_x": "scaleX",
        "scale_y": "scaleY",
        "scale_z": "scaleZ",
        "visibility": "visibility",
        # Aliases
        "t": "translate",
        "tx": "translateX",
        "ty": "translateY",
        "tz": "translateZ",
        "r": "rotate",
        "rx": "rotateX",
        "ry": "rotateY",
        "rz": "rotateZ",
        "s": "scale",
        "sx": "scaleX",
        "sy": "scaleY",
        "sz": "scaleZ",
        "v": "visibility",
    }

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match node.property = value patterns for known properties."""
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Attribute):
                    return target.attr in self.PROPERTY_MAP
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.setAttr(...)."""
        assign_node = node  # type: ast.Assign
        target = assign_node.targets[0]  # type: ast.Attribute

        node_expr = ast.unparse(target.value)
        maya_attr = self.PROPERTY_MAP[target.attr]
        value_expr = ast.unparse(assign_node.value)

        # Compound attributes (translate, rotate, scale) need unpacking
        if maya_attr in ("translate", "rotate", "scale"):
            converted = f"cmds.setAttr(f'{{{node_expr}}}.{maya_attr}', *{value_expr})"
        else:
            converted = f"cmds.setAttr(f'{{{node_expr}}}.{maya_attr}', {value_expr})"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


# =============================================================================
# Node Method Rules
# =============================================================================


class NodeRenameRule(ConversionRule):
    """Convert node.rename(name) to cmds.rename(node, name)."""

    name = "node_rename"
    category = "node_methods"
    description = "Convert Node.rename() to cmds.rename"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match node.rename(...) patterns."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "rename":
                return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.rename(...)."""
        call_node = node  # type: ast.Call
        node_expr = ast.unparse(call_node.func.value)

        new_name = ast.unparse(call_node.args[0]) if call_node.args else "''"

        converted = f"cmds.rename({node_expr}, {new_name})"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class NodeDeleteRule(ConversionRule):
    """Convert node.delete() to cmds.delete(node)."""

    name = "node_delete"
    category = "node_methods"
    description = "Convert Node.delete() to cmds.delete"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match node.delete() patterns."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "delete":
                return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.delete(...)."""
        call_node = node  # type: ast.Call
        node_expr = ast.unparse(call_node.func.value)

        converted = f"cmds.delete({node_expr})"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class NodeDuplicateRule(ConversionRule):
    """Convert node.duplicate() to cmds.duplicate(node)."""

    name = "node_duplicate"
    category = "node_methods"
    description = "Convert Node.duplicate() to cmds.duplicate"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match node.duplicate() patterns."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "duplicate":
                return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.duplicate(...)."""
        call_node = node  # type: ast.Call
        node_expr = ast.unparse(call_node.func.value)

        kwargs = {}
        for keyword in call_node.keywords:
            if keyword.arg is not None:
                kwargs[keyword.arg] = ast.unparse(keyword.value)

        kwargs_str = ", ".join(f"{key}={value}" for key, value in kwargs.items())

        if kwargs_str:
            converted = f"cmds.duplicate({node_expr}, {kwargs_str})[0]"
        else:
            converted = f"cmds.duplicate({node_expr})[0]"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class DagNodeSelectRule(ConversionRule):
    """Convert node.select() to cmds.select(node, replace=True)."""

    name = "dagnode_select"
    category = "node_methods"
    description = "Convert DagNode.select() to cmds.select"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match node.select() patterns."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "select":
                return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.select(...)."""
        call_node = node  # type: ast.Call
        node_expr = ast.unparse(call_node.func.value)

        converted = f"cmds.select({node_expr}, replace=True)"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class PlugLockRule(ConversionRule):
    """Convert plug.lock() to cmds.setAttr(plug.path, lock=True)."""

    name = "plug_lock"
    category = "attribute_methods"
    description = "Convert Plug.lock() to cmds.setAttr with lock flag"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match node["attr"].lock() patterns."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "lock":
                if isinstance(func.value, ast.Subscript):
                    return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.setAttr(..., lock=True)."""
        call_node = node  # type: ast.Call
        subscript = call_node.func.value  # type: ast.Subscript

        node_expr = ast.unparse(subscript.value)
        attr_name = self._extract_attr_name(subscript.slice)

        converted = f"cmds.setAttr(f'{{{node_expr}}}.{attr_name}', lock=True)"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_attr_name(self, slice_node: ast.AST) -> str:
        """Extract attribute name from subscript slice."""
        if isinstance(slice_node, ast.Constant):
            return str(slice_node.value)
        return ast.unparse(slice_node)


class PlugUnlockRule(ConversionRule):
    """Convert plug.unlock() to cmds.setAttr(plug.path, lock=False)."""

    name = "plug_unlock"
    category = "attribute_methods"
    description = "Convert Plug.unlock() to cmds.setAttr with lock=False"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match node["attr"].unlock() patterns."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "unlock":
                if isinstance(func.value, ast.Subscript):
                    return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.setAttr(..., lock=False)."""
        call_node = node  # type: ast.Call
        subscript = call_node.func.value  # type: ast.Subscript

        node_expr = ast.unparse(subscript.value)
        attr_name = self._extract_attr_name(subscript.slice)

        converted = f"cmds.setAttr(f'{{{node_expr}}}.{attr_name}', lock=False)"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )

    def _extract_attr_name(self, slice_node: ast.AST) -> str:
        """Extract attribute name from subscript slice."""
        if isinstance(slice_node, ast.Constant):
            return str(slice_node.value)
        return ast.unparse(slice_node)


class TransformFreezeRule(ConversionRule):
    """Convert transform.freeze() to cmds.makeIdentity(...)."""

    name = "transform_freeze"
    category = "transform_methods"
    description = "Convert Transform.freeze() to cmds.makeIdentity"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match transform.freeze() patterns."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "freeze":
                return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.makeIdentity(...)."""
        call_node = node  # type: ast.Call
        node_expr = ast.unparse(call_node.func.value)

        # Extract kwargs with defaults
        translate = "True"
        rotate = "True"
        scale = "True"

        for keyword in call_node.keywords:
            if keyword.arg == "translate":
                translate = ast.unparse(keyword.value)
            elif keyword.arg == "rotate":
                rotate = ast.unparse(keyword.value)
            elif keyword.arg == "scale":
                scale = ast.unparse(keyword.value)

        converted = (
            f"cmds.makeIdentity({node_expr}, apply=True, "
            f"translate={translate}, rotate={rotate}, scale={scale})"
        )

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class NodeAddAttrRule(ConversionRule):
    """Convert node.add_attr(name, **kwargs) to cmds.addAttr(...)."""

    name = "node_add_attr"
    category = "node_methods"
    description = "Convert Node.add_attr() to cmds.addAttr"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match node.add_attr() patterns."""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "add_attr":
                return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert to cmds.addAttr(...)."""
        call_node = node  # type: ast.Call
        node_expr = ast.unparse(call_node.func.value)

        # First arg is attr name
        attr_name = ast.unparse(call_node.args[0]) if call_node.args else "''"

        kwargs = {}
        for keyword in call_node.keywords:
            if keyword.arg is not None:
                kwargs[keyword.arg] = ast.unparse(keyword.value)

        kwargs_str = ", ".join(f"{key}={value}" for key, value in kwargs.items())

        if kwargs_str:
            converted = f"cmds.addAttr({node_expr}, longName={attr_name}, {kwargs_str})"
        else:
            converted = f"cmds.addAttr({node_expr}, longName={attr_name})"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
        )


class ResolveRule(ConversionRule):
    """Convert resolve(name) to name (pass-through for string node names).

    Handles:
    - resolve('nodeName')
    - tm.resolve('nodeName')
    - tik.maya.resolve('nodeName')
    """

    name = "resolve_call"
    category = "utilities"
    description = "Convert resolve() to direct node name usage"

    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        """Match resolve(...) calls in various forms."""
        if isinstance(node, ast.Call):
            func = node.func
            # Direct call: resolve(...)
            if isinstance(func, ast.Name) and func.id == "resolve":
                return True
            # Attribute access: tm.resolve(...) or tik.maya.resolve(...)
            if isinstance(func, ast.Attribute) and func.attr == "resolve":
                return True
        return False

    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        """Convert resolve(name) to just name."""
        call_node = node  # type: ast.Call

        if call_node.args:
            converted = ast.unparse(call_node.args[0])
        else:
            converted = "# ERROR: resolve() called without arguments"

        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code=converted,
            notes="resolve() removed; in cmds code, use string node names directly",
        )


# =============================================================================
# Rule Registry
# =============================================================================


def get_default_rules() -> List[ConversionRule]:
    """Return the default set of conversion rules.

    Returns:
        List of ConversionRule instances in priority order.
    """
    return [
        # Node creation (high priority)
        TransformCreateRule(),
        JointCreateRule(),
        MeshCreateRule(),
        CurveCreateRule(),
        LocatorCreateRule(),
        # Attribute access
        PlugGetRule(),
        PlugSetRule(),
        PlugValueSetRule(),  # Must come before PlugValueGetRule
        PlugValueGetRule(),
        # Connections
        PlugConnectRule(),
        PlugRshiftRule(),
        # Properties
        TransformPropertySetRule(),
        # Node methods
        NodeRenameRule(),
        NodeDeleteRule(),
        NodeDuplicateRule(),
        DagNodeSelectRule(),
        NodeAddAttrRule(),
        # Attribute methods
        PlugLockRule(),
        PlugUnlockRule(),
        # Transform methods
        TransformFreezeRule(),
        # Utilities
        ResolveRule(),
    ]
