"""Blendshape type for Maya integration."""

from maya import cmds
from maya.api import OpenMaya

from ..core.node import Node
# from .mesh import Mesh
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
        shape_type = cmds.objectType(shapes[0]) # assuming all shapes are of the same type
        return [resolve(shape, class_name=shape_type) for shape in shapes]

    def get_target_weights(self, target_id, geometry=None):
        """
        Returns the weights of a given target index from a blendShape node.
        Generic support for Meshes, Nurbs Curves, Nurbs Surfaces, and Lattices.

        Args:
            self (str): Name of the blendShape node.
            target_id (int): The index of the target shape (weight index).
            geometry (str, optional): The specific geometry to query.
                                      If None, defaults to the first connected geometry.

        Returns:
            list: Flat list of float weights.
        """

        # Get all geometries connected to this blendshape
        # The order of this list corresponds to the inputTarget index
        connected_geos = cmds.blendShape(self.name, query=True,
                                         geometry=True) or []

        if not self.base_shapes:
            cmds.warning(f"No geometry connected to {self}")
            return []

        target_geo = None
        geom_index = 0

        if geometry:
            geometry = resolve(geometry) # ensure we have the correct wrapped object
            long_geo_input = geometry.long_name  # ensure we have the long name
            long_connected = cmds.ls(connected_geos, long=True)

            try:
                geom_index = long_connected.index(long_geo_input)
                target_geo = geometry
            except ValueError:
                raise ValueError(
                    f"Geometry '{geometry}' is not connected to blendShape '{self}'")
        else:
            # Default to the first one (standard behavior for single-shape setups)
            target_geo = connected_geos[0]
            geom_index = 0

        # Generic component count (works for mesh, curve, surface, lattice)
        vert_count = cmds.getAttr(f"{target_geo}.controlPoints", size=True)

        try:
            plug = self[f"inputTarget[{geom_index}]"][f"inputTargetGroup[{target_id}]"]["targetWeights"].as_api_plug()


        except RuntimeError:
            # If the plug path is invalid (e.g. target doesn't exist), return defaults
            return [1.0] * vert_count

        # API 2.0: Returns an MIntArray of logical indices directly
        # Note: If no weights are painted (all 1.0), this might be empty.
        indices = plug.getExistingArrayAttributeIndices()

        # Initialize full weight list with default 1.0
        weights = [1.0] * vert_count

        # API 2.0 MIntArray is iterable.
        # 'p_idx' is the physical index (0, 1, 2...)
        # 'logical_idx' is the actual vertex ID (3, 10, 50...)
        for p_idx, logical_idx in enumerate(indices):

            if logical_idx < vert_count:
                # elementByPhysicalIndex is faster for iteration than logical lookup
                weights[logical_idx] = plug.elementByPhysicalIndex(p_idx).asFloat()

        return weights

    def set_target_weights(self, target_id, weights, geometry=None):
        """
        Sets the weights for a given target index on a blendShape node.
        Generic support for Meshes, Nurbs Curves, Nurbs Surfaces, and Lattices.

        Args:
            target_id (int): The index of the target shape (weight index).
            weights (list): Flat list of float weights. Must match component count.
            geometry (str/Node, optional): The specific geometry to apply to.
                                           If None, defaults to the first connected geometry.
        """
        # 1. Resolve Geometry and Indices
        connected_geos = cmds.blendShape(self.name, query=True,
                                         geometry=True) or []

        if not connected_geos:
            cmds.warning(f"No geometry connected to {self}")
            return

        target_geo = None
        geom_index = 0

        if geometry:
            # Ensure we are working with the wrapped object to get .long_name
            geometry_obj = resolve(geometry)
            long_geo_input = geometry_obj.long_name
            long_connected = cmds.ls(connected_geos, long=True)

            try:
                geom_index = long_connected.index(long_geo_input)
                # We need the string name for cmds.getAttr later
                target_geo = geometry_obj.name
            except ValueError:
                raise ValueError(
                    f"Geometry '{geometry}' is not connected to blendShape '{self}'")
        else:
            target_geo = connected_geos[0]
            geom_index = 0

        # Validate Component Count
        # Using controlPoints allows this to work for meshes, curves, and lattices generically
        vert_count = cmds.getAttr(f"{target_geo}.controlPoints", size=True)

        if len(weights) != vert_count:
            raise ValueError(
                f"Weight list length ({len(weights)}) does not match "
                f"component count of {target_geo} ({vert_count})"
            )

        # Get the Plug via API 2.0
        # Accessing: inputTarget[geom_index].inputTargetGroup[target_id].targetWeights
        try:
            plug = self[f"inputTarget[{geom_index}]"][
                f"inputTargetGroup[{target_id}]"][
                "targetWeights"].as_api_plug()
        except Exception as e:
            raise RuntimeError(
                f"Could not access plug for target {target_id}: {e}")

        # We iterate the input list (logical indices) and set the values on the MPlug.
        for idx, weight_val in enumerate(weights):
            # We use elementByLogicalIndex because we are writing to specific vertex IDs (0, 1, 2...)
            # If the element doesn't exist yet, Maya creates it here.
            element_plug = plug.elementByLogicalIndex(idx)
            element_plug.setFloat(weight_val)