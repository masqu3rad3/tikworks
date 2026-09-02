"""Tests for the scalar comparison/blend helpers on Plug."""

import tik.maya as tm
from tik.maya.core.constants import NodeNames


def _holder(**attrs):
    node = tm.Transform.create(name="holder")
    plugs = {}
    for name, value in attrs.items():
        plugs[name] = tm.attribute.add_float(node, name, default=value)
    return node, plugs


def test_minimum_picks_the_smaller():
    _node, plugs = _holder(a=5.0)
    result = plugs["a"].minimum(3.0)
    assert abs(result.value - 3.0) < 1e-6
    plugs["a"].value = 1.0
    assert abs(result.value - 1.0) < 1e-6


def test_maximum_picks_the_larger():
    _node, plugs = _holder(a=5.0)
    result = plugs["a"].maximum(8.0)
    assert abs(result.value - 8.0) < 1e-6
    plugs["a"].value = 12.0
    assert abs(result.value - 12.0) < 1e-6


def test_minimum_accepts_a_plug():
    _node, plugs = _holder(a=5.0, b=2.0)
    result = plugs["a"].minimum(plugs["b"])
    assert abs(result.value - 2.0) < 1e-6


def test_clamped_bounds_both_sides():
    _node, plugs = _holder(a=5.0)
    result = plugs["a"].clamped(1.0, 3.0)
    assert abs(result.value - 3.0) < 1e-6
    plugs["a"].value = 0.0
    assert abs(result.value - 1.0) < 1e-6
    plugs["a"].value = 2.0
    assert abs(result.value - 2.0) < 1e-6


def test_lerp_interpolates():
    _node, plugs = _holder(a=0.0, b=10.0, w=0.25)
    result = plugs["a"].lerp(plugs["b"], plugs["w"])
    assert abs(result.value - 2.5) < 1e-6
    plugs["w"].value = 1.0
    assert abs(result.value - 10.0) < 1e-6


def test_gt_switches_branches():
    _node, plugs = _holder(a=5.0)
    result = plugs["a"].gt(10.0, 100.0, -100.0)
    assert abs(result.value - (-100.0)) < 1e-6
    plugs["a"].value = 20.0
    assert abs(result.value - 100.0) < 1e-6


def test_power_uses_a_supported_node():
    _node, plugs = _holder(a=2.0)
    result = plugs["a"] ** 3.0
    assert abs(result.value - 8.0) < 1e-6
    expected = "power" if NodeNames.uses_native_math_nodes else "multiplyDivide"
    assert result.node.type == expected
