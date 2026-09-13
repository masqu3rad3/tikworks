"""The reverse foot, driven directly rather than through the leg module."""

import math

import pytest
from maya import cmds

import tik.maya as tm
from tik.trigger.systems import foot as foot_system

#: The leg guide pose the mirrored tests build from (left side; the fixture
#: negates X for the right).
LEG_POSES = {
    "hip": (1, 10.4, 0),
    "thigh": (2, 9.6, 0),
    "knee": (2, 5.3, 0.45),
    "ankle": (2, 1.0, 0),
    "ball": (2, 0.25, 1.3),
    "toe": (2, 0.05, 2.4),
    "heel": (2, 0.05, -0.6),
    "tip": (2, 0.05, 2.8),
    "bank_in": (2.8, 0.05, 1.3),
    "bank_out": (1.2, 0.05, 1.3),
    "neutral": (1 + 1 * 1.4, 10.4 - 9.4 * 1.4, 0),
}

#: Left-foot marker positions, matching the leg module's defaults.
_STRAIGHT_POSITIONS = {
    "ankle": (2.0, 1.0, 0.0),
    "ball": (2.0, 0.25, 1.3),
    "heel": (2.0, 0.05, -0.6),
    "tip": (2.0, 0.05, 2.8),
    "bank_in": (2.8, 0.05, 1.3),
    "bank_out": (1.2, 0.05, 1.3),
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
    """§6.2 connects a channel straight into ``bank_in.rotateZ`` (F-4).

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
    foot_system.build_foot_controls(ctx, result, size=size, guides=guides)
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
                continue  # two clamps, not a direct sum -- see build_foot_bank
            result.controls[control_role].transform[channel].value = 7.0
            assert result.pivots[pivot_role][channel].value == pytest.approx(
                7.0, abs=1e-4
            ), (control_role, channel)
            result.controls[control_role].transform[channel].value = 0.0


def test_a_control_sits_exactly_on_its_twin_pivot(build_context):
    """``match=`` is claimed to give position AND orientation in one step.

    A test that only checked position (e.g. ``distance_to``) would pass even
    if the control's world rotation drifted from its pivot -- and a drifted
    rotation is exactly what a snap-then-align-then-zero bug would produce,
    since ``offset.snap_to(control.transform)`` moves the parent the control
    is about to be re-parented under. Checking both axes and position
    together is what makes this a real lockstep check rather than a
    coincidence.
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


def test_positive_bank_rolls_one_edge_and_leaves_the_other(build_context):
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    foot_system.build_foot_bank(ctx, result)

    result.controls["bank"].transform["rotateZ"].value = 45.0
    assert result.pivots["bank_out"]["rotateZ"].value == pytest.approx(45.0, abs=1e-4)
    assert result.pivots["bank_in"]["rotateZ"].value == pytest.approx(0.0, abs=1e-4)

    result.controls["bank"].transform["rotateZ"].value = -45.0
    assert result.pivots["bank_out"]["rotateZ"].value == pytest.approx(0.0, abs=1e-4)
    assert result.pivots["bank_in"]["rotateZ"].value == pytest.approx(-45.0, abs=1e-4)


def test_bank_lays_down_no_animation_curves(build_context):
    """The legacy used setDrivenKeyframe for what is a straight line.

    A build should not author animation curves: they are editable, they
    serialise into the scene, and a rigger who scrubs onto them cannot tell
    they were made by code.
    """
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    foot_system.build_foot_bank(ctx, result)

    for role in ("bank_in", "bank_out"):
        curves = tm.listConnections(
            result.pivots[role]["rotateZ"].path, type="animCurve"
        )
        assert not curves, role


def _built_limb(ctx):
    from tik.trigger.systems import limb as limb_system

    return limb_system.build_limb_controls(
        ctx,
        [
            tm.Joint.create(name="lg%d" % index, position=position)
            for index, position in enumerate([(2, 9.6, 0), (2, 5.3, 0.45), (2, 1, 0)])
        ],
        labels=("upper", "lower", "foot"),
    )


def test_the_foot_chains_make_two_sc_handles(build_context):
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    guides = _foot_guides()
    guides["toe"] = tm.Joint.create(name="guide_toe", position=(2.0, 0.05, 2.4))

    limb_result = _built_limb(ctx)
    bind = [
        tm.Joint.create(name="bind_ball", position=(2, 0.25, 1.3)),
        tm.Joint.create(name="bind_toe", position=(2, 0.05, 2.4)),
    ]
    foot_system.build_foot_chains(
        ctx, result, limb_result, guides=guides, bind_joints=bind, size=1.0
    )
    assert len(result.ball_joints) == 2
    assert len(result.toe_joints) == 2
    handles = [
        node
        for node in tm.ls(type="ikHandle")
        if "ball" in node.name or "toe" in node.name
    ]
    assert len(handles) == 2


def test_build_foot_chains_never_touches_the_limbs_last_ik_joint(build_context):
    """No SC handle on the RP chain.

    Starting an ``ikSCsolver`` on ``limb_result.ik_joints[-1]`` would contend
    with the limb's own ``MatrixConstraint`` for that joint's rotate channels.
    Captured before and after ``build_foot_chains`` runs: the connections
    driving each rotate axis must come out byte-identical, and the new joint
    is not a start joint of either SC handle -- a test that only checked one
    of the two would pass on a fix that broke the other.
    """
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    guides = _foot_guides()
    guides["toe"] = tm.Joint.create(name="guide_toe", position=(2.0, 0.05, 2.4))

    limb_result = _built_limb(ctx)
    driver = tm.Transform.create(name="driver", parent=ctx.groups.rig.long_name)
    driver.snap_to(limb_result.ik_joints[-1])
    from tik.trigger.systems import limb as limb_system

    limb_system.build_limb_solve(ctx, limb_result, driver=driver)
    last_ik = limb_result.ik_joints[-1]

    def _rotate_sources():
        # MatrixConstraint connects the whole ``rotate`` compound in one shot
        # when no axis is skipped (which is the case for the limb's own
        # constraint here) -- ``listConnections`` on a *child* plug like
        # ``rotateX`` reports nothing for a compound-to-compound connection,
        # only the parent plug does. Check the compound first and only fall
        # back to per-axis lookups for the (here unused) partial-skip case,
        # so the sanity assertion below is checking the connection that
        # actually exists rather than one that can never be found.
        #
        # Raw ``cmds.listConnections`` here, not ``tm.listConnections``: the
        # tik wrapper resolves every string result through the node registry
        # (``listConnections`` is a ``NODE_FACTORIES`` entry), which drops
        # the ``.attribute`` suffix off a ``plugs=True`` result and returns a
        # bare ``Node`` for the source -- a fresh, identity-only wrapper each
        # call, so two calls that hit the very same plug would never compare
        # equal. Comparing the plain plug-path strings is what actually
        # proves the connection did not change.
        compound = tuple(
            cmds.listConnections(
                last_ik["rotate"].path, source=True, destination=False, plugs=True
            )
            or []
        )
        if compound:
            return {"rotate": compound}
        sources = {}
        for axis in ("X", "Y", "Z"):
            sources[axis] = tuple(
                cmds.listConnections(
                    last_ik["rotate" + axis].path,
                    source=True,
                    destination=False,
                    plugs=True,
                )
                or []
            )
        return sources

    before = _rotate_sources()
    # Sanity: the limb's own constraint really is driving it already, so an
    # empty-everywhere before/after match would not be a pass by accident.
    assert all(before.values()), before

    bind = [
        tm.Joint.create(name="bind_ball", position=(2, 0.25, 1.3)),
        tm.Joint.create(name="bind_toe", position=(2, 0.05, 2.4)),
    ]
    foot_system.build_foot_chains(
        ctx, result, limb_result, guides=guides, bind_joints=bind, size=1.0
    )
    assert _rotate_sources() == before

    for handle in tm.ls(type="ikHandle"):
        wrapped = tm.resolve(handle)
        assert wrapped.start_joint.long_name != last_ik.long_name, handle


def test_bank_behaviour_is_mirrored_between_the_two_feet(mirrored_pair):
    """Same ``bank`` value lifts the two feet by the same magnitude, opposite direction.

    This pins *behaviour*, not the frame mechanism: ``ankle_driver``'s bake
    against ``ik_tweak`` erases the frame's baseline before the bank delta is
    applied, so this assertion holds under either the behaviour-mirrored
    frame or a naive mirror (verified by hand -- flipping ``foot_frame`` to
    the naive convention does not make it fail). What it does catch is real:
    it is the test that found the summed-offset bug in
    ``build_foot_bank`` (see the regression test below). For the mechanism
    itself -- the claim that the frame is uniquely the behaviour mirror, and
    the one test that fails immediately if that regresses -- see
    ``test_the_mirrored_frame_is_the_behaviour_mirror``.
    """
    left, right = mirrored_pair("leg", LEG_POSES)
    for ctx in (left, right):
        ctx.controller_by_role("bank").transform["rotateZ"].value = 30.0

    left_up = left.outputs["foot"].world_axis("y")
    right_up = right.outputs["foot"].world_axis("y")
    assert left_up[0] == pytest.approx(-right_up[0], abs=1e-3)
    assert left_up[1] == pytest.approx(right_up[1], abs=1e-3)


def test_a_mirrored_foot_rests_and_rolls_exactly_like_the_source(mirrored_pair):
    """Both sides of a real, two-legged build -- not just the isolated frame.

    Regression test for a defect found while building this module: every
    pivot's world rotation is proven behaviour-mirrored in isolation (the
    tests above), but ``build_foot_bank`` summed the bank control's own
    OFFSET group into the live bank value -- and on the mirrored side that
    offset carries a real, non-zero baseline of its own (``bank`` is the one
    control in ``CONTROL_CHAIN`` parented directly under the world-aligned
    IK control rather than a behaviour-mirrored sibling, so its offset's
    local decomposition of the frame's ``Rx(180)`` lands on exactly
    ``rotateX = -180``, not zero). Wiring that baseline into a live
    connection popped every pivot from ``bank_in`` down on the mirrored
    side's REST pose, and made an identical ``footRoll`` value lift the two
    feet by different amounts. No isolated system test caught it because
    none of them build a mirrored pair through the whole leg.
    """
    left, right = mirrored_pair("leg", LEG_POSES)

    # Rest pose: ball and toe land on their own guides on both sides.
    for ctx in (left, right):
        for role in ("ball", "toe"):
            guide_pos = ctx.guide(role).world_position
            joint_pos = ctx.outputs[role].world_position
            assert (joint_pos - guide_pos).length() < 1e-3, role

    # An identical footRoll must lift both feet by the same amount -- a
    # world-Y-invariant motion, not a mirrored one.
    for ctx in (left, right):
        ctx.controller_by_role("ik").transform["footRoll"].value = 40.0
    left_height = left.outputs["ball"].world_position.y
    right_height = right.outputs["ball"].world_position.y
    assert left_height == pytest.approx(right_height, abs=1e-3)


def test_fk_ball_mirrors_on_every_axis_not_just_the_one_that_reads_zero(mirrored_pair):
    """``fk_ball``'s three unlocked rotate channels must all mirror.

    Regression test for a second, sharper defect than the one above:
    ``build_foot_chains`` never passed ``reverse_aim``/``reverse_up`` to the
    FK side's ``orient_chain``. Ball-to-toe is ``(0, -0.2, 1.1)`` on this
    module's own numbers -- the X term is ``2*mult - 2*mult``, zero on
    EITHER side -- so the unreversed call gave ``fk_ball`` the identical
    world frame on both feet, while ``fk_control`` was still built
    ``match=fk_ball, mirror="behaviour"``: an un-mirrored frame wearing a
    behaviour-mirror tag.

    By spec 6.3's own algebra a local rotation only mirrors correctly when
    its world axis is the mirror normal. ``fk_ball``'s local Z happens to
    map to world -X, so driving ``rotateZ`` alone (as an earlier, incomplete
    version of this test did) reads as correct BY COINCIDENCE -- rotateX
    and rotateY do not, and
    both are unlocked on the control, so an animator can reach them. This is
    exactly the trap spec 6.3 names: "a claim proven only where its
    mechanism is inert is not proven." Driving all three channels here is
    what actually proves the mirror, rather than the one axis that would
    have passed regardless.
    """
    left, right = mirrored_pair("leg", LEG_POSES)
    for ctx in (left, right):
        ctx.controller_by_role("ik").transform["ikFk"].value = 0.0

    for channel in ("rotateX", "rotateY", "rotateZ"):
        rest = {
            side: ctx.outputs["toe"].world_position
            for side, ctx in (("L", left), ("R", right))
        }
        for ctx in (left, right):
            ctx.controller_by_role("fk_ball").transform[channel].value = 25.0
        rolled = {
            side: ctx.outputs["toe"].world_position
            for side, ctx in (("L", left), ("R", right))
        }
        for ctx in (left, right):
            ctx.controller_by_role("fk_ball").transform[channel].value = 0.0

        left_delta = rolled["L"] - rest["L"]
        right_delta = rolled["R"] - rest["R"]
        assert right_delta.x == pytest.approx(-left_delta.x, abs=1e-3), channel
        assert right_delta.y == pytest.approx(left_delta.y, abs=1e-3), channel
        assert right_delta.z == pytest.approx(left_delta.z, abs=1e-3), channel

    for ctx in (left, right):
        ctx.controller_by_role("ik").transform["ikFk"].value = 1.0


def test_the_ball_and_toe_blend_on_the_limb_switch(build_context):
    """``ikFk`` at 0 and 1 puts the ball and toe bind joints exactly where FK
    and IK respectively say (spec 10.3), not merely "the two switch extremes
    differ".

    The earlier version of this test asserted only
    ``fk_driven * ik_driven < 0.999`` on the ball's world X axis -- which an
    inverted blend weight (``MatrixBlend(ik_joint, [fk_joint], [switch])``
    instead of the correct ``MatrixBlend(fk_joint, [ik_joint], [switch])``)
    would satisfy just as readily: the two sampled orientations still
    differ, they are simply attached to the wrong end of the switch. Direct
    positional equality against ``result.ball_joints``/``toe_joints`` --
    which ``build_foot_chains`` already exposes -- catches that: it fails
    immediately if the extremes are swapped, because the bind joint would
    then sit on the *other* joint's position at each switch value.
    """
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    guides = _foot_guides()
    guides["toe"] = tm.Joint.create(name="guide_toe", position=(2.0, 0.05, 2.4))

    limb_result = _built_limb(ctx)
    bind = [
        tm.Joint.create(name="bind_ball", position=(2, 0.25, 1.3)),
        tm.Joint.create(name="bind_toe", position=(2, 0.05, 2.4)),
    ]
    foot_system.build_foot_chains(
        ctx, result, limb_result, guides=guides, bind_joints=bind, size=1.0
    )
    ball_bind, toe_bind = bind

    # Move the FK ball off the IK ball's position: at rest the two coincide
    # (both are set to the same guide position), so a positional check could
    # not tell a correct blend from a swapped one without a real difference
    # to attribute to the right side.
    ctx.controller_by_role("fk_ball").transform["rotateZ"].value = 25.0

    switch = limb_result.switch_plug
    switch.value = 0.0
    assert ball_bind.distance_to(result.ball_joints[0]) == pytest.approx(0.0, abs=1e-4)
    assert toe_bind.distance_to(result.toe_joints[0]) == pytest.approx(0.0, abs=1e-4)

    switch.value = 1.0
    assert ball_bind.distance_to(result.ball_joints[1]) == pytest.approx(0.0, abs=1e-4)
    assert toe_bind.distance_to(result.toe_joints[1]) == pytest.approx(0.0, abs=1e-4)


def test_ikfk_is_one_switch_for_the_whole_leg(scene):
    """Exactly one real ``ikFk`` attribute exists on the built rig.

    The earlier version of this test asserted
    ``"ikFk" not in [c for c in Leg.controls if c.endswith("Fk")]`` --
    vacuous, because every role in this codebase is snake_case (``_role()``
    joins with underscores), so no role can ever end in capital ``"Fk"``. A
    real second switch named e.g. ``foot_ik_fk`` would have sailed straight
    through it.

    The real invariant is about the *built rig*, not the manifest: every FK
    control (including the foot's ``fk_ball``) carries an ``ikFk`` PROXY of
    the limb's own switch, so the channel box always shows one no matter
    which controller is selected -- but there must be exactly one REAL,
    non-proxy attribute underneath all of them. A proxy attribute is a real
    Maya connection (``addAttr -proxy``): the proxy plug has an incoming
    connection from the attribute it mirrors, the real one does not.
    """
    from tik.trigger.core import ParentRef, get_module
    from tik.trigger.maya import Builder

    body = scene.create_guides(get_module("base")(name="body"))
    leg = scene.create_guides(
        get_module("leg")(name="leg", side="L"),
        parent=ParentRef(body.instance_id, "root"),
    )
    for role, (x, y, z) in LEG_POSES.items():
        cmds.xform(
            scene.guide_node(leg.instance_id, role).long_name, ws=True, t=(x, y, z)
        )
    Builder().build(document=scene.document, afterlife="keep")

    plugs = cmds.ls("*.ikFk") or []
    assert plugs, "no ikFk attribute was built at all"
    real = [
        plug
        for plug in plugs
        if not cmds.listConnections(plug, source=True, destination=False, plugs=True)
    ]
    assert len(real) == 1, f"expected exactly one real ikFk attribute, found {real}"


def test_every_proxy_writes_through_to_its_control(build_context):
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    host = ctx.controller("ik", size=1.0, mirror="world")
    foot_system.build_foot_proxies(ctx, result, host)

    for attribute, role, channel in foot_system.PROXIES:
        host.transform[attribute].value = 11.0
        assert result.controls[role].transform[channel].value == pytest.approx(
            11.0, abs=1e-4
        ), attribute
        host.transform[attribute].value = 0.0


def test_a_proxy_reads_back_what_its_control_was_set_to(build_context):
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    host = ctx.controller("ik", size=1.0, mirror="world")
    foot_system.build_foot_proxies(ctx, result, host)

    result.controls["heel"].transform["rotateX"].value = -17.5
    assert host.transform["heelRoll"].value == pytest.approx(-17.5, abs=1e-4)


def test_keying_a_proxy_lands_the_curve_on_the_control(build_context):
    """Measured in Maya on 2026-09-12, and the reason this design works.

    An animator in the channel box and an animator on the controller write
    the same curve. There is nothing to reconcile because there are not two
    of anything.
    """
    ctx = build_context("leg", name="probe")
    result = _built_foot(ctx)
    host = ctx.controller("ik", size=1.0, mirror="world")
    foot_system.build_foot_proxies(ctx, result, host)

    cmds.setKeyframe(host.transform.long_name, attribute="heelRoll", time=1)

    on_control = cmds.listConnections(
        result.controls["heel"].transform["rotateX"].path, type="animCurve"
    )
    on_proxy = cmds.listConnections(host.transform["heelRoll"].path, type="animCurve")
    assert on_control, "the curve must land on the control"
    assert not on_proxy, "and not on the proxy"


def test_the_proxy_names_match_the_channel_table():
    """A channel cannot be wired one way and proxied another."""
    wired = {
        (role, channel)
        for role, channels in foot_system.CONTROL_CHANNELS.items()
        for channel in channels
    }
    proxied = {(role, channel) for _name, role, channel in foot_system.PROXIES}
    assert wired == proxied


def _roll_rig(ctx, overlap):
    result = _built_foot(ctx)
    host = ctx.controller("ik", size=1.0, mirror="world")
    foot_system.build_foot_roll(ctx, result, host, overlap=overlap)
    return result, host


def _sample(result, host, value):
    host.transform["footRoll"].value = value
    return (
        result.controls["heel"].offset["rotateX"].value,
        result.controls["ball"].offset["rotateX"].value,
        result.controls["toe"].offset["rotateX"].value,
    )


def test_a_hard_break_is_exactly_min_and_max(build_context):
    """overlap 0 must be the hard behaviour, not an approximation of it."""
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=0.0)
    host.transform["rollBreak"].value = 30.0

    for value in (0.0, 10.0, 30.0, 55.0, 90.0):
        heel, ball, toe = _sample(result, host, value)
        assert heel == pytest.approx(min(value, 0.0), abs=1e-3), value
        assert ball == pytest.approx(min(value, 30.0), abs=1e-3), value
        assert toe == pytest.approx(max(value - 30.0, 0.0), abs=1e-3), value


