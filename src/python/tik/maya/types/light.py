"""Light node type wrapper."""

from maya import cmds

from ..core.registry import register
from ..core.shapenode import ShapeNode


@register("light")
class Light(ShapeNode):
    """Wrapper for light nodes."""

    @classmethod
    def create(cls, light_type="pointLight", **kwargs):
        """Create a light node.

        Args:
            light_type : str, optional
                Type of light to create. Default is "pointLight".
                Accepted values include "pointLight", "directionalLight",
                "spotLight", "areaLight", "ambientLight", etc.
            **kwargs
                Additional keyword arguments passed to cmds.createNode.

        Returns:
            Light
                Instance of the created light node.
        """
        light_node = cmds.createNode(light_type, **kwargs)
        return Light(light_node)
