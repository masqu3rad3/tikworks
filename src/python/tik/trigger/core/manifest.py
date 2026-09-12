"""Module manifest pieces: guides, inputs and outputs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

#: Control tiers, in the order the visibilities enum lists them. ``all`` is
#: the enum's fourth item, not a tier a control can be given.
TIERS = ("primary", "secondary", "tertiary")


class GuideKind(str, Enum):
    """What a guide *is*, to the rig. Never what it looks like.

    The look is a pure function of the kind and lives in one table, in
    ``tik/trigger/guides/nodes.py``. A module states the kind; nothing
    anywhere states a radius, a colour or a shape -- a radius was only ever
    the sentence "this is the module root" written in the wrong language.
    """

    #: The module's anchor. Derived: the first guide a copy draws.
    ROOT = "root"
    #: A joint in the rig. Move it, a bone moves. Derived: the default.
    JOINT = "joint"
    #: Only its *position* is read; nothing in the rig is shaped like it.
    REFERENCE = "reference"
    #: A real rig joint the module places, not the rigger. Declared.
    DRIVEN = "driven"


@dataclass(frozen=True)
class Input:
    """An attachment point another module (or a scene node) can drive.

    Leaving an input unwired is a legal, ordinary state: the socket is created
    either way and simply stands still at its matched guide, so a module built
    alone is a rig root of its own. ``required`` is for the rare module that
    genuinely cannot build without a driver -- nothing this repo ships sets it.

    Args:
        name: Input name (unique per module).
        kind: ``transform`` | ``joint`` | ``attribute`` (graph validation).
        primary: The input the tree view shows as parenting (one per module).
        required: Build fails without a source. Almost never true.
        shared: One port for the whole module rather than one per copy. An
            input belongs to a copy by default -- five fingers may hang off
            five different things -- so this is for the input every copy
            genuinely shares, wired once and driving all of their sockets.
        help: Tooltip text.
    """

    name: str
    kind: str = "transform"
    primary: bool = False
    required: bool = False
    shared: bool = False
    help: str = ""


@dataclass(frozen=True)
class GuideAttr:
    """A float attribute a module's guide carries, authored by the rigger.

    Guides normally round-trip through the ``.trg`` by world position alone.
    A module that needs per-guide *data* -- a twist weight, a falloff -- can
    declare it here and the guide layer creates, exports and restores it.

    Args:
        name: Attribute long name, created on every guide of its role.
        default: Value written at draw time. ``draw_guides`` may overwrite it
            per guide.
        keyable: Whether it shows in the channel box.
        help: Tooltip text.
    """

    name: str
    default: float = 0.0
    keyable: bool = True
    help: str = ""


def instance_key(name: str, side: str) -> str:
    """Stable key used in files and connections: ``L_arm`` / ``body``."""
    side = str(side)
    return name if side in ("C", "") else f"{side}_{name}"


class GuideLayout:
    """Ordered guide roles a module needs.

    Example:
        GuideLayout("collar", "shoulder", "elbow", "hand")
        GuideLayout("root", multi="segment", min=2)   # root + N segment guides

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
        reference: Sequence[str] = (),
        driven: Sequence[str] = (),
    ) -> None:
        if not roles:
            raise ValueError("GuideLayout needs at least one role.")
        if len(set(roles)) != len(roles):
            raise ValueError("Guide roles must be unique.")
        if multi in roles:
            raise ValueError("The multi role must not repeat a fixed role.")
        self.roles: tuple[str, ...] = tuple(roles)
        self.multi = multi
        self.min_count = (min if min is not None else 1) if multi else 0
        self.max_count = max if multi else 0
        self.reference: tuple[str, ...] = tuple(reference)
        self.driven: tuple[str, ...] = tuple(driven)
        self._validate_kinds()

    def _validate_kinds(self) -> None:
        """Declared kinds must name real, distinct, non-root roles."""
        known = set(self.all_roles)
        for label, group in (("reference", self.reference), ("driven", self.driven)):
            for role in group:
                if role not in known:
                    raise ValueError(
                        f"GuideLayout {label}={role!r} is not one of its roles."
                    )
                if role == self.root:
                    # root_guide() and parent_ref() find a module by walking
                    # guide joints; a root that is neither would strand it.
                    raise ValueError(
                        f"GuideLayout {label}={role!r} is the root role, which "
                        "must stay an ordinary joint."
                    )
        both = set(self.reference) & set(self.driven)
        if both:
            raise ValueError(
                f"Guide role(s) {sorted(both)} declared both reference and driven."
            )

    def kind_for(self, role: str, *, is_root: bool = False) -> GuideKind:
        """What ``role`` is. Declared kinds win; the rest is derived.

        ``is_root`` comes from the draft, which knows which guide a copy
        created first -- not from ``self.root``, because a copy's first guide
        is its own root.

        A role this layout has never heard of is a plain ``JOINT``: pivot
        preset guides are created by the framework, not declared here, and
        name their kind explicitly.
        """
        if role in self.reference:
            return GuideKind.REFERENCE
        if role in self.driven:
            return GuideKind.DRIVEN
        return GuideKind.ROOT if is_root else GuideKind.JOINT

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
        multi_count = (
            sum(1 for role, _index in pairs if role == self.multi) if self.multi else 0
        )
        if self.multi:
            if multi_count < self.min_count:
                problems.append(
                    f"needs at least {self.min_count} '{self.multi}' guides"
                )
            if self.max_count and multi_count > self.max_count:
                problems.append(
                    f"allows at most {self.max_count} '{self.multi}' guides"
                )
        for role, _index in pairs:
            if role not in self.all_roles:
                problems.append(f"unknown guide role '{role}'")
        return problems

    def __repr__(self) -> str:
        multi = f", multi={self.multi!r}" if self.multi else ""
        return f"GuideLayout({', '.join(repr(role) for role in self.roles)}{multi})"
