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
from tik.maya import attribute
from tik.trigger.core import (
    BoolField,
    ChoiceField,
    FloatField,
    GuideLayout,
    Input,
    Module,
    register_module,
)
from tik.trigger.systems.limb import _derive_size, build_ikfk_limb
from tik.trigger.systems.reach import build_reach


@register_module("arm")
class Arm(Module):
    """Biped arm: collar, shoulder, elbow, hand."""

    label = "Arm"
    guides = GuideLayout("collar", "shoulder", "elbow", "hand")
    inputs = (Input("root", primary=True, help="Where the collar hangs (chest/body)"),)
    outputs = ("collar", "upperarm", "lowerarm", "hand")
    space_controls = ("ik", "pole")

    stretch = BoolField(True, help="Build the stretch network")
    squash = BoolField(True, help="Build the compress-side network")
    pole_pin = BoolField(False, help="Lock the elbow to the pole control")
    auto_collar = BoolField(True, help="Build the auto-collar network")
    auto_collar_start = FloatField(
        0.0, min=0.0, max=180.0, label="Auto Collar Start Angle",
        help="Degrees below which the automation does nothing",
    )
    auto_collar_end = FloatField(
        90.0, min=0.0, max=180.0, label="Auto Collar End Angle",
        help="Degrees at or above which it is fully applied",
    )
    auto_collar_interpolation = ChoiceField(
        "smooth", choices=("linear", "smooth", "spline"),
        label="Auto Collar Interpolation",
    )

    def validate(self) -> list[str]:
        problems = super().validate()
        if self.auto_collar and self.auto_collar_start >= self.auto_collar_end:
            problems.append(
                "auto collar start angle must be below the end angle "
                f"({self.auto_collar_start} >= {self.auto_collar_end})"
            )
        return problems

    # --------------------------------------------------------------- guides
    def draw_guides(self, ctx) -> None:
        mult = ctx.side_mult
        collar = ctx.joint("collar", (2 * mult, 0, 0), radius=1.5)
        shoulder = ctx.joint("shoulder", (5 * mult, 0, 0), parent=collar)
        elbow = ctx.joint("elbow", (9 * mult, 0, -1), parent=shoulder)
        ctx.joint("hand", (14 * mult, 0, 0), parent=elbow)

    # ---------------------------------------------------------------- build
    def build(self, ctx) -> None:
        collar_guide = ctx.guide("collar")
        limb_guides = [ctx.guide("shoulder"), ctx.guide("elbow"), ctx.guide("hand")]
        size = _derive_size(limb_guides)

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
        attribute.lock_and_hide(collar_ctrl.transform, ("sx", "sy", "sz", "v"))

        # the limb -------------------------------------------------------------
        limb = build_ikfk_limb(
            ctx,
            limb_guides,
            parent=collar_ctrl.transform,
            bind_joints=bind_joints,
            soft_ik=True,  # never optional for an IK solution
            stretch=self.stretch,
            squash=self.squash,
            pole_pin=self.pole_pin,
            labels=("upper", "lower", "hand"),
        )
        if self.auto_collar:
            auto_grp = tm.Transform.create(
                name=ctx.name("collar", "auto", suffix="grp"),
                parent=collar_offset.long_name,
            )
            auto_grp.snap_to(collar_ctrl.transform)
            # Relative, so set_parent writes no compensation into the channels.
            collar_ctrl.transform.set_parent(auto_grp, relative=True)
            build_reach(
                ctx,
                auto_grp,
                socket,
                limb.ik_tweak.transform,
                limb.ik_control.transform,
                prefix="autoCollar",
                start_angle=self.auto_collar_start,
                end_angle=self.auto_collar_end,
                interpolation=self.auto_collar_interpolation,
                name="collar",
            )

        ctx.output("collar", collar_jnt)
        ctx.output("upperarm", bind_joints[0])
        ctx.output("lowerarm", bind_joints[1])
        ctx.output("hand", bind_joints[2])
