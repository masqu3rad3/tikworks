"""The three new pieces together on one arm, end to end.

An arm with limb lock, a twist module on the forearm and a ribbon module on
the upper arm: the combination the design was written for.
"""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder, tags


@pytest.fixture
def guides():
    cmds.file(new=True, force=True)
    trigger.load_plugins()
    return GuideScene()


@pytest.fixture
def rigged(guides):
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body, limb_lock=True)
    fore = guides.add("twist", side="L", name="fore", parent=arm, count=3)
    guides.connect("L_fore.base", "L_arm.lowerarm")
    guides.connect("L_fore.end", "L_arm.hand")
    upper = guides.add("ribbon", side="L", name="upper", parent=arm, joint_count=4)
    guides.connect("L_upper.start", "L_arm.upperarm")
    guides.connect("L_upper.end", "L_arm.lowerarm")

    # Cover each span. Sockets connect with maintain_offset, so a guide left
    # at the module default bakes that offset in permanently.
    def arm_guide(role):
        return guides.guide_node(arm.instance_id, role, 0)

    # Twist: place the base, aim it down the segment, dial the length. Its end
    # guide moves in translateX only, so aiming is the base's job.
    start, finish = arm_guide("elbow"), arm_guide("hand")
    base = guides.guide_node(fore.instance_id, "base", 0)
    base.world_position = start.world_position
    base.aim_at(finish)
    guides.guide_node(fore.instance_id, "end", 0)["translateX"].value = (
        start.distance_to(finish)
    )

    # Ribbon guides are free, so they simply snap onto their span.
    for role, arm_role in (("start", "shoulder"), ("end", "elbow")):
        node = guides.guide_node(upper.instance_id, role, 0)
        node.world_position = arm_guide(arm_role).world_position
    report = Builder().build(document=guides.document, afterlife="keep")
    return report, arm, fore, upper


def test_everything_builds(rigged):
    report, arm, fore, upper = rigged
    assert report.count == 4
    for index in range(3):
        assert cmds.objExists(f"L_fore_twist{index}_jnt")
    for index in range(4):
        assert cmds.objExists(f"L_upper_joint{index}_jnt")
    control = report.rigs[arm.instance_id].controller_by_role("ik").transform
    assert cmds.objExists(f"{control.long_name}.limbLock")


def test_the_whole_rig_is_cycle_free(rigged):
    """The regression guard for the limb lock's pre-push reference."""
    report, arm, _fore, _upper = rigged
    control = report.rigs[arm.instance_id].controller_by_role("ik").transform
    control["limbLock"].value = 1.0
    control["lockLength"].value = control["currentLength"].value
    for context in report.rigs.values():
        for node in context.outputs.values():
            node.world_position  # force evaluation of every output
    assert (cmds.cycleCheck(all=True, list=True) or []) == []


def test_twist_joints_are_siblings_of_the_hand(rigged):
    """Engine twist-bone shape: under the segment start, beside the next joint."""
    for index in range(3):
        parent = cmds.listRelatives(f"L_fore_twist{index}_jnt", parent=True)[0]
        assert parent == "L_arm_lowerarm_jnt"


def test_ribbon_joints_are_real_bind_joints(rigged):
    """Not the construct's own world-space island."""
    for index in range(4):
        joint = f"L_upper_joint{index}_jnt"
        assert cmds.getAttr(f"{joint}.inheritsTransform")
        parent = cmds.listRelatives(joint, parent=True)[0]
        assert "ribbon" not in parent
        assert cmds.getAttr(f"{parent}.inheritsTransform")


def test_deform_joints_are_tagged_for_export(rigged):
    report, _arm, fore, upper = rigged
    for instance in (fore, upper):
        context = report.rigs[instance.instance_id]
        assert context.deform_joints
        for joint in context.deform_joints:
            assert joint.meta.get(tags.KIND) == tags.DEFORM


def test_twist_joints_track_the_segment_end_to_end(rigged):
    """The whole point: they stay on the base-to-end line as the arm moves."""
    report, arm, fore, _upper = rigged
    arm_ctx = report.rigs[arm.instance_id]
    twist_ctx = report.rigs[fore.instance_id]
    control = arm_ctx.controller_by_role("ik").transform
    base, end = arm_ctx.outputs["lowerarm"], arm_ctx.outputs["hand"]

    for pose in ((14, 0, 0), (19, 7, 4), (10, -6, 5)):
        control.world_position = pose
        axis = end.world_position - base.world_position
        for name, joint in twist_ctx.outputs.items():
            to_joint = joint.world_position - base.world_position
            fraction = (to_joint * axis) / (axis * axis)
            closest = base.world_position + axis * fraction
            assert (
                joint.world_position - closest
            ).length() < 1e-3, f"{name} left the segment at {pose}"