def test_outside_the_band_the_overlap_changes_nothing(build_context):
    """The soft version is exact wherever it matters."""
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=10.0)
    host.transform["rollBreak"].value = 30.0

    for value in (0.0, 12.0, 19.9, 40.1, 75.0):
        heel, ball, toe = _sample(result, host, value)
        assert ball == pytest.approx(min(value, 30.0), abs=1e-3), value
        assert toe == pytest.approx(max(value - 30.0, 0.0), abs=1e-3), value


def test_the_toe_starts_before_the_break(build_context):
    """A genuine overlap, not a rounded corner.

    At r == b the ball sits 0.25w short and the toe has taken up that 0.25w.
    """
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=10.0)
    host.transform["rollBreak"].value = 30.0

    heel, ball, toe = _sample(result, host, 30.0)
    assert ball == pytest.approx(30.0 - 0.25 * 10.0, abs=1e-3)
    assert toe == pytest.approx(0.25 * 10.0, abs=1e-3)


def test_the_toe_never_goes_negative(build_context):
    """The bug the naive blend had: toe == -0.78 at r=25, b=30, w=10."""
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=10.0)
    host.transform["rollBreak"].value = 30.0

    for step in range(-90, 91):
        _heel, _ball, toe = _sample(result, host, float(step))
        assert toe >= -1e-4, "toe went backwards at footRoll=%d" % step


