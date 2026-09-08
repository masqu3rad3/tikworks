"""The polish tool's controller-shape browser.

The library, the thumbnails and the filtering all live in
:class:`tik.shared.ui.shape_picker.ShapePicker`; this is the polish-side shell
around it. Polish keeps the *unpinned* library on purpose -- a cleanup tool
should see the artist's personal shapes. Only a rig build must not.
"""

from __future__ import annotations

from tik.shared.ui.Qt import QtWidgets
from tik.shared.ui.shape_picker import ShapePicker
from tik.tools.polish.core import PolishCore


class ControllerShapesWidget(QtWidgets.QWidget):
    """Browse the shape library and apply a shape to the selection."""

    def __init__(self, core=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Controller Shape Library")
        self.core = core or PolishCore()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.picker = ShapePicker(self.core.library)
        layout.addWidget(self.picker)
