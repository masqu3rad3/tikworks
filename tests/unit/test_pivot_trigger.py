"""Movable pivots and pivot presets, built against a real Maya scene.

Spec: docs/superpowers/specs/2026-09-07-movable-pivots-and-pivot-presets-design.md
"""

import pytest
from maya import cmds

from tik.trigger.core import (
    GuideLayout,
    Module,
    clear_registries,
    get_module,
    register_module,
)
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder


class PivotToy(Module):
    """One control with a movable pivot and two presets."""

    label = "Pivot Toy"
    sided = False
    guides = GuideLayout("root", "hand")
    inputs = ()
    outputs = ("root",)
    controls = ("main",)
    pivot_controls = {"main": "hand"}
    pivot_presets = Module.pivot_presets.with_default(
        [{"control": "main", "label": label} for label in ("tip", "ball")]
    )

    def draw_guides(self, guides):
        root = guides.joint("root", (0, 0, 0))
        guides.joint("hand", (5, 0, 0), parent=root)

    def build(self, rig):
        main = rig.controller("main", match=rig.guide("hand"))
        rig.pivot_control(main)
        rig.output("root", rig.bind_joint("root", match=rig.guide("root")))


class BarePivotToy(PivotToy):
    """A movable pivot with no presets at all."""

    pivot_presets = Module.pivot_presets.with_default([])


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("pivot_toy")(PivotToy)
    register_module("bare_pivot_toy")(BarePivotToy)
    yield
    clear_registries()


def _build(module_type, preset_positions=None):
    """Build one instance, optionally moving its preset guides first."""
    cmds.file(new=True, force=True)
    scene = GuideScene()
    instance = scene.create_guides(get_module(module_type)(name="toy"))
    # draw/sync take an iterable of instance ids, never a bare string
    scene.draw([instance.instance_id])
    for role, position in (preset_positions or {}).items():
        scene.guide_node(instance.instance_id, role).world_position = position
    scene.sync([instance.instance_id])
    report = Builder().build(document=scene.document, afterlife="keep")
    return report.rigs[instance.instance_id]


def _pivot(ctx):
    return ctx.controller_by_role("main_pivot")


def test_pivot_control_is_a_child_of_its_main_and_untiered():
    from tik.trigger.maya import tags

    ctx = _build("pivot_toy")
    main = ctx.controller_by_role("main")
    pivot = _pivot(ctx)
    assert pivot is not None
    # under main, through its own offset group
    assert pivot.offset.parent.long_name == main.transform.long_name
    assert pivot.transform.meta.get(tags.TIER) is None


def test_show_pivot_drives_the_pivot_controls_visibility():
    ctx = _build("pivot_toy")
    main = ctx.controller_by_role("main")
    pivot = _pivot(ctx)
    assert main.transform["showPivot"].exists()
    assert main.transform["showPivot"].keyable is False
    main.transform["showPivot"].value = True
    assert pivot.offset["visibility"].value is True
    main.transform["showPivot"].value = False
    assert pivot.offset["visibility"].value is False


def test_preset_enum_carries_default_first_then_the_rows_in_order():
    ctx = _build("pivot_toy")
    main = ctx.controller_by_role("main")
    listed = cmds.attributeQuery(
        "pivotPreset", node=main.transform.long_name, listEnum=True
    )[0]
    assert listed == "default:tip:ball"


def test_each_preset_moves_the_rotate_and_scale_pivot():
    ctx = _build(
        "pivot_toy",
        {"pivot_main_tip": (9.0, 0.0, 0.0), "pivot_main_ball": (7.0, 0.0, 0.0)},
    )
    main = ctx.controller_by_role("main")
    expected = {0: [0.0, 0.0, 0.0], 1: [4.0, 0.0, 0.0], 2: [2.0, 0.0, 0.0]}
    for index, value in expected.items():
        main.transform["pivotPreset"].value = index
        assert [
            round(item, 4) for item in main.transform["rotatePivot"].value[0]
        ] == value
        assert [
            round(item, 4) for item in main.transform["scalePivot"].value[0]
        ] == value


def test_a_manual_offset_adds_on_top_of_the_preset():
    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    pivot = _pivot(ctx)
    main.transform["pivotPreset"].value = 1
    pivot.transform.translate = (0.0, 0.5, 0.0)
    assert [round(item, 4) for item in main.transform["rotatePivot"].value[0]] == [
        4.0,
        0.5,
        0.0,
    ]


def test_the_pivot_control_marks_the_rotations_fixed_point():
    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    pivot = _pivot(ctx)
    main.transform["pivotPreset"].value = 1
    rest = [round(value, 4) for value in pivot.transform.world_position]
    main.transform.rotate = (0.0, 90.0, 0.0)
    assert [round(value, 4) for value in pivot.transform.world_position] == rest


def test_no_presets_means_no_preset_enum():
    ctx = _build("bare_pivot_toy")
    main = ctx.controller_by_role("main")
    assert main.transform["showPivot"].exists()
    assert not main.transform["pivotPreset"].exists()
    # and the pivot still moves by hand
    _pivot(ctx).transform.translate = (0.0, 0.0, 3.0)
    assert [round(item, 4) for item in main.transform["rotatePivot"].value[0]] == [
        0.0,
        0.0,
        3.0,
    ]


def test_building_a_pivot_for_an_undeclared_control_raises():
    class Undeclared(PivotToy):
        pivot_controls = {}
        pivot_presets = Module.pivot_presets.with_default([])

    clear_registries()
    register_module("undeclared")(Undeclared)
    with pytest.raises(Exception):
        _build("undeclared")
