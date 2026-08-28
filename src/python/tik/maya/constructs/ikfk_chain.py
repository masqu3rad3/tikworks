"""IK/FK blended joint chain.

Given a joint chain, builds an IK copy (with handle) and an FK copy, and
drives the original joints from a per-joint ``blendMatrix`` weighted by a
single ``ikFk`` plug (0 = FK, 1 = IK).
"""

from __future__ import annotations

from typing import Optional, Sequence

from maya import cmds

from ..core import attribute
from ..core.decorators import undo
from ..core.plug import Plug
from ..core.registry import resolve
from ..core.scene import create_node
from ..types.ikhandle import IkHandle
from ..types.joint import Joint
from ..types.transform import Transform
from .matrix_constraint import MatrixConstraint


def _node(item):
    return resolve(item) if isinstance(item, str) else item


class IkFkChain:
    """Wrapper for an IK/FK blend setup."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.group: Transform = None
        self.blend_joints: list[Joint] = []
        self.ik_joints: list[Joint] = []
        self.fk_joints: list[Joint] = []
        self.ik_handle: IkHandle = None
        self.switch: Plug = None
        self.blend_nodes: list = []
        self.constraints: list[MatrixConstraint] = []
        self._reverse = None

    @classmethod
    @undo
    def create(
        cls,
        joints: Sequence,
        *,
        name: str,
        switch: Optional[Plug] = None,
        solver: str = "ikRPsolver",
        parent=None,
    ) -> "IkFkChain":
        """Build the IK/FK setup on ``joints``.

        Args:
            joints: Existing joint chain (root first) that becomes the blend result.
            name: Prefix for created nodes.
            switch: Float plug 0..1 driving the blend; created on the group if omitted.
            solver: IK solver type for the handle.
            parent: Optional parent for the group.
        """
        joints = [_node(joint) for joint in joints]
        if len(joints) < 2:
            raise ValueError("IkFkChain needs at least two joints.")
        chain = cls(name)
        chain.blend_joints = joints

        chain.group = Transform.create(name=f"{name}_ikfk_grp")
        root_parent = joints[0].parent
        if root_parent is not None:
            chain.group.snap_to(root_parent, position=True, rotation=True, scale=True)
        if parent is not None:
            chain.group.parent = _node(parent)

        chain.switch = switch or attribute.add_float(
            chain.group, "ikFk", default=1.0, min=0.0, max=1.0
        )
        chain.ik_joints = chain._copy_chain("ik")
        chain.fk_joints = chain._copy_chain("fk")
        chain.ik_handle = IkHandle.create(
            chain.ik_joints[0], chain.ik_joints[-1], solver=solver, name=f"{name}_ikHandle"
        )
        chain.ik_handle.parent = chain.group
        chain._blend()
        return chain

    def _copy_chain(self, tag: str) -> list[Joint]:
        copies: list[Joint] = []
        current_parent = self.group
        for index, source in enumerate(self.blend_joints):
            joint = Joint.create(
                name=f"{self.name}_{tag}_{index}_jnt",
                parent=current_parent.long_name,
                radius=source.radius,
            )
            joint.joint_orient = source.joint_orient
            joint.translate = tuple(source.translate)
            joint.rotate = tuple(source.rotate)
            copies.append(joint)
            current_parent = joint
        return copies

    def _blend(self) -> None:
        for index, joint in enumerate(self.blend_joints):
            blend = create_node("blendMatrix", name=f"{self.name}_{index}_blendMatrix")
            self.fk_joints[index]["worldMatrix[0]"] >> blend["inputMatrix"]
            self.ik_joints[index]["worldMatrix[0]"] >> blend["target[0].targetMatrix"]
            self.switch >> blend["target[0].weight"]
            constraint = MatrixConstraint.create(
                blend["outputMatrix"],
                joint,
                maintain_offset=False,
                name=f"{self.name}_{index}_ikfk",
            )
            self.blend_nodes.append(blend)
            self.constraints.append(constraint)

    # ------------------------------------------------------------ accessors
    @property
    def ik_visibility(self) -> Plug:
        """Plug equal to the switch (1 when IK is active)."""
        return self.switch

    @property
    def fk_visibility(self) -> Plug:
        """Plug equal to ``1 - switch`` (1 when FK is active)."""
        if self._reverse is None:
            self._reverse = create_node("reverse", name=f"{self.name}_ikfk_reverse")
            self.switch >> self._reverse["inputX"]
        return self._reverse["outputX"]

    def pole_vector(self, node):
        """Add a pole vector constraint from ``node`` to the IK handle."""
        return self.ik_handle.pole_vector(node)

    @undo
    def delete(self) -> None:
        """Delete the IK/FK network, leaving the original joints unconstrained."""
        for constraint in self.constraints:
            constraint.delete()
        nodes = [node.long_name for node in self.blend_nodes if node.exists()]
        if self._reverse is not None and self._reverse.exists():
            nodes.append(self._reverse.long_name)
        if self.group is not None and self.group.exists():
            nodes.append(self.group.long_name)
        if nodes:
            cmds.delete(nodes)
