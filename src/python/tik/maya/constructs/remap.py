"""Remap a scalar from one range to another, with a choice of curve.

Wraps ``remapValue``, whose ramp interpolation enum is exactly
``none`` / ``linear`` / ``smooth`` / ``spline``.
"""

from __future__ import annotations

from typing import Optional

from maya import cmds

from ..core.decorators import undo
from ..core.plug import Plug
from ..core.scene import create_node

INTERPOLATIONS = {"none": 0, "linear": 1, "smooth": 2, "spline": 3}


class Remap:
    """Wrapper for a ``remapValue`` node."""

    def __init__(self, node) -> None:
        self.node = node

    @classmethod
    @undo
    def create(
        cls,
        value,
        *,
        input_min,
        input_max,
        output_min=0.0,
        output_max=1.0,
        interpolation: str = "smooth",
        name: Optional[str] = None,
    ) -> "Remap":
        """Remap ``value`` from the input range onto the output range.

        Args:
            value: Plug or float driving the remap.
            input_min: Plug or float; values at or below map to ``output_min``.
            input_max: Plug or float; values at or above map to ``output_max``.
            output_min: Plug or float.
            output_max: Plug or float.
            interpolation: ``none``, ``linear``, ``smooth`` or ``spline``.
            name: Prefix for the created node.

        Returns:
            The construct.
        """
        if interpolation not in INTERPOLATIONS:
            raise ValueError(
                f"Unknown interpolation '{interpolation}'. Use one of "
                f"{sorted(INTERPOLATIONS)}."
            )
        node = create_node("remapValue", name=f"{name or 'remap'}_remapValue")
        for attr, item in (
            ("inputValue", value),
            ("inputMin", input_min),
            ("inputMax", input_max),
            ("outputMin", output_min),
            ("outputMax", output_max),
        ):
            if isinstance(item, Plug):
                item >> node[attr]
            else:
                node[attr].value = float(item)
        # The ramp's two default points carry the curve shape.
        for index, position in ((0, 0.0), (1, 1.0)):
            node[f"value[{index}].value_Position"].value = position
            node[f"value[{index}].value_FloatValue"].value = position
            node[f"value[{index}].value_Interp"].value = INTERPOLATIONS[interpolation]
        return cls(node)

    @property
    def output(self) -> Plug:
        """The remapped scalar."""
        return self.node["outValue"]

    @undo
    def delete(self) -> None:
        """Delete the node."""
        if self.node.exists():
            cmds.delete(self.node.long_name)
