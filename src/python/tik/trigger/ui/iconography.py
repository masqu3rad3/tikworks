"""Icons for actions and guide modules, and what to draw when there are none.

Two families, deliberately different. An action is a verb: it carries its own
colour and is never tinted, which is safe because ``delegates.py`` paints run
state as a separate status dot. A guide module is a noun: monochrome artwork
recoloured per side, so one ``arm.svg`` serves ``L_arm`` and ``R_arm``.
"""

from __future__ import annotations

from typing import Optional

from tik.shared.ui import pick, theme
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.Qt import QtCore, QtGui
from tik.shared.ui.theme import MODULE_COLORS
from tik.trigger.core import icons

DEFAULT_SIZE = 22


def action_icon(action_cls: type, size: int = DEFAULT_SIZE) -> QtGui.QIcon:
    """An action's artwork, or the generated initials chip when it has none."""
    found = icons.find(action_cls)
    if found is not None:
        return pick.icon(found.path)
    category = getattr(action_cls, "category", "utility")
    colour = theme.CATEGORY.get(category, theme.CATEGORY["utility"])
    return glyph_icon(initials(action_cls.display_label()), colour, size=size)


def module_colour(module_cls: type, side: Optional[str] = None) -> str:
    """The tint for a module: its side if it has one, else its category."""
    if side:
        # ``Side`` is a str-mixin enum, so a plain dict lookup accepts both
        # ``Side.LEFT`` and ``"L"``. Do not wrap this in ``str()``: what that
        # returns for a mixin enum varies by Python version.
        return theme.SIDE.get(side, theme.SIDE["C"])
    category = getattr(module_cls, "category", "generic")
    return MODULE_COLORS.get(category, MODULE_COLORS["generic"])


def module_icon(
    module_cls: type, side: Optional[str] = None, size: int = DEFAULT_SIZE
) -> QtGui.QIcon:
    """A module's artwork, tinted, or a sketch of its guide topology."""
    colour = module_colour(module_cls, side)
    found = icons.find(module_cls)
    if found is None:
        return topology_icon(module_cls, colour, size)
    if found.is_raster:
        return pick.icon(found.path)  # finished art: never recoloured
    return pick.tinted_icon(found.path, colour, size)


def guide_count(module_cls: type) -> int:
    """How many guides the module declares, counting one for a multi role."""
    layout = getattr(module_cls, "guides", None)
    roles = len(getattr(layout, "roles", ()) or ())
    if getattr(layout, "multi", None):
        roles += max(getattr(layout, "min_count", 1), 1)
    return max(roles, 1)


def topology_icon(module_cls: type, colour: str, size: int) -> QtGui.QIcon:
    """A joint chain drawn from the module's declared ``GuideLayout``.

    A module with no artwork still knows its own shape, so the fallback says
    something true -- four stacked joints for a spine -- rather than two
    letters. Different modules with the same joint count look alike, which is
    why this never substitutes for authored art.
    """
    count = min(guide_count(module_cls), 5)
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    pen = QtGui.QPen(QtGui.QColor(colour), max(size * 0.06, 1.0))
    painter.setPen(pen)
    painter.setBrush(QtGui.QColor(colour))
    margin = size * 0.18
    span = size - margin * 2
    radius = max(size * 0.09, 1.2)
    points = []
    for index in range(count):
        fraction = index / (count - 1) if count > 1 else 0.5
        points.append(
            QtCore.QPointF(margin + span * fraction, size - margin - span * fraction)
        )
    for start, end in zip(points, points[1:]):
        painter.drawLine(start, end)
    for point in points:
        painter.drawEllipse(point, radius, radius)
    painter.end()
    return QtGui.QIcon(pixmap)
