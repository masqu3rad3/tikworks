"""
Controller facade.

A Controller is a semantic wrapper around a Transform node that:
- is tagged as a controller in Maya
- manages NURBS curve shapes under the transform
- exposes a controller-centric API
"""

from __future__ import annotations

import logging

from maya import cmds

from ..core.decorators import keepselection
from ..core.registry import resolve
from ..types.transform import Transform
from ..utils.control_shapes import ControlShapeLibrary  # Import the manager

LOG = logging.getLogger(__name__)


def replace_curve(orig_curve, new_curve, snap=True, transfer_color=True):
    """Replace curve shapes on a controller.

    Args:
        orig_curve: Name of the original nurbsCurve transform to replace.
        new_curve: Name of the new nurbsCurve transform to replace with.
            snap: Match the new curve's position to the original (default True).
            transfer_color: Transfer the color override from the new curve to
                the original (default True).
    """
    if snap:
        new_curve = cmds.duplicate(new_curve, rc=1)[0]
        cmds.parentConstraint(orig_curve, new_curve)

    orig_shapes = cmds.listRelatives(orig_curve, shapes=True, type="nurbsCurve")

    new_shapes = cmds.listRelatives(new_curve, shapes=True, type="nurbsCurve")

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
        cmds.connectAttr(f"{new_shape}.worldSpace", f"{orig_shape}.create")

        cmds.dgeval(f"{orig_shape}.worldSpace")
        cmds.disconnectAttr(f"{new_shape}.worldSpace", f"{orig_shape}.create")

        spans = cmds.getAttr(f"{orig_shape}.degree")
        degree = cmds.getAttr(f"{orig_shape}.spans")
        for idx in range(0, spans + degree):
            cmds.xform(
                f"{orig_shape}.cv[{idx}]",
                translation=cmds.pointPosition(f"{new_shape}.cv[{idx}]"),
                worldSpace=True,
            )

    if snap:
        cmds.delete(new_curve)


