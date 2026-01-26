import maya.cmds as cmds

from ..core.apicommon import create_node_with_dag_modifier
from ..core.registry import register
from .transform import Transform


@register("joint")
class Joint(Transform):
    """Wrapper for joint nodes."""

    @classmethod
    def create(cls, name=None, parent=None, position=None, orientation=None, scale=None, radius=None):
        """Create and wrap a new joint node."""
        jnt = create_node_with_dag_modifier("joint", name=name, parent=parent)
        jnt_obj = cls(jnt)
        if position is not None:
            jnt_obj.translate = position
        if orientation is not None:
            jnt_obj.orient(orientation)
        if scale is not None:
            jnt_obj.scale = scale
        if radius is not None:
            jnt_obj.radius = radius
        return cls(jnt)

    @property
    def radius(self):
        """Get or set the joint radius."""
        return self["radius"].get()

    @radius.setter
    def radius(self, value):
        """Set the joint radius."""
        self["radius"].set(value)

    def orient(self, xyz=(0, 0, 0)):
        """Orient the joint using the provided XYZ values."""
        cmds.joint(self.name, e=True, orientation=xyz)
