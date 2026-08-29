"""Tests for the MatrixSpline construct."""

import pytest
from maya import cmds
from maya.api import OpenMaya

import tik.maya as tm
from tik.core.bspline import basis
from tik.maya.constructs.matrix_spline import MatrixSpline


def _drivers(positions):
    drivers = []
    for index, position in enumerate(positions):
        driver = tm.Transform.create(name=f"driver{index}")
        driver.translate = position
        drivers.append(driver)
    return drivers


def _axes(transform):
    matrix = transform.world_matrix
    return (
        OpenMaya.MVector(matrix[0], matrix[1], matrix[2]),
        OpenMaya.MVector(matrix[4], matrix[5], matrix[6]),
    )


def _close(vector, expected, tolerance=1e-4):
    return all(abs(a - b) < tolerance for a, b in zip(vector, expected))


def test_outputs_match_basis_weighted_positions():
    positions = [(0, 0, 0), (5, 3, 0), (10, 0, 2)]
    drivers = _drivers(positions)
    parameters = [0.2, 0.5, 0.8]
    spline = MatrixSpline.create(drivers, parameters, name="spl", degree=2)
    assert spline.degree == 2
    assert [output.transform.name for output in spline.outputs] == ["spl_0_out", "spl_1_out", "spl_2_out"]
    for output, u in zip(spline.outputs, parameters):
        weights = basis(u, 3, 2)
        expected = [sum(w * p[axis] for w, p in zip(weights, positions)) for axis in range(3)]
        assert _close(output.transform.world_translation, expected)
        assert output.weights == pytest.approx(weights)


def test_outputs_live_update_when_driver_moves():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.5], name="spl")
    drivers[1].translate = (10, 8, 0)
    assert _close(spline.outputs[0].transform.world_translation, (5, 4, 0))


def test_outputs_aim_along_strip_with_up_from_first_driver():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.25, 0.75], name="spl")
    for output in spline.outputs:
        x_axis, y_axis = _axes(output.transform)
        assert _close(x_axis, (1, 0, 0))
        assert _close(y_axis, (0, 1, 0))
    drivers[0].rotate = (90, 0, 0)  # default up frame rolls with the first driver
    _, y_axis = _axes(spline.outputs[0].transform)
    assert _close(y_axis, (0, 0, 1))


def test_explicit_up_matrix():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    frame = tm.Transform.create(name="frame")
    frame.rotate = (-90, 0, 0)
    spline = MatrixSpline.create(drivers, [0.5], name="spl", up_matrix=frame["worldMatrix[0]"])
    _, y_axis = _axes(spline.outputs[0].transform)
    assert _close(y_axis, (0, 0, -1))


def test_driver_rotation_does_not_leak_into_position_blend():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.5], name="spl")
    drivers[1].rotate = (0, 0, 90)
    assert _close(spline.outputs[0].transform.world_translation, (5, 0, 0))


def test_scale_blends():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.5], name="spl")
    drivers[1].scale = (3, 3, 3)
    matrix = OpenMaya.MTransformationMatrix(spline.outputs[0].transform.world_matrix)
    assert _close(matrix.scale(OpenMaya.MSpace.kWorld), (2, 2, 2))


def test_degree_is_clamped_to_driver_count():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.5], name="spl", degree=3)
    assert spline.degree == 1


def test_invalid_inputs():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    with pytest.raises(ValueError):
        MatrixSpline.create(drivers[:1], [0.5], name="spl")
    with pytest.raises(ValueError):
        MatrixSpline.create(drivers, [1.0], name="spl")
    with pytest.raises(ValueError):
        MatrixSpline.create(drivers, [0.7, 0.3], name="spl")
    with pytest.raises(ValueError):
        MatrixSpline.create(drivers, [0.5], name="spl", twists=[None])


def test_outputs_are_world_space_regardless_of_parent():
    parent = tm.Transform.create(name="parent")
    parent.translate = (0, 100, 0)
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.5], name="spl", parent=parent)
    assert spline.group.parent.name == "parent"
    assert spline.group["inheritsTransform"].value is False
    assert _close(spline.outputs[0].transform.world_translation, (5, 0, 0))


def test_twist_interpolates_with_position_weights():
    drivers = _drivers([(0, 0, 0), (5, 0, 0), (10, 0, 0)])
    twists = [tm.attribute.add_float(driver, "twist") for driver in drivers]
    spline = MatrixSpline.create(drivers, [0.5], name="spl", degree=2, twists=twists)
    twists[0].value = 100.0
    twists[1].value = 20.0
    twists[2].value = 300.0
    assert spline.outputs[0].twist.value == pytest.approx(0.25 * 100 + 0.5 * 20 + 0.25 * 300)


def test_twist_is_unbounded_and_stays_out_of_the_matrix():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    twists = [tm.attribute.add_float(driver, "twist") for driver in drivers]
    spline = MatrixSpline.create(drivers, [0.5], name="spl", twists=twists)
    twists[1].value = 900.0
    assert spline.outputs[0].twist.value == pytest.approx(450.0)
    _, y_axis = _axes(spline.outputs[0].transform)
    assert _close(y_axis, (0, 1, 0))


def test_missing_twists_leave_plug_at_zero():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    spline = MatrixSpline.create(drivers, [0.5], name="spl", twists=[None, None])
    assert spline.outputs[0].twist.value == 0.0
    assert not cmds.listConnections(spline.outputs[0].twist.path, source=True, destination=False)


def test_delete_removes_network():
    drivers = _drivers([(0, 0, 0), (10, 0, 0)])
    twists = [tm.attribute.add_float(driver, "twist") for driver in drivers]
    spline = MatrixSpline.create(drivers, [0.25, 0.75], name="spl", twists=twists)
    spline.delete()
    assert not cmds.objExists("spl_spline_grp")
    assert not cmds.ls(type=["parentMatrix", "pickMatrix", "aimMatrix"])
    assert not cmds.ls("multDL*")


def test_exported_from_tik_maya():
    assert tm.MatrixSpline is MatrixSpline
