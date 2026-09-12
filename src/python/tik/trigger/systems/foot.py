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

**No side multipliers anywhere.** Every pivot is built on one frame aimed
heel-to-tip with the ankle as up, which points the same way on both feet, so
``rx`` is roll, ``ry`` is spin and ``rz`` is lean on the left and the right
alike. The legacy module's per-attribute multiplier table -- with its two
exemptions for heel roll and toe roll -- was paying for a frame problem one
attribute at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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

    Built from the foot's own geometry rather than from a side convention,
    which is what makes both feet agree. ``aim_at`` bakes plain rotation
    values, so the frame is static once created.
    """
    frame = tm.Transform.create(
        name=rig.name(name, "frame"),
        parent=parent.long_name if parent is not None else rig.groups.rig.long_name,
    )
    frame.snap_to(guides["heel"], rotation=False)
    frame.aim_at(
        guides["tip"],
        aim_vector=(0, 0, 1),
        up_vector=(0, 1, 0),
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

    result.root = tm.Transform.create(
        name=rig.name(name, "root", suffix="grp"), parent=rig.groups.rig.long_name
    )
    result.root.snap_to(parent)
    tm.MatrixConstraint.create(parent, result.root, maintain_offset=True)

    branch = result.root
    for role in PIVOTS:
        # toe_wiggle is a second child of toe, not a link below ball_roll:
        # it carries the ball and toe handles, so it must bend the toes
        # without moving the leg.
        under = result.pivots["toe"] if role == "toe_wiggle" else branch
        pivot = tm.Transform.create(
            name=rig.name(name, role, suffix="grp"), parent=under.long_name
        )
        pivot.snap_to(guides[PIVOT_GUIDES[role]], rotation=False)
        # Position from the marker, rotation from the shared frame. This is
        # the whole of §6.3.
        pivot.align_to(result.frame, position=False)
        result.pivots[role] = pivot
        if role != "toe_wiggle":
            branch = pivot

    # What the limb solve follows.
    result.ankle_driver = tm.Transform.create(
        name=rig.name(name, "ankleDriver", suffix="grp"),
        parent=result.pivots["ball_roll"].long_name,
    )
    result.ankle_driver.snap_to(guides["ankle"], rotation=False)
    result.ankle_driver.align_to(parent, position=False)
    return result
