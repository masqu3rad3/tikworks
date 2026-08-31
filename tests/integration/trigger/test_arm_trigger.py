"""Arm module: single IK chain, one bind hierarchy, optional stretch."""

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.core import ParentRef, get_module
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder, tags


@pytest.fixture
def scene():
    cmds.file(new=True, force=True)
    return GuideScene()


def _build_arm(scene, side="L", **settings):
    body = scene.create_guides(get_module("base")(name="body"))
    cmds.xform(
        scene.guide_node(body.instance_id, "root").long_name, ws=True, t=(0, 15, 0)
    )
    arm = scene.create_guides(
        get_module("arm")(name="arm", side=side, settings=settings),
        parent=ParentRef(body.instance_id, "root"),
    )
    mult = -1 if side == "R" else 1
    for role, position in (
        ("collar", (2, 15, 0)),
        ("shoulder", (5, 15, 0)),
        ("elbow", (9, 15, -1)),
        ("hand", (14, 15, 0)),
    ):
        cmds.xform(
            scene.guide_node(arm.instance_id, role).long_name,
            ws=True,
            t=(position[0] * mult, position[1], position[2]),
        )
    report = Builder().build(rig_name="hero", afterlife="delete")
    return report, body, arm


def _arm_ctx(scene, side="L", **settings):
    report, _body, arm = _build_arm(scene, side=side, **settings)
    return report.rigs[arm.instance_id]


def _ik_control(ctx):
    return next(
        item.transform
        for item in ctx.controllers
        if item.transform.name.endswith("_ik_ctrl")
    )


# ------------------------------------------------------------------ manifest
def test_declares_four_outputs():
    assert get_module("arm").output_names({}) == (
        "collar",
        "upperarm",
        "lowerarm",
        "hand",
    )


def test_has_only_the_behaviour_fields():
    """No ik_solver, no ribbon fields, no soft_ik, no size or limit knobs."""
    names = set(get_module("arm").fields())
    assert names == {
        "stretch", "squash", "pole_pin", "anim_spaces",
        "limb_lock", "lock_from",
        "auto_collar",
        "auto_collar_lift_min_angle", "auto_collar_lift_max_angle",
        "auto_collar_lift_min_output", "auto_collar_lift_max_output",
        "auto_collar_swing_min_angle", "auto_collar_swing_max_angle",
        "auto_collar_swing_min_output", "auto_collar_swing_max_output",
        "auto_collar_interpolation",
    }


def test_control_names_carry_one_module_token(scene):
    """L_arm_ik_ctrl, not L_arm_arm_ik_ctrl."""
    ctx = _arm_ctx(scene)
    names = {item.transform.name for item in ctx.controllers}
    assert "L_arm_ik_ctrl" in names
    assert "L_arm_pole_ctrl" in names
    assert not any("_arm_arm_" in name for name in names)


def test_controller_size_scales_with_the_limb():
    """No size field: size is derived from the chain length."""
    from tik.trigger.systems.limb import _derive_size

    short = tm.Joint.chain(
        [(0, 0, 0), (4, 0, -1), (8, 0, 0)], name_pattern="short_{index}"
    )
    long_chain = tm.Joint.chain(
        [(0, 0, 0), (40, 0, -1), (80, 0, 0)], name_pattern="long_{index}"
    )
    assert _derive_size(short) > 0
    assert _derive_size(long_chain) > _derive_size(short)


# -------------------------------------------------------------- deform rules
def test_bind_skeleton_is_a_single_chain(scene):
    ctx = _arm_ctx(scene)
    collar = ctx.outputs["collar"]
    upper = ctx.outputs["upperarm"]
    lower = ctx.outputs["lowerarm"]
    hand = ctx.outputs["hand"]
    assert upper.parent.name == collar.name
    assert lower.parent.name == upper.name
    assert hand.parent.name == lower.name