def test_the_three_slices_always_sum_to_the_roll(build_context):
    """heel + ball + toe == footRoll, everywhere. The invariant."""
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=10.0)
    host.transform["rollBreak"].value = 30.0

    for value in (-40.0, -5.0, 0.0, 15.0, 29.0, 30.0, 31.0, 60.0):
        heel, ball, toe = _sample(result, host, value)
        assert (heel + ball + toe) == pytest.approx(value, abs=1e-3), value


def test_negative_roll_drives_the_heel_and_nothing_else(build_context):
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=10.0)
    host.transform["rollBreak"].value = 30.0

    heel, ball, toe = _sample(result, host, -25.0)
    assert heel == pytest.approx(-25.0, abs=1e-3)
    assert ball == pytest.approx(0.0, abs=1e-3)
    assert toe == pytest.approx(0.0, abs=1e-3)


def test_the_roll_adds_to_the_animator_s_own_value(build_context):
    """The offset group carries the automation; the control stays theirs."""
    ctx = build_context("leg", name="probe")
    result, host = _roll_rig(ctx, overlap=0.0)
    host.transform["rollBreak"].value = 30.0
    host.transform["footRoll"].value = 20.0
    result.controls["ball"].transform["rotateX"].value = 7.0

    assert result.pivots["ball_roll"]["rotateX"].value == pytest.approx(27.0, abs=1e-3)


