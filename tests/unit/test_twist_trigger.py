"""Tests for the twist extractor and the twist module."""

import pytest

import tik.maya as tm
from tik.trigger.systems.twist import dominant_axis, twist_plug


def _pair(rest_rotation=(0.0, 0.0, 0.0)):
    """A reference transform and a child driver, optionally rested off-identity."""
    reference = tm.Transform.create(name="ref")
    driver = tm.Transform.create(name="drv", parent=reference.long_name)
    driver.translate = (5, 0, 0)
    driver.rotate = rest_rotation
    return reference, driver


# --------------------------------------------------------------- matrix source
def test_matrix_source_is_zero_at_rest():
    reference, driver = _pair(rest_rotation=(20.0, 15.0, -10.0))
    plug = twist_plug(driver, reference, name="fore", axis="X", source="matrix")
    assert abs(plug.value) < 1e-4


def test_matrix_source_tracks_the_driver():
    reference, driver = _pair()
    plug = twist_plug(driver, reference, name="fore", axis="X", source="matrix")
    for angle in (30.0, 90.0, 170.0, -170.0):
        driver.rotate = (angle, 0, 0)
        assert abs(plug.value - angle) < 1e-3


def test_matrix_source_ignores_swing():
    reference, driver = _pair()
    plug = twist_plug(driver, reference, name="fore", axis="X", source="matrix")
    driver.rotate = (120.0, 0, 0)
    baseline = plug.value
    for swing in (30.0, 60.0):
        driver.rotate = (120.0, swing, 0)
        assert abs(plug.value - baseline) < 1e-3


def test_matrix_source_wraps_past_180():
    """The documented bound. See spec section 2.1 -- a rotation matrix for 200
    degrees is identical to the matrix for -160, so no quaternion wiring can
    recover the difference. Asserted so nobody re-attempts the slerp trick.
    """
    reference, driver = _pair()
    plug = twist_plug(driver, reference, name="fore", axis="X", source="matrix")
    driver.rotate = (200.0, 0, 0)
    assert abs(plug.value - (-160.0)) < 1e-3


def test_dominant_axis_picks_the_chain_axis():
    start = tm.Transform.create(name="a")
    end = tm.Transform.create(name="b")
    end.translate = (7, 0, 0)
    assert dominant_axis(start, end)[0] == "X"
    end.translate = (0, 0, -7)
    axis, direction = dominant_axis(start, end)
    assert axis == "Z" and direction == -1


# -------------------------------------------------------------- channel source
def test_channel_source_is_unbounded():
    reference, driver = _pair()
    driver["rotateOrder"].value = 0  # xyz -- X applied innermost
    plug = twist_plug(driver, reference, name="prop", axis="X", source="channel")
    previous = None
    for step in range(-80, 81):
        angle = step * 5.0
        driver.rotate = (angle, 0, 0)
        value = plug.value
        assert abs(value - angle) < 1e-3
        if previous is not None:
            assert abs(value - previous) < 10.0  # no wrap anywhere in +/-400
        previous = value


def test_channel_source_is_zero_at_rest():
    reference, driver = _pair(rest_rotation=(35.0, 0.0, 0.0))
    plug = twist_plug(driver, reference, name="prop", axis="X", source="channel")
    assert abs(plug.value) < 1e-4
    driver.rotate = (395.0, 0, 0)
    assert abs(plug.value - 360.0) < 1e-3


def test_channel_source_rejects_an_invalid_driver():
    reference = tm.Transform.create(name="ref")
    driver = tm.Transform.create(name="drv")
    with pytest.raises(ValueError, match="channel source"):
        twist_plug(driver, reference, name="bad", axis="X", source="channel")


# ----------------------------------------------------------------- auto source
def test_auto_prefers_the_channel_when_valid():
    reference, driver = _pair()
    driver["rotateOrder"].value = 0
    plug = twist_plug(driver, reference, name="prop", axis="X", source="auto")
    driver.rotate = (400.0, 0, 0)
    assert abs(plug.value - 400.0) < 1e-3  # unbounded => the channel was used


