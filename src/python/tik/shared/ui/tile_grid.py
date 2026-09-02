"""A shelf of icon tiles grouped by category that reflows to the available width."""

from __future__ import annotations

from typing import Optional, Sequence

from tik.shared.ui import theme
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets


class TileEntry:
    __slots__ = ("key", "label", "category", "tooltip")

    def __init__(self, key: str, label: str, category: str = "", tooltip: str = "") -> None:
        self.key = key
        self.label = label
        self.category = category
        self.tooltip = tooltip


class Tile(QtWidgets.QToolButton):
    WIDTH = 66
    HEIGHT = 58

    def __init__(self, entry: TileEntry, color: str, mime_type: str, parent=None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.mime_type = mime_type
        self.setObjectName("ShelfTile")
        self.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        self.setIcon(glyph_icon(initials(entry.label), color, size=22))
        self.setIconSize(QtCore.QSize(22, 22))
        self.setText(entry.label)
        self.setToolTip(entry.tooltip or f"{entry.label} — click: add · drag: place")
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._press: Optional[QtCore.QPoint] = None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton:
            self._press = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._press is not None and (event.pos() - self._press).manhattanLength() > QtWidgets.QApplication.startDragDistance():
            drag = QtGui.QDrag(self)
            mime = QtCore.QMimeData()
            mime.setData(self.mime_type, self.entry.key.encode("utf-8"))
            drag.setMimeData(mime)
            drag.setPixmap(self.icon().pixmap(22, 22))
            self._press = None
            drag.exec_(QtCore.Qt.CopyAction)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._press = None
        super().mouseReleaseEvent(event)


class TileGrid(QtWidgets.QScrollArea):
    """Scrollable, reflowing tile shelf. ``activated(key)`` on click."""

    activated = QtCore.Signal(str)

    def __init__(self, entries: Sequence[TileEntry], mime_type: str, parent=None, colors: Optional[dict] = None, columns_hint: int = 2) -> None:
        super().__init__(parent)
        self.setObjectName("TileGrid")
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.entries = list(entries)
        self.mime_type = mime_type
        self.colors = colors or theme.CATEGORY
        self.tiles: dict[str, Tile] = {}
        self._sections: list[tuple[QtWidgets.QLabel, list[Tile], QtWidgets.QGridLayout]] = []
        self._columns = 0
        body = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(body)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(4)
        self._build()
        self._layout.addStretch(1)
        self.setWidget(body)
        self.setMinimumWidth(Tile.WIDTH + 24)
        self._reflow(columns_hint)

    def _build(self) -> None:
        current = None
        tiles: list[Tile] = []
        for entry in sorted(self.entries, key=lambda item: (item.category, item.label)):
            if entry.category != current:
                current = entry.category
                header = QtWidgets.QLabel(current.upper())
                header.setObjectName("ShelfHeader")
                self._layout.addWidget(header)
                holder = QtWidgets.QWidget()
                grid = QtWidgets.QGridLayout(holder)
                grid.setContentsMargins(0, 0, 0, 4)
                grid.setSpacing(6)
                self._layout.addWidget(holder)
                tiles = []
                self._sections.append((header, tiles, grid))
            tile = Tile(entry, self.colors.get(entry.category, theme.CATEGORY["utility"]), self.mime_type)
            tile.clicked.connect(lambda _c=False, key=entry.key: self.activated.emit(key))
            tiles.append(tile)
            self.tiles[entry.key] = tile

    @property
    def columns(self) -> int:
        return self._columns

    def _reflow(self, columns: int) -> None:
        columns = max(1, columns)
        if columns == self._columns:
            return
        self._columns = columns
        for _header, tiles, grid in self._sections:
            for tile in tiles:
                grid.removeWidget(tile)
            for index, tile in enumerate(tiles):
                grid.addWidget(tile, index // columns, index % columns, QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
            for column in range(columns, grid.columnCount()):
                grid.setColumnStretch(column, 0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        available = self.viewport().width() - 12
        self._reflow(max(1, (available + 6) // (Tile.WIDTH + 6)))
