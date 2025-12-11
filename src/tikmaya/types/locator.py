"""Locator node type wrapper."""

from maya import cmds

from ..core.shapenode import ShapeNode
from ..core.registry import register

@register("locator")
class Locator(ShapeNode):
    """Wrapper for locator nodes."""

    @classmethod
    def create(cls, **kwargs):
        """Create a locator node.

        Returns:
            Locator: Instance of the created locator.
        """

        result = cmds.spaceLocator(**kwargs)
        if isinstance(result, (list, tuple)):
            result = result[0]
        return Locator(result)
