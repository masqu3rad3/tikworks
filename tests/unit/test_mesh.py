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

    i = 0
    dx = pts_world[i].x - pts_object[i].x
    dy = pts_world[i].y - pts_object[i].y
    dz = pts_world[i].z - pts_object[i].z
    assert (dx, dy, dz) == pytest.approx((3.0, 4.0, 5.0), abs=1e-5)

    assert (pts_object[i].x, pts_object[i].y, pts_object[i].z) == pytest.approx(
        (pts_transform[i].x, pts_transform[i].y, pts_transform[i].z), abs=1e-6
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
    assert any(mfn.isNormalLocked(i) for i in range(mfn.numNormals))

    mesh.unlock_normals(soften=True)

    sel2 = OpenMaya.MSelectionList()
    sel2.add(mesh.long_name)
    mfn2 = OpenMaya.MFnMesh(sel2.getDagPath(0))

    assert not any(mfn2.isNormalLocked(i) for i in range(mfn2.numNormals))
    assert all(mfn2.isEdgeSmooth(i) for i in range(mfn2.numEdges))


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


