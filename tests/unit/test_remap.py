"""Tests for the Remap construct."""

from maya import cmds

import tik.maya as tm


def _driver(value=0.0):
    node = tm.Transform.create(name="remap_driver")
    return node["angle"].create("float", default=value)


def test_below_the_input_minimum_is_the_output_minimum():
    plug = _driver(-10.0)
    remap = tm.Remap.create(plug, input_min=0.0, input_max=90.0, name="r")
    assert abs(remap.output.value) < 1e-4


def test_above_the_input_maximum_is_the_output_maximum():
    plug = _driver(180.0)
    remap = tm.Remap.create(plug, input_min=0.0, input_max=90.0, name="r_high")
    assert abs(remap.output.value - 1.0) < 1e-4


def test_output_range_is_honoured():
    plug = _driver(90.0)
    remap = tm.Remap.create(
        plug,
        input_min=0.0,
        input_max=90.0,
        output_min=2.0,
        output_max=8.0,
        name="r_out",
    )
    assert abs(remap.output.value - 8.0) < 1e-4


def test_linear_midpoint_is_exactly_half():
    plug = _driver(45.0)
    remap = tm.Remap.create(
        plug, input_min=0.0, input_max=90.0, interpolation="linear", name="r_lin"
    )
    assert abs(remap.output.value - 0.5) < 1e-3


def test_the_three_interpolations_agree_at_the_ends_and_differ_between():
    """The only thing that proves the choice reached remapValue."""
    values = {}
    for index, kind in enumerate(("linear", "smooth", "spline")):
        plug = _driver(22.5)
        remap = tm.Remap.create(
            plug, input_min=0.0, input_max=90.0, interpolation=kind, name=f"r_{index}"
        )
        values[kind] = remap.output.value
        plug.value = 0.0
        assert abs(remap.output.value) < 1e-4
        plug.value = 90.0
        assert abs(remap.output.value - 1.0) < 1e-4
    assert abs(values["linear"] - values["smooth"]) > 1e-3


def test_rejects_an_unknown_interpolation():
    import pytest

    plug = _driver()
    with pytest.raises(ValueError, match="interpolation"):
        tm.Remap.create(plug, input_min=0.0, input_max=1.0, interpolation="wobble")


# ------------------------------------------------------- explicit ramp shape


def _ramp(remap, index):
    node = remap.node
    return (
        node[f"value[{index}].value_Position"].value,
        node[f"value[{index}].value_FloatValue"].value,
        node[f"value[{index}].value_Interp"].value,
    )


def test_the_default_ramp_is_unchanged():
    from tik.maya.constructs.remap import INTERPOLATIONS

    remap = tm.Remap.create(_driver(), input_min=0.0, input_max=1.0, name="r_default")
    assert _ramp(remap, 0) == (0.0, 0.0, INTERPOLATIONS["smooth"])
    assert _ramp(remap, 1) == (1.0, 1.0, INTERPOLATIONS["smooth"])


def test_three_points_land_on_the_ramp():
    from tik.maya.constructs.remap import INTERPOLATIONS

    remap = tm.Remap.create(
        _driver(),
        input_min=-40.0,
        input_max=60.0,
        output_min=-8.0,
        output_max=22.0,
        points=[(0.0, 0.0), (0.4, 8.0 / 30.0), (1.0, 1.0)],
        name="r_three",
    )
    assert _ramp(remap, 0) == (0.0, 0.0, INTERPOLATIONS["smooth"])
    position, value, interp = _ramp(remap, 1)
    assert abs(position - 0.4) < 1e-6
    assert abs(value - 8.0 / 30.0) < 1e-6
    assert interp == INTERPOLATIONS["smooth"]
    assert _ramp(remap, 2) == (1.0, 1.0, INTERPOLATIONS["smooth"])


def test_the_middle_point_makes_zero_land_on_zero():
    """The whole reason the argument exists: an asymmetric signed range."""
    remap = tm.Remap.create(
        _driver(0.0),
        input_min=-40.0,
        input_max=60.0,
        output_min=-8.0,
        output_max=22.0,
        points=[(0.0, 0.0), (0.4, 8.0 / 30.0), (1.0, 1.0)],
        name="r_zero",
    )
    assert abs(remap.output.value) < 1e-4


def test_a_three_point_ramp_still_clamps_at_both_ends():
    plug = _driver(120.0)
    remap = tm.Remap.create(
        plug,
        input_min=-40.0,
        input_max=60.0,
        output_min=-8.0,
        output_max=22.0,
        points=[(0.0, 0.0), (0.4, 8.0 / 30.0), (1.0, 1.0)],
        name="r_clamp",
    )
    assert abs(remap.output.value - 22.0) < 1e-4
    plug.value = -200.0
    assert abs(remap.output.value + 8.0) < 1e-4


def test_rejects_a_single_point():
    import pytest

    with pytest.raises(ValueError, match="two points"):
        tm.Remap.create(
            _driver(), input_min=0.0, input_max=1.0, points=[(0.0, 0.0)], name="r_one"
        )


def test_rejects_an_out_of_range_point():
    import pytest

    with pytest.raises(ValueError, match="outside"):
        tm.Remap.create(
            _driver(),
            input_min=0.0,
            input_max=1.0,
            points=[(0.0, 0.0), (1.5, 1.0)],
            name="r_wide",
        )


def test_delete_removes_the_node():
    plug = _driver()
    remap = tm.Remap.create(plug, input_min=0.0, input_max=1.0, name="r_del")
    name = remap.node.long_name
    remap.delete()
    assert not cmds.objExists(name)
