"""Leg module: eleven guides, a reverse foot, one IK chain."""

import pytest
from maya import cmds

import tik.maya as tm
from tik.trigger.core import ParentRef, get_module
from tik.trigger.core.manifest import GuideKind
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder


@pytest.fixture
def scene():
    cmds.file(new=True, force=True)
    return GuideScene()


def test_the_leg_declares_eleven_guides():
    leg = get_module("leg")
    assert leg.guides.all_roles == (
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
    )


def test_the_foot_markers_are_reference_guides():
    """A marker is read for its position and nothing is shaped like it.

    Reference is also what stops them drawing bones: a reference guide is a
    locator transform, so it suppresses its own bone without suppressing its
    siblings -- four markers under the ankle would otherwise smear a blob.
    """
    layout = get_module("leg").guides
    for role in ("heel", "tip", "bank_in", "bank_out", "neutral"):
        assert layout.kind_for(role) is GuideKind.REFERENCE, role
    for role in ("thigh", "knee", "ankle", "ball", "toe"):
        assert layout.kind_for(role) is GuideKind.JOINT, role
    assert layout.kind_for("hip", is_root=True) is GuideKind.ROOT


def test_only_the_ankle_is_read_for_its_orientation():
    """The chain is oriented by convention; the ankle aligns the foot."""
    assert get_module("leg").guides.oriented == ("ankle",)


def test_drawing_a_leg_creates_all_eleven(scene):
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    for role in get_module("leg").guides.all_roles:
        assert scene.guide_node(leg.instance_id, role) is not None, role


def test_the_neutral_guide_is_collinear_with_hip_and_ankle(scene):
    """Exactly collinear, not approximately.

    The reach network measures the angle between this direction and the
    ankle's; at the guide pose that angle must be exactly zero or no scalar
    value leaves the bind pose alone. The arm measured a hand-written triple
    rounded to one decimal landing 0.006 out -- sixty times the tolerance.
    """
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    hip = scene.guide_node(leg.instance_id, "hip").world_position
    ankle = scene.guide_node(leg.instance_id, "ankle").world_position
    neutral = scene.guide_node(leg.instance_id, "neutral").world_position

    to_ankle = ankle - hip
    to_neutral = neutral - hip
    to_ankle.normalize()
    to_neutral.normalize()
    assert (to_ankle * to_neutral) == pytest.approx(1.0, abs=1e-6)


def test_the_collinearity_check_actually_discriminates(scene):
    """Sceptic's check on the test above: it must actually be able to fail.

    A dot product of two normalized vectors near 1.0 is not, on its own,
    proof the check can catch a wrong guide -- confirm it moves measurably
    once ``neutral`` is pushed off the hip-ankle line, using the real guide
    nodes rather than a hand-rolled vector example.

    Note for whoever edits ``draw_guides`` next: on this module's own
    numbers, a *hand-rounded-to-one-decimal* triple (the exact mistake the
    arm made) lands only ~5e-8 off -- under this test's 1e-6 tolerance,
    unlike the arm's 0.006. That is a property of these particular
    coordinates (the hip-ankle direction is already decimal-clean), not a
    defect in the check: it still catches any materially wrong guide, which
    is what matters, since the shipped code derives ``neutral`` exactly and
    never hand-types it.
    """
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    hip = scene.guide_node(leg.instance_id, "hip").world_position
    ankle = scene.guide_node(leg.instance_id, "ankle").world_position
    neutral_node = scene.guide_node(leg.instance_id, "neutral")

    # A visible, half-a-unit nudge off the line -- not a rounding artefact.
    pushed = neutral_node.world_position
    neutral_node.world_position = (pushed.x, pushed.y, pushed.z + 0.5)
    wrong_neutral = neutral_node.world_position

    to_ankle = ankle - hip
    to_wrong = wrong_neutral - hip
    to_ankle.normalize()
    to_wrong.normalize()
    dot = to_ankle * to_wrong

    assert dot != pytest.approx(1.0, abs=1e-6)
    assert (1.0 - dot) > 1e-4


def test_the_knee_bends_forward_of_the_hip_and_ankle(scene):
    """The bend plane is unambiguous: the knee sits ahead in Z of both ends.

    A test cannot judge whether the pose "reads as a leg", but it can check
    the one thing that actually matters mechanically -- the IK solver needs a
    knee that is not collinear with hip and ankle, and the sign of its offset
    is what keeps the knee pointing forward rather than backward.
    """
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    hip = scene.guide_node(leg.instance_id, "hip").world_position
    knee = scene.guide_node(leg.instance_id, "knee").world_position
    ankle = scene.guide_node(leg.instance_id, "ankle").world_position

    assert knee.z > hip.z
    assert knee.z > ankle.z