class Controller:
    """Semantic wrapper for controller transforms in Maya.

    A Controller is a Transform node that:
    - Is tagged as a controller
    - Manages NURBS curve shapes for visual representation
    - Provides a controller-centric API for shape and color management
    """

    ROLE_ATTR = "isController"

    def __init__(self, node):
        """Initialize a Controller wrapper.

        Args:
            node: Node name, path, or Transform wrapper to wrap as a controller.

        Raises:
            TypeError: If the node is not a Transform.
        """
        self.node = resolve(node)
        # Validation
        if not isinstance(self.node, Transform):
            raise TypeError(f"Controller must wrap a Transform, got {type(self.node)}")

    @classmethod
    def create(cls, name, shape="Circle", size=1.0, color=None, **kwargs):
        """Create a new controller transform with specified shape and properties.

        Args:
            name: Name for the new controller.
            shape: Shape name from library or curve data dict (default: "Circle").
            size: Scale multiplier for the shape (default: 1.0).
            color: Color to apply (int, tuple, or Color object).
            **kwargs: Additional arguments passed to Transform.create().

        Returns:
            Controller: The newly created controller instance.
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
        """Create a Controller wrapper from an existing controller node.

        Args:
            node: Node name or wrapper that is tagged as a controller.

        Returns:
            Controller: Controller instance wrapping the node.

        Raises:
            RuntimeError: If the node is not tagged as a controller.
        """
        node = resolve(node)
        if not cls.is_controller(node):
            raise RuntimeError(f"Node '{node.name}' is not a Controller")
        return cls(node)

    @classmethod
    def is_controller(cls, node) -> bool:
        """Check if a node is tagged as a controller.

        Args:
            node: Node name or wrapper to check.

        Returns:
            bool: True if the node is tagged as a controller, False otherwise.
        """
        node = resolve(node)
        return node.has_attr(cls.ROLE_ATTR) and node[cls.ROLE_ATTR].value

    # --------------------------------------------------
    # properties
    # --------------------------------------------------

    @property
    def color(self):
        """Get or set the display color of the controller shapes.

        Can be set to:
            - int: Maya index color (0-31)
            - tuple/list: RGB values (0.0-1.0)
            - Color: tik.core.Color object
        """
        return self.get_color()

    @color.setter
    def color(self, value):
        self.set_color(value)

    @property
    def transform(self) -> Transform:
        """Pass-through to the underlying transform node.

        Returns:
            Transform: The wrapped transform node.
        """
        return self.node

    # --------------------------------------------------
    # tagging
    # --------------------------------------------------

    def _tag_as_controller(self):
        """Tag the transform as a controller by adding or setting the role attribute."""
        if not self.node[self.ROLE_ATTR].exists():
            self.node.add_attr(self.ROLE_ATTR, attributeType="bool", defaultValue=True)
        self.node[self.ROLE_ATTR].value = True

    # --------------------------------------------------
    # shape management
    # --------------------------------------------------

    @property
    def shapes(self) -> list:
        """Return all shape nodes under the controller transform.

        Returns:
            list: List of shape node wrappers.
        """
        return self.node.shapes

    def clear_shapes(self):
        """Delete all shapes under the controller transform."""
        for shape in self.shapes:
            shape.delete()

    def add_shape(self, curve_data: dict, size=1.0):
        """Add a curve shape under the controller transform.

        Args:
            curve_data: Dictionary containing curve definition with keys:
                - 'point': List of (x, y, z) tuples for CV positions
                - 'degree': Curve degree (default: 3)
                - 'periodic': Whether curve is periodic (default: False)
                - 'knot': Optional knot vector
            size: Scale multiplier applied to all points (default: 1.0).
        """
        points = curve_data["point"]
        if size != 1.0:
            points = [
                (point[0] * size, point[1] * size, point[2] * size) for point in points
            ]

        kwargs = {
            "point": points,
            "degree": curve_data.get("degree", 3),
            "periodic": curve_data.get("periodic", False),
        }
        if curve_data.get("knot"):
            kwargs["knot"] = curve_data.get("knot")

        curve_trans = cmds.curve(**kwargs)
        curve_shape = cmds.listRelatives(curve_trans, shapes=True, fullPath=True)[0]
        curve_shape = cmds.rename(
            curve_shape, f"{self.node.name}Shape#"
        )  # Ensure unique name

        cmds.parent(curve_shape, self.node.partial_name, relative=True, shape=True)
        cmds.delete(curve_trans)

    def set_shape(self, shape, size=1.0):
        """Replace controller shapes with a new shape.

        Args:
            shape: Shape name from library (str) or raw curve data (dict).
            size: Scale multiplier, shapes are normalized to 1.0 (default: 1.0).

        Note:
            This clears all existing shapes before adding the new one.
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
        for curve_def in shape_data.get("curves", []):
            self.add_shape(curve_def, size=size)

    @keepselection
    def replace_shape(self, shape, size=1.0, snap=True, transfer_color=True):
        """Replace existing controller shapes while preserving transformations.

        Args:
            shape: Shape name from library (str) or raw curve data (dict).
            size: Scale multiplier (default: 1.0).
            snap: Whether to match the position of the new shape (default: True).
                transfer_color: Transfer the color from the old shape (default True).
        """

        # Create new temporary shapes and replace
        temp_ctrl = Controller.create(
            name=f"{self.node.name}_tempShape", shape=shape, size=size, color=None
        )
        replace_curve(
            orig_curve=self.node.partial_name,
            new_curve=temp_ctrl.node.name,
            snap=snap,
            transfer_color=transfer_color,
        )
        temp_ctrl.node.delete()

    def get_color(self, as_color=False):
        """Get the display color of the controller shapes.

        Args:
            as_color: If True, return as Color object when using RGB;
                     otherwise return raw value (default: False).

        Returns:
            int, tuple, Color, or None: The color value or None if no override is set.
        """
        return self.node.get_color(as_color=as_color)

    def set_color(self, color):
        """Set the display color of the controller shapes.

        Args:
            color: Color specification:
                - int: Maya index color (0-31)
                - tuple/list: RGB values (0.0-1.0)
                - Color: tik.core.Color object
                - None: Disable color override
        """
        self.node.set_color(color)

    # --------------------------------------------------
    # defaults & cleanup
    # --------------------------------------------------

    def _post_create_cleanup(self):
        """Clean up after controller creation by hiding history attributes."""
        # hide history in channel box
        if self.node["isHistoricallyInteresting"].exists():
            self.node["isHistoricallyInteresting"].value = 0

    # --------------------------------------------------
    # ergonomic passthrough
    # --------------------------------------------------

    def __getattr__(self, item):
        """Pass through attribute access to the underlying transform node.

        Args:
            item: Attribute name to access.

        Returns:
            The attribute value from the transform node.
        """
        return getattr(self.node, item)

    def __getitem__(self, item):
        """Pass plug access through to the underlying transform node.

        ``__getattr__`` does not cover this: Python looks dunder methods up on
        the type, so without it a controller cannot be indexed, connected, or
        handed to a construct that reads a plug off its driver.

        Args:
            item: Attribute (plug) name.

        Returns:
            Plug: The plug on the transform node.
        """
        return self.node[item]
