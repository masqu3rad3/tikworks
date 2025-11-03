"""Transform node type wrapper."""

from maya import cmds
from ..core.dagnode import DagNode
from ..core.registry import register


@register("transform")
class Transform(DagNode):
    """Wrapper for transform nodes."""

    def freeze(self, translate=True, rotate=True, scale=True):
        cmds.makeIdentity(self.name, apply=True, translate=translate, rotate=rotate, scale=scale)

    def snap_to(self, target):
        pos = cmds.xform(target.name, q=True, ws=True, t=True)
        rot = cmds.xform(target.name, q=True, ws=True, ro=True)
        cmds.xform(self.name, ws=True, t=pos)
        cmds.xform(self.name, ws=True, ro=rot)
