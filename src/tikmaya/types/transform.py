"""Transform node type wrapper."""

from maya import cmds
from maya.api import OpenMaya
from ..core.dagnode import DagNode
from ..core.registry import register, get_node


@register("transform")
class Transform(DagNode):
    """Wrapper for transform nodes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def create(cls, name=None, **kwargs):
        """Create a transform node."""
        result = cmds.createNode("transform", name=name, **kwargs)
        return cls(result)

    def freeze(self, translate=True, rotate=True, scale=True):
        cmds.makeIdentity(self.name, apply=True, translate=translate, rotate=rotate, scale=scale)

    @property
    def shapes(self) -> "list[ShapeNode]":
        names = cmds.listRelatives(self.name, shapes=True, fullPath=True) or []
        return [get_node(s) for s in names]

    @property
    def mdag_path(self):
        """Return the MDagPath for this transform node."""
        selection_ls = OpenMaya.MSelectionList()
        selection_ls.add(self.name)
        return selection_ls.getDagPath(0)

    def snap_to(self, target, position=True, rotation=True, scale=False):
        """Snap this transform to another transform's position, rotation, and/or scale."""
        node_m_transform = OpenMaya.MFnTransform(self.mdag_path)
        if isinstance(target, str):
            target = get_node(target)
        # if its not a transform, raise error
        if not isinstance(target, Transform):
            raise TypeError(f"Target '{target.name}' is not a Transform node.")
        target_m_transform = OpenMaya.MFnTransform(target.mdag_path)
        if position:
            target_rotate_pivot = OpenMaya.MVector(
                target_m_transform.rotatePivot(OpenMaya.MSpace.kWorld)
            )
            node_m_transform.setTranslation(target_rotate_pivot,
                                            OpenMaya.MSpace.kWorld)
        if rotation:
            target_mt_matrix = OpenMaya.MTransformationMatrix(
                OpenMaya.MMatrix(cmds.xform(target.name, matrix=True, ws=1, q=True))
            )
            node_m_transform.setRotation(
                target_mt_matrix.rotation(True), OpenMaya.MSpace.kWorld
            )
        if scale:
            target_scale = target_m_transform.scale()
            node_m_transform.setScale(target_scale)
