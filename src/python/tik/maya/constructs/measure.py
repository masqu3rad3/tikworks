"""Live distance measurement between two transforms."""

from __future__ import annotations

from typing import Optional

from maya import cmds

from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import resolve
from ..core.scene import create_node


def _node(item):
    return resolve(item) if isinstance(item, str) else item


def _matrix_plug(item) -> Plug:
    """Return a world-matrix plug for a node, a node name, or a matrix plug."""
    if isinstance(item, Plug):
        return item
    return _node(item)["worldMatrix[0]"]


def _label(item) -> str:
    """Short name for an item that may be a node or a plug."""
    return item.node.name if isinstance(item, Plug) else _node(item).name


class Measure:
    """Wrapper for a ``distanceBetween`` node fed by two world matrices."""

    def __init__(self, node, start, end, initial_distance: float) -> None:
        self.node = node
        self.start = start
        self.end = end
        self.initial_distance = initial_distance
        self._ratio_nodes: list = []

    @classmethod
    @undo
    def create(cls, start, end, name: Optional[str] = None) -> "Measure":
        """Measure the distance between ``start`` and ``end``.

        Args:
            start: Node, node name, or matrix plug.
            end: Node, node name, or matrix plug.
            name: Prefix for the created node.
        """
        name = name or f"{_label(start)}_{_label(end)}"
        node = create_node("distanceBetween", name=f"{name}_distance")
        _matrix_plug(start) >> node["inMatrix1"]
        _matrix_plug(end) >> node["inMatrix2"]
        return cls(node, start, end, node["distance"].value)

    @property
    def distance(self) -> Plug:
        """Return the live distance plug."""
        return self.node["distance"]

    @undo
    def ratio_plug(self, scale_plug: Optional[Plug] = None) -> Plug:
        """Return a plug with ``distance / initial_distance`` (/ ``scale_plug``).

        Useful for stretch setups: 1.0 at rest, 2.0 when twice as long.
        """
        ratio = self.distance / self.initial_distance
        self._ratio_nodes.append(ratio.node)
        if scale_plug is not None:
            ratio = ratio / scale_plug
            self._ratio_nodes.append(ratio.node)
        return ratio

    @undo
    def delete(self) -> None:
        """Delete the measurement network."""
        nodes = [self.node, *self._ratio_nodes]
        cmds.delete([node.long_name for node in nodes if node.exists()])
