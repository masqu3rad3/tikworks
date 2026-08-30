"""Tests for the SoftIk construct.

The three curve properties asserted here are what make the solve *soft*
rather than merely curved.
"""

import math

import tik.maya as tm

L = 10.0


def _rig(soft=1.0, stretch=0.0):
    root = tm.Transform.create(name="soft_root")
    goal = tm.Transform.create(name="soft_goal")
    holder = tm.Transform.create(name="soft_holder")
    length = tm.attribute.add_float(holder, "chainLength", default=L)
    soft_ik = tm.SoftIk.create(root, goal, length, name="soft")
    soft_ik.soft_plug.value = soft
    soft_ik.stretch_plug.value = stretch
    return root, goal, soft_ik


def _at(goal, soft_ik, distance):
    goal.translate = (distance, 0, 0)
    return soft_ik.soft_distance.value


def test_identity_below_the_seam():
    """f(d) == d while d <= da."""
    _root, goal, soft_ik = _rig(soft=1.0)
    for distance in (1.0, 4.0, 8.0):
        assert abs(_at(goal, soft_ik, distance) - distance) < 1e-3


def test_c0_continuity_at_the_seam():
    """f(da) == da, with da = L - ds."""
    _root, goal, soft_ik = _rig(soft=1.0)
    da = L - (1.0 + 0.001)
    assert abs(_at(goal, soft_ik, da) - da) < 1e-3


def test_c1_continuity_at_the_seam():
    """f'(da) == 1 — no velocity discontinuity."""
    _root, goal, soft_ik = _rig(soft=1.0)
    ds = 1.0 + 0.001
    da = L - ds
    step = 1e-3
    at = _at(goal, soft_ik, da)
    above = _at(goal, soft_ik, da + step)
    slope = (above - at) / step
    assert abs(slope - 1.0) < 1e-2


def test_asymptotic_to_chain_length():
    """f(d) -> L from below, so the chain never fully straightens.

    Strictly below is only observable while the exponential term is still
    representable against L; far out it underflows to exactly L in float64.
    """
    _root, goal, soft_ik = _rig(soft=1.0)
    assert _at(goal, soft_ik, 12.0) < L
    assert _at(goal, soft_ik, 20.0) < L
    for distance in (12.0, 20.0, 50.0, 500.0):
        assert _at(goal, soft_ik, distance) <= L + 1e-9
    assert abs(_at(goal, soft_ik, 50.0) - L) < 1e-3


def test_never_overshoots_the_chain_length():
    """The elbow must not pop: f is monotonic and bounded by L."""
    _root, goal, soft_ik = _rig(soft=2.0)
    previous = -1.0
    for distance in [step * 0.5 for step in range(1, 60)]:
        value = _at(goal, soft_ik, distance)
        assert value <= L + 1e-9
        assert value >= previous - 1e-9
        previous = value


def test_matches_the_closed_form_above_the_seam():
    _root, goal, soft_ik = _rig(soft=2.0)
    ds = 2.0 + 0.001
    da = L - ds
    distance = 12.0
    expected = L - ds * math.exp(-(distance - da) / ds)
    assert abs(_at(goal, soft_ik, distance) - expected) < 1e-3


def test_softness_zero_reaches_almost_the_full_length():
    _root, goal, soft_ik = _rig(soft=0.0)
    assert abs(_at(goal, soft_ik, 20.0) - L) < 1e-2


def test_gap_is_zero_without_stretch():
    _root, goal, soft_ik = _rig(soft=1.0, stretch=0.0)
    goal.translate = (20, 0, 0)
    assert abs(soft_ik.gap_plug.value) < 1e-4


def test_gap_is_the_shortfall_with_stretch():
    _root, goal, soft_ik = _rig(soft=1.0, stretch=1.0)
    goal.translate = (20, 0, 0)
    expected = 20.0 - soft_ik.soft_distance.value
    assert abs(soft_ik.gap_plug.value - expected) < 1e-3


def test_goal_matrix_sits_on_the_root_to_goal_ray():
    _root, goal, soft_ik = _rig(soft=1.0, stretch=0.0)
    goal.translate = (0, 20, 0)
    driven = tm.Transform.create(name="soft_probe")
    tm.MatrixConstraint.create(soft_ik.goal_matrix, driven, maintain_offset=False)
    position = driven.world_translation
    assert abs(position.x) < 1e-3 and abs(position.z) < 1e-3
    assert abs(position.y - soft_ik.soft_distance.value) < 1e-3


def test_stretch_one_puts_the_goal_on_the_control():
    _root, goal, soft_ik = _rig(soft=1.0, stretch=1.0)
    goal.translate = (20, 0, 0)
    driven = tm.Transform.create(name="soft_probe_stretch")
    tm.MatrixConstraint.create(soft_ik.goal_matrix, driven, maintain_offset=False)
    assert abs(driven.world_translation.x - 20.0) < 1e-3


def test_chain_length_plug_is_live():
    """Per-segment scale reaches the soft threshold through this plug."""
    _root, goal, soft_ik = _rig(soft=1.0)
    holder = tm.resolve("soft_holder")
    holder["chainLength"].value = 20.0
    assert abs(_at(goal, soft_ik, 100.0) - 20.0) < 1e-2
