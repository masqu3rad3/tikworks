"""Blendshape type for Maya integration."""

from __future__ import annotations

from array import array
from functools import partial
from typing import Optional, Union

from maya import cmds

from ..core.apicommon import create_node_with_dg_modifier
from ..core.deformer import Deformer, DeformerWeights
from ..core.registry import register, resolve
from ..core.scene import proxy_wrapper


@register("blendShape")
class BlendShape(Deformer):
    """Blendshape node type for Maya."""

    tm_blendshape = partial(proxy_wrapper, "blendShape")

    @classmethod
    def create(cls, geometry=None, targets=None, name=None, **kwargs) -> "BlendShape":
        """Create Blendshape node type for Maya.

        Args:
            geometry (str, optional): The geometry that will be applied to.
            targets (list, optional): List of target geometry objects.
            name (str, optional): Optional name for the blendShape node.

        Returns:
            BlendShape: The created BlendShape instance.
        """
        # if both geometry and influences are None, create a simple skinCluster Node
        if geometry is None and targets is None:
            node_name = create_node_with_dg_modifier("blendShape", name=name)
            return cls(node_name)

        # if only one of the influences or geometry is None, raise an error
        if geometry is None:
            raise ValueError(
                "To create blendshape with connections, geometry must be provided.\n"
                "Alternatively, call SkinCluster.create() without geometry and targets to create an unbound skinCluster node."
            )

        default_kwargs = {
            "frontOfChain": True,
            "topologyCheck": True,
        }
        default_kwargs.update(kwargs)

        if name:
            default_kwargs["name"] = name

        result = cls.tm_blendshape(targets, geometry, **default_kwargs)
        bs_node = result[0] if isinstance(result, (list, tuple)) else result
        return bs_node

    @property
    def influences(self):
        """Return the list of blendshape influences."""
        _influences = cmds.aliasAttr(self.name, query=True)
        if _influences:
            return _influences[::2]
        return None

    @property
    def base_shapes(self):
        """Return the list of base shapes as list of objects."""
        shapes = cmds.blendShape(self.name, query=True, geometry=True)
        if not shapes:
            return []
        shape_type = cmds.objectType(shapes[0])
        return [resolve(shape, class_name=shape_type) for shape in shapes]

    @property
    def weight_count(self):
        """Return the number of weight targets."""
        return cmds.blendShape(self.name, query=True, weightCount=True)

    @property
    def next_target(self) -> int:
        """Returns the next free index from a multi index attribute"""
        return cmds.blendShape(self.name, query=True, weightCount=True)

    # --------------------------------------------------------------------------
    # Private Helpers
    # --------------------------------------------------------------------------

    def _get_geometry_info(self, geometry=None):
        """
        Resolves the geometry index and vertex count.
        """
        connected_geos = cmds.blendShape(self.name, query=True, geometry=True) or []

        if not connected_geos:
            raise RuntimeError(f"No geometry connected to {self.name}")

        if geometry:
            geometry_obj = resolve(geometry)
            target_geo_long = geometry_obj.long_name
            long_connected = cmds.ls(connected_geos, long=True)

            try:
                geom_index = long_connected.index(target_geo_long)
            except ValueError:
                raise ValueError(
                    f"Geometry '{geometry}' is not connected to blendShape '{self.name}'"
                )
        else:
            target_geo_long = cmds.ls(connected_geos[0], long=True)[0]
            geom_index = 0

        # Generic component count
        vert_count = cmds.getAttr(f"{target_geo_long}.controlPoints", size=True)

        return geom_index, vert_count, target_geo_long

    def _get_weight_plug(self, geom_index, target_id=None):
        """
        Returns the MPlug for weights.
        """
        try:
            if target_id is None:
                # This corresponds to the top-level node weight in Paint Tool
                try:  # Maya 2025+
                    return self[f"weightList[{geom_index}]"]["weights"].mplug
                except RuntimeError:  # Older Maya versions
                    return self[f"inputTarget[{geom_index}]"]["baseWeights"].mplug
            else:
                # path: inputTarget[geom_index].inputTargetGroup[target_id].targetWeights
                return self[f"inputTarget[{geom_index}]"][
                    f"inputTargetGroup[{target_id}]"
                ]["targetWeights"].mplug
        except Exception:  # noqa: BLE001 - any missing plug means "no weights"
            return None

    def _read_weights(self, plug, vert_count):
        """Reads sparse weights from plug, filling defaults with 1.0."""
        if plug is None:
            return array("d", [1.0]) * vert_count

        indices = plug.getExistingArrayAttributeIndices()
        weights = array("d", [1.0]) * vert_count

        for physical_idx, logical_idx in enumerate(indices):
            if logical_idx < vert_count:
                element = plug.elementByPhysicalIndex(physical_idx)
                try:
                    value = element.asDouble()
                except Exception:  # noqa: BLE001 - float-typed weight plugs
                    value = element.asFloat()
                weights[logical_idx] = float(value)

        return weights

    def _write_weights(self, plug, weights):
        """Writes dense weights list to plug via API (Fast, No Undo)."""
        if plug is None:
            raise RuntimeError("Cannot access weight plug for writing.")

        for idx, weight_val in enumerate(weights):
            element_plug = plug.elementByLogicalIndex(idx)
            element_plug.setFloat(weight_val)

    # --------------------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------------------

    def add_target(self, target_geometry, name=None, weight=1.0, **kwargs):
        """Add a new target shape to the blendshape.

        Args:
            geometry: The geometry to add as a target.
            name: Optional name for the target.
            weight: Initial weight value for the target.
        Returns:
            int: The index of the newly added target.
        """
        base_shapes = self.base_shapes
        if not base_shapes:
            raise RuntimeError(f"No base shapes connected to blendShape '{self.name}'")
        connected_mesh = base_shapes[0].long_name
        idx = self.next_target
        cmds.blendShape(
            self.name,
            edit=True,
            target=(connected_mesh, idx, target_geometry, 1.0),
            weight=[idx, weight],
            inBetween=False,
            **kwargs,
        )

        if name:
            cmds.aliasAttr(f"{name}", f"{self.name}.w[{idx}]")

        return idx

    def add_inbetween(self, target, target_geometry, weight=0.5, **kwargs):
        """Add an in-between target shape to an existing target.

        Args:
            target: The index or name of the target to add the in-between to.
            target_geometry: The geometry to add as the in-between target.
            weight: The weight value at which the in-between is active.
        """
        if isinstance(target, str):
            target_id = self.index_by_name(target)
        elif isinstance(target, int):
            target_id = target
        else:
            raise TypeError("Target must be an integer index or string name.")

        base_shapes = self.base_shapes
        if not base_shapes:
            raise RuntimeError(f"No base shapes connected to blendShape '{self.name}'")
        connected_mesh = base_shapes[0].long_name

        cmds.blendShape(
            self.name,
            edit=True,
            target=(connected_mesh, target_id, target_geometry, weight),
            inBetween=True,
            **kwargs,
        )

    def get_weights(self, geometry: Optional[str] = None) -> DeformerWeights:
        """
        Get all weights for all target shapes as a list of lists.
        Each sublist corresponds to a target shape.
        Args:
            geometry: The geometry to query weights for.

        Returns:
            DeformerWeights: An object containing all weights.
        """
        geom_index, vertex_count, _ = self._get_geometry_info(geometry)
        target_count = self.weight_count

        if target_count == 0:
            return DeformerWeights(
                [],
                channel_count=0,
                element_count=vertex_count,
                channel_names=[],
            )

        channel_names = self.influences or []
        if len(channel_names) != target_count:
            channel_names = []

        target_weights_by_target = [
            self._read_weights(
                self._get_weight_plug(geom_index, target_id=target_index), vertex_count
            )
            for target_index in range(target_count)
        ]

        flat_weights = array("d", [0.0]) * (vertex_count * target_count)
        for vertex_index in range(vertex_count):
            base_offset = vertex_index * target_count
            for target_index in range(target_count):
                flat_weights[base_offset + target_index] = float(
                    target_weights_by_target[target_index][vertex_index]
                )

        return DeformerWeights(
            flat_weights,
            channel_count=target_count,
            element_count=vertex_count,
            channel_names=channel_names,
        )

    def set_weights(
        self,
        weights: Union[DeformerWeights, list[float]],
        geometry: Optional[str] = None,
    ) -> None:
        """Set all weights for the geometry.

        Args:
            weights: DeformerWeights or list of weight values.
            geometry: Optional specific geometry to set.
            normalize: Whether to normalize weights after setting.
        """
        geom_index, vertex_count, geo_name = self._get_geometry_info(geometry)
        target_count = self.weight_count

        if target_count == 0:
            if isinstance(weights, DeformerWeights) and len(weights) == 0:
                return
            if not isinstance(weights, DeformerWeights) and len(weights) == 0:
                return
            raise ValueError(
                f"BlendShape '{self.name}' has no targets but weights were provided."
            )

        if isinstance(weights, DeformerWeights):
            if weights.channel_count != target_count:
                raise ValueError(
                    f"Channel count {weights.channel_count} != target count {target_count}"
                )
            if weights.element_count != vertex_count:
                raise ValueError(
                    f"Element count {weights.element_count} != {geo_name} count {vertex_count}"
                )
            flat_weights = weights.weights
        else:
            expected_count = vertex_count * target_count
            if len(weights) != expected_count:
                raise ValueError(
                    f"Weight length {len(weights)} != {geo_name} expected {expected_count}"
                )
            flat_weights = weights

        for target_index in range(target_count):
            target_weights = [
                flat_weights[vertex_index * target_count + target_index]
                for vertex_index in range(vertex_count)
            ]
            plug = self._get_weight_plug(geom_index, target_id=target_index)
            self._write_weights(plug, target_weights)

    # python
    def get_influence_weights(self, target, geometry=None) -> DeformerWeights:
        """
        Get weights for a specific target shape and return a DeformerWeights container.

        Args:
            target: The index or name of the target.
            geometry: Optional geometry to query.

        Returns:
            DeformerWeights: channel_count==1, element_count==vertex_count.
        """
        if isinstance(target, str):
            target_id = self.index_by_name(target)
            target_name = target
        elif isinstance(target, int):
            target_id = target
            try:
                target_name = self.name_by_index(target_id)
            except ValueError:
                target_name = None
        else:
            raise TypeError("Target must be an integer index or string name.")

        idx, vertex_count, _ = self._get_geometry_info(geometry)
        plug = self._get_weight_plug(idx, target_id=target_id)
        weights_list = self._read_weights(plug, vertex_count)

        channel_names = [target_name] if target_name else []
        return DeformerWeights(
            weights_list,
            channel_count=1,
            element_count=vertex_count,
            channel_names=channel_names,
        )

    def set_influence_weights(self, target, weights, geometry=None):
        """Set weights for a specific target shape.
        Args:
            target: The index or name of the target.
            weights: DeformerWeights or list of floats.
        """
        if isinstance(target, str):
            target_id = self.index_by_name(target)
        elif isinstance(target, int):
            target_id = target
        else:
            raise TypeError("Target must be an integer index or string name.")

        idx, count, geo_name = self._get_geometry_info(geometry)

        # Normalize incoming representation to a dense list per-vertex
        if isinstance(weights, DeformerWeights):
            if weights.channel_count != 1:
                raise ValueError(
                    f"Expected DeformerWeights.channel_count==1 for a single target, got {weights.channel_count}"
                )
            if weights.element_count != count:
                raise ValueError(
                    f"Element count {weights.element_count} != {geo_name} count {count}"
                )
            target_weights = list(weights.weights)
        else:
            if len(weights) != count:
                raise ValueError(
                    f"Weight length {len(weights)} != {geo_name} count {count}"
                )
            target_weights = list(weights)

        plug = self._get_weight_plug(idx, target_id=target_id)
        self._write_weights(plug, target_weights)

    def get_base_weights(self, geometry=None):
        """
        Get the global deformer weights.
        (This corresponds to the BlendShape node entry in the Paint Weights tool).
        """
        idx, count, _ = self._get_geometry_info(geometry)
        plug = self._get_weight_plug(
            idx, target_id=None
        )  # target_id None implies Base/Deformer
        weights_list = self._read_weights(plug, count)
        return DeformerWeights(
            weights_list,
            channel_count=1,
            element_count=count,
            channel_names=["baseLayer"],
        )

    def set_base_weights(self, weights, geometry=None):
        """
        Set the global deformer weights.
        """
        idx, count, geo_name = self._get_geometry_info(geometry)

        # Normalize incoming representation to a dense list per-vertex
        if isinstance(weights, DeformerWeights):
            if weights.channel_count != 1:
                raise ValueError(
                    f"Expected DeformerWeights.channel_count==1 for a single target, got {weights.channel_count}"
                )
            if weights.element_count != count:
                raise ValueError(
                    f"Element count {weights.element_count} != {geo_name} count {count}"
                )
            target_weights = weights.to_m_double_array()
        else:
            if len(weights) != count:
                raise ValueError(
                    f"Weight length {len(weights)} != {geo_name} count {count}"
                )
            target_weights = list(weights)

        plug = self._get_weight_plug(
            idx, target_id=None
        )  # target_id None implies Base/Deformer
        self._write_weights(plug, target_weights)

    def index_by_name(self, target_name):
        """Get the index of a target by its name."""
        for index in range(self.weight_count):
            if cmds.aliasAttr(self[f"w[{index}]"].path, query=True) == target_name:
                return index
        raise ValueError(
            f"Target name '{target_name}' not found in blendShape '{self.name}'"
        )

    def name_by_index(self, target_index):
        """Get the name of a target by its index."""
        target_name = cmds.aliasAttr(self[f"w[{target_index}]"].path, query=True)
        if target_name is None:
            raise ValueError(
                f"Target index '{target_index}' not found in blendShape '{self.name}'"
            )
        return target_name

    def save_weights(self, file_path, **kwargs):
        """Export blendshape weights to a file.

        Args:
            file_path (str or Path Object): The file path to export weights to.
        """

        # the default vertex connections are only True if the base mesh is a mesh.
        base_shapes = self.base_shapes
        if not base_shapes or base_shapes[0].type != "mesh":
            vertex_connections = False
        else:
            vertex_connections = True

        default_kwargs = {
            "defaultValue": -1.0,  # export all weights explicitly
            "vertexConnections": vertex_connections,
            "attribute": ["origin", "envelope"],
        }
        # update the default kwargs with any user-provided kwargs
        default_kwargs.update(kwargs)
        self._save_deformer_weights(file_path, **default_kwargs)

    def load_weights(self, file_path, method="index", **kwargs):
        """Import blendshape weights from a file.

        Args:
            file_path (str or Path Object): The file path to import weights from.
            method (str): The method to use for importing weights.
                Valid values are: "index", "nearest", "barycentric", "bilinear" and "over"
        """
        default_kwargs = {"ignoreName": True, "attribute": ["origin", "envelope"]}
        # update the default kwargs with any user-provided kwargs
        default_kwargs.update(kwargs)

        self._load_deformer_weights(file_path, method=method, **default_kwargs)
