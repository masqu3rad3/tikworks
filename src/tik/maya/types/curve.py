"""Curve node type wrapper."""

from maya import cmds
from maya.api import OpenMaya

from ..core.registry import register
from ..core.shapenode import ShapeNode


@register("nurbsCurve")
class Curve(ShapeNode):
    """Wrapper for NURBS curve nodes."""

    @classmethod
    def create(cls, *args, **kwargs):
        """Create a NURBS curve node."""
        result = cmds.curve(*args, **kwargs)
        curve = cls(result)
        if kwargs.get("name"):
            curve.rename(f"{kwargs.get('name')}Shape")
        return cls(result)

    def cvs(self, space="world"):
        """Return all control vertex positions.

        Args:
            space : str, optional
                Coordinate space to return the CVs in.
                Accepted values: "world", "object", "transform".
                Default is "world".
        Returns:
            OpenMaya.MPointArray
                Array of CV positions in the requested space.
        """
        # Map simple string options to MSpace enums
        _space_map = {
            "world": OpenMaya.MSpace.kWorld,
            "object": OpenMaya.MSpace.kObject,
            "transform": OpenMaya.MSpace.kTransform,
        }
        if space not in _space_map:
            raise ValueError(
                f"Invalid space '{space}'. Must be one of: "
                f"{', '.join(_space_map.keys())}"
            )

        mfn_object = OpenMaya.MFnNurbsCurve(self.dag_path)
        return mfn_object.cvPositions(_space_map[space])

    @property
    def line_width(self):
        """Get or set the line width of the curve for display purposes."""
        return self["lineWidth"].get()

    @line_width.setter
    def line_width(self, value):
        self["lineWidth"].set(value)

    def scale_points(self, scale_factor, pivot="object", pivot_point=None):
        """Scale the control points of the curve.

        Args:
            scale_factor : float
                Uniform scale factor to apply to all CVs.
            pivot : str, optional
                Pivot mode for scaling. Accepted values are "object", "center" or "custom".
                Default is "object".
            pivot_point : tuple of float, optional
                Custom pivot point (x, y, z) if pivot_mode is "custom".
        """
        cvs = self.cvs(space="object")

        if pivot == "custom":
            if pivot_point is None:
                raise ValueError(
                    "pivot_point must be provided when pivot_mode is 'custom'."
                )
            pivot = OpenMaya.MPoint(*pivot_point)
        elif pivot == "object":
            pivot = OpenMaya.MPoint(0, 0, 0)
        elif pivot == "center":
            bbox = OpenMaya.MBoundingBox()
            for cv in cvs:
                bbox.expand(cv)
            pivot = bbox.center
        else:
            raise ValueError(
                "Invalid pivot_mode. Must be 'object', 'center' or 'custom'."
            )

        scaled_cvs = OpenMaya.MPointArray()
        for cv in cvs:
            # Translate CV to origin based on pivot
            cv -= pivot
            # Scale
            cv *= scale_factor
            # Translate back
            cv += pivot
            scaled_cvs.append(cv)

        # Update the CV positions
        mfn_object = OpenMaya.MFnNurbsCurve(self.dag_path)
        mfn_object.setCVPositions(scaled_cvs)
