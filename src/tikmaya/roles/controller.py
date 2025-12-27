"""
Controller facade.

A Controller is a semantic wrapper around a Transform node that:
- is tagged as a controller in Maya
- manages NURBS curve shapes under the transform
- exposes a controller-centric API
"""


from maya import cmds
import logging

from tikmaya.core.decorators import keepselection
from tikmaya.core.registry import resolve
from tikmaya.types.transform import Transform
# from tikmaya.types.curve import Curve
from tikmaya.utils.control_shapes import ControlShapeLibrary  # Import the manager

LOG = logging.getLogger(__name__)

def replace_curve(orig_curve, new_curve, snap=True, transfer_color=True):
    """Replace orig_curve with new_curve.

    Args:
        orig_curve (str): nurbsCurve to replace.
        new_curve (str): nurbsCurve to replace with.
        maintain_offset (bool, optional): Match position. Defaults to True.
    """
    if snap:
        new_curve = cmds.duplicate(new_curve, rc=1)[0]
        cmds.parentConstraint(orig_curve, new_curve)

    orig_shapes = cmds.listRelatives(orig_curve, shapes=True,
                                         type="nurbsCurve")

    new_shapes = cmds.listRelatives(new_curve, shapes=True,
                                    type="nurbsCurve")


    color = None
    if transfer_color:
        if cmds.getAttr(f"{new_curve}.overrideEnabled"):
            color = cmds.getAttr(f"{new_curve}.overrideColor")

    # Make amount of shapes equal
    shape_dif = len(orig_shapes) - len(new_shapes)
    if shape_dif != 0:
        # If original curve has fewer shapes, create new nulls until equal
        if shape_dif < 0:
            for shape in range(0, shape_dif * -1):
                dupe_curve = cmds.duplicate(orig_shapes, renameChildren=True)[0]
                dupe_shape = cmds.listRelatives(dupe_curve, shapes=True)[0]
                orig_shapes.append(dupe_shape)
                cmds.select(dupe_shape, orig_curve)
                cmds.parent(relative=True, shape=True)
                cmds.delete(dupe_curve)
        # If original curve has more shapes, delete shapes until equal
        if shape_dif > 0:
            for shape in range(0, shape_dif):
                cmds.delete(orig_shapes[shape])

    orig_shapes = cmds.listRelatives(orig_curve, shapes=True)
    # For each shape, transfer from original to new.
    for new_shape, orig_shape in zip(new_shapes, orig_shapes):
        if color:
            cmds.setAttr(f"{orig_shape}.overrideEnabled", 1)
            cmds.setAttr(f"{orig_shape}.overrideColor", color)
        cmds.connectAttr(
            f"{new_shape}.worldSpace",
            f"{orig_shape}.create"
        )

        cmds.dgeval(f"{orig_shape}.worldSpace")
        cmds.disconnectAttr(
            f"{new_shape}.worldSpace",
            f"{orig_shape}.create"
        )

        spans = cmds.getAttr(f"{orig_shape}.degree")
        degree = cmds.getAttr(f"{orig_shape}.spans")
        for idx in range(0, spans + degree):
            cmds.xform(
                f"{orig_shape}.cv[{idx}]",
                # orig_shape + ".cv[" + str(idx) + "]",
                # t=cmds.pointPosition(new_shape + ".cv[" + str(idx) + "]"),
                translation=cmds.pointPosition(f"{new_shape}.cv[{idx}]"),
                worldSpace=True,
            )

    if snap:
        cmds.delete(new_curve)


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
        return node.has_attr(cls.ROLE_ATTR) and node[cls.ROLE_ATTR].value

    # --------------------------------------------------
    # properties
    # --------------------------------------------------

    @property
    def color(self):
        return self.get_color()

    @color.setter
    def color(self, value):
        self.set_color(value)

    @property
    def transform(self) -> Transform:
        """Pass-through to the underlying transform node."""
        return self.node

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

    @property
    def shapes(self) -> list:
        return self.node.shapes

    def clear_shapes(self):
        """Delete all shapes under the controller transform."""
        for shape in self.shapes:
            shape.delete()

    def add_shape(self, curve_data: dict, size=1.0):
        """
        Add a curve shape under the controller transform.
        Applies size scaling to the incoming points.
        """
        points = curve_data['point']
        if size != 1.0:
            points = [(point[0] * size, point[1] * size, point[2] * size) for point in points]

        kwargs = {
            "point": points,
            "degree": curve_data.get('degree', 3),
            "periodic": curve_data.get('periodic', False)
        }
        if curve_data.get('knot'):
            kwargs["knot"] = curve_data.get('knot')

        curve_trans = cmds.curve(**kwargs)
        curve_shape = cmds.listRelatives(curve_trans, shapes=True, fullPath=True)[0]
        curve_shape = cmds.rename(curve_shape, f"{self.node.name}Shape#")  # Ensure unique name

        self.node.invalidate_cache()

        cmds.parent(curve_shape, self.node.name, relative=True, shape=True)
        cmds.delete(curve_trans)

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
            lib = ControlShapeLibrary.get_instance()
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

    @keepselection
    def replace_shape(self, shape, size=1.0, snap=True, transfer_color=True):
        """
        Replace existing controller shapes with new shape.

        Args:
            shape (str | dict): Name of shape in library OR raw dict data
            size (float): Scale multiplier (shapes are normalized to 1.0)
            snap (bool): Whether to snap new shape to old shape position
            transfer_color (bool): Whether to transfer color from old shape
        """


        # Create new temporary shapes and replace
        temp_ctrl = Controller.create(
            name=f"{self.node.name}_tempShape",
            shape=shape,
            size=size,
            color=None
        )
        replace_curve(
            orig_curve=self.node.name,
            new_curve=temp_ctrl.node.name,
            snap=snap,
            transfer_color=transfer_color
        )
        temp_ctrl.node.delete()

    def get_color(self):
        """Get the display color of the controller shapes."""
        return self.node.get_color()

    def set_color(self, color):
        """
        Set the display color of the controller shapes.

        Args:
            color (int | tuple | list):
                - int: Maya index color (0-31)
                - tuple/list: RGB values (0.0 - 1.0)
        """
        self.node.set_color(color)

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

    def __getattr__(self, item):
        return getattr(self.node, item)