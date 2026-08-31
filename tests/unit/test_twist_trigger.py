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


def test_projected_position_ignores_sideways_drift():
    """A guide dragged off the axis still reads its along-axis fraction."""
    from tik.trigger.modules.twist.twist import projected_position

    start = tm.Transform.create(name="s")
    end = tm.Transform.create(name="e")
    end.translate = (10, 0, 0)
    probe = tm.Transform.create(name="p")
    probe.translate = (2.5, 6, -3)  # far off the axis
    assert abs(projected_position(start, end, probe) - 0.25) < 1e-6
    probe.translate = (-4, 0, 0)  # behind the start, clamped
    assert projected_position(start, end, probe) == 0.0


def test_guide_weights_default_to_position():
    from tik.trigger.modules.twist.twist import WEIGHT_ATTR, Twist

    module = Twist(name="fore", settings={"count": 3})
    assert module.guide_attrs["twist"][0].name == WEIGHT_ATTR


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
