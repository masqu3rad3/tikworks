"""The reverse foot, driven directly rather than through the leg module."""

import math

import pytest

import tik.maya as tm
from tik.trigger.systems import foot as foot_system

#: Left-foot marker positions, matching the leg module's defaults.
_STRAIGHT_POSITIONS = {
    "ankle": (2.0, 1.0, 0.0),
    "ball": (2.0, 0.25, 1.3),
    "heel": (2.0, 0.05, -0.6),
    "tip": (2.0, 0.05, 2.8),
    "bank_in": (1.2, 0.05, 1.3),
    "bank_out": (2.8, 0.05, 1.3),
}


def _foot_guides(positions=None):
    """Guide joints at ``positions`` (default: the straight-foot markers)."""
    positions = positions if positions is not None else _STRAIGHT_POSITIONS
    return {
        role: tm.Joint.create(name="guide_" + role, position=position)
        for role, position in positions.items()
    }


def _rotate_about_y(position, pivot, degrees):
    """``position`` rotated about the world Y axis through ``pivot`` (XZ only)."""
    theta = math.radians(degrees)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    dx = position[0] - pivot[0]
    dz = position[2] - pivot[2]
    return (
        pivot[0] + dx * cos_t + dz * sin_t,
        position[1],
        pivot[2] - dx * sin_t + dz * cos_t,
    )


def _toed_out_positions(degrees: float = 25.0, mirror: bool = False) -> dict:
    """The straight-foot markers, toed out about world Y through the ankle.

    The ordinary production pose, not an edge case: the straight layout
    puts heel, tip and the ankle all on the same module X, which is exactly
    why ``foot_frame`` came out as a plain identity matrix for it -- a
    degenerate case that cannot tell a real aim/up construction from a
    no-op, nor a naively-mirrored frame from a behaviour-mirrored one (both
    read back as identity on both feet). Every marker but the ankle itself
    rotates, ``ball`` included: three pivots (``ball_spin``, ``ball_roll``,
    ``toe_wiggle``) sit on it, and leaving it on the old heel-tip line while
    the rest of the foot turned would put those three off the foot this
    layout is meant to describe.

    ``mirror=True`` negates X afterwards, giving the guide placement a
    naively-mirrored right foot would actually have (this repo's own
    definition of "mirrored" for a guide layout, matching the
    ``mirrored_pair`` fixture's convention) -- the input §6.3's proof and
    F-1 are about, not an already-corrected one.
    """
    ankle = _STRAIGHT_POSITIONS["ankle"]
    positions = {
        role: (
            position if role == "ankle" else _rotate_about_y(position, ankle, degrees)
        )
        for role, position in _STRAIGHT_POSITIONS.items()
    }
    if mirror:
        positions = {role: (-x, y, z) for role, (x, y, z) in positions.items()}
    return positions


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
        distance = result.pivots[pivot_role].distance_to(guides[guide_role])
        assert distance == pytest.approx(0.0, abs=1e-5), pivot_role


