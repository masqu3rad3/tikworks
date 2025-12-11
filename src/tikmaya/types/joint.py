import maya.cmds as cmds

from .transform import Transform
from ..core.registry import register


@register("joint")
class Joint(Transform):
    """Wrapper for joint nodes."""

    @classmethod
    def create(cls, **kwargs):
        """Create a joint node.

        Returns:
            Joint: Instance of the created joint.
        """
        j = cmds.joint(**kwargs)
        return cls(j)

    def orient(self, xyz=(0, 0, 0)):
        """Orient the joint.

        Args:
            xyz (tuple[float, float, float]): Orientation values.

        Returns:
            None
        """
        cmds.joint(self.name, e=True, orientation=xyz)
