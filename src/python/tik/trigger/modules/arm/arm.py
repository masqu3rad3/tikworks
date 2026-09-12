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
from tik.trigger.systems.limb import (
    _derive_size,
    build_ikfk_limb,
    limb_control_names,
    limb_control_orients,
    limb_control_shapes,
    limb_pivot_controls,
)
from tik.trigger.systems.limb_lock import build_limb_lock
from tik.trigger.systems.reach import ReachAxis, build_reach

LIMB_LOCK = FieldGroup("Limb Lock")
AUTO_COLLAR = FieldGroup("Auto Collar", collapsed=True)

#: The FK labels ``build()`` passes to ``build_ikfk_limb``. Named once so the
#: manifest and the build cannot disagree.
LIMB_LABELS = ("upper", "lower", "hand")

#: The limb's own three guides, in chain order. The limb system never names a
#: guide, so the anchors for its pivot presets come from here.
LIMB_GUIDES = ("shoulder", "elbow", "hand")


def _conventional_frames(rig, positions):
    """A throwaway chain on the convention, to read orientations off.

    X to the next joint, Y up -- so in a T-pose Y is up for *every* joint on
    *both* sides, which is what lets the arm bend on a single rotation.

    No ``reverse_aim`` / ``reverse_up``. ``_build_chains`` passes those for the
    puppet because a mirrored-behaviour limb needs a negative ``translateX``
    for ``ChainLengths`` to read; the deform skeleton has no such requirement,
    and flipping its Y would put the right arm's bend axis upside down.

    Read off a throwaway rather than oriented in place: ``cmds.joint
    -orientJoint`` silently *skips* a joint that has non-zero rotations (a
    warning, no error), and ``match=`` leaves the guide's rotation exactly
    there. Copying the world rotation also keeps the orientation in ``rotate``
    with ``jointOrient`` at zero, which is where ``match=`` always put it.
    """
    source = tm.Joint.chain(
        [tuple(position) for position in positions],
        name_pattern=rig.name("convention", "src{index}", suffix="jnt"),
        parent=rig.groups.rig,
        orient=False,
    )
    tm.Joint.orient_chain(source, aim_axis="x", up_axis="y")
    return source


#: How far past the hand the ``neutral`` guide sits, as a multiple of the
#: collar-to-hand distance. Only the direction matters to the auto-collar;
#: sitting beyond the hand keeps the guide selectable rather than buried.
NEUTRAL_REACH = 1.4


