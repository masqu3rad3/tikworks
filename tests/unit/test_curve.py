import pytest
from maya import cmds
from maya.api import OpenMaya
from tik.maya.types.curve import Curve

class TestCurveCreate:
    def test_create_curve_basic(self):
        # Create a simple degree 1 curve
        curve = Curve.create(d=1, p=[(0, 0, 0), (1, 1, 1)])
        assert isinstance(curve, Curve)
        assert cmds.nodeType(curve.name) == "nurbsCurve"
        # Check degree
        assert cmds.getAttr(f"{curve.name}.degree") == 1

    def test_create_curve_with_name(self):
        # When name is provided, the shape should be renamed to <name>Shape
        curve = Curve.create(d=1, p=[(0, 0, 0), (1, 0, 0)], name="myCurve")
        assert isinstance(curve, Curve)
        # The transform should be named "myCurve" because cmds.curve(name="myCurve") names the transform
        # But wait, cmds.curve(name="myCurve") creates "myCurve" transform and "curveShape1" (or similar).
        # The code does:
        # curve = cls(result) -> wraps shape
        # if kwargs.get("name"): curve.rename(f"{kwargs.get('name')}Shape")
        # So if I pass name="myCurve", cmds.curve creates transform "myCurve".
        # Then the wrapper renames the shape to "myCurveShape".

        assert curve.transform.name == "myCurve"
        assert curve.name == "myCurveShape"

class TestCurveCVs:
    def test_cvs_world_space(self):
        # Create a curve
        curve = Curve.create(d=1, p=[(0, 0, 0), (1, 1, 1), (2, 2, 2)])
        cvs = curve.cvs(space="world")
        assert isinstance(cvs, OpenMaya.MPointArray)
        assert len(cvs) == 3

        p0 = cvs[0]
        assert (p0.x, p0.y, p0.z) == (0, 0, 0)
        p1 = cvs[1]
        assert (p1.x, p1.y, p1.z) == (1, 1, 1)

    def test_cvs_object_space(self):
        curve = Curve.create(d=1, p=[(0, 0, 0), (1, 0, 0)])
        # Move transform
        cmds.move(5, 5, 5, curve.transform.name)

        # Object space CVs should remain at creation coordinates relative to transform
        cvs = curve.cvs(space="object")
        p0 = cvs[0]
        assert (p0.x, p0.y, p0.z) == (0, 0, 0)

        # World space should be shifted
        cvs_world = curve.cvs(space="world")
        p0_world = cvs_world[0]
        assert (p0_world.x, p0_world.y, p0_world.z) == (5, 5, 5)

    def test_cvs_transform_space(self):
        curve = Curve.create(d=1, p=[(1, 0, 0), (2, 0, 0)])
        cvs = curve.cvs(space="transform")
        assert len(cvs) == 2

    def test_cvs_invalid_space_raises(self):
        curve = Curve.create(d=1, p=[(0, 0, 0), (1, 0, 0)])
        with pytest.raises(ValueError, match="Invalid space 'invalid'"):
            curve.cvs(space="invalid")

class TestCurveLineWidth:
    def test_line_width_property(self):
        curve = Curve.create(d=1, p=[(0, 0, 0), (1, 0, 0)])

        # Default seems to be -1.0 (default width) in some Maya versions/environments
        # Just check it returns a float
        assert isinstance(curve.line_width, float)

        # Set new width
        curve.line_width = 2.5
        assert curve.line_width == 2.5

        # Verify with cmds
        assert cmds.getAttr(f"{curve.name}.lineWidth") == 2.5


class TestCurveScaleCvs:
    """Tests for the scale_points method."""

    def test_scale_points_object_pivot(self):
        """Test scaling CVs with object pivot (origin)."""
        curve = Curve.create(d=1, p=[(1, 0, 0), (2, 0, 0), (3, 0, 0)])

        # Scale by 2x with object pivot (origin)
        curve.scale_points(2.0, pivot="object")

        cvs = curve.cvs(space="object")
        assert cvs[0].x == pytest.approx(2.0, abs=1e-5)
        assert cvs[1].x == pytest.approx(4.0, abs=1e-5)
        assert cvs[2].x == pytest.approx(6.0, abs=1e-5)

    def test_scale_points_center_pivot(self):
        """Test scaling CVs with center pivot (bounding box center)."""
        curve = Curve.create(d=1, p=[(-1, 0, 0), (0, 0, 0), (1, 0, 0)])

        # Get center before scaling
        cvs_before = curve.cvs(space="object")

        # Scale by 0.5 with center pivot
        curve.scale_points(0.5, pivot="center")

        cvs_after = curve.cvs(space="object")
        # With center pivot, the center should stay roughly the same
        # and the endpoints should move closer
        assert cvs_after[0].x == pytest.approx(-0.5, abs=1e-5)
        assert cvs_after[2].x == pytest.approx(0.5, abs=1e-5)

    def test_scale_points_custom_pivot(self):
        """Test scaling CVs with custom pivot point."""
        curve = Curve.create(d=1, p=[(0, 0, 0), (2, 0, 0)])

        # Scale by 2x with custom pivot at (2, 0, 0)
        curve.scale_points(2.0, pivot="custom", pivot_point=(2, 0, 0))

        cvs = curve.cvs(space="object")
        # Point at (0,0,0) should move to (-2, 0, 0) relative to pivot (2,0,0)
        assert cvs[0].x == pytest.approx(-2.0, abs=1e-5)
        # Point at (2,0,0) should stay at (2, 0, 0)
        assert cvs[1].x == pytest.approx(2.0, abs=1e-5)

    def test_scale_points_custom_pivot_requires_pivot_point(self):
        """Test scale_points raises ValueError when custom pivot without pivot_point."""
        curve = Curve.create(d=1, p=[(0, 0, 0), (1, 0, 0)])

        with pytest.raises(ValueError, match="pivot_point must be provided"):
            curve.scale_points(2.0, pivot="custom")

    def test_scale_points_invalid_pivot_raises(self):
        """Test scale_points raises ValueError for invalid pivot mode."""
        curve = Curve.create(d=1, p=[(0, 0, 0), (1, 0, 0)])

        with pytest.raises(ValueError, match="Invalid pivot_mode"):
            curve.scale_points(2.0, pivot="invalid_pivot")
