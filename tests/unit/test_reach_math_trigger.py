"""The reach ramp arithmetic, which decides where the neutral lands."""

import pytest

from tik.trigger.systems.reach import ReachAxis


def test_the_middle_point_puts_zero_on_zero():
    axis = ReachAxis(min_angle=-40.0, max_angle=60.0, min_output=-8.0, max_output=22.0)
    points = axis.ramp_points()
    assert len(points) == 3
    assert points[0] == (0.0, 0.0)
    assert points[2] == (1.0, 1.0)
    position, value = points[1]
    assert abs(position - 0.4) < 1e-9
    assert abs(value - 8.0 / 30.0) < 1e-9


def test_the_middle_point_reconstructs_zero_output():
    """position -> value -> output must come back to exactly zero."""
    axis = ReachAxis(min_angle=-60.0, max_angle=75.0, min_output=-6.0, max_output=15.0)
    _position, value = axis.ramp_points()[1]
    output = axis.min_output + value * (axis.max_output - axis.min_output)
    assert abs(output) < 1e-9


def test_a_symmetric_axis_puts_the_neutral_in_the_middle():
    axis = ReachAxis(min_angle=-60.0, max_angle=60.0, min_output=-10.0, max_output=10.0)
    position, value = axis.ramp_points()[1]
    assert abs(position - 0.5) < 1e-9
    assert abs(value - 0.5) < 1e-9


def test_the_middle_point_stays_inside_the_ramp():
    """A point at 0.0 or 1.0 would collide with an endpoint."""
    axis = ReachAxis(min_angle=-1.0, max_angle=89.0, min_output=-0.5, max_output=20.0)
    position, value = axis.ramp_points()[1]
    assert 0.0 < position < 1.0
    assert 0.0 < value < 1.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_angle": 10.0, "max_angle": 60.0},    # neutral outside the range
        {"min_angle": -60.0, "max_angle": -10.0},  # neutral outside the range
        {"min_angle": 0.0, "max_angle": 60.0},     # neutral on the boundary
        {"min_angle": -60.0, "max_angle": 0.0},    # neutral on the boundary
    ],
)
def test_rejects_a_neutral_outside_the_input_range(kwargs):
    axis = ReachAxis(min_output=-5.0, max_output=5.0, **kwargs)
    with pytest.raises(ValueError, match="lift"):
        axis.validate("lift")


def test_rejects_an_inverted_output_range():
    axis = ReachAxis(min_angle=-45.0, max_angle=45.0, min_output=10.0, max_output=-10.0)
    with pytest.raises(ValueError, match="swing"):
        axis.validate("swing")


def test_rejects_a_flat_output_range():
    axis = ReachAxis(min_angle=-45.0, max_angle=45.0, min_output=5.0, max_output=5.0)
    with pytest.raises(ValueError, match="swing"):
        axis.validate("swing")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_angle": -90.0, "max_angle": 75.0},
        {"min_angle": -60.0, "max_angle": 90.0},
        {"min_angle": -120.0, "max_angle": 75.0},
        {"min_angle": -60.0, "max_angle": 120.0},
    ],
)
def test_rejects_a_limit_the_driver_can_never_reach(kwargs):
    """Off-plane angles saturate at +/-90, so a wider limit never completes."""
    axis = ReachAxis(min_output=-5.0, max_output=5.0, **kwargs)
    with pytest.raises(ValueError, match="90"):
        axis.validate("lift")


def test_a_valid_axis_validates_silently():
    ReachAxis(
        min_angle=-60.0, max_angle=75.0, min_output=-6.0, max_output=15.0
    ).validate("lift")
