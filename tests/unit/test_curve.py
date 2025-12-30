import pytest
from maya import cmds
from maya.api import OpenMaya
from tik.maya.types.curve import Curve

class TestCurveCreate:
    def test_create_curve_basic(self):
        # Create a simple degree 1 curve
        c = Curve.create(d=1, p=[(0, 0, 0), (1, 1, 1)])
        assert isinstance(c, Curve)
        assert cmds.nodeType(c.name) == "nurbsCurve"
        # Check degree
        assert cmds.getAttr(f"{c.name}.degree") == 1

    def test_create_curve_with_name(self):
        # When name is provided, the shape should be renamed to <name>Shape
        c = Curve.create(d=1, p=[(0, 0, 0), (1, 0, 0)], name="myCurve")
        assert isinstance(c, Curve)
        # The transform should be named "myCurve" because cmds.curve(name="myCurve") names the transform
        # But wait, cmds.curve(name="myCurve") creates "myCurve" transform and "curveShape1" (or similar).
        # The code does:
        # curve = cls(result) -> wraps shape
        # if kwargs.get("name"): curve.rename(f"{kwargs.get('name')}Shape")
        # So if I pass name="myCurve", cmds.curve creates transform "myCurve".
        # Then the wrapper renames the shape to "myCurveShape".

        assert c.transform.name == "myCurve"
        assert c.name == "myCurveShape"

class TestCurveCVs:
    def test_cvs_world_space(self):
        # Create a curve
        c = Curve.create(d=1, p=[(0, 0, 0), (1, 1, 1), (2, 2, 2)])
        cvs = c.cvs(space="world")
        assert isinstance(cvs, OpenMaya.MPointArray)
        assert len(cvs) == 3

        p0 = cvs[0]
        assert (p0.x, p0.y, p0.z) == (0, 0, 0)
        p1 = cvs[1]
        assert (p1.x, p1.y, p1.z) == (1, 1, 1)

    def test_cvs_object_space(self):
        c = Curve.create(d=1, p=[(0, 0, 0), (1, 0, 0)])
        # Move transform
        cmds.move(5, 5, 5, c.transform.name)

        # Object space CVs should remain at creation coordinates relative to transform
        cvs = c.cvs(space="object")
        p0 = cvs[0]
        assert (p0.x, p0.y, p0.z) == (0, 0, 0)

        # World space should be shifted
        cvs_world = c.cvs(space="world")
        p0_world = cvs_world[0]
        assert (p0_world.x, p0_world.y, p0_world.z) == (5, 5, 5)

    def test_cvs_transform_space(self):
        c = Curve.create(d=1, p=[(1, 0, 0), (2, 0, 0)])
        cvs = c.cvs(space="transform")
        assert len(cvs) == 2

    def test_cvs_invalid_space_raises(self):
        c = Curve.create(d=1, p=[(0, 0, 0), (1, 0, 0)])
        with pytest.raises(ValueError, match="Invalid space 'invalid'"):
            c.cvs(space="invalid")

class TestCurveLineWidth:
    def test_line_width_property(self):
        c = Curve.create(d=1, p=[(0, 0, 0), (1, 0, 0)])

        # Default seems to be -1.0 (default width) in some Maya versions/environments
        # Just check it returns a float
        assert isinstance(c.line_width, float)

        # Set new width
        c.line_width = 2.5
        assert c.line_width == 2.5

        # Verify with cmds
        assert cmds.getAttr(f"{c.name}.lineWidth") == 2.5

