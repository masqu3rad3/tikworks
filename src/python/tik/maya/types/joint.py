"""Joint node type wrapper."""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

import maya.cmds as cmds

from ..core.apicommon import create_node_with_dag_modifier
from ..core.registry import register
from .transform import Transform

_MIRROR_FLAGS = {"x": "mirrorYZ", "y": "mirrorXZ", "z": "mirrorXY"}


@register("joint")
class Joint(Transform):
    """Wrapper for joint nodes."""

    @classmethod
    def create(
        cls,
        name=None,
        parent=None,
        position=None,
        orientation=None,
        scale=None,
        radius=None,
    ):
        """Create and wrap a new joint node.

        Args:
            name: Node name.
            parent: Parent node or name.
            position: Local translation.
            orientation: Joint orient values in degrees.
            scale: Scale values.
            radius: Display radius.
        """
        jnt = create_node_with_dag_modifier("joint", name=name, parent=parent)
        jnt_obj = cls(jnt)
        if position is not None:
            jnt_obj.translate = position
        if orientation is not None:
            jnt_obj.orient(orientation)
        if scale is not None:
            jnt_obj.scale = scale
        if radius is not None:
            jnt_obj.radius = radius
        return jnt_obj

    @classmethod
    def chain(
        cls,
        positions: Sequence[Sequence[float]],
        name_pattern: str = "joint_{index}",
        parent=None,
        radius: float = 1.0,
        orient: bool = True,
    ) -> list["Joint"]:
        """Create a parented joint chain through world ``positions``.

        Args:
            positions: World positions, one per joint.
            name_pattern: ``str.format`` pattern receiving ``index``.
            parent: Optional parent for the first joint.
            radius: Display radius applied to every joint.
            orient: Orient the chain (aim X down the chain, Y up) when True.
        """
        joints: list[Joint] = []
        current_parent = parent
        for index, position in enumerate(positions):
            joint = cls.create(
                name=name_pattern.format(index=index),
                parent=current_parent,
                radius=radius,
            )
            joint.world_position = position
            joints.append(joint)
            current_parent = joint
        if orient and len(joints) > 1:
            cls.orient_chain(joints)
        return joints

    @staticmethod
    def orient_chain(
        joints: Iterable["Joint"],
        aim_axis: str = "x",
        up_axis: str = "y",
        world_up: Sequence[float] = (0, 1, 0),
    ) -> None:
        """Orient ``joints`` so ``aim_axis`` points down the chain.

        The last joint inherits its parent orientation (zero joint orient).
        """
        joints = list(joints)
        orient_flag = f"{aim_axis}{up_axis}{''.join(sorted(set('xyz') - {aim_axis, up_axis}))}"
        secondary = f"{up_axis}up"
        for joint in joints[:-1]:
            cmds.joint(
                joint.long_name,
                edit=True,
                orientJoint=orient_flag,
                secondaryAxisOrient=secondary,
                zeroScaleOrient=True,
            )
        if joints:
            cmds.joint(joints[-1].long_name, edit=True, orientation=(0, 0, 0))

    @property
    def radius(self):
        """Get or set the joint radius."""
        return self["radius"].get()

    @radius.setter
    def radius(self, value):
        self["radius"].set(value)

    @property
    def joint_orient(self):
        """Get or set the joint orient values (degrees)."""
        return tuple(self["jointOrient"].get()[0])

    @joint_orient.setter
    def joint_orient(self, value):
        self["jointOrient"].set((value[0], value[1], value[2]))

    def orient(self, xyz=(0, 0, 0)):
        """Orient the joint using the provided XYZ values."""
        cmds.joint(self.long_name, edit=True, orientation=xyz)

    def mirror(
        self,
        mirror_axis: str = "x",
        search: str = "",
        replace: str = "",
        behavior: bool = True,
    ) -> "Joint":
        """Mirror this joint (and its hierarchy) across the given world axis.

        Args:
            mirror_axis: ``"x"``, ``"y"`` or ``"z"`` — the axis flipped.
            search: Substring replaced in the mirrored names.
            replace: Replacement for ``search``.
            behavior: Mirror behaviour (True) or orientation only (False).

        Returns:
            The mirrored root joint.
        """
        flag = _MIRROR_FLAGS[mirror_axis.lower()]
        kwargs = {flag: True, "mirrorBehavior": behavior}
        if search or replace:
            kwargs["searchReplace"] = (search, replace)
        result = cmds.mirrorJoint(self.long_name, **kwargs)
        return Joint(result[0])
