"""Locate the icon file belonging to a registered action or module.

Pure path work: no Qt and no Maya, because ``tik/trigger/core`` may import
neither. Resolution lives here rather than in the UI layer so the rule that a
plugin is ``<folder>/<folder>.py`` is stated once, beside the ``discovery``
module that established it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ACTION = "action"
MODULE = "module"

#: Tried in order; first hit wins. A PNG is an artist's finished artwork and
#: deliberately supersedes the authored SVG placeholder beside it.
SUFFIXES = (".png", ".svg")


@dataclass(frozen=True)
class IconFile:
    """An icon on disk and the family of plugin it belongs to."""

    path: Path
    family: str

    @property
    def is_raster(self) -> bool:
        """True for a PNG: finished art that must never be recoloured."""
        return self.path.suffix.lower() == ".png"


def plugin_folder(cls: type) -> Optional[Path]:
    """The folder holding the module that defines ``cls``."""
    module = sys.modules.get(getattr(cls, "__module__", ""))
    file_name = getattr(module, "__file__", None)
    if not file_name:
        return None
    return Path(file_name).resolve().parent


def family_of(cls: type) -> Optional[str]:
    """``ACTION``, ``MODULE``, or None when ``cls`` is neither."""
    if getattr(cls, "action_type", ""):
        return ACTION
    if getattr(cls, "module_type", ""):
        return MODULE
    return None


def icon_names(cls: type) -> tuple[str, ...]:
    """Names to try, most specific first: declared ``icon``, then the type."""
    registered = getattr(cls, "action_type", "") or getattr(cls, "module_type", "")
    declared = getattr(cls, "icon", "") or ""
    return tuple(dict.fromkeys(name for name in (declared, registered) if name))


def find(cls: type) -> Optional[IconFile]:
    """Return ``cls``'s icon file, or None when it has no artwork."""
    family = family_of(cls)
    folder = plugin_folder(cls)
    if family is None or folder is None:
        return None
    for name in icon_names(cls):
        for suffix in SUFFIXES:
            candidate = folder / f"{name}{suffix}"
            if candidate.is_file():
                return IconFile(candidate, family)
    return None
