import pytest
from maya import cmds
from maya.api import OpenMaya

from tikmaya.types.transform import Transform


def test_create_with_and_without_name():
    t_named = Transform.create(name="tm_named")
    t_auto = Transform.create()

    assert cmds.nodeType(t_named.name) == "transform"
    assert t_named.name == "tm_named"
    assert cmds.nodeType(t_auto.name) == "transform"


def test_create_with_parenting():
    parent = Transform.create(name="tm_parent")
    child = Transform.create(name="tm_child", parent=parent.name)

    parents = cmds.listRelatives(child.name, parent=True, fullPath=False) or []
    assert parents and parents[0] == parent.name


def test_shapes_empty_when_no_shapes():
    t = Transform.create(name="tm_no_shapes")
    assert t.shapes == []


def test_shapes_returns_resolved_wrappers():
    t = Transform.create(name="tm_with_shape")
    shape_name = cmds.createNode("mesh", parent=t.name)
    shapes = t.shapes

    assert len(shapes) == 1
    assert hasattr(shapes[0], "name")
    assert shapes[0].name == shape_name


def test_mdag_path_is_valid():
    t = Transform.create(name="tm_dag")
    dag = t.mdag_path

    assert isinstance(dag, OpenMaya.MDagPath)
    assert t.name in dag.fullPathName()


def test_world_translation_matches_channel():
    t = Transform.create(name="tm_world_trans")
    cmds.setAttr(f"{t.name}.translate", 1.0, 2.0, 3.0, type="double3")

    v = t.world_translation
    assert (v.x, v.y, v.z) == pytest.approx((1.0, 2.0, 3.0), abs=1e-6)


def test_snap_to_position_only_copies_world_position():
    src = Transform.create(name="tm_snap_pos_src")
    dst = Transform.create(name="tm_snap_pos_dst")

    cmds.setAttr(f"{src.name}.translate", 0.0, 0.0, 0.0, type="double3")
    cmds.setAttr(f"{src.name}.rotate", 0.0, 0.0, 0.0, type="double3")
    cmds.setAttr(f"{src.name}.scale", 1.0, 1.0, 1.0, type="double3")

    cmds.setAttr(f"{dst.name}.translate", 4.0, 5.0, 6.0, type="double3")
    cmds.setAttr(f"{dst.name}.rotate", 10.0, 20.0, 30.0, type="double3")
    cmds.setAttr(f"{dst.name}.scale", 2.0, 3.0, 4.0, type="double3")

    src.snap_to(dst, position=True, rotation=False, scale=False)

    assert cmds.getAttr(f"{src.name}.translate")[0] == pytest.approx(
        cmds.getAttr(f"{dst.name}.translate")[0], abs=1e-6
    )
    assert cmds.getAttr(f"{src.name}.rotate")[0] == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)
    assert cmds.getAttr(f"{src.name}.scale")[0] == pytest.approx((1.0, 1.0, 1.0), abs=1e-6)


def test_snap_to_rotation_only_copies_rotation():
    src = Transform.create(name="tm_snap_rot_src")
    dst = Transform.create(name="tm_snap_rot_dst")

    cmds.setAttr(f"{src.name}.rotate", 0.0, 0.0, 0.0, type="double3")
    cmds.setAttr(f"{dst.name}.rotate", 15.0, 25.0, 35.0, type="double3")

    src.snap_to(dst, position=False, rotation=True, scale=False)

    assert cmds.getAttr(f"{src.name}.rotate")[0] == pytest.approx(
        cmds.getAttr(f"{dst.name}.rotate")[0], abs=1e-6
    )


def test_snap_to_scale_only_copies_scale():
    src = Transform.create(name="tm_snap_scl_src")
    dst = Transform.create(name="tm_snap_scl_dst")

    cmds.setAttr(f"{src.name}.scale", 1.0, 1.0, 1.0, type="double3")
    cmds.setAttr(f"{dst.name}.scale", 1.5, 2.0, 2.5, type="double3")

    src.snap_to(dst, position=False, rotation=False, scale=True)

    assert cmds.getAttr(f"{src.name}.scale")[0] == pytest.approx(
        cmds.getAttr(f"{dst.name}.scale")[0], abs=1e-6
    )


def test_snap_to_accepts_target_name_string():
    src = Transform.create(name="tm_snap_str_src")
    dst = Transform.create(name="tm_snap_str_dst")

    cmds.setAttr(f"{dst.name}.translate", 2.0, 3.0, 4.0, type="double3")
    cmds.setAttr(f"{dst.name}.rotate", 5.0, 15.0, 25.0, type="double3")
    cmds.setAttr(f"{dst.name}.scale", 1.2, 0.8, 1.1, type="double3")

    src.snap_to(dst.name, position=True, rotation=True, scale=True)

    assert cmds.getAttr(f"{src.name}.translate")[0] == pytest.approx(
        cmds.getAttr(f"{dst.name}.translate")[0], abs=1e-6
    )
    assert cmds.getAttr(f"{src.name}.rotate")[0] == pytest.approx(
        cmds.getAttr(f"{dst.name}.rotate")[0], abs=1e-6
    )
    assert cmds.getAttr(f"{src.name}.scale")[0] == pytest.approx(
        cmds.getAttr(f"{dst.name}.scale")[0], abs=1e-6
    )


def test_snap_to_raises_for_non_transform_target():
    src = Transform.create(name="tm_snap_err_src")
    non_xform = cmds.createNode("mesh", name="tm_not_transform")

    with pytest.raises(TypeError):
        src.snap_to(non_xform)


