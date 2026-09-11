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


# ------------------------------------------------------- switch pivot (tool)
def test_switch_pivot_preset_holds_the_pose():
    from tik.trigger.maya.pivot import switch_pivot_preset

    ctx = _build(
        "pivot_toy",
        {"pivot_main_tip": (9.0, 0.0, 0.0), "pivot_main_ball": (7.0, 0.0, 0.0)},
    )
    main = ctx.controller_by_role("main")
    main.transform["pivotPreset"].value = 1
    main.transform.rotate = (0.0, 45.0, 0.0)
    # the world *matrix*, not world_position: the latter queries the rotate
    # pivot, which is a fixed point by construction and so proves nothing.
    before = [round(value, 4) for value in main.transform.world_matrix]

    switch_pivot_preset(main, "ball")

    assert main.transform["pivotPreset"].value == 2
    assert [round(value, 4) for value in main.transform.world_matrix] == before


def test_switch_pivot_preset_holds_the_pose_under_a_rotated_parent():
    """The compensation is written in the control's own parent space."""
    import tik.maya as tm
    from tik.trigger.maya.pivot import switch_pivot_preset

    ctx = _build(
        "pivot_toy",
        {"pivot_main_tip": (9.0, 0.0, 0.0), "pivot_main_ball": (7.0, 0.0, 0.0)},
    )
    main = ctx.controller_by_role("main")
    parent = tm.resolve(main.transform.parent)
    parent.rotate = (12.0, 34.0, -21.0)
    parent.translate = (3.0, 1.0, -2.0)
    main.transform["pivotPreset"].value = 1
    main.transform.rotate = (0.0, 45.0, 0.0)
    before = [round(value, 4) for value in main.transform.world_matrix]

    switch_pivot_preset(main, "ball")

    assert [round(value, 4) for value in main.transform.world_matrix] == before


def test_switch_pivot_preset_accepts_an_index_and_rejects_an_unknown_name():
    from tik.trigger.maya.pivot import switch_pivot_preset

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    switch_pivot_preset(main, 1)
    assert main.transform["pivotPreset"].value == 1
    with pytest.raises(ValueError):
        switch_pivot_preset(main, "knuckle")


def test_switch_pivot_preset_rejects_a_control_with_no_presets():
    from tik.trigger.maya.pivot import preset_labels, switch_pivot_preset

    ctx = _build("pivot_toy")
    pivot = _pivot(ctx)
    assert preset_labels(pivot) == []
    with pytest.raises(ValueError):
        switch_pivot_preset(pivot, "tip")


# ------------------------------------------------------- switching a range
def test_key_times_unions_every_channel():
    from tik.trigger.maya.pivot import key_times

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    cmds.setKeyframe(main.transform.long_name, attribute="translateX", time=1)
    cmds.setKeyframe(main.transform.long_name, attribute="translateX", time=20)
    cmds.setKeyframe(main.transform.long_name, attribute="rotateY", time=10)
    cmds.setKeyframe(main.transform.long_name, attribute="rotateY", time=40)

    assert key_times(main, 1, 30) == (1.0, 10.0, 20.0)


def test_switch_over_a_range_holds_the_pose_at_every_key():
    from tik.trigger.maya.pivot import switch_pivot_preset

    ctx = _build(
        "pivot_toy",
        {"pivot_main_tip": (9.0, 0.0, 0.0), "pivot_main_ball": (7.0, 0.0, 0.0)},
    )
    main = ctx.controller_by_role("main")
    main.transform["pivotPreset"].value = 1
    for time, angle in ((1, 0.0), (12, 35.0), (24, -20.0)):
        cmds.currentTime(time)
        main.transform.rotate = (0.0, angle, 0.0)
        cmds.setKeyframe(main.transform.long_name, attribute=["translate", "rotate"])

    before = {}
    for time in (1, 12, 24):
        cmds.currentTime(time)
        before[time] = [round(value, 4) for value in main.transform.world_matrix]

    switch_pivot_preset(main, "ball", key=True, times=(1.0, 12.0, 24.0))

    for time in (1, 12, 24):
        cmds.currentTime(time)
        assert [round(value, 4) for value in main.transform.world_matrix] == before[
            time
        ]
    assert main.transform["pivotPreset"].value == 2


