"""Matrix switch: drive a transform from one of several targets.

A ``blendMatrix`` holds one target per driver; an integer/enum control plug
selects which target has weight 1 through ``condition`` nodes. The blended
matrix drives the transform through a :class:`MatrixConstraint`, so parent
compensation and joint orient handling come for free.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from maya import cmds
from maya.api import OpenMaya

from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import ensure_node
from ..core.scene import create_node
from .matrix_constraint import MatrixConstraint

WORLD = None  # sentinel driver meaning "world space"


class MatrixSwitch:
    """Wrapper for a switchable matrix constraint network."""

    def __init__(
        self, driven, blend, control: Plug, constraint: MatrixConstraint, name: str
    ) -> None:
        self.driven = driven
        self.blend = blend
        self.control = control
        self.constraint = constraint
        self.name = name
        self._targets: list = []
        self._conditions: list = []

    @classmethod
    @undo
    def create(
        cls,
        drivers: Sequence,
        driven,
        control: Optional[Plug] = None,
        *,
        maintain_offset: bool = True,
        skip_translate: Iterable[str] = (),
        skip_rotate: Iterable[str] = (),
        skip_scale: Iterable[str] = ("x", "y", "z"),
        name: Optional[str] = None,
    ) -> "MatrixSwitch":
        """Create the switch.

        Args:
            drivers: Driver nodes/names; ``None`` entries mean world space.
            driven: Transform to drive.
            control: Integer/enum plug selecting the active driver index. When
                omitted an integer attribute ``switch`` is added on ``driven``.
            maintain_offset: Capture each driver's offset at creation time.
            skip_translate: Axes left unconnected on the driven node.
            skip_rotate: Axes left unconnected on the driven node.
            skip_scale: Axes left unconnected (all by default).
            name: Prefix for created nodes (defaults to the driven name).
        """
        driven = ensure_node(driven)
        name = name or f"{driven.name}_switch"
        if control is None:
            control = driven["switch"].create(
                "int", default=0, min=0, max=max(len(drivers) - 1, 0)
            )

        rest_matrix = OpenMaya.MMatrix(driven["worldMatrix[0]"].value)
        blend = create_node("blendMatrix", name=f"{name}_blendMatrix")
        constraint = MatrixConstraint.create(
            blend["outputMatrix"],
            driven,
            maintain_offset=False,
            skip_translate=skip_translate,
            skip_rotate=skip_rotate,
            skip_scale=skip_scale,
            name=name,
        )
        switch = cls(driven, blend, control, constraint, name)
        for driver in drivers:
            switch.add_target(
                driver, maintain_offset=maintain_offset, rest_matrix=rest_matrix
            )
        return switch

    @property
    def targets(self) -> list:
        """Return the driver nodes in index order (``None`` for world)."""
        return list(self._targets)

    @undo
    def add_target(
        self,
        driver,
        maintain_offset: bool = True,
        rest_matrix: Optional[OpenMaya.MMatrix] = None,
    ) -> int:
        """Append a driver as a new switch target and return its index.

        Args:
            driver: Driver node/name, or ``None`` for world space.
            maintain_offset: Capture the offset between driven and driver.
            rest_matrix: World matrix of the driven node used for the offset;
                defaults to its current world matrix.
        """
        index = len(self._targets)
        driven_world = (
            OpenMaya.MMatrix(rest_matrix)
            if rest_matrix is not None
            else OpenMaya.MMatrix(self.driven["worldMatrix[0]"].value)
        )
        driver = ensure_node(driver) if driver is not None else None

        if driver is None:
            offset = driven_world if maintain_offset else OpenMaya.MMatrix()
            self.blend[f"target[{index}].targetMatrix"].value = list(offset)
        else:
            driver_world = OpenMaya.MMatrix(driver["worldMatrix[0]"].value)
            if maintain_offset:
                mult = create_node(
                    "multMatrix", name=f"{self.name}_target{index}_multMatrix"
                )
                mult["matrixIn[0]"].value = list(driven_world * driver_world.inverse())
                driver["worldMatrix[0]"] >> mult["matrixIn[1]"]
                mult["matrixSum"] >> self.blend[f"target[{index}].targetMatrix"]
            else:
                driver["worldMatrix[0]"] >> self.blend[f"target[{index}].targetMatrix"]

        condition = create_node(
            "condition", name=f"{self.name}_target{index}_condition"
        )
        condition["operation"].value = 0  # equal
        condition["secondTerm"].value = index
        condition["colorIfTrueR"].value = 1.0
        condition["colorIfFalseR"].value = 0.0
        self.control >> condition["firstTerm"]
        condition["outColorR"] >> self.blend[f"target[{index}].weight"]

        self._targets.append(driver)
        self._conditions.append(condition)
        if index == 0 and self.blend["inputMatrix"].get_input() is None:
            # blendMatrix blends from inputMatrix; use the first target as base
            # so weight 0 on every target still yields a valid matrix.
            source = self.blend[f"target[{index}].targetMatrix"].get_input(plug=True)
            if source is not None:
                source >> self.blend["inputMatrix"]
            else:
                self.blend["inputMatrix"].value = self.blend[
                    f"target[{index}].targetMatrix"
                ].value
        return index

    @property
    def nodes(self) -> list:
        """Return every node created by this switch."""
        created = [self.blend, *self._conditions, *self.constraint.nodes]
        for index in range(len(self._targets)):
            source = self.blend[f"target[{index}].targetMatrix"].get_input()
            if source is not None and source.type == "multMatrix":
                created.append(source)
        return created

    @undo
    def delete(self) -> None:
        """Delete the whole switch network."""
        cmds.delete([node.long_name for node in self.nodes if node.exists()])
