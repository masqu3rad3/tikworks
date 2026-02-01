"""SkinCluster type for Maya integration."""
from functools import partial

from pathlib import Path
from typing import List, Optional, Union

from maya import cmds
from maya.api import OpenMaya
from maya.api import OpenMayaAnim

from ..core.node import Node
from ..core.registry import register
from ..core.scene import proxy_wrapper


class SkinWeights:
    """Container for skin weights enabling arithmetic operations.

    This class wraps weight data and provides dunder methods for intuitive
    weight manipulation.

    Attributes:
        weights: List of weight values (flat array).
        influence_count: Number of influences.
        vertex_count: Number of vertices.
        influence_names: Optional list of influence names.
    """

    def __init__(
        self,
        weights: List[float],
        influence_count: int,
        vertex_count: int,
        influence_names: Optional[List[str]] = None,
    ):
        """Initialize SkinWeights container.

        Args:
            weights: List of weight values (flat array).
            influence_count: Number of influences.
            vertex_count: Number of vertices.
            influence_names: Optional list of influence names for reference.
        """
        self._weights = list(weights)
        self._influence_count = influence_count
        self._vertex_count = vertex_count
        self._influence_names = influence_names or []

    # === Properties ===

    @property
    def weights(self) -> List[float]:
        """The raw weight list."""
        return self._weights

    @property
    def influence_count(self) -> int:
        """Number of influences."""
        return self._influence_count

    @property
    def vertex_count(self) -> int:
        """Number of vertices."""
        return self._vertex_count

    @property
    def influence_names(self) -> List[str]:
        """Names of influences if available."""
        return self._influence_names

    # === Public Methods ===

    def get_vertex_weights(self, vertex_index: int) -> List[float]:
        """Get weights for a single vertex across all influences.

        Args:
            vertex_index: The vertex index to query.

        Returns:
            List of weights for each influence at the specified vertex.
        """
        if vertex_index < 0 or vertex_index >= self._vertex_count:
            raise IndexError(
                f"Vertex index {vertex_index} out of range [0, {self._vertex_count})"
            )
        start_idx = vertex_index * self._influence_count
        return self._weights[start_idx : start_idx + self._influence_count]

    def get_influence_weights(self, influence_index: int) -> List[float]:
        """Get weights for a single influence across all vertices.

        Args:
            influence_index: The influence index to query.

        Returns:
            List of weights for each vertex at the specified influence.
        """
        if influence_index < 0 or influence_index >= self._influence_count:
            raise IndexError(
                f"Influence index {influence_index} out of range "
                f"[0, {self._influence_count})"
            )
        return [
            self._weights[vtx_idx * self._influence_count + influence_index]
            for vtx_idx in range(self._vertex_count)
        ]

    def copy(self) -> "SkinWeights":
        """Create a deep copy of this SkinWeights instance."""
        return SkinWeights(
            list(self._weights),
            self._influence_count,
            self._vertex_count,
            list(self._influence_names),
        )

    def clamp(self, min_value: float = 0.0, max_value: float = 1.0) -> "SkinWeights":
        """Clamp all weight values to the specified range.

        Args:
            min_value: Minimum weight value.
            max_value: Maximum weight value.

        Returns:
            Self for method chaining.
        """
        self._weights = [
            max(min_value, min(max_value, weight)) for weight in self._weights
        ]
        return self

    def normalize(self) -> "SkinWeights":
        """Normalize weights so each vertex sums to 1.0.

        Returns:
            Self for method chaining.
        """
        for vtx_idx in range(self._vertex_count):
            start_idx = vtx_idx * self._influence_count
            end_idx = start_idx + self._influence_count
            total = sum(self._weights[start_idx:end_idx])
            if total > 0:
                for idx in range(start_idx, end_idx):
                    self._weights[idx] /= total
        return self

    # === Dunder Methods ===

    def __len__(self) -> int:
        """Return total number of weight values."""
        return len(self._weights)

    def __getitem__(self, index: int) -> float:
        """Get weight at index."""
        return self._weights[index]

    def __setitem__(self, index: int, value: float) -> None:
        """Set weight at index."""
        self._weights[index] = value

    def __iter__(self):
        """Iterate over weight values."""
        return iter(self._weights)

    def __add__(self, other: Union["SkinWeights", float]) -> "SkinWeights":
        """Add weights or scalar to this instance."""
        result = self.copy()
        if isinstance(other, SkinWeights):
            if len(other) != len(self):
                raise ValueError("SkinWeights dimensions must match for addition.")
            result._weights = [
                self_w + other_w
                for self_w, other_w in zip(self._weights, other._weights)
            ]
        else:
            result._weights = [weight + float(other) for weight in self._weights]
        return result

    def __radd__(self, other: float) -> "SkinWeights":
        """Right-add for scalar values."""
        return self.__add__(other)

    def __sub__(self, other: Union["SkinWeights", float]) -> "SkinWeights":
        """Subtract weights or scalar from this instance."""
        result = self.copy()
        if isinstance(other, SkinWeights):
            if len(other) != len(self):
                raise ValueError("SkinWeights dimensions must match for subtraction.")
            result._weights = [
                self_w - other_w
                for self_w, other_w in zip(self._weights, other._weights)
            ]
        else:
            result._weights = [weight - float(other) for weight in self._weights]
        return result

    def __rsub__(self, other: float) -> "SkinWeights":
        """Right-subtract for scalar values."""
        result = self.copy()
        result._weights = [float(other) - weight for weight in self._weights]
        return result

    def __mul__(self, other: Union["SkinWeights", float]) -> "SkinWeights":
        """Multiply weights by another SkinWeights or scalar."""
        result = self.copy()
        if isinstance(other, SkinWeights):
            if len(other) != len(self):
                raise ValueError(
                    "SkinWeights dimensions must match for multiplication."
                )
            result._weights = [
                self_w * other_w
                for self_w, other_w in zip(self._weights, other._weights)
            ]
        else:
            result._weights = [weight * float(other) for weight in self._weights]
        return result

    def __rmul__(self, other: float) -> "SkinWeights":
        """Right-multiply for scalar values."""
        return self.__mul__(other)

    def __truediv__(self, other: Union["SkinWeights", float]) -> "SkinWeights":
        """Divide weights by another SkinWeights or scalar."""
        result = self.copy()
        if isinstance(other, SkinWeights):
            if len(other) != len(self):
                raise ValueError("SkinWeights dimensions must match for division.")
            result._weights = [
                (self_w / other_w) if other_w != 0 else 0.0
                for self_w, other_w in zip(self._weights, other._weights)
            ]
        else:
            divisor = float(other)
            if divisor == 0:
                raise ZeroDivisionError("Cannot divide SkinWeights by zero.")
            result._weights = [weight / divisor for weight in self._weights]
        return result

    def __neg__(self) -> "SkinWeights":
        """Invert weights (1.0 - weight)."""
        result = self.copy()
        result._weights = [1.0 - weight for weight in self._weights]
        return result

    def __eq__(self, other: "SkinWeights") -> bool:
        """Check equality with another SkinWeights."""
        if not isinstance(other, SkinWeights):
            return False
        if len(self) != len(other):
            return False
        tolerance = 1e-6
        return all(
            abs(self_w - other_w) <= tolerance
            for self_w, other_w in zip(self._weights, other._weights)
        )

    def __repr__(self) -> str:
        """Debug representation."""
        return (
            f"<SkinWeights vertices={self._vertex_count} "
            f"influences={self._influence_count}>"
        )


