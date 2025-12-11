"""Transform node type wrapper."""

from maya import cmds
from maya.api import OpenMaya
from ..core.dagnode import DagNode
from ..core.registry import register, resolve
from ..core.decorators import add_aliases


@register("transform")
@add_aliases({
    "translate": "t",
    "rotate": "r",
    "scale": "s",
    "translate_x": "tx",
    "translate_y": "ty",
    "translate_z": "tz",
    "rotate_x": "rx",
    "rotate_y": "ry",
    "rotate_z": "rz",
    "scale_x": "sx",
    "scale_y": "sy",
    "scale_z": "sz",
})
class Transform(DagNode):
    """Wrapper for transform nodes."""

    def __init__(self, *args, **kwargs):
        """Initialize the transform wrapper."""
        super().__init__(*args, **kwargs)

    @classmethod
    def create(cls, **kwargs):
        """Create a transform node.

        Returns:
            Transform: Instance of the created transform.
        """
        result = cmds.createNode("transform", **kwargs)
        return cls(result)

    @property
    def shapes(self) -> "list[ShapeNode]":
        """Retrieve the shape children for this transform.

        Returns:
            list[ShapeNode]: Wrapped child shapes.
        """
        names = cmds.listRelatives(self.name, shapes=True, fullPath=True) or []
        return [resolve(s) for s in names]

    @property
    def mdag_path(self):
        """Return the MDagPath for this transform node.

        Returns:
            OpenMaya.MDagPath: DAG path for this transform.
        """
        selection_ls = OpenMaya.MSelectionList()
        selection_ls.add(self.name)
        return selection_ls.getDagPath(0)

    @property
    def world_translation(self):
        """Return the world translation of this transform's rotate pivot.

        Returns:
            OpenMaya.MVector: World translation of the rotate pivot.
        """
        target_m_transform = OpenMaya.MFnTransform(self.mdag_path)
        target_rotate_pivot = OpenMaya.MVector(
            target_m_transform.rotatePivot(OpenMaya.MSpace.kWorld)
        )
        return target_rotate_pivot

    @property
    def world_matrix(self):
        """Return the world matrix of this transform node.

        Returns:
            OpenMaya.MMatrix: World transformation matrix.
        """
        return OpenMaya.MMatrix(self["worldMatrix[0]"].get())

    @property
    def matrix(self):
        """Return the local matrix of this transform node.

        Returns:
            OpenMaya.MMatrix: Local transformation matrix.
        """
        return OpenMaya.MMatrix(self["matrix"].get())

    @property
    def parent_matrix(self):
        """Return the local matrix of this transform node's parent.

        Returns:
            OpenMaya.MMatrix: Parent's local transformation matrix.
        """
        return OpenMaya.MMatrix(self["parentMatrix[0]"].get())

    @property
    def translate(self):
        """Get or set the translation of this transform node.

        Returns:
            OpenMaya.MVector: Translation vector.
        """
        return OpenMaya.MVector(self["translate"].get()[0])

    @translate.setter
    def translate(self, value):
        """Set the translation of this transform node.

        Args:
            value (tuple[float, float, float]): Translation values.
        """
        self["translate"].set((value[0], value[1], value[2]))

    @property
    def rotate(self):
        """Get or set the rotation of this transform node.

        Returns:
            OpenMaya.MVector: Rotation vector.
        """
        return OpenMaya.MVector(self["rotate"].get()[0])

    @rotate.setter
    def rotate(self, value):
        """Set the rotation of this transform node.

        Args:
            value (tuple[float, float, float]): Rotation values.
        """
        self["rotate"].set((value[0], value[1], value[2]))

    @property
    def scale(self):
        """Get or set the scale of this transform node.

        Returns:
            OpenMaya.MVector: Scale vector.
        """
        return OpenMaya.MVector(self["scale"].get()[0])

    @scale.setter
    def scale(self, value):
        """Set the scale of this transform node.

        Args:
            value (tuple[float, float, float]): Scale values.
        """
        self["scale"].set((value[0], value[1], value[2]))

    @property
    def translate_x(self):
        """Get or set the X translation of this transform node.

        Returns:
            float: X translation value.
        """
        return self["translateX"].get()

    @translate_x.setter
    def translate_x(self, value):
        """Set the X translation of this transform node.

        Args:
            value (float): X translation value.
        """
        self["translateX"].set(value)

    @property
    def translate_y(self):
        """Get or set the Y translation of this transform node.

        Returns:
            float: Y translation value.
        """
        return self["translateY"].get()

    @translate_y.setter
    def translate_y(self, value):
        """Set the Y translation of this transform node.

        Args:
            value (float): Y translation value.
        """
        self["translateY"].set(value)

    @property
    def translate_z(self):
        """Get or set the Z translation of this transform node.

        Returns:
            float: Z translation value.
        """
        return self["translateZ"].get()

    @translate_z.setter
    def translate_z(self, value):
        """Set the Z translation of this transform node.

        Args:
            value (float): Z translation value.
        """
        self["translateZ"].set(value)

    @property
    def rotate_x(self):
        """Get or set the X rotation of this transform node.

        Returns:
            float: X rotation value.
        """
        return self["rotateX"].get()

    @rotate_x.setter
    def rotate_x(self, value):
        """Set the X rotation of this transform node.

        Args:
            value (float): X rotation value.
        """
        self["rotateX"].set(value)

    @property
    def rotate_y(self):
        """Get or set the Y rotation of this transform node.

        Returns:
            float: Y rotation value.
        """
        return self["rotateY"].get()

    @rotate_y.setter
    def rotate_y(self, value):
        """Set the Y rotation of this transform node.

        Args:
            value (float): Y rotation value.
        """
        self["rotateY"].set(value)

    @property
    def rotate_z(self):
        """Get or set the Z rotation of this transform node.

        Returns:
            float: Z rotation value.
        """
        return self["rotateZ"].get()

    @rotate_z.setter
    def rotate_z(self, value):
        """Set the Z rotation of this transform node.

        Args:
            value (float): Z rotation value.
        """
        self["rotateZ"].set(value)

    @property
    def scale_x(self):
        """Get or set the X scale of this transform node.

        Returns:
            float: X scale value.
        """
        return self["scaleX"].get()

    @scale_x.setter
    def scale_x(self, value):
        """Set the X scale of this transform node.

        Args:
            value (float): X scale value.
        """
        self["scaleX"].set(value)

    @property
    def scale_y(self):
        """Get or set the Y scale of this transform node.

        Returns:
            float: Y scale value.
        """
        return self["scaleY"].get()

    @scale_y.setter
    def scale_y(self, value):
        """Set the Y scale of this transform node.

        Args:
            value (float): Y scale value.
        """
        self["scaleY"].set(value)

    @property
    def scale_z(self):
        """Get or set the Z scale of this transform node.

        Returns:
            float: Z scale value.
        """
        return self["scaleZ"].get()

    @scale_z.setter
    def scale_z(self, value):
        """Set the Z scale of this transform node.

        Args:
            value (float): Z scale value.
        """
        self["scaleZ"].set(value)

    def snap_to(self, target, position=True, rotation=True, scale=False):
        """Snap this transform to another transform's position, rotation, and/or scale.

        Args:
            target (Transform | str): Target transform or name to snap to.
            position (bool): Whether to match position.
            rotation (bool): Whether to match rotation.
            scale (bool): Whether to match scale.

        Raises:
            TypeError: If the target cannot be resolved to a Transform.
        """
        node_m_transform = OpenMaya.MFnTransform(self.mdag_path)
        if isinstance(target, str):
            target = resolve(target)
        # if its not a transform, raise error
        if not isinstance(target, Transform):
            raise TypeError(f"Target '{target.name}' is not a Transform node.")
        target_m_transform = OpenMaya.MFnTransform(target.mdag_path)
        if position:
            target_rotate_pivot = OpenMaya.MVector(
                target_m_transform.rotatePivot(OpenMaya.MSpace.kWorld)
            )
            node_m_transform.setTranslation(
                target_rotate_pivot, OpenMaya.MSpace.kWorld
            )
        if rotation:
            target_mt_matrix = OpenMaya.MTransformationMatrix(
                OpenMaya.MMatrix(
                    cmds.xform(target.name, matrix=True, ws=1, q=True)
                )
            )
            node_m_transform.setRotation(
                target_mt_matrix.rotation(True), OpenMaya.MSpace.kWorld
            )
        if scale:
            target_scale = target_m_transform.scale()
            node_m_transform.setScale(target_scale)

    def freeze(self, translate=True, rotate=True, scale=True):
        """Freeze the transformations on this transform node.

        Args:
            translate (bool): Whether to freeze translation.
            rotate (bool): Whether to freeze rotation.
            scale (bool): Whether to freeze scale.
        """
        cmds.makeIdentity(
            self.name, apply=True, translate=translate, rotate=rotate, scale=scale
        )
