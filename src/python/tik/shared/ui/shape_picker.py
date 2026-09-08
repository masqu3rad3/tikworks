"""Choosing a control shape by looking at it.

Reads :mod:`tik.core.control_shapes` and never ``tik.maya`` -- importing
anything under ``tik.maya`` requires a live Maya, and this widget has to run
headless. Thumbnails are the ``.png`` sibling each shape ships beside its JSON.
"""

from __future__ import annotations

from typing import Optional

from tik.core.control_shapes import ControlShapeLibrary
from tik.shared.ui import theme
from tik.shared.ui.filter_bar import FilterBar
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.tile_grid import TileEntry, TileGrid

_LIBRARY: Optional[ControlShapeLibrary] = None
_ICONS: dict = {}


def default_library() -> ControlShapeLibrary:
    """One library for the whole tool, scanned once.

    A fold builds a button per control and each one used to construct its own,
    rescanning the shape folder every time. The scan is only milliseconds, but
    it is milliseconds per control per selection for an answer that cannot
    change while the tool is open.
    """
    global _LIBRARY  # noqa: PLW0603 - one shared library per process
    if _LIBRARY is None:
        _LIBRARY = ControlShapeLibrary()
    return _LIBRARY


def thumbnail_for(library, name: str) -> Optional[QtGui.QIcon]:
    """The shape's ``.png`` sibling as an icon, or ``None`` when absent.

    Cached by resolved *path*, not by name: decoding a PNG per tile per
    rebuild is the bulk of what made the Designer stutter, but two libraries
    can hold different files under one name -- polish searches the artist's
    own folder, the rig build does not -- so a name-keyed cache would serve
    one of them the other's thumbnail.
    """
    path = library.get_path(name)
    if not path:
        return None
    thumb = path.with_suffix(".png")
    key = str(thumb)
    if key in _ICONS:
        return _ICONS[key]
    icon = None
    if thumb.exists():
        pixmap = QtGui.QPixmap(key)
        if not pixmap.isNull():
            icon = QtGui.QIcon(pixmap)
    _ICONS[key] = icon
    return icon


class ShapePicker(QtWidgets.QWidget):
    """A filterable grid of every shape the library resolves, by category."""

    shapeChosen = QtCore.Signal(str)  # noqa: N815 - matches the Qt widgets here

    def __init__(self, library=None, parent=None) -> None:
        super().__init__(parent)
        self.library = library if library is not None else default_library()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.filter_bar = FilterBar(placeholder="Filter shapes…")
        self.filter_bar.filter_changed.connect(self._render)
        layout.addWidget(self.filter_bar)

        self._holder = QtWidgets.QVBoxLayout()
        self._holder.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._holder, 1)

        self._entries = [
            TileEntry(
                key=name,
                label=name,
                category=(info.get("category") or "uncategorised"),
                tooltip=name,
            )
            for name, info in sorted(self.library.get_shape_data().items())
        ]
        self.grid = None
        self._render()

    # ------------------------------------------------------------- reading
    def names(self) -> tuple:
        """Every shape name the library offers, sorted."""
        return tuple(entry.key for entry in self._entries)

    def visible_names(self) -> tuple:
        """The names the current filter leaves showing."""
        model = self.filter_bar.model
        return tuple(
            entry.key
            for entry in self._entries
            if not model.is_active or model.matches(entry.key)
        )

    def _tile_icon(self, entry, size: int) -> QtGui.QIcon:
        """A ``TileGrid`` icon provider: ``(entry, size) -> QIcon``.

        Falls back to the initials glyph a tile would draw anyway, so a shape
        whose thumbnail is missing still gets a tile rather than a blank one.
        """
        icon = thumbnail_for(self.library, entry.key)
        if icon is not None:
            return icon
        return glyph_icon(initials(entry.label), theme.CATEGORY["utility"], size=size)

    # ------------------------------------------------------------- writing
    def set_filter(self, text: str) -> None:
        """Narrow the grid to names matching ``text``.

        Drives the bar's own model rather than a private string, so typing and
        calling this land in the same place.
        """
        self.filter_bar.model.set_pending_text(text or "")

    def choose(self, name: str) -> None:
        """Announce ``name`` as the chosen shape."""
        self.shapeChosen.emit(name)

    def _render(self) -> None:
        """Rebuild the grid for the current filter.

        ``TileGrid`` takes its entries at construction and has no setter, so a
        filter change replaces the widget. 86 tiles rebuild imperceptibly, and
        reaching into its private ``_build`` to avoid that would be worse.
        """
        visible = set(self.visible_names())
        if self.grid is not None:
            self._holder.removeWidget(self.grid)
            self.grid.deleteLater()
        self.grid = TileGrid(
            [entry for entry in self._entries if entry.key in visible],
            "application/x-tik-shape",
            colors={},  # every category falls back to the neutral tint
            icon_provider=self._tile_icon,
        )
        self.grid.activated.connect(self.choose)
        self._holder.addWidget(self.grid)