def test_the_chain_descends_monotonically_from_hip_to_ankle(scene):
    """Hip, thigh, knee and ankle step down in Y with no reversal."""
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    heights = [
        scene.guide_node(leg.instance_id, role).world_position.y
        for role in ("hip", "thigh", "knee", "ankle")
    ]
    for higher, lower in zip(heights, heights[1:]):
        assert higher > lower, heights


def test_the_foot_markers_sit_near_the_ground_plane(scene):
    """Heel, tip, bank_in, bank_out and ball all sit close to Y=0.

    They describe the footprint the reverse foot pivots around, so they must
    sit near the ground rather than floating mid-shin or burrowing below it.
    """
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    for role in ("heel", "tip", "bank_in", "bank_out", "ball"):
        y = scene.guide_node(leg.instance_id, role).world_position.y
        assert 0.0 <= y < 0.5, f"{role} sits at y={y}, not near the ground plane"


def test_the_leg_builds_standalone_with_no_parent(scene):
    """No parent, no inputs: the module still builds completely.

    ``root`` is not ``required``, so the socket simply stands free at the
    hip guide when nothing feeds it -- nothing in the build, from the bind
    chain through the limb and the reverse foot, depends on that input
    being wired.
    """
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    report = Builder().build(document=scene.document, afterlife="delete")
    ctx = report.rigs[leg.instance_id]
    for name in ("hip", "upperleg", "lowerleg", "foot", "ball", "toe"):
        assert ctx.outputs[name] is not None, name


def test_the_bank_markers_straddle_the_ankle_in_x(scene):
    """``bank_in`` and ``bank_out`` sit on opposite sides of the ankle.

    ``bank_out`` is the marker nearer the body midline (x=0) and ``bank_in``
    the one farther from it -- a different X *sign* on each side, but on
    both sides the ankle's X must land strictly between them. If the two
    were ever swapped or misplaced in ``draw_guides``, the reverse foot's
    bank pivots would roll the wrong way.

    This assertion ran inverted until a rigger caught it in the viewport:
    it was written from the guess that "in" meant the inboard marker, and
    it then pinned that guess rather than the behaviour. The legacy module
    is the authority -- `bankout` at 4*side, `bankin` at 6*side, leg at
    5*side -- and rolling onto an edge pivots about the edge that stays
    down, not the one that lifts.
    """
    for side in ("L", "R"):
        leg = scene.create_guides(get_module("leg")(name="leg", side=side))
        ankle_x = scene.guide_node(leg.instance_id, "ankle").world_position.x
        bank_in_x = scene.guide_node(leg.instance_id, "bank_in").world_position.x
        bank_out_x = scene.guide_node(leg.instance_id, "bank_out").world_position.x

        assert abs(bank_out_x) < abs(ankle_x) < abs(bank_in_x), side
        assert (bank_in_x - ankle_x) * (bank_out_x - ankle_x) < 0.0, side


def test_heel_and_tip_bracket_the_ankle_in_z(scene):
    """``heel`` sits behind the ankle in Z, ``tip`` in front of it.

    The foot's frame is built by aiming heel-to-tip (``systems/foot.py``); if
    the two were swapped here the frame would point backwards and every
    later test would agree with it, since ``systems/foot.py``'s own tests
    build their own hardcoded guides rather than reading the module's.
    """
    for side in ("L", "R"):
        leg = scene.create_guides(get_module("leg")(name="leg", side=side))
        ankle_z = scene.guide_node(leg.instance_id, "ankle").world_position.z
        heel_z = scene.guide_node(leg.instance_id, "heel").world_position.z
        tip_z = scene.guide_node(leg.instance_id, "tip").world_position.z

        assert heel_z < ankle_z < tip_z, side


