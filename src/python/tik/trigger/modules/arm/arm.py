"""Arm module: collar + IK/FK arm with ribbon segments.

Composes tik.maya constructs: ``IkFkChain`` for the blend, two ``Ribbon``
setups for the upper/lower arm, ``MatrixConstraint`` for wiring.
"""

from __future__ import annotations

import tik.maya as tm
from tik.maya import attribute
from tik.trigger.core import (
    BoolField,
    ChoiceField,
    FloatField,
    Guides,
    IntField,
    Module,
    register_module,
)


@register_module("arm")
class Arm(Module):
    """Biped arm: collar, shoulder, elbow, hand."""

    label = "Arm"
    guides = Guides("collar", "shoulder", "elbow", "hand")
    plugs = ("collar", "hand")
    sockets = ("root",)

    ribbon_joints = IntField(5, min=1, max=20, help="Deformer joints per ribbon segment")
    ribbon_controllers = IntField(1, min=0, max=5, help="Mid controllers per ribbon segment")
    controller_size = FloatField(3.0, min=0.01, label="Controller Size")
    ik_solver = ChoiceField("ikRPsolver", choices=["ikRPsolver", "ikSCsolver"], label="IK Solver")
    stretchy = BoolField(True, help="Ribbon joints scale with the segment length")

    # --------------------------------------------------------------- guides
    def draw_guides(self, ctx) -> None:
        mult = ctx.side_mult
        collar = ctx.joint("collar", (2 * mult, 0, 0), radius=1.5)
        shoulder = ctx.joint("shoulder", (5 * mult, 0, 0), parent=collar)
        elbow = ctx.joint("elbow", (9 * mult, 0, -1), parent=shoulder)
        ctx.joint("hand", (14 * mult, 0, 0), parent=elbow)

    # ---------------------------------------------------------------- build
    def build(self, ctx) -> None:
        size = self.controller_size
        collar_guide = ctx.guide("collar")
        chain_guides = [ctx.guide("shoulder"), ctx.guide("elbow"), ctx.guide("hand")]

        # joints ----------------------------------------------------------
        collar_jnt = tm.Joint.create(
            name=ctx.name("collar", suffix="jnt"), parent=ctx.groups.joints.long_name
        )
        collar_jnt.align_to(collar_guide)
        rig_joints = tm.Joint.chain(
            [tuple(guide.world_position) for guide in chain_guides],
            name_pattern=ctx.name("arm{index}", suffix="rig"),
            parent=collar_jnt,
        )
        shoulder_jnt, elbow_jnt, hand_rig_jnt = rig_joints
        hand_jnt = tm.Joint.create(
            name=ctx.name("hand", suffix="jnt"), parent=ctx.groups.joints.long_name
        )
        hand_jnt.align_to(hand_rig_jnt)
        tm.MatrixConstraint.create(hand_rig_jnt, hand_jnt, maintain_offset=True)

        # socket + collar controller ----------------------------------------
        socket = tm.Transform.create(
            name=ctx.name("root", suffix="socket"), parent=ctx.groups.controllers.long_name
        )
        socket.align_to(collar_jnt)
        ctx.socket("root", socket)
        collar_ctrl = ctx.controller("collar", shape="CurvedCircle", size=size, parent=socket, match=collar_jnt)
        collar_ctrl.transform.create_offset_group(name=ctx.name("collar", suffix="offset"))
        tm.MatrixConstraint.create(collar_ctrl.transform, collar_jnt, maintain_offset=True)

        # ik/fk switch controller --------------------------------------------
        switch_ctrl = ctx.controller("switch", shape="Cube", size=size * 0.4, parent=socket, match=hand_rig_jnt)
        switch_offset = switch_ctrl.transform.create_offset_group(name=ctx.name("switch", suffix="offset"))
        switch_offset.translate = tuple(
            value + offset for value, offset in zip(switch_offset.translate, (0, size * 1.5, 0))
        )
        attribute.lock_and_hide(switch_ctrl.transform)
        switch_plug = attribute.add_float(switch_ctrl.transform, "ikFk", default=1.0, min=0.0, max=1.0)
        tm.MatrixConstraint.create(hand_rig_jnt, switch_offset, maintain_offset=True, skip_scale="xyz")

        chain = tm.IkFkChain.create(
            rig_joints, name=ctx.name("arm"), switch=switch_plug, solver=self.ik_solver, parent=ctx.groups.rig
        )
        tm.MatrixConstraint.create(collar_jnt, chain.group, maintain_offset=True)

        # fk controllers -----------------------------------------------------
        fk_parent = collar_ctrl.transform
        fk_group = None
        for label, joint in zip(("upArm", "lowArm", "hand"), chain.fk_joints):
            controller = ctx.controller(f"fk_{label}", shape="Circle", size=size, parent=fk_parent, match=joint)
            offset = controller.transform.create_offset_group(name=ctx.name(f"fk_{label}", suffix="offset"))
            attribute.lock_and_hide(controller.transform, ("sx", "sy", "sz", "v"))
            tm.MatrixConstraint.create(controller.transform, joint, maintain_offset=True, skip_scale="xyz")
            fk_group = fk_group or offset
            fk_parent = controller.transform
        chain.fk_visibility >> fk_group["visibility"]

        # ik controllers -----------------------------------------------------
        ik_group = tm.Transform.create(name=ctx.name("ik", suffix="grp"), parent=socket.long_name)
        chain.ik_visibility >> ik_group["visibility"]
        hand_ik = ctx.controller("ik_hand", shape="Cube", size=size, parent=ik_group, match=hand_rig_jnt)
        hand_ik.transform.create_offset_group(name=ctx.name("ik_hand", suffix="offset"))
        tm.MatrixConstraint.create(
            hand_ik.transform, chain.ik_handle, maintain_offset=True, skip_rotate="xyz", skip_scale="xyz"
        )
        tm.MatrixConstraint.create(
            hand_ik.transform, chain.ik_joints[-1], maintain_offset=True, skip_translate="xyz", skip_scale="xyz"
        )

        pole_position = self._pole_position(shoulder_jnt, elbow_jnt, hand_rig_jnt, size * 3)
        pole = ctx.controller("ik_pole", shape="Diamond", size=size * 0.5, parent=ik_group)
        pole.transform.world_position = pole_position
        pole.transform.create_offset_group(name=ctx.name("ik_pole", suffix="offset"))
        attribute.lock_and_hide(pole.transform, ("rx", "ry", "rz", "sx", "sy", "sz", "v"))
        chain.pole_vector(pole.transform)

        # ribbons ------------------------------------------------------------
        deform = [collar_jnt]
        for label, start, end in (("upArm", shoulder_jnt, elbow_jnt), ("lowArm", elbow_jnt, hand_rig_jnt)):
            ribbon = tm.Ribbon.create(
                start,
                end,
                name=ctx.name(label),
                joint_count=self.ribbon_joints,
                controller_count=self.ribbon_controllers,
                scaleable=self.stretchy,
                parent=ctx.groups.scale,
            )
            ribbon.pin_start(start)
            ribbon.pin_end(end)
            for controller in ribbon.controllers:
                ctx.controllers.append(controller)
            deform.extend(ribbon.deformer_joints)
        deform.append(hand_jnt)

        for joint in deform:
            ctx.deform_joint(joint)
        ctx.plug("collar", collar_jnt)
        ctx.plug("hand", hand_jnt)

    @staticmethod
    def _pole_position(start, mid, end, distance: float):
        """Point ``distance`` away from the chain, in the bend direction."""
        start_pos, mid_pos, end_pos = start.world_position, mid.world_position, end.world_position
        axis = end_pos - start_pos
        to_mid = mid_pos - start_pos
        projection = start_pos + axis * ((to_mid * axis) / (axis * axis)) if axis.length() else start_pos
        direction = mid_pos - projection
        if direction.length() < 1e-4:
            direction = axis ^ tm.Transform.between(start, end) if False else type(axis)(0, 0, -1)
        direction.normalize()
        return mid_pos + direction * distance
