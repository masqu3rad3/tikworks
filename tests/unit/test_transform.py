import pytest
from maya import cmds
from maya.api import OpenMaya

from tik.maya.types.transform import Transform


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
    transform = Transform.create(name="tm_no_shapes")
    assert transform.shapes == []


def test_shapes_returns_resolved_wrappers():
    transform = Transform.create(name="tm_with_shape")
    shape_name = cmds.createNode("mesh", parent=transform.name)
    shapes = transform.shapes

    assert len(shapes) == 1
    assert hasattr(shapes[0], "name")
    assert shapes[0].name == shape_name


def test_world_translation_matches_channel():
    transform = Transform.create(name="tm_world_trans")
    cmds.setAttr(f"{transform.name}.translate", 1.0, 2.0, 3.0, type="double3")

    translation = transform.world_translation
    assert (translation.x, translation.y, translation.z) == pytest.approx(
        (1.0, 2.0, 3.0), abs=1e-6
    )


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
    assert cmds.getAttr(f"{src.name}.rotate")[0] == pytest.approx(
        (0.0, 0.0, 0.0), abs=1e-6
    )
    assert cmds.getAttr(f"{src.name}.scale")[0] == pytest.approx(
        (1.0, 1.0, 1.0), abs=1e-6
    )


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
    transform = Transform.create(name="tm_freeze")

    cmds.setAttr(f"{transform.name}.translate", 7.0, 8.0, 9.0, type="double3")
    cmds.setAttr(f"{transform.name}.rotate", 15.0, 25.0, 35.0, type="double3")
    cmds.setAttr(f"{transform.name}.scale", 1.5, 1.1, 0.9, type="double3")

    transform.freeze(translate=True, rotate=True, scale=False)

    assert cmds.getAttr(f"{transform.name}.translate")[0] == pytest.approx(
        (0.0, 0.0, 0.0), abs=1e-6
    )
    assert cmds.getAttr(f"{transform.name}.rotate")[0] == pytest.approx(
        (0.0, 0.0, 0.0), abs=1e-6
    )
    assert cmds.getAttr(f"{transform.name}.scale")[0] == pytest.approx(
        (1.5, 1.1, 0.9), abs=1e-6
    )


def test_getting_world_matrix():
    transform = Transform.create(name="tm_world_matrix")
    cmds.setAttr(f"{transform.name}.translate", 1.0, 2.0, 3.0, type="double3")
    cmds.setAttr(f"{transform.name}.rotate", 10.0, 20.0, 30.0, type="double3")
    cmds.setAttr(f"{transform.name}.scale", 1.0, 2.0, 3.0, type="double3")

    world_matrix = transform.world_matrix
    expected_matrix = OpenMaya.MMatrix(
        cmds.xform(transform.name, query=True, matrix=True, worldSpace=True)
    )

    assert list(world_matrix) == pytest.approx(expected_matrix, abs=1e-6)


def test_getting_matrix():
    transform = Transform.create(name="tm_matrix")
    cmds.setAttr(f"{transform.name}.translate", 4.0, 5.0, 6.0, type="double3")
    cmds.setAttr(f"{transform.name}.rotate", 15.0, 25.0, 35.0, type="double3")
    cmds.setAttr(f"{transform.name}.scale", 2.0, 3.0, 4.0, type="double3")

    local_matrix = transform.matrix
    expected_matrix = OpenMaya.MMatrix(
        cmds.xform(transform.name, query=True, matrix=True, objectSpace=True)
    )

    assert list(local_matrix) == pytest.approx(expected_matrix, abs=1e-6)


def test_getting_parent_matrix():
    parent = Transform.create(name="tm_parent_matrix")
    child = Transform.create(name="tm_child_matrix", parent=parent.name)

    cmds.setAttr(f"{parent.name}.translate", 1.0, 0.0, 0.0, type="double3")
    cmds.setAttr(f"{parent.name}.rotate", 0.0, 45.0, 0.0, type="double3")
    cmds.setAttr(f"{parent.name}.scale", 1.0, 1.0, 1.0, type="double3")

    parent_matrix = child.parent_matrix
    expected_matrix = OpenMaya.MMatrix(
        cmds.xform(parent.name, query=True, matrix=True, worldSpace=True)
    )

    assert list(parent_matrix) == pytest.approx(expected_matrix, abs=1e-6)