def _build_leg(scene, side="L", ankle_roll=0.0, **settings):
    """A rigger-authored pose, deliberately not the module's default."""
    body = scene.create_guides(get_module("base")(name="body"))
    leg = scene.create_guides(
        get_module("leg")(name="leg", side=side, settings=settings),
        parent=ParentRef(body.instance_id, "root"),
    )
    mult = -1 if side == "R" else 1
    for role, (x, y, z) in {
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
    }.items():
        cmds.xform(
            scene.guide_node(leg.instance_id, role).long_name,
            ws=True,
            t=(x * mult, y, z),
        )
    if ankle_roll:
        cmds.xform(
            scene.guide_node(leg.instance_id, "ankle").long_name,
            ws=True,
            ro=(0, 0, ankle_roll),
        )
    report = Builder().build(document=scene.document, afterlife="keep")
    return report.rigs[leg.instance_id]


def test_the_bind_chain_runs_hip_to_toe(scene):
    ctx = _build_leg(scene)
    for name in ("hip", "upperleg", "lowerleg", "foot", "ball", "toe"):
        assert ctx.outputs[name] is not None, name


def test_rolling_the_ankle_guide_leaves_the_ball_aimed_at_the_toe(scene):
    """The step the arm never needed.

    The arm's oriented guide is its LAST joint, so re-aligning it disturbs
    nothing. The ankle has the ball and the toe under it: re-orienting a
    joint rotates everything beneath it, so both have to be put back.
    """
    ctx = _build_leg(scene, ankle_roll=30.0)
    ball = ctx.outputs["ball"]
    toe = ctx.outputs["toe"]

    to_toe = toe.world_position - ball.world_position
    to_toe.normalize()
    ball_x = ball.world_axis("x")
    assert (ball_x * to_toe) == pytest.approx(1.0, abs=1e-4)


def test_the_ankle_takes_the_guide_rotation_the_chain_does_not(scene):
    """The one guide whose rotation is read, and only it.

    ``ankle_roll`` is written as an absolute ``ro=(0, 0, ankle_roll)`` onto
    an identity-oriented guide, i.e. a pure rotation *about* world Z -- so
    the Z axis itself is exactly what stays fixed under it (confirmed
    against a bare joint: worldMatrix's Z row is (0, 0, 1) whatever the
    roll). Comparing ``world_axis("z")`` therefore could not have failed
    here no matter what the ankle did with the guide's rotation; ``"x"`` is
    the axis the roll actually moves.
    """
    rolled = _build_leg(scene, ankle_roll=30.0)
    foot_x = rolled.outputs["foot"].world_axis("x")
    # Read before the scene is wiped below: `rolled`'s nodes do not survive
    # `cmds.file(new=True)`, so anything compared against the flat build has
    # to be captured here, not re-read from `rolled.outputs` afterwards.
    rolled_lowerleg_x = rolled.outputs["lowerleg"].world_axis("x")

    cmds.file(new=True, force=True)
    flat_scene = GuideScene()
    flat = _build_leg(flat_scene, ankle_roll=0.0)
    flat_x = flat.outputs["foot"].world_axis("x")

    assert (foot_x * flat_x) < 0.99, "the ankle must follow its guide's roll"
    # ...while the knee above it must not have moved.
    assert (
        rolled_lowerleg_x * flat.outputs["lowerleg"].world_axis("x")
    ) == pytest.approx(1.0, abs=1e-4)


def test_the_ball_and_toe_joints_land_on_their_own_guides(scene):
    """A self-contained, absolute check on what the ball/toe correction does.

    Not a rolled-vs-flat comparison: ``ball`` and ``toe`` are guide
    *children* of ``ankle`` (siblings under it in ``draw_guides``), so
    rotating the ankle guide drags their own guide positions along with
    it too -- a rigger-authored roll moves the guide, not just the bind
    joint. Comparing a rolled build's ball against a flat build's would
    therefore compare two genuinely different guide poses (confirmed by
    reading both guides directly: the ball guide itself sits several tenths
    of a unit apart between the two scenes), not exercise the correction.

    The correction's actual job is narrower and self-contained: whatever
    the ball/toe *guides* end up at, the bind joints must land exactly
    there, roll or no roll. That is what this checks, directly against
    each joint's own guide within a single build.
    """
    ctx = _build_leg(scene, ankle_roll=30.0)
    for role in ("ball", "toe"):
        guide_pos = ctx.guide(role).world_position
        joint_pos = ctx.outputs[role].world_position
        assert (joint_pos - guide_pos).length() < 1e-3, role


