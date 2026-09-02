"""Controller shape library UI widget for TikWorks Maya tools."""

import sys

# Lazy loading of Maya-dependent code.
# This allows tik.trigger to be imported in headless/test environments
# without requiring Maya.

_maya_available = True


def __getattr__(name):
    global _maya_available
    if name in ("cs_handler", "MOCK_DATA", "ShapeLibraryModel", "FlatLeafProxyModel",
                "HoverOverlay", "ShapeLibraryWidget"):
        if _maya_available:
            try:
                from tik.maya.utils import control_shapes
                from tik.vendor.Qt import QtCore, QtGui, QtWidgets

                global cs_handler, MOCK_DATA
                cs_handler = control_shapes.ControlShapeLibrary()
                MOCK_DATA = cs_handler.get_shape_data()
                _maya_available = True
            except ImportError:
                _maya_available = False
                raise AttributeError(
                    f"tik.{name} requires Maya and is not available in this environment"
                )
        else:
            raise AttributeError(
                f"tik.{name} requires Maya and is not available in this environment"
            )

    if name == "cs_handler":
        raise AttributeError(
            "tik.cs_handler requires Maya and is not available in this environment"
        )
    if name == "MOCK_DATA":
        raise AttributeError(
            "tik.MOCK_DATA requires Maya and is not available in this environment"
        )
    if name in ("ShapeLibraryModel", "FlatLeafProxyModel", "HoverOverlay", "ShapeLibraryWidget"):
        raise AttributeError(
            f"tik.{name} requires Maya Qt widgets and is not available in this environment"
        )
    raise AttributeError(f"module 'tik' has no attribute '{name}'")
