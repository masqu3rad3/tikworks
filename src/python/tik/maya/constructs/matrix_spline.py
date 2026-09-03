"""MatrixSpline: geometry-free spline of transforms built from matrix nodes.

Each output is a swing-only transform driven through ``offsetParentMatrix``:
a B-spline-weighted ``parentMatrix`` blend of the driver world matrices
(translate and scale only, rotation stripped by ``pickMatrix``), oriented by
an ``aimMatrix`` that aims at the next output and aligns its up axis to a
caller-supplied, twist-free frame. Twist is interpolated with the same
weights as plain float math and exposed per output as a ``twist`` plug; it
never enters a matrix, so it is unbounded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from maya import cmds

from tik.core.bspline import basis, clamp_degree

from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import ensure_node
from ..core.scene import create_node
from ..types.transform import Transform

AIM = 1  # aimMatrix.primaryMode "Aim"
ALIGN = 2  # aimMatrix.secondaryMode "Align"


@dataclass
class SplineOutput:
    """One sample along the spline."""

    parameter: float
    weights: list[float]
    transform: Transform
    twist: Plug
    nodes: list = field(default_factory=list)


class MatrixSpline:
    """Wrapper holding the drivers, outputs and network of a matrix spline."""

    def __init__(self, name: str, group: Transform, drivers: list, degree: int) -> None:
        self.name = name
        self.group = group
        self.drivers = drivers
        self.degree = degree
        self.outputs: list[SplineOutput] = []

    @classmethod
    @undo
    def create(
        cls,
        drivers: Sequence,
        parameters: Sequence[float],
        *,
        name: str,
        degree: int = 3,
        twists: Optional[Sequence[Optional[Plug]]] = None,
        up_matrix: Optional[Plug] = None,
        aim_axis: Sequence[float] = (1, 0, 0),
        up_axis: Sequence[float] = (0, 1, 0),
        parent=None,
    ) -> "MatrixSpline":
        """Sample ``drivers`` at ``parameters``.

        Args:
            drivers: Ordered transforms (or names) acting as control points.
            parameters: Ascending values in ``[0, 1)``; one output per value.
            name: Prefix for all created nodes.
            degree: Requested B-spline degree, clamped to ``len(drivers) - 1``.
            twists: Optional float plug per driver (``None`` contributes no
                twist), interpolated with the position weights.
            up_matrix: World matrix plug whose ``up_axis`` orients every
                output's secondary axis. Defaults to the first driver.
            aim_axis: Output axis pointing along the strip.
            up_axis: Output axis aligned to ``up_matrix``.
            parent: Optional parent for the spline group.
        """
        drivers = [ensure_node(driver) for driver in drivers]
        if len(drivers) < 2:
            raise ValueError("MatrixSpline needs at least two drivers.")
        parameters = [float(value) for value in parameters]
        if any(value < 0.0 or value >= 1.0 for value in parameters):
            raise ValueError("MatrixSpline parameters must satisfy 0 <= u < 1.")
        if parameters != sorted(parameters):
            raise ValueError("MatrixSpline parameters must be ascending.")
        twists = list(twists) if twists is not None else [None] * len(drivers)
        if len(twists) != len(drivers):
            raise ValueError("One twist plug (or None) per driver is required.")
        degree = clamp_degree(len(drivers), degree)
        if up_matrix is None:
            up_matrix = drivers[0]["worldMatrix[0]"]

        # created in place under the parent so its local transform stays identity;
        # outputs carry world-space matrices and must not be transformed again
        group_kwargs = {"parent": ensure_node(parent).long_name} if parent is not None else {}
        group = Transform.create(name=f"{name}_spline_grp", **group_kwargs)
        group["inheritsTransform"].value = False

        spline = cls(name, group, drivers, degree)
        blends = [spline._create_blend(index, u) for index, u in enumerate(parameters)]
        for index, (u, (pick, weights, nodes)) in enumerate(zip(parameters, blends)):
            if index + 1 < len(blends):
                target = blends[index + 1][0]["outputMatrix"]
            else:
                target = drivers[-1]["worldMatrix[0]"]
            aim = spline._create_aim(index, pick, target, up_matrix, aim_axis, up_axis)
            output = Transform.create(name=f"{name}_{index}_out", parent=group.long_name)
            aim["outputMatrix"] >> output["offsetParentMatrix"]
            twist = output["twist"].create("float", default=0.0)
            twist_source, math_nodes = spline._weighted_sum(twists, weights)
            if twist_source is not None:
                twist_source >> twist
            spline.outputs.append(SplineOutput(u, weights, output, twist, [*nodes, aim, *math_nodes]))
        return spline

    @staticmethod
    def _weighted_sum(plugs: Sequence[Optional[Plug]], weights: Sequence[float]):
        """Return ``(plug, nodes)`` for ``sum(w * plug)``; ``(None, [])`` if nothing contributes."""
        total = None
        nodes: list = []
        for plug, weight in zip(plugs, weights):
            if plug is None or abs(weight) < 1e-9:
                continue
            term = plug
            if abs(weight - 1.0) > 1e-9:
                term = plug * weight
                nodes.append(term.node)
            if total is None:
                total = term
            else:
                total = total + term
                nodes.append(total.node)
        return total, nodes

    @property
    def nodes(self) -> list:
        """Every DG node created for the spline (output transforms excluded)."""
        return [node for output in self.outputs for node in output.nodes]

    @undo
    def delete(self) -> None:
        """Delete the spline group, its outputs and the whole network."""
        cmds.delete([node.long_name for node in self.nodes if node.exists()])
        if self.group.exists():
            cmds.delete(self.group.long_name)

    def _create_blend(self, index: int, u: float):
        """parentMatrix (weighted drivers) -> pickMatrix (translate + scale only)."""
        weights = basis(u, len(self.drivers), self.degree)
        blend = create_node("parentMatrix", name=f"{self.name}_{index}_parentMatrix")
        for slot, (driver, weight) in enumerate(zip(self.drivers, weights)):
            driver["worldMatrix[0]"] >> blend[f"target[{slot}].targetMatrix"]
            blend[f"target[{slot}].weight"].value = weight
        pick = create_node("pickMatrix", name=f"{self.name}_{index}_pickMatrix")
        pick["useRotate"].value = False
        pick["useShear"].value = False
        blend["outputMatrix"] >> pick["inputMatrix"]
        return pick, weights, [blend, pick]

    def _create_aim(self, index: int, pick, target: Plug, up_matrix: Plug, aim_axis, up_axis):
        aim = create_node("aimMatrix", name=f"{self.name}_{index}_aimMatrix")
        pick["outputMatrix"] >> aim["inputMatrix"]
        aim["primaryMode"].value = AIM
        aim["primaryInputAxis"].value = tuple(aim_axis)
        target >> aim["primaryTargetMatrix"]
        aim["secondaryMode"].value = ALIGN
        aim["secondaryInputAxis"].value = tuple(up_axis)
        aim["secondaryTargetVector"].value = tuple(up_axis)
        up_matrix >> aim["secondaryTargetMatrix"]
        return aim
