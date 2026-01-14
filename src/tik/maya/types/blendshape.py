"""Blendshape type for Maya integration."""

from maya import cmds

from ..core.node import Node
# from .mesh import Mesh
from ..core.registry import register, resolve

@register("blendShape")
class BlendShape(Node):
    """Blendshape node type for Maya."""

    @classmethod
    def create(cls, **kwargs):
        """Create Blendshape node type for Maya."""
        blendshape = cmds.createNode("blendShape", **kwargs)
        return cls(blendshape)

    @property
    def influences(self):
        """Return the list of blendshape influences."""
        _influences = cmds.aliasAttr(self.name, query=True)
        if _influences:
            return _influences[::2]
        return None

    @property
    def base_shapes(self):
        """Return the list of base shapes as list of objects."""
        shapes = cmds.blendShape(self.name, query=True, geometry=True)
        if not shapes:
            return []
        shape_type = cmds.objectType(shapes[0])
        return [resolve(shape, class_name=shape_type) for shape in shapes]