def test_connected_arm_leaves_its_bind_group_empty(scene):
    report, body, arm = _build_arm(scene)
    body_ctx = report.rigs[body.instance_id]
    arm_ctx = report.rigs[arm.instance_id]
    assert arm_ctx.outputs["collar"].parent.name == body_ctx.outputs["root"].name
    assert not cmds.listRelatives(arm_ctx.groups.bind.long_name, children=True)


def test_every_output_is_a_bind_joint(scene):
    ctx = _arm_ctx(scene)
    for name, node in ctx.outputs.items():
        assert node.type == "joint", f"output '{name}' is a {node.type}"
        assert node in ctx.deform_joints


# ------------------------------------------------------------------- rigging
def test_builds_exactly_one_ik_handle(scene):
    """The whole point: one IK chain, no SC chain to blend against."""
    _arm_ctx(scene)
    assert len(cmds.ls(type="ikHandle")) == 1


def test_every_controller_lives_in_the_control_group(scene):
    ctx = _arm_ctx(scene)
    control_group = ctx.groups.control.long_name
    for controller in ctx.controllers:
        assert control_group in controller.transform.long_name


def test_collar_is_a_behaviour_control(scene):
    ctx = _arm_ctx(scene)
    collar = next(
        item.transform
        for item in ctx.controllers
        if item.transform.name.endswith("_collar_ctrl")
    )
    assert collar.meta[tags.MIRROR] == tags.BEHAVIOUR


def test_builds_without_a_ribbon(scene):
    ctx = _arm_ctx(scene)
    assert not cmds.ls(type="nurbsSurface")
    assert not cmds.ls("*ribbon*")


# --------------------------------------------------------------------- flags
def test_stretch_on_builds_the_limit_with_it(scene):
    control = _ik_control(_arm_ctx(scene))
    assert control.has_attr("stretch")
    assert control.has_attr("stretchLimit")
    assert control.has_attr("squash")


def test_stretch_off_builds_no_stretch_attributes(scene):
    control = _ik_control(_arm_ctx(scene, stretch=False, squash=False))
    assert not control.has_attr("stretch")
    assert not control.has_attr("stretchLimit")
    assert not control.has_attr("squash")


def test_segment_scale_and_soft_ik_are_always_present(scene):
    """Neither is optional, with or without the stretch network."""
    control = _ik_control(_arm_ctx(scene, stretch=False, squash=False))
    assert control.has_attr("sUpper")
    assert control.has_attr("sLower")
    assert control.has_attr("softIk")
    assert control.has_attr("poleFollow")


def test_stretch_off_builds_a_smaller_graph(scene):
    ctx = _arm_ctx(scene, stretch=False, squash=False)
    lean = len(cmds.ls(type="condition"))
    cmds.file(new=True, force=True)
    fresh = GuideScene()
    _arm_ctx(fresh, stretch=True, squash=True)
    full = len(cmds.ls(type="condition"))
    assert lean < full


# ----------------------------------------------------------------- behaviour
def test_hand_follows_ik_when_switched(scene):
    ctx = _arm_ctx(scene)
    control = _ik_control(ctx)
    control["ikFk"].value = 1.0
    before = ctx.outputs["hand"].world_translation
    control.translate = tuple(
        value + shift for value, shift in zip(control.translate, (0, 3, 0))
    )
    after = ctx.outputs["hand"].world_translation
    assert (after - before).length() > 1.0


def test_arm_does_not_cycle(scene):
    _arm_ctx(scene)
    cmds.dgdirty(allPlugs=True)
    assert not (cmds.cycleCheck(all=True) or [])


def test_right_arm_mirrors(scene):
    ctx = _arm_ctx(scene, side="R")
    assert ctx.outputs["hand"].world_position.x < 0


