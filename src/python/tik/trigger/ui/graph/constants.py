"""Geometry, colours and collapse modes shared by the graph items and views."""

from __future__ import annotations

from tik.shared.ui import theme
from tik.shared.ui.Qt import QtGui

NODE_WIDTH = 150
ROW = 18
HEADER = 22
PORT_RADIUS = 5
GLYPH_WIDTH = 16
#: Width of the left-edge draw-state stripe. The out-of-date stripe is the
#: whole width; the not-drawn one keeps its 3px dotted rhythm, which is the
#: point -- "not there" is the ordinary state of a new module and must stay
#: quiet, while "out of date" is the one that wants the eye.
STATE_STRIPE = 6
#: The out-of-date badge in the header: a dark chip carrying an amber "!".
BADGE = 13
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

#: The search overlay's width and its inset from the viewport corner.
FILTER_WIDTH = 220
FILTER_MARGIN = 8

#: How far a node fades when the filter rules it out. Not zero: a filtered
#: node keeps its place and its wires, so the graph never claims a connection
#: that is not there -- it just stops competing for attention.
FILTERED_OPACITY = 0.15

#: Ink for a port group's heading -- the copy's name, drawn once above its
#: ports instead of prefixed onto every one of them.
PORT_GROUP_INK = "#8a8a8a"

#: A node earns its own port filter at this many ports. Below it the list is
#: readable at a glance and a search box would be clutter; above it, hunting
#: for one port among forty is the whole problem.
PORT_FILTER_MIN = 8

#: Height of a node's port-filter row.
PORT_FILTER_ROW = 18
