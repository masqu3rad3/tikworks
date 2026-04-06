"""
Core conversion engine for tik.maya → maya.cmds transformation.

This module orchestrates the conversion process:
1. Parse source code into AST
2. Analyze and track tik.maya usage patterns
3. Apply conversion rules
4. Expand blessed helpers
5. Generate output code
6. Produce conversion report
"""

import ast
from typing import Dict, List, Optional, Set

from .codegen import CodeBuilder, generate_cmds_import, generate_header_comment
from .helpers import (
    HelperRegistry,
    get_default_registry,
    get_unsupported_reason,
)
from .parsing import get_node_source, parse_source
from .report import ConversionEntry, ConversionReport, EntryType
from .rules import ConversionRule, RuleContext, get_default_rules


class ConversionState:
    """Tracks state during AST traversal and conversion.

    Maintains information about:
    - Variable types (tracking tik.maya object assignments)
    - Import statements
    - Converted nodes (to avoid double-processing)
    """

    def __init__(self) -> None:
        """Initialize conversion state."""
        self.variable_types: Dict[str, str] = {}
        self.imports: Dict[str, str] = {}
        self.converted_nodes: Set[int] = set()
        self.tik_imports_found: bool = False

    def track_variable(self, name: str, type_name: str) -> None:
        """Track a variable's tik.maya type.

        Args:
            name: Variable name.
            type_name: The tik.maya type (e.g., "Transform").
        """
        self.variable_types[name] = type_name

    def get_variable_type(self, name: str) -> Optional[str]:
        """Get the tracked type for a variable.

        Args:
            name: Variable name.

        Returns:
            The type name if tracked, None otherwise.
        """
        return self.variable_types.get(name)

    def mark_converted(self, node: ast.AST) -> None:
        """Mark an AST node as converted.

        Args:
            node: The AST node that was converted.
        """
        self.converted_nodes.add(id(node))

    def is_converted(self, node: ast.AST) -> bool:
        """Check if an AST node has been converted.

        Args:
            node: The AST node to check.

        Returns:
            True if already converted.
        """
        return id(node) in self.converted_nodes


