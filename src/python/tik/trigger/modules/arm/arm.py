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
from tik.trigger.systems.limb_lock import build_limb_lock
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
    limb_lock = BoolField(
        True,
        label="Limb Lock",
        help="Hold the shoulder-to-hand distance while the hand anchors. "
             "Inert until the animator raises limbLock.",
    )
    lock_target = ChoiceField(
        "socket",
        choices=("socket", "output"),
        label="Limb Lock Target",
        help="'socket' pushes this module's own socket; 'output' publishes "
             "the push for a body module to absorb",
    )
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

    @classmethod
    def output_names(cls, settings=None):
        values = settings or {}
        enabled = values.get("limb_lock", cls.limb_lock.default)
        target = values.get("lock_target", cls.lock_target.default)
        if enabled and target == "output":
            return (*cls.outputs, "lock")
        return tuple(cls.outputs)

    def validate(self) -> list[str]:
        problems = super().validate()
        if self.auto_collar and self.auto_collar_start >= self.auto_collar_end:
            problems.append(
                "auto collar start angle must be below the end angle "
                f"({self.auto_collar_start} >= {self.auto_collar_end})"
            )
        return problems

    # --------------------------------------------------------------- guides
    def draw_guides(self, guides) -> None:
        mult = guides.side_mult
        collar = guides.joint("collar", (2 * mult, 0, 0), radius=1.5)
        shoulder = guides.joint("shoulder", (5 * mult, 0, 0), parent=collar)
        elbow = guides.joint("elbow", (9 * mult, 0, -1), parent=shoulder)
        guides.joint("hand", (14 * mult, 0, 0), parent=elbow)

    # ---------------------------------------------------------------- build
    def build(self, rig) -> None:
        collar_guide = rig.guide("collar")
        limb_guides = rig.guides("shoulder", "elbow", "hand")
        size = _derive_size(limb_guides)

        socket = rig.socket("root", match=collar_guide)

        # deform skeleton — created in final position, never reparented -------
        collar_jnt = rig.bind_joint("collar", match=collar_guide)
        bind_joints = []
        parent_joint = collar_jnt
        for label, guide_node in zip(("upperarm", "lowerarm", "hand"), limb_guides):
            joint = rig.bind_joint(label, parent=parent_joint, match=guide_node)
            bind_joints.append(joint)
            parent_joint = joint

        # collar ---------------------------------------------------------------
        # The controller lives in control_grp and is driven by the socket rather
        # than parented under it: control_grp holds nothing but controllers and
        # their offset groups.
        collar_ctrl = rig.controller(
            "collar",
            shape="CurvedCircle",
            size=size,
            match=collar_jnt,
            mirror="behaviour",
        )
        # Driven after the limb is built: limb lock may insert a buffer
        # between the socket and everything hanging off it.
        collar_driver = socket
        tm.MatrixConstraint.create(collar_ctrl, collar_jnt, maintain_offset=True)
        attribute.lock_and_hide(collar_ctrl, ("sx", "sy", "sz", "v"))

        # the limb -------------------------------------------------------------
        limb = build_ikfk_limb(
            rig,
            limb_guides,
            parent=collar_ctrl,
            bind_joints=bind_joints,
            soft_ik=True,  # never optional for an IK solution
            stretch=self.stretch,
            squash=self.squash,
            pole_pin=self.pole_pin,
            labels=("upper", "lower", "hand"),
        )
        if self.auto_collar:
            auto_grp = rig.group("collar", "auto", under=collar_ctrl.offset)
            auto_grp.snap_to(collar_ctrl.transform)
            # Relative, so set_parent writes no compensation into the channels.
            collar_ctrl.transform.set_parent(auto_grp, relative=True)
            build_reach(
                rig,
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

        if self.limb_lock:
            # In socket mode the buffer sits between the socket and everything
            # hanging off it, and becomes the lock's target. lock_root still
            # reads the raw socket, which is what keeps the graph acyclic.
            buffer_group = None
            if self.lock_target == "socket":
                buffer_group = rig.group("lock", "push", under="socket")
                buffer_group.snap_to(socket)
                collar_driver = buffer_group
            lock = build_limb_lock(
                rig,
                socket=socket,
                chain_root=limb.ik_joints[0],
                driver=limb.ik_tweak.transform,
                control=limb.ik_control,
                target=buffer_group,
            )
            if buffer_group is None:
                rig.output("lock", lock.push)

        tm.MatrixConstraint.create(
            collar_driver, collar_ctrl.offset, maintain_offset=True
        )

        rig.output("collar", collar_jnt)
        rig.output("upperarm", bind_joints[0])
        rig.output("lowerarm", bind_joints[1])
        rig.output("hand", bind_joints[2])
