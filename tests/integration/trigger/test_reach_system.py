"""Integration tests for the reach system."""

from maya import cmds

import tik.maya as tm
from tik.trigger.systems.reach import build_reach


def _setup(ctx, **kwargs):
    """A socket, a base to drive, and a target standing in for the IK hand."""
    socket = tm.Transform.create(name="reach_socket", parent=ctx.groups.socket.long_name)
    base = tm.Transform.create(name="reach_base", parent=ctx.groups.control.long_name)
    base.translate = (2, 0, 0)
    target = tm.Transform.create(name="reach_target", parent=ctx.groups.control.long_name)
    target.translate = (12, 0, 0)
    control = ctx.controller("reach_ctrl", mirror="world")
    build_reach(
        ctx, base, socket, target, control.transform,
        prefix="autoCollar", name="reach", **kwargs
    )
    return socket, base, target, control.transform


def _matrix(node):
    return list(node["worldMatrix[0]"].value)


def _close(first, second, tolerance=1e-4):
    return all(abs(a - b) < tolerance for a, b in zip(first, second))


def test_adds_the_three_attributes(build_context):
    _socket, _base, _target, control = _setup(build_context())
    assert control.has_attr("autoCollar")
    assert control.has_attr("autoCollarVertical")
    assert control.has_attr("autoCollarHorizontal")
    assert abs(control["autoCollar"].value) < 1e-6
    assert abs(control["autoCollarVertical"].value - 0.5) < 1e-6
    assert abs(control["autoCollarHorizontal"].value - 0.5) < 1e-6


def test_off_is_inert(build_context):
    _socket, base, target, _control = _setup(build_context())
    before = _matrix(base)
    target.translate = (12, 20, 8)
    assert _close(_matrix(base), before)


def test_below_the_start_angle_is_inert(build_context):
    """Catches an inverted or unclamped remap."""
    _socket, base, target, control = _setup(
        build_context(), start_angle=30.0, end_angle=60.0
    )
    control["autoCollar"].value = 1.0
    before = _matrix(base)
    target.translate = (12, 0.2, 0)  # a fraction of a degree off the rest direction
    assert _close(_matrix(base), before, tolerance=1e-3)


def test_above_the_start_angle_moves(build_context):
    _socket, base, target, control = _setup(
        build_context(), start_angle=5.0, end_angle=45.0
    )
    control["autoCollar"].value = 1.0
    before = _matrix(base)
    target.translate = (12, 12, 0)
    assert not _close(_matrix(base), before, tolerance=1e-3)


def test_zero_vertical_ignores_vertical_motion(build_context):
    """The per-axis test: proves the multipliers reach the right components."""
    _socket, base, target, control = _setup(build_context())
    control["autoCollar"].value = 1.0
    control["autoCollarVertical"].value = 0.0
    control["autoCollarHorizontal"].value = 1.0
    before = _matrix(base)
    target.translate = (12, 20, 0)
    assert _close(_matrix(base), before, tolerance=1e-3)
    target.translate = (12, 0, 20)
    assert not _close(_matrix(base), before, tolerance=1e-3)


def test_does_not_cycle(build_context):
    _socket, _base, _target, control = _setup(build_context())
    control["autoCollar"].value = 1.0
    cmds.dgdirty(allPlugs=True)
    assert not (cmds.cycleCheck(all=True) or [])


def test_everything_is_parented(build_context):
    """Ground rule nine: a system parents everything it creates."""
    ctx = build_context()
    before = set(cmds.ls(assemblies=True, long=True))
    _setup(ctx)
    assert set(cmds.ls(assemblies=True, long=True)) == before
