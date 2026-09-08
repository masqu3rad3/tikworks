"""Ground rules that bind every trigger module, not just the arm.

Spec: docs/superpowers/specs/2026-08-30-arm-module-and-module-ground-rules-design.md

A failure here is a finding about the offending module, not a test to relax.
"""

import ast
from pathlib import Path

import maya.api.OpenMaya as om
import pytest
from maya import cmds

import tik.maya as tm
from tik.maya.roles.controller import Controller
from tik.trigger.core import ParentRef, get_module
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder, tags

MODULE_TYPES = ("base", "fkchain", "arm")


def _solo(module_type):
    """Build one unconnected instance and return its context."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    module = get_module(module_type)(name=module_type)
    instance = scene.create_guides(module)
    if get_module(module_type).primary_input() is not None:
        # A module with a required input needs something to hang from.
        cmds.file(new=True, force=True)
        scene = GuideScene()
        body = scene.create_guides(get_module("base")(name="body"))
        instance = scene.create_guides(
            get_module(module_type)(name=module_type),
            parent=ParentRef(body.instance_id, "root"),
        )
    report = Builder().build(document=scene.document, afterlife="keep")
    return report.rigs[instance.instance_id]


#: Settings each shipped module is checked at. A type absent from this mapping
#: is checked once, at its defaults.
CONTROL_VARIATIONS = {
    "fkchain": [{"segments": 1}, {"segments": 5}],
    "ribbon": [
        {"mid_count": 0},
        {"mid_count": 2, "start_controller": True, "end_controller": True},
    ],
}


def _shipped_module_types():
    """The modules this repo ships, ignoring anything a test registered."""
    import tik.trigger as trigger
    from tik.trigger.core import registry

    trigger.load_plugins()  # collection runs before any fixture
    return sorted(
        cls.module_type
        for cls in registry.iter_modules()
        if cls.__module__.startswith("tik.trigger.modules.")
    )


def _built_with(module_type, settings):
    """Build one instance under a base, with every required input wired."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    body = scene.create_guides(get_module("base")(name="body"))
    module_cls = get_module(module_type)
    primary = module_cls.primary_input()
    instance = scene.create_guides(
        module_cls(name=module_type),
        parent=ParentRef(body.instance_id, "root") if primary is not None else None,
    )
    for declared in module_cls.inputs:
        if declared.optional or (primary is not None and declared.name == primary.name):
            continue
        scene.set_input(instance.instance_id, declared.name, f"{body.key}.root")
    if settings:
        scene.write_settings(
            instance.instance_id,
            {**scene.read_settings(instance.instance_id), **settings},
        )
        # Drawing is manual since the Draw/Sync split: write_settings flags the
        # module, it does not rebuild its joints.
        scene.draw()
    report = Builder().build(document=scene.document, afterlife="keep")
    return report.rigs[instance.instance_id]


def _built_control_roles(ctx):
    """Roles tagged on the controllers a build created, tweaks and pivots excluded.

    A tweak is parented under its main and follows it, so a space switch on
    one would fight the parent it hangs from -- it is never in a manifest. A
    pivot controller is the same species for the same reason.
    """
    return sorted(
        role
        for role in (
            controller.transform.meta.get(tags.ROLE) for controller in ctx.controllers
        )
        if role and not role.endswith(("_tweak", "_pivot"))
    )


@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_every_module_declares_exactly_the_controllers_it_builds(module_type):
    """Rule: the control manifest is what the module builds, minus tweaks.

    Equality, not subset. A control the module forgot to declare is invisible
    in the anim-space table -- the exact bug fkchain and ribbon shipped with.
    """
    module_cls = get_module(module_type)
    for settings in CONTROL_VARIATIONS.get(module_type, [{}]):
        ctx = _built_with(module_type, settings)
        declared = sorted(module_cls.control_names(ctx.instance.settings))
        assert (
            _built_control_roles(ctx) == declared
        ), f"{module_type} at {settings or 'defaults'}: manifest and build disagree"


