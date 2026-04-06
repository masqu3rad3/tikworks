"""
AST parsing utilities for tik.maya code analysis.

This module handles parsing of Python source code using the AST module,
providing utilities for analyzing tik.maya expressions without relying
on tik.maya internals.
"""

import ast
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ParsedExpression:
    """Represents a parsed tik.maya expression with context."""

    node: ast.AST
    line_number: int
    col_offset: int
    end_line_number: Optional[int]
    end_col_offset: Optional[int]
    source_segment: str


class TikMayaASTVisitor(ast.NodeVisitor):
    """
    AST visitor that identifies tik.maya patterns in source code.

    This visitor recognizes:
    - Node creation patterns (Transform.create(), Mesh.create(), etc.)
    - Attribute access patterns (node["attr"], node.property)
    - Attribute assignment patterns (node["attr"].set(), node.property = value)
    - Connection patterns (plug.connect(), plug >> other_plug)
    - Method call patterns on tik.maya objects
    """

    # Known tik.maya type names for recognition
    TIK_TYPES = frozenset(
        {
            "Node",
            "DagNode",
            "ShapeNode",
            "Transform",
            "Joint",
            "Mesh",
            "Curve",
            "Nurbs",
            "Locator",
            "Light",
            "Camera",
            "Controller",
        }
    )

    # Known tik.maya module import patterns
    TIK_IMPORT_PATTERNS = frozenset(
        {
            "tik.maya",
            "tik.maya.types",
            "tik.maya.core",
            "tik.maya.roles",
        }
    )

    def __init__(self, source_lines: List[str]):
        """Initialize visitor with source lines for segment extraction.

        Args:
            source_lines: List of source code lines for context extraction.
        """
        self.source_lines = source_lines
        self.found_expressions: List[ParsedExpression] = []
        self.tik_imports: Dict[str, str] = {}  # Maps alias -> full module path
        self.tik_names: Dict[str, str] = (
            {}
        )  # Maps name -> type (e.g., "node1" -> "Transform")

    def get_source_segment(
        self,
        start_line: int,
        start_col: int,
        end_line: Optional[int],
        end_col: Optional[int],
    ) -> str:
        """Extract source code segment from line/column positions.

        Args:
            start_line: 1-based starting line number.
            start_col: 0-based starting column.
            end_line: 1-based ending line number (optional).
            end_col: 0-based ending column (optional).

        Returns:
            The source code segment as a string.
        """
        if end_line is None or end_col is None:
            # Single token, return the line from start_col
            return self.source_lines[start_line - 1][start_col:]

        if start_line == end_line:
            return self.source_lines[start_line - 1][start_col:end_col]

        # Multi-line segment
        lines = [self.source_lines[start_line - 1][start_col:]]
        for line_idx in range(start_line, end_line - 1):
            lines.append(self.source_lines[line_idx])
        lines.append(self.source_lines[end_line - 1][:end_col])
        return "\n".join(lines)

    def visit_Import(self, node: ast.Import) -> Any:
        """Track import statements for tik modules."""
        for alias in node.names:
            if any(
                alias.name.startswith(pattern) for pattern in self.TIK_IMPORT_PATTERNS
            ):
                name = alias.asname if alias.asname else alias.name
                self.tik_imports[name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        """Track from ... import statements for tik modules."""
        if node.module and any(
            node.module.startswith(pattern) for pattern in self.TIK_IMPORT_PATTERNS
        ):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                self.tik_imports[name] = f"{node.module}.{alias.name}"
                # Track if importing a known type directly
                if alias.name in self.TIK_TYPES:
                    self.tik_names[name] = alias.name
        self.generic_visit(node)

    def _is_tik_type_reference(self, node: ast.AST) -> Optional[str]:
        """Check if node references a known tik.maya type.

        Args:
            node: AST node to check.

        Returns:
            The type name if it's a tik type, None otherwise.
        """
        if isinstance(node, ast.Name):
            if node.id in self.TIK_TYPES:
                return node.id
            if node.id in self.tik_names:
                return self.tik_names[node.id]
        elif isinstance(node, ast.Attribute):
            # e.g., tik.maya.Transform or tik_maya.Transform
            if node.attr in self.TIK_TYPES:
                return node.attr
        return None

    def _is_tik_object_reference(self, node: ast.AST) -> bool:
        """Check if node likely references a tik.maya object instance.

        This is heuristic-based since we don't have runtime type info.

        Args:
            node: AST node to check.

        Returns:
            True if the node likely references a tik object.
        """
        if isinstance(node, ast.Name):
            # Check if we've tracked this name as a tik object
            return node.id in self.tik_names
        return False


def parse_source(source_code: str) -> Tuple[ast.Module, List[str]]:
    """Parse Python source code into AST and lines.

    Args:
        source_code: Python source code string.

    Returns:
        Tuple of (AST module, list of source lines).

    Raises:
        SyntaxError: If the source code has syntax errors.
    """
    tree = ast.parse(source_code)
    lines = source_code.splitlines()
    return tree, lines


def get_node_source(node: ast.AST, source_lines: List[str]) -> str:
    """Extract source code for an AST node.

    Args:
        node: AST node with line/column info.
        source_lines: List of source code lines.

    Returns:
        The source code corresponding to the node.
    """
    if not hasattr(node, "lineno"):
        return ""

    start_line = node.lineno
    start_col = node.col_offset
    end_line = getattr(node, "end_lineno", start_line)
    end_col = getattr(node, "end_col_offset", None)

    if end_line is None:
        return source_lines[start_line - 1][start_col:]

    if start_line == end_line:
        if end_col is not None:
            return source_lines[start_line - 1][start_col:end_col]
        return source_lines[start_line - 1][start_col:]

    # Multi-line
    lines = [source_lines[start_line - 1][start_col:]]
    for line_idx in range(start_line, end_line - 1):
        lines.append(source_lines[line_idx])
    if end_col is not None:
        lines.append(source_lines[end_line - 1][:end_col])
    else:
        lines.append(source_lines[end_line - 1])
    return "\n".join(lines)


def unparse_node(node: ast.AST) -> str:
    """Convert an AST node back to source code.

    Args:
        node: AST node to unparse.

    Returns:
        Python source code string.
    """
    return ast.unparse(node)