def test_freeze_zeroes_translate_and_rotate_keeps_scale_when_scale_false():
    t = Transform.create(name="tm_freeze")

    cmds.setAttr(f"{t.name}.translate", 7.0, 8.0, 9.0, type="double3")
    cmds.setAttr(f"{t.name}.rotate", 15.0, 25.0, 35.0, type="double3")
    cmds.setAttr(f"{t.name}.scale", 1.5, 1.1, 0.9, type="double3")

    t.freeze(translate=True, rotate=True, scale=False)

    assert cmds.getAttr(f"{t.name}.translate")[0] == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)
    assert cmds.getAttr(f"{t.name}.rotate")[0] == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)
    assert cmds.getAttr(f"{t.name}.scale")[0] == pytest.approx((1.5, 1.1, 0.9), abs=1e-6)

def test_getting_world_matrix():
    t = Transform.create(name="tm_world_matrix")
    cmds.setAttr(f"{t.name}.translate", 1.0, 2.0, 3.0, type="double3")
    cmds.setAttr(f"{t.name}.rotate", 10.0, 20.0, 30.0, type="double3")
    cmds.setAttr(f"{t.name}.scale", 1.0, 2.0, 3.0, type="double3")

    world_matrix = t.world_matrix
    expected_matrix = OpenMaya.MMatrix(cmds.xform(t.name, query=True, matrix=True, worldSpace=True))

    assert list(world_matrix) == pytest.approx(expected_matrix, abs=1e-6)

def test_getting_matrix():
    t = Transform.create(name="tm_matrix")
    cmds.setAttr(f"{t.name}.translate", 4.0, 5.0, 6.0, type="double3")
    cmds.setAttr(f"{t.name}.rotate", 15.0, 25.0, 35.0, type="double3")
    cmds.setAttr(f"{t.name}.scale", 2.0, 3.0, 4.0, type="double3")

    local_matrix = t.matrix
    expected_matrix = OpenMaya.MMatrix(cmds.xform(t.name, query=True, matrix=True, objectSpace=True))

    assert list(local_matrix) == pytest.approx(expected_matrix, abs=1e-6)

def test_getting_parent_matrix():
    parent = Transform.create(name="tm_parent_matrix")
    child = Transform.create(name="tm_child_matrix", parent=parent.name)

    cmds.setAttr(f"{parent.name}.translate", 1.0, 0.0, 0.0, type="double3")
    cmds.setAttr(f"{parent.name}.rotate", 0.0, 45.0, 0.0, type="double3")
    cmds.setAttr(f"{parent.name}.scale", 1.0, 1.0, 1.0, type="double3")

    parent_matrix = child.parent_matrix
    expected_matrix = OpenMaya.MMatrix(cmds.xform(parent.name, query=True, matrix=True, worldSpace=True))

    assert list(parent_matrix) == pytest.approx(expected_matrix, abs=1e-6)

def test_getting_and_setting_translate():
    t = Transform.create(name="tm_translate")
    t.translate = OpenMaya.MVector(3.0, 4.0, 5.0)

    translate = t.translate
    assert (translate.x, translate.y, translate.z) == pytest.approx((3.0, 4.0, 5.0), abs=1e-6)
    assert t.translate_x == pytest.approx(3.0, abs=1e-6)
    assert t.translate_y == pytest.approx(4.0, abs=1e-6)
    assert t.translate_z == pytest.approx(5.0, abs=1e-6)
    # individual axis
    t.translate_x = 6.0
    t.translate_y = 7.0
    t.translate_z = 8.0
    translate = t.translate
    assert (translate.x, translate.y, translate.z) == pytest.approx((6.0, 7.0, 8.0), abs=1e-6)

def test_getting_and_setting_rotate():
    t = Transform.create(name="tm_rotate")
    t.rotate = OpenMaya.MVector(10.0, 20.0, 30.0)

    rotate = t.rotate
    assert (rotate.x, rotate.y, rotate.z) == pytest.approx((10.0, 20.0, 30.0), abs=1e-6)
    assert t.rotate_x == pytest.approx(10.0, abs=1e-6)
    assert t.rotate_y == pytest.approx(20.0, abs=1e-6)
    assert t.rotate_z == pytest.approx(30.0, abs=1e-6)
    # individual axis
    t.rotate_x = 15.0
    t.rotate_y = 25.0
    t.rotate_z = 35.0
    rotate = t.rotate
    assert (rotate.x, rotate.y, rotate.z) == pytest.approx((15.0, 25.0, 35.0), abs=1e-6)

def test_getting_and_setting_scale():
    t = Transform.create(name="tm_scale")
    t.scale = OpenMaya.MVector(1.5, 2.0, 2.5)

    scale = t.scale
    assert (scale.x, scale.y, scale.z) == pytest.approx((1.5, 2.0, 2.5), abs=1e-6)
    assert t.scale_x == pytest.approx(1.5, abs=1e-6)
    assert t.scale_y == pytest.approx(2.0, abs=1e-6)
    assert t.scale_z == pytest.approx(2.5, abs=1e-6)
    # individual axis
    t.scale_x = 2.0
    t.scale_y = 3.0
    t.scale_z = 4.0
    scale = t.scale
    assert (scale.x, scale.y, scale.z) == pytest.approx((2.0, 3.0, 4.0), abs=1e-6)