def test_each_foot_channel_moves_the_foot_the_way_its_name_says(mirrored_pair):
    """The channel table has axis letters; nothing until now checked they
    are the RIGHT letters.

    Every other test in this file checks *consistency* -- a channel reaches
    its pivot, both feet agree, the roll slices sum back to ``footRoll``. A
    channel wired to the wrong rotation axis passes every one of them: the
    control still drives *a* pivot channel, the sum still holds, both feet
    still agree with each other -- they are just all agreeing on the wrong
    motion. That is exactly the defect a rigger reported: ball roll swinging
    the foot sideways instead of lifting the heel, ball spin landing on the
    same axis as the lean, banking pitching instead of tipping onto an edge.
    None of the 524 integration tests standing at the time were anatomical,
    so none of them caught it.

    Each proxy is driven to a generous 30 degrees in turn and the DOMINANT
    component of the resulting bind-joint motion is checked against what the
    channel's name promises, not merely that *some* motion happened. In this
    frame X is side, Y is up, Z is forward:

    - a **roll** (heel lifts / toe dips) must move its joint dominantly in Y,
      with near-zero sideways (X) motion
    - a **spin** (yaw) must move its joint dominantly in X, with near-zero Y
      **and** a non-trivial Z -- see below for why Z is checked too
    - **bank** must tip the foot: the ankle moves dominantly in X while the
      toe moves dominantly in Y -- a real secondary signal that only
      ``bank`` produces (its pivots sit above the whole stack, unlike
      ``ball_roll``'s, so rotating it alone reaches all the way to the toe)
    - **ballLean** tips the same way, checked at the ankle alone -- rotating
      ``ball_roll`` does not reach the toe (``toe_wiggle`` is its sibling,
      not its child), so there is no secondary signal to check there
    - **toeWiggle** must bend the toe dominantly in Y, not yaw it in X

    **Why spin also checks Z.** ``ball_spin``'s guide sits exactly on
    ``ball_roll``'s (both are the ``ball`` marker), and the joint measured
    for spin has an offset from that shared point that is mostly along Y.
    Rotating *either* a genuine Y-axis spin or a wrongly-Z-axis lean about
    that point swings X dominantly with only a second-order (near-zero) Y
    change -- so "X dominant, Y near-zero" alone cannot tell ``ballSpin``'s
    pre-fix ``rotateZ`` bug from a correct ``rotateY``, and was measured to
    pass under the broken mapping while writing this test. The tell is Z: a
    Y-axis rotation swings X *and* Z together (Z changes by a comparable,
    non-trivial amount here), while a Z-axis rotation leaves Z **exactly**
    invariant by construction. Requiring a real Z move is what actually
    catches the bug the "identical to ballLean" verdict describes.

    Measured (this build, left leg, ``LEG_POSES``, 30 degrees each): the
    margins below are generous on purpose -- this is a "which axis" test,
    not a precision one. Restoring the pre-fix mapping (``ballRoll ->
    rotateY``, ``ballSpin -> rotateZ``, ``toeWiggle -> rotateY``,
    ``bank -> rotateX``) fails this test on exactly those four channels and
    passes on the other five -- verified by hand while writing this test
    (see the fix's report), which is the evidence this class of bug cannot
    ship silently again.
    """
    left, _right = mirrored_pair("leg", LEG_POSES)
    ik = left.controller_by_role("ik")
    angle = 30.0
    dominant_min = 0.15
    ratio_max = 0.35
    spin_z_min = 0.05

    def _delta(attribute, role):
        rest = left.outputs[role].world_position
        ik.transform[attribute].value = angle
        moved = left.outputs[role].world_position
        ik.transform[attribute].value = 0.0
        return moved - rest

    def _assert_dominant(label, delta, dominant_axis, other_axis):
        dominant = abs(getattr(delta, dominant_axis))
        other = abs(getattr(delta, other_axis))
        assert dominant > dominant_min, "%s: %s delta %.4f is not a real move" % (
            label,
            dominant_axis,
            dominant,
        )
        assert (
            other < ratio_max * dominant
        ), "%s: %s delta %.4f is not near-zero next to %s delta %.4f" % (
            label,
            other_axis,
            other,
            dominant_axis,
            dominant,
        )

    # (attribute, joint output) -- roll channels must dominate in Y
    for attribute, role in (
        ("heelRoll", "toe"),
        ("toeRoll", "foot"),
        ("ballRoll", "foot"),
    ):
        _assert_dominant(attribute, _delta(attribute, role), "y", "x")

    # (attribute, joint output) -- spin/yaw channels must dominate in X, with
    # near-zero Y *and* a real Z move (the Z-invariance discriminator above).
    for attribute, role in (
        ("heelSpin", "toe"),
        ("toeSpin", "foot"),
        ("ballSpin", "foot"),
    ):
        delta = _delta(attribute, role)
        _assert_dominant(attribute, delta, "x", "y")
        assert abs(delta.z) > spin_z_min, (
            "%s: z delta %.4f is exactly zero -- this is a lean (Z-axis), "
            "not a spin (Y-axis)" % (attribute, delta.z)
        )

    _assert_dominant("ballLean", _delta("ballLean", "foot"), "x", "y")
    # Bank gets an X-dominant check rather than the near-zero-Y one the other
    # tip channels use, and the difference is geometry, not leniency. The bank
    # pivots sit on the floor at the foot's edges while the ankle rides ~0.95
    # above them, so arcing about one MUST lift the ankle: at 30 degrees the
    # measured delta is x -0.58, y +0.27, which is exactly
    # `rotate((+0.8, +0.95), 30deg)`. Demanding a near-zero Y here would be
    # demanding that the foot bank without rolling onto the edge.
    #
    # It still discriminates the defect this test was written for. The old
    # wiring put bank on `rotateX` (a pitch), which moves the ankle
    # (0, +0.52, +0.65) -- no X at all -- so `|dx| > |dy|` fails on it just as
    # the near-zero-Y form did.
    bank_delta = _delta("bank", "foot")
    assert abs(bank_delta.x) > abs(bank_delta.y), (
        "bank (ankle): x delta %.4f must dominate y delta %.4f -- bank tips the "
        "foot onto an edge about the forward axis; a y-dominant move is a pitch"
        % (bank_delta.x, bank_delta.y)
    )
    assert abs(bank_delta.x) > dominant_min, (
        "bank (ankle): x delta %.4f is not a real move" % bank_delta.x
    )
    _assert_dominant("bank (toe)", _delta("bank", "toe"), "y", "x")
    _assert_dominant("toeWiggle", _delta("toeWiggle", "toe"), "y", "x")


def test_foot_roll_lifts_the_ankle_not_sideways(mirrored_pair):
    """``footRoll`` is the animator's one auto-roll channel; sweeping it
    positive must lift the ankle, not swing it sideways.

    A separate test from the nine discrete channels above: ``footRoll``
    drives the same controls' OFFSET groups (``build_foot_roll``, §8.3)
    through the smooth-minimum in §8.2, not their proxied ``transform``
    channels, and it shares ``ball``'s channel with ``ballRoll`` (both land
    on ``offset["rotateX"]`` / ``transform["rotateX"]``) -- the same class
    of axis bug could reappear in one without the other test noticing.
    """
    left, _right = mirrored_pair("leg", LEG_POSES)
    ik = left.controller_by_role("ik")

    rest = left.outputs["foot"].world_position
    ik.transform["footRoll"].value = 30.0
    moved = left.outputs["foot"].world_position
    ik.transform["footRoll"].value = 0.0
    delta = moved - rest

    assert delta.y > 0.15, "footRoll did not lift the ankle in Y"
    assert abs(delta.x) < 0.35 * delta.y, "footRoll swung the ankle sideways"
