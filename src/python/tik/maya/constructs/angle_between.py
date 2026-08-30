"""The angle between two vectors, in degrees."""

from __future__ import annotations

from typing import Optional

from maya import cmds

from ..core.decorators import undo
from ..core.plug import Plug
from ..core.scene import create_node


class AngleBetween:
    """Wrapper for an ``angleBetween`` node."""

    def __init__(self, node) -> None:
        self.node = node

    @classmethod
    @undo
    def create(cls, first, second, name: Optional[str] = None) -> "AngleBetween":
        """Measure the angle between ``first`` and ``second``.

        Args:
            first: Compound plug or a 3-tuple.
            second: Compound plug or a 3-tuple.
            name: Prefix for the created node.

        Returns:
            The construct.
        """
        node = create_node("angleBetween", name=f"{name or 'angle'}_angleBetween")
        for attr, item in (("vector1", first), ("vector2", second)):
            if isinstance(item, Plug):
                item >> node[attr]
            else:
                node[attr].value = tuple(float(component) for component in item)
        return cls(node)

    @property
    def angle(self) -> Plug:
        """The angle in degrees."""
        return self.node["angle"]

    @undo
    def delete(self) -> None:
        """Delete the node."""
        if self.node.exists():
            cmds.delete(self.node.long_name)
