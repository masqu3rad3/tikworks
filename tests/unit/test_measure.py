"""Tests for the Measure construct."""

from maya import cmds

import tik.maya as tm
from tik.maya.constructs.measure import Measure


def _pair():
    start = tm.Transform.create(name="start")
    end = tm.Transform.create(name="end")
    end.translate = (3, 4, 0)
    return start, end


def test_distance_plug_and_initial():
    start, end = _pair()
    measure = Measure.create(start, end, name="arm")
    assert measure.node.name == "arm_distance"
    assert abs(measure.distance.value - 5.0) < 1e-6
    assert abs(measure.initial_distance - 5.0) < 1e-6


def test_distance_is_live():
    start, end = _pair()
    measure = Measure.create(start, end)
    end.translate = (6, 8, 0)
    assert abs(measure.distance.value - 10.0) < 1e-6


def test_ratio_plug():
    start, end = _pair()
    measure = Measure.create(start, end)
    ratio = measure.ratio_plug()
    assert abs(ratio.value - 1.0) < 1e-6
    end.translate = (6, 8, 0)
    assert abs(ratio.value - 2.0) < 1e-6


def test_ratio_plug_with_scale():
    start, end = _pair()
    holder = tm.Transform.create(name="holder")
    scale_plug = holder["globalScale"].create("float", default=2.0)
    measure = Measure.create(start, end)
    ratio = measure.ratio_plug(scale_plug)
    end.translate = (6, 8, 0)
    assert abs(ratio.value - 1.0) < 1e-6


def test_delete():
    start, end = _pair()
    measure = Measure.create(start, end, name="m")
    measure.ratio_plug()
    measure.delete()
    assert not cmds.objExists("m_distance")


def test_create_accepts_matrix_plugs():
    start = tm.Transform.create(name="plug_measure_a")
    end = tm.Transform.create(name="plug_measure_b")
    end.translate = (0, 0, 5)

    measure = tm.Measure.create(
        start["worldMatrix[0]"], end["worldMatrix[0]"], name="plug_measure"
    )
    assert abs(measure.distance.value - 5.0) < 1e-4

    end.translate = (0, 0, 9)
    assert abs(measure.distance.value - 9.0) < 1e-4


def test_create_mixes_a_node_and_a_plug():
    start = tm.Transform.create(name="mixed_measure_a")
    end = tm.Transform.create(name="mixed_measure_b")
    end.translate = (4, 0, 0)

    measure = tm.Measure.create(start, end["worldMatrix[0]"], name="mixed_measure")
    assert abs(measure.distance.value - 4.0) < 1e-4
