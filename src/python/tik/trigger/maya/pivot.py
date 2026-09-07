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


def current_preset(control) -> Optional[str]:
    """The preset label ``control`` is currently on, or None when it has none.

    Args:
        control: A controller, transform or node name.

    Returns:
        str: The label, or None when the control has no pivot presets.
    """
    node = _transform(control)
    labels = preset_labels(node)
    if not labels:
        return None
    index = int(node[PRESET_ATTR].value)
    return labels[index] if 0 <= index < len(labels) else None


def playback_range() -> tuple[float, float]:
    """The playback start and end, as the timeline shows them."""
    return (
        float(tm.playbackOptions(query=True, minTime=True)),
        float(tm.playbackOptions(query=True, maxTime=True)),
    )


def key_times(control, start: float, end: float) -> tuple[float, ...]:
    """Keyframe times on any keyable channel of ``control`` within the range.

    The union across *all* channels, not just translation: once the pivot
    moves, every later pose depends on it, so a control keyed only on rotation
    still needs its translation corrected at those times.

    Args:
        control: A controller, transform or node name.
        start: First frame of the range, inclusive.
        end: Last frame of the range, inclusive.

    Returns:
        tuple[float, ...]: Sorted, de-duplicated times.
    """
    node = _transform(control)
    found = tm.keyframe(node.long_name, query=True, timeChange=True) or []
    return tuple(sorted({float(time) for time in found if start <= time <= end}))


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
    control, preset: Union[str, int], key: bool = False, times=None
) -> str:
    """Set ``control``'s pivot preset while holding its pose.

    A ``rotatePivot`` change displaces the control by a constant translation in
    its parent's space, so correcting ``translate`` by the parent-space delta
    puts it back exactly. Over several ``times`` the correction is redone at
    each, because every pose after the switch depends on the new pivot.

    Args:
        control: A controller, transform or node name carrying ``pivotPreset``.
        preset: A preset label or its enum index.
        key: Key ``translate`` at each corrected time, and the preset once, at
            the first. That single stepped key sets the preset for the whole
            curve, so a range that starts partway through an existing
            animation changes the pivot for the frames before it too, with no
            correction there.
        times: Times to correct at; ``None`` means the current frame only.

    Returns:
        str: One line describing what happened.

    Raises:
        ValueError: If the control has no pivot presets, or ``preset`` names
            one it does not have.
    """
    node = _transform(control)
    labels = preset_labels(node)
    if not labels:
        raise ValueError(f"'{node.name}' has no pivot presets.")
    index = _preset_index(node, preset, labels)
    label = labels[index]

    frames = tuple(float(moment) for moment in times) if times else None
    restore = float(tm.currentTime(query=True))
    if frames is None:
        frames = (restore,)
    try:
        # Two passes, and the order is load-bearing. Keying the enum makes
        # every later frame evaluate with the *new* pivot, so a one-pass loop
        # measures no displacement there and leaves those poses uncorrected.
        # The displacement depends on the control's rotation and the two pivot
        # points, never on its translation, so recording the old origins up
        # front is exact.
        origins = {}
        for moment in frames:
            tm.currentTime(moment)
            origins[moment] = _local_origin(node)

        node[PRESET_ATTR].value = index
        if key:
            # A pivot is a discrete state: interpolating between two enum
            # values is meaningless, so it is keyed once, stepped. The tangents
            # ride on setKeyframe rather than a keyTangent call, whose range
            # flag wants a tuple the cmds proxy turns into a list.
            tm.setKeyframe(
                node.long_name,
                attribute=PRESET_ATTR,
                time=frames[0],
                inTangentType="step",
                outTangentType="step",
            )

        for moment in frames:
            tm.currentTime(moment)
            after = _local_origin(node)
            node.translate = tuple(
                current - (moved - rest)
                for current, rest, moved in zip(node.translate, origins[moment], after)
            )
            if key:
                tm.setKeyframe(node.long_name, attribute="translate", time=moment)
    finally:
        tm.currentTime(restore)

    if len(frames) > 1:
        return f"{node.name} to {label} over {len(frames)} keys — pose held"
    return f"{node.name} to {label} — pose held"
