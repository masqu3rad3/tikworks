"""Naming mechanics.

Only mechanics live here (uniqueness, token joining). Naming *conventions*
(what a side token looks like, which suffix a joint gets) belong to the
callers, e.g. a rigging framework.
"""

from __future__ import annotations

import re
from typing import Optional

from maya import cmds

_TRAILING_DIGITS = re.compile(r"^(.*?)(\d+)$")


def unique_name(base: str, separator: str = "") -> str:
    """Return ``base`` if no node uses it, else the next free numbered name.

    Existing numeric padding is respected (``arm01`` -> ``arm02``).
    """
    if not cmds.objExists(base):
        return base

    match = _TRAILING_DIGITS.match(base)
    if match and not separator:
        stem, digits = match.group(1), match.group(2)
        counter, width = int(digits), len(digits)
    else:
        stem, counter, width = base + separator, 0, 1

    while True:
        counter += 1
        candidate = f"{stem}{counter:0{width}d}"
        if not cmds.objExists(candidate):
            return candidate


def format_name(
    *tokens,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
    side: Optional[str] = None,
    sep: str = "_",
) -> str:
    """Join non-empty tokens as ``side, prefix, *tokens, suffix``.

    Integers are accepted as tokens; ``None`` and empty strings are skipped.
    """
    parts = [side, prefix, *tokens, suffix]
    return sep.join(str(part) for part in parts if part is not None and part != "")
