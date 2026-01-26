"""
Core conversion engine for maya.cmds → tik.maya transformation.

This module orchestrates the reverse conversion process:
1. Parse source code into AST
2. Analyze and track maya.cmds usage patterns
3. Apply reverse conversion rules
4. Generate tik.maya output code
5. Produce conversion report

This engine mirrors the structure of engine.py but operates
in the reverse direction: lifting cmds into tik.maya.
"""

import ast
from typing import Dict, List, Optional, Set

from .codegen import CodeBuilder
from .codegen_tik import generate_tik_header_comment, generate_tik_import
from .report import ConversionEntry, ConversionReport, EntryType
from .rules_reverse import (
    ReverseConversionRule,
    ReverseRuleContext,
    get_default_reverse_rules,
    get_unsupported_cmds_reason,
)


def parse_source(source_code: str):
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
    if start_line <= len(source_lines):
        return source_lines[start_line - 1].strip()
    return ""


class ReverseConversionState:
    """Tracks state during AST traversal and reverse conversion.

    Maintains information about:
    - Variable types (inferred from cmds calls)
    - Import statements
    - Converted nodes (to avoid double-processing)
    - Node name to variable mappings
    """

    def __init__(self) -> None:
        """Initialize conversion state."""
        self.variable_types: Dict[str, str] = {}
        self.imports: Dict[str, str] = {}
        self.converted_nodes: Set[int] = set()
        self.cmds_imports_found: bool = False
        self.node_variables: Dict[str, str] = {}  # Maps node names to variables

    def track_variable(self, name: str, type_name: str) -> None:
        """Track a variable's inferred type.

        Args:
            name: Variable name.
            type_name: The inferred type (e.g., "Transform").
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

    def track_node_variable(self, node_name: str, var_name: str) -> None:
        """Track a node name to variable mapping.

        Args:
            node_name: The Maya node name string.
            var_name: The Python variable name.
        """
        self.node_variables[node_name] = var_name


class ReverseConverter:
    """Main converter class for maya.cmds → tik.maya transformation.

    The converter performs semantic lifting of maya.cmds code into
    idiomatic tik.maya expressions. It compresses explicit cmds calls
    into the equivalent tik.maya API.

    Usage:
        converter = ReverseConverter()
        result = converter.convert(source_code)
        print(result.converted_code)
        print(result.summary())
    """

    def __init__(
        self,
        rules: Optional[List[ReverseConversionRule]] = None,
        add_imports: bool = True,
        add_header: bool = True,
        preserve_comments: bool = True,
    ) -> None:
        """Initialize the reverse converter.

        Args:
            rules: List of conversion rules to use (uses defaults if None).
            add_imports: Whether to add tik.maya import to output.
            add_header: Whether to add header comment to output.
            preserve_comments: Whether to preserve original comments.
        """
        self.rules = rules or get_default_reverse_rules()
        self.add_imports = add_imports
        self.add_header = add_header
        self.preserve_comments = preserve_comments

    def convert(self, source_code: str) -> ConversionReport:
        """Convert maya.cmds source code to tik.maya.

        Args:
            source_code: Python source code using maya.cmds.

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
        state = ReverseConversionState()
        entries: List[ConversionEntry] = []

        # First pass: analyze imports and variable assignments
        self._analyze_imports(tree, state)
        self._analyze_assignments(tree, state, source_lines)

        # Create rule context
        context = ReverseRuleContext(
            variable_types=state.variable_types,
            source_lines=source_lines,
            imports=state.imports,
            node_variables=state.node_variables,
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
                # Check for unsupported cmds calls
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

    def _analyze_imports(self, tree: ast.Module, state: ReverseConversionState) -> None:
        """Analyze import statements for maya.cmds usage.

        Args:
            tree: The AST module.
            state: Conversion state to update.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "maya" in alias.name or "cmds" in alias.name:
                        state.cmds_imports_found = True
                        name = alias.asname if alias.asname else alias.name
                        state.imports[name] = alias.name

            elif isinstance(node, ast.ImportFrom):
                if node.module and ("maya" in node.module or "cmds" in node.module):
                    state.cmds_imports_found = True
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        state.imports[name] = f"{node.module}.{alias.name}"

    def _analyze_assignments(
        self,
        tree: ast.Module,
        state: ReverseConversionState,
        source_lines: List[str],
    ) -> None:
        """Analyze assignments to infer variable types from cmds calls.

        Args:
            tree: The AST module.
            state: Conversion state to update.
            source_lines: Source code lines.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                value = node.value
                type_name = self._infer_type_from_cmds(value)

                if type_name:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            state.track_variable(target.id, type_name)
                            # If the cmds call has a name kw, map that node name to the variable
                            node_name = self._extract_node_name_from_cmds(value)
                            if node_name:
                                state.track_node_variable(node_name, target.id)

    def _extract_node_name_from_cmds(self, node: ast.AST) -> Optional[str]:
        """Extract explicit node name from cmds creation calls (name kw).

        Args:
            node: AST node to analyze.

        Returns:
            The explicit node name if present, None otherwise.
        """
        if not isinstance(node, ast.Call):
            return None
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "cmds"
        ):
            return None

        # Look for name kwarg
        for kw in node.keywords:
            if (
                kw.arg == "name"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                return kw.value.value
        return None

    def _infer_type_from_cmds(self, node: ast.AST) -> Optional[str]:
        """Infer tik.maya type from a cmds expression.

        Args:
            node: AST node to analyze.

        Returns:
            The inferred type name if recognized, None otherwise.
        """
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name) and func.value.id == "cmds":
                    cmd_name = func.attr

                    # Map cmds functions to tik types
                    type_map = {
                        "createNode": self._infer_createnode_type(node),
                        "joint": "Joint",
                        "polySphere": "Mesh",
                        "polyCube": "Mesh",
                        "polyPlane": "Mesh",
                        "polyCylinder": "Mesh",
                        "polyCone": "Mesh",
                        "polyTorus": "Mesh",
                        "curve": "Curve",
                        "spaceLocator": "Locator",
                    }

                    if cmd_name in type_map:
                        result = type_map[cmd_name]
                        if callable(result):
                            return result
                        return result

        # Handle subscript for list results: cmds.polySphere()[0]
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Call):
                return self._infer_type_from_cmds(node.value)

        return None

    def _infer_createnode_type(self, call_node: ast.Call) -> Optional[str]:
        """Infer type from cmds.createNode() call.

        Args:
            call_node: The createNode call AST node.

        Returns:
            The inferred type or None.
        """
        if call_node.args:
            first_arg = call_node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                node_type = first_arg.value
                type_map = {
                    "transform": "Transform",
                    "joint": "Joint",
                    "mesh": "Mesh",
                    "nurbsCurve": "Curve",
                    "locator": "Locator",
                }
                return type_map.get(node_type)
        return None

    def _check_unsupported(
        self,
        node: ast.AST,
        source_lines: List[str],
        entries: List[ConversionEntry],
    ) -> None:
        """Check if a node contains unsupported cmds operations.

        Args:
            node: AST node to check.
            source_lines: Source code lines.
            entries: List to append entries to.
        """
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name) and func.value.id == "cmds":
                    cmd_name = func.attr
                    reason = get_unsupported_cmds_reason(cmd_name)

                    if reason:
                        line_num = getattr(node, "lineno", 0)
                        original_code = get_node_source(node, source_lines)

                        entries.append(
                            ConversionEntry(
                                entry_type=EntryType.UNSUPPORTED,
                                line_number=line_num,
                                original_code=original_code,
                                message=f"cmds.{cmd_name}: {reason}",
                            )
                        )

    def _apply_replacement(
        self, original_line: str, original_expr: str, replacement: str
    ) -> str:
        """Apply a replacement to a line, preserving indentation and targets."""
        stripped = original_line.lstrip()
        indent = original_line[: len(original_line) - len(stripped)]

        # Check if the original line is an assignment statement
        is_orig_assignment = False
        assignment_target = None
        try:
            parsed = ast.parse(stripped)
            if parsed.body and isinstance(parsed.body[0], ast.Assign):
                is_orig_assignment = True
                assign_node = parsed.body[0]
                if assign_node.targets:
                    assignment_target = ast.unparse(assign_node.targets[0])
        except SyntaxError:
            pass

        # Check if the replacement is an assignment statement
        is_replacement_assignment = False
        try:
            parsed_replacement = ast.parse(replacement)
            if parsed_replacement.body and isinstance(
                parsed_replacement.body[0], ast.Assign
            ):
                is_replacement_assignment = True
        except SyntaxError:
            pass

        # If the source line is an assignment but the replacement is NOT an assignment,
        # preserve the assignment target from the source line.
        if is_orig_assignment and assignment_target and not is_replacement_assignment:
            return f"{indent}{assignment_target} = {replacement}"

        # Fallback: try to replace the expression within the line
        if original_expr.strip() in original_line:
            return original_line.replace(original_expr.strip(), replacement)

        return indent + replacement

    def _build_output(
        self,
        source_lines: List[str],
        replacements: Dict[int, str],
        entries: List[ConversionEntry],
        state: ReverseConversionState,
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
            header = generate_tik_header_comment(
                warnings=warnings if warnings else None
            )
            for line in header.splitlines():
                builder.add_line(line)
            builder.add_blank_line()

        # Add imports if requested and cmds imports were found
        if self.add_imports and state.cmds_imports_found:
            builder.add_line(generate_tik_import())
            builder.add_blank_line()

        # Process lines
        skip_cmds_imports = state.cmds_imports_found
        for line_num, line in enumerate(source_lines, start=1):
            # Skip cmds import lines
            if skip_cmds_imports and self._is_cmds_import_line(line):
                builder.add_comment(f"Original: {line.strip()}")
                continue

            # Apply replacement if exists
            if line_num in replacements:
                builder.add_line(replacements[line_num])
            else:
                builder.add_line(line)

        return builder.build()

    def _is_cmds_import_line(self, line: str) -> bool:
        """Check if a line is a maya.cmds import statement.

        Args:
            line: Source line to check.

        Returns:
            True if it's a cmds import line.
        """
        stripped = line.strip()
        return (
            stripped.startswith("from maya import cmds")
            or stripped.startswith("from maya.cmds")
            or stripped.startswith("import maya.cmds")
            or "maya import cmds" in stripped
        )


def convert_to_tik(
    source_code: str,
    add_imports: bool = True,
    add_header: bool = True,
) -> ConversionReport:
    """Convenience function to convert maya.cmds code to tik.maya.

    Args:
        source_code: Python source code using maya.cmds.
        add_imports: Whether to add tik.maya import.
        add_header: Whether to add header comment.

    Returns:
        ConversionReport with results.
    """
    converter = ReverseConverter(add_imports=add_imports, add_header=add_header)
    return converter.convert(source_code)
