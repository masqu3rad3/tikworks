"""Integration tests for the reach system.

The driver is a position, so these tests move a target and read the driven
group's rotation. No limb is built here -- the FK branch and the ikFk blend
are exercised by the arm tests, which have real FK controls.
"""

import math

from maya import cmds

import tik.maya as tm
from tik.trigger.systems.reach import ReachAxis, build_reach

LIFT = ReachAxis(min_angle=-60.0, max_angle=75.0, min_output=-6.0, max_output=15.0)
SWING = ReachAxis(min_angle=-45.0, max_angle=60.0, min_output=-6.0, max_output=10.0)

ORIGIN = 2.0
NEUTRAL = (16.0, 0.0, 0.0)


def _setup(ctx, lift=LIFT, swing=SWING, **kwargs):
    """A socket, an origin, a target, and the reach driving a group."""
    socket = tm.Transform.create(name="reach_socket", parent=ctx.groups.socket.long_name)
    origin = tm.Transform.create(name="reach_origin", parent=socket.long_name)
    origin.translate = (ORIGIN, 0, 0)
    holder = tm.Transform.create(name="reach_holder", parent=ctx.groups.rig.long_name)
    target = tm.Transform.create(name="reach_target", parent=ctx.groups.control.long_name)
    target.translate = (14, 0, 0)
    control = ctx.controller("reach_ctrl", mirror="world")
    reach = build_reach(
        ctx, holder, origin, socket, NEUTRAL, target, control.transform,
        prefix="autoCollar", lift=lift, swing=swing, name="reach", **kwargs
    )
    return socket, target, control.transform, reach


def _rotation(reach):
    """The driven group's local rotation, in degrees."""
    return tuple(reach.group.rotate)


def _lift(reach):
    return _rotation(reach)[2]


def _swing(reach):
    return _rotation(reach)[1]


def _place(target, elevation_deg, azimuth_deg=0.0, distance=12.0):
    """Put the target at an angle off the +X neutral line, about the origin."""
    elevation = math.radians(elevation_deg)
    azimuth = math.radians(azimuth_deg)
    target.translate = (
        ORIGIN + distance * math.cos(elevation) * math.cos(azimuth),
        distance * math.sin(elevation),
        distance * math.cos(elevation) * math.sin(azimuth),
    )


# ------------------------------------------------------------------ surface


def test_adds_exactly_two_attributes(build_context):
    _socket, _target, control, _reach = _setup(build_context())
    assert control.has_attr("autoCollarLift")
    assert control.has_attr("autoCollarSwing")
    assert not control.has_attr("autoCollar")
    assert not control.has_attr("autoCollarVertical")
    assert not control.has_attr("autoCollarHorizontal")
    assert abs(control["autoCollarLift"].value) < 1e-6
    assert abs(control["autoCollarSwing"].value) < 1e-6


def test_off_is_inert(build_context):
    _socket, target, _control, reach = _setup(build_context())
    before = _rotation(reach)
    _place(target, 60.0, 40.0)
    assert all(abs(actual - expected) < 1e-4 for actual, expected in zip(_rotation(reach), before))


# ------------------------------------------------------------- the neutral


def test_the_neutral_direction_produces_no_rotation(build_context):
    """The regression test for the two-zeros bug."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    control["autoCollarSwing"].value = 1.0
    _place(target, 0.0, 0.0)
    assert all(abs(value) < 1e-4 for value in _rotation(reach))


def test_the_sign_flips_across_the_neutral(build_context):
    """The collar must not dip on its way up."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    _place(target, 20.0)
    above = _lift(reach)
    _place(target, -20.0)
    below = _lift(reach)
    assert above > 0.0 > below


def test_the_scalar_never_moves_the_neutral(build_context):
    """The regression test for the old input-side multipliers."""
    _socket, target, control, reach = _setup(build_context())
    _place(target, 0.0)
    for scalar in (0.0, 0.25, 0.5, 1.0):
        control["autoCollarLift"].value = scalar
        control["autoCollarSwing"].value = scalar
        assert all(abs(value) < 1e-4 for value in _rotation(reach))


# ------------------------------------------------------------- saturation


