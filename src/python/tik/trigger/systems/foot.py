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
