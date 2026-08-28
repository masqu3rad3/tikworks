"""Collapsible shelf of tiles (actions or modules): click to add, drag to place."""

from __future__ import annotations

from typing import Optional, Sequence

from tik.shared.ui import theme
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets

from .palette import PaletteEntry


class ShelfTile(QtWidgets.QToolButton):
    def __init__(self, entry: PaletteEntry, color: str, mime_type: str, parent=None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.mime_type = mime_type
        self.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        self.setIcon(glyph_icon(initials(entry.label), color, size=22))
        self.setIconSize(QtCore.QSize(22, 22))
        self.setText(entry.label)
        self.setToolTip(f"{entry.key} · click: add after selection · drag: place anywhere")
        self.setFixedWidth(68)
        self.setAutoRaise(True)
        self._press_pos: Optional[QtCore.QPoint] = None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton:
            self._press_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._press_pos is not None and (event.pos() - self._press_pos).manhattanLength() > QtWidgets.QApplication.startDragDistance():
            drag = QtGui.QDrag(self)
            mime = QtCore.QMimeData()
            mime.setData(self.mime_type, self.entry.key.encode("utf-8"))
            drag.setMimeData(mime)
            drag.setPixmap(self.icon().pixmap(22, 22))
            self._press_pos = None
            drag.exec_(QtCore.Qt.CopyAction)
            return
        super().mouseMoveEvent(event)


class Shelf(QtWidgets.QWidget):
    """Category-grouped tiles; ``collapsed`` hides everything but a thin handle."""

    add_requested = QtCore.Signal(str)  # key
    toggled = QtCore.Signal(bool)  # collapsed

    def __init__(self, entries: Sequence[PaletteEntry], mime_type: str, parent=None, colors: Optional[dict] = None, title: str = "Actions") -> None:
        super().__init__(parent)
        self.entries = list(entries)
        self.mime_type = mime_type
        self.colors = colors or theme.CATEGORY
        self._collapsed = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.handle = QtWidgets.QToolButton()
        self.handle.setText(f"◂ {title}")
        self.handle.setAutoRaise(True)
        self.handle.setToolTip("Collapse / expand the shelf")
        self.handle.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        layout.addWidget(self.handle)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        body = QtWidgets.QWidget()
        self.body_layout = QtWidgets.QVBoxLayout(body)
        self.body_layout.setContentsMargins(4, 4, 4, 4)
        self.body_layout.setSpacing(2)
        self.tiles: dict[str, ShelfTile] = {}
        self._build_tiles()
        self.body_layout.addStretch(1)
        self.scroll.setWidget(body)
        layout.addWidget(self.scroll, 1)
        self.title = title
        self.setFixedWidth(160)

    def _build_tiles(self) -> None:
        current = None
        grid_layout = None
        for entry in sorted(self.entries, key=lambda item: (item.category, item.label)):
            if entry.category != current:
                current = entry.category
                label = QtWidgets.QLabel(current.upper())
                label.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 9px; letter-spacing: 1px; margin-top: 6px;")
                self.body_layout.addWidget(label)
                holder = QtWidgets.QWidget()
                grid_layout = QtWidgets.QGridLayout(holder)
                grid_layout.setContentsMargins(0, 0, 0, 0)
                grid_layout.setSpacing(2)
                self.body_layout.addWidget(holder)
            tile = ShelfTile(entry, self.colors.get(entry.category, theme.CATEGORY["utility"]), self.mime_type)
            tile.clicked.connect(lambda _checked=False, key=entry.key: self.add_requested.emit(key))
            count = grid_layout.count()
            grid_layout.addWidget(tile, count // 2, count % 2)
            self.tiles[entry.key] = tile

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.scroll.setVisible(not collapsed)
        self.handle.setText(("▸ " if collapsed else "◂ ") + self.title)
        self.setFixedWidth(24 if collapsed else 160)
        self.toggled.emit(collapsed)
