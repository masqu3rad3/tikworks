"""Core utilities for Tik Maya Polish tools."""

from tik.maya.utils import control_shapes
from .config import settings


class PolishCore:
    """Core utilities for Tik Maya Polish tools."""
    def __init__(self):
        self.library = control_shapes.ControlShapeLibrary()
        for additional_path in settings.get("additional_library_paths", []):
            self.library.add_path(additional_path)

    @staticmethod
    def capture_control_shape(shape_transform, name=None, category="custom"):
        """Capture a control shape to disk using the ControlShapeLibrary.

        Args:
            shape_transform (str): The transform node of the control shape.
            name (str, optional): The name to save the shape as. Defaults to None.
            category (str, optional): The category under which to save the shape. Defaults to "custom".
        """
        control_shapes.capture_to_disk(shape_transform, name=name, category=category)