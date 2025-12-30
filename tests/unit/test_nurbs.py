import pytest
from maya import cmds
from maya.api import OpenMaya
from tik.maya.types.nurbs import Nurbs

class TestNurbsCreate:
    def test_create_primitive_plane(self):
        n = Nurbs.create("nurbsPlane", name="testPlane")
        assert isinstance(n, Nurbs)
        assert cmds.nodeType(n.name) == "nurbsSurface"
        # nurbsPlane returns transform usually, but Nurbs wrapper wraps the shape
        # The create method handles the return value of cmds.nurbsPlane which is [transform, shape] usually
        # Let's verify what cmds.nurbsPlane returns. It returns [transform, makeNurbsPlane].
        # Wait, cmds.nurbsPlane returns [transform, makeNurbsPlane] (history node).
        # The create method in nurbs.py says:
        # result = getattr(cmds, cmd)(**kwargs)
        # if isinstance(result, (list, tuple)): result = result[0]
        # So it gets the transform.
        # Then Nurbs(result) is called. Nurbs inherits ShapeNode.
        # ShapeNode(transform) finds the shape.
        assert n.transform.name == "testPlane"

    def test_create_primitive_sphere(self):
        n = Nurbs.create("sphere", name="testSphere")
        assert isinstance(n, Nurbs)
        assert n.transform.name == "testSphere"

    def test_create_node_surface(self):
        # cmds.createNode("nurbsSurface") returns the shape name directly
        n = Nurbs.create("nurbsSurface", name="testSurfaceShape")
        assert isinstance(n, Nurbs)
        assert n.name == "testSurfaceShape"

    def test_create_invalid_command_raises(self):
        with pytest.raises(ValueError, match="Command 'invalidCmd' is not valid"):
            Nurbs.create("invalidCmd")

class TestNurbsCVs:
    def test_cvs_world_space(self):
        # Create a plane at 0,0,0
        n = Nurbs.create("nurbsPlane", w=1, lr=1, d=3, u=1, v=1, ax=(0, 1, 0))
        # A default 1x1 plane usually has CVs.
        cvs = n.cvs(space="world")
        assert isinstance(cvs, OpenMaya.MPointArray)
        assert len(cvs) > 0

    def test_cvs_object_space(self):
        n = Nurbs.create("nurbsPlane")
        cvs = n.cvs(space="object")
        assert len(cvs) > 0

    def test_cvs_transform_space(self):
        n = Nurbs.create("nurbsPlane")
        cvs = n.cvs(space="transform")
        assert len(cvs) > 0

    def test_cvs_invalid_space_raises(self):
        n = Nurbs.create("nurbsPlane")
        with pytest.raises(ValueError, match="Invalid space 'invalid'"):
            n.cvs(space="invalid")

