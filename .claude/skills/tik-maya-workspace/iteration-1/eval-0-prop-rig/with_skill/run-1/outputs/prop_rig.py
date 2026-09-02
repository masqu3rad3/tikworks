"""Simple prop rig builder.

Builds a minimal rig for the currently selected mesh:

- ``<name>_root_grp``   root group, placed at the mesh transform
- ``<name>_offset_grp`` offset group under the root
- ``<name>_ctrl``       circle controller under the offset group,
  driving the mesh transform (translate/rotate/scale, offset maintained)

Usage (inside Maya, with a mesh selected)::

    from tools.prop_rig import build_prop_rig
    rig = build_prop_rig()
    rig["control"].node  # the controller transform wrapper
"""

from __future__ import annotations

from typing import Optional

import tik.maya as tm
from tik.maya.core.decorators import undo
from tik.maya.roles import Controller
from tik.maya.types.transform import Transform

CONTROL_COLOR = 17  # yellow index color
CONTROL_PADDING = 1.25  # circle radius relative to the mesh's largest planar extent


def _mesh_transform(node) -> Optional[Transform]:
    """Return the transform carrying a mesh shape for `node`, or None.

    Accepts either a mesh shape or its transform (name or wrapper).
    """
    node = tm.resolve(node)
    if isinstance(node, tm.Mesh):
        return node.parent
    if isinstance(node, Transform):
        if any(shape.type == "mesh" for shape in node.shapes):
            return node
    return None


def _selected_mesh_transform() -> Transform:
    """Return the mesh transform from the current selection.

    Raises:
        RuntimeError: If nothing suitable is selected.
    """
    for node in tm.ls(selection=True, long=True):
        transform = _mesh_transform(node)
        if transform is not None:
            return transform
    raise RuntimeError(
        "Select a mesh (or its transform) before building the prop rig."
    )


def _control_size(mesh: Transform) -> float:
    """Return a circle radius that comfortably surrounds the mesh."""
    bbox = mesh.bounding_box
    extent = max(bbox.width, bbox.depth) * 0.5 * CONTROL_PADDING
    return extent if extent > 0.0 else 1.0


@undo
def build_prop_rig(
    mesh=None,
    name: Optional[str] = None,
    control_shape: str = "Circle",
    control_size: Optional[float] = None,
    control_color=CONTROL_COLOR,
) -> dict:
    """Build a simple prop rig driving a mesh transform.

    Creates a root group at the mesh's transform, an offset group under it,
    and a circle controller (under the offset group) that drives the mesh's
    transform via parent and scale constraints with maintained offset.

    Args:
        mesh: Mesh shape or transform (name or wrapper). Defaults to the
            current selection.
        name: Base name for the rig nodes. Defaults to the mesh transform's
            name.
        control_shape: Control shape library name (default: "Circle").
        control_size: Controller shape size. Defaults to a size fitted to
            the mesh's bounding box.
        control_color: Controller color (index int, RGB tuple, or None).

    Returns:
        dict: The created rig, with keys ``mesh`` (Transform), ``root``
        (Transform), ``offset`` (Transform), ``control`` (Controller), and
        ``constraints`` (list of constraint node wrappers).

    Raises:
        RuntimeError: If no mesh is given and none is selected.
        ValueError: If the given node is not a mesh.
    """
    if mesh is None:
        mesh_transform = _selected_mesh_transform()
    else:
        mesh_transform = _mesh_transform(mesh)
        if mesh_transform is None:
            raise ValueError(f"'{mesh}' is not a mesh or a mesh transform.")

    base_name = name or mesh_transform.name

    # Root group placed at the mesh transform; offset group inherits it.
    root = Transform.create(name=f"{base_name}_root_grp")
    root.snap_to(mesh_transform, position=True, rotation=True)
    offset = Transform.create(name=f"{base_name}_offset_grp", parent=root)

    control = Controller.create(
        name=f"{base_name}_ctrl",
        shape=control_shape,
        size=control_size if control_size is not None else _control_size(mesh_transform),
        color=control_color,
        parent=offset,
    )

    # Drive the mesh transform from the controller, keeping its current pose.
    constraints = [
        tm.parentConstraint(control.node, mesh_transform, maintainOffset=True)[0],
        tm.scaleConstraint(control.node, mesh_transform, maintainOffset=True)[0],
    ]

    control.node.select()
    return {
        "mesh": mesh_transform,
        "root": root,
        "offset": offset,
        "control": control,
        "constraints": constraints,
    }
