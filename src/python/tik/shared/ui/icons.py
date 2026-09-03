"""Generated icons: coloured rounded squares with a short glyph (no image assets)."""

from __future__ import annotations

from tik.shared.ui.Qt import QtCore, QtGui

_CACHE: dict[tuple, QtGui.QIcon] = {}


def glyph_icon(
    text: str, color: str, size: int = 18, text_color: str = "#1a1a1a"
) -> QtGui.QIcon:
    """A rounded square in ``color`` with ``text`` (1-2 letters) centred."""
    key = (text, color, size, text_color)
    if key in _CACHE:
        return _CACHE[key]
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor(color))
    painter.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(int(size * 0.55))
    painter.setFont(font)
    painter.setPen(QtGui.QColor(text_color))
    painter.drawText(pixmap.rect(), QtCore.Qt.AlignCenter, text[:2])
    painter.end()
    icon = QtGui.QIcon(pixmap)
    _CACHE[key] = icon
    return icon


def initials(label: str) -> str:
    """One or two letters that stand for ``label`` (``fk chain`` -> ``FC``)."""
    words = [word for word in label.replace("_", " ").split() if word]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].capitalize()
    return (words[0][0] + words[1][0]).upper()
