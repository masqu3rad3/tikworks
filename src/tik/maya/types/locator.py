"""Locator node type wrapper."""

from maya import cmds

from ..core.registry import register
from ..core.shapenode import ShapeNode


@register("locator")
class Locator(ShapeNode):
    """Wrapper for locator nodes."""

    @classmethod
    def create(cls, **kwargs):
        """Create a locator node."""

        result = cmds.spaceLocator(**kwargs)
        if isinstance(result, (list, tuple)):
            result = result[0]
        return Locator(result)
