"""Joint node type wrapper."""

from __future__ import annotations

from typing import Iterable, Sequence

import maya.cmds as cmds
from maya.api import OpenMaya

from ..core.apicommon import create_node_with_dag_modifier
from ..core.registry import register
from .transform import Transform

_MIRROR_FLAGS = {"x": "mirrorYZ", "y": "mirrorXZ", "z": "mirrorXY"}
_AXIS_VECTORS = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


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

    @classmethod
    def duplicate_chain(
        cls,
        joints: Sequence["Joint"],
        prefix: str,
        parent=None,
    ) -> list["Joint"]:
        """Duplicate ``joints`` as a fresh parented chain named ``<prefix>_<i>_jnt``.

        Copies ``jointOrient``, ``translate``, ``rotate``, ``scale``,
        ``preferredAngle`` and ``radius``. Dropping ``preferredAngle`` would let
        an ``ikRPsolver`` chain solve to a degenerate plane.

        Args:
            joints: Source chain, root first.
            prefix: Name prefix for the copies.
            parent: Optional parent for the first copy.

        Returns:
            The copies, root first.
        """
        copies: list[Joint] = []
        current_parent = parent
        for index, source in enumerate(joints):
            joint = cls.create(
                name=f"{prefix}_{index}_jnt",
                parent=(
                    current_parent.long_name
                    if hasattr(current_parent, "long_name")
                    else current_parent
                ),
                radius=source.radius,
            )
            joint.joint_orient = source.joint_orient
            joint.translate = tuple(source.translate)
            joint.rotate = tuple(source.rotate)
            joint.scale = tuple(source.scale)
            joint.preferred_angle = source.preferred_angle
            copies.append(joint)
            current_parent = joint
        return copies

    @staticmethod
    def orient_chain(
        joints: Iterable["Joint"],
        aim_axis: str = "x",
        up_axis: str = "y",
        world_up: Sequence[float] = (0, 1, 0),
        reverse_aim: bool = False,
        reverse_up: bool = False,
    ) -> None:
        """Orient ``joints`` so ``aim_axis`` points down the chain.

        The last joint inherits its parent orientation (zero joint orient).

        Args:
            joints: The chain, root first.
            aim_axis: Axis aimed down the chain.
            up_axis: Secondary axis.
            world_up: World up reference.
            reverse_aim: Flip the aim axis 180 degrees about ``up_axis`` — a
                mirrored-behaviour side, where the aim axis points back up the
                chain and ``translateX`` is therefore negative.
            reverse_up: Flip the up axis 180 degrees about ``aim_axis``.
        """
        joints = list(joints)
        if len(joints) < 2:
            return
        if reverse_aim or reverse_up:
            Joint._orient_chain_aimed(
                joints, aim_axis, up_axis, world_up, reverse_aim, reverse_up
            )
            return
        orient_flag = (
            f"{aim_axis}{up_axis}{''.join(sorted(set('xyz') - {aim_axis, up_axis}))}"
        )
        secondary = f"{up_axis}up"
        for joint in joints[:-1]:
            cmds.joint(
                joint.long_name,
                edit=True,
                orientJoint=orient_flag,
                secondaryAxisOrient=secondary,
                zeroScaleOrient=True,
            )
        cmds.joint(joints[-1].long_name, edit=True, orientation=(0, 0, 0))

    @staticmethod
    def _orient_chain_aimed(
        joints, aim_axis, up_axis, world_up, reverse_aim, reverse_up
    ):
        """Orient with explicit (optionally negated) aim and up vectors.

        ``cmds.joint -orientJoint`` takes an axis *string* and so cannot express
        a negated axis. Aim-constraining each joint at the next one with a
        negated vector can, and baking the result with ``makeIdentity`` moves it
        into ``jointOrient``.

        The chain is flattened to the world first so each joint can be aimed
        without its parent's orientation interfering, then re-parented — which
        recomputes the local translations, giving the negative ``translateX``
        that a mirrored-behaviour side needs.
        """
        aim_vector = OpenMaya.MVector(*_AXIS_VECTORS[aim_axis])
        up_vector = OpenMaya.MVector(*_AXIS_VECTORS[up_axis])
        if reverse_aim:
            aim_vector = -aim_vector
        if reverse_up:
            up_vector = -up_vector

        # long_name is re-resolved on every use: unparenting a joint invalidates
        # the cached paths of everything below it.
        for joint in joints[1:]:
            cmds.parent(joint.long_name, world=True)

        for index, joint in enumerate(joints[:-1]):
            constraint = cmds.aimConstraint(
                joints[index + 1].long_name,
                joint.long_name,
                aimVector=tuple(aim_vector),
                upVector=tuple(up_vector),
                worldUpVector=tuple(world_up),
                worldUpType="vector",
                weight=1.0,
            )
            cmds.delete(constraint)
            cmds.makeIdentity(joint.long_name, apply=True)

        for index, joint in enumerate(joints[1:]):
            cmds.parent(joint.long_name, joints[index].long_name)
        cmds.makeIdentity(joints[-1].long_name, apply=True)
        joints[-1].joint_orient = (0.0, 0.0, 0.0)

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

    @property
    def preferred_angle(self):
        """Get or set the preferred angle values (degrees).

        An ``ikRPsolver`` chain with a zero preferred angle can solve to a
        degenerate plane, so this must survive chain duplication.
        """
        return tuple(self["preferredAngle"].get()[0])

    @preferred_angle.setter
    def preferred_angle(self, value):
        self["preferredAngle"].set((value[0], value[1], value[2]))

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