def test_the_preset_enum_is_keyed_once_and_stepped():
    from tik.trigger.maya.pivot import switch_pivot_preset

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    path = main.transform.long_name + ".pivotPreset"
    switch_pivot_preset(main, "tip", key=True, times=(3.0, 9.0, 15.0))

    assert cmds.keyframe(path, query=True, timeChange=True) == [3.0]
    assert cmds.keyTangent(path, query=True, outTangentType=True) == ["step"]


def test_switch_without_key_leaves_no_keys():
    from tik.trigger.maya.pivot import switch_pivot_preset

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    switch_pivot_preset(main, "tip", key=False, times=(1.0, 5.0))

    assert not cmds.keyframe(main.transform.long_name, query=True, timeChange=True)


def test_current_preset_reads_the_label():
    from tik.trigger.maya.pivot import current_preset

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    assert current_preset(main) == "default"
    main.transform["pivotPreset"].value = 2
    assert current_preset(main) == "ball"
    assert current_preset(_pivot(ctx)) is None


# ------------------------------------------------------------- the switch tab
def _context_for(*controls):
    from tik.trigger.anim.context import Control, SwitchContext

    return SwitchContext(
        nodes=tuple(item.transform.long_name for item in controls),
        controls=tuple(
            Control(node=item.transform.long_name, role="main", side="C", module="toy")
            for item in controls
        ),
    )


def test_pivot_switch_offers_the_controls_presets():
    from tik.trigger.anim.switches.pivot.pivot import PivotSwitch

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    switch = PivotSwitch()
    context = _context_for(main)

    assert switch.states(context) == ["default", "tip", "ball"]
    assert switch.current(context) == "default"


def test_pivot_switch_offers_nothing_for_a_control_without_presets():
    from tik.trigger.anim.switches.pivot.pivot import PivotSwitch

    ctx = _build("bare_pivot_toy")
    main = ctx.controller_by_role("main")
    context = _context_for(main)
    assert PivotSwitch().states(context) == []
    assert PivotSwitch().current(context) is None


def test_pivot_switch_offers_only_what_the_whole_selection_shares():
    """The intersection: a preset only some controls have would silently skip."""
    from tik.trigger.anim.switches.pivot.pivot import PivotSwitch

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    bare = _pivot(ctx)  # the pivot control itself has no presets
    assert PivotSwitch().states(_context_for(main, bare)) == []


def test_pivot_switch_applies_and_reports():
    from tik.trigger.anim.switches.pivot.pivot import PivotSwitch

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    report = PivotSwitch().apply(_context_for(main), "tip", key=False, times=(1.0,))

    assert main.transform["pivotPreset"].value == 1
    assert "tip" in report and "pose held" in report


def test_pivot_switch_says_so_when_nothing_matches():
    from tik.trigger.anim.switches.pivot.pivot import PivotSwitch

    ctx = _build("pivot_toy")
    report = PivotSwitch().apply(
        _context_for(_pivot(ctx)), "tip", key=False, times=(1.0,)
    )
    assert "No selected control" in report


def test_pivot_switch_reports_a_range():
    from tik.trigger.anim.switches.pivot.pivot import PivotSwitch

    ctx = _build("pivot_toy", {"pivot_main_tip": (9.0, 0.0, 0.0)})
    main = ctx.controller_by_role("main")
    report = PivotSwitch().apply(
        _context_for(main), "tip", key=True, times=(1.0, 5.0, 9.0)
    )
    assert "over 3 keys" in report


# ------------------------------------------------ the anchor is addressable
def test_pivot_anchor_normalises_a_bare_role_to_index_zero():
    class Simple(Module):
        guides = GuideLayout("root")
        controls = ("root",)
        control_shapes = {"root": "Circle"}
        pivot_controls = {"root": "root"}

    assert Simple.pivot_anchor("root", {}) == ("root", 0)


