"""Arm module: collar plus a single-IK-chain IK/FK arm.

Three joint sets, not four. The bind joints *are* the IK/FK blend result, so
no redundant blend chain exists, and there is no second IK chain for the pole
— the pole gets a twist-aware auto space instead.

Ribbons and twist live in their own modules. A twist module attached to the
``upperarm`` output creates its joints as siblings of ``lowerarm_jnt``, which
is exactly how engine twist bones are structured, so nothing here needs to
anticipate them.
"""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import (
    BoolField,
    FloatField,
    Guides,
    Input,
    Module,
    register_module,
)
from tik.trigger.systems.limb import build_ikfk_limb


@register_module("arm")
class Arm(Module):
    """Biped arm: collar, shoulder, elbow, hand."""

    label = "Arm"
    guides = Guides("collar", "shoulder", "elbow", "hand")
    inputs = (Input("root", primary=True, help="Where the collar hangs (chest/body)"),)
    outputs = ("collar", "upperarm", "lowerarm", "hand")

    stretch = BoolField(True, help="Build the stretch network")
    squash = BoolField(True, help="Build the compress-side network")
    stretch_limit = FloatField(
        50.0,
        min=0.0,
        max=500.0,
        label="Stretch Limit %",
        help="Default cap on how far a segment may stretch, as a percentage",
    )
    pole_pin = BoolField(False, help="Lock the elbow to the pole control")
    controller_size = FloatField(3.0, min=0.01, label="Controller Size")

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
        limb_guides = [ctx.guide("shoulder"), ctx.guide("elbow"), ctx.guide("hand")]

        # socket -------------------------------------------------------------
        socket = tm.Transform.create(
            name=ctx.name("root", suffix="socket"), parent=ctx.groups.socket.long_name
        )
        socket.align_to(collar_guide)
        ctx.attach("root", socket)

        # deform skeleton — created in final position, never reparented -------
        collar_jnt = ctx.bind_joint("collar", match=collar_guide)
        bind_joints = []
        parent_joint = collar_jnt
        for label, guide_node in zip(("upperarm", "lowerarm", "hand"), limb_guides):
            joint = ctx.bind_joint(label, parent=parent_joint, match=guide_node)
            bind_joints.append(joint)
            parent_joint = joint

        # collar ---------------------------------------------------------------
        # The controller lives in control_grp and is driven by the socket rather
        # than parented under it: control_grp holds nothing but controllers and
        # their offset groups.
        collar_ctrl = ctx.controller(
            "collar",
            shape="CurvedCircle",
            size=size,
            match=collar_jnt,
            mirror="behaviour",
        )
        collar_offset = collar_ctrl.transform.create_offset_group(
            name=ctx.name("collar", suffix="offset")
        )
        tm.MatrixConstraint.create(socket, collar_offset, maintain_offset=True)
        tm.MatrixConstraint.create(collar_ctrl.transform, collar_jnt, maintain_offset=True)

        # the limb -------------------------------------------------------------
        build_ikfk_limb(
            ctx,
            limb_guides,
            name="arm",
            parent=collar_ctrl.transform,
            bind_joints=bind_joints,
            controller_size=size,
            soft_ik=True,  # never optional for an IK solution
            stretch=self.stretch,
            squash=self.squash,
            stretch_limit_default=self.stretch_limit,
            pole_pin=self.pole_pin,
            labels=("upper", "lower", "hand"),
        )

        ctx.output("collar", collar_jnt)
        ctx.output("upperarm", bind_joints[0])
        ctx.output("lowerarm", bind_joints[1])
        ctx.output("hand", bind_joints[2])
