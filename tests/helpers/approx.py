"""Tolerant comparisons for scene maths in tests."""

from maya.api import OpenMaya


def close(vector, expected, tolerance=1e-4):
    """True when every component of ``vector`` is within ``tolerance`` of ``expected``."""
    return all(abs(a - b) < tolerance for a, b in zip(vector, expected))


def axes(transform):
    """The world X and Y axes of ``transform`` as ``MVector``s."""
    matrix = transform.world_matrix
    return (
        OpenMaya.MVector(matrix[0], matrix[1], matrix[2]),
        OpenMaya.MVector(matrix[4], matrix[5], matrix[6]),
    )