def test_getting_and_setting_translate():
    transform = Transform.create(name="tm_translate")
    transform.translate = OpenMaya.MVector(3.0, 4.0, 5.0)

    translate = transform.translate
    assert (translate.x, translate.y, translate.z) == pytest.approx(
        (3.0, 4.0, 5.0), abs=1e-6
    )
    assert transform.translate_x == pytest.approx(3.0, abs=1e-6)
    assert transform.translate_y == pytest.approx(4.0, abs=1e-6)
    assert transform.translate_z == pytest.approx(5.0, abs=1e-6)
    # individual axis
    transform.translate_x = 6.0
    transform.translate_y = 7.0
    transform.translate_z = 8.0
    translate = transform.translate
    assert (translate.x, translate.y, translate.z) == pytest.approx(
        (6.0, 7.0, 8.0), abs=1e-6
    )


def test_getting_and_setting_rotate():
    transform = Transform.create(name="tm_rotate")
    transform.rotate = OpenMaya.MVector(10.0, 20.0, 30.0)

    rotate = transform.rotate
    assert (rotate.x, rotate.y, rotate.z) == pytest.approx((10.0, 20.0, 30.0), abs=1e-6)
    assert transform.rotate_x == pytest.approx(10.0, abs=1e-6)
    assert transform.rotate_y == pytest.approx(20.0, abs=1e-6)
    assert transform.rotate_z == pytest.approx(30.0, abs=1e-6)
    # individual axis
    transform.rotate_x = 15.0
    transform.rotate_y = 25.0
    transform.rotate_z = 35.0
    rotate = transform.rotate
    assert (rotate.x, rotate.y, rotate.z) == pytest.approx((15.0, 25.0, 35.0), abs=1e-6)


def test_getting_and_setting_scale():
    transform = Transform.create(name="tm_scale")
    transform.scale = OpenMaya.MVector(1.5, 2.0, 2.5)

    scale = transform.scale
    assert (scale.x, scale.y, scale.z) == pytest.approx((1.5, 2.0, 2.5), abs=1e-6)
    assert transform.scale_x == pytest.approx(1.5, abs=1e-6)
    assert transform.scale_y == pytest.approx(2.0, abs=1e-6)
    assert transform.scale_z == pytest.approx(2.5, abs=1e-6)
    # individual axis
    transform.scale_x = 2.0
    transform.scale_y = 3.0
    transform.scale_z = 4.0
    scale = transform.scale
    assert (scale.x, scale.y, scale.z) == pytest.approx((2.0, 3.0, 4.0), abs=1e-6)


def test_collect_children_recursive():
    # Setup hierarchy:
    # root
    #   |- child1
    #   |    |- grandChild1
    #   |- child2
    root = Transform.create(name="root")
    child1 = Transform.create(name="child1", parent=root.name)
    grandChild1 = Transform.create(name="grandChild1", parent=child1.name)
    child2 = Transform.create(name="child2", parent=root.name)

    collected = root.collect_hierarchy()
    names = {node.name for node in collected}
    assert names == {"child1", "grandChild1", "child2"}


def test_collect_children_with_depth_limit():
    root = Transform.create(name="rootD")
    child1 = Transform.create(name="child1D", parent=root.name)
    grandChild1 = Transform.create(name="grandChild1D", parent=child1.name)

    collected = root.collect_hierarchy(max_depth=1)
    names = {node.name for node in collected}
    assert "child1D" in names
    assert "grandChild1D" not in names


def test_collect_children_include_self():
    root = Transform.create(name="rootS")
    collected = root.collect_hierarchy(include_self=True)
    assert len(collected) == 1
    assert collected[0].name == "rootS"