def test_every_pivot_shares_one_frame_aimed_heel_to_tip(build_context):
    """Every pivot on one foot reads its rotation from the same frame.

    Within a single foot this needs no side story at all: every pivot is
    simply aligned to the frame `build_foot_pivots` built for it. The two
    feet agreeing with each other -- and why that takes a behaviour-mirrored
    frame rather than a naive one -- is
    `test_the_mirrored_frame_is_the_behaviour_mirror`, not this test.
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
    guides = _foot_guides(_toed_out_positions())

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


def test_the_mirrored_frame_is_the_behaviour_mirror(build_context):
    """Section 6.3's uniqueness proof, pinned so it cannot regress silently.

    A naive mirror of the frame (``M = diag(-1,1,1)`` applied straight to
    the guide positions) comes back with Z and Y mirrored but X negated
    relative to that -- because X is a cross product of the other two, and
    a reflection negates a cross product one extra time. Requiring the
    mirrored frame to reproduce mirrored motion for *every* rotation forces
    a unique answer instead: ``F_R = -M F_L``, i.e. every column keeps its
    own X component and negates Y and Z. That is the *behaviour* mirror
    (``Rx(180)``) this repo already uses for mirrored joints, and it is what
    lets every channel connection downstream of this frame go in with no
    side term anywhere.
    """
    # "base" is deliberately unsided (``sided = False`` -- it is a rig root,
    # not a left/right limb) and forces ``side_mult`` to ``1`` regardless of
    # what is asked for, which would silently take the mirrored branch this
    # test exists to exercise out of the picture. "control" is an ordinary
    # sided module and gives a real ``side_mult`` of ``-1`` for "R".
    left_positions = _toed_out_positions()
    right_positions = _toed_out_positions(mirror=True)

    left_ctx = build_context("control", name="probeL", side="L")
    left_anchor = tm.Transform.create(
        name="anchorL", parent=left_ctx.groups.rig.long_name
    )
    left_result = foot_system.build_foot_pivots(
        left_ctx, parent=left_anchor, guides=_foot_guides(left_positions)
    )

    right_ctx = build_context("control", name="probeR", side="R")
    right_anchor = tm.Transform.create(
        name="anchorR", parent=right_ctx.groups.rig.long_name
    )
    right_result = foot_system.build_foot_pivots(
        right_ctx, parent=right_anchor, guides=_foot_guides(right_positions)
    )
    assert left_ctx.side_mult == 1 and right_ctx.side_mult == -1  # sanity

    # F_R == -M F_L: every column keeps X, negates Y and Z. The naive
    # mirror this design withdrew would instead keep Y/Z and negate X.
    for axis in ("x", "y", "z"):
        left_axis = left_result.frame.world_axis(axis)
        right_axis = right_result.frame.world_axis(axis)
        assert right_axis.x == pytest.approx(left_axis.x, abs=1e-4), axis
        assert right_axis.y == pytest.approx(-left_axis.y, abs=1e-4), axis
        assert right_axis.z == pytest.approx(-left_axis.z, abs=1e-4), axis

    # The payoff: the SAME positive rotation about each local axis, applied
    # on both sides, must move the foot as an exact mirror image of the
    # other side -- no negation anywhere, unlike the naive frame this
    # design withdrew.
    #
    # The marker's own local offset must be the FULL negation of the left's,
    # ``-v``, not ``S v = diag(-1,1,1) v``. Proof: for any single-axis
    # rotation R(t) applied identically on both sides, R(t)(-v) - (-v) =
    # -(R(t)v - v) always (linearity), so with F_R = -M F_L: delta_R =
    # F_R * (-(R(t)v - v)) = -F_R(R(t)v - v) = -(-M F_L)(R(t)v - v) =
    # M * (F_L(R(t)v - v)) = M * delta_L -- the exact spatial mirror, on
    # every axis, unconditionally. ``S v`` does not have this property for
    # a general offset: verified numerically that with ``S v`` the Y and Z
    # rotations do not come back as a clean mirror of any kind, only X does
    # (and there as the *behaviour* mirror of ``delta_L``, not the spatial
    # one) -- because unlike ``-v``, ``S v`` does not satisfy
    # ``R(t) S v - S v = S(R(t)v - v)`` for the y/z rotations (S and R_y/R_z
    # do not commute; S and R_x do, which is why the x-axis case alone
    # looked clean with ``S v`` too, just not spatially).
    left_pivot = left_result.pivots["ball_roll"]
    right_pivot = right_result.pivots["ball_roll"]
    left_offset = (0.3, 0.5, 1.0)
    right_offset = (-left_offset[0], -left_offset[1], -left_offset[2])
    left_marker = tm.Transform.create(name="markerL", parent=left_pivot.long_name)
    left_marker.translate = left_offset
    right_marker = tm.Transform.create(name="markerR", parent=right_pivot.long_name)
    right_marker.translate = right_offset

    left_rest_rotate = tuple(left_pivot.rotate)
    right_rest_rotate = tuple(right_pivot.rotate)

    for index, axis in enumerate("xyz"):
        left_rest_pos = left_marker.world_position
        left_rot = list(left_rest_rotate)
        left_rot[index] += 15.0
        left_pivot.rotate = tuple(left_rot)
        left_delta = left_marker.world_position - left_rest_pos
        left_pivot.rotate = left_rest_rotate

        right_rest_pos = right_marker.world_position
        right_rot = list(right_rest_rotate)
        right_rot[index] += 15.0
        right_pivot.rotate = tuple(right_rot)
        right_delta = right_marker.world_position - right_rest_pos
        right_pivot.rotate = right_rest_rotate

        assert right_delta.x == pytest.approx(-left_delta.x, abs=1e-4), axis
        assert right_delta.y == pytest.approx(left_delta.y, abs=1e-4), axis
        assert right_delta.z == pytest.approx(left_delta.z, abs=1e-4), axis


def test_every_pivot_rests_at_identity_local_rotation(build_context):
    """§6.2 connects a channel straight into ``bank_in.rotateX`` (F-4).

    Every pivot but ``bank_in`` sits under a sibling that already carries
    the shared frame's world rotation, so its own local rotate is zero by
    construction. ``bank_in``'s parent is ``root`` instead, so ``root`` must
    also carry the frame's rotation -- not the driver's -- or ``bank_in``'s
    rest-pose local rotate would hold the frame-vs-driver delta, and §6.2's
    connection would overwrite (not add to) that rest value the moment the
    build wires it, popping the foot.

    An identity anchor -- what every other test in this file uses -- cannot
    expose this: with the driver at identity, the delta IS the frame's own
    rotation restated, and the straight foot's frame is also identity, so
    the bug hides in both the default anchor and the default guide layout.
    The anchor here is given an arbitrary rotation of its own so the delta
    is a real one.
    """
    ctx = build_context("base", name="probe")
    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    anchor.rotate = (10.0, 20.0, 30.0)
    guides = _foot_guides(_toed_out_positions())
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=guides)

    for role in foot_system.PIVOTS:
        rotate = result.pivots[role].rotate
        for component in rotate:
            assert component == pytest.approx(0.0, abs=1e-4), role


def _built_foot(ctx, size=1.0):
    anchor = tm.Transform.create(name="anchor", parent=ctx.groups.rig.long_name)
    guides = _foot_guides()
    result = foot_system.build_foot_pivots(ctx, parent=anchor, guides=guides)
    foot_system.build_foot_controls(ctx, result, size=size)
    return result


def test_the_controls_nest_like_the_pivots(build_context):
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    chain = ("bank", "heel", "ball_spin", "toe", "ball", "toe_wiggle")
    for child, parent in zip(chain[1:], chain[:-1]):
        control = result.controls[child]
        assert control.offset.parent.long_name == (
            result.controls[parent].transform.long_name
        ), child


def test_every_foot_control_is_secondary(build_context):
    from tik.trigger.maya import tags

    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    for role, control in result.controls.items():
        assert control.transform.meta.get(tags.TIER) == "secondary", role


def test_a_control_channel_and_its_offset_sum_onto_the_pivot(build_context):
    """The sum is what lets automation and the animator both drive a pivot."""
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)

    result.controls["heel"].transform["rotateX"].value = 20.0
    result.controls["heel"].offset["rotateX"].value = 5.0
    assert result.pivots["heel"]["rotateX"].value == pytest.approx(25.0, abs=1e-4)


def test_every_declared_channel_reaches_its_pivot(build_context):
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    for control_role, channels in foot_system.CONTROL_CHANNELS.items():
        for channel, pivot_role in channels.items():
            if control_role == "bank":
                continue  # two clamps, not a direct sum -- see Task 10
            result.controls[control_role].transform[channel].value = 7.0
            assert result.pivots[pivot_role][channel].value == pytest.approx(
                7.0, abs=1e-4
            ), (control_role, channel)
            result.controls[control_role].transform[channel].value = 0.0


def test_a_control_sits_exactly_on_its_twin_pivot(build_context):
    """``match=`` is claimed to give position AND orientation in one step.

    A test that only checked position (e.g. ``distance_to``) would pass even
    if the control's world rotation drifted from its pivot -- and a drifted
    rotation is exactly what the brief's snap-then-align-then-zero bug would
    have produced, since ``offset.snap_to(control.transform)`` moves the
    parent the control is about to be re-parented under. Checking both axes
    and position together is what makes this a real lockstep check rather
    than a coincidence.
    """
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    for role in foot_system.CONTROL_CHAIN:
        pivot = result.pivots[foot_system.CONTROL_GUIDES[role]]
        control = result.controls[role]
        assert control.transform.distance_to(pivot) == pytest.approx(
            0.0, abs=1e-5
        ), role
        for axis in ("x", "y", "z"):
            assert (
                control.transform.world_axis(axis) * pivot.world_axis(axis)
            ) == pytest.approx(1.0, abs=1e-4), (role, axis)


def test_every_foot_control_is_behaviour_mirrored(build_context):
    """Correction 1: ``mirror="behaviour"``, not ``"world"``.

    The foot's own frame is itself behaviour-mirrored (spec 6.3), so a
    control matched onto a pivot -- and therefore onto that frame -- is
    behaviour-mirrored for real. This is the tag a pose-mirror tool reads,
    and it also gates ``rig.controller``'s orient conjugation, which the
    next test exercises.
    """
    from tik.trigger.maya import tags

    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    for role, control in result.controls.items():
        assert control.transform.meta.get(tags.MIRROR) == tags.BEHAVIOUR, role


def test_the_right_foots_declared_orients_are_conjugated(build_context):
    """A ``mirror="world"`` regression would silently skip this conjugation.

    ``rig.controller`` only conjugates a declared ``control_orients`` entry
    when the control is behaviour-mirrored (``rig.py`` line ~466). None of
    the other tests in this file build on the right side, so this is the one
    place a regression back to ``mirror="world"`` -- correction 1's exact
    bug -- would go unnoticed: every other assertion here is insensitive to
    which mirror string was used.
    """
    from tik.trigger.maya.rig import mirror_orient

    left_ctx = build_context("leg", name="probeL", side="L")
    left_result = _built_foot(left_ctx)
    right_ctx = build_context("leg", name="probeR", side="R")
    right_result = _built_foot(right_ctx)

    declared = left_ctx.module.control_orient_defaults(left_ctx.module.values())
    checked = 0
    for role in foot_system.CONTROL_CHAIN:
        orient = declared.get(role)
        if not orient:
            continue
        checked += 1
        assert left_result.controls[role].shape_orient == orient, role
        assert right_result.controls[role].shape_orient == mirror_orient(orient), role
    assert checked > 0  # sanity: the leg module does declare foot orients
