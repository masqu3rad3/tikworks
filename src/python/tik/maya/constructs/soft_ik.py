"""Soft IK: an exponential approach curve for an IK goal.

With ``L`` the total rest length, ``ds = softIk + 0.001`` and ``da = L - ds``::

    f(d) = d                          if d <= da
         = L - ds * e^(-(d-da)/ds)    if d >  da

The curve is C0 at the seam (``f(da) = L - ds = da``) and C1 there
(``f'(da) = 1``, matching the identity branch), and asymptotic to ``L`` so the
chain never fully straightens. Those three properties are what make the solve
soft rather than merely curved.

A branchless form does not work: ``min(d, L - ds*e^...)`` picks the wrong
branch below ``da`` (at ``d=0, ds=1, L=10`` the exponential term evaluates to
``-8093``) and ``max`` picks the wrong branch above, so one ``condition`` node
stays.
"""

from __future__ import annotations

import math
from typing import Optional

from maya import cmds

from ..core.constants import TRANSFORM_CHANNELS
from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import resolve
from ..core.scene import create_node
from ..types.transform import Transform
from .measure import Measure


def _node(item):
    return resolve(item) if isinstance(item, str) else item


class SoftIk:
    """Softened goal position for an IK handle."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.group: Optional[Transform] = None
        self.root = None
        self.goal = None
        self.measure: Optional[Measure] = None
        self._nodes: list = []
        self._distance: Optional[Plug] = None
        self._soft_distance: Optional[Plug] = None
        self._gap: Optional[Plug] = None
        self._goal_matrix: Optional[Plug] = None

    @classmethod
    @undo
    def create(
        cls,
        root,
        goal,
        chain_length: Plug,
        *,
        name: Optional[str] = None,
        parent=None,
        scale_plug: Optional[Plug] = None,
    ) -> "SoftIk":
        """Build the soft-IK network between ``root`` and ``goal``.

        Args:
            root: Transform at the chain root. MUST be upstream of the IK
                solve — an ``ikRPsolver`` rotates the chain's root joint, so
                passing that joint creates a cycle.
            goal: Transform the chain reaches for (the IK control).
            chain_length: Plug carrying the total rest length, normally
                ``ChainLengths.total_length``.
            name: Prefix for created nodes.
            parent: Optional parent for the construct's group.
            scale_plug: Optional global scale the raw distance is divided by.

        Returns:
            The construct.
        """
        soft = cls(name or "softIk")
        soft.root = _node(root)
        soft.goal = _node(goal)

        soft.group = Transform.create(name=f"{soft.name}_softIk_grp")
        if parent is not None:
            soft.group.parent = _node(parent)
        soft.group["softIk"].create("float", default=0.0, min=0.0)
        soft.group["stretch"].create("float", default=0.0, min=0.0, max=1.0)
        # Held as an attribute rather than a floatConstant node: one fewer node
        # type to depend on across Maya versions.
        soft.group["eConstant"].create("float", default=math.e)
        for channel in TRANSFORM_CHANNELS + ("eConstant",):
            plug = soft.group[channel]
            plug.locked = True
            plug.visible = False

        soft.measure = Measure.create(
            soft.root["worldMatrix[0]"],
            soft.goal["worldMatrix[0]"],
            name=f"{soft.name}_softIk",
        )
        distance = soft.measure.distance
        if scale_plug is not None:
            distance = distance / scale_plug
        soft._distance = distance

        soft._build_curve(chain_length)
        soft._build_goal()
        return soft

    # ----------------------------------------------------------- internals
    def _build_curve(self, chain_length: Plug) -> None:
        """Wire ``f(d)`` and the stretch gap."""
        distance = self._distance
        ds = self.soft_plug + 0.001  # guards the divide below
        da = chain_length - ds

        # L - ds * e^(-(d-da)/ds)
        exponent = (distance - da) / ds * -1.0
        curve = chain_length - self.group["eConstant"] ** exponent * ds

        # One condition: identity below the seam, the curve above it.
        self._soft_distance = distance.gt(da, curve, distance)
        self._gap = (distance - self._soft_distance) * self.stretch_plug

    def _build_goal(self) -> None:
        """Place the goal along the root-to-goal ray at the blended distance."""
        aim = create_node("aimMatrix", name=f"{self.name}_softIk_aimMatrix")
        aim["primaryMode"].value = 1  # Aim
        aim["secondaryMode"].value = 0  # None
        aim["primaryInputAxisX"].value = 1.0
        aim["primaryInputAxisY"].value = 0.0
        aim["primaryInputAxisZ"].value = 0.0
        for axis in "XYZ":
            aim[f"primaryTargetVector{axis}"].value = 0.0  # aim at the position
        self.root["worldMatrix[0]"] >> aim["inputMatrix"]
        self.goal["worldMatrix[0]"] >> aim["primaryTargetMatrix"]

        offset = create_node("composeMatrix", name=f"{self.name}_softIk_offset")
        blended = self._soft_distance.lerp(self._distance, self.stretch_plug)
        blended >> offset["inputTranslateX"]

        mult = create_node("multMatrix", name=f"{self.name}_softIk_goalMultMatrix")
        offset["outputMatrix"] >> mult["matrixIn[0]"]
        aim["outputMatrix"] >> mult["matrixIn[1]"]

        self._nodes.extend([aim, offset, mult])
        self._goal_matrix = mult["matrixSum"]

    # ----------------------------------------------------------- accessors
    @property
    def soft_plug(self) -> Plug:
        """Softness distance in scene units; ``0`` disables softening."""
        return self.group["softIk"]

    @property
    def stretch_plug(self) -> Plug:
        """0 = goal is the soft point, 1 = goal is the control."""
        return self.group["stretch"]

    @property
    def distance_plug(self) -> Plug:
        """Raw (scaled) root-to-goal distance."""
        return self._distance

    @property
    def soft_distance(self) -> Plug:
        """``f(d)`` — the softened distance."""
        return self._soft_distance

    @property
    def gap_plug(self) -> Plug:
        """``stretch * (d - f(d))`` — the shortfall a stretch network consumes."""
        return self._gap

    @property
    def goal_matrix(self) -> Plug:
        """World matrix for the ikHandle."""
        return self._goal_matrix

    @undo
    def delete(self) -> None:
        """Delete the network."""
        if self.measure is not None:
            self.measure.delete()
        names = [node.long_name for node in self._nodes if node.exists()]
        if self.group is not None and self.group.exists():
            names.append(self.group.long_name)
        if names:
            cmds.delete(names)