def test_auto_hip_is_inert_at_the_guide_pose(scene):
    """The neutral is where the leg is drawn, so raising the scalars must
    not move the hip -- matching the arm's own
    ``test_bind_pose_is_exact_with_the_automation_full_on``.

    The original version of this check compared ``thigh.offset`` against
    identity. That group is a static bake of the hip bind joint's own
    conventional bone orientation (X toward the thigh guide) -- it is
    non-zero purely because the hip and thigh guides are not stacked
    vertically (there is a real X offset between them), and it has nothing
    to do with auto-hip: it is exactly as non-identity with ``auto_hip``
    off, or with the reach network deleted outright. Checking it could never
    have caught a mis-placed neutral guide.

    The real invariant is that raising ``autoHipLift``/``autoHipSwing`` from
    their build-time zero must not move the thigh control at all, which
    holds only because the driven angle is exactly zero at the guide pose --
    i.e. only when the neutral guide really is collinear with hip-to-ankle.
    """
    ctx = _build_leg(scene, auto_hip=True)
    thigh = ctx.controller_by_role("thigh")
    ik = ctx.controller_by_role("ik")
    before = list(thigh.transform["worldMatrix[0]"].value)
    ik.transform["autoHipLift"].value = 1.0
    ik.transform["autoHipSwing"].value = 1.0
    after = list(thigh.transform["worldMatrix[0]"].value)
    for first, second in zip(before, after):
        assert first == pytest.approx(second, abs=1e-4)


def test_auto_hip_off_builds_no_reach_network(scene):
    """No reach network at all when auto_hip is off.

    ``"hip" in node`` (a bare ``Node``, not ``node.name``) is refused by
    ``Node.__contains__`` -- membership testing on a node falls back to
    integer indexing and used to segfault Maya, so it now raises
    ``TypeError`` instead. Comparing against ``node.name`` is what actually
    checks the node's name. The internal reach nodes are named from
    ``build_reach``'s own ``name="hip"`` argument (``L_leg_hip_lift_remapValue``
    / ``L_leg_hip_swing_remapValue``) -- the ``autoHip`` token is only the
    *animator-facing attribute* prefix (``autoHipLift``), never part of an
    internal node's name, so matching for it here would never find anything
    regardless of whether ``build_reach`` ran.

    This also has to prove it discriminates: on a leg that never wires
    ``build_reach`` in at all, "no reach nodes" would hold trivially
    regardless of the flag. The second half re-runs the identical query with
    ``auto_hip=True`` and requires it to find something, or the query would
    still be asserting nothing.
    """
    _build_leg(scene, auto_hip=False)
    assert not [node for node in tm.ls(type="remapValue") if "hip" in node.name]

    cmds.file(new=True, force=True)
    on_scene = GuideScene()
    _build_leg(on_scene, auto_hip=True)
    found = [node for node in tm.ls(type="remapValue") if "hip" in node.name]
    assert found, "auto_hip=True must build a reach network with remapValue nodes"


def test_a_bad_auto_hip_range_is_a_validation_problem():
    leg = get_module("leg")(name="leg", settings={"auto_hip_lift_angles": (10.0, 75.0)})
    problems = leg.validate()
    assert any("auto hip lift" in problem for problem in problems)


def test_the_bind_pose_is_exact_with_every_automation_full_on(scene):
    """Every automation built, every default in place: nothing has moved.

    The arm's own tolerance. A leg that does not reproduce the pose its
    guides describe has an automation whose zero is not zero, and every
    later measurement then reads a pose error rather than the feature.
    """
    ctx = _build_leg(
        scene,
        stretch=True,
        squash=True,
        limb_lock=True,
        auto_hip=True,
        pole_pin=True,
    )
    for name, guide_role in (
        ("upperleg", "thigh"),
        ("lowerleg", "knee"),
        ("foot", "ankle"),
        ("ball", "ball"),
        ("toe", "toe"),
    ):
        expected = scene.guide_node(ctx.instance.instance_id, guide_role).world_position
        actual = ctx.outputs[name].world_position
        # `world_position` is a raw OpenMaya.MVector, which has no
        # `distance_to` (that lives on `Transform`/`Node`, e.g.
        # `pole_base.distance_to(driver)` elsewhere in this codebase) --
        # subtract-and-measure-length is the same computation.
        assert (actual - expected).length() == pytest.approx(0.0, abs=1e-4), name


