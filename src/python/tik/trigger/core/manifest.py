"""Module manifest pieces: guides, inputs and outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class Input:
    """An attachment point another module (or a scene node) can drive.

    Args:
        name: Input name (unique per module).
        kind: ``transform`` | ``joint`` | ``attribute`` (graph validation).
        primary: The input the tree view shows as parenting (one per module).
        optional: Build succeeds without a source.
        help: Tooltip text.
    """

    name: str
    kind: str = "transform"
    primary: bool = False
    optional: bool = False
    help: str = ""


def instance_key(name: str, side: str) -> str:
    """Stable key used in files and connections: ``L_arm`` / ``body``."""
    side = str(side)
    return name if side in ("C", "") else f"{side}_{name}"


class Guides:
    """Ordered guide roles a module needs.

    Example:
        Guides("collar", "shoulder", "elbow", "hand")
        Guides("root", multi="segment", min=2)   # root + N segment guides

    Args:
        *roles: Fixed roles, root first.
        multi: Optional role that repeats ``count`` times after the fixed ones.
        min: Minimum count for the multi role (default 1).
        max: Maximum count for the multi role (default unlimited).
    """

    def __init__(
        self,
        *roles: str,
        multi: Optional[str] = None,
        min: Optional[int] = None,  # noqa: A002
        max: Optional[int] = None,  # noqa: A002
    ) -> None:
        if not roles:
            raise ValueError("Guides needs at least one role.")
        if len(set(roles)) != len(roles):
            raise ValueError("Guide roles must be unique.")
        if multi in roles:
            raise ValueError("The multi role must not repeat a fixed role.")
        self.roles: tuple[str, ...] = tuple(roles)
        self.multi = multi
        self.min_count = (min if min is not None else 1) if multi else 0
        self.max_count = max if multi else 0

    @property
    def root(self) -> str:
        """The first (root) role."""
        return self.roles[0]

    @property
    def all_roles(self) -> tuple[str, ...]:
        """Fixed roles plus the multi role when present."""
        return self.roles + ((self.multi,) if self.multi else ())

    def expand(self, count: Optional[int] = None) -> list[tuple[str, int]]:
        """Return ``(role, index)`` pairs for a concrete guide set.

        Args:
            count: Number of multi-role guides; defaults to ``min_count``.
        """
        pairs = [(role, 0) for role in self.roles]
        if self.multi:
            count = self.min_count if count is None else count
            pairs.extend((self.multi, index) for index in range(count))
        return pairs

    def validate(self, pairs: Sequence[tuple[str, int]]) -> list[str]:
        """Return a list of problems for the given ``(role, index)`` pairs."""
        problems: list[str] = []
        present = set(pairs)
        for role in self.roles:
            if (role, 0) not in present:
                problems.append(f"missing guide '{role}'")
        multi_count = sum(1 for role, _index in pairs if role == self.multi) if self.multi else 0
        if self.multi:
            if multi_count < self.min_count:
                problems.append(f"needs at least {self.min_count} '{self.multi}' guides")
            if self.max_count and multi_count > self.max_count:
                problems.append(f"allows at most {self.max_count} '{self.multi}' guides")
        for role, _index in pairs:
            if role not in self.all_roles:
                problems.append(f"unknown guide role '{role}'")
        return problems

    def __repr__(self) -> str:
        multi = f", multi={self.multi!r}" if self.multi else ""
        return f"Guides({', '.join(repr(role) for role in self.roles)}{multi})"
