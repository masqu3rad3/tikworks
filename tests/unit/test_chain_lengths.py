"""Tests for the ChainLengths construct."""

from maya import cmds

import tik.maya as tm


def _chain(name="cl"):
    return tm.Joint.chain(
        [(0, 0, 0), (4, 0, 0), (10, 0, 0)], name_pattern=name + "_{index}"
    )


def test_rest_plugs_hold_measured_lengths():
    joints = _chain()
    lengths = tm.ChainLengths.create(joints, name="cl")
    assert lengths.segment_count == 2
    assert abs(lengths.rest_plugs[0].value - 4.0) < 1e-4
    assert abs(lengths.rest_plugs[1].value - 6.0) < 1e-4


def test_total_length_sums_the_rest_plugs():
    joints = _chain("total")
    lengths = tm.ChainLengths.create(joints, name="total")
    assert abs(lengths.total_length.value - 10.0) < 1e-4
    lengths.rest_plugs[0].value = 6.0
    assert abs(lengths.total_length.value - 12.0) < 1e-4


def test_no_factors_drives_tx_to_rest():
    joints = _chain("plain")
    tm.ChainLengths.create(joints, name="plain")
    assert abs(joints[1].translate.x - 4.0) < 1e-4
    assert abs(joints[2].translate.x - 6.0) < 1e-4


def test_side_sign_negates_tx():
    joints = _chain("right")
    tm.ChainLengths.create(joints, side_sign=-1, name="right")
    assert abs(joints[1].translate.x - (-4.0)) < 1e-4
    assert abs(joints[2].translate.x - (-6.0)) < 1e-4


def test_rest_plug_drives_tx_live():
    joints = _chain("live")
    lengths = tm.ChainLengths.create(joints, name="live")
    lengths.rest_plugs[0].value = 8.0
    assert abs(joints[1].translate.x - 8.0) < 1e-4


def test_a_factor_scales_every_segment():
    joints = _chain("factor")
    holder = tm.Transform.create(name="factor_holder")
    factor = tm.attribute.add_float(holder, "factor", default=1.0)
    lengths = tm.ChainLengths.create(joints, name="factor")
    lengths.add_factor(factor)
    assert abs(joints[1].translate.x - 4.0) < 1e-4
    factor.value = 2.0
    assert abs(joints[1].translate.x - 8.0) < 1e-4
    assert abs(joints[2].translate.x - 12.0) < 1e-4


def test_factors_multiply_together():
    joints = _chain("two")
    holder = tm.Transform.create(name="two_holder")
    first = tm.attribute.add_float(holder, "first", default=2.0)
    second = tm.attribute.add_float(holder, "second", default=3.0)
    lengths = tm.ChainLengths.create(joints, name="two")
    lengths.add_factor(first)
    lengths.add_factor(second)
    assert abs(joints[1].translate.x - 24.0) < 1e-4


def test_factor_applies_after_the_side_sign():
    """A factor must scale the magnitude, never flip the direction."""
    joints = _chain("signed")
    holder = tm.Transform.create(name="signed_holder")
    factor = tm.attribute.add_float(holder, "factor", default=2.0)
    lengths = tm.ChainLengths.create(joints, side_sign=-1, name="signed")
    lengths.add_factor(factor)
    assert abs(joints[1].translate.x - (-8.0)) < 1e-4


def test_override_blends_towards_explicit_lengths():
    joints = _chain("pin")
    holder = tm.Transform.create(name="pin_holder")
    weight = tm.attribute.add_float(holder, "pin", default=0.0, min=0.0, max=1.0)
    upper = tm.attribute.add_float(holder, "upper", default=9.0)
    lower = tm.attribute.add_float(holder, "lower", default=1.0)
    lengths = tm.ChainLengths.create(joints, name="pin")
    lengths.add_override([upper, lower], weight)
    assert abs(joints[1].translate.x - 4.0) < 1e-4
    weight.value = 1.0
    assert abs(joints[1].translate.x - 9.0) < 1e-4
    assert abs(joints[2].translate.x - 1.0) < 1e-4


def test_delete_releases_the_joints():
    joints = _chain("gone")
    lengths = tm.ChainLengths.create(joints, name="gone")
    lengths.delete()
    assert not cmds.listConnections(
        f"{joints[1].name}.translateX", source=True, destination=False
    )


def test_delete_removes_the_arithmetic_nodes_too():
    """Factors and side-sign multiplies are created by plug arithmetic."""
    joints = _chain("leak")
    holder = tm.Transform.create(name="leak_holder")
    factor = tm.attribute.add_float(holder, "factor", default=2.0)
    weight = tm.attribute.add_float(holder, "pin", default=0.0)
    upper = tm.attribute.add_float(holder, "upper", default=9.0)
    lower = tm.attribute.add_float(holder, "lower", default=1.0)

    before = set(cmds.ls(long=True))
    lengths = tm.ChainLengths.create(joints, side_sign=-1, name="leak")
    lengths.add_factor(factor)
    lengths.add_override([upper, lower], weight)
    lengths.total_length  # noqa: B018 - builds the sum network on access
    lengths.delete()

    leaked = set(cmds.ls(long=True)) - before
    assert not leaked, f"ChainLengths.delete left {sorted(leaked)} behind"
