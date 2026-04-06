"""Transform node type wrapper."""

from __future__ import annotations

from typing import Any
from typing import TYPE_CHECKING

from maya import cmds
from maya.api import OpenMaya

from ..core.apicommon import create_node_with_dag_modifier
from ..core.dagnode import DagNode
from ..core.decorators import add_aliases
from ..core.registry import register, resolve

if TYPE_CHECKING:
    from ..core.shapenode import ShapeNode


@register("transform")
@add_aliases(
    {
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
    }
)
class Transform(DagNode):
    """Wrapper for transform nodes."""

    def __init__(self, *args, **kwargs):
        """Initialize the Transform wrapper."""
        super().__init__(*args, **kwargs)
        self._fn_transform = OpenMaya.MFnTransform(self._m_obj)

    @classmethod
    def create(cls, **kwargs):
        """Create a transform node."""
        result = create_node_with_dag_modifier("transform", **kwargs)
        return cls(result)

    @property
    def shapes(self) -> "list[ShapeNode]":
        """Return shape nodes under this transform."""
        dag_node = OpenMaya.MFnDagNode(self._m_obj)
        shapes = []
        for idx in range(dag_node.childCount()):
            child = dag_node.child(idx)
            if child.hasFn(OpenMaya.MFn.kShape):
                fn_dag = OpenMaya.MFnDagNode(child)
                shapes.append(resolve(fn_dag.fullPathName()))
        return shapes

    @property
    def world_translation(self):
        """Return the world translation of this transform's rotate pivot.

        Returns:
            OpenMaya.MVector: World translation of the rotate pivot.
        """
        target_m_transform = OpenMaya.MFnTransform(self.dag_path)
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
        """Get or set the translation of this transform node."""
        return OpenMaya.MVector(self["translate"].get()[0])

    @translate.setter
    def translate(self, value):
        self["translate"].set((value[0], value[1], value[2]))

    @property
    def rotate(self):
        """Get or set the rotation of this transform node."""
        return OpenMaya.MVector(self["rotate"].get()[0])

    @rotate.setter
    def rotate(self, value):
        self["rotate"].set((value[0], value[1], value[2]))

    @property
    def scale(self):
        """Get or set the scale of this transform node."""
        return OpenMaya.MVector(self["scale"].get()[0])

    @scale.setter
    def scale(self, value):
        self["scale"].set((value[0], value[1], value[2]))

    @property
    def translate_x(self):
        """Get or set the X translation of this transform node."""
        return self["translateX"].get()

    @translate_x.setter
    def translate_x(self, value):
        self["translateX"].set(value)

    @property
    def translate_y(self):
        """Get or set the Y translation of this transform node."""
        return self["translateY"].get()

    @translate_y.setter
    def translate_y(self, value):
        self["translateY"].set(value)

    @property
    def translate_z(self):
        """Get or set the Z translation of this transform node."""
        return self["translateZ"].get()

    @translate_z.setter
    def translate_z(self, value):
        self["translateZ"].set(value)

    @property
    def rotate_x(self):
        """Get or set the X rotation of this transform node."""
        return self["rotateX"].get()

    @rotate_x.setter
    def rotate_x(self, value):
        self["rotateX"].set(value)

    @property
    def rotate_y(self):
        """Get or set the Y rotation of this transform node."""
        return self["rotateY"].get()

    @rotate_y.setter
    def rotate_y(self, value):
        self["rotateY"].set(value)

    @property
    def rotate_z(self):
        """Get or set the Z rotation of this transform node."""
        return self["rotateZ"].get()

    @rotate_z.setter
    def rotate_z(self, value):
        self["rotateZ"].set(value)

    @property
    def scale_x(self):
        """Get or set the X scale of this transform node."""
        return self["scaleX"].get()

    @scale_x.setter
    def scale_x(self, value):
        self["scaleX"].set(value)

    @property
    def scale_y(self):
        """Get or set the Y scale of this transform node."""
        return self["scaleY"].get()

    @scale_y.setter
    def scale_y(self, value):
        self["scaleY"].set(value)

    @property
    def scale_z(self):
        """Get or set the Z scale of this transform node."""
        return self["scaleZ"].get()

    @scale_z.setter
    def scale_z(self, value):
        self["scaleZ"].set(value)

    def snap_to(self, target, position=True, rotation=True, scale=False):
        """Snap this transform to another transform's position,
        rotation, and/or scale."""
        node_m_transform = OpenMaya.MFnTransform(self.dag_path)
        if isinstance(target, str):
            target = resolve(target)
        # if its not a transform, raise error
        if not isinstance(target, Transform):
            raise TypeError(f"Target '{target.name}' is not a Transform node.")
        target_m_transform = OpenMaya.MFnTransform(target.dag_path)
        if position:
            target_rotate_pivot = OpenMaya.MVector(
                target_m_transform.rotatePivot(OpenMaya.MSpace.kWorld)
            )
            node_m_transform.setTranslation(target_rotate_pivot, OpenMaya.MSpace.kWorld)
        if rotation:
            target_mt_matrix = OpenMaya.MTransformationMatrix(target.world_matrix)
            node_m_transform.setRotation(
                target_mt_matrix.rotation(True), OpenMaya.MSpace.kWorld
            )
        if scale:
            target_scale = target_m_transform.scale()
            node_m_transform.setScale(target_scale)

    def freeze(self, translate=True, rotate=True, scale=True):
        """Freeze the transformations on this transform node."""
        cmds.makeIdentity(
            self.name,
            apply=True,
            translate=translate,
            rotate=rotate,
            scale=scale,
        )

    def collect_hierarchy(self, node_types=None, include_self=False, max_depth=-1):
        """Collect nodes in the hierarchy under this transform.

        Args:
            node_types (list[str], optional): List of node types to include.
                If None, includes all types. Defaults to None.
            include_self (bool, optional): Whether to include this node.
                Defaults to False.
            max_depth (int, optional): Maximum depth to traverse.
                -1 for unlimited. Defaults to -1.

        Returns:
            list[DagNode]: List of collected nodes.
        """
        if isinstance(node_types, str):
            node_types = [node_types]
        collected = []

        def _collect(current_node, current_depth):
            if max_depth != -1 and current_depth > max_depth:
                return
            if current_depth > 0 or include_self:
                if node_types is None or current_node.type in node_types:
                    collected.append(current_node)
            for child in current_node.children:
                if isinstance(child, Transform):
                    _collect(child, current_depth + 1)
            for shape in current_node.shapes:
                if node_types is None or shape.type in node_types:
                    collected.append(shape)

        _collect(self, 0)
        return collected

    def collect_shape_transforms(self, shape_types=None):
        """Get transforms of shapes under hierarchy of given node."""
        shape_types = shape_types or ["mesh", "nurbsCurve", "nurbsSurface"]
        type_map = {
            "mesh": OpenMaya.MFn.kMesh,
            "nurbsCurve": OpenMaya.MFn.kNurbsCurve,
            "nurbsSurface": OpenMaya.MFn.kNurbsSurface,
        }
        target_fns = [type_map[st] for st in shape_types if st in type_map]

        transforms = set()

        def _traverse(dag_path):
            fn_dag = OpenMaya.MFnDagNode(dag_path)
            for idx in range(fn_dag.childCount()):
                child = fn_dag.child(idx)
                if any(child.hasFn(fn) for fn in target_fns):
                    transforms.add(dag_path.fullPathName())
                if child.hasFn(OpenMaya.MFn.kTransform):
                    child_path = OpenMaya.MDagPath.getAPathTo(child)
                    _traverse(child_path)

        _traverse(self._dag_path())
        return [Transform(node) for node in transforms]

    def create_offset_group(self, name: str = None) -> "Transform":
        """Create an offset transform above this transform in the hierarchy.

        Args:
            name (str, optional): Name for the offset transform.
                If None, defaults to "<this_node_name>_OFFSET".
                Defaults to None.

        Returns:
            Transform: The created offset transform node.
        """
        if name is None:
            name = f"{self.name}_OFFSET"
        offset_transform = Transform.create(name=name)

        # Snap offset to this transform
        offset_transform.snap_to(self, position=True, rotation=True, scale=True)

        # Reparent this transform under the offset
        original_parent = self.parent
        self.parent = offset_transform
        if original_parent:
            offset_transform.parent = original_parent

        return offset_transform