# ------------------------------------------------------------- limb lock (hip)
#
# The arm's two ``lock_from`` modes are both covered
# (``tests/unit/test_limb_lock_trigger.py``); the leg only ever built the
# default ``"thigh"``. In the ``locks_hip`` branch ``hang_from`` is driven by
# ``build_limb_lock`` *and* read by ``build_reach`` as ``rest_from`` -- the one
# topology on this module where a cycle is plausible -- so this also asserts
# no cycle, not just that the length holds.
def test_thigh_mode_moves_the_upperleg_but_not_the_hip(scene):
    """The default: a thigh-to-ankle lock leaves the hip on the pelvis."""
    ctx = _build_leg(scene, limb_lock=True, lock_from="thigh")
    control = ctx.controller_by_role("ik").transform
    hip = ctx.outputs["hip"]
    upperleg = ctx.outputs["upperleg"]

    control.world_position = (2.0, -15.0, 3.0)
    hip_before, upperleg_before = hip.world_position, upperleg.world_position
    control["limbLock"].value = 1.0

    assert (upperleg.world_position - upperleg_before).length() > 1.0
    assert (
        hip.world_position - hip_before
    ).length() < 1e-3, "the hip should not move in thigh mode"


def test_hip_mode_carries_the_hip_along(scene):
    ctx = _build_leg(scene, limb_lock=True, lock_from="hip")
    control = ctx.controller_by_role("ik").transform
    hip = ctx.outputs["hip"]
    upperleg = ctx.outputs["upperleg"]

    control.world_position = (2.0, -15.0, 3.0)
    hip_before, upperleg_before = hip.world_position, upperleg.world_position
    control["limbLock"].value = 1.0

    assert (upperleg.world_position - upperleg_before).length() > 1.0
    assert (
        hip.world_position - hip_before
    ).length() > 1.0, "the hip should travel with the push in hip mode"


def test_both_lock_modes_hold_the_thigh_to_ankle_length_with_no_cycle(scene):
    for index, mode in enumerate(("thigh", "hip")):
        if index:
            # A fresh scene per mode: `_build_leg` names its instances
            # `body`/`leg` unconditionally, so reusing one scene across
            # iterations would collide on those names.
            cmds.file(new=True, force=True)
            scene = GuideScene()
        ctx = _build_leg(scene, limb_lock=True, lock_from=mode)
        control = ctx.controller_by_role("ik").transform
        upperleg = ctx.outputs["upperleg"]
        ankle_tweak = ctx.controller_by_role("ik_tweak").transform

        rest = control["lockLength"].value
        control["limbLock"].value = 1.0
        for pose in ((2.0, -15.0, 3.0), (-4.0, -8.0, 6.0)):
            control.world_position = pose
            held = (ankle_tweak.world_position - upperleg.world_position).length()
            assert abs(held - rest) < 1e-2, f"{mode} at {pose}: {held} != {rest}"

        for node in ctx.outputs.values():
            node.world_position  # force evaluation
        assert (cmds.cycleCheck(all=True, list=True) or []) == [], mode


# ------------------------------------------------------------------- C1: soft
# IK saturation vs. the reverse foot's ankle driver
def test_pulling_the_ik_control_past_reach_keeps_the_foot_together(scene):
    """A straight-leg contact pose: plant the foot, raise the hips.

    At the shipped ``stretch``/``softIk`` attribute defaults (both 0), the
    limb's soft-IK goal saturates at chain length
    (``SoftIk._build_curve``/``_build_goal`` in ``systems/limb.py``) the
    moment the IK control is pulled past hip-to-ankle reach. Before the fix,
    ``ik_ankle`` hung rigidly off ``foot.ankle_driver``, which keeps
    following the control with no such ceiling, while the limb's actual
    solved ankle (``outputs["foot"]``) stopped at full reach: the ball and
    toe kept travelling with the control, tearing the foot away from the
    shin. Measured on this exact build and pull target: foot-to-ball comes
    back at ``21.7419`` without the fix (rest is ``1.5008``) and at the rest
    distance, within tolerance, with it.
    """
    ctx = _build_leg(scene)
    rest_distance = (
        ctx.outputs["ball"].world_position - ctx.outputs["foot"].world_position
    ).length()

    control = ctx.controller_by_role("ik").transform
    # Straight down through the ankle, and well past hip -> ankle reach
    # (~9.45 units on this module's guide pose).
    control.world_position = (2.0, -20.0, 0.0)

    pulled_distance = (
        ctx.outputs["ball"].world_position - ctx.outputs["foot"].world_position
    ).length()
    assert pulled_distance == pytest.approx(rest_distance, abs=1e-2), (
        f"the foot separated from the shin: rest={rest_distance}, "
        f"pulled={pulled_distance}"
    )
