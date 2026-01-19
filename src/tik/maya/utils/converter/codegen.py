"""
Code generation utilities for maya.cmds output.

This module handles the generation of valid Python code that uses
maya.cmds from the converted AST representations.
"""

from typing import List, Optional


class CodeBuilder:
    """Utility for building well-formatted Python code output.

    Handles indentation, line continuations, and comment insertion
    to produce readable, diff-friendly output.
    """

    def __init__(self, indent_size: int = 4) -> None:
        """Initialize the code builder.

        Args:
            indent_size: Number of spaces per indentation level.
        """
        self.indent_size = indent_size
        self._lines: List[str] = []
        self._current_indent = 0

    def add_line(self, line: str) -> "CodeBuilder":
        """Add a line of code with current indentation.

        Args:
            line: The line of code to add.

        Returns:
            Self for method chaining.
        """
        if line.strip():
            indent = " " * (self._current_indent * self.indent_size)
            self._lines.append(f"{indent}{line}")
        else:
            self._lines.append("")
        return self

    def add_comment(self, comment: str) -> "CodeBuilder":
        """Add a comment line.

        Args:
            comment: The comment text (without #).

        Returns:
            Self for method chaining.
        """
        return self.add_line(f"# {comment}")

    def add_import(self, module: str, items: Optional[List[str]] = None) -> "CodeBuilder":
        """Add an import statement.

        Args:
            module: Module to import from.
            items: Specific items to import (for 'from' imports).

        Returns:
            Self for method chaining.
        """
        if items:
            self.add_line(f"from {module} import {', '.join(items)}")
        else:
            self.add_line(f"import {module}")
        return self

    def add_blank_line(self) -> "CodeBuilder":
        """Add a blank line.

        Returns:
            Self for method chaining.
        """
        self._lines.append("")
        return self

    def indent(self) -> "CodeBuilder":
        """Increase indentation level.

        Returns:
            Self for method chaining.
        """
        self._current_indent += 1
        return self

    def dedent(self) -> "CodeBuilder":
        """Decrease indentation level.

        Returns:
            Self for method chaining.
        """
        self._current_indent = max(0, self._current_indent - 1)
        return self

    def build(self) -> str:
        """Build the final code string.

        Returns:
            The generated code as a string.
        """
        return "\n".join(self._lines)


def generate_cmds_import() -> str:
    """Generate the standard maya.cmds import statement.

    Returns:
        Import statement string.
    """
    return "from maya import cmds"


def generate_header_comment(
    original_info: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> str:
    """Generate a header comment for converted code.

    Args:
        original_info: Information about the original source.
        warnings: List of warnings to include.

    Returns:
        Header comment string.
    """
    lines = [
        '"""',
        "Auto-generated maya.cmds code.",
        "Converted from tik.maya source.",
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


def wrap_in_function(
    code: str,
    function_name: str = "converted_code",
    docstring: Optional[str] = None,
) -> str:
    """Wrap converted code in a function definition.

    Args:
        code: The code to wrap.
        function_name: Name for the function.
        docstring: Optional docstring.

    Returns:
        The wrapped code.
    """
    builder = CodeBuilder()
    builder.add_line(f"def {function_name}():")
    builder.indent()

    if docstring:
        builder.add_line(f'"""{docstring}"""')

    for line in code.splitlines():
        builder.add_line(line.strip())

    return builder.build()


def format_setattr_call(
    node_expr: str,
    attr_name: str,
    value: str,
    use_fstring: bool = True,
) -> str:
    """Format a cmds.setAttr call.

    Args:
        node_expr: Expression for the node.
        attr_name: Attribute name.
        value: Value expression.
        use_fstring: Whether to use f-strings for the path.

    Returns:
        Formatted setAttr call.
    """
    if use_fstring:
        return f"cmds.setAttr(f'{{{node_expr}}}.{attr_name}', {value})"
    return f"cmds.setAttr('{node_expr}.{attr_name}', {value})"


def format_getattr_call(
    node_expr: str,
    attr_name: str,
    use_fstring: bool = True,
) -> str:
    """Format a cmds.getAttr call.

    Args:
        node_expr: Expression for the node.
        attr_name: Attribute name.
        use_fstring: Whether to use f-strings for the path.

    Returns:
        Formatted getAttr call.
    """
    if use_fstring:
        return f"cmds.getAttr(f'{{{node_expr}}}.{attr_name}')"
    return f"cmds.getAttr('{node_expr}.{attr_name}')"


def format_connectattr_call(
    src_node: str,
    src_attr: str,
    dst_node: str,
    dst_attr: str,
    force: bool = True,
    use_fstring: bool = True,
) -> str:
    """Format a cmds.connectAttr call.

    Args:
        src_node: Source node expression.
        src_attr: Source attribute name.
        dst_node: Destination node expression.
        dst_attr: Destination attribute name.
        force: Whether to force the connection.
        use_fstring: Whether to use f-strings for paths.

    Returns:
        Formatted connectAttr call.
    """
    force_str = "True" if force else "False"
    if use_fstring:
        return (
            f"cmds.connectAttr(f'{{{src_node}}}.{src_attr}', "
            f"f'{{{dst_node}}}.{dst_attr}', force={force_str})"
        )
    return (
        f"cmds.connectAttr('{src_node}.{src_attr}', "
        f"'{dst_node}.{dst_attr}', force={force_str})"
    )