class ShapeButton(QtWidgets.QToolButton):
    """A thumbnail that opens a :class:`ShapePicker` popup.

    An empty value is not a missing one: it means *inherit*, and the button
    draws the placeholder the caller supplies -- the module's own default --
    so an unedited row still shows what the control looks like.
    """

    shapeChosen = QtCore.Signal(str)  # noqa: N815 - matches the Qt widgets here

    SIZE = 48

    def __init__(self, library=None, parent=None) -> None:
        super().__init__(parent)
        self.library = library if library is not None else default_library()
        self._value = ""
        self._placeholder = ""
        self._picker: Optional[ShapePicker] = None
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setIconSize(QtCore.QSize(self.SIZE - 8, self.SIZE - 8))
        self.setAutoRaise(True)
        self.clicked.connect(self.open_picker)
        self._refresh()

    @property
    def picker(self) -> ShapePicker:
        """The popup, built the first time it is actually wanted.

        A picker is 86 tiles; a fold builds one button per control role and
        rebuilds them on every selection. Building the popup eagerly cost
        ~60ms a button -- most of a second for an arm, on every click.
        """
        if self._picker is None:
            picker = ShapePicker(self.library)
            picker.setWindowFlags(QtCore.Qt.Popup)
            picker.resize(420, 460)
            picker.shapeChosen.connect(self._on_chosen)
            self._picker = picker
        return self._picker

    # ------------------------------------------------------------- value
    def value(self) -> str:
        """The chosen shape, or ``""`` when the row inherits its default."""
        return self._value

    def setValue(self, name: str) -> None:  # noqa: N802 - matches the Qt widgets here
        """Set the chosen shape without emitting."""
        self._value = name or ""
        self._refresh()

    def setPlaceholder(  # noqa: N802 - matches the Qt widgets here
        self, name: str
    ) -> None:
        """The inherited default drawn when nothing is chosen."""
        self._placeholder = name or ""
        self._refresh()

    def open_picker(self) -> None:
        """Show the picker under the button."""
        self.picker.move(self.mapToGlobal(QtCore.QPoint(0, self.height())))
        self.picker.show()

    def _on_chosen(self, name: str) -> None:
        if self._picker is not None:
            self._picker.hide()
        self.setValue(name)
        self.shapeChosen.emit(name)

    def _refresh(self) -> None:
        shown = self._value or self._placeholder
        icon = thumbnail_for(self.library, shown) if shown else None
        self.setIcon(icon or QtGui.QIcon())
        self.setText("" if icon else (shown[:2] if shown else "-"))
        if self._value:
            self.setToolTip(self._value)
        elif self._placeholder:
            self.setToolTip(f"{self._placeholder} (module default)")
        else:
            self.setToolTip("No shape")
        # An inherited value reads as inherited.
        self.setStyleSheet(
            "" if self._value else f"QToolButton {{ color: {theme.TEXT_DIM}; }}"
        )
