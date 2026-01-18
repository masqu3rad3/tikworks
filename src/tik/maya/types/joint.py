import maya.cmds as cmds
from .transform import Transform
from ..core.registry import register
from ..core.scene import create_node_with_dag_modifier


@register("joint")
class Joint(Transform):
    """Wrapper for joint nodes."""

    @classmethod
    def create(cls, name=None, parent=None):
        """Create and wrap a new joint node."""
        # j = cmds.joint(**kwargs)
        jnt = create_node_with_dag_modifier("joint", name=name, parent=parent)
        return cls(jnt)

    def orient(self, xyz=(0, 0, 0)):
        """Orient the joint using the provided XYZ values."""
        cmds.joint(self.name, e=True, orientation=xyz)
