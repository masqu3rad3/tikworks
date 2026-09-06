"""Geometry, colours and collapse modes shared by the graph items and views."""

from __future__ import annotations

from tik.shared.ui import theme
from tik.shared.ui.Qt import QtGui

NODE_WIDTH = 150
ROW = 18
HEADER = 22
PORT_RADIUS = 5
GLYPH_WIDTH = 16
WIRE_PRIMARY = QtGui.QColor(theme.ACCENT)
WIRE_SECONDARY = QtGui.QColor("#8fa4c0")
PORT_SPACE = "#c9a227"  # space ports read apart from input ports at a glance
# scene rect half-size: effectively infinite canvas, so panning is never clamped
WORLD = 100000.0
GRID = 20
MODE_MINIMAL, MODE_CONNECTED, MODE_FULL = 0, 1, 2
COLUMN_GAP = 60
ROW_GAP = 24
# A reference frame: the gap it leaves around its members, and its title bar.
FRAME_PADDING = 16
FRAME_TITLE = 20
# Same family as the tree's provenance chip, so "borrowed" reads identically
# in both panes rather than being learned twice.
FRAME_INK = "#6f8fa8"
