"""The reverse foot, driven directly rather than through the leg module."""

import math

import pytest

import tik.maya as tm
from tik.trigger.systems import foot as foot_system


def _foot_guides():
    """Left-foot marker positions, matching the leg module's defaults."""
    return {
        role: tm.Joint.create(name="guide_" + role, position=position)
        for role, position in {
            "ankle": (2.0, 1.0, 0.0),
            "ball": (2.0, 0.25, 1.3),
            "heel": (2.0, 0.05, -0.6),
            "tip": (2.0, 0.05, 2.8),
            "bank_in": (1.2, 0.05, 1.3),
            "bank_out": (2.8, 0.05, 1.3),
        }.items()
    }


def _rotate_about_y(position, pivot, degrees):
    """``position`` rotated about the world Y axis through ``pivot`` (XZ only).

    Used to derive a toed-out foot from the straight one: the straight
    layout puts heel, tip and the ankle all on the same module X, which is
    exactly why ``foot_frame`` came out as a plain identity matrix for it --
    a degenerate case that cannot tell a real aim/up construction from a
    no-op. A toed-out foot is not collinear that way.
    """
    theta = math.radians(degrees)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    dx = position[0] - pivot[0]
    dz = position[2] - pivot[2]
    return (
        pivot[0] + dx * cos_t + dz * sin_t,
        position[1],
        pivot[2] - dx * sin_t + dz * cos_t,
    )


def test_the_pivots_nest_in_the_documented_order(build_context):
    ctx = build_context("base", name="probe")
    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=_foot_guides())

    expected = [
        ("bank_in", result.root),
        ("bank_out", result.pivots["bank_in"]),
        ("heel", result.pivots["bank_out"]),
        ("ball_spin", result.pivots["heel"]),
        ("toe", result.pivots["ball_spin"]),
        ("ball_roll", result.pivots["toe"]),
        ("toe_wiggle", result.pivots["toe"]),
    ]
    for role, parent in expected:
        assert result.pivots[role].parent.long_name == parent.long_name, role


def test_the_ankle_driver_sits_under_ball_roll(build_context):
    """What build_limb_solve will follow."""
    ctx = build_context("base", name="probe")
    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=_foot_guides())
    assert result.ankle_driver.parent.long_name == result.pivots["ball_roll"].long_name


def test_each_pivot_sits_on_its_marker(build_context):
    ctx = build_context("base", name="probe")
    guides = _foot_guides()
    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=guides)

    for pivot_role, guide_role in (
        ("bank_in", "bank_in"),
        ("bank_out", "bank_out"),
        ("heel", "heel"),
        ("ball_spin", "ball"),
        ("toe", "tip"),
        ("ball_roll", "ball"),
        ("toe_wiggle", "ball"),
    ):
        expected = guides[guide_role].world_position
        actual = result.pivots[pivot_role].world_position
        assert (actual - expected).length() == pytest.approx(0.0, abs=1e-5), pivot_role


def test_every_pivot_shares_one_frame_aimed_heel_to_tip(build_context):
    """The claim the whole side-multiplier simplification rests on.

    The old module multiplied eight of nine attributes by the side sign and
    then had to exempt two. The cause was the frame: build them all on one
    frame aimed heel-to-tip with the ankle as up, and rx/ry/rz mean the same
    thing on both feet with no multiplier anywhere.
    """
    ctx = build_context("base", name="probe")
    guides = _foot_guides()
    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=guides)

    to_tip = guides["tip"].world_position - guides["heel"].world_position
    to_tip.normalize()
    assert (result.frame.world_axis("z") * to_tip) == pytest.approx(1.0, abs=1e-4)

    reference = result.frame.world_axis("x")
    for role, pivot in result.pivots.items():
        assert (pivot.world_axis("x") * reference) == pytest.approx(1.0, abs=1e-4), role


def test_the_frame_is_well_formed(build_context):
    """A Z-only check would still pass a silently-rolled, degenerate frame.

    ``tm.AimFrame`` is known to fail silently when the up reference is
    parallel to the aim direction, and every pivot in the stack inherits
    this frame's rotation -- so it is not enough to know Z points at the
    tip. The three axes must also be mutually orthogonal and unit length,
    and Y (the up we asked for) must actually lean toward world up rather
    than, say, straight down with a compensating roll.
    """
    ctx = build_context("base", name="probe")
    guides = _foot_guides()
    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=guides)

    x_axis = result.frame.world_axis("x")
    y_axis = result.frame.world_axis("y")
    z_axis = result.frame.world_axis("z")

    for axis in (x_axis, y_axis, z_axis):
        assert axis.length() == pytest.approx(1.0, abs=1e-5)

    assert (x_axis * y_axis) == pytest.approx(0.0, abs=1e-5)
    assert (y_axis * z_axis) == pytest.approx(0.0, abs=1e-5)
    assert (x_axis * z_axis) == pytest.approx(0.0, abs=1e-5)

    to_tip = guides["tip"].world_position - guides["heel"].world_position
    to_tip.normalize()
    assert (z_axis * to_tip) == pytest.approx(1.0, abs=1e-4)

    # Y's component along world up, without constructing a second vector.
    assert y_axis.y > 0.5


def test_the_frame_follows_a_toed_out_foot(build_context):
    """The straight-foot case cannot rule out a frame that does nothing.

    Heel, tip and the ankle guide all share the module's X in the straight
    layout, so ``foot_frame`` comes out as the plain identity matrix -- every
    assertion above (Z at the tip, orthonormal axes, Y toward world up) is
    satisfied by a frame that was never actually built, or built wrong and
    landed on identity by coincidence. A toed-out foot -- the ordinary
    production pose, not an edge case -- breaks that collinearity, so if the
    pivots come out aligned to a real, non-identity frame here, the aim/up
    construction is doing the work the design claims rather than coasting on
    a degenerate input.
    """
    ctx = build_context("base", name="probe")
    straight = _foot_guides()
    ankle_pos = tuple(straight["ankle"].world_position)
    positions = {
        "ankle": ankle_pos,
        "ball": tuple(straight["ball"].world_position),
    }
    for role in ("heel", "tip", "bank_in", "bank_out"):
        positions[role] = _rotate_about_y(
            tuple(straight[role].world_position), ankle_pos, 25.0
        )
    guides = {
        role: tm.Joint.create(name="guide_toed_" + role, position=position)
        for role, position in positions.items()
    }

    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=guides)

    x_axis = result.frame.world_axis("x")
    y_axis = result.frame.world_axis("y")
    z_axis = result.frame.world_axis("z")

    to_tip = guides["tip"].world_position - guides["heel"].world_position
    to_tip.normalize()
    assert (z_axis * to_tip) == pytest.approx(1.0, abs=1e-4)
    # The point of this test: not the straight foot's identity matrix. Heel
    # and tip no longer share X, so a real aim has to give Z a real X part.
    assert abs(z_axis.x) > 0.3

    for axis in (x_axis, y_axis, z_axis):
        assert axis.length() == pytest.approx(1.0, abs=1e-5)
    assert (x_axis * y_axis) == pytest.approx(0.0, abs=1e-5)
    assert (y_axis * z_axis) == pytest.approx(0.0, abs=1e-5)
    assert (x_axis * z_axis) == pytest.approx(0.0, abs=1e-5)
    assert y_axis.y > 0.5

    reference = x_axis
    for role, pivot in result.pivots.items():
        assert (pivot.world_axis("x") * reference) == pytest.approx(1.0, abs=1e-4), role
