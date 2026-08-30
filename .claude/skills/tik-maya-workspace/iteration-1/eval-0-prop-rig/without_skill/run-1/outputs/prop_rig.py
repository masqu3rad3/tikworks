"""Simple prop rig builder.

Builds a minimal control rig for the currently selected mesh:

    <name>_root_GRP          (root group, placed at the mesh pivot)
    └── <name>_offset_GRP    (offset group, zeroed under the root)
        └── <name>_CTRL      (circle controller, drives the mesh transform)

The mesh transform is driven via parent + scale constraints so the geometry
hierarchy is left untouched.

Usage (inside Maya, with a mesh selected):

    from tools.prop_rig import build_prop_rig
    rig = build_prop_rig()
"""

from __future__ import annotations

import logging

import tik.maya as tm
from tik.maya.core.decorators import undo
from tik.maya.roles.controller import Controller
from tik.maya.types.mesh import Mesh
from tik.maya.types.transform import Transform

LOG = logging.getLogger(__name__)

DEFAULT_COLOR = 17  # Maya index yellow
SIZE_PADDING = 1.2  # controller circle sits slightly outside the mesh bounds


def _find_selected_mesh_transform():
    """Return the transform of the first selected mesh, or None.

    Accepts either a selected mesh shape or a selected transform that has a
    mesh shape under it.
    """
    for node in tm.ls(selection=True, long=True):
        if isinstance(node, Mesh):
            return node.parent
        if isinstance(node, Transform) and any(
            isinstance(shape, Mesh) for shape in node.shapes
        ):
            return node
    return None


def _fit_controller_size(mesh_transform: Transform) -> float:
    """Derive a circle radius that encloses the mesh in the ground plane."""
    bbox = mesh_transform.bounding_box
    radius = max(bbox.width, bbox.depth) * 0.5
    if radius <= 0.0:
        return 1.0
    return radius * SIZE_PADDING


@undo
def build_prop_rig(name=None, controller_size=None, controller_color=DEFAULT_COLOR):
    """Build a simple prop rig for the currently selected mesh.

    Creates a root group snapped to the mesh pivot, an offset group under it,
    and a circle controller under the offset that drives the mesh transform
    through parent and scale constraints.

    Args:
        name (str, optional): Base name for the rig nodes. Defaults to the
            selected mesh transform's name.
        controller_size (float, optional): Radius of the circle controller.
            Defaults to a size fitted to the mesh bounding box.
        controller_color (int | tuple, optional): Controller display color
            (Maya index or RGB tuple). Defaults to yellow (17).

    Returns:
        dict: The created rig nodes:
            ``root`` (Transform), ``offset`` (Transform),
            ``controller`` (Controller), ``mesh_transform`` (Transform).

    Raises:
        RuntimeError: If no mesh (or transform with a mesh shape) is selected.
    """
    mesh_transform = _find_selected_mesh_transform()
    if mesh_transform is None:
        raise RuntimeError(
            "Select a mesh (or its transform) before building a prop rig."
        )

    name = name or mesh_transform.name

    # Root group, snapped to the mesh so the rig lives at the prop's pivot.
    root = Transform.create(name=f"{name}_root_GRP")
    root.snap_to(mesh_transform, position=True, rotation=True)

    # Offset group, created under the root with an identity local transform.
    offset = Transform.create(name=f"{name}_offset_GRP", parent=root.long_name)

    # Circle controller under the offset (also identity local transform).
    if controller_size is None:
        controller_size = _fit_controller_size(mesh_transform)
    ctrl = Controller.create(
        name=f"{name}_CTRL",
        shape="Circle",
        size=controller_size,
        color=controller_color,
        parent=offset.long_name,
    )

    # Drive the mesh transform from the controller.
    tm.parentConstraint(ctrl.node, mesh_transform, maintainOffset=True)
    tm.scaleConstraint(ctrl.node, mesh_transform, maintainOffset=True)

    ctrl.node.select()
    LOG.info("Built prop rig '%s' for mesh '%s'.", name, mesh_transform.name)

    return {
        "root": root,
        "offset": offset,
        "controller": ctrl,
        "mesh_transform": mesh_transform,
    }
