"""Mesh node type wrapper."""

from maya import cmds
from maya.api import OpenMaya

from ..core.shapenode import ShapeNode
from ..core.registry import register


@register("mesh")
class Mesh(ShapeNode):
    """Wrapper for mesh nodes."""

    valid_primitives = {
        "polyCube",
        "polySphere",
        "polyPlane",
        "polyCylinder",
        "polyCone",
        "polyTorus",
    }
    valid_commands = {"mesh"}

    @classmethod
    def create(cls, cmd, **kwargs):
        """Create a mesh or polygon primitive.

        Args:
            cmd (str): The Maya command to create the mesh (e.g. 'polySphere').
            **kwargs: Additional keyword arguments to pass to the command.
        """
        if cmd in cls.valid_primitives:
            result = getattr(cmds, cmd)(**kwargs)
            if isinstance(result, (list, tuple)):
                result = result[0]
        elif cmd in cls.valid_commands:
            result = cmds.createNode(cmd, **kwargs)
        else:
            raise ValueError(
                f"Command '{cmd}' is not valid for creating a Mesh. Valid "
                f"commands: {cls.valid_primitives.union(cls.valid_commands)}"
            )
        return Mesh(result)

    def vertices(self, space="world"):
        """Return all vertex positions.

        Args:
            space : str, optional
                Coordinate space to return the vertices in.
                Accepted values: "world", "object", "transform".
                Default is "world".

        Returns:
            OpenMaya.MPointArray
                Array of vertex positions in the requested space.
        """
        # Map simple string options to MSpace enums
        _space_map = {
            "world": OpenMaya.MSpace.kWorld,
            "object": OpenMaya.MSpace.kObject,
            "transform": OpenMaya.MSpace.kTransform,
        }

        if space not in _space_map:
            raise ValueError(
                f"Invalid space '{space}'. Must be one of: "
                f"{', '.join(_space_map.keys())}"
            )

        selection_ls = OpenMaya.MSelectionList()
        selection_ls.add(self.name)
        dag_path = selection_ls.getDagPath(0)

        mfn_mesh = OpenMaya.MFnMesh(dag_path)
        return mfn_mesh.getPoints(_space_map[space])

    def vertices_in_radius(self, point_coordinates, radius=0.2):
        """Return vertex indices within a radius from a point in space.

        Args:
            point (OpenMaya.MPoint): The center point to measure from.
            radius (float, optional): The radius distance. Defaults to 0.2.
        Returns:
            list: List of vertex indices within the radius.
        """
        # point_node = self.resolve_node(point_name_or_node)
        compare_point = OpenMaya.MPoint(point_coordinates)

        vertex_ids = []
        for vertex_id, vertex in enumerate(self.vertices()):
            distance = (vertex - compare_point).length()
            if distance < radius:
                vertex_ids.append(vertex_id)

        return vertex_ids

    def unlock_normals(self, soften=False):
        """Unlock the normals of the specified geometry.

        Args:
            soften (bool, optional): If true, Defaults to False.
        """

        # Retrieve the MFnMesh api object.
        selection_list = OpenMaya.MSelectionList()
        selection_list.add(self.long_name)
        mfn_mesh = OpenMaya.MFnMesh(selection_list.getDagPath(0))
        # if its already unlocked, do not process again.
        lock_state = any(
            mfn_mesh.isNormalLocked(normal_index)
            for normal_index in range(mfn_mesh.numNormals)
        )
        if lock_state:
            mfn_mesh.unlockVertexNormals(
                OpenMaya.MIntArray(range(mfn_mesh.numVertices))
            )
        if soften:
            edge_ids = OpenMaya.MIntArray(range(mfn_mesh.numEdges))
            smooths = OpenMaya.MIntArray([True] * mfn_mesh.numEdges)
            mfn_mesh.setEdgeSmoothings(edge_ids, smooths)
            mfn_mesh.cleanupEdgeSmoothing()
            mfn_mesh.updateSurface()

    def get_vertex_colors(self, indices=None):
        """Get vertex colors.

        Args:
            indices (list[int], optional): List of vertex indices to retrieve colors for.

        Returns:
            OpenMaya.MColorArray or None: Vertex colors if they exist, else None.
        """
        # if displayColors is off, return None
        if not self["displayColors"].get():
            return None

        selection_list = OpenMaya.MSelectionList()
        selection_list.add(self.long_name)
        mfn_mesh = OpenMaya.MFnMesh(selection_list.getDagPath(0))

        # API 2.0 returns the array directly
        colors = mfn_mesh.getVertexColors()

        if len(colors) == 0:
            return None

        if indices is not None:
            filtered_colors = OpenMaya.MColorArray()
            for i in indices:
                if 0 <= i < len(colors):
                    filtered_colors.append(colors[i])
            return filtered_colors

        return colors

    def set_vertex_colors(self, color, indices=None):
        """Set vertex color for vertices.

        Args:
            color (tuple): RGB color values as a tuple of three floats (0.0 to 1.0).
            indices (list[int], optional): List of vertex indices to set color for.
        """
        if not color:
            self["displayColors"].set(False)
            return

        selection_list = OpenMaya.MSelectionList()
        selection_list.add(self.long_name)
        mfn_mesh = OpenMaya.MFnMesh(selection_list.getDagPath(0))

        if indices is None:
            indices = range(mfn_mesh.numVertices)

        colors = OpenMaya.MColorArray()
        m_color = OpenMaya.MColor(color)
        for _ in indices:
            colors.append(m_color)

        vertex_indices = OpenMaya.MIntArray(indices)
        mfn_mesh.setVertexColors(colors, vertex_indices)

        # make sure the display of vertex colors is enabled
        self["displayColors"].set(True)