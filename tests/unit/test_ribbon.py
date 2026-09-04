"""Tests for the pure-math Ribbon construct."""

import math

import pytest
from approx import axes, close
from maya import cmds

import tik.maya as tm
from tik.core.bspline import basis
from tik.maya.constructs.ribbon import Ribbon


def _endpoints():
    start = tm.Transform.create(name="start")
    end = tm.Transform.create(name="end")
    end.translate = (10, 0, 0)
    return start, end


def test_ribbon_creates_expected_nodes():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="upArm", joint_count=4, mid_count=1)
    assert len(ribbon.deformer_joints) == 4
    assert len(ribbon.mid_plugs) == 1
    assert ribbon.group.name == "upArm_ribbon_grp"
    assert ribbon.start_plug.parent.name == ribbon.group.name
    assert ribbon.deformer_joints[0].name == "upArm_0_jnt"
    assert ribbon.mid_plugs[0].name == "upArm_mid0_plug"
    assert not cmds.ls(type=["nurbsSurface", "follicle", "skinCluster"])
    assert ribbon.spline.degree == 2  # start + mid + end clamps cubic to quadratic
    assert ribbon.control_spline.degree == 1


def test_joints_are_distributed_between_endpoints():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3, mid_count=0)
    assert ribbon.control_spline is None
    for index, joint in enumerate(ribbon.deformer_joints):
        assert close(joint.world_translation, (10 * (index + 0.5) / 3, 0, 0))


def test_joints_match_basis_weighted_positions_after_bending():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=5, mid_count=1)
    ribbon.mid_plugs[0].translate = (0, 3, 0)
    positions = [(0, 0, 0), (5, 3, 0), (10, 0, 0)]
    for index, joint in enumerate(ribbon.deformer_joints):
        weights = basis((index + 0.5) / 5, 3, 2)
        expected = [
            sum(weight * position[axis] for weight, position in zip(weights, positions))
            for axis in range(3)
        ]
        assert close(joint.world_translation, expected)


def test_plugs_sit_on_endpoints_and_joints_aim_along_strip():
    start, end = _endpoints()
    end.translate = (0, 10, 0)
    ribbon = Ribbon.create(start, end, name="rbn", up_vector=(0, 0, 1))
    assert close(ribbon.start_plug.world_translation, start.world_translation)
    assert close(ribbon.end_plug.world_translation, end.world_translation)
    x_axis, y_axis = axes(ribbon.deformer_joints[0])
    assert close(x_axis, (0, 1, 0))
    assert close(y_axis, (0, 0, 1))


def test_deformer_joints_are_flat_with_live_channels():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=2, mid_count=0)
    for joint in ribbon.deformer_joints:
        assert joint.parent.name == ribbon.joint_group.name
        assert joint["rotateOrder"].value == 0
        assert not cmds.listConnections(
            f"{joint.long_name}.offsetParentMatrix", source=True, destination=False
        )
        assert close(joint.translate, joint.world_translation)
    ribbon.end_plug.translate = (5, 4, 0)
    assert ribbon.deformer_joints[1]["translateY"].value == pytest.approx(3.0, abs=1e-4)
    assert ribbon.deformer_joints[1]["translateX"].value == pytest.approx(7.5, abs=1e-4)


def test_mid_plug_follows_ends():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", mid_count=1)
    ribbon.start_plug.translate = (-5, 4, 0)
    ribbon.end_plug.translate = (5, 4, 0)
    assert ribbon.mid_plugs[0].world_translation.y == pytest.approx(4, abs=1e-3)


def test_twist_interpolates_as_unbounded_floats():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3, mid_count=0)
    ribbon.end_twist.value = 270.0
    for index, joint in enumerate(ribbon.deformer_joints):
        angle = 270 * (index + 0.5) / 3  # 45, 135, 225
        assert joint["rotateX"].value == pytest.approx(angle, abs=1e-3)
        x_axis, y_axis = axes(joint)
        assert close(x_axis, (1, 0, 0))
        assert close(
            y_axis, (0, math.cos(math.radians(angle)), math.sin(math.radians(angle)))
        )


def test_mid_plug_roll_adds_local_twist():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3, mid_count=1)
    ribbon.mid_plugs[0].rotate = (90, 0, 0)
    weights = basis(0.5, 3, 2)
    assert ribbon.deformer_joints[1]["rotateX"].value == pytest.approx(
        weights[1] * 90, abs=1e-3
    )
    assert close(ribbon.deformer_joints[1].world_translation, (5, 0, 0))


