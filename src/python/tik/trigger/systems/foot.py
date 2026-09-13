"""Reverse foot: a pivot stack upstream of the leg's own IK handle.

The foot is not downstream of the limb, it is wrapped around it. Rolling onto
the toe has to drag the ankle -- and therefore the knee, and therefore the hip
-- with it, which means these pivots sit between the IK control and the IK
handle. ``systems/limb.py`` opens in the middle for exactly this.

Two parallel hierarchies, and they stay in lockstep by construction::

    rig_grp                          control_grp
      root      <- ik_tweak            bank_ctrl.offset  <- ik_tweak
        bank_in                          bank_ctrl
          bank_out                         heel_ctrl
            heel                             ball_spin_ctrl
              ball_spin                        toe_ctrl
                toe                              ball_ctrl
                  ball_roll                      toe_wiggle_ctrl
                    ankle_driver
                  toe_wiggle

Each controller sits at its pivot's position with the same ancestor chain, so
it inherits its ancestors' rotation exactly as its pivot does. No constraint
runs between the two and no cycle is possible. ``bank`` is the one exception
and §6.4 of the spec says why.

**The frame is behaviour-mirrored, and that is what needs no sign rule
anywhere else.** A frame aimed heel-to-tip with the ankle as up, built
naively from each foot's own geometry, does *not* come back as a plain
mirror on the right side: the aim and up axes mirror cleanly (they come
from point differences and a Gram-Schmidt, both reflection-equivariant),
but the third axis is their cross product, and a reflection negates a cross
product one extra time (``(Ma) x (Mb) = -M(a x b)``). So a naive frame's
``rx`` ends up same-signed between feet, while ``ry``/``rz`` end up
sign-flipped relative to what mirrored motion needs -- reproducing the
legacy's exemption pattern (``hRoll``/``tRoll``/``bank`` escaped
``sideMult``; every ``rotateY``/``rotateZ`` driver took it) exactly, not by
coincidence.

The unique fix -- proven in §6.3 of the spec, not merely chosen -- is to
require the mirrored frame to reproduce mirrored motion for *every*
rotation, which forces ``F_R = -M F_L = Rx(180) . F_L``: the *behaviour*
mirror, the same "180 degree roll about X" this repo already uses for
mirrored joints (``mirror_orient`` in ``tik/trigger/maya/rig.py``). Built by
aiming local ``-Z``/``-Y`` instead of ``+Z``/``+Y`` on the mirrored side
(below), it is a proper rotation (``det = +1``) with nothing for
``jointOrient`` to choke on, and it is what makes every channel connection
in this file signless: no side term on the bank clamps, none on the
auto-roll, none anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import tik.maya as tm

#: Pivot roles, in creation order. Nesting is each on the one before it,
#: except ``toe_wiggle``, which is a second child of ``toe``.
PIVOTS = (
    "bank_in",
    "bank_out",
    "heel",
    "ball_spin",
    "toe",
    "ball_roll",
    "toe_wiggle",
)

#: Which marker each pivot sits on.
PIVOT_GUIDES = {
    "bank_in": "bank_in",
    "bank_out": "bank_out",
    "heel": "heel",
    "ball_spin": "ball",
    "toe": "tip",
    "ball_roll": "ball",
    "toe_wiggle": "ball",
}


@dataclass
class FootResult:
    """Everything the leg needs after the foot is built."""

    frame: object = None
    root: object = None
    pivots: dict = field(default_factory=dict)
    ankle_driver: object = None
    controls: dict = field(default_factory=dict)
    ball_joints: list = field(default_factory=list)
    toe_joints: list = field(default_factory=list)


def foot_frame(rig, guides: dict, *, parent=None, name: str = "foot"):
    """A static frame aimed heel to tip, with the ankle as up.

    Built from the foot's own geometry rather than from a side convention.
    On the mirrored side, the aim and up vectors are negated rather than
    left alone: aiming local ``-Z`` at the tip and upping on ``-Y`` lands the
    frame on the *behaviour* mirror of the unmirrored side (``F_R = -M F_L``,
    §6.3 of the spec) rather than the naive mirror a plain ``aim_at`` would
    give, which is what lets every channel connection built on this frame go
    in with no side term. ``aim_at`` bakes plain rotation values, so the
    frame is static once created.
    """
    frame = tm.Transform.create(
        name=rig.name(name, "frame", suffix="grp"),
        parent=parent.long_name if parent is not None else rig.groups.rig.long_name,
    )
    frame.snap_to(guides["heel"], rotation=False)
    aim, up = ((0, 0, -1), (0, -1, 0)) if rig.side_mult < 0 else ((0, 0, 1), (0, 1, 0))
    frame.aim_at(
        guides["tip"],
        aim_vector=aim,
        up_vector=up,
        world_up_object=guides["ankle"],
    )
    return frame


def build_foot_pivots(rig, *, parent, guides: dict, name: str = "foot") -> FootResult:
    """Build the reverse-foot pivot stack under ``parent``.

    Args:
        rig: The module's ``ModuleRig``.
        parent: What the stack rides -- the limb's IK tweak, or a group
            constrained to it.
        guides: Guide nodes keyed by role. Needs ``ankle``, ``ball``,
            ``heel``, ``tip``, ``bank_in`` and ``bank_out``.
        name: Extra name token.

    Returns:
        A :class:`FootResult` with ``frame``, ``root``, ``pivots`` and
        ``ankle_driver`` filled. Pass ``ankle_driver`` to
        ``build_limb_solve(driver=)``.
    """
    result = FootResult()
    result.frame = foot_frame(rig, guides, name=name)

    result.root = rig.group(name, "root", under="rig")
    result.root.snap_to(parent)
    # The frame's rotation, not the driver's: every other pivot ends up with
    # the frame's world rotation under a sibling that already has it, so its
    # local rotate is zero. ``bank_in`` is the exception -- its parent is
    # ``root`` -- so ``root`` must carry the frame's rotation too, or
    # ``bank_in``'s rest-pose local rotate holds the frame-vs-driver delta
    # and popping the foot the moment §6.2 connects a channel into it.
    # ``maintain_offset=True`` on the constraint below absorbs the
    # difference between this and the driver's own rotation.
    result.root.align_to(result.frame, position=False)
    tm.MatrixConstraint.create(parent, result.root, maintain_offset=True)

    branch = result.root
    for role in PIVOTS:
        # toe_wiggle is a second child of toe, not a link below ball_roll:
        # it carries the ball and toe handles, so it must bend the toes
        # without moving the leg.
        under = result.pivots["toe"] if role == "toe_wiggle" else branch
        pivot = rig.group(name, role, under=under)
        pivot.snap_to(guides[PIVOT_GUIDES[role]], rotation=False)
        # Position from the marker, rotation from the shared frame. This is
        # the whole of §6.3.
        pivot.align_to(result.frame, position=False)
        result.pivots[role] = pivot
        if role != "toe_wiggle":
            branch = pivot

    # What the limb solve follows.
    result.ankle_driver = rig.group(
        name, "ankleDriver", under=result.pivots["ball_roll"]
    )
    result.ankle_driver.snap_to(guides["ankle"], rotation=False)
    result.ankle_driver.align_to(parent, position=False)
    return result


#: Which controller channel drives which pivot channel. The single place the
#: mapping lives -- the proxy names in ``PROXIES`` key off it, so a channel
#: cannot be wired one way and proxied another.
CONTROL_CHANNELS = {
    "bank": {"rotateX": "bank_in"},  # special-cased: two clamped pivots
    "heel": {"rotateX": "heel", "rotateY": "heel"},
    "ball_spin": {"rotateZ": "ball_spin"},
    "toe": {"rotateX": "toe", "rotateY": "toe"},
    "ball": {"rotateY": "ball_roll", "rotateZ": "ball_roll"},
    "toe_wiggle": {"rotateY": "toe_wiggle"},
}

#: Controller nesting, outermost first. Matches the pivot stack so the two
#: hierarchies inherit the same rotation without a constraint between them.
CONTROL_CHAIN = ("bank", "heel", "ball_spin", "toe", "ball", "toe_wiggle")

#: Which PIVOT each controller co-locates with. Pivot roles, not guide
#: roles: the controller has to land exactly where its twin is, and the
#: pivots have already resolved every marker.
CONTROL_GUIDES = {
    "bank": "ball_roll",
    "heel": "heel",
    "ball_spin": "ball_spin",
    "toe": "toe",
    "ball": "ball_roll",
    "toe_wiggle": "toe_wiggle",
}


def build_foot_controls(
    rig,
    result: FootResult,
    *,
    size: float,
    guides: Optional[dict] = None,
    parent=None,
    name: str = "foot",
) -> FootResult:
    """Build the controller chain that mirrors the pivot stack.

    Every control is ``mirror="behaviour"``: the foot's frame is itself
    behaviour-mirrored (``F_R = Rx(180) . F_L``, spec §6.3), and a control
    born from ``match=`` on a pivot inherits that pivot's frame exactly --
    so the controls are behaviour-mirrored for real, not by declaration.
    That is what lets the channel sums below carry no side term: the sign
    the legacy multiplier table used to supply is already in the frame.

    ``match=result.pivots[CONTROL_GUIDES[role]]`` gets position *and*
    orientation from the pivot in one step -- ``rig.controller`` applies
    ``match`` before creating the offset group, so the offset group is
    what ends up carrying the pivot's placement, not the control fighting
    its own parent for it.

    ``tier="secondary"`` puts all six behind the rig's ``visibilities_ctrl``,
    so an animator who prefers the proxy attributes never sees them.
    """
    guides = guides if guides is not None else {}
    under = parent if parent is not None else rig.groups.control
    for role in CONTROL_CHAIN:
        control = rig.controller(
            role,
            size=size,
            parent=under,
            match=result.pivots[CONTROL_GUIDES[role]],
            mirror="behaviour",
            tier="secondary",
        )
        for channel in ("tx", "ty", "tz", "sx", "sy", "sz", "v"):
            plug = control[channel]
            plug.locked = True
            plug.visible = False
        result.controls[role] = control
        under = control

    # The outermost control rides what the pivot stack rides.
    tm.MatrixConstraint.create(
        result.root, result.controls[CONTROL_CHAIN[0]].offset, maintain_offset=True
    )

    for role, channels in CONTROL_CHANNELS.items():
        if role == "bank":
            continue  # two clamped pivots, wired in build_foot_bank
        control = result.controls[role]
        for channel, pivot_role in channels.items():
            summed = control.offset[channel] + control.transform[channel]
            summed >> result.pivots[pivot_role][channel]
    return result


def build_foot_chains(
    rig,
    result: FootResult,
    limb_result,
    *,
    guides: dict,
    bind_joints,
    size: float,
    name: str = "foot",
) -> FootResult:
    """Extend both puppet chains with a ball and a toe, and blend them.

    The limb solves three joints; a foot has five. The IK side does **not**
    start its two SC handles on ``limb_result.ik_joints[-1]``: that joint's
    rotation is already the output of the limb's own
    ``MatrixConstraint(driver, ik_joints[-1], skip_translate="xyz",
    skip_scale="xyz")`` (``build_limb_solve``), and a second solve rooted
    there would contend with it for the same channels. Instead a fresh
    ``ik_ankle`` joint is created *parented under* ``result.ankle_driver`` --
    upstream of the limb's solve, where the reverse foot's pivot stack
    already lives -- and both SC handles run inside that new joint:
    ``ik_ankle -> ik_ball`` and ``ik_ball -> ik_toe``. The limb's RP chain is
    left entirely alone; nothing here writes to it.

    Every created joint under a non-identity parent gets its world position
    set explicitly (``.world_position = ...``) rather than through
    ``Joint.create(position=...)``, which sets local *translate* -- correct
    only when the parent is at the origin, which none of these are.

    The two extra joints take the same ``ikFk`` switch the limb made, so one
    value covers the whole leg and there is no second switch for an animator
    to find.

    Args:
        rig: The module's ``ModuleRig``.
        result: The foot, after ``build_foot_controls``.
        limb_result: What ``build_limb_controls`` returned.
        guides: Guide nodes; needs ``ball`` and ``toe``.
        bind_joints: ``[ball_bind, toe_bind]``.
        size: Controller size for ``fk_ball``.
        name: Extra name token.
    """
    ball_at = guides["ball"].world_position
    toe_at = guides["toe"].world_position

    # --- IK side: two SC handles inside the reverse foot -------------------
    # Parented under the foot's own ankle driver (upstream of the limb's
    # solve), not under the limb's last IK joint (whose rotation is already
    # spoken for). No offset is set here: a freshly parented joint with no
    # translate sits exactly at its parent's world position, which is
    # exactly where the ankle driver already is.
    ik_ankle = tm.Joint.create(
        name=rig.name(name, "ikAnkle", suffix="jnt"), parent=result.ankle_driver
    )
    ik_ball = tm.Joint.create(
        name=rig.name(name, "ikBall", suffix="jnt"), parent=ik_ankle
    )
    ik_ball.world_position = ball_at
    ik_toe = tm.Joint.create(name=rig.name(name, "ikToe", suffix="jnt"), parent=ik_ball)
    ik_toe.world_position = toe_at
    tm.Joint.orient_chain([ik_ankle, ik_ball, ik_toe], aim_axis="x", up_axis="y")

    ball_handle = tm.IkHandle.create(
        ik_ankle,
        ik_ball,
        solver="ikSCsolver",
        name=rig.name(name, "ball", suffix="ikHandle"),
    )
    toe_handle = tm.IkHandle.create(
        ik_ball,
        ik_toe,
        solver="ikSCsolver",
        name=rig.name(name, "toe", suffix="ikHandle"),
    )
    for handle in (ball_handle, toe_handle):
        handle.parent = rig.groups.rig
        # Constrained, never parented: toe_wiggle is a controller's twin in
        # rig_grp, and an IK handle under control_grp would break the ground
        # rules. This is the pattern _build_soft_ik already uses.
        tm.MatrixConstraint.create(
            result.pivots["toe_wiggle"],
            handle,
            maintain_offset=True,
            skip_rotate="xyz",
            skip_scale="xyz",
        )

    # --- FK side ----------------------------------------------------------
    fk_ball = tm.Joint.create(
        name=rig.name(name, "fkBall", suffix="jnt"), parent=limb_result.fk_joints[-1]
    )
    fk_ball.world_position = ball_at
    fk_toe = tm.Joint.create(name=rig.name(name, "fkToe", suffix="jnt"), parent=fk_ball)
    fk_toe.world_position = toe_at
    tm.Joint.orient_chain([fk_ball, fk_toe], aim_axis="x", up_axis="y")

    fk_control = rig.controller(
        "fk_ball",
        size=size,
        parent=limb_result.fk_controls[-1],
        match=fk_ball,
        mirror="behaviour",
    )
    for channel in ("tx", "ty", "tz", "sx", "sy", "sz", "v"):
        plug = fk_control[channel]
        plug.locked = True
        plug.visible = False
    fk_control["ikFk"].create(proxy=limb_result.switch_plug)
    tm.MatrixConstraint.create(
        fk_control, fk_ball, maintain_offset=True, skip_scale="xyz"
    )

    # --- blend onto the deform skeleton -----------------------------------
    result.ball_joints = [fk_ball, ik_ball]
    result.toe_joints = [fk_toe, ik_toe]
    for index, (fk_joint, ik_joint) in enumerate(
        ((fk_ball, ik_ball), (fk_toe, ik_toe))
    ):
        blend = tm.MatrixBlend.create(
            fk_joint,
            [ik_joint],
            [limb_result.switch_plug],
            name=rig.name(name, "blend%d" % index),
        )
        tm.MatrixConstraint.create(
            blend.output, bind_joints[index], maintain_offset=True
        )
    return result


#: ``(attribute, control role, channel)``, ground up. The names are the
#: legacy module's, shortened to the house style: riggers and animators have
#: the muscle memory and there is no reason to spend it.
PROXIES = (
    ("heelRoll", "heel", "rotateX"),
    ("heelSpin", "heel", "rotateY"),
    ("ballSpin", "ball_spin", "rotateZ"),
    ("toeRoll", "toe", "rotateX"),
    ("toeSpin", "toe", "rotateY"),
    ("ballRoll", "ball", "rotateY"),
    ("ballLean", "ball", "rotateZ"),
    ("toeWiggle", "toe_wiggle", "rotateY"),
    ("bank", "bank", "rotateX"),
)


def build_foot_proxies(rig, result: FootResult, control) -> None:
    """Proxy every foot channel onto ``control``.

    Measured: Maya will proxy a single compound child (``rotateX``) under a
    different long name, the proxy is two-way, and **keying the proxy creates
    the animation curve on the source**. So the channel box and the
    controller are two front ends on one interface, not two interfaces that
    can disagree -- which is why there is no additive offset attribute here.

    Args:
        rig: The module's ``ModuleRig``.
        result: The foot, after ``build_foot_controls``.
        control: The controller the attributes appear on (the leg's IK foot).
    """
    rig.separator(control, "foot_")
    for attribute, role, channel in PROXIES:
        control.transform[attribute].create(
            proxy=result.controls[role].transform[channel]
        )


def build_foot_bank(rig, result: FootResult, *, name: str = "foot") -> FootResult:
    """Split the bank control's roll across the two edge pivots.

    Two clamps, not the legacy's pair of set-driven keys: the relationship is
    a straight line, and expressing a straight line as an animation curve
    puts editable, serialising keyframes into a rig nobody keyed.

    **Bank is the one place the two hierarchies are not twins.** One channel
    feeds two mutually exclusive pivots, so there is no single pivot for the
    control to correspond to: it is a handle for a value, and rotating it
    does not tilt it onto the edge the foot banks over. A single pivot whose
    ``rotatePivot`` switched on the sign would restore the correspondence --
    and the switch would be free, because the rotation is zero at the instant
    the sign changes. Rejected for now as cleverness bought against a
    structure the legacy proved in production; this is the note saying where
    to look if the detachment turns out to bother animators.
    """
    channel = result.controls["bank"].transform["rotateX"]
    total = result.controls["bank"].offset["rotateX"] + channel
    total.maximum(0.0) >> result.pivots["bank_out"]["rotateX"]
    total.minimum(0.0) >> result.pivots["bank_in"]["rotateX"]
    return result
