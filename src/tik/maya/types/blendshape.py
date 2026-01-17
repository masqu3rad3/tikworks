"""Blendshape type for Maya integration."""
from pathlib import Path

from maya import cmds
from maya import mel

from ..core.node import Node
from ..core.registry import register, resolve

@register("blendShape")
class BlendShape(Node):
    """Blendshape node type for Maya."""

    @classmethod
    def create(cls, **kwargs):
        """Create Blendshape node type for Maya."""
        blendshape = cmds.createNode("blendShape", **kwargs)
        return cls(blendshape)

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

        geom_index = 0
        target_geo_long = ""

        if geometry:
            geometry_obj = resolve(geometry)
            target_geo_long = geometry_obj.long_name
            long_connected = cmds.ls(connected_geos, long=True)

            try:
                geom_index = long_connected.index(target_geo_long)
            except ValueError:
                raise ValueError(
                    f"Geometry '{geometry}' is not connected to blendShape '{self.name}'")
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
                # --- FIX: Use weightList for Deformer (Global) Weights ---
                # path: weightList[geom_index].weights
                # This corresponds to the top-level node weight in Paint Tool
                return self[f"weightList[{geom_index}]"]["weights"].as_api_plug()
            else:
                # --- Target Weights ---
                # path: inputTarget[geom_index].inputTargetGroup[target_id].targetWeights
                return self[f"inputTarget[{geom_index}]"][f"inputTargetGroup[{target_id}]"]["targetWeights"].as_api_plug()
        except Exception:
            return None

    def _read_weights(self, plug, vert_count):
        """Reads sparse weights from plug, filling defaults with 1.0."""
        if plug is None:
            return [1.0] * vert_count

        indices = plug.getExistingArrayAttributeIndices()
        weights = [1.0] * vert_count

        for p_idx, logical_idx in enumerate(indices):
            if logical_idx < vert_count:
                weights[logical_idx] = plug.elementByPhysicalIndex(p_idx).asFloat()

        return weights

    def _write_weights(self, plug, weights):
        """Writes dense weights list to plug via API (Fast, No Undo)."""
        if plug is None:
            raise RuntimeError("Cannot access weight plug for writing.")

        for i, weight_val in enumerate(weights):
            element_plug = plug.elementByLogicalIndex(i)
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
            **kwargs
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
            **kwargs
        )


    def get_target_weights(self, target, geometry=None):
        """
        Get weights for a specific target shape (e.g. 'pCube2').
        Args:
            target: The index or name of the target.
        """
        if isinstance(target, str):
            target_id = self.index_by_name(target)
        elif isinstance(target, int):
            target_id = target
        else:
            raise TypeError("Target must be an integer index or string name.")
        idx, count, _ = self._get_geometry_info(geometry)
        plug = self._get_weight_plug(idx, target_id=target_id)
        return self._read_weights(plug, count)

    def set_target_weights(self, target, weights, geometry=None):
        """Set weights for a specific target shape.
        Args:
            target: The index or name of the target.
        """
        if isinstance(target, str):
            target_id = self.index_by_name(target)
        elif isinstance(target, int):
            target_id = target
        else:
            raise TypeError("Target must be an integer index or string name.")
        
        idx, count, geo_name = self._get_geometry_info(geometry)

        if len(weights) != count:
            raise ValueError(f"Weight length {len(weights)} != {geo_name} count {count}")

        plug = self._get_weight_plug(idx, target_id=target_id)
        self._write_weights(plug, weights)

    def get_weights(self, geometry=None):
        """
        Get the global deformer weights.
        (This corresponds to the BlendShape node entry in the Paint Weights tool).
        """
        idx, count, _ = self._get_geometry_info(geometry)
        plug = self._get_weight_plug(idx, target_id=None) # target_id None implies Base/Deformer
        return self._read_weights(plug, count)

    def set_weights(self, weights, geometry=None):
        """
        Set the global deformer weights.
        """
        idx, count, geo_name = self._get_geometry_info(geometry)

        if len(weights) != count:
            raise ValueError(f"Weight length {len(weights)} != {geo_name} count {count}")

        plug = self._get_weight_plug(idx, target_id=None) # target_id None implies Base/Deformer
        self._write_weights(plug, weights)

    def index_by_name(self, target_name):
        """Get the index of a target by its name."""
        for index in range(self.weight_count):
            if cmds.aliasAttr(self[f"w[{index}]"].path, query=True) == target_name:
                return index
        raise ValueError(f"Target name '{target_name}' not found in blendShape '{self.name}'")

    def name_by_index(self, target_index):
        """Get the name of a target by its index."""
        target_name = cmds.aliasAttr(self[f"w[{target_index}]"].path, query=True)
        if target_name is None:
            raise ValueError(f"Target index '{target_index}' not found in blendShape '{self.name}'")
        return target_name

    def __split_path(self, file_path, validate=False):
        """Validate and split a file path into directory and filename."""
        file_path = Path(file_path)
        if validate:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        file_name = file_path.name
        file_dir = file_path.parent.as_posix()
        return file_dir, file_name

    def save_weights(self, file_path, **kwargs):
        """Export blendshape weights to a file.

        Args:
            file_path (str or Path Object): The file path to export weights to.
        """
        file_dir, file_name = self.__split_path(file_path, validate=True)

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

        cmds.deformerWeights(
            file_name,
            export=True,
            deformer=self.name,
            path=file_dir,
            **default_kwargs
        )


    def load_weights(self, file_path, method="index", **kwargs):
        """Import blendshape weights from a file.

        Args:
            file_path (str or Path Object): The file path to import weights from.
            method (str): The method to use for importing weights.
                Valid values are: "index", "nearest", "barycentric", "bilinear" and "over"
        """
        file_dir, file_name = self.__split_path(file_path, validate=False)

        default_kwargs = {
            "ignoreName": True,
            "attribute": ["origin", "envelope"]
        }
        # update the default kwargs with any user-provided kwargs
        default_kwargs.update(kwargs)

        cmds.deformerWeights(
            file_name,
            path=file_dir,
            im=True,
            deformer=self.name,
            method=method,
            **default_kwargs
        )