@register("skinCluster")
class SkinCluster(Node):
    """SkinCluster node type for Maya."""

    @classmethod
    def create(
        cls,
        geometry: str,
        influences: List[str],
        name: Optional[str] = None,
        **kwargs,
    ) -> "SkinCluster":
        """Create a new skinCluster on geometry.

        Args:
            geometry: The geometry to bind.
            influences: List of influence objects (joints, transforms).
            name: Optional name for the skinCluster node.
            **kwargs: Additional arguments passed to cmds.skinCluster.

        Returns:
            SkinCluster instance wrapping the new node.
        """
        default_kwargs = {
            "toSelectedBones": False,
            "bindMethod": 0,
            "skinMethod": 0,
            "normalizeWeights": 1,
            "maximumInfluences": 4,
        }
        default_kwargs.update(kwargs)

        if name:
            default_kwargs["name"] = name

        skin_fn = partial(proxy_wrapper, "skinCluster")
        # result = cmds.skinCluster(influences, geometry, **default_kwargs)
        result = skin_fn(influences, geometry, **default_kwargs)
        skin_node = result[0] if isinstance(result, (list, tuple)) else result
        return skin_node

    # === Properties ===

    @property
    def influences(self) -> List[str]:
        """Return list of influence object names."""
        return cmds.skinCluster(self.name, query=True, influence=True) or []

    @property
    def influence_count(self) -> int:
        """Return the number of influences."""
        return len(self.influences)

    @property
    def geometry(self) -> Optional[str]:
        """Return the first connected geometry shape name."""
        geometries = cmds.skinCluster(self.name, query=True, geometry=True)
        return geometries[0] if geometries else None

    @property
    def geometries(self) -> List[str]:
        """Return all connected geometry shape names."""
        return cmds.skinCluster(self.name, query=True, geometry=True) or []

    @property
    def skinning_method(self) -> int:
        """Return the skinning method (0=Linear, 1=DualQuaternion, 2=Blend)."""
        return cmds.skinCluster(self.name, query=True, skinMethod=True)

    @skinning_method.setter
    def skinning_method(self, value: int) -> None:
        """Set the skinning method."""
        cmds.skinCluster(self.name, edit=True, skinMethod=value)

    # TODO: Maybe normalize weights shouldnt be a property...
    @property
    def normalize_weights(self) -> int:
        """Return normalize weights mode (0=None, 1=Interactive, 2=Post)."""
        return cmds.skinCluster(self.name, query=True, normalizeWeights=True)

    @normalize_weights.setter
    def normalize_weights(self, value: int) -> None:
        """Set normalize weights mode."""
        cmds.skinCluster(self.name, edit=True, normalizeWeights=value)

    @property
    def max_influences(self) -> int:
        """Return the maximum number of influences per vertex."""
        return cmds.skinCluster(self.name, query=True, maximumInfluences=True)

    @max_influences.setter
    def max_influences(self, value: int) -> None:
        """Set the maximum number of influences per vertex."""
        cmds.skinCluster(self.name, edit=True, maximumInfluences=value)

    # TODO: Do we need this here?
    @property
    def vertex_count(self) -> int:
        """Return the number of vertices in the bound geometry."""
        geometry = self.geometry
        if not geometry:
            return 0
        return cmds.polyEvaluate(geometry, vertex=True)

    # === Private Helpers ===

    def _get_skin_fn(self) -> OpenMayaAnim.MFnSkinCluster:
        """Return the MFnSkinCluster function set."""
        return OpenMayaAnim.MFnSkinCluster(self.m_obj)

    def _get_geometry_dag_and_components(
        self, geometry: Optional[str] = None
    ) -> tuple:
        """Get the DAG path and component for geometry vertices.

        Args:
            geometry: Optional specific geometry name.

        Returns:
            Tuple of (MDagPath, MObject component, MFnSkinCluster).
        """
        target_geo = geometry or self.geometry
        if not target_geo:
            raise RuntimeError(f"No geometry connected to skinCluster '{self.name}'")

        selection_list = OpenMaya.MSelectionList()
        selection_list.add(target_geo)
        dag_path = selection_list.getDagPath(0)

        mesh_iter = OpenMaya.MItMeshVertex(dag_path)
        indices = list(range(mesh_iter.count()))

        single_indexed_component = OpenMaya.MFnSingleIndexedComponent()
        vertex_component = single_indexed_component.create(
            OpenMaya.MFn.kMeshVertComponent
        )
        single_indexed_component.addElements(indices)

        skin_fn = self._get_skin_fn()
        return dag_path, vertex_component, skin_fn

    def _get_influence_indices(
        self, skin_fn: OpenMayaAnim.MFnSkinCluster
    ) -> OpenMaya.MIntArray:
        """Get the influence indices array."""
        influence_dags = skin_fn.influenceObjects()
        influence_indices = OpenMaya.MIntArray(len(influence_dags), 0)
        for idx in range(len(influence_dags)):
            influence_indices[idx] = int(
                skin_fn.indexForInfluenceObject(influence_dags[idx])
            )
        return influence_indices

    def __split_path(self, file_path, validate=False):
        """Validate and split a file path into directory and filename."""
        file_path = Path(file_path)
        if validate:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        file_name = file_path.name
        file_dir = file_path.parent.as_posix()
        return file_dir, file_name

    # === Public Methods ===

    def influence_index(self, influence: str) -> int:
        """Get the index of an influence by name.

        Args:
            influence: Name of the influence object.

        Returns:
            The logical index of the influence.
        """
        skin_fn = self._get_skin_fn()
        selection_list = OpenMaya.MSelectionList()
        try:
            selection_list.add(influence)
            influence_dag = selection_list.getDagPath(0)
            return skin_fn.indexForInfluenceObject(influence_dag)
        except RuntimeError:
            raise ValueError(
                f"Influence '{influence}' not found in skinCluster '{self.name}'"
            )

    def add_influence(
        self,
        influence: str,
        weight: float = 0.0,
        lock_weights: bool = False,
    ) -> int:
        """Add an influence to the skinCluster.

        Args:
            influence: The transform/joint to add as an influence.
            weight: Default weight value for the new influence.
            lock_weights: Whether to lock the influence weights.

        Returns:
            The index of the newly added influence.
        """
        cmds.skinCluster(
            self.name,
            edit=True,
            addInfluence=influence,
            weight=weight,
            lockWeights=lock_weights,
        )
        return self.influence_index(influence)

    def remove_influence(self, influence: str) -> None:
        """Remove an influence from the skinCluster.

        Args:
            influence: The influence object to remove.
        """
        cmds.skinCluster(self.name, edit=True, removeInfluence=influence)

    def lock_influence(self, influence: str, lock: bool = True) -> None:
        """Lock or unlock an influence's weights.

        Maya connects the skinCluster's lockWeights array to each influence's
        'liw' (Lock Influence Weights) attribute.

        Args:
            influence: The influence object name.
            lock: True to lock, False to unlock.
        """
        if cmds.attributeQuery("liw", node=influence, exists=True):
            cmds.setAttr(f"{influence}.liw", lock)
        else:
            index = self.influence_index(influence)
            cmds.setAttr(f"{self.name}.lockWeights[{index}]", lock)

    def is_influence_locked(self, influence: str) -> bool:
        """Check if an influence's weights are locked.

        Args:
            influence: The influence object name.

        Returns:
            True if locked, False otherwise.
        """
        if cmds.attributeQuery("liw", node=influence, exists=True):
            return cmds.getAttr(f"{influence}.liw")
        index = self.influence_index(influence)
        return cmds.getAttr(f"{self.name}.lockWeights[{index}]")

    def get_weights(self, geometry: Optional[str] = None) -> SkinWeights:
        """Get all skin weights for the geometry.

        Args:
            geometry: Optional specific geometry to query.

        Returns:
            SkinWeights container with weight data.
        """
        dag_path, vertex_component, skin_fn = self._get_geometry_dag_and_components(
            geometry
        )
        weights, _ = skin_fn.getWeights(dag_path, vertex_component)

        influence_dags = skin_fn.influenceObjects()
        influence_names = [
            OpenMaya.MFnDagNode(dag).name() for dag in influence_dags
        ]

        return SkinWeights(
            list(weights),
            influence_count=len(influence_dags),
            vertex_count=self.vertex_count,
            influence_names=influence_names,
        )

    def set_weights(
        self,
        weights: Union[SkinWeights, List[float]],
        geometry: Optional[str] = None,
        normalize: bool = True,
    ) -> None:
        """Set all skin weights for the geometry.

        Args:
            weights: SkinWeights or list of weight values.
            geometry: Optional specific geometry to set.
            normalize: Whether to normalize weights after setting.
        """
        dag_path, vertex_component, skin_fn = self._get_geometry_dag_and_components(
            geometry
        )
        influence_indices = self._get_influence_indices(skin_fn)

        if isinstance(weights, SkinWeights):
            weight_array = OpenMaya.MDoubleArray(weights.weights)
        else:
            weight_array = OpenMaya.MDoubleArray(weights)

        skin_fn.setWeights(
            dag_path, vertex_component, influence_indices, weight_array, normalize
        )

    def get_vertex_weights(
        self, vertex_indices: List[int], geometry: Optional[str] = None
    ) -> SkinWeights:
        """Get weights for specific vertices.

        Args:
            vertex_indices: List of vertex indices to query.
            geometry: Optional specific geometry.

        Returns:
            SkinWeights for the specified vertices.
        """
        target_geo = geometry or self.geometry
        if not target_geo:
            raise RuntimeError(f"No geometry connected to skinCluster '{self.name}'")

        selection_list = OpenMaya.MSelectionList()
        selection_list.add(target_geo)
        dag_path = selection_list.getDagPath(0)

        single_indexed_component = OpenMaya.MFnSingleIndexedComponent()
        vertex_component = single_indexed_component.create(
            OpenMaya.MFn.kMeshVertComponent
        )
        single_indexed_component.addElements(vertex_indices)

        skin_fn = self._get_skin_fn()
        weights, _ = skin_fn.getWeights(dag_path, vertex_component)

        influence_dags = skin_fn.influenceObjects()
        influence_names = [
            OpenMaya.MFnDagNode(dag).name() for dag in influence_dags
        ]

        return SkinWeights(
            list(weights),
            influence_count=len(influence_dags),
            vertex_count=len(vertex_indices),
            influence_names=influence_names,
        )

    def set_vertex_weights(
        self,
        vertex_indices: List[int],
        weights: Union[SkinWeights, List[float]],
        geometry: Optional[str] = None,
        normalize: bool = True,
    ) -> None:
        """Set weights for specific vertices.

        Args:
            vertex_indices: List of vertex indices to set.
            weights: Weight values to set.
            geometry: Optional specific geometry.
            normalize: Whether to normalize weights.
        """
        target_geo = geometry or self.geometry
        if not target_geo:
            raise RuntimeError(f"No geometry connected to skinCluster '{self.name}'")

        selection_list = OpenMaya.MSelectionList()
        selection_list.add(target_geo)
        dag_path = selection_list.getDagPath(0)

        single_indexed_component = OpenMaya.MFnSingleIndexedComponent()
        vertex_component = single_indexed_component.create(
            OpenMaya.MFn.kMeshVertComponent
        )
        single_indexed_component.addElements(vertex_indices)

        skin_fn = self._get_skin_fn()
        influence_indices = self._get_influence_indices(skin_fn)

        if isinstance(weights, SkinWeights):
            weight_array = OpenMaya.MDoubleArray(weights.weights)
        else:
            weight_array = OpenMaya.MDoubleArray(weights)

        skin_fn.setWeights(
            dag_path, vertex_component, influence_indices, weight_array, normalize
        )

    def get_blend_weights(self, geometry: Optional[str] = None) -> List[float]:
        """Get dual quaternion blend weights.

        Args:
            geometry: Optional specific geometry.

        Returns:
            List of blend weights (one per vertex).
        """
        dag_path, vertex_component, skin_fn = self._get_geometry_dag_and_components(
            geometry
        )
        return list(skin_fn.getBlendWeights(dag_path, vertex_component))

    def set_blend_weights(
        self,
        weights: List[float],
        geometry: Optional[str] = None,
    ) -> None:
        """Set dual quaternion blend weights.

        Args:
            weights: Blend weight values (one per vertex).
            geometry: Optional specific geometry.
        """
        dag_path, vertex_component, skin_fn = self._get_geometry_dag_and_components(
            geometry
        )
        weight_array = OpenMaya.MDoubleArray(weights)
        skin_fn.setBlendWeights(dag_path, vertex_component, weight_array)

    def prune_weights(self, threshold: float = 0.001) -> None:
        """Remove weight values below the threshold.

        Args:
            threshold: Weights below this value are set to zero.
        """
        cmds.skinPercent(self.name, self.geometry, pruneWeights=threshold)

    def copy_weights(
        self,
        target: "SkinCluster",
        surface_association: str = "closestPoint",
        influence_association: str = "closestJoint",
        **kwargs,
    ) -> None:
        """Copy weights from this skinCluster to another.

        Args:
            target: Target SkinCluster to copy weights to.
            surface_association: How to match surface points.
            influence_association: How to match influences.
            **kwargs: Additional arguments for copySkinWeights.
        """
        cmds.copySkinWeights(
            sourceSkin=self.name,
            destinationSkin=target.name,
            surfaceAssociation=surface_association,
            influenceAssociation=influence_association,
            noMirror=True,
            **kwargs,
        )

    def mirror_weights(
        self,
        mirror_mode: str = "YZ",
        mirror_inverse: bool = False,
        **kwargs,
    ) -> None:
        """Mirror skin weights across an axis.

        Args:
            mirror_mode: Mirror plane ('YZ', 'XZ', 'XY').
            mirror_inverse: Invert the mirror direction.
            **kwargs: Additional arguments for copySkinWeights.
        """
        cmds.copySkinWeights(
            sourceSkin=self.name,
            destinationSkin=self.name,
            mirrorMode=mirror_mode,
            mirrorInverse=mirror_inverse,
            surfaceAssociation="closestPoint",
            influenceAssociation=["label", "closestJoint"],
            **kwargs,
        )

    def reset_weights(self, to_bind_pose: bool = True) -> None:
        """Reset weights to default (bind pose) state.

        Args:
            to_bind_pose: If True, go to bind pose before resetting.
        """
        if to_bind_pose:
            cmds.skinCluster(self.name, edit=True, moveJointsMode=True)
            cmds.dagPose(self.influences, restore=True, g=True, bindPose=True)
            cmds.skinCluster(self.name, edit=True, moveJointsMode=False)

        cmds.skinPercent(
            self.name,
            f"{self.geometry}.vtx[*]",
            normalize=True,
            resetToDefault=True,
        )

    def save_weights(self, file_path, **kwargs):
        """Export skinCluster weights to a file.

        Args:
            file_path (str or Path Object): The file path to export weights to.
            **kwargs: Additional arguments for deformerWeights command.
        """
        file_dir, file_name = self.__split_path(file_path, validate=True)

        base_geo = self.geometry
        if base_geo and cmds.objectType(base_geo) == "mesh":
            vertex_connections = True
        else:
            vertex_connections = False

        default_kwargs = {
            "defaultValue": -1.0,
            "vertexConnections": vertex_connections,
            "attribute": ["envelope", "skinningMethod", "normalizeWeights"],
        }
        default_kwargs.update(kwargs)

        cmds.deformerWeights(
            file_name, export=True, deformer=self.name, path=file_dir, **default_kwargs
        )

    def load_weights(self, file_path, method="index", **kwargs):
        """Import skinCluster weights from a file.

        Args:
            file_path (str or Path Object): The file path to import weights from.
            method (str): The method to use for importing weights.
                Valid values are: "index", "nearest", "barycentric", "bilinear", "over"
            **kwargs: Additional arguments for deformerWeights command.
        """
        file_dir, file_name = self.__split_path(file_path, validate=False)

        default_kwargs = {
            "ignoreName": True,
            "attribute": ["envelope", "skinningMethod", "normalizeWeights"],
        }
        default_kwargs.update(kwargs)

        cmds.deformerWeights(
            file_name,
            path=file_dir,
            im=True,
            deformer=self.name,
            method=method,
            **default_kwargs,
        )

    def unbind(self, delete_history: bool = True) -> None:
        """Unbind the skinCluster from geometry.

        Args:
            delete_history: If True, delete history after unbinding.
        """
        geometry = self.geometry
        if geometry:
            cmds.skinCluster(self.name, edit=True, unbind=True)
            if delete_history:
                cmds.delete(geometry, constructionHistory=True)

    def rebind(self) -> None:
        """Rebind geometry to the skinCluster.

        This recalculates the bind matrices by entering moveJointsMode,
        restoring the bind pose, and exiting moveJointsMode.
        """
        cmds.skinCluster(self.name, edit=True, moveJointsMode=True)
        self.go_to_bind_pose()
        cmds.skinCluster(self.name, edit=True, moveJointsMode=False)

    def bind_pose(self) -> Optional[str]:
        """Get the bind pose node associated with this skinCluster.

        Returns:
            Name of the bindPose node, or None if not found.
        """
        connections = cmds.listConnections(
            f"{self.name}.bindPose", source=True, destination=False, type="dagPose"
        )
        return connections[0] if connections else None

    def go_to_bind_pose(self) -> None:
        """Move the skeleton to its bind pose."""
        bind_pose_node = self.bind_pose()
        if bind_pose_node:
            cmds.dagPose(bind_pose_node, restore=True, g=True)

    # === Dunder Methods ===

    def __len__(self) -> int:
        """Return the number of influences."""
        return self.influence_count

    def __contains__(self, influence: str) -> bool:
        """Check if an influence is part of this skinCluster."""
        return influence in self.influences

    def __iter__(self):
        """Iterate over influence names."""
        return iter(self.influences)
