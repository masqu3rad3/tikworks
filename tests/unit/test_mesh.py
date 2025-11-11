import pytest
from maya import cmds
from maya.api import OpenMaya

from tikmaya.types.mesh import Mesh


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
