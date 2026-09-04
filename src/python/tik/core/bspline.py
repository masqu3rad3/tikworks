"""Clamped uniform B-spline basis functions (pure Python, DCC-agnostic).

Used to turn "sample a strip at parameter u" into fixed blend weights over an
ordered set of control transforms. ``basis`` is the Cox–de Boor recursion.
"""

from __future__ import annotations


def knots(count: int, degree: int) -> list[float]:
    """Clamped uniform knot vector for ``count`` control points."""
    spans = count - degree
    interior = [index / spans for index in range(1, spans)]
    return [0.0] * (degree + 1) + interior + [1.0] * (degree + 1)


def clamp_degree(count: int, degree: int) -> int:
    """Highest usable degree for ``count`` control points, at most ``degree``."""
    return max(0, min(degree, count - 1))


def basis(parameter: float, count: int, degree: int) -> list[float]:
    """Return the ``count`` basis weights at ``parameter`` in [0, 1].

    The weights sum to 1 and interpolate the end points (0 -> first control
    point, 1 -> last). ``parameter`` is clamped to [0, 1].
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    if not 0 <= degree <= count - 1:
        raise ValueError(f"degree must be within [0, {count - 1}], got {degree}")
    parameter = min(max(float(parameter), 0.0), 1.0)
    if parameter >= 1.0:
        weights = [0.0] * count
        weights[-1] = 1.0
        return weights
    knot = knots(count, degree)
    weights = [
        1.0 if knot[index] <= parameter < knot[index + 1] else 0.0
        for index in range(len(knot) - 1)
    ]
    for level in range(1, degree + 1):
        next_weights = []
        for index in range(len(knot) - 1 - level):
            span_start, span_end = knot[index], knot[index + level]
            left = 0.0
            if span_end != span_start:
                left = (
                    (parameter - span_start) / (span_end - span_start) * weights[index]
                )
            next_start, next_end = knot[index + 1], knot[index + level + 1]
            right = 0.0
            if next_end != next_start:
                right = (
                    (next_end - parameter)
                    / (next_end - next_start)
                    * weights[index + 1]
                )
            next_weights.append(left + right)
        weights = next_weights
    return weights
