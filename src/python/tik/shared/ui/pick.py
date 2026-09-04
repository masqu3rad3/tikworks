"""Pick shared UI resources: icons, pixmaps and the theme stylesheet.

Paths in, Qt objects out. This module knows nothing about actions or modules --
the tik.trigger side of that lives in ``tik/trigger/ui/iconography.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from tik.shared.ui.Qt import QtCore, QtGui

PathLike = Union[str, Path]

THEME_FOLDER = Path(__file__).parent / "theme"
RC_FOLDER = THEME_FOLDER / "rc"

_ICONS: dict[str, QtGui.QIcon] = {}
_TINTED: dict[tuple, QtGui.QIcon] = {}


def icon(path: PathLike) -> QtGui.QIcon:
    """A cached ``QIcon`` for ``path``."""
    key = str(path)
    if key not in _ICONS:
        _ICONS[key] = QtGui.QIcon(key)
    return _ICONS[key]


def pixmap(path: PathLike, size: Optional[int] = None) -> QtGui.QPixmap:
    """``path`` rendered at ``size`` square, or at its natural size."""
    if size is None:
        return QtGui.QPixmap(str(path))
    return icon(path).pixmap(QtCore.QSize(size, size))


def tinted_icon(path: PathLike, colour: str, size: int) -> QtGui.QIcon:
    """``path`` recoloured to ``colour``, keeping its alpha silhouette.

    Only ever call this on monochrome artwork: every opaque pixel becomes
    ``colour``. Tinting is done on the rendered pixmap rather than in the
    document because Qt's SVG renderer handles ``currentColor`` poorly.
    """
    key = (str(path), colour, size)
    if key in _TINTED:
        return _TINTED[key]
    base = pixmap(path, size)
    stamped = QtGui.QPixmap(base.size())
    stamped.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(stamped)
    painter.drawPixmap(0, 0, base)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
    painter.fillRect(stamped.rect(), QtGui.QColor(colour))
    painter.end()
    _TINTED[key] = QtGui.QIcon(stamped)
    return _TINTED[key]


def style_file(file_name: str = "theme.qss") -> QtCore.QFile:
    """The theme stylesheet, open for reading, with ``css:``/``rc:`` paths set."""
    QtCore.QDir.addSearchPath("css", str(THEME_FOLDER))
    QtCore.QDir.addSearchPath("rc", str(RC_FOLDER))
    handle = QtCore.QFile(f"css:{file_name}")
    handle.open(QtCore.QFile.ReadOnly | QtCore.QFile.Text)
    return handle


def clear_cache() -> None:
    """Drop both caches. Primarily for tests."""
    _ICONS.clear()
    _TINTED.clear()