def test_collect_children_filter_type():
    root = Transform.create(name="rootT")
    child1 = Transform.create(name="child1T", parent=root.name)
    # Add a shape
    shape = cmds.createNode("mesh", parent=root.name, name="meshShape")

    # Filter for transforms only
    collected = root.collect_hierarchy(node_types=["transform"])
    names = {node.name for node in collected}
    assert "child1T" in names
    assert "meshShape" not in names

    # Filter for meshes only
    collected_mesh = root.collect_hierarchy(node_types=["mesh"])
    names_mesh = {node.name for node in collected_mesh}
    assert "meshShape" in names_mesh
    assert "child1T" not in names_mesh


def test_collect_shape_transforms():
    root = Transform.create(name="rootST")
    child1 = Transform.create(name="child1ST", parent=root.name)

    # Add shapes
    s1 = cmds.createNode("mesh", parent=root.name, name="s1")
    s2 = cmds.createNode("nurbsCurve", parent=child1.name, name="s2")

    transforms = root.collect_shape_transforms()
    names = {transform.name for transform in transforms}

    assert "rootST" in names
    assert "child1ST" in names


def test_collect_hierarchy_with_string_node_type():
    root = Transform.create(name="rootStr")
    child1 = Transform.create(name="child1Str", parent=root.name)

    collected = root.collect_hierarchy(node_types="transform")
    names = {node.name for node in collected}
    assert "child1Str" in names


class TestInsertOffsetParent:
    """Tests for the create_offset_group method."""

    def test_create_offset_group_basic(self):
        """Test creating an offset group with default name."""
        node = Transform.create(name="offsetChild")
        cmds.setAttr(f"{node.name}.translate", 5, 10, 15, type="double3")
        cmds.setAttr(f"{node.name}.rotate", 10, 20, 30, type="double3")

        offset = node.create_offset_group()

        # Verify offset name
        assert offset.name == "offsetChild_OFFSET"

        # Verify offset is now the parent
        parents = cmds.listRelatives(node.name, parent=True)
        assert parents and parents[0] == offset.name

        # Verify offset has same transforms as original
        offset_trans = cmds.getAttr(f"{offset.name}.translate")[0]
        assert offset_trans == pytest.approx((5, 10, 15), abs=1e-5)

        offset_rot = cmds.getAttr(f"{offset.name}.rotate")[0]
        assert offset_rot == pytest.approx((10, 20, 30), abs=1e-5)

    def test_create_offset_group_custom_name(self):
        """Test creating an offset group with custom name."""
        node = Transform.create(name="customOffsetChild")

        offset = node.create_offset_group(name="myCustomOffset")

        assert offset.name == "myCustomOffset"
        parents = cmds.listRelatives(node.name, parent=True)
        assert parents and parents[0] == "myCustomOffset"

    def test_create_offset_group_preserves_hierarchy(self):
        """Test create_offset_group preserves original parent hierarchy."""
        grandparent = Transform.create(name="grandparent")
        parent = Transform.create(name="parentNode", parent=grandparent)
        child = Transform.create(name="childNode", parent=parent)
        cmds.setAttr(f"{child.name}.translate", 3, 6, 9, type="double3")

        offset = child.create_offset_group()

        # Verify hierarchy: grandparent -> parent -> offset -> child
        child_parents = cmds.listRelatives(child.name, parent=True)
        assert child_parents and child_parents[0] == offset.name

        offset_parents = cmds.listRelatives(offset.name, parent=True)
        assert offset_parents and offset_parents[0] == parent.name

    def test_create_offset_group_no_parent(self):
        """Test create_offset_group when node has no parent."""
        node = Transform.create(name="noParentNode")
        cmds.setAttr(f"{node.name}.translate", 1, 2, 3, type="double3")

        offset = node.create_offset_group()

        # Verify offset is parent of node
        parents = cmds.listRelatives(node.name, parent=True)
        assert parents and parents[0] == offset.name

        # Verify offset has no parent (world space)
        offset_parents = cmds.listRelatives(offset.name, parent=True)
        assert offset_parents is None
