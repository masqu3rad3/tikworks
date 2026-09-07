"""Switching a control's pivot preset without moving it.

A pivot switch always disturbs a non-zero rotation: rotating about a different
point *is* a different transform, and a live ``rotatePivotTranslate``
compensation does not fix it -- the algebra collapses to ``p' = p.R`` and the
pivot stops doing anything at all (spec Part 0.1). What works is compensating
once, at the moment of the switch, which is what Maya's own pivot edit does.

Animation-time only. Nothing in the build path imports this.
"""

from __future__ import annotations

from typing import Optional, Sequence, Union

import tik.maya as tm
from tik.maya.core.decorators import undo

PRESET_ATTR = "pivotPreset"


def _transform(control):
    """The Transform behind a role, or ``control`` resolved."""
    node = getattr(control, "transform", None)
    return node if node is not None else tm.resolve(control)


def _local_origin(node) -> Sequence[float]:
    """Where the node's origin sits in its parent's space.

    The translation row of the local matrix. Changing ``rotatePivot`` shifts
    that matrix by a constant translation -- constant because the shift
    ``(rp2 - rp) - (rp2 - rp).R`` does not depend on the point being
    transformed -- so the difference across a switch is exactly what
    ``translate`` must give back.
    """
    return node["matrix"].get()[12:15]


def preset_labels(control) -> list[str]:
    """The preset names on ``control``, ``default`` first.

    Args:
        control: A controller, transform or node name.

    Returns:
        list[str]: The enum labels, or an empty list when the control has no
        movable pivot with presets.
    """
    node = _transform(control)
    if not node[PRESET_ATTR].exists():
        return []
    listed = tm.attributeQuery(PRESET_ATTR, node=node.long_name, listEnum=True)
    return listed[0].split(":") if listed else []


def _preset_index(node, preset: Union[str, int], labels: Sequence[str]) -> int:
    """Resolve ``preset`` to an enum index, raising when it names nothing."""
    if isinstance(preset, bool) or not isinstance(preset, (str, int)):
        raise ValueError(f"'{preset!r}' is not a preset name or index.")
    if isinstance(preset, int):
        if not 0 <= preset < len(labels):
            raise ValueError(f"'{node.name}' has no pivot preset at index {preset}.")
        return preset
    if preset not in labels:
        raise ValueError(
            f"'{node.name}' has no pivot preset '{preset}'. Known: {list(labels)}."
        )
    return labels.index(preset)


@undo
def switch_pivot_preset(
    control, preset: Union[str, int], key: bool = False
) -> Optional[str]:
    """Set ``control``'s pivot preset while holding its current pose.

    Reads where the control sits in its parent's space, switches the preset,
    then writes ``translate`` so it lands back there. Rotation applied *after*
    the switch swings about the new pivot, which is the point.

    Args:
        control: A controller, transform or node name carrying ``pivotPreset``.
        preset: A preset label or its enum index.
        key: Set a key on ``pivotPreset`` and ``translate`` afterwards.

    Returns:
        str: The label switched to.

    Raises:
        ValueError: If the control has no pivot presets, or ``preset`` names
            one it does not have.
    """
    node = _transform(control)
    labels = preset_labels(node)
    if not labels:
        raise ValueError(f"'{node.name}' has no pivot presets.")
    index = _preset_index(node, preset, labels)

    before = _local_origin(node)
    node[PRESET_ATTR].value = index
    after = _local_origin(node)
    node.translate = tuple(
        current - (moved - rest)
        for current, rest, moved in zip(node.translate, before, after)
    )
    if key:
        tm.setKeyframe(node.long_name, attribute=[PRESET_ATTR, "translate"])
    return labels[index]