def test_pivot_anchor_carries_an_explicit_index():
    class Chain(Module):
        guides = GuideLayout("root", multi="segment", min=1, max=10)
        controls = ("fk0", "fk1")
        control_shapes = {"fk0": "Circle", "fk1": "Circle"}
        pivot_controls = {"fk0": ("root", 0), "fk1": ("segment", 1)}

    assert Chain.pivot_anchor("fk1", {}) == ("segment", 1)


def test_pivot_anchor_is_none_for_a_control_without_one():
    class Simple(Module):
        guides = GuideLayout("root")
        controls = ("root", "other")
        control_shapes = {"root": "Circle", "other": "Circle"}
        pivot_controls = {"root": "root"}

    assert Simple.pivot_anchor("other", {}) is None


def test_pivot_controls_for_copy_returns_the_anchors_not_just_the_names():
    """The hook dropped its anchors, so no computed module could declare one."""
    from tik.core.fields import IntField

    class Chain(Module):
        guides = GuideLayout("root", multi="segment", min=1, max=10)
        count = IntField(2)

        @classmethod
        def controls_for_copy(cls, settings=None):
            number = int((settings or {}).get("count", 2))
            return tuple(f"fk{index}" for index in range(number))

        @classmethod
        def control_shape_defaults_for_copy(cls, settings=None):
            return {role: "Circle" for role in cls.controls_for_copy(settings)}

        @classmethod
        def pivot_controls_for_copy(cls, settings=None):
            found = {"fk0": ("root", 0)}
            for index in range(1, len(cls.controls_for_copy(settings))):
                found[f"fk{index}"] = ("segment", index - 1)
            return found

    assert Chain.pivot_control_names({"count": 3}) == ("fk0", "fk1", "fk2")
    assert Chain.pivot_anchor("fk2", {"count": 3}) == ("segment", 1)


def test_pivot_labels_lists_one_controls_rows_in_order():
    class Simple(Module):
        guides = GuideLayout("root")
        controls = ("root", "other")
        control_shapes = {"root": "Circle", "other": "Circle"}
        pivot_controls = {"root": "root", "other": "root"}

    module = Simple()
    module.pivot_presets = [
        {"control": "root", "label": "tip"},
        {"control": "other", "label": "ignored"},
        {"control": "root", "label": "heel"},
    ]
    assert module.pivot_labels("root") == ["tip", "heel"]
    assert module.pivot_labels("nobody") == []


def test_a_module_that_builds_its_own_pivot_gets_exactly_one():
    """The builder's seam skips a role that already has a pivot.

    Every module called rig.pivot_control itself before the seam existed and
    a studio module may still, so a second one -- which would fail on its
    showPivot attribute -- must never be made. PivotToy is that module.
    """
    ctx = _build("pivot_toy")
    pivots = [
        controller
        for controller in ctx.controllers
        if controller.transform.name.endswith("_pivot_ctrl")
    ]
    assert len(pivots) == 1


def test_a_ribbon_mid_is_offered_no_movable_pivot():
    """A mid rides the surface, so a moved pivot does not behave there.

    Exempt rather than merely absent: the ground rules treat a control with
    no pivot as an oversight unless the module says it meant it.
    """
    import tik.trigger as trigger
    from tik.trigger.core import get_module

    trigger.load_plugins()
    ribbon = get_module("ribbon")
    settings = {"mid_count": 2, "start_controller": True, "end_controller": True}
    module = ribbon(name="ribbon")
    module.apply(settings, strict=False)
    values = module.values()

    assert sorted(ribbon.pivot_control_names(values)) == ["end", "start"]
    assert sorted(ribbon.pivot_exempt_names(values)) == ["mid0", "mid1"]
    # The picker offers exactly the pivot-capable controls.
    assert ribbon.pivot_anchor("mid0", values) is None
    assert ribbon.pivot_anchor("start", values) == ("start", 0)
