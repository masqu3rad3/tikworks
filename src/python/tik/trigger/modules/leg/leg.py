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
    register_module,
)
from tik.trigger.systems.limb import (
    conventional_frames,
    derive_size,
    limb_control_names,
    limb_control_orients,
    limb_control_shapes,
    limb_pivot_controls,
)

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
#: hip-to-ankle distance. Only the direction matters to the reach network;
#: sitting beyond the ankle keeps the guide selectable rather than buried.
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
        # The IK control is a foot, not a cube. Overrides the limb default.
        "ik": "FootPrint",
        "fk_ball": "Circle",
        "heel": "CurvedArrow",
        "ball_spin": "Rotator",
        "toe": "CurvedArrow",
        "ball": "CurvedArrow",
        "toe_wiggle": "Arrow",
        "bank": "DualCurvedArrow",
    }
    control_orients = {
        **limb_control_orients(labels=LIMB_LABELS),
        "fk_ball": (0.0, 0.0, -90.0),
        # Shapes are authored flat in XZ with the normal on +Y. A roll pivot
        # turns about the foot frame's X, so its arrow wants the normal on X:
        # Rz(-90) maps +Y to +X. A spin turns about Z: Rx(90) maps +Y to +Z.
        # A wiggle turns about Y and needs no turn at all.
        #
        # Every foot control is `mirror="behaviour"` (the foot's own frame
        # is behaviour-mirrored, spec §6.3), so these DO get conjugated on
        # the right side, same as every other behaviour-mirrored control: a
        # shape authored for the left arrives rolled 180 degrees about X on
        # the mirrored frame, and the conjugation undoes it.
        "heel": (0.0, 0.0, -90.0),
        "toe": (0.0, 0.0, -90.0),
        "ball": (0.0, 0.0, -90.0),
        "bank": (0.0, 0.0, -90.0),
        "ball_spin": (90.0, 0.0, 0.0),
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
    roll_overlap = FloatField(
        10.0,
        min=0.0,
        label="Roll Overlap",
        group=FOOT,
        help="Degrees either side of rollBreak over which the ball hands off "
        "to the toe. 0 is a hard switch.",
    )

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
        guides.joint("bank_in", (1.2 * mult, 0.05, 1.3), parent=ankle)
        guides.joint("bank_out", (2.8 * mult, 0.05, 1.3), parent=ankle)

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
        """The deform skeleton. Limb, foot and automation land in Task 15."""
        hip_guide = rig.guide("hip")
        limb_guides = rig.guides(*LIMB_GUIDES)
        foot_guides = rig.guides("ball", "toe")

        rig.socket("root", match=hip_guide)

        # deform skeleton -- created in final position, never reparented -----
        hip_jnt = rig.bind_joint("hip", match=hip_guide)
        chain = [hip_jnt]
        parent_joint = hip_jnt
        for label, guide_node in zip(
            ("upperleg", "lowerleg", "foot", "ball", "toe"),
            [*limb_guides, *foot_guides],
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

        self._bind_chain = chain
        self._size = derive_size(limb_guides)
