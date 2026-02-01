"""SkinCluster type for Maya integration."""
from functools import partial

from typing import List, Optional, Union

from maya import cmds
from maya.api import OpenMaya
from maya.api import OpenMayaAnim

from ..core.deformer import Deformer, WeightsIO, DeformerWeights
from ..core.registry import register
from ..core.scene import proxy_wrapper
from ..core.apicommon import create_node_with_dg_modifier



@register("skinCluster")
class SkinCluster(Deformer):
    """SkinCluster node type for Maya."""
    tm_skincluster = partial(proxy_wrapper, "skinCluster")

    @classmethod
    def create(
        cls,
        geometry: str = None,
        influences: List[str] = None,
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
        # if both geometry and influences are None, create a simple skinCluster Node
        if geometry is None and influences is None:
            sc_name = create_node_with_dg_modifier("skinCluster", name=name)
            return cls(sc_name)

        # if only one of the influences or geometry is None, raise an error
        if geometry is None or influences is None:
            raise ValueError("To create skincluster with connections, geometry and influences must be provided.\n"
                             "Alternatively, call SkinCluster.create() without geometry and influences to create an unbound skinCluster node.")

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

        # skin_fn = partial(proxy_wrapper, "skinCluster")
        # result = cmds.skinCluster(influences, geometry, **default_kwargs)
        result = cls.tm_skincluster(influences, geometry, **default_kwargs)
        skin_node = result[0] if isinstance(result, (list, tuple)) else result
        return skin_node

    @classmethod
    def create_from_weights_object(cls, weights_object, **kwargs):
        """Create a skincluster from the given weights object.

        Args:
            weights_object: A WeightsIO instance containing weight data.
            **kwargs: Additional arguments passed to create().

        Returns:
            SkinCluster instance with weights applied.
        """
        geometry_name = weights_object.shapes[0].name
        influences = weights_object.influence_names
        skincluster = cls.create(geometry_name, influences, **kwargs)
        skincluster.set_weights(weights_object.to_m_array())
        return skincluster

    @classmethod
    def create_from_file(cls, file_path, **kwargs) -> "SkinCluster":
        """Create a skinCluster by importing weights from a file.

        Args:
            file_path: The file path to import weights from.
            **kwargs: Additional arguments passed to load_weights.
        """
        # instanciate the weights object.
        weights = WeightsIO.load_json(file_path)
        return cls.create_from_weights_object(weights, **kwargs)

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
        geometries = self.tm_skincluster(self.name, query=True, geometry=True)
        return geometries[0] if geometries else None

    @property
    def geometries(self) -> List[str]:
        """Return all connected geometry shape names."""
        return self.tm_skincluster(self.name, query=True, geometry=True) or []

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
        return cmds.polyEvaluate(str(geometry), vertex=True)

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
        selection_list.add(str(target_geo))
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

    def get_weights(self, geometry: Optional[str] = None) -> DeformerWeights:
        """Get all skin weights for the geometry.

        Args:
            geometry: Optional specific geometry to query.

        Returns:
            DeformerWeights container with weight data.
        """
        dag_path, vertex_component, skin_fn = self._get_geometry_dag_and_components(
            geometry
        )
        weights, _ = skin_fn.getWeights(dag_path, vertex_component)

        influence_dags = skin_fn.influenceObjects()
        influence_names = [
            OpenMaya.MFnDagNode(dag).name() for dag in influence_dags
        ]

        return DeformerWeights(
            list(weights),
            channel_count=len(influence_dags),
            element_count=self.vertex_count,
            channel_names=influence_names,
        )

    def set_weights(
        self,
        weights: Union[DeformerWeights, List[float]],
        geometry: Optional[str] = None,
        normalize: bool = True,
    ) -> None:
        """Set all skin weights for the geometry.

        Args:
            weights: DeformerWeights or list of weight values.
            geometry: Optional specific geometry to set.
            normalize: Whether to normalize weights after setting.
        """
        dag_path, vertex_component, skin_fn = self._get_geometry_dag_and_components(
            geometry
        )
        influence_indices = self._get_influence_indices(skin_fn)

        if isinstance(weights, DeformerWeights):
            weight_array = OpenMaya.MDoubleArray(weights.weights)
        else:
            weight_array = OpenMaya.MDoubleArray(weights)

        skin_fn.setWeights(
            dag_path, vertex_component, influence_indices, weight_array, normalize
        )

    def get_vertex_weights(
        self, vertex_indices: List[int], geometry: Optional[str] = None
    ) -> DeformerWeights:
        """Get weights for specific vertices.

        Args:
            vertex_indices: List of vertex indices to query.
            geometry: Optional specific geometry.

        Returns:
            DeformerWeights for the specified vertices.
        """
        target_geo = geometry or self.geometry
        if not target_geo:
            raise RuntimeError(f"No geometry connected to skinCluster '{self.name}'")

        selection_list = OpenMaya.MSelectionList()
        selection_list.add(str(target_geo))
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

        return DeformerWeights(
            list(weights),
            channel_count=len(influence_dags),
            element_count=len(vertex_indices),
            channel_names=influence_names,
        )

    def set_vertex_weights(
        self,
        vertex_indices: List[int],
        weights: Union[DeformerWeights, List[float]],
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
        selection_list.add(str(target_geo))
        dag_path = selection_list.getDagPath(0)

        single_indexed_component = OpenMaya.MFnSingleIndexedComponent()
        vertex_component = single_indexed_component.create(
            OpenMaya.MFn.kMeshVertComponent
        )
        single_indexed_component.addElements(vertex_indices)

        skin_fn = self._get_skin_fn()
        influence_indices = self._get_influence_indices(skin_fn)

        if isinstance(weights, DeformerWeights):
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
        cmds.skinPercent(self.name, str(self.geometry), pruneWeights=threshold)

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
        # file_dir, file_name = self.__split_path(file_path, validate=True)

        if self.geometry and self.geometry.type == "mesh":
            vertex_connections = True
        else:
            vertex_connections = False

        default_kwargs = {
            "defaultValue": -1.0,
            "vertexConnections": vertex_connections,
            "attribute": ["envelope", "skinningMethod", "normalizeWeights"],
        }
        default_kwargs.update(kwargs)

        self._save_deformer_weights(file_path, **default_kwargs)

        # cmds.deformerWeights(
        #     file_name, export=True, deformer=self.name, path=file_dir, **default_kwargs
        # )

    def load_weights(self, file_path, method="index", **kwargs):
        """Import skinCluster weights from a file.

        Args:
            file_path (str or Path Object): The file path to import weights from.
            method (str): The method to use for importing weights.
                Valid values are: "index", "nearest", "barycentric", "bilinear", "over"
            **kwargs: Additional arguments for deformerWeights command.
        """
        # file_dir, file_name = self.__split_path(file_path, validate=False)

        default_kwargs = {
            "ignoreName": True,
            "attribute": ["envelope", "skinningMethod", "normalizeWeights"],
        }
        default_kwargs.update(kwargs)

        self._load_deformer_weights(file_path, method=method, **default_kwargs)

        # cmds.deformerWeights(
        #     file_name,
        #     path=file_dir,
        #     im=True,
        #     deformer=self.name,
        #     method=method,
        #     **default_kwargs,
        # )

    def unbind(self, delete_history: bool = True) -> None:
        """Unbind the skinCluster from geometry.

        Args:
            delete_history: If True, delete history after unbinding.
        """
        geometry = self.geometry
        if geometry:
            cmds.skinCluster(self.name, edit=True, unbind=True)
            if delete_history:
                cmds.delete(str(geometry), constructionHistory=True)

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
