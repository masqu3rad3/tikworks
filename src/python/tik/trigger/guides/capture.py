"""Capture: the scene's poses and guide attrs, into the document.

Three rules, all load-bearing (spec 4.2):

1. **Additive.** Only records for joints that exist are updated. A missing joint
   leaves its stored pose alone -- this single rule is what makes deleting a
   guide joint lossless rather than a race.
2. **Undo-safe.** Callers persist the result inside the undo chunk of whatever
   operation triggered them, or not at all; capture itself only mutates Python.
3. **Never inside a regenerate**, or it captures a half-built rendering.

Pure apart from the optional scene read, so it unit-tests without Maya.
"""

from __future__ import annotations

import contextlib
from typing import Iterable, Optional

from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.guide_document import GuideDocument

#: True while a regenerate is midway through rebuilding a rendering.
_REGENERATING = False


@contextlib.contextmanager
def regenerating():
    """Mark a rebuild in progress, so a capture cannot read a half-built scene."""
    global _REGENERATING
    was, _REGENERATING = _REGENERATING, True
    try:
        yield
    finally:
        _REGENERATING = was


def is_regenerating() -> bool:
    return _REGENERATING


def capture(
    document: GuideDocument,
    rendered: Optional[list] = None,
    scope: Optional[Iterable[str]] = None,
) -> bool:
    """Fold the scene's poses and guide attrs into ``document``.

    Args:
        document: Mutated in place.
        rendered: A ``RenderedGuide`` list; read from the scene when omitted.
        scope: Instance ids to capture, or None for every module. Draw uses it
            to capture exactly the modules it is about to redraw, without
            quietly pulling the rest of the scene in as a side effect.

    Returns:
        True when anything changed.
    """
    if _REGENERATING:
        raise GuideError(
            "capture ran inside a regenerate; it would record a half-built rendering."
        )
    if rendered is None:
        from .snapshot import snapshot

        rendered = snapshot()

    by_instance: dict = {}
    for guide in rendered:
        by_instance.setdefault(guide.instance_id, {})[guide.pair] = guide

    wanted = None if scope is None else set(scope)
    changed = False
    for entry in document.modules:
        if wanted is not None and entry.instance_id not in wanted:
            continue
        found = by_instance.get(entry.instance_id)
        if not found:
            continue  # additive: nothing rendered, so nothing to say
        for record in entry.guides:
            guide = found.get(record.pair)
            if guide is None:
                continue  # additive: this one is gone, keep what we stored
            position = tuple(float(value) for value in guide.position)
            rotation = tuple(float(value) for value in guide.rotation)
            attrs = {key: float(value) for key, value in guide.attrs.items()}
            if (
                record.position != position
                or record.rotation != rotation
                or record.rotate_order != guide.rotate_order
                or record.attrs != attrs
            ):
                changed = True
            record.position = position
            record.rotation = rotation
            record.rotate_order = guide.rotate_order
            record.attrs = attrs
    return changed