def test_collar_locks_scale_and_visibility(scene):
    ctx = _arm_ctx(scene)
    collar = next(
        item.transform
        for item in ctx.controllers
        if item.transform.name.endswith("_collar_ctrl")
    )
    for attr in ("sx", "sy", "sz", "v"):
        assert cmds.getAttr(f"{collar.long_name}.{attr}", lock=True)
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
        assert not cmds.getAttr(f"{collar.long_name}.{attr}", lock=True)


# -------------------------------------------------------------------- spaces
# --------------------------------------------------------------- auto-collar
def _collar_control(ctx):
    return next(
        item.transform
        for item in ctx.controllers
        if item.transform.name.endswith("_collar_ctrl")
    )


def test_auto_collar_defaults_to_off(scene):
    control = _ik_control(_arm_ctx(scene))
    assert control.has_attr("autoCollarLift")
    assert control.has_attr("autoCollarSwing")
    assert abs(control["autoCollarLift"].value) < 1e-6
    assert abs(control["autoCollarSwing"].value) < 1e-6


def test_the_old_auto_collar_attributes_are_gone(scene):
    """One dial per axis, scaling the output. No master, no input-side scale."""
    control = _ik_control(_arm_ctx(scene))
    assert not control.has_attr("autoCollar")
    assert not control.has_attr("autoCollarVertical")
    assert not control.has_attr("autoCollarHorizontal")


def test_auto_collar_fields_exist():
    names = set(get_module("arm").fields())
    assert {"auto_collar", "auto_collar_lift_min_angle",
            "auto_collar_lift_max_output", "auto_collar_swing_max_angle",
            "auto_collar_interpolation"} <= names


def test_auto_collar_can_be_switched_off(scene):
    control = _ik_control(_arm_ctx(scene, auto_collar=False))
    assert not control.has_attr("autoCollarLift")


def test_the_arm_declares_a_neutral_guide():
    assert "neutral" in get_module("arm").guides.roles


def test_validate_rejects_a_neutral_on_the_boundary():
    """The neutral must sit *strictly* inside each axis's input range.

    The field bounds keep the sign right, but zero is assignable and still
    degenerate: the middle ramp point would collide with an endpoint.
    """
    module = get_module("arm")(name="arm")
    module.auto_collar_lift_min_angle = 0.0
    assert any("lift" in problem for problem in module.validate())
    module.auto_collar_lift_min_angle = -60.0
    module.auto_collar_swing_max_angle = 0.0
    assert any("swing" in problem for problem in module.validate())


def test_the_angle_fields_cannot_reach_the_drivers_ceiling():
    """Off-plane angles saturate at +/-90, so a wider limit never completes.

    The field bounds are the rigger-facing half of that guard; ReachAxis
    validates the same thing for anything set programmatically.
    """
    fields = get_module("arm").fields()
    for name in (
        "auto_collar_lift_min_angle", "auto_collar_lift_max_angle",
        "auto_collar_swing_min_angle", "auto_collar_swing_max_angle",
    ):
        field = fields[name]
        assert abs(field.min) < 90.0 and abs(field.max) < 90.0, name


def test_auto_collar_off_is_inert(scene):
    """At 0 the collar must not move, however far the hand goes."""
    ctx = _arm_ctx(scene)
    collar = _collar_control(ctx)
    control = _ik_control(ctx)
    before = list(collar["worldMatrix[0]"].value)
    control.translate = (0, 20, 10)
    after = list(collar["worldMatrix[0]"].value)
    for first, second in zip(before, after):
        assert abs(first - second) < 1e-4


def test_auto_collar_on_follows_the_hand(scene):
    ctx = _arm_ctx(scene)
    collar = _collar_control(ctx)
    control = _ik_control(ctx)
    control["autoCollarLift"].value = 1.0
    before = tuple(collar.world_axis("x"))
    control.translate = (0, 20, 0)
    after = tuple(collar.world_axis("x"))
    assert max(abs(a - b) for a, b in zip(before, after)) > 0.05


