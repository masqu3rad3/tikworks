"""Arm module: single IK chain, one bind hierarchy, optional stretch."""

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.backends.maya import tags
from tik.trigger.core import Builder, ParentRef, get_module


@pytest.fixture
def backend():
    cmds.file(new=True, force=True)
    return trigger.maya_backend()


def _build_arm(backend, side="L", **settings):
    body = backend.create_guides(get_module("base")(name="body"))
    cmds.xform(
        backend.guide_node(body.instance_id, "root").long_name, ws=True, t=(0, 15, 0)
    )
    arm = backend.create_guides(
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
            backend.guide_node(arm.instance_id, role).long_name,
            ws=True,
            t=(position[0] * mult, position[1], position[2]),
        )
    report = Builder(backend).build(rig_name="hero", afterlife="delete")
    return report, body, arm


def _arm_ctx(backend, side="L", **settings):
    report, _body, arm = _build_arm(backend, side=side, **settings)
    return report.contexts[arm.instance_id]


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
    assert names == {"stretch", "squash", "pole_pin", "anim_spaces"}


def test_control_names_carry_one_module_token(backend):
    """L_arm_ik_ctrl, not L_arm_arm_ik_ctrl."""
    ctx = _arm_ctx(backend)
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
def test_bind_skeleton_is_a_single_chain(backend):
    ctx = _arm_ctx(backend)
    collar = ctx.outputs["collar"]
    upper = ctx.outputs["upperarm"]
    lower = ctx.outputs["lowerarm"]
    hand = ctx.outputs["hand"]
    assert upper.parent.name == collar.name
    assert lower.parent.name == upper.name
    assert hand.parent.name == lower.name


def test_connected_arm_leaves_its_bind_group_empty(backend):
    report, body, arm = _build_arm(backend)
    body_ctx = report.contexts[body.instance_id]
    arm_ctx = report.contexts[arm.instance_id]
    assert arm_ctx.outputs["collar"].parent.name == body_ctx.outputs["root"].name
    assert not cmds.listRelatives(arm_ctx.groups.bind.long_name, children=True)


def test_every_output_is_a_bind_joint(backend):
    ctx = _arm_ctx(backend)
    for name, node in ctx.outputs.items():
        assert node.type == "joint", f"output '{name}' is a {node.type}"
        assert node in ctx.deform_joints


# ------------------------------------------------------------------- rigging
def test_builds_exactly_one_ik_handle(backend):
    """The whole point: one IK chain, no SC chain to blend against."""
    _arm_ctx(backend)
    assert len(cmds.ls(type="ikHandle")) == 1


def test_every_controller_lives_in_the_control_group(backend):
    ctx = _arm_ctx(backend)
    control_group = ctx.groups.control.long_name
    for controller in ctx.controllers:
        assert control_group in controller.transform.long_name


def test_collar_is_a_behaviour_control(backend):
    ctx = _arm_ctx(backend)
    collar = next(
        item.transform
        for item in ctx.controllers
        if item.transform.name.endswith("_collar_ctrl")
    )
    assert collar.meta[tags.MIRROR] == tags.BEHAVIOUR


def test_builds_without_a_ribbon(backend):
    ctx = _arm_ctx(backend)
    assert not cmds.ls(type="nurbsSurface")
    assert not cmds.ls("*ribbon*")


# --------------------------------------------------------------------- flags
def test_stretch_on_builds_the_limit_with_it(backend):
    control = _ik_control(_arm_ctx(backend))
    assert control.has_attr("stretch")
    assert control.has_attr("stretchLimit")
    assert control.has_attr("squash")


def test_stretch_off_builds_no_stretch_attributes(backend):
    control = _ik_control(_arm_ctx(backend, stretch=False, squash=False))
    assert not control.has_attr("stretch")
    assert not control.has_attr("stretchLimit")
    assert not control.has_attr("squash")


def test_segment_scale_and_soft_ik_are_always_present(backend):
    """Neither is optional, with or without the stretch network."""
    control = _ik_control(_arm_ctx(backend, stretch=False, squash=False))
    assert control.has_attr("sUpper")
    assert control.has_attr("sLower")
    assert control.has_attr("softIk")
    assert control.has_attr("poleFollow")


def test_stretch_off_builds_a_smaller_graph(backend):
    ctx = _arm_ctx(backend, stretch=False, squash=False)
    lean = len(cmds.ls(type="condition"))
    cmds.file(new=True, force=True)
    fresh = trigger.maya_backend()
    _arm_ctx(fresh, stretch=True, squash=True)
    full = len(cmds.ls(type="condition"))
    assert lean < full


# ----------------------------------------------------------------- behaviour
def test_hand_follows_ik_when_switched(backend):
    ctx = _arm_ctx(backend)
    control = _ik_control(ctx)
    control["ikFk"].value = 1.0
    before = ctx.outputs["hand"].world_translation
    control.translate = tuple(
        value + shift for value, shift in zip(control.translate, (0, 3, 0))
    )
    after = ctx.outputs["hand"].world_translation
    assert (after - before).length() > 1.0


def test_arm_does_not_cycle(backend):
    _arm_ctx(backend)
    cmds.dgdirty(allPlugs=True)
    assert not (cmds.cycleCheck(all=True) or [])


def test_right_arm_mirrors(backend):
    ctx = _arm_ctx(backend, side="R")
    assert ctx.outputs["hand"].world_position.x < 0


def test_collar_locks_scale_and_visibility(backend):
    ctx = _arm_ctx(backend)
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


def test_auto_collar_defaults_to_off(backend):
    control = _ik_control(_arm_ctx(backend))
    assert control.has_attr("autoCollar")
    assert abs(control["autoCollar"].value) < 1e-6


def test_auto_collar_off_is_inert(backend):
    """At 0 the collar must not move, however far the hand goes."""
    ctx = _arm_ctx(backend)
    collar = _collar_control(ctx)
    control = _ik_control(ctx)
    before = list(collar["worldMatrix[0]"].value)
    control.translate = (0, 20, 10)
    after = list(collar["worldMatrix[0]"].value)
    for first, second in zip(before, after):
        assert abs(first - second) < 1e-4


def test_auto_collar_on_follows_the_hand(backend):
    ctx = _arm_ctx(backend)
    collar = _collar_control(ctx)
    control = _ik_control(ctx)
    control["autoCollar"].value = 1.0
    before = tuple(collar.world_axis("x"))
    control.translate = (0, 20, 0)
    after = tuple(collar.world_axis("x"))
    assert max(abs(a - b) for a, b in zip(before, after)) > 0.05


def test_wrist_roll_does_not_spin_the_collar(backend):
    """Up comes from the socket, so rolling the wrist leaves the collar alone."""
    ctx = _arm_ctx(backend)
    collar = _collar_control(ctx)
    control = _ik_control(ctx)
    control["autoCollar"].value = 1.0
    before = list(collar["worldMatrix[0]"].value)
    control.rotate = (90, 0, 0)
    after = list(collar["worldMatrix[0]"].value)
    for first, second in zip(before, after):
        assert abs(first - second) < 1e-3


def test_auto_collar_does_not_cycle(backend):
    ctx = _arm_ctx(backend)
    _ik_control(ctx)["autoCollar"].value = 1.0
    cmds.dgdirty(allPlugs=True)
    assert not (cmds.cycleCheck(all=True) or [])


# --------------------------------------------------------------- final sweep
def test_arm_still_satisfies_every_ground_rule(backend):
    ctx = _arm_ctx(backend)
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