def test_auto_falls_back_to_matrix_when_not_parented():
    reference = tm.Transform.create(name="ref")
    driver = tm.Transform.create(name="drv")  # not a child of reference
    driver.translate = (5, 0, 0)
    plug = twist_plug(driver, reference, name="fore", axis="X", source="auto")
    driver.rotate = (200.0, 0, 0)
    assert abs(plug.value - (-160.0)) < 1e-3  # bounded => the matrix was used


def test_auto_falls_back_to_matrix_on_a_bad_rotate_order():
    reference, driver = _pair()
    driver["rotateOrder"].value = 1  # yzx -- X is outermost, not a pure roll
    plug = twist_plug(driver, reference, name="fore", axis="X", source="auto")
    driver.rotate = (200.0, 0, 0)
    assert abs(plug.value - (-160.0)) < 1e-3


# ---------------------------------------------------------------- the module
def test_twist_module_is_registered():
    import tik.trigger as trigger
    from tik.trigger.core import get_module
    from tik.trigger.modules.twist.twist import Twist

    # Other suites clear the registries, so discovery has to be re-run here.
    trigger.load_plugins()
    assert get_module("twist") is Twist


def test_output_names_follow_the_count():
    from tik.trigger.modules.twist.twist import Twist

    assert Twist.output_names({"count": 3}) == ("twist0", "twist1", "twist2")


def test_twist_guides_are_railed_and_locked():
    """A twist guide is a handle on two numbers; its channels are not editable."""
    import tik.trigger as trigger
    from tik.trigger.guides import GuideScene

    trigger.load_plugins()
    guides = GuideScene()
    guides.clear()
    handle = guides.add("twist", name="fore", count=3)
    node = guides.guide_node(handle.instance_id, "twist", 1)
    assert node["translate"].get_input() is not None, "not railed"
    for channel in ("tx", "ty", "tz", "rx", "ry", "rz"):
        assert node[channel].locked, f"{channel} should be locked"
    assert not node["position"].locked and not node["twistWeight"].locked

    # position drives placement along base -> end
    end = guides.guide_node(handle.instance_id, "end", 0)
    node["position"].value = 0.25
    assert abs(node.translate[0] - end.translate[0] * 0.25) < 1e-6


def test_guides_declare_position_and_weight():
    from tik.trigger.modules.twist.twist import POSITION_ATTR, WEIGHT_ATTR, Twist

    declared = {attr.name for attr in Twist.attrs_for_role("twist")}
    assert declared == {POSITION_ATTR, WEIGHT_ATTR}


def test_twist_builds_on_an_arm():
    """The real shape: forearm twist between the arm's lowerarm and hand."""
    from maya import cmds

    import tik.trigger as trigger
    from tik.trigger.guides import GuideScene
    from tik.trigger.maya import Builder

    trigger.load_plugins()
    guides = GuideScene()
    guides.clear()
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    twist = guides.add("twist", side="L", name="fore", parent=arm, count=3)
    guides.connect("L_fore.base", "L_arm.lowerarm")
    guides.connect("L_fore.end", "L_arm.hand")

    report = Builder().build(rig_name="hero", afterlife="keep")
    assert report.rigs[twist.instance_id]

    for index in range(3):
        joint = f"L_fore_twist{index}_jnt"
        assert cmds.objExists(joint), f"{joint} was not built"
        # driven rotation, and a parent that is the arm's own bind joint
        assert cmds.listConnections(f"{joint}.rotateX", source=True, destination=False)
        assert cmds.listRelatives(joint, parent=True)[0] == "L_arm_lowerarm_jnt"

    # A negative weight must reverse the joint against the extracted angle.
    ctx = report.rigs[twist.instance_id]
    assert len(ctx.outputs) == 3


