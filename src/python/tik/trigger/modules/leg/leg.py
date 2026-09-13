"""Leg module: hip plus a single-IK-chain IK/FK leg with a reverse foot.

The arm's recipe down to the ankle, and then a second solver hierarchy
wrapped *around* it: the reverse foot's pivots sit upstream of the leg's own
IK handle, so rolling onto the toe drags the ankle, the knee and the hip with
it. The foot is not downstream of the limb.

Ribbons and twist live in their own modules. A twist attached to the
``upperleg`` output creates its joints as siblings of the shin, which is
exactly how engine twist bones are structured, so nothing here anticipates
them.
"""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import (
    BoolField,
    ChoiceField,
    FieldGroup,
    FloatField,
    GuideLayout,
    Input,
    Module,
    Vector2Field,
    register_module,
)
from tik.trigger.systems.foot import (
    build_foot_bank,
    build_foot_chains,
    build_foot_controls,
    build_foot_pivots,
    build_foot_proxies,
    build_foot_roll,
)
from tik.trigger.systems.limb import (
    build_limb_controls,
    build_limb_solve,
    conventional_frames,
    derive_size,
    limb_control_names,
    limb_control_orients,
    limb_control_shapes,
    limb_pivot_controls,
)
from tik.trigger.systems.limb_lock import build_limb_lock
from tik.trigger.systems.reach import ReachAxis, build_reach

LIMB_LOCK = FieldGroup("Limb Lock")
AUTO_HIP = FieldGroup("Auto Hip", collapsed=True)
FOOT = FieldGroup("Foot", collapsed=True)

#: The FK labels ``build()`` passes to the limb. Named once so the manifest
#: and the build cannot disagree.
LIMB_LABELS = ("upper", "lower", "foot")

#: The limb's own three guides, in chain order. The limb system never names a
#: guide, so the anchors for its pivot presets come from here.
LIMB_GUIDES = ("thigh", "knee", "ankle")

#: The reverse foot's controllers, ground up. ``systems/foot.py`` builds them
#: and the module declares them; the two must not drift.
FOOT_CONTROLS = ("heel", "ball_spin", "toe", "ball", "toe_wiggle", "bank")

#: How far past the ankle the ``neutral`` guide sits, as a multiple of the
#: hip-to-ankle distance. Only the direction matters to the reach network,
#: which reads the hip-to-neutral direction and nothing else -- the
#: multiplier itself is shared with the arm's own ``NEUTRAL_REACH`` for
#: consistency across limb modules, not chosen for where it lands. Unlike
#: the arm, where beyond-the-hand sits in open space, on the leg this puts
#: the guide below the floor plane; harmless, since its position is never
#: read as a rest-pose landmark, only the ray from the hip through it.
NEUTRAL_REACH = 1.4


