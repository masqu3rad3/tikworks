"""A titled section that folds away (ported from creature_kit)."""

from __future__ import annotations

from tik.shared.ui.Qt import QtCore, QtWidgets


class CollapsibleGroup(QtWidgets.QWidget):
    """A checkable header button over a collapsible content area."""

    toggled = QtCore.Signal(bool)

    def __init__(self, title: str, parent=None, expanded: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("CollapsibleGroup")
        self._button = QtWidgets.QToolButton()
        self._button.setText(title)
        self._button.setCheckable(True)
        self._button.setChecked(expanded)
        self._button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._button.setArrowType(
            QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow
        )
        self._button.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self._content = QtWidgets.QWidget()
        self._content_layout = QtWidgets.QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(9, 4, 9, 9)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._button)
        layout.addWidget(self._content)
        self._content.setVisible(expanded)
        self._button.toggled.connect(self._on_toggled)

    @property
    def content_layout(self) -> QtWidgets.QVBoxLayout:
        """The layout to add widgets to."""
        return self._content_layout

    @property
    def title(self) -> str:
        """The header text."""
        return self._button.text()

    def is_expanded(self) -> bool:
        """True while the content is shown."""
        return self._button.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        """Show or hide the content."""
        self._button.setChecked(bool(expanded))

    def _on_toggled(self, checked: bool) -> None:
        self._content.setVisible(checked)
        self._button.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )
        self.toggled.emit(checked)