@pytest.fixture
def connected_rig():
    """A base with an arm attached: one hierarchy spanning two modules."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    body = scene.create_guides(get_module("base")(name="body"))
    arm = scene.create_guides(
        get_module("arm")(name="arm", side="L"),
        parent=ParentRef(body.instance_id, "root"),
    )
    report = Builder().build(document=scene.document, afterlife="keep")
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
    arm_ctx = report.rigs[arm.instance_id]
    children = cmds.listRelatives(arm_ctx.groups.bind.long_name, children=True) or []
    assert children == [], f"bind_grp should be empty when connected, holds {children}"


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_no_controller_outside_the_control_group(module_type):
    """Rule 1.3: control_grp holds controllers and their offset groups only."""
    ctx = _solo(module_type)
    control_group = ctx.groups.control.long_name
    for controller in ctx.controllers:
        assert (
            control_group in controller.transform.long_name
        ), f"{controller.transform.name} is outside {control_group}"


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
        assert rule in (
            tags.BEHAVIOUR,
            tags.WORLD,
        ), f"{controller.transform.name} declares mirror rule {rule!r}"


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
    _solo(module_type)
    cmds.dgdirty(allPlugs=True)
    cycles = cmds.cycleCheck(all=True) or []
    assert not cycles, f"'{module_type}' evaluates with a cycle: {cycles}"


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_module_parents_everything_it_creates(module_type):
    """Rule 1.7: nothing a module builds is left at the world root."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    before = set(cmds.ls(assemblies=True, long=True))

    if get_module(module_type).primary_input() is not None:
        body = scene.create_guides(get_module("base")(name="body"))
        scene.create_guides(
            get_module(module_type)(name=module_type),
            parent=ParentRef(body.instance_id, "root"),
        )
    else:
        scene.create_guides(get_module(module_type)(name=module_type))
    Builder().build(document=scene.document, afterlife="delete")

    # trigger_modules_grp holds the guide *document*, which deliberately
    # outlives the guides it renders -- it is not module output.
    stray = (
        set(cmds.ls(assemblies=True, long=True))
        - before
        - {"|rig_grp", "|trigger_modules_grp"}
    )
    assert not stray, f"'{module_type}' left {sorted(stray)} at the world root"


# ------------------------------------------------- sockets from declarations
@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_every_declared_input_gets_a_socket(module_type):
    """Declaring an input is what creates its socket; a module cannot forget."""
    rig = _solo(module_type)
    module_cls = get_module(module_type)
    structural = [item.name for item in module_cls.inputs if item.kind != "space"]

    for name in structural:
        socket = rig.socket(name)
        assert cmds.nodeType(socket.long_name) == "transform"
        assert socket.parent.long_name == rig.groups.socket.long_name
        assert socket.meta.get(tags.KIND) == tags.INPUT
        assert socket.meta.get(tags.ROLE) == name


