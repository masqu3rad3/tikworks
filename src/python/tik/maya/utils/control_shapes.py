"""Capturing control shapes out of a Maya scene.

The library itself is pure and lives in :mod:`tik.core.control_shapes`; it is
re-exported here so existing call sites keep working. Only the capture
utilities below need a scene.
"""

from __future__ import annotations

import logging

import maya.api.OpenMaya as om
from maya import cmds

from tik.core.control_shapes import (  # noqa: F401 - re-exported for callers
    CURRENT_PLATFORM,
    ControlShapeLibrary,
    _normalize_ratio,
    _resolve_folder_path,
    _scale_data,
    get_home_dir,
    save_to_disk,
)

from ..constructs import Panel
from ..core.registry import resolve
from ..types.camera import Camera

LOG = logging.getLogger(__name__)

CAMERA_POSITIONS = {
    "front": (0, 0, 10),
    "back": (0, 0, -10),
    "left": (-10, 0, 0),
    "right": (10, 0, 0),
    "top": (0, 10, 0),
    "bottom": (0, -10, 0),
    "iso": (10, 10, 10),
    "oneThird": (10, 5, 5),
}


# ------------------------------------------------------------------------------
# Capture Utilities
# ------------------------------------------------------------------------------


def capture_to_disk(
    node_name,
    name=None,
    folder_path=None,
    category=None,
    normalize=True,
    thumbnail=True,
):
    """Capture shape data from a Maya node and save it to disk as JSON.

    Args:
        node_name: Name of the Maya transform node to capture.
        name: Optional name for the saved shape (defaults to node name).
        folder_path: Destination folder (defaults to user library path).
        category: Optional subfolder category for organization.
        normalize: Whether to normalize the shape to unit scale (default: True).
        thumbnail: Whether to capture a thumbnail image (default: True).

    Returns:
        Path or None: Path to the saved JSON file, or None on error.
    """
    data = capture(node_name, name=name, normalize=normalize)
    if not data:
        LOG.error(f"No curve data found on node '{node_name}'.")
        return None

    if not name:
        name = node_name.split("|")[-1]

    # Default to the library's user path if no path is provided
    if not folder_path:
        folder_path = ControlShapeLibrary.get_instance().user_path

    if thumbnail:
        capture_thumbnail(node_name, name, folder_path, category=category)

    return save_to_disk(data, name, folder_path=folder_path, category=category)


def capture(node_name, name=None, normalize=True):
    """Scrape curve data from a transform."""
    node = resolve(node_name)

    shapes_data = []
    all_points = []

    # Iterate over shapes
    child_count = node.dag_path.childCount()
    for idx in range(child_count):
        child = node.dag_path.child(idx)
        if child.hasFn(om.MFn.kNurbsCurve):
            fn_curve = om.MFnNurbsCurve(child)

            # Get Points in Object Space
            points_array = fn_curve.cvPositions(om.MSpace.kObject)
            points = [(point.x, point.y, point.z) for point in points_array]
            all_points.extend(points)

            shapes_data.append(
                {
                    "point": points,
                    "knot": list(fn_curve.knots()),
                    "degree": int(fn_curve.degree),
                    "periodic": fn_curve.form == om.MFnNurbsCurve.kPeriodic,
                }
            )

    if not shapes_data:
        return None

    final_data = {"name": name or node.name, "curves": shapes_data}

    if normalize and all_points:
        ratio = _normalize_ratio(all_points)
        final_data = _scale_data(final_data, ratio)

    return final_data


def capture_thumbnail(
    node_name, name, folder_path, category=None, camera_position=None
):
    """Snapshot the thumbnail of the current viewport for the shape."""
    # Note: Camera creation is kept for potential future setup,
    # though playblast currently grabs active view.
    node = resolve(node_name).duplicate()
    node.set_color((0.996, 0.494, 0.0))  # Orange
    for shape in node.shapes:
        shape.line_width = 3
    render_globals = resolve("hardwareRenderingGlobals")
    _original_sample_state = render_globals["multiSampleEnable"].value
    _original_sample_count = render_globals["multiSampleCount"].value
    render_globals["multiSampleEnable"].value = True
    render_globals["multiSampleCount"].value = 16
    _camera = Camera.create(name="tmp_thumbnail_cam")
    _camera.set_controls("cameraAndAim")
    _camera.aim.translate = (0, 0, 0)
    _camera.lens = 300
    camera_position = camera_position or _guess_camera_view(node)
    if camera_position not in CAMERA_POSITIONS:
        raise RuntimeError(f"Unknown camera position '{camera_position}'")
    cam_pos = CAMERA_POSITIONS[camera_position]
    _camera.transform.translate = cam_pos

    panel = Panel(_camera, [200, 200], inherit=False)
    panel.overscan = True
    panel.grid = False
    panel.hud = False
    panel.joints = False
    panel.locators = False
    panel.pivots = False
    panel.polymeshes = False
    panel.selection_highlighting = False
    panel.manipulators = False
    panel.color_management_enabled = False
    panel.isolate(node)
    node.select()
    panel.fit_view()
    panel.camera.fit("overscan")
    panel.overscan = 1.1

    folder_path = _resolve_folder_path(folder_path, category)
    filename = f"{name}.png"
    file_path = str(folder_path / filename)

    frame = cmds.currentTime(query=True)
    store = cmds.getAttr("defaultRenderGlobals.imageFormat")
    cmds.setAttr("defaultRenderGlobals.imageFormat", 8)  # jpg

    cmds.playblast(
        completeFilename=file_path,
        forceOverwrite=True,
        format="image",
        width=200,
        height=200,
        showOrnaments=False,
        frame=[frame],
        viewer=False,
        editorPanelName=panel.name,
        percent=100,
    )
    cmds.setAttr("defaultRenderGlobals.imageFormat", store)

    panel.close()
    # Cleanup temp camera if needed, or leave for user to delete
    _camera.delete()
    node.delete()

    render_globals["multiSampleEnable"].value = _original_sample_state
    render_globals["multiSampleCount"].value = _original_sample_count
    return file_path


def _guess_camera_view(node_name):
    """Depending on the bounding box of the node, select the best camera view.

    Shapes that are flat from X or Y axis should use top view
    otherwise iso view.
    """
    node = resolve(node_name)
    flat_threshold = 0.01
    if node.bounding_box.height < flat_threshold:
        return "top"
    # if its the bb is almost cube shaped, use oneThird view
    if (node.bb.width + node.bb.height + node.bb.depth) / 3 - min(
        node.bb.width, node.bb.height, node.bb.depth
    ) < flat_threshold:
        return "oneThird"
    return "iso"
