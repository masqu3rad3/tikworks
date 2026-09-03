import pytest
from maya import cmds
from maya.api import OpenMaya

from tik.maya.types.mesh import Mesh


def test_create_with_valid_primitive_returns_mesh_wrapper():
    mesh = Mesh.create("polySphere", name="tm_mesh_sphere")
    assert cmds.nodeType(mesh.name) == "mesh"

    sel = OpenMaya.MSelectionList()
    sel.add(mesh.name)
    dag = sel.getDagPath(0)
    mfn = OpenMaya.MFnMesh(dag)
    assert isinstance(mfn, OpenMaya.MFnMesh)


def test_create_with_valid_mesh_command_returns_mesh_wrapper():
    mesh = Mesh.create("mesh", name="tm_raw_mesh_shape")
    assert cmds.nodeType(mesh.name) == "mesh"
    assert cmds.nodeType(mesh.transform.name) == "transform"


def test_create_with_invalid_command_raises_value_error():
    with pytest.raises(ValueError):
        Mesh.create("polyBanana")


def test_vertices_returns_points_in_requested_spaces_and_respects_translate():
    xform, _ = cmds.polySphere(name="tm_vertices_sphere", r=1.0)
    shape = cmds.listRelatives(xform, shapes=True, type="mesh", fullPath=False)[0]
    mesh = Mesh(shape)

    cmds.setAttr(f"{xform}.translate", 3.0, 4.0, 5.0, type="double3")

    pts_object = mesh.vertices(space="object")
    pts_world = mesh.vertices(space="world")
    pts_transform = mesh.vertices(space="transform")

    assert len(pts_object) == len(pts_world) == len(pts_transform)

    index = 0
    dx = pts_world[index].x - pts_object[index].x
    dy = pts_world[index].y - pts_object[index].y
    dz = pts_world[index].z - pts_object[index].z
    assert (dx, dy, dz) == pytest.approx((3.0, 4.0, 5.0), abs=1e-5)

    assert (pts_object[index].x, pts_object[index].y, pts_object[index].z) == pytest.approx(
        (pts_transform[index].x, pts_transform[index].y, pts_transform[index].z), abs=1e-6
    )


def test_vertices_invalid_space_raises_value_error():
    xform, _ = cmds.polySphere(name="tm_invalid_space", r=1.0)
    shape = cmds.listRelatives(xform, shapes=True, type="mesh", fullPath=False)[0]
    mesh = Mesh(shape)

    with pytest.raises(ValueError):
        mesh.vertices(space="bogus")


def test_vertices_in_radius_counts_vertices_near_point():
    xform, _ = cmds.polyPlane(name="tm_radius_plane", w=1.0, h=1.0, sx=1, sy=1)
    shape = cmds.listRelatives(xform, shapes=True, type="mesh", fullPath=False)[0]
    mesh = Mesh(shape)

    small = mesh.vertices_in_radius((0.0, 0.0, 0.0), radius=0.25)
    large = mesh.vertices_in_radius((0.0, 0.0, 0.0), radius=0.75)

    sel = OpenMaya.MSelectionList()
    sel.add(shape)
    mfn = OpenMaya.MFnMesh(sel.getDagPath(0))

    assert small == []
    assert len(large) == mfn.numVertices


def test_vertices_in_radius_empty_when_point_far_away():
    xform, _ = cmds.polySphere(name="tm_radius_far", r=1.0)
    shape = cmds.listRelatives(xform, shapes=True, type="mesh", fullPath=False)[0]
    mesh = Mesh(shape)

    result = mesh.vertices_in_radius((1000.0, 1000.0, 1000.0), radius=0.5)
    assert result == []


def test_unlock_normals_unlocks_all_and_softens_edges():
    xform, _ = cmds.polyCube(name="tm_unlock_cube", w=1.0, h=1.0, d=1.0)
    shape = cmds.listRelatives(xform, shapes=True, type="mesh", fullPath=False)[0]
    mesh = Mesh(shape)

    sel = OpenMaya.MSelectionList()
    sel.add(shape)
    dag = sel.getDagPath(0)
    mfn = OpenMaya.MFnMesh(dag)

    mfn.lockVertexNormals(OpenMaya.MIntArray(range(mfn.numVertices)))
    assert any(mfn.isNormalLocked(index) for index in range(mfn.numNormals))

    mesh.unlock_normals(soften=True)

    sel2 = OpenMaya.MSelectionList()
    sel2.add(mesh.long_name)
    mfn2 = OpenMaya.MFnMesh(sel2.getDagPath(0))

    assert not any(mfn2.isNormalLocked(index) for index in range(mfn2.numNormals))
    assert all(mfn2.isEdgeSmooth(index) for index in range(mfn2.numEdges))