def test_wrist_roll_does_not_spin_the_collar(scene):
    """Up comes from the socket, so rolling the wrist leaves the collar alone."""
    ctx = _arm_ctx(scene)
    collar = _collar_control(ctx)
    control = _ik_control(ctx)
    control["autoCollarLift"].value = 1.0
    control["autoCollarSwing"].value = 1.0
    before = list(collar["worldMatrix[0]"].value)
    control.rotate = (90, 0, 0)
    after = list(collar["worldMatrix[0]"].value)
    for first, second in zip(before, after):
        assert abs(first - second) < 1e-3


def test_auto_collar_does_not_cycle(scene):
    ctx = _arm_ctx(scene)
    control = _ik_control(ctx)
    control["autoCollarLift"].value = 1.0
    control["autoCollarSwing"].value = 1.0
    cmds.dgdirty(allPlugs=True)
    assert not (cmds.cycleCheck(all=True) or [])


def test_bind_pose_is_exact_with_the_automation_full_on(scene):
    """The regression test for the rest-direction bug: the old code fails it.

    The animator's scalars multiply the remap output, so no scalar value can
    move the neutral -- and at the guide pose the arm IS on the neutral.
    """
    ctx = _arm_ctx(scene)
    collar = _collar_control(ctx)
    control = _ik_control(ctx)
    before = list(collar["worldMatrix[0]"].value)
    control["autoCollarLift"].value = 1.0
    control["autoCollarSwing"].value = 1.0
    after = list(collar["worldMatrix[0]"].value)
    for first, second in zip(before, after):
        assert abs(first - second) < 1e-4


def test_raising_the_arm_never_dips_the_collar(scene):
    """The original complaint, as a test.

    The old mechanism blended the collar toward pointing at the hand, so from
    an A-pose any weight above zero rotated it down, and the dip deepened as
    the arm rose.
    """
    ctx = _arm_ctx(scene)
    collar = _collar_control(ctx)
    control = _ik_control(ctx)
    control["autoCollarLift"].value = 1.0
    # The automation drives a parent group, so the control's own channels stay
    # zero -- how far the collar's own X has tilted up is the honest measure.
    heights = []
    for height in range(0, 15):
        control.translate = (0.0, float(height), 0.0)
        heights.append(collar.world_axis("x")[1])
    rest = heights[0]  # zero offset is the bind pose, which is the neutral
    readings = [value - rest for value in heights]
    assert min(readings) > -1e-4, f"collar dipped: {readings}"
    assert all(b >= a - 1e-6 for a, b in zip(readings, readings[1:])), readings
    assert max(readings) > 0.05, readings


# --------------------------------------------------------------- final sweep
def test_arm_still_satisfies_every_ground_rule(scene):
    ctx = _arm_ctx(scene)
    control_group = ctx.groups.control.long_name
    for controller in ctx.controllers:
        assert control_group in controller.transform.long_name
        assert controller.transform.meta[tags.MIRROR] in (tags.BEHAVIOUR, tags.WORLD)
    for _name, node in ctx.outputs.items():
        assert node.type == "joint" and node in ctx.deform_joints
    for joint in ctx.deform_joints:
        assert not cmds.listConnections(
            f"{joint.long_name}.offsetParentMatrix", source=True, destination=False
        )


# -------------------------------------------------------------------- spaces
def _arm_with_spaces(scene, rows, wires):
    body = scene.create_guides(get_module("base")(name="body"))
    cmds.xform(
        scene.guide_node(body.instance_id, "root").long_name, ws=True, t=(0, 15, 0)
    )
    arm = scene.create_guides(
        get_module("arm")(name="arm", side="L", settings={"anim_spaces": rows}),
        parent=ParentRef(body.instance_id, "root"),
    )
    inputs = dict(scene.find_instances([arm.instance_id])[0].inputs)
    inputs.update(wires)
    scene.set_inputs(arm.instance_id, inputs)
    report = Builder().build(rig_name="hero", afterlife="keep")
    return report, report.rigs[arm.instance_id]


