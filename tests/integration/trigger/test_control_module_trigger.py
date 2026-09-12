"""The control module: one control, one joint, one of each per copy.

A deliberately small module -- a guide, a controller, a bind joint -- whose
whole point is that spaces, a movable pivot and per-copy ports fall out of the
manifest rather than out of ``build()``.
"""

from maya import cmds

from tik.trigger.core import get_module
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder


def _build(**settings):
    """One control module, standalone, with its input left unwired."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    module = get_module("control")(name="head", side="L")
    if settings:
        module.apply(settings, strict=False)
    instance = scene.create_guides(module)
    report = Builder().build(document=scene.document, afterlife="keep")
    return report.rigs[instance.instance_id]


def _driver_of(joint):
    """The transform whose world matrix drives ``joint``'s translation.

    Straight through the constraint network rather than ``listHistory``: the
    tweak is a *child* of its main, so the main is upstream of the tweak's
    world matrix either way and history cannot tell the two apart.
    """
    decompose = joint["translate"].get_input()
    mult = decompose["inputMatrix"].get_input()
    for index in range(4):
        source = mult[f"matrixIn[{index}]"].get_input(plug=True)
        if source is not None and source.attr.startswith("worldMatrix"):
            return source.node
    return None


def _controls(rig):
    """Every controller the build made, by name."""
    return sorted(
        controller.transform.name
        for _slug, context in rig.contexts
        for controller in context.controllers
    )


# ------------------------------------------------------------ the essentials
def test_it_builds_one_control_and_one_joint():
    rig = _build()

    assert rig.controller_by_role("root").transform.name == "L_head_root_ctrl"
    assert [joint.name for joint in rig.deform_joints] == ["L_head_root_jnt"]


def test_the_joint_is_published_as_the_output():
    rig = _build()

    assert rig.outputs["root"].name == "L_head_root_jnt"


def test_the_joint_follows_the_control():
    rig = _build()

    assert _driver_of(rig.outputs["root"]).name == "L_head_root_ctrl"


def test_an_unwired_input_still_builds_and_stands_at_the_guide():
    rig = _build()

    socket = rig.attachments["root"]
    assert socket.parent.name.endswith("socket_grp")


# ------------------------------------------------------------------- tweak
def test_there_is_no_tweak_by_default():
    assert "L_head_root_tweak_ctrl" not in _controls(_build())


def test_the_tweak_is_built_when_asked():
    assert "L_head_root_tweak_ctrl" in _controls(_build(tweak=True))


def test_the_joint_follows_the_tweak_when_there_is_one():
    """Downstream connections read the tweak, not the main."""
    rig = _build(tweak=True)

    assert _driver_of(rig.outputs["root"]).name == "L_head_root_tweak_ctrl"


# ------------------------------------------------------------------- pivot
def test_no_preset_rows_means_no_pivot():
    """Declaring offers a pivot; a row is what builds it."""
    assert "L_head_root_pivot_ctrl" not in _controls(_build())


def test_a_preset_row_builds_the_pivot():
    rig = _build(pivot_presets=[{"control": "root", "label": "tip"}])

    assert "L_head_root_pivot_ctrl" in _controls(rig)
    assert rig.controller_by_role("root").transform.has_attr("pivotPreset")


# ------------------------------------------------------------------ spaces
def test_the_control_can_host_an_animation_space():
    """``space_controls`` is undeclared, so the one control is offered one."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    scene.add("base", name="body")
    handle = scene.add(
        "control",
        name="head",
        side="L",
        anim_spaces=[{"control": "root", "mode": "parent", "label": "body"}],
    )
    handle.set_input("root_body", "body.root")

    report = Builder().build(document=scene.document, afterlife="keep")

    control = report.rigs[handle.instance_id].controller_by_role("root")
    assert control.transform.has_attr("parentSwitch")


# ------------------------------------------------------------------ copies
def test_each_copy_gets_its_own_control_joint_and_ports():
    cmds.file(new=True, force=True)
    scene = GuideScene()
    scene.add("base", name="a")
    scene.add("base", name="b")
    handle = scene.add(
        "control",
        name="props",
        side="L",
        copies=[{"slug": "", "name": "hat"}, {"slug": "c1", "name": "bag"}],
    )
    handle.set_input("root", "a.root")
    handle.set_input("c1_root", "b.root")

    report = Builder().build(document=scene.document, afterlife="keep")
    rig = report.rigs[handle.instance_id]

    assert _controls(rig) == ["L_bag_root_ctrl", "L_hat_root_ctrl"]
    assert sorted(rig.outputs) == ["c1_root", "root"]
    assert rig.outputs["root"].name == "L_hat_root_jnt"
    assert rig.outputs["c1_root"].name == "L_bag_root_jnt"
    assert report.connections == [
        ("L_props.root", "a.root"),
        ("L_props.c1_root", "b.root"),
    ]
