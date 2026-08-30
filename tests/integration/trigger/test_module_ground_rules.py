"""Ground rules that bind every trigger module, not just the arm.

Spec: docs/superpowers/specs/2026-08-30-arm-module-and-module-ground-rules-design.md

A failure here is a finding about the offending module, not a test to relax.
"""

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.maya import tags
from tik.trigger.core import ParentRef, get_module
from tik.trigger.maya import Builder

MODULE_TYPES = ("base", "fkchain", "arm")


def _solo(module_type):
    """Build one unconnected instance and return its context."""
    cmds.file(new=True, force=True)
    backend = trigger.maya_backend()
    module = get_module(module_type)(name=module_type)
    instance = backend.create_guides(module)
    if get_module(module_type).primary_input() is not None:
        # A module with a required input needs something to hang from.
        cmds.file(new=True, force=True)
        backend = trigger.maya_backend()
        body = backend.create_guides(get_module("base")(name="body"))
        instance = backend.create_guides(
            get_module(module_type)(name=module_type),
            parent=ParentRef(body.instance_id, "root"),
        )
    report = Builder(backend).build(rig_name="rules", afterlife="keep")
    return report.contexts[instance.instance_id]


@pytest.fixture
def connected_rig():
    """A base with an arm attached: one hierarchy spanning two modules."""
    cmds.file(new=True, force=True)
    backend = trigger.maya_backend()
    body = backend.create_guides(get_module("base")(name="body"))
    arm = backend.create_guides(
        get_module("arm")(name="arm", side="L"),
        parent=ParentRef(body.instance_id, "root"),
    )
    report = Builder(backend).build(rig_name="rules", afterlife="keep")
    return report, body, arm


def test_exactly_one_bind_hierarchy_root(connected_rig):
    """Rule 1.5: every rig has exactly one deform-joint hierarchy."""
    _report, _body, _arm = connected_rig
    deform = {
        node.long_name
        for node in tm.find_by_meta(tags.KIND, tags.DEFORM, node_type="joint")
    }
    assert deform, "no deform joints were tagged"
    roots = [
        node
        for node in deform
        if (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
        not in deform
    ]
    assert len(roots) == 1, f"expected one bind root, got {roots}"


def test_connected_module_leaves_its_bind_group_empty(connected_rig):
    """Rule 1.3: bind_grp is empty once the module is connected."""
    report, _body, arm = connected_rig
    arm_ctx = report.contexts[arm.instance_id]
    children = cmds.listRelatives(arm_ctx.groups.bind.long_name, children=True) or []
    assert children == [], f"bind_grp should be empty when connected, holds {children}"


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_no_controller_outside_the_control_group(module_type):
    """Rule 1.3: control_grp holds controllers and their offset groups only."""
    ctx = _solo(module_type)
    control_group = ctx.groups.control.long_name
    for controller in ctx.controllers:
        assert control_group in controller.transform.long_name, (
            f"{controller.transform.name} is outside {control_group}"
        )


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_every_output_is_a_tagged_bind_joint(module_type):
    """Rule 1.5: ctx.bind_parent reads outputs, so they must be bind joints."""
    ctx = _solo(module_type)
    assert ctx.outputs, f"'{module_type}' produced no outputs"
    for name, node in ctx.outputs.items():
        assert node.type == "joint", f"output '{name}' is a {node.type}, not a joint"
        assert node in ctx.deform_joints, f"output '{name}' is not a bind joint"


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_every_controller_declares_a_mirror_rule(module_type):
    """Rule 1.6: a pose-mirror tool needs the rule per control."""
    ctx = _solo(module_type)
    assert ctx.controllers, f"'{module_type}' produced no controllers"
    for controller in ctx.controllers:
        rule = controller.transform.meta[tags.MIRROR]
        assert rule in (tags.BEHAVIOUR, tags.WORLD), (
            f"{controller.transform.name} declares mirror rule {rule!r}"
        )


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_module_has_exactly_the_four_groups(module_type):
    """Rule 1.3: socket / control / rig / bind, and nothing else."""
    ctx = _solo(module_type)
    children = {
        path.split("|")[-1]
        for path in cmds.listRelatives(
            ctx.groups.limb.long_name, children=True, fullPath=True
        )
        or []
    }
    assert children == {
        ctx.groups.socket.name,
        ctx.groups.control.name,
        ctx.groups.rig.name,
        ctx.groups.bind.name,
    }


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_bind_joints_carry_live_trs(module_type):
    """Rule 1.4: bind joints bake and export, so TRS must be driven.

    A transform parked in offsetParentMatrix would leave the channels empty.
    """
    ctx = _solo(module_type)
    for joint in ctx.deform_joints:
        assert not cmds.listConnections(
            f"{joint.long_name}.offsetParentMatrix", source=True, destination=False
        ), f"{joint.name} is driven through offsetParentMatrix"


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_module_builds_without_a_cycle(module_type):
    ctx = _solo(module_type)
    cmds.dgdirty(allPlugs=True)
    cycles = cmds.cycleCheck(all=True) or []
    assert not cycles, f"'{module_type}' evaluates with a cycle: {cycles}"


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_module_parents_everything_it_creates(module_type):
    """Rule 1.7: nothing a module builds is left at the world root."""
    cmds.file(new=True, force=True)
    backend = trigger.maya_backend()
    before = set(cmds.ls(assemblies=True, long=True))

    if get_module(module_type).primary_input() is not None:
        body = backend.create_guides(get_module("base")(name="body"))
        backend.create_guides(
            get_module(module_type)(name=module_type),
            parent=ParentRef(body.instance_id, "root"),
        )
    else:
        backend.create_guides(get_module(module_type)(name=module_type))
    Builder(backend).build(rig_name="rules", afterlife="delete")

    stray = set(cmds.ls(assemblies=True, long=True)) - before - {"|rules_rig"}
    assert not stray, f"'{module_type}' left {sorted(stray)} at the world root"
