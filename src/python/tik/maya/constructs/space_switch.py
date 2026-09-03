"""Space switch: an enum attribute that re-parents a control between spaces.

An offset group is inserted above the node and driven by a
:class:`MatrixSwitch`; index 0 is always world space.
"""

from __future__ import annotations

from typing import Optional, Sequence

from maya import cmds

from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import resolve
from .matrix_switch import WORLD, MatrixSwitch

_MODES = {
    "parent": {},
    "point": {"skip_rotate": ("x", "y", "z")},
    "orient": {"skip_translate": ("x", "y", "z")},
}


def _node(item):
    return resolve(item) if isinstance(item, str) else item


class SpaceSwitch:
    """Wrapper for a space switch setup."""

    def __init__(self, node, offset, attr: Plug, switch: MatrixSwitch) -> None:
        self.node = node
        self.offset = offset
        self.attr = attr
        self.switch = switch

    @classmethod
    @undo
    def create(
        cls,
        node,
        spaces: Sequence,
        *,
        control=None,
        attr_name: str = "space",
        mode: str = "parent",
        labels: Optional[Sequence[str]] = None,
        default: int = 0,
        world: bool = True,
        name: Optional[str] = None,
    ) -> "SpaceSwitch":
        """Create a space switch on ``node``.

        Args:
            node: The controlled transform (an offset group is added above it).
            spaces: Target transforms; ``world`` is always prepended as index 0.
            control: Node receiving the enum attribute (defaults to ``node``).
            attr_name: Enum attribute name.
            mode: ``"parent"``, ``"point"`` or ``"orient"``.
            labels: Enum labels for ``spaces`` (defaults to node names).
            default: Default enum index.
            world: Prepend a ``world`` entry at index 0. Set False when only
                the given spaces should appear.
            name: Prefix for created nodes.
        """
        if mode not in _MODES:
            raise ValueError(f"Unknown mode '{mode}'. Use one of {sorted(_MODES)}.")
        node = _node(node)
        control = _node(control) if control is not None else node
        spaces = [_node(space) for space in spaces]
        labels = list(labels) if labels else [space.name for space in spaces]
        name = name or f"{node.name}_space"

        offset = node.create_offset_group(name=f"{name}_grp")
        entries = [WORLD, *spaces] if world else list(spaces)
        names = ["world", *labels] if world else list(labels)
        attr = control[attr_name].create("enum", items=names, default=default)
        switch = MatrixSwitch.create(
            entries,
            offset,
            control=attr,
            maintain_offset=True,
            name=name,
            **_MODES[mode],
        )
        return cls(node, offset, attr, switch)

    @property
    def labels(self) -> list[str]:
        """Return the enum labels, world first."""
        listed = cmds.attributeQuery(self.attr.attr, node=self.attr.node.long_name, listEnum=True)
        return listed[0].split(":") if listed else []

    @undo
    def add_space(self, target, label: Optional[str] = None) -> int:
        """Append a new space and extend the enum; returns its index."""
        target = _node(target)
        label = label or target.name
        new_labels = [*self.labels, label]
        cmds.addAttr(self.attr.path, edit=True, enumName=":".join(new_labels))
        return self.switch.add_target(target, maintain_offset=True)

    @undo
    def delete(self) -> None:
        """Remove the switch network, offset group, and enum attribute."""
        self.switch.delete()
        parent = self.offset.parent
        self.node.parent = parent
        self.offset.delete()
        self.attr.delete()