def test_lift_is_monotonic_from_the_neutral_to_the_limit(build_context):
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    samples = []
    for elevation in range(0, 76, 5):
        _place(target, float(elevation))
        samples.append(_lift(reach))
    assert all(later >= earlier - 1e-6 for earlier, later in zip(samples, samples[1:])), samples
    assert abs(samples[-1] - LIFT.max_output) < 1e-3


def test_saturates_past_the_upper_limit(build_context):
    """Today's mechanism reaches +139 degrees at +120. This one stops."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    _place(target, 75.0)
    at_limit = _lift(reach)
    _place(target, 89.0)
    assert abs(_lift(reach) - at_limit) < 1e-3
    assert abs(at_limit - LIFT.max_output) < 1e-3


def test_saturates_below_the_lower_limit(build_context):
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    _place(target, -60.0)
    at_limit = _lift(reach)
    _place(target, -85.0)
    assert abs(_lift(reach) - at_limit) < 1e-3
    assert abs(at_limit - LIFT.min_output) < 1e-3


# ------------------------------------------------------------- smoothness


def test_no_hard_corner_at_the_limit(build_context):
    """Finite differences either side of the limit must both be near zero."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    readings = {}
    for elevation in (73.0, 74.0, 76.0, 77.0):
        _place(target, elevation)
        readings[elevation] = _lift(reach)
    inside = readings[74.0] - readings[73.0]
    outside = readings[77.0] - readings[76.0]
    assert abs(inside) < 0.05, inside
    assert abs(outside) < 1e-6


def test_no_hard_corner_at_the_neutral(build_context):
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    readings = {}
    for elevation in (-2.0, -1.0, 1.0, 2.0):
        _place(target, elevation)
        readings[elevation] = _lift(reach)
    below = readings[-1.0] - readings[-2.0]
    above = readings[2.0] - readings[1.0]
    assert abs(below - above) < 0.05, (below, above)


# ----------------------------------------------------------------- the axes


def test_the_axes_are_independent(build_context):
    """The per-axis test that proves each strand reached its own remap."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    control["autoCollarSwing"].value = 0.0
    _place(target, 0.0, 60.0)
    assert all(abs(value) < 1e-3 for value in _rotation(reach))
    control["autoCollarSwing"].value = 1.0
    assert abs(_swing(reach)) > 1.0


def test_swing_tilts_the_group_toward_the_target(build_context):
    """Direction, not just antisymmetry.

    This test used to assert only that `rotateY` flipped sign across the
    neutral -- which a completely inverted rig satisfies too, and that is
    exactly how the swing sign error shipped. Assert where the group's own
    X axis actually points instead.
    """
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarSwing"].value = 1.0
    _place(target, 0.0, 30.0)
    forward = reach.group.world_axis("x")[2]
    _place(target, 0.0, -30.0)
    back = reach.group.world_axis("x")[2]
    assert forward > 0.0 > back, (forward, back)


def test_lift_tilts_the_group_toward_the_target(build_context):
    """The same, for elevation."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    _place(target, 30.0)
    up = reach.group.world_axis("x")[1]
    _place(target, -30.0)
    down = reach.group.world_axis("x")[1]
    assert up > 0.0 > down, (up, down)


def test_the_scalars_scale_the_output(build_context):
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    _place(target, 60.0)
    full = _lift(reach)
    control["autoCollarLift"].value = 0.5
    assert abs(_lift(reach) - full * 0.5) < 1e-3


def test_the_folded_arm_does_not_wrap(build_context):
    """atan2(y, hypot(x, z)) has no branch cut; atan2(y, x) does."""
    _socket, target, control, reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    _place(target, 10.0, 170.0)
    across = _lift(reach)
    _place(target, 10.0, 190.0)
    assert abs(_lift(reach) - across) < 1.0


# ------------------------------------------------------------ ground rules


def test_does_not_cycle(build_context):
    _socket, _target, control, _reach = _setup(build_context())
    control["autoCollarLift"].value = 1.0
    control["autoCollarSwing"].value = 1.0
    cmds.dgdirty(allPlugs=True)
    assert not (cmds.cycleCheck(all=True) or [])


def test_everything_is_parented(build_context):
    """Ground rule nine: a system parents everything it creates."""
    ctx = build_context()
    before = set(cmds.ls(assemblies=True, long=True))
    _setup(ctx)
    assert set(cmds.ls(assemblies=True, long=True)) == before