def test_arm_declares_its_space_controls():
    assert get_module("arm").space_controls == ("ik", "pole")


def test_two_rows_on_one_control_make_one_enum(scene):
    rows = [
        {"control": "ik", "mode": "parent", "label": "body"},
        {"control": "ik", "mode": "parent", "label": "root"},
    ]
    wires = {"ik_body": "body.root", "ik_root": "body.root"}
    _report, ctx = _arm_with_spaces(scene, rows, wires)
    control = _ik_control(ctx)
    assert control.has_attr("parentSwitch")
    listed = cmds.attributeQuery(
        "parentSwitch", node=control.long_name, listEnum=True
    )[0]
    assert listed.split(":") == ["body", "root"]


def test_no_world_entry_is_added(scene):
    """Nothing appears that the rigger did not define."""
    rows = [{"control": "ik", "mode": "parent", "label": "body"}]
    _report, ctx = _arm_with_spaces(scene, rows, {"ik_body": "body.root"})
    listed = cmds.attributeQuery(
        "parentSwitch", node=_ik_control(ctx).long_name, listEnum=True
    )[0]
    assert "world" not in listed.split(":")


def test_modes_build_separate_switches(scene):
    """Two modes on one control are two switches, so the labels must differ:
    (control, label) is the derived port name."""
    rows = [
        {"control": "ik", "mode": "parent", "label": "body"},
        {"control": "ik", "mode": "orient", "label": "chest"},
    ]
    wires = {"ik_body": "body.root", "ik_chest": "body.root"}
    _report, ctx = _arm_with_spaces(scene, rows, wires)
    control = _ik_control(ctx)
    assert control.has_attr("parentSwitch")
    assert control.has_attr("orientSwitch")


def test_trg_round_trip_keeps_rows_and_wires(scene, tmp_path):
    from tik.trigger.guides import GuideScene

    guides = GuideScene()
    body = guides.add("base", name="body")
    guides.add(
        "arm", side="L", name="arm", parent=body,
        anim_spaces=[{"control": "ik", "mode": "parent", "label": "body"}],
    )
    guides.connect("L_arm.ik_body", "body.root")

    path = guides.export(tmp_path / "spaces")
    guides.clear()
    guides.import_(path)

    restored = guides.find("arm", "L")
    assert restored.anim_spaces == [
        {"control": "ik", "mode": "parent", "label": "body"}
    ]
    assert restored.inputs.get("ik_body") == "body.root"


def test_pole_controller_rests_at_zero(scene):
    """The rest offset lives in a group, so the animator sees clean channels."""
    ctx = _arm_ctx(scene)
    pole = ctx.controller_by_role("pole").transform

    assert tuple(round(value, 6) for value in pole.translate) == (0.0, 0.0, 0.0)
    assert tuple(round(value, 6) for value in pole.rotate) == (0.0, 0.0, 0.0)

    # zeroed channels must not mean a controller sitting on the chain
    elbow = ctx.outputs["lowerarm"]
    assert (pole.world_position - elbow.world_position).length() > 1.0


def test_pole_rest_group_carries_the_offset(scene):
    ctx = _arm_ctx(scene)
    pole = ctx.controller_by_role("pole").transform
    rest = pole.parent
    assert rest.name.endswith("rest_grp"), f"unexpected parent {rest.name}"
    # the offset the controller used to hold is now on the group
    assert tuple(rest.translate) != (0.0, 0.0, 0.0)


def test_pole_still_drives_the_solve(scene):
    """Zeroing the channels must not detach the pole from the IK handle."""
    ctx = _arm_ctx(scene)
    pole = ctx.controller_by_role("pole").transform
    elbow = ctx.outputs["lowerarm"]

    before = elbow.world_position
    pole.translate = (0, 0, 12)
    assert (elbow.world_position - before).length() > 0.1