@register_module("leg", category="limbs")
class Leg(Module):
    """Biped leg: hip, thigh, knee, ankle, ball, toe, and a reverse foot."""

    label = "Leg"
    #: Only the ankle's rotation reaches the rig: the chain is oriented by
    #: convention at build time, so rolling the hip, thigh or knee guide
    #: changes nothing. The ankle's is what aligns the foot to the model.
    guides = GuideLayout(
        "hip",
        "thigh",
        "knee",
        "ankle",
        "ball",
        "toe",
        "heel",
        "tip",
        "bank_in",
        "bank_out",
        "neutral",
        reference=("heel", "tip", "bank_in", "bank_out", "neutral"),
        oriented=("ankle",),
    )
    inputs = (Input("root", primary=True, help="Where the hip hangs (pelvis/body)"),)
    outputs = ("hip", "upperleg", "lowerleg", "foot", "ball", "toe")
    controls = (
        "thigh",
        *limb_control_names(labels=LIMB_LABELS),
        "fk_ball",
        *FOOT_CONTROLS,
    )
    control_shapes = {
        "thigh": "CurvedCircle",
        **limb_control_shapes(labels=LIMB_LABELS),
        # No "ik" entry: the rigger wants a plain cube, which is already
        # ``limb_control_shapes``'s default -- no override needed.
        "fk_ball": "Circle",
        # The foot controls follow the shape vocabulary in AI/coding_rules.md:
        # a pin where the pivot's location must be visible, then one arc per
        # free rotation axis. `toe_wiggle` is a toe, so it takes the pin.
        "heel": "DualCurvedArrow",
        "ball_spin": "CurvedArrow",
        "toe": "DualCurvedArrow",
        "ball": "DualCurvedArrow",
        "toe_wiggle": "SpherePin",
        "bank": "CurvedArrow",
    }
    control_orients = {
        **limb_control_orients(labels=LIMB_LABELS),
        "fk_ball": (0.0, 0.0, -90.0),
        # Per the shape vocabulary in AI/coding_rules.md, a shape's
        # distinguished axis means different things per shape, so these are
        # derived from the SHAPE as well as the control's free axes. In the
        # foot frame X is side, Y is up, Z is forward.
        #
        # `DualCurvedArrow` is two arcs at right angles: its unused axis is
        # +Y, and that is what goes onto the control's LOCKED axis, leaving
        # the two arcs on the two free ones.
        #   heel / toe  -- free X (roll) and Y (spin), locked Z
        #                  -> Rx(90) puts the unused +Y onto Z
        #   ball        -- free X (roll) and Z (lean), locked Y
        #                  -> unused +Y is already on Y, no turn
        #
        # `CurvedArrow`'s distinguished axis is its NORMAL, on +Z, and it
        # goes onto the single rotation axis.
        #   ball_spin   -- turns about Y -> Rx(-90) maps +Z onto +Y
        #   bank        -- turns about Z -> already there, no turn
        #
        # `SpherePin`'s stalk is +Y and aligns to the joint's UP vector, not
        # to a rotation axis, so it never takes a turn at all. Giving
        # `toe_wiggle` the roll correction would lay the pin flat along the
        # foot instead of standing it up where the pivot can be seen.
        #
        # Every foot control is `mirror="behaviour"` (the foot's own frame is
        # behaviour-mirrored, spec section 6.3), so these DO get conjugated on
        # the right side: a shape authored for the left arrives rolled 180
        # degrees about X on the mirrored frame, and the conjugation undoes it.
        "heel": (90.0, 0.0, 0.0),
        "toe": (90.0, 0.0, 0.0),
        "ball_spin": (-90.0, 0.0, 0.0),
    }
    #: No entry for ``ik``: the reverse foot already owns that control's
    #: pivot, and offering both would give the animator two pivots on one
    #: node whose corrections do not compose. The foot controls are pivots
    #: themselves, so a movable pivot on one is meaningless.
    pivot_controls = {
        "thigh": "hip",
        **{
            role: guide
            for role, guide in limb_pivot_controls(
                labels=LIMB_LABELS, guides=LIMB_GUIDES
            ).items()
            if role != "ik"
        },
        "fk_ball": "ball",
    }

    @classmethod
    def pivot_exempt_for_copy(cls, settings=None):
        """``ik`` and every reverse-foot control, on the record.

        ``ik`` is exempt because the reverse foot already owns that control's
        pivot -- offering a second would give the animator two pivots on one
        node whose corrections do not compose. Every ``FOOT_CONTROLS`` role is
        exempt because it *is* a pivot: a heel or toe roll control already
        pivots the foot from a fixed point, so a movable pivot on top of it is
        meaningless rather than merely unbuilt.
        """
        return ("ik", *FOOT_CONTROLS)

    stretch = BoolField(True, help="Build the stretch network")
    squash = BoolField(True, help="Build the compress-side network")
    pole_pin = BoolField(False, help="Lock the knee to the pole control")
    lock_from = ChoiceField(
        "thigh",
        choices=("thigh", "hip"),
        label="Lock From",
        group=LIMB_LOCK,
        help="'thigh' displaces the leg chain and leaves the hip on the "
        "pelvis; 'hip' carries the hip joint along too",
    )
    limb_lock = BoolField(
        True,
        label="Limb Lock",
        group=LIMB_LOCK,
        help="Hold the thigh-to-foot distance while the foot anchors. "
        "Inert until the animator raises limbLock.",
    )
    auto_hip = BoolField(True, help="Build the auto-hip network", group=AUTO_HIP)
    auto_hip_lift_angles = Vector2Field(
        (-55.0, 70.0),
        min=-89.0,
        max=89.0,
        labels=("Lower", "Upper"),
        label="Lift Angles",
        group=AUTO_HIP,
        help="Leg elevation either side of the neutral guide at full falloff. "
        "Both stay inside +/-89: the driver's off-plane angles saturate "
        "at 90, so a wider limit is never reached.",
    )
    auto_hip_lift_degrees = Vector2Field(
        (-4.0, 12.0),
        min=-90.0,
        max=90.0,
        labels=("Lower", "Upper"),
        label="Lift Degrees",
        group=AUTO_HIP,
        help="Hip rotation at each of those angles.",
    )
    auto_hip_swing_angles = Vector2Field(
        (-40.0, 55.0),
        min=-89.0,
        max=89.0,
        labels=("Back", "Front"),
        label="Swing Angles",
        group=AUTO_HIP,
        help="Leg azimuth either side of the neutral guide at full falloff.",
    )
    auto_hip_swing_degrees = Vector2Field(
        (-4.0, 8.0),
        min=-90.0,
        max=90.0,
        labels=("Back", "Front"),
        label="Swing Degrees",
        group=AUTO_HIP,
        help="Hip rotation at each of those angles.",
    )
    auto_hip_interpolation = ChoiceField(
        "smooth",
        choices=("linear", "smooth", "spline"),
        label="Auto Hip Interpolation",
        group=AUTO_HIP,
        help="Only 'smooth' is free of a slope discontinuity: 'linear' kinks "
        "at the neutral and both limits, 'spline' kinks at both limits.",
    )
    roll_overlap = FloatField(
        10.0,
        min=0.0,
        label="Roll Overlap",
        group=FOOT,
        help="Degrees either side of rollBreak over which the ball hands off "
        "to the toe. 0 is a hard switch.",
    )

    def _lift_axis(self) -> ReachAxis:
        # Component order is (min, max), matching ReachAxis's first two and
        # last two arguments.
        return ReachAxis(*self.auto_hip_lift_angles, *self.auto_hip_lift_degrees)

    def _swing_axis(self) -> ReachAxis:
        return ReachAxis(*self.auto_hip_swing_angles, *self.auto_hip_swing_degrees)

    def validate(self) -> list[str]:
        """The base checks plus the auto-hip axis ranges."""
        problems = super().validate()
        if self.auto_hip:
            for label, axis in (
                ("lift", self._lift_axis()),
                ("swing", self._swing_axis()),
            ):
                try:
                    axis.validate("auto hip %s" % label)
                except ValueError as error:
                    problems.append(str(error))
        return problems

    def draw_guides(self, guides) -> None:
        """A rest stance: the chain hangs down, knee pushed forward in +Z.

        The knee's +Z is what makes the bend plane unambiguous -- the same job
        the arm's elbow does with -1 in Z. The four foot markers are siblings
        of the ankle rather than links in a chain, and are reference guides,
        so none of them draws a bone.
        """
        mult = guides.side_mult
        hip_at = (1.0 * mult, 10.4, 0.0)
        ankle_at = (2.0 * mult, 1.0, 0.0)
        hip = guides.joint("hip", hip_at)
        thigh = guides.joint("thigh", (2.0 * mult, 9.6, 0.0), parent=hip)
        knee = guides.joint("knee", (2.0 * mult, 5.3, 0.45), parent=thigh)
        ankle = guides.joint("ankle", ankle_at, parent=knee)
        ball = guides.joint("ball", (2.0 * mult, 0.25, 1.3), parent=ankle)
        guides.joint("toe", (2.0 * mult, 0.05, 2.4), parent=ball)

        # Position-only markers around the shoe. Siblings of the ankle: they
        # describe the foot's footprint, not a chain through it.
        guides.joint("heel", (2.0 * mult, 0.05, -0.6), parent=ankle)
        guides.joint("tip", (2.0 * mult, 0.05, 2.8), parent=ankle)
        # `bank_out` is the marker NEARER the body midline and `bank_in` the
        # one farther out. That reads backwards until you follow the pivots:
        # the stack is `bank_in > bank_out`, and rolling the foot onto an edge
        # means pivoting about the edge that stays on the ground while the
        # opposite one lifts. The legacy module placed them this way too
        # (`bankout` at 4*side, `bankin` at 6*side, with the leg at 5*side).
        guides.joint("bank_in", (2.8 * mult, 0.05, 1.3), parent=ankle)
        guides.joint("bank_out", (1.2 * mult, 0.05, 1.3), parent=ankle)

        # Where the ankle sits when the hip is at rest -- the auto-hip's zero.
        # Derived from the ankle rather than typed as a triple: the reach
        # network measures the angle between this direction and the ankle's,
        # and at the guide pose that angle must be exactly zero.
        neutral_at = tuple(
            start + (end - start) * NEUTRAL_REACH
            for start, end in zip(hip_at, ankle_at)
        )
        guides.joint("neutral", neutral_at, parent=hip)

    def build(self, rig) -> None:
        """Bind skeleton, limb, reverse foot, auto hip and limb lock.

        The limb is built in two phases with the reverse foot between them
        (``build_limb_controls`` / ``build_limb_solve``): the foot's pivot
        stack is wired upstream of the limb's own IK handle, so rolling onto
        the toe drags the ankle, the knee and the hip with it.
        """
        hip_guide = rig.guide("hip")
        limb_guides = rig.guides(*LIMB_GUIDES)
        chain_foot_guides = rig.guides("ball", "toe")

        socket = rig.socket("root", match=hip_guide)

        # deform skeleton -- created in final position, never reparented -----
        hip_jnt = rig.bind_joint("hip", match=hip_guide)
        chain = [hip_jnt]
        parent_joint = hip_jnt
        for label, guide_node in zip(
            ("upperleg", "lowerleg", "foot", "ball", "toe"),
            [*limb_guides, *chain_foot_guides],
        ):
            joint = rig.bind_joint(label, parent=parent_joint, match=guide_node)
            chain.append(joint)
            parent_joint = joint

        # The deform skeleton takes the convention, not the guides' rotations:
        # X to the next joint, Y up. The guides stay world-aligned, which is
        # load-bearing: `build_reach` derives its mirror correction by
        # comparing its own frame's Z against the socket's, and the socket is
        # matched to the hip guide, so orienting that guide would make both
        # terms flip together and silently cancel the correction.
        frames = conventional_frames(rig, [joint.world_position for joint in chain])
        # Position *and* rotation, root first: re-orienting a joint rotates
        # everything under it, so each child has to be put back after its
        # parent moves.
        for joint, frame in zip(chain, frames):
            joint.align_to(frame)

        # The ankle is the exception, and the only guide whose rotation is
        # read: it is what aligns the foot to the model.
        chain[3].align_to(limb_guides[-1], position=False)
        # ...and it has children, which the arm's hand does not. Step 3 just
        # rotated the ball and the toe with it, so the ball goes back onto
        # its conventional frame. Omitting this is the single easiest
        # mistake here and it is invisible until a rigger rolls the ankle
        # guide.
        chain[4].align_to(frames[4])
        # The toe needs no line of its own. `align_to` is an absolute
        # world-space reset, not a relative nudge, so restoring the ball
        # above puts every untouched descendant back with it for free: the
        # toe's own local transform was never disturbed, only its ancestor's
        # was, and the ancestor is now exactly where it started. This holds
        # only because the ball's correction above is a *full* one -- were
        # it ever narrowed to `position=False` like the ankle's, the toe
        # would stop being restored and would need its own align_to back.

        tm.delete(frames[0].long_name)

        for name, joint in zip(
            ("hip", "upperleg", "lowerleg", "foot", "ball", "toe"), chain
        ):
            rig.output(name, joint)

        size = derive_size(limb_guides)

        # Two places the lock can push, both inert pass-throughs otherwise.
        # `hang_from` carries the hip with it; `limb_from` moves only the leg
        # chain, leaving the pelvis alone. build_limb_lock owns the
        # translation of whichever one it targets, so only the other gets a
        # full constraint here.
        locks_hip = self.limb_lock and self.lock_from == "hip"
        hang_from = rig.group("lock", "hip", under="socket")
        hang_from.snap_to(socket)
        if not locks_hip:
            tm.MatrixConstraint.create(socket, hang_from, maintain_offset=True)

        # hip control ------------------------------------------------------
        thigh_ctrl = rig.controller(
            "thigh", size=size, match=chain[0], mirror="behaviour"
        )
        tm.MatrixConstraint.create(hang_from, thigh_ctrl.offset, maintain_offset=True)
        tm.MatrixConstraint.create(thigh_ctrl, chain[0], maintain_offset=True)
        for channel in ("sx", "sy", "sz", "v"):
            plug = thigh_ctrl[channel]
            plug.locked = True
            plug.visible = False

        limb_from = rig.group("lock", "limb", under="rig")
        limb_from.snap_to(thigh_ctrl.transform)
        if locks_hip or not self.limb_lock:
            tm.MatrixConstraint.create(thigh_ctrl, limb_from, maintain_offset=True)

        # the limb, opened in the middle for the foot ----------------------
        limb = build_limb_controls(
            rig,
            limb_guides,
            parent=limb_from,
            controller_size=size,
            labels=LIMB_LABELS,
        )

        foot_guides = {
            role: rig.guide(role)
            for role in ("ankle", "ball", "toe", "heel", "tip", "bank_in", "bank_out")
        }
        foot = build_foot_pivots(
            rig, parent=limb.ik_tweak.transform, guides=foot_guides
        )
        build_foot_controls(rig, foot, size=size * 0.35, parent=limb.ik_control)
        build_foot_bank(rig, foot)

        # The solve follows the bottom of the pivot stack, not the tweak:
        # that is what makes rolling onto the toe drag the ankle, the knee
        # and the hip with it.
        build_limb_solve(
            rig,
            limb,
            driver=foot.ankle_driver,
            bind_joints=chain[1:4],
            soft_ik=True,  # never optional for an IK solution
            stretch=self.stretch,
            squash=self.squash,
            pole_pin=self.pole_pin,
        )

        build_foot_chains(
            rig,
            foot,
            limb,
            guides=foot_guides,
            bind_joints=chain[4:6],
            size=size * 0.5,
        )
        build_foot_proxies(rig, foot, limb.ik_control)
        build_foot_roll(rig, foot, limb.ik_control, overlap=float(self.roll_overlap))

        if self.auto_hip:
            reach = build_reach(
                rig,
                thigh_ctrl.offset,
                thigh_ctrl.transform,
                hang_from,
                tuple(rig.guide("neutral").world_position),
                limb.ik_tweak.transform,
                limb.ik_control.transform,
                lift=self._lift_axis(),
                swing=self._swing_axis(),
                fk_controls=limb.fk_controls,
                switch_plug=limb.switch_plug,
                prefix="autoHip",
                interpolation=self.auto_hip_interpolation,
                name="hip",
            )
            # Relative, so set_parent writes no compensation into the
            # channels: `align` already carries the hip's own orientation.
            thigh_ctrl.transform.set_parent(reach.align, relative=True)

        if self.limb_lock:
            # Built last because it needs the limb's IK tweak; lock_root
            # still reads the raw socket, which keeps the graph acyclic.
            target, follows = (
                (hang_from, socket) if locks_hip else (limb_from, thigh_ctrl)
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
