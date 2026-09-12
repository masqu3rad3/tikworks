"""The framework builds a movable pivot where the rigger asked for one.

Spec: docs/superpowers/specs/2026-09-11-control-capability-declarations-design.md

Declaring is what makes a pivot available; a preset row is what builds it --
the same sentence the ground rules use for sockets.
"""

from maya import cmds

from tik.trigger.core import get_module
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder


def _build(module_type, settings=None):
    cmds.file(new=True, force=True)
    scene = GuideScene()
    module = get_module(module_type)(name=module_type)
    if settings:
        module.apply(settings, strict=False)
    instance = scene.create_guides(module)
    report = Builder().build(document=scene.document, afterlife="keep")
    return report.rigs[instance.instance_id]


def _pivots(rig):
    """Every pivot controller the build made, by name."""
    return sorted(
        controller.transform.name
        for _slug, context in rig.contexts
        for controller in context.controllers
        if controller.transform.name.endswith("_pivot_ctrl")
    )


def test_arm_still_builds_its_hand_pivot_without_an_explicit_call():
    """arm ships three preset rows, so a fresh arm is unchanged."""
    assert any("ik_pivot_ctrl" in name for name in _pivots(_build("arm")))


def test_a_declared_control_with_no_preset_rows_builds_no_pivot():
    """fkchain declares a pivot per segment; a fresh one has no rows."""
    rig = _build("fkchain")
    assert _pivots(rig) == []
    assert rig.pivot_node("fk0") is None


def test_a_preset_row_is_what_builds_the_pivot():
    """Still true -- but what a row alone builds is a null, not a control.

    The row asked for named positions, not for a pivot the animator drags.
    """
    rig = _build(
        "fkchain",
        {"segments": 3, "pivot_presets": [{"control": "fk1", "label": "tip"}]},
    )
    assert _pivots(rig) == []
    assert "fk1_pivot_grp" in rig.pivot_node("fk1").name


def test_an_emptied_arm_keeps_the_pivot_its_tick_asked_for():
    """Deleting the rows deletes the named positions, not the pivot.

    ``arm`` ships the tick as well as the three rows, so an arm whose rigger
    cleared the table still hands the animator a pivot to drag -- it just has
    no enum to switch.
    """
    rig = _build("arm", {"pivot_presets": []})
    main = rig.controller_by_role("ik")
    assert any("ik_pivot_ctrl" in name for name in _pivots(rig))
    assert not main.transform.has_attr("pivotPreset")


def test_an_arm_with_neither_builds_no_pivot():
    """The rule is uniform: nothing asked for means nothing built."""
    rig = _build("arm", {"pivot_presets": [], "movable_pivots": []})
    assert _pivots(rig) == []
    assert rig.pivot_node("ik") is None


def test_a_tick_with_no_rows_builds_a_bare_pivot():
    """The feature: showPivot and a pivot to move, with no enum at all."""
    rig = _build("fkchain", {"segments": 3, "movable_pivots": ["fk1"]})

    names = _pivots(rig)
    assert len(names) == 1
    assert "fk1_pivot_ctrl" in names[0]
    assert not rig.controller_by_role("fk1").transform.has_attr("pivotPreset")


def test_a_tick_and_rows_together_build_one_pivot_with_its_enum():
    rig = _build(
        "fkchain",
        {
            "segments": 3,
            "movable_pivots": ["fk1"],
            "pivot_presets": [{"control": "fk1", "label": "tip"}],
        },
    )

    assert len(_pivots(rig)) == 1
    assert rig.controller_by_role("fk1").transform.has_attr("pivotPreset")


def test_a_tick_on_one_control_builds_nothing_on_the_others():
    rig = _build("fkchain", {"segments": 3, "movable_pivots": ["fk1"]})

    assert all("fk0_pivot" not in name for name in _pivots(rig))


# ------------------------------------------------ movable vs. merely preset
def _pivot_node(rig, role):
    return rig.pivot_node(role)


def test_rows_without_a_tick_demote_the_pivot_to_a_null():
    """Named positions the animator switches, with nothing to drag."""
    rig = _build(
        "fkchain",
        {"segments": 3, "pivot_presets": [{"control": "fk0", "label": "tip"}]},
    )
    main = rig.controller_by_role("fk0")

    assert _pivots(rig) == []
    assert not main.transform.has_attr("showPivot")
    assert main.transform.has_attr("pivotPreset")


def test_the_demoted_null_exists_and_drives_the_pivot():
    rig = _build(
        "fkchain",
        {"segments": 3, "pivot_presets": [{"control": "fk0", "label": "tip"}]},
    )
    node = _pivot_node(rig, "fk0")

    assert node is not None
    assert not cmds.listRelatives(node.long_name, shapes=True)
    driver = rig.controller_by_role("fk0").transform["rotatePivot"].get_input()
    assert driver.long_name == node.long_name


def test_a_tick_keeps_it_a_controller_with_show_pivot():
    rig = _build(
        "fkchain",
        {
            "segments": 3,
            "movable_pivots": ["fk0"],
            "pivot_presets": [{"control": "fk0", "label": "tip"}],
        },
    )
    main = rig.controller_by_role("fk0")

    assert len(_pivots(rig)) == 1
    assert main.transform.has_attr("showPivot")
    assert main.transform.has_attr("pivotPreset")
