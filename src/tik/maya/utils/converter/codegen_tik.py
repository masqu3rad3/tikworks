"""
Code generation utilities for tik.maya output.

This module handles the generation of valid Python code that uses
tik.maya from converted maya.cmds AST representations.
"""

from typing import List, Optional


def generate_tik_import() -> str:
    """Generate the standard tik.maya import statement.

    Returns:
        Import statement string.
    """
    return "from tik.maya import Transform, Joint, Mesh, Curve, Locator, resolve"


def generate_tik_header_comment(
    original_info: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> str:
    """Generate a header comment for converted tik.maya code.

    Args:
        original_info: Information about the original source.
        warnings: List of warnings to include.

    Returns:
        Header comment string.
    """
    lines = [
        '"""',
        "Auto-generated tik.maya code.",
        "Converted from maya.cmds source.",
        "",
    ]

    if original_info:
        lines.append(f"Original: {original_info}")
        lines.append("")

    if warnings:
        lines.append("WARNINGS:")
        for warning in warnings:
            lines.append(f"  - {warning}")
        lines.append("")

    lines.append('"""')
    return "\n".join(lines)


def format_plug_set(
    node_expr: str,
    attr_name: str,
    value: str,
) -> str:
    """Format a Plug.set() call.

    Args:
        node_expr: Expression for the node.
        attr_name: Attribute name.
        value: Value expression.

    Returns:
        Formatted set() call.
    """
    return f"{node_expr}['{attr_name}'].set({value})"


def format_plug_get(
    node_expr: str,
    attr_name: str,
) -> str:
    """Format a Plug.get() call.

    Args:
        node_expr: Expression for the node.
        attr_name: Attribute name.

    Returns:
        Formatted get() call.
    """
    return f"{node_expr}['{attr_name}'].get()"


def format_plug_connect(
    src_node: str,
    src_attr: str,
    dst_node: str,
    dst_attr: str,
) -> str:
    """Format a Plug.connect() call.

    Args:
        src_node: Source node expression.
        src_attr: Source attribute name.
        dst_node: Destination node expression.
        dst_attr: Destination attribute name.

    Returns:
        Formatted connect() call.
    """
    return f"{src_node}['{src_attr}'].connect({dst_node}['{dst_attr}'])"


def format_rshift_connect(
    src_node: str,
    src_attr: str,
    dst_node: str,
    dst_attr: str,
) -> str:
    """Format a >> connection expression.

    Args:
        src_node: Source node expression.
        src_attr: Source attribute name.
        dst_node: Destination node expression.
        dst_attr: Destination attribute name.

    Returns:
        Formatted >> connection.
    """
    return f"{src_node}['{src_attr}'] >> {dst_node}['{dst_attr}']"


def format_node_create(
    type_name: str,
    **kwargs,
) -> str:
    """Format a node creation call.

    Args:
        type_name: The tik.maya type name (e.g., 'Transform').
        **kwargs: Keyword arguments for the create() call.

    Returns:
        Formatted create() call.
    """
    if kwargs:
        kwargs_str = ", ".join(f"{key}={value}" for key, value in kwargs.items())
        return f"{type_name}.create({kwargs_str})"
    return f"{type_name}.create()"


def format_resolve_call(node_name: str) -> str:
    """Format a resolve() call to wrap a node name.

    Args:
        node_name: The node name string.

    Returns:
        Formatted resolve() call.
    """
    return f"resolve('{node_name}')"