class Converter:
    """Main converter class for tik.maya → maya.cmds transformation.

    The converter performs semantic expansion of tik.maya code into
    explicit maya.cmds equivalents. It does not introspect tik.maya
    internals or rely on runtime behavior.

    Usage:
        converter = Converter()
        result = converter.convert(source_code)
        print(result.converted_code)
        print(result.summary())
    """

    # Known tik.maya type names
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
            "Plug",
        }
    )

    def __init__(
        self,
        rules: Optional[List[ConversionRule]] = None,
        helper_registry: Optional[HelperRegistry] = None,
        add_imports: bool = True,
        add_header: bool = True,
        preserve_comments: bool = True,
    ) -> None:
        """Initialize the converter.

        Args:
            rules: List of conversion rules to use (uses defaults if None).
            helper_registry: Helper registry for blessed expansions.
            add_imports: Whether to add maya.cmds import to output.
            add_header: Whether to add header comment to output.
            preserve_comments: Whether to preserve original comments.
        """
        self.rules = rules or get_default_rules()
        self.helper_registry = helper_registry or get_default_registry()
        self.add_imports = add_imports
        self.add_header = add_header
        self.preserve_comments = preserve_comments

    def convert(self, source_code: str) -> ConversionReport:
        """Convert tik.maya source code to maya.cmds.

        Args:
            source_code: Python source code using tik.maya.

        Returns:
            ConversionReport with converted code and metadata.
        """
        # Parse source
        try:
            tree, source_lines = parse_source(source_code)
        except SyntaxError as syntax_error:
            return ConversionReport(
                source_code=source_code,
                converted_code=source_code,
                entries=[
                    ConversionEntry(
                        entry_type=EntryType.WARNING,
                        line_number=syntax_error.lineno or 0,
                        original_code="",
                        message=f"Syntax error: {syntax_error.msg}",
                    )
                ],
            )

        # Initialize state
        state = ConversionState()
        entries: List[ConversionEntry] = []

        # First pass: analyze imports and variable assignments
        self._analyze_imports(tree, state)
        self._analyze_assignments(tree, state, source_lines)

        # Create rule context
        context = RuleContext(
            variable_types=state.variable_types,
            source_lines=source_lines,
            imports=state.imports,
        )

        # Second pass: convert nodes
        line_replacements: Dict[int, str] = {}

        for node in ast.walk(tree):
            if state.is_converted(node):
                continue

            # Try each rule
            for rule in self.rules:
                if rule.matches(node, context):
                    match = rule.convert(node, context)
                    state.mark_converted(node)

                    line_num = getattr(node, "lineno", 0)
                    original_code = get_node_source(node, source_lines)

                    entries.append(
                        ConversionEntry(
                            entry_type=EntryType.RULE_APPLIED,
                            line_number=line_num,
                            original_code=original_code,
                            converted_code=match.converted_code,
                            rule_name=match.rule_name,
                        )
                    )

                    # Track line replacement
                    if line_num > 0:
                        line_replacements[line_num] = self._apply_replacement(
                            source_lines[line_num - 1],
                            original_code,
                            match.converted_code,
                        )
                    break
            else:
                # Check for unsupported method calls
                self._check_unsupported(node, source_lines, entries)

        # Build output
        converted_code = self._build_output(
            source_lines, line_replacements, entries, state
        )

        return ConversionReport(
            source_code=source_code,
            converted_code=converted_code,
            entries=entries,
        )

    def _analyze_imports(self, tree: ast.Module, state: ConversionState) -> None:
        """Analyze import statements for tik.maya usage.

        Args:
            tree: The AST module.
            state: Conversion state to update.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "tik" in alias.name:
                        state.tik_imports_found = True
                        name = alias.asname if alias.asname else alias.name
                        state.imports[name] = alias.name

            elif isinstance(node, ast.ImportFrom):
                if node.module and "tik" in node.module:
                    state.tik_imports_found = True
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        state.imports[name] = f"{node.module}.{alias.name}"
                        # Track type imports
                        if alias.name in self.TIK_TYPES:
                            state.variable_types[name] = alias.name

    def _analyze_assignments(
        self,
        tree: ast.Module,
        state: ConversionState,
        source_lines: List[str],
    ) -> None:
        """Analyze assignments to track variable types.

        Args:
            tree: The AST module.
            state: Conversion state to update.
            source_lines: Source code lines.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                # Check if RHS is a tik.maya type instantiation or create call
                value = node.value

                type_name = self._extract_type_from_expr(value)
                if type_name:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            state.track_variable(target.id, type_name)

    def _extract_type_from_expr(self, node: ast.AST) -> Optional[str]:
        """Extract tik.maya type from an expression.

        Args:
            node: AST node to analyze.

        Returns:
            The type name if recognized, None otherwise.
        """
        if isinstance(node, ast.Call):
            func = node.func

            # Type.create(...) pattern
            if isinstance(func, ast.Attribute) and func.attr == "create":
                if isinstance(func.value, ast.Name):
                    if func.value.id in self.TIK_TYPES:
                        return func.value.id

            # Type(name) instantiation pattern
            if isinstance(func, ast.Name):
                if func.id in self.TIK_TYPES:
                    return func.id

            # resolve(name) returns a tik object
            if isinstance(func, ast.Name) and func.id == "resolve":
                return "Node"  # Generic, could be any type

        return None

    def _check_unsupported(
        self,
        node: ast.AST,
        source_lines: List[str],
        entries: List[ConversionEntry],
    ) -> None:
        """Check if a node contains unsupported operations.

        Args:
            node: AST node to check.
            source_lines: Source code lines.
            entries: List to append entries to.
        """
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                method_name = func.attr
                reason = get_unsupported_reason(method_name)

                if reason:
                    line_num = getattr(node, "lineno", 0)
                    original_code = get_node_source(node, source_lines)

                    entries.append(
                        ConversionEntry(
                            entry_type=EntryType.UNSUPPORTED,
                            line_number=line_num,
                            original_code=original_code,
                            message=f"{method_name}: {reason}",
                        )
                    )

    def _apply_replacement(
        self, original_line: str, original_expr: str, replacement: str
    ) -> str:
        """Apply a replacement to a line, preserving indentation.

        Args:
            original_line: The full original line.
            original_expr: The expression being replaced.
            replacement: The replacement code.

        Returns:
            The line with replacement applied.
        """
        # Find leading whitespace
        stripped = original_line.lstrip()
        indent = original_line[: len(original_line) - len(stripped)]

        # Try to replace the expression in the line
        if original_expr.strip() in original_line:
            return original_line.replace(original_expr.strip(), replacement)

        # Fallback: replace the whole line content
        return indent + replacement

    def _build_output(
        self,
        source_lines: List[str],
        replacements: Dict[int, str],
        entries: List[ConversionEntry],
        state: ConversionState,
    ) -> str:
        """Build the final output code.

        Args:
            source_lines: Original source lines.
            replacements: Line number to replacement mapping.
            entries: Conversion entries.
            state: Conversion state.

        Returns:
            The converted code string.
        """
        builder = CodeBuilder()

        # Add header if requested
        if self.add_header:
            warnings = [
                entry.message
                for entry in entries
                if entry.entry_type == EntryType.UNSUPPORTED
            ]
            header = generate_header_comment(warnings=warnings if warnings else None)
            for line in header.splitlines():
                builder.add_line(line)
            builder.add_blank_line()

        # Add imports if requested and tik imports were found
        if self.add_imports and state.tik_imports_found:
            builder.add_line(generate_cmds_import())
            builder.add_blank_line()

        # Process lines
        skip_tik_imports = state.tik_imports_found
        for line_num, line in enumerate(source_lines, start=1):
            # Skip tik import lines
            if skip_tik_imports and self._is_tik_import_line(line):
                builder.add_comment(f"Original: {line.strip()}")
                continue

            # Apply replacement if exists
            if line_num in replacements:
                builder.add_line(replacements[line_num])
            else:
                builder.add_line(line)

        return builder.build()

    def _is_tik_import_line(self, line: str) -> bool:
        """Check if a line is a tik.maya import statement.

        Args:
            line: Source line to check.

        Returns:
            True if it's a tik import line.
        """
        stripped = line.strip()
        return (
            stripped.startswith("from tik")
            or stripped.startswith("import tik")
            or "from tik." in stripped
        )


def convert(
    source_code: str,
    add_imports: bool = True,
    add_header: bool = True,
) -> ConversionReport:
    """Convenience function to convert tik.maya code to maya.cmds.

    Args:
        source_code: Python source code using tik.maya.
        add_imports: Whether to add maya.cmds import.
        add_header: Whether to add header comment.

    Returns:
        ConversionReport with results.
    """
    converter = Converter(add_imports=add_imports, add_header=add_header)
    return converter.convert(source_code)