def _arm_with_twist(count=3):
    from maya import cmds

    import tik.trigger as trigger
    from tik.trigger.guides import GuideScene
    from tik.trigger.maya import Builder

    trigger.load_plugins()
    guides = GuideScene()
    guides.clear()
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    fore = guides.add("twist", side="L", name="fore", parent=arm, count=count)
    guides.connect("L_fore.base", "L_arm.lowerarm")
    guides.connect("L_fore.end", "L_arm.hand")
    # The authored workflow: place the base on the segment start, aim it down
    # the segment, then dial the end guide's length. The end guide moves in
    # translateX only, so aiming is the base's job. Sockets connect with
    # maintain_offset, so a guide left at the module default bakes that
    # offset in permanently.
    elbow = guides.guide_node(arm.instance_id, "elbow", 0)
    wrist = guides.guide_node(arm.instance_id, "hand", 0)
    base = guides.guide_node(fore.instance_id, "base", 0)
    end = guides.guide_node(fore.instance_id, "end", 0)
    base.world_position = elbow.world_position
    base.aim_at(wrist)
    end["translateX"].value = elbow.distance_to(wrist)
    report = Builder().build(rig_name="hero", afterlife="keep")
    return report.rigs[arm.instance_id], report.rigs[fore.instance_id]


def _distance_to_segment(point, start, end):
    axis = end - start
    length_squared = axis * axis
    if length_squared < 1e-12:
        return (point - start).length()
    fraction = ((point - start) * axis) / length_squared
    fraction = max(0.0, min(1.0, fraction))
    return (point - (start + axis * fraction)).length()


def test_twist_joints_lie_on_the_base_to_end_segment():
    """They must sit on the line between base and end, in every pose."""
    arm_ctx, twist_ctx = _arm_with_twist()
    base = arm_ctx.outputs["lowerarm"]
    end = arm_ctx.outputs["hand"]
    control = arm_ctx.controller_by_role("ik").transform

    for pose in ((14, 0, 0), (20, 6, 3), (9, -5, 7)):
        control.world_position = pose
        for name, joint in twist_ctx.outputs.items():
            offset = _distance_to_segment(
                joint.world_position, base.world_position, end.world_position
            )
            assert offset < 1e-3, f"{name} is {offset:.4f} off the segment at {pose}"


def test_twist_joints_keep_their_fraction_along_the_segment():
    arm_ctx, twist_ctx = _arm_with_twist(count=3)
    base = arm_ctx.outputs["lowerarm"]
    end = arm_ctx.outputs["hand"]
    control = arm_ctx.controller_by_role("ik").transform
    control.world_position = (20, 6, 3)

    axis = end.world_position - base.world_position
    length_squared = axis * axis
    fractions = []
    for index in range(3):
        joint = twist_ctx.outputs[f"twist{index}"]
        fractions.append(
            ((joint.world_position - base.world_position) * axis) / length_squared
        )
    assert fractions == sorted(fractions), "twist joints are out of order"
    for index, fraction in enumerate(fractions):
        expected = (index + 1) / 4.0
        assert abs(fraction - expected) < 1e-2, f"twist{index}: {fraction} != {expected}"


def test_end_guide_moves_only_along_x():
    """X is the twist axis by construction: the end guide is a length handle."""
    import tik.trigger as trigger
    from tik.trigger.guides import GuideScene

    trigger.load_plugins()
    guides = GuideScene()
    guides.clear()
    handle = guides.add("twist", name="fore", count=2)
    end = guides.guide_node(handle.instance_id, "end", 0)

    assert not end["tx"].locked, "length must stay adjustable"
    for channel in ("ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
        assert end[channel].locked, f"{channel} should be locked on the end guide"
    assert end.translate[1] == 0.0 and end.translate[2] == 0.0

    # the base stays free to place and orient; only scale is meaningless
    base = guides.guide_node(handle.instance_id, "base", 0)
    for channel in ("tx", "ty", "tz", "rx", "ry", "rz"):
        assert not base[channel].locked, f"{channel} should stay free on the base"
    assert base["sx"].locked
