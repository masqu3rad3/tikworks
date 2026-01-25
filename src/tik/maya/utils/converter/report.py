"""
Conversion report data structures.

Provides structured reporting of conversion results including
applied rules, helper expansions, and unsupported operations.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class EntryType(Enum):
    """Classification of conversion entry types."""

    RULE_APPLIED = "rule_applied"
    HELPER_EXPANDED = "helper_expanded"
    UNSUPPORTED = "unsupported"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ConversionEntry:
    """A single entry in the conversion report."""

    entry_type: EntryType
    line_number: int
    original_code: str
    converted_code: Optional[str] = None
    rule_name: Optional[str] = None
    message: Optional[str] = None

    def __str__(self) -> str:
        """Format entry for human-readable display."""
        prefix = f"[{self.entry_type.value}] Line {self.line_number}"
        if self.rule_name:
            prefix += f" ({self.rule_name})"
        if self.message:
            return f"{prefix}: {self.message}"
        return prefix


@dataclass
class ConversionReport:
    """Complete report of a code conversion operation."""

    source_code: str
    converted_code: str
    entries: List[ConversionEntry] = field(default_factory=list)

    @property
    def rules_applied(self) -> List[ConversionEntry]:
        """Return all entries where a rule was successfully applied."""
        return [
            entry
            for entry in self.entries
            if entry.entry_type == EntryType.RULE_APPLIED
        ]

    @property
    def helpers_expanded(self) -> List[ConversionEntry]:
        """Return all entries where a blessed helper was expanded."""
        return [
            entry
            for entry in self.entries
            if entry.entry_type == EntryType.HELPER_EXPANDED
        ]

    @property
    def unsupported_operations(self) -> List[ConversionEntry]:
        """Return all unsupported operations that were not converted."""
        return [
            entry for entry in self.entries if entry.entry_type == EntryType.UNSUPPORTED
        ]

    @property
    def warnings(self) -> List[ConversionEntry]:
        """Return all warning entries."""
        return [
            entry for entry in self.entries if entry.entry_type == EntryType.WARNING
        ]

    @property
    def success_count(self) -> int:
        """Count of successfully converted expressions."""
        return len(self.rules_applied) + len(self.helpers_expanded)

    @property
    def failure_count(self) -> int:
        """Count of failed or unsupported conversions."""
        return len(self.unsupported_operations)

    def summary(self) -> str:
        """Generate a human-readable summary of the conversion."""
        lines = [
            "=" * 60,
            "CONVERSION REPORT",
            "=" * 60,
            f"Rules applied:        {len(self.rules_applied)}",
            f"Helpers expanded:     {len(self.helpers_expanded)}",
            f"Unsupported:          {len(self.unsupported_operations)}",
            f"Warnings:             {len(self.warnings)}",
            "-" * 60,
        ]

        if self.rules_applied:
            lines.append("\nRULES APPLIED:")
            for entry in self.rules_applied:
                lines.append(f"  Line {entry.line_number}: {entry.rule_name}")

        if self.helpers_expanded:
            lines.append("\nHELPERS EXPANDED:")
            for entry in self.helpers_expanded:
                lines.append(f"  Line {entry.line_number}: {entry.rule_name}")

        if self.unsupported_operations:
            lines.append("\nUNSUPPORTED OPERATIONS:")
            for entry in self.unsupported_operations:
                lines.append(f"  Line {entry.line_number}: {entry.message}")
                lines.append(f"    Original: {entry.original_code.strip()}")

        if self.warnings:
            lines.append("\nWARNINGS:")
            for entry in self.warnings:
                lines.append(f"  Line {entry.line_number}: {entry.message}")

        lines.append("=" * 60)
        return "\n".join(lines)
