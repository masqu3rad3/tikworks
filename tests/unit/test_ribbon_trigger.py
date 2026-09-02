"""Tests for the ribbon trigger module."""

from maya import cmds

import tik.trigger as trigger
from tik.trigger.core import get_module
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder, tags
from tik.trigger.modules.ribbon.ribbon import RibbonModule


def test_ribbon_module_is_registered():
    trigger.load_plugins()
    assert get_module("ribbon") is RibbonModule


def test_output_names_follow_the_joint_count():
    assert RibbonModule.output_names({"joint_count": 3}) == (
        "joint0", "joint1", "joint2",
    )


def _built(**settings):
    trigger.load_plugins()
    guides = GuideScene()
    guides.clear()
    body = guides.add("base", name="body")
    strip = guides.add("ribbon", side="L", name="upper", parent=body, **settings)
    guides.connect("L_upper.end", "body.root")
    report = Builder().build(document=guides.document, rig_name="rbn", afterlife="keep")
    return report.rigs[strip.instance_id]


def test_mid_controllers_are_module_owned():
    ctx = _built(joint_count=4, mid_count=2)
    assert len(ctx.controllers) == 2
    for controller in ctx.controllers:
        transform = controller.transform
        assert transform.meta.get(tags.KIND) == tags.CONTROLLER
        assert controller.offset is not None
        # in control_grp, via its offset group
        assert controller.offset.parent.name == ctx.groups.control.name


def test_bind_joints_are_real_and_outside_the_ribbon_group():
    ctx = _built(joint_count=3, mid_count=1)
    assert len(ctx.outputs) == 3
    for index in range(3):
        joint = f"L_upper_joint{index}_jnt"
        assert cmds.objExists(joint)
        # driven by its ribbon joint, and not living in the non-inheriting group
        assert cmds.listConnections(f"{joint}.translate", source=True, destination=False)
        assert "ribbon_grp" not in (cmds.listRelatives(joint, parent=True) or [""])[0]


def test_twist_plugs_are_fed():
    """start_twist and end_twist must have a driver, not sit at zero."""
    _built(joint_count=3, mid_count=1)
    for suffix in ("start_plug", "end_plug"):
        found = cmds.ls(f"*_{suffix}")
        assert found, f"no {suffix} was built"
        assert cmds.listConnections(
            f"{found[0]}.twist", source=True, destination=False
        ), f"{found[0]}.twist has no driver"


def test_moving_a_mid_controller_deforms_the_strip():
    ctx = _built(joint_count=5, mid_count=1)
    joint = ctx.outputs["joint2"]
    before = joint.world_position
    ctx.controllers[0].transform.translate = (0, 4, 0)
    after = joint.world_position
    assert (after - before).length() > 1e-3