@register_module("arm", category="limbs")
class Arm(Module):
    """Biped arm: collar, shoulder, elbow, hand."""

    label = "Arm"
    #: Only the hand's rotation reaches the rig: the chain is oriented by
    #: convention at build time, so rolling the collar, shoulder or elbow
    #: guide changes nothing -- and the Designer does not offer an axis on a
    #: guide whose orientation it would then ignore. The hand's is what
    #: aligns the wrist to the model.
    guides = GuideLayout(
        "collar",
        "shoulder",
        "elbow",
        "hand",
        "neutral",
        reference=("neutral",),
        oriented=("hand",),
    )
    inputs = (Input("root", primary=True, help="Where the collar hangs (chest/body)"),)
    outputs = ("collar", "upperarm", "lowerarm", "hand")
    controls = ("collar", *limb_control_names(labels=LIMB_LABELS))
    control_shapes = {
        "collar": "CurvedCircle",
        **limb_control_shapes(labels=LIMB_LABELS),
    }
    control_orients = limb_control_orients(labels=LIMB_LABELS)
    pivot_controls = {
        "collar": "collar",
        **limb_pivot_controls(labels=LIMB_LABELS, guides=LIMB_GUIDES),
    }
    #: The hand pivot has always been the animator's to drag, so the tick
    #: ships on. Its three preset rows below are the named positions; the
    #: tick is what keeps the pivot a controller rather than a null.
    movable_pivots = Module.movable_pivots.with_default(["ik"])
    pivot_presets = Module.pivot_presets.with_default(
        # Proximal to distal: the order the preset fan walks, so the markers
        # land anatomically rather than arbitrarily.
        [{"control": "ik", "label": label} for label in ("wrist", "ball", "tip")]
    )

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
        """Collar, then an A-pose arm: the chain hangs 45 degrees below level.

        A-pose rather than T, because it gives the better shoulder
        deformation. The collar stays level -- a clavicle is roughly
        horizontal in any pose -- so the A starts at the shoulder.

        The elbow's -1 in Z survives the rotation untouched, because turning
        about Z does not change Z: the pole direction stays behind the arm
        with no compensation anywhere.
        """
        mult = guides.side_mult
        collar_at = (2.0 * mult, 0.0, 0.0)
        hand_at = (11.4 * mult, -6.4, 0.0)
        collar = guides.joint("collar", collar_at)
        shoulder = guides.joint("shoulder", (5 * mult, 0, 0), parent=collar)
        elbow_at = (7.8 * mult, -2.8, -1)
        elbow = guides.joint("elbow", elbow_at, parent=shoulder)
        hand = guides.joint("hand", hand_at, parent=elbow)
        # Where the wrist sits when the collar is at rest -- the auto-collar's
        # zero. Only the *direction* from `collar` matters, so sitting past the
        # hand costs nothing and keeps the guide selectable.
        #
        # Derived from the hand rather than typed as a triple: the reach
        # network measures the angle between this direction and the wrist's,
        # and at the guide pose that angle must be exactly zero or no scalar
        # value leaves the bind pose alone. A hand-written triple is only
        # approximately collinear -- rounding the A-pose to one decimal put it
        # 0.006 out, which is 60x the tolerance
        # test_bind_pose_is_exact_with_the_automation_full_on allows.
        neutral_at = tuple(
            start + (end - start) * NEUTRAL_REACH
            for start, end in zip(collar_at, hand_at)
        )
        guides.joint("neutral", neutral_at, parent=collar)

        # The hand guide starts on the convention -- X down the arm, Y up -- so
        # a rigger who never touches it still gets a conventional wrist. This
        # is the same frame the lowerarm gets at build time (aimed at the hand,
        # world up +Y), so the two agree.
        #
        # Only the hand. The rest deliberately stay world-aligned: their
        # rotation is ignored at build time, and the collar's is load-bearing
        # in a way that is easy to miss -- `build_reach` derives its mirror
        # correction by comparing its own frame's Z against the socket's, and
        # the socket is matched to the collar guide. Orienting that guide makes
        # both terms flip together, so the correction silently cancels and the
        # right arm's swing inverts.
        beyond = tm.Transform.create(name="arm_handAim_tmp")
        beyond.world_position = tuple(
            far + (far - near) for far, near in zip(hand_at, elbow_at)
        )
        hand.aim_at(beyond, aim_vector=(1, 0, 0), up_vector=(0, 1, 0))
        beyond.delete()

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

        # The deform skeleton takes the convention, not the guides' rotations:
        # X to the next joint, Y up. `_build_chains` has always built the
        # puppet from guide *positions* and oriented it this way, so the two
        # used to disagree -- twist still documents an arm's lowerarm X being
        # only 0.98 aligned with the direction to the hand.
        #
        # The *guides* are deliberately left world-aligned. `build_reach`
        # derives its mirror correction by comparing its frame's Z against the
        # socket's, and the socket is matched to the collar guide -- so that
        # comparison only resolves a side while the guide's rotation is
        # identity. Orienting the guides makes both terms flip together and
        # the correction is silently lost on the right arm.
        frames = _conventional_frames(
            rig,
            [collar_guide.world_position]
            + [guide.world_position for guide in limb_guides],
        )
        # Position *and* rotation, root first: re-orienting a joint rotates
        # everything under it, so each child has to be put back after its
        # parent moves. The throwaway chain sits on the guide positions, so
        # aligning to it restores the pose exactly as it corrects the frame.
        for joint, frame in zip([collar_jnt, *bind_joints], frames):
            joint.align_to(frame)
        # The hand is the exception, and the only guide whose rotation is read:
        # it is what aligns the wrist to the model.
        bind_joints[-1].align_to(limb_guides[-1], position=False)
        tm.delete(frames[0].long_name)

        # collar ---------------------------------------------------------------
        # The controller lives in control_grp and is driven by the socket rather
        # than parented under it: control_grp holds nothing but controllers and
        # their offset groups.
        collar_ctrl = rig.controller(
            "collar",
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
            labels=LIMB_LABELS,
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
