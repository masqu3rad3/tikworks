"""
Controller facade.

A Controller is a semantic wrapper around a Transform node that:
- is tagged as a controller in Maya
- manages NURBS curve shapes under the transform
- exposes a controller-centric API
"""


from maya import cmds
import logging

from tikmaya.core.registry import resolve
from tikmaya.types.transform import Transform
from tikmaya.types.curve import Curve
from tikmaya.utils.shapes import ShapeLibrary  # Import the manager

LOG = logging.getLogger(__name__)


class Controller:
    ROLE_ATTR = "isController"
    # REQUIRED_TYPE = "transform"

    def __init__(self, node):
        self.node = resolve(node)
        # Validation
        if not isinstance(self.node, Transform):
            raise TypeError(
                f"Controller must wrap a Transform, got {type(self.node)}")

    @classmethod
    def create(cls, name, shape="circle", size=1.0, color=None, **kwargs):
        """
        Create a new controller transform and apply controller semantics.
        """
        node = Transform.create(name=name, **kwargs)
        ctrl = cls(node.long_name)
        ctrl._tag_as_controller()

        ctrl.set_shape(shape, size=size)

        if color:
            # Assumes Transform has a set_color method or similar
            ctrl.set_color(color)

        ctrl._post_create_cleanup()
        return ctrl

    @classmethod
    def from_node(cls, node):
        node = resolve(node)
        if not cls.is_controller(node):
            raise RuntimeError(f"Node '{node.name}' is not a Controller")
        return cls(node)

    @classmethod
    def is_controller(cls, node) -> bool:
        node = resolve(node)
        return node.has_attr(cls.ROLE_ATTR) and node.get_attr(cls.ROLE_ATTR)

    # --------------------------------------------------
    # tagging
    # --------------------------------------------------

    def _tag_as_controller(self):
        if not self.node[self.ROLE_ATTR].exists():
            self.node.add_attr(self.ROLE_ATTR, attributeType="bool", defaultValue=True)
        self.node[self.ROLE_ATTR].value = True

    # --------------------------------------------------
    # shape management
    # --------------------------------------------------

    def shapes(self) -> list:
        return self.node.shapes

    def clear_shapes(self):
        """Delete all shapes under the controller transform."""
        for shape in self.shapes():
            shape.delete()

    def add_shape(self, curve_data: dict, size=1.0):
        """
        Add a curve shape under the controller transform.
        Applies size scaling to the incoming points.
        """
        # 1. Scale points if size != 1.0
        # We assume curve_data['points'] is a list of (x,y,z) tuples
        points = curve_data['point']
        if size != 1.0:
            points = [(point[0] * size, point[1] * size, point[2] * size) for point in points]

        # 2. Prepare args for Curve.create
        # Ensure your Curve.create accepts these args
        curve = Curve.create(
            name=self.node.name,
            point=points,
            knot=curve_data.get('knot'),
            degree=curve_data.get('degree', 3),
            periodic=curve_data.get('periodic', False)
        )

        # 3. Shape Parenting Trick
        # Curve.create likely makes a Transform+Shape. We want just the shape.
        _excess_transform = curve.transform.name
        curve.parent = self.node
        cmds.delete(_excess_transform)

    def set_shape(self, shape, size=1.0):
        """
        Replace controller shapes.

        Args:
            shape (str | dict): Name of shape in library OR raw dict data
            size (float): Scale multiplier (shapes are normalized to 1.0)
        """
        self.clear_shapes()

        shape_data = None

        if isinstance(shape, str):
            # Resolve via Library
            lib = ShapeLibrary.get_instance()
            shape_data = lib.load(shape)
            if not shape_data:
                LOG.error("Shape %s not found.", shape)
                return
        elif isinstance(shape, dict):
            shape_data = shape
        else:
            raise TypeError("Shape must be a string name or curve data dict")

        # Iterate through all curves in the shape definition
        for curve_def in shape_data.get('curves', []):
            self.add_shape(curve_def, size=size)

    def set_color(self, color):
        """
        Set the display color of the controller shapes.

        Args:
            color (int | tuple | list):
                - int: Maya index color (0-31)
                - tuple/list: RGB values (0.0 - 1.0)
        """
        shapes = self.shapes()
        if not shapes:
            return

        is_rgb = isinstance(color, (list, tuple))

        for shape in shapes:
            # Ensure attributes exist (usually do on shapes)
            if not shape.has_attr("overrideEnabled"):
                continue

            shape["overrideEnabled"].value = True

            if is_rgb:
                shape["overrideRGBColors"].value = True
                shape["overrideColorRGB"].value = color
            else:
                shape["overrideRGBColors"].value = False
                shape["overrideColor"].value = int(color)

    # --------------------------------------------------
    # defaults & cleanup
    # --------------------------------------------------

    def _post_create_cleanup(self):
        # hide history in channel box
        if self.node["isHistoricallyInteresting"].exists():
            self.node["isHistoricallyInteresting"].value = 0

    # --------------------------------------------------
    # ergonomic passthrough
    # --------------------------------------------------

    @property
    def transform(self) -> Transform:
        return self.node

    def __getattr__(self, item):
        return getattr(self.node, item)