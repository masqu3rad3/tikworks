"""Continuous N-target matrix blend.

A ``blendMatrix`` whose targets carry float weights, unlike ``MatrixSwitch``
which selects one target discretely through ``condition`` nodes.
"""

from __future__ import annotations

from typing import Optional, Sequence

from maya import cmds

from ..core.decorators import undo
from ..core.plug import Plug, world_matrix_plug
from ..core.scene import create_node


class MatrixBlend:
    """Wrapper for a ``blendMatrix`` with float-weighted targets."""

    def __init__(self, node) -> None:
        self.node = node

    @classmethod
    @undo
    def create(
        cls,
        base,
        targets: Sequence,
        weights: Optional[Sequence] = None,
        *,
        name: Optional[str] = None,
    ) -> "MatrixBlend":
        """Blend ``targets`` over ``base``.

        Args:
            base: Node, name, or matrix plug used at weight zero.
            targets: Nodes, names, or matrix plugs.
            weights: One ``Plug`` or float per target; defaults to ``1.0``.
            name: Prefix for the created node.

        Returns:
            The construct wrapping the new ``blendMatrix``.
        """
        targets = list(targets)
        if not targets:
            raise ValueError("MatrixBlend needs at least one target.")
        if weights is not None and len(weights) != len(targets):
            raise ValueError("weights must have one entry per target.")
        name = name or "matrixBlend"
        node = create_node("blendMatrix", name=f"{name}_blendMatrix")
        world_matrix_plug(base) >> node["inputMatrix"]
        for index, target in enumerate(targets):
            world_matrix_plug(target) >> node[f"target[{index}].targetMatrix"]
            weight = 1.0 if weights is None else weights[index]
            if isinstance(weight, Plug):
                weight >> node[f"target[{index}].weight"]
            else:
                node[f"target[{index}].weight"].value = float(weight)
        return cls(node)

    @property
    def output(self) -> Plug:
        """Return the blended world-matrix plug."""
        return self.node["outputMatrix"]

    def weight_plug(self, index: int = 0) -> Plug:
        """Return the weight plug for target ``index``."""
        return self.node[f"target[{index}].weight"]

    @undo
    def delete(self) -> None:
        """Delete the blend node."""
        if self.node.exists():
            cmds.delete(self.node.long_name)
