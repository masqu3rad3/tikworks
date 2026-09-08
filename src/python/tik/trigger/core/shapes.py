"""The shape library a rig build resolves through.

Pinned on purpose. ``tik.core``'s library searches
``~/TikWorks/user_control_shapes`` after the shipped set, so a personal
``Circle.json`` silently replaces the shipped one -- and two artists building
the same ``.tr`` get different rigs. A per-user folder is a preference by any
reasonable reading, and *a preference can never change a rig*, so the build
does not search it.

``TRIGGER_SHAPES_PATH`` is the escape hatch, and it is the right one: a studio
path is deployed and version-controlled, so it resolves the same for everyone.
A personal shape has to be promoted to such a path before a rig can use it.

The picker reads this same library, so it is not possible to choose a shape the
build cannot resolve.
"""

from __future__ import annotations

import os
from typing import Optional

from tik.core.control_shapes import ControlShapeLibrary

SHAPES_ENV = "TRIGGER_SHAPES_PATH"
"""Deployed, version-controlled roots added to the pinned search order."""

DEFAULT_SHAPE = "Circle"
"""The shape a control falls back to when nothing declares one."""

_LIBRARY: Optional[ControlShapeLibrary] = None


def library() -> ControlShapeLibrary:
    """The pinned library: the shipped set plus ``TRIGGER_SHAPES_PATH``."""
    global _LIBRARY  # noqa: PLW0603 - one cached library per process
    if _LIBRARY is None:
        found = ControlShapeLibrary(include_user_path=False)
        for entry in os.environ.get(SHAPES_ENV, "").split(os.pathsep):
            if entry:
                found.add_path(entry)
        _LIBRARY = found
    return _LIBRARY


def reset() -> None:
    """Drop the cached library, so a changed environment is picked up."""
    global _LIBRARY  # noqa: PLW0603 - one cached library per process
    _LIBRARY = None


def shape_names() -> tuple[str, ...]:
    """Every resolvable shape name, sorted."""
    return tuple(sorted(library().list_shapes()))


def has_shape(name: str) -> bool:
    """Whether ``name`` resolves in the pinned library."""
    return bool(name) and name in set(library().list_shapes())
