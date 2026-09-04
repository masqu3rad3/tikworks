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
    ChoiceField,
    FieldGroup,
    GuideLayout,
    Input,
    Module,
    Vector2Field,
    register_module,
)
from tik.trigger.systems.limb import _derive_size, build_ikfk_limb
from tik.trigger.systems.limb_lock import build_limb_lock
from tik.trigger.systems.reach import ReachAxis, build_reach

LIMB_LOCK = FieldGroup("Limb Lock")
AUTO_COLLAR = FieldGroup("Auto Collar", collapsed=True)


@register_module("arm")
class Arm(Module):
    """Biped arm: collar, shoulder, elbow, hand."""

    label = "Arm"
    guides = GuideLayout("collar", "shoulder", "elbow", "hand", "neutral")
    inputs = (Input("root", primary=True, help="Where the collar hangs (chest/body)"),)
    outputs = ("collar", "upperarm", "lowerarm", "hand")
    space_controls = ("ik", "pole")

    stretch = BoolField(True, help="Build the stretch network")
    squash = BoolField(True, help="Build the compress-side network")
    pole_pin = BoolField(False, help="Lock the elbow to the pole control")
    lock_from = ChoiceField(
        "shoulder",
        choices=("shoulder", "collar"),
        label="Lock From",
        group=LIMB_LOCK,
        help="'shoulder' displaces the arm chain and leaves the collar on the "
        "chest; 'collar' carries the clavicle along too",
    )
    limb_lock = BoolField(
        True,
        label="Limb Lock",
        group=LIMB_LOCK,
        help="Hold the shoulder-to-hand distance while the hand anchors. "
        "Inert until the animator raises limbLock.",
    )
    auto_collar = BoolField(
        True, help="Build the auto-collar network", group=AUTO_COLLAR
    )
    # Angles are measured from the `neutral` guide, so zero is where the
    # clavicle changes direction. Both limits stay inside +/-89: the driver's
    # off-plane angles saturate at 90, so a wider limit is never reached.
    auto_collar_lift_angles = Vector2Field(
        (-60.0, 75.0),
        min=-89.0,
        max=89.0,
        labels=("Lower", "Upper"),
        label="Lift Angles",
        group=AUTO_COLLAR,
        help="Arm elevation either side of the neutral guide at full falloff. "
        "Both stay inside +/-89: the driver's off-plane angles saturate "
        "at 90, so a wider limit is never reached.",
    )
    auto_collar_lift_degrees = Vector2Field(
        (-6.0, 15.0),
        min=-90.0,
        max=90.0,
        labels=("Lower", "Upper"),
        label="Lift Degrees",
        group=AUTO_COLLAR,
        help="Collar rotation at each of those angles.",
    )
    auto_collar_swing_angles = Vector2Field(
        (-45.0, 60.0),
        min=-89.0,
        max=89.0,
        labels=("Back", "Front"),
        label="Swing Angles",
        group=AUTO_COLLAR,
        help="Arm azimuth either side of the neutral guide at full falloff.",
    )
    auto_collar_swing_degrees = Vector2Field(
        (-6.0, 10.0),
        min=-90.0,
        max=90.0,
        labels=("Back", "Front"),
        label="Swing Degrees",
        group=AUTO_COLLAR,
        help="Collar rotation at each of those angles.",
    )
    auto_collar_interpolation = ChoiceField(
        "smooth",
        choices=("linear", "smooth", "spline"),
        label="Auto Collar Interpolation",
        group=AUTO_COLLAR,
        help="Only 'smooth' is free of a slope discontinuity: 'linear' kinks "
        "at the neutral and both limits, 'spline' kinks at both limits.",
    )

    def _lift_axis(self) -> ReachAxis:
        # Component order is (min, max), matching ReachAxis's first two and
        # last two arguments.
        return ReachAxis(*self.auto_collar_lift_angles, *self.auto_collar_lift_degrees)

    def _swing_axis(self) -> ReachAxis:
        return ReachAxis(
            *self.auto_collar_swing_angles, *self.auto_collar_swing_degrees
        )

    def validate(self) -> list[str]:
        """The base checks plus the auto-collar axis ranges."""
        problems = super().validate()
        if self.auto_collar:
            for label, axis in (
                ("lift", self._lift_axis()),
                ("swing", self._swing_axis()),
            ):
                try:
                    axis.validate(f"auto collar {label}")
                except ValueError as error:
                    problems.append(str(error))
        return problems

    # --------------------------------------------------------------- guides
    def draw_guides(self, guides) -> None:
        """Collar, shoulder, elbow and hand along X, with a bent elbow."""
        mult = guides.side_mult
        collar = guides.joint("collar", (2 * mult, 0, 0), radius=1.5)
        shoulder = guides.joint("shoulder", (5 * mult, 0, 0), parent=collar)
        elbow = guides.joint("elbow", (9 * mult, 0, -1), parent=shoulder)
        guides.joint("hand", (14 * mult, 0, 0), parent=elbow)
        # Where the wrist sits when the collar is at rest -- the auto-collar's
        # zero. Only the direction from `collar` matters, so sitting past the
        # hand costs nothing and keeps the guide selectable. The default guide
        # arm is already a T-pose, so the default neutral is the T-pose.
        guides.joint("neutral", (18 * mult, 0, 0), parent=collar, radius=0.8)

    # ---------------------------------------------------------------- build
    def build(self, rig) -> None:
        """IK/FK limb, limb lock, twist and the optional auto collar."""
        collar_guide = rig.guide("collar")
        limb_guides = rig.guides("shoulder", "elbow", "hand")
        size = _derive_size(limb_guides)

        socket = rig.socket("root", match=collar_guide)

        # Two places the lock can push, both inert pass-throughs otherwise.
        # `hang_from` carries the collar with it; `limb_from` moves only the
        # arm chain, leaving the clavicle on the chest. build_limb_lock owns
        # the translation of whichever one it targets, so only the other gets
        # a full constraint here.
        locks_collar = self.limb_lock and self.lock_from == "collar"
        hang_from = rig.group("lock", "collar", under="socket")
        hang_from.snap_to(socket)
        if not locks_collar:
            tm.MatrixConstraint.create(socket, hang_from, maintain_offset=True)

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
        tm.MatrixConstraint.create(hang_from, collar_ctrl.offset, maintain_offset=True)
        tm.MatrixConstraint.create(collar_ctrl, collar_jnt, maintain_offset=True)
        for channel in ("sx", "sy", "sz", "v"):
            plug = collar_ctrl[channel]
            plug.locked = True
            plug.visible = False

        # the limb -------------------------------------------------------------
        limb_from = rig.group("lock", "limb", under="rig")
        limb_from.snap_to(collar_ctrl.transform)
        if locks_collar or not self.limb_lock:
            tm.MatrixConstraint.create(collar_ctrl, limb_from, maintain_offset=True)

        limb = build_ikfk_limb(
            rig,
            limb_guides,
            parent=limb_from,
            bind_joints=bind_joints,
            soft_ik=True,  # never optional for an IK solution
            stretch=self.stretch,
            squash=self.squash,
            pole_pin=self.pole_pin,
            labels=("upper", "lower", "hand"),
        )
        if self.auto_collar:
            reach = build_reach(
                rig,
                collar_ctrl.offset,
                collar_ctrl.transform,
                hang_from,
                tuple(rig.guide("neutral").world_position),
                limb.ik_tweak.transform,
                limb.ik_control.transform,
                lift=self._lift_axis(),
                swing=self._swing_axis(),
                fk_controls=limb.fk_controls,
                switch_plug=limb.switch_plug,
                prefix="autoCollar",
                interpolation=self.auto_collar_interpolation,
                name="collar",
            )
            # Relative, so set_parent writes no compensation into the channels:
            # `align` already carries the collar's own orientation.
            collar_ctrl.transform.set_parent(reach.align, relative=True)

        if self.limb_lock:
            # Built last because it needs the limb's IK tweak; lock_root still
            # reads the raw socket, which is what keeps the graph acyclic.
            target, follows = (
                (hang_from, socket) if locks_collar else (limb_from, collar_ctrl)
            )
            build_limb_lock(
                rig,
                socket=socket,
                chain_root=limb.ik_joints[0],
                driver=limb.ik_tweak.transform,
                control=limb.ik_control,
                target=target,
                follows=follows,
            )

        rig.output("collar", collar_jnt)
        rig.output("upperarm", bind_joints[0])
        rig.output("lowerarm", bind_joints[1])
        rig.output("hand", bind_joints[2])