def test_start_roll_beyond_180_with_twist_wired_does_not_flip():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3, mid_count=0)
    ribbon.start_plug["rotateX"] >> ribbon.start_twist
    ribbon.end_plug["rotateX"] >> ribbon.end_twist
    ribbon.start_plug.rotate = (270, 0, 0)
    ribbon.end_plug.rotate = (270, 0, 0)
    for joint in ribbon.deformer_joints:
        assert joint["rotateX"].value == pytest.approx(270, abs=1e-3)
        x_axis, y_axis = axes(joint)
        assert close(x_axis, (1, 0, 0))
        assert close(y_axis, (0, 0, -1))


def test_invalid_arguments():
    start, end = _endpoints()
    with pytest.raises(ValueError):
        Ribbon.create(start, end, name="rbn", joint_count=0)
    end.translate = (0, 0, 0)
    with pytest.raises(ValueError):
        Ribbon.create(start, end, name="rbn")


def test_pinning_end_stretches_ribbon():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3)
    ribbon.pin_start(start)
    ribbon.pin_end(end)
    end.translate = (20, 0, 0)
    xs = sorted(joint.world_translation.x for joint in ribbon.deformer_joints)
    assert xs[-1] > 10


def test_scaleable_switch_drives_joint_scale():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", scaleable=True)
    assert ribbon.scale_switch is not None
    assert ribbon.scale_switch.value == 1.0
    assert ribbon.measure.node.name == "rbn_ribbon_distance"
    ribbon.pin_end(end)
    end.translate = (20, 0, 0)
    assert ribbon.deformer_joints[0]["scaleX"].value == pytest.approx(2.0, abs=1e-4)
    assert ribbon.deformer_joints[0]["scaleY"].value == pytest.approx(1.0, abs=1e-4)
    ribbon.scale_switch.value = 0.0
    assert ribbon.deformer_joints[0]["scaleX"].value == pytest.approx(1.0, abs=1e-4)


def test_preserve_volume():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", scaleable=True, preserve_volume=True)
    ribbon.pin_end(end)
    end.translate = (40, 0, 0)
    assert ribbon.deformer_joints[0]["scaleX"].value == pytest.approx(4.0, abs=1e-4)
    assert ribbon.deformer_joints[0]["scaleY"].value == pytest.approx(0.5, abs=1e-4)
    assert ribbon.deformer_joints[0]["scaleZ"].value == pytest.approx(0.5, abs=1e-4)


def test_not_scaleable():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", scaleable=False)
    assert ribbon.scale_switch is None
    assert ribbon.measure is None
    ribbon.pin_end(end)
    end.translate = (20, 0, 0)
    assert ribbon.deformer_joints[0]["scaleX"].value == pytest.approx(1.0, abs=1e-4)


def test_pinned_start_roll_with_wired_twist_follows_without_flip():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=2, mid_count=0)
    ribbon.pin_start(start)
    ribbon.pin_end(end)
    start["rotateX"] >> ribbon.start_twist
    end["rotateX"] >> ribbon.end_twist
    start.rotate = (450, 0, 0)
    end.rotate = (450, 0, 0)
    for joint in ribbon.deformer_joints:
        assert joint["rotateX"].value == pytest.approx(450, abs=1e-3)
        x_axis, y_axis = axes(joint)
        assert close(x_axis, (1, 0, 0))
        assert close(y_axis, (0, 0, 1))


def test_delete():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn")
    ribbon.delete()
    assert not cmds.objExists("rbn_ribbon_grp")
    assert not cmds.objExists("rbn_ribbon_distance")
    assert not cmds.ls(
        type=[
            "parentMatrix",
            "pickMatrix",
            "aimMatrix",
            "decomposeMatrix",
            "composeMatrix",
        ]
    )


def test_create_is_one_undo_step():
    start, end = _endpoints()
    Ribbon.create(start, end, name="rbn")
    cmds.undo()
    assert not cmds.objExists("rbn_ribbon_grp")


def test_ribbon_creates_no_controllers():
    """A tik.maya construct never creates a controller (animator-opinion rule)."""
    import inspect

    from tik.maya.constructs import ribbon as ribbon_module

    source = inspect.getsource(ribbon_module)
    assert "Controller.create" not in source
    assert "from ..roles" not in source


def test_pin_mid_drives_the_strip():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="pin", joint_count=5, mid_count=1)
    driver = tm.Transform.create(name="mid_driver")
    driver.snap_to(ribbon.mid_plugs[0])
    ribbon.pin_mid(0, driver)
    before = ribbon.deformer_joints[2].world_position
    driver.translate = (
        driver.translate[0],
        driver.translate[1] + 5.0,
        driver.translate[2],
    )
    after = ribbon.deformer_joints[2].world_position
    assert (after - before).length() > 1e-3


def test_mid_frames_parent_the_plugs():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="frm", joint_count=4, mid_count=2)
    assert len(ribbon.mid_frames) == 2 and len(ribbon.mid_plugs) == 2
    for frame, plug in zip(ribbon.mid_frames, ribbon.mid_plugs):
        assert plug.parent.long_name == frame.long_name
