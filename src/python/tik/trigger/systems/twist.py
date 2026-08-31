"""Twist extraction: how much a driver rolls about one axis, in degrees.

Two sources, because they have genuinely different reach:

``matrix``
    Swing-twist decomposition of the driver's rotation relative to a
    reference. Works for any driver in any hierarchy, however it is
    constrained, and is **bounded to +/-180 about the rest pose**. That bound
    is a property of the representation, not of the wiring: the rotation
    matrix for 200 degrees is identical to the one for -160, and
    ``decomposeMatrix`` canonicalises the quaternion to the ``w >= 0``
    hemisphere, so the difference is gone before any quaternion node sees it.
    A ``quatSlerp`` half-angle trick was measured against Maya 2026 and does
    not recover it in any ``angleInterpolation`` mode.

``channel``
    Reads the driver's ``rotate<axis>`` channel directly. Genuinely unbounded
    -- a propeller or wheel winds past 360 without a pop -- but only correct
    when that channel *is* the roll relative to the reference.
"""

from __future__ import annotations

import logging

import tik.maya as tm

logger = logging.getLogger(__name__)

AXES = ("X", "Y", "Z")
SOURCES = ("auto", "matrix", "channel")

#: Rotate order whose innermost (first applied) rotation is this axis, which
#: is what makes the matching rotate channel a pure roll about the bone axis.
_INNERMOST_ORDER = {"X": 0, "Y": 2, "Z": 4}  # xyz, yzx, zxy


def dominant_axis(node_a, node_b) -> tuple[str, int]:
    """Which local axis of ``node_a`` points at ``node_b``.

    Args:
        node_a: The node whose local axes are tested.
        node_b: The node it is assumed to aim at.

    Returns:
        ``(axis, direction)`` where axis is ``"X"``, ``"Y"`` or ``"Z"`` and
        direction is ``1`` or ``-1``.
    """
    aim = node_b.world_position - node_a.world_position
    if aim.length() < 1e-6:
        return "X", 1
    aim.normalize()
    best, best_dot, best_sign = "X", -1.0, 1
    for axis in AXES:
        projection = node_a.world_axis(axis.lower()) * aim
        if abs(projection) > best_dot:
            best, best_dot = axis, abs(projection)
            best_sign = 1 if projection > 0 else -1
    return best, best_sign


def _channel_is_valid(driver, reference, axis: str) -> bool:
    """True when ``driver.rotate<axis>`` is the roll relative to ``reference``.

    Both conditions must hold: the reference must be the driver's parent, so
    the local channel is measured against the right frame; and the rotate
    order must apply this axis innermost, so the channel is a roll about the
    bone's own axis rather than one term of a composite rotation.
    """
    parent = driver.parent
    if parent is None or parent.long_name != reference.long_name:
        return False
    return driver["rotateOrder"].value == _INNERMOST_ORDER[axis]


def twist_plug(
    driver,
    reference,
    *,
    name: str,
    axis: str = "auto",
    source: str = "auto",
):
    """A plug carrying ``driver``'s roll about ``axis``, relative to ``reference``.

    Args:
        driver: Transform whose roll is measured.
        reference: Transform the roll is measured against.
        name: Prefix for every created node.
        axis: ``"auto"``, ``"X"``, ``"Y"`` or ``"Z"``. ``"auto"`` picks the
            axis of ``reference`` pointing at ``driver``, resolved once in
            Python at build time.
        source: ``"auto"``, ``"matrix"`` or ``"channel"``. See the module
            docstring. ``"auto"`` uses ``channel`` when it is valid, which
            gives an FK-driven twist its unbounded range, and ``matrix``
            otherwise.

    Returns:
        A float plug in degrees, zero at the pose held when this was built.
    """
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, got {source!r}.")
    if axis == "auto":
        axis = dominant_axis(reference, driver)[0]
    axis = axis.upper()
    if axis not in AXES:
        raise ValueError(f"axis must be one of {AXES} or 'auto', got {axis!r}.")

    if source == "auto":
        source = "channel" if _channel_is_valid(driver, reference, axis) else "matrix"
        logger.debug("twist '%s': auto-selected the %s source", name, source)
    if source == "channel":
        return _channel_plug(driver, reference, axis, name)
    return _matrix_plug(driver, reference, axis, name)


def _channel_plug(driver, reference, axis: str, name: str):
    """The driver's own rotate channel, re-zeroed to the build pose."""
    if not _channel_is_valid(driver, reference, axis):
        raise ValueError(
            f"twist '{name}': the channel source needs '{driver.name}' parented to "
            f"'{reference.name}' with rotate order "
            f"{_INNERMOST_ORDER[axis]} so rotate{axis} is a pure roll."
        )
    channel = driver[f"rotate{axis}"]
    rest = channel.value
    if abs(rest) < 1e-9:
        return channel
    # Subtracting a constant keeps the plug unbounded, which is the whole
    # point of this source; re-referencing through a matrix would not.
    return channel - rest


def _matrix_plug(driver, reference, axis: str, name: str):
    """Swing-twist decomposition of driver-relative-to-reference."""
    # decomposeMatrix and quatToEuler both ship as plugins, and a fresh
    # mayapy session has neither loaded.
    tm.ensure_plugin("matrixNodes")
    tm.ensure_plugin("quatNodes")
    mult = tm.create_node("multMatrix", name=f"{name}_twist_multMatrix")
    # matrixIn[0] * matrixIn[1] * matrixIn[2]  ->  rest^-1 * driver * ref^-1,
    # i.e. the delta expressed in the rest-local frame, so the twist axis
    # stays the segment's own axis in every pose.
    rest = driver.world_matrix * reference.world_matrix.inverse()
    mult["matrixIn[0]"].value = list(rest.inverse())
    driver["worldMatrix[0]"] >> mult["matrixIn[1]"]
    reference["worldInverseMatrix[0]"] >> mult["matrixIn[2]"]

    decompose = tm.create_node("decomposeMatrix", name=f"{name}_twist_decomposeMatrix")
    mult["matrixSum"] >> decompose["inputMatrix"]

    # Feeding quatToEuler only the axis component and W is what isolates
    # twist from swing.
    to_euler = tm.create_node("quatToEuler", name=f"{name}_twist_quatToEuler")
    decompose[f"outputQuat{axis}"] >> to_euler[f"inputQuat{axis}"]
    decompose["outputQuatW"] >> to_euler["inputQuatW"]
    return to_euler[f"outputRotate{axis}"]
