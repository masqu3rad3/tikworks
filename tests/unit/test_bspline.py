"""Tests for the pure-Python B-spline basis (no scene needed)."""

import pytest

from tik.core.bspline import basis, clamp_degree, knots


def test_knots_are_clamped_uniform():
    assert knots(4, 3) == [0, 0, 0, 0, 1, 1, 1, 1]
    assert knots(5, 3) == [0, 0, 0, 0, 0.5, 1, 1, 1, 1]
    assert knots(3, 1) == [0, 0, 0.5, 1, 1]


def test_partition_of_unity_and_non_negative():
    for count in range(2, 7):
        for degree in range(0, count):
            for step in range(0, 10):
                weights = basis(step / 10, count, degree)
                assert len(weights) == count
                assert sum(weights) == pytest.approx(1.0)
                assert all(weight >= 0.0 for weight in weights)


def test_endpoints_interpolate():
    assert basis(0.0, 4, 3) == [1.0, 0.0, 0.0, 0.0]
    assert basis(1.0, 4, 3) == [0.0, 0.0, 0.0, 1.0]


def test_degree_one_is_linear():
    assert basis(0.25, 2, 1) == pytest.approx([0.75, 0.25])
    assert basis(0.25, 3, 1) == pytest.approx([0.5, 0.5, 0.0])


def test_degree_two_is_quadratic_bezier_for_three_points():
    assert basis(0.5, 3, 2) == pytest.approx([0.25, 0.5, 0.25])


def test_cubic_symmetry():
    forward = basis(0.3, 5, 3)
    backward = basis(0.7, 5, 3)
    assert forward == pytest.approx(list(reversed(backward)))


def test_clamp_degree():
    assert clamp_degree(2, 3) == 1
    assert clamp_degree(5, 3) == 3
    assert clamp_degree(1, 3) == 0


def test_invalid_arguments():
    with pytest.raises(ValueError):
        basis(0.5, 0, 0)
    with pytest.raises(ValueError):
        basis(0.5, 3, 3)