def test_space_inputs_get_no_socket():
    """Anim-space inputs feed a SpaceSwitch on a control, not a matrix attach."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    body = scene.create_guides(get_module("base")(name="body"))
    arm = scene.create_guides(
        get_module("arm")(
            name="arm",
            side="L",
            settings={
                "anim_spaces": [{"control": "ik", "mode": "parent", "label": "world"}]
            },
        ),
        parent=ParentRef(body.instance_id, "root"),
    )
    report = Builder().build(document=scene.document, afterlife="keep")
    rig = report.rigs[arm.instance_id]

    assert "root" in rig.attachments
    assert "ik_world" not in rig.attachments


@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_every_top_level_controller_has_an_offset_group(module_type):
    """A control that hangs from control_grp gets its offset group for free.

    A tweak is the exception on purpose: it is a child of the control it
    refines, so it rides along and needs no offset of its own.
    """
    rig = _solo(module_type)
    assert rig.controllers
    tweaks = {
        control.transform.long_name
        for control in rig.controllers
        if control.offset is None
    }
    for control in rig.controllers:
        if control.transform.long_name in tweaks:
            parent = control.transform.parent
            assert parent is not None and Controller.is_controller(
                parent
            ), f"{control.transform.name} has no offset group and no parent control"
            continue
        # the offset is above the control; a module may insert its own group
        # between them (the arm's auto-collar does)
        assert control.transform.long_name.startswith(control.offset.long_name + "|")


# ------------------------------------------------------------------- tiers
@pytest.mark.parametrize("module_type", MODULE_TYPES)
def test_every_controller_carries_a_valid_tier(module_type):
    """Rule: a tweak has no tier; everything else declares one of TIERS."""
    from tik.trigger.core import TIERS

    ctx = _solo(module_type)
    for controller in ctx.controllers:
        role = controller.transform.meta.get(tags.ROLE, "")
        tier = controller.transform.meta.get(tags.TIER)
        if role.endswith(("_tweak", "_pivot")):
            assert tier is None, f"{controller.transform.name} is a tiered helper"
        else:
            assert tier in TIERS, f"{controller.transform.name} has tier {tier!r}"


@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_visibilities_enum_matches_the_control_manifest(module_type):
    """One enum on visibilities_ctrl iff the module declares controls."""
    module_cls = get_module(module_type)
    ctx = _built_with(module_type, {})
    vis = ctx.scaffold.visibilities.transform
    expected = bool(module_cls.control_names(ctx.instance.settings))
    assert (
        vis[ctx.instance.key].exists() is expected
    ), f"{module_type}: enum present={not expected}"


# ------------------------------------------------------------ movable pivots
@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_every_movable_pivot_names_a_control_and_a_guide_the_module_has(module_type):
    """Rule: pivot_controls points at real controls and real guide roles.

    A typo here is invisible until a rigger opens the properties table and
    finds a preset row pointing at nothing.
    """
    module_cls = get_module(module_type)
    for settings in CONTROL_VARIATIONS.get(module_type, [{}]):
        instance = module_cls(settings=settings)
        controls = set(module_cls.control_names(instance.values()))
        roles = set(module_cls.guides.all_roles)
        for control, anchor in module_cls.pivot_controls.items():
            assert control in controls, f"{module_type}: '{control}' is not a control"
            assert anchor in roles, f"{module_type}: anchor '{anchor}' is not a guide"


@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_every_preset_row_targets_a_movable_control(module_type):
    """Rule: a module's own default rows never warn out of the box."""
    assert get_module(module_type)().warnings() == []


@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_every_declared_control_has_a_resolvable_default_shape(module_type):
    """Rule: the manifest names a shape the pinned library can resolve.

    A default that does not resolve means every rig using that module silently
    falls back to a circle, which is exactly the bug this manifest exists to
    prevent.
    """
    from tik.trigger.core import shapes

    module_cls = get_module(module_type)
    for settings in CONTROL_VARIATIONS.get(module_type, [{}]):
        module = module_cls(name=module_type)
        module.apply(settings, strict=False)
        defaults = module_cls.control_shape_defaults(module.values())
        for role in module_cls.control_names(module.values()):
            assert role in defaults, f"{module_type}: '{role}' declares no shape"
            assert shapes.has_shape(
                defaults[role]
            ), f"{module_type}: '{role}' names '{defaults[role]}', not in the library"


def test_no_module_or_system_passes_a_shape_to_rig_controller():
    """Rule: the manifest is the only place a default lives.

    ``rig.controller`` has no ``shape`` argument; this catches a call that
    tries to reintroduce one before it silently becomes a second source.
    """
    import inspect

    from tik.trigger.maya.rig import ModuleRig

    assert "shape" not in inspect.signature(ModuleRig.controller).parameters

    # ``maya`` too: rig.py builds the tweak and pivot controllers through the
    # same method, and a shape= there is the same second source of truth.
    root = Path(__file__).resolve().parents[3] / "src" / "python" / "tik" / "trigger"
    offenders = []
    for folder in ("modules", "systems", "maya"):
        for py_file in (root / folder).rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(source)):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Attribute) and func.attr == "controller"):
                    continue
                if any(kw.arg == "shape" for kw in node.keywords):
                    offenders.append(f"{py_file.name}:{node.lineno}")
    assert offenders == [], f"rig.controller(shape=) at {offenders}"


# ------------------------------------------------------- tweak appearance
def test_a_tweak_takes_its_master_shape_at_the_tweak_scale():
    """Rule: a tweak looks like the control it belongs to, only smaller.

    A tweak is not in the manifest, so it has no role of its own to resolve --
    it reads what its master resolved to. A fixed circle under a cube read as
    a different kind of control rather than a finer grip on the same one.
    """
    from tik.trigger.maya.rig import TWEAK_SCALE

    ctx = _built_with("arm", {})
    by_role = {
        controller.transform.meta.get(tags.ROLE): controller
        for controller in ctx.controllers
    }
    for role, controller in by_role.items():
        if not role or not role.endswith("_tweak"):
            continue
        master = by_role[role[: -len("_tweak")]]
        assert controller.shape_name == master.shape_name, role
        assert controller.shape_size == pytest.approx(
            master.shape_size * TWEAK_SCALE
        ), role


