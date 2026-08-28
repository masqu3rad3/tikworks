"""Tests for the Ribbon construct."""

from maya import cmds

import tik.maya as tm
from tik.maya.constructs.ribbon import Ribbon


def _endpoints():
    start = tm.Transform.create(name="start")
    end = tm.Transform.create(name="end")
    end.translate = (10, 0, 0)
    return start, end


def test_ribbon_creates_expected_nodes():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="upArm", joint_count=4, controller_count=1)
    assert len(ribbon.deformer_joints) == 4
    assert len(ribbon.controllers) == 1
    assert ribbon.surface.type == "nurbsSurface"
    assert ribbon.group.name == "upArm_ribbon_grp"
    assert ribbon.start_plug.parent.name == ribbon.scale_group.name
    assert ribbon.skin_cluster.type == "skinCluster"
    assert len(ribbon.bind_joints) == 3


def test_joints_are_distributed_between_endpoints():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3)
    xs = sorted(jnt.world_translation.x for jnt in ribbon.deformer_joints)
    assert 0 < xs[0] < xs[1] < xs[2] < 10
    assert all(abs(jnt.world_translation.y) < 1e-4 for jnt in ribbon.deformer_joints)


def test_plugs_sit_on_endpoints():
    start, end = _endpoints()
    end.translate = (0, 10, 0)
    ribbon = Ribbon.create(start, end, name="rbn", up_vector=(0, 0, 1))
    assert (ribbon.start_plug.world_translation - start.world_translation).length() < 1e-4
    assert (ribbon.end_plug.world_translation - end.world_translation).length() < 1e-4


def test_pinning_end_stretches_ribbon():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3)
    ribbon.pin_start(start)
    ribbon.pin_end(end)
    end.translate = (20, 0, 0)
    xs = sorted(jnt.world_translation.x for jnt in ribbon.deformer_joints)
    assert xs[-1] > 10


def test_scaleable_switch_drives_joint_scale():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", scaleable=True)
    assert ribbon.scale_switch is not None
    assert ribbon.scale_switch.value == 1.0
    ribbon.pin_end(end)
    end.translate = (20, 0, 0)
    assert abs(ribbon.deformer_joints[0]["scaleX"].value - 2.0) < 1e-4
    ribbon.scale_switch.value = 0.0
    assert abs(ribbon.deformer_joints[0]["scaleX"].value - 1.0) < 1e-4


def test_not_scaleable():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", scaleable=False)
    assert ribbon.scale_switch is None
    assert not cmds.listConnections(f"{ribbon.deformer_joints[0].name}.sx", source=True, destination=False)


def test_mid_controller_follows_ends():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", controller_count=1)
    ribbon.pin_start(start)
    ribbon.pin_end(end)
    start.translate = (0, 4, 0)
    end.translate = (10, 4, 0)
    assert abs(ribbon.controllers[0].transform.world_translation.y - 4) < 1e-3


def test_delete():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn")
    ribbon.delete()
    assert not cmds.objExists("rbn_ribbon_grp")
    assert not cmds.objExists("rbn_ribbon_distance")
