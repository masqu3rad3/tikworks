import maya.cmds as cmds
from .transform import Transform
from ..core.registry import register


@register("joint")
class Joint(Transform):
    """Wrapper for joint nodes."""

    @classmethod
    def create(cls, **kwargs):
        j = cmds.joint(**kwargs)
        return cls(j)

    def orient(self, xyz=(0, 0, 0)):
        cmds.joint(self.name, e=True, orientation=xyz)