def test_a_rigger_override_reaches_the_tweak_too():
    """The tweak follows the master's *resolved* shape, override included."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    body = scene.create_guides(get_module("base")(name="body"))
    instance = scene.create_guides(
        get_module("arm")(name="arm"),
        parent=ParentRef(body.instance_id, "root"),
    )
    scene.write_settings(
        instance.instance_id,
        {"control_shape_overrides": [{"control": "ik", "shape": "Diamond"}]},
    )
    report = Builder().build(document=scene.document, afterlife="keep")
    ctx = report.rigs[instance.instance_id]

    by_role = {
        controller.transform.meta.get(tags.ROLE): controller
        for controller in ctx.controllers
    }
    assert by_role["ik"].shape_name == "Diamond"
    assert by_role["ik_tweak"].shape_name == "Diamond"


def test_no_controller_shape_resolves_through_the_user_path():
    """Tweaks and pivots set their shape after creation, and must stay pinned.

    ``Controller.set_shape`` resolves a *name* through the unpinned singleton,
    which searches the artist's own folder -- the exact hole the pinned
    library exists to close.
    """
    import inspect

    from tik.trigger.maya import rig as rig_module

    source = inspect.getsource(rig_module)
    assert (
        "set_shape(shape" not in source
    ), "a raw name reaches Controller.set_shape; resolve it through _curve_for"


# ------------------------------------------------------ shape orientation
def _shape_normal(controller):
    """The plane normal of a flat controller shape, in its own local space."""
    points = []
    for shape in controller.transform.shapes:
        node = shape.long_name
        count = cmds.getAttr(f"{node}.spans") + cmds.getAttr(f"{node}.degree")
        points += [
            om.MVector(*cmds.pointPosition(f"{node}.cv[{i}]", local=True))
            for i in range(count)
        ]
    # The normal of the best-fit plane: sum the cross products around the ring.
    normal = om.MVector(0, 0, 0)
    centre = sum(points, om.MVector(0, 0, 0)) / len(points)
    for first, second in zip(points, points[1:] + points[:1]):
        normal += (first - centre) ^ (second - centre)
    return normal.normal()


@pytest.mark.parametrize("side", ["left", "right"])
def test_fk_shapes_are_aligned_to_their_bone(side):
    """Rule: an FK control's shape wraps its bone, on both sides.

    Shapes are authored flat in XZ with the normal on +Y, but an FK joint runs
    along local X -- so an unrotated circle lies *along* the limb rather than
    around it. The right side is mirrored by behaviour (a 180 roll about X),
    which puts its bone on local -X, so the turn has to mirror with it.
    """
    cmds.file(new=True, force=True)
    scene = GuideScene()
    body = scene.create_guides(get_module("base")(name="body"))
    instance = scene.create_guides(
        get_module("arm")(name="arm", side=side),
        parent=ParentRef(body.instance_id, "root"),
    )
    report = Builder().build(document=scene.document, afterlife="keep")
    ctx = report.rigs[instance.instance_id]

    checked = 0
    for controller in ctx.controllers:
        role = controller.transform.meta.get(tags.ROLE) or ""
        if not role.startswith("fk") or role.endswith("_tweak"):
            continue
        normal = _shape_normal(controller)
        # Aligned to the bone axis: the sign is the side's business, the
        # alignment is not.
        assert abs(normal.x) > 0.99, (
            f"{side} {role}: shape normal is ({normal.x:.2f}, {normal.y:.2f}, "
            f"{normal.z:.2f}), not along the bone"
        )
        checked += 1
    assert checked, "no FK controllers were checked"


def test_a_tweak_inherits_its_master_orientation():
    """A tweak takes the master's shape; a turned shape must arrive turned."""
    ctx = _built_with("arm", {})
    by_role = {
        controller.transform.meta.get(tags.ROLE): controller
        for controller in ctx.controllers
    }
    for role, controller in by_role.items():
        if role and role.endswith("_tweak"):
            master = by_role[role[: -len("_tweak")]]
            assert controller.shape_orient == master.shape_orient, role
