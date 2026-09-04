"""A frame that aims at one target and takes its up direction from another.

The frame sits at ``base``'s position with ``aim_axis`` pointed at
``aim_target``'s position and ``up_axis`` aligned to an axis of ``up_target``.

Because the secondary mode is *Align* rather than *Aim*, rolling ``up_target``
about its twist axis rolls the frame. That twist-awareness is the point: a
rest-captured static offset cannot reproduce it.

``offsetParentMatrix`` is used deliberately. This is a rig helper that is never
exported, and parking the frame there leaves local TRS free to express an
offset along the frame. The live-TRS rule binds bind joints only.
"""

from __future__ import annotations

from typing import Optional, Sequence

from maya import cmds

from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import ensure_node
from ..core.scene import create_node
from ..types.transform import Transform

# A target vector perpendicular to the twist axis.
TWIST_TARGETS = {
    "X": (0.0, 1.0, 0.0),
    "Y": (1.0, 0.0, 0.0),
    "Z": (1.0, 0.0, 0.0),
}


class AimFrame:
    """Wrapper for an ``aimMatrix`` frame and its optional transform."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.node = None
        self.transform: Optional[Transform] = None
        self._nodes: list = []

    @classmethod
    @undo
    def create(
        cls,
        base,
        aim_target,
        up_target=None,
        *,
        aim_axis: Sequence[float] = (1.0, 0.0, 0.0),
        up_axis: Sequence[float] = (0.0, 1.0, 0.0),
        twist_axis: str = "Y",
        parent=None,
        name: Optional[str] = None,
        create_transform: bool = True,
    ) -> "AimFrame":
        """Build the frame.

        Args:
            base: Transform supplying the frame's position. When feeding an IK
                solve, this MUST be upstream of it — an ``ikRPsolver`` rotates
                the chain's root joint, so using that joint creates a cycle.
            aim_target: Transform the primary axis points at.
            up_target: Transform supplying the up direction; defaults to
                ``aim_target``.
            aim_axis: Primary input axis.
            up_axis: Secondary input axis.
            twist_axis: Which axis of ``up_target`` the frame tracks around;
                one of ``"X"``, ``"Y"``, ``"Z"``.
            parent: Optional parent for the created transform.
            name: Prefix for created nodes.
            create_transform: Create a transform carrying the frame. When
                False only ``.matrix`` is produced.

        Returns:
            The construct.
        """
        base = ensure_node(base)
        aim_target = ensure_node(aim_target)
        up_target = ensure_node(up_target) if up_target is not None else aim_target
        twist = twist_axis.upper()
        if twist not in TWIST_TARGETS:
            raise ValueError(f"twist_axis must be X, Y or Z, got {twist_axis!r}.")

        frame = cls(name or "aimFrame")
        node = create_node("aimMatrix", name=f"{frame.name}_aimMatrix")
        node["primaryMode"].value = 1  # Aim
        node["secondaryMode"].value = 2  # Align — the twist-aware part

        secondary_target = TWIST_TARGETS[twist]
        for index, axis in enumerate("XYZ"):
            node[f"primaryInputAxis{axis}"].value = aim_axis[index]
            node[f"primaryTargetVector{axis}"].value = 0.0  # aim at the position
            node[f"secondaryInputAxis{axis}"].value = up_axis[index]
            node[f"secondaryTargetVector{axis}"].value = secondary_target[index]

        base["worldMatrix[0]"] >> node["inputMatrix"]
        aim_target["worldMatrix[0]"] >> node["primaryTargetMatrix"]
        up_target["worldMatrix[0]"] >> node["secondaryTargetMatrix"]
        frame.node = node

        if create_transform:
            frame._build_transform(parent)
        return frame

    def _build_transform(self, parent) -> None:
        """Create the transform carrying the frame in ``offsetParentMatrix``.

        The transform is created *under* its parent rather than reparented
        afterwards: ``set_parent`` compensates local TRS to preserve world
        position, and those are exactly the channels that must stay zero so a
        caller can offset along the frame.
        """
        parent = ensure_node(parent) if parent is not None else None
        transform = Transform.create(
            name=f"{self.name}_frame",
            parent=parent.long_name if parent is not None else None,
        )
        if parent is not None:
            mult = create_node("multMatrix", name=f"{self.name}_frameMultMatrix")
            self.node["outputMatrix"] >> mult["matrixIn[0]"]
            parent["worldInverseMatrix[0]"] >> mult["matrixIn[1]"]
            mult["matrixSum"] >> transform["offsetParentMatrix"]
            self._nodes.append(mult)
        else:
            self.node["outputMatrix"] >> transform["offsetParentMatrix"]
        self.transform = transform

    @property
    def matrix(self) -> Plug:
        """The output frame as a world-matrix plug."""
        return self.node["outputMatrix"]

    @undo
    def delete(self) -> None:
        """Delete the frame network and its transform."""
        names = [node.long_name for node in [self.node, *self._nodes] if node.exists()]
        if self.transform is not None and self.transform.exists():
            names.append(self.transform.long_name)
        if names:
            cmds.delete(names)