def test_vertex_colors_get_set_all():
    """Test setting and getting vertex colors for all vertices."""
    mesh = Mesh.create("polyPlane", name="tm_color_plane", sx=1, sy=1)
    # Plane 1x1 has 4 vertices.

    # Initially no colors or displayColors off
    mesh["displayColors"].set(False)
    assert mesh.get_vertex_colors() is None

    red = (1.0, 0.0, 0.0)
    mesh.set_vertex_colors(red)

    assert mesh["displayColors"].get() is True

    colors = mesh.get_vertex_colors()
    assert colors is not None
    assert len(colors) == 4
    for color_val in colors:
        assert (color_val.r, color_val.g, color_val.b) == pytest.approx(red, abs=1e-5)


def test_vertex_colors_get_set_indices():
    """Test setting and getting vertex colors for specific indices."""
    mesh = Mesh.create("polyPlane", name="tm_color_plane_idx", sx=1, sy=1)
    # 4 vertices: 0, 1, 2, 3

    # Initialize all to black first to have a baseline
    mesh.set_vertex_colors((0.0, 0.0, 0.0))

    blue = (0.0, 0.0, 1.0)
    indices = [0, 2]

    # Set blue on 0 and 2
    mesh.set_vertex_colors(blue, indices=indices)

    # Check subset
    subset_colors = mesh.get_vertex_colors(indices=indices)
    assert len(subset_colors) == 2
    for color_val in subset_colors:
        assert (color_val.r, color_val.g, color_val.b) == pytest.approx(blue, abs=1e-5)

    # Check others (should be black)
    other_indices = [1, 3]
    other_colors = mesh.get_vertex_colors(indices=other_indices)
    assert len(other_colors) == 2
    for color_val in other_colors:
        assert (color_val.r, color_val.g, color_val.b) == pytest.approx((0.0, 0.0, 0.0), abs=1e-5)


def test_vertex_colors_display_off():
    """Test that get_vertex_colors returns None when displayColors is off."""
    mesh = Mesh.create("polyCube", name="tm_color_cube")
    mesh.set_vertex_colors((1.0, 1.0, 1.0))
    assert mesh.get_vertex_colors() is not None

    mesh["displayColors"].set(False)
    assert mesh.get_vertex_colors() is None


def test_set_vertex_colors_with_color_object():
    """Test setting vertex colors using a Color object."""
    from tik.core.color import Color

    mesh = Mesh.create("polyPlane", name="tm_color_obj_plane", sx=1, sy=1)

    green = Color("green")
    mesh.set_vertex_colors(green)

    assert mesh["displayColors"].get() is True
    colors = mesh.get_vertex_colors()
    assert colors is not None
    # Green is (0, 0.5, 0)
    for color_val in colors:
        assert color_val.g == pytest.approx(0.5, abs=1e-2)


def test_set_vertex_colors_clears_when_empty():
    """Test set_vertex_colors disables display colors when given empty/None color."""
    mesh = Mesh.create("polyPlane", name="tm_clear_colors_plane", sx=1, sy=1)

    # First set some colors
    mesh.set_vertex_colors((1.0, 0.0, 0.0))
    assert mesh["displayColors"].get() is True

    # Clear colors by passing empty/falsy value
    mesh.set_vertex_colors(None)
    assert mesh["displayColors"].get() is False

    # Also test with empty tuple
    mesh.set_vertex_colors((1.0, 0.0, 0.0))
    assert mesh["displayColors"].get() is True
    mesh.set_vertex_colors(())
    assert mesh["displayColors"].get() is False


def test_get_vertex_colors_empty_array_returns_none():
    """Test get_vertex_colors returns None when colors array is empty.

    This covers line 138 in mesh.py: if len(colors) == 0: return None
    We use module-level patching to mock the OpenMaya.MFnMesh class.
    """
    from unittest.mock import patch, MagicMock
    import tik.maya.types.mesh as mesh_module

    mesh = Mesh.create("polyPlane", name="tm_empty_colors_mesh", sx=1, sy=1)
    mesh["displayColors"].set(True)

    # Create a mock MFnMesh that returns empty color array
    mock_mfn_mesh_instance = MagicMock()
    mock_mfn_mesh_instance.getVertexColors.return_value = OpenMaya.MColorArray()

    mock_mfn_mesh_class = MagicMock(return_value=mock_mfn_mesh_instance)

    # Patch OpenMaya.MFnMesh in the mesh module's namespace
    with patch.object(mesh_module.OpenMaya, "MFnMesh", mock_mfn_mesh_class):
        result = mesh.get_vertex_colors()

    assert result is None
