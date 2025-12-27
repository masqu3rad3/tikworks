import os
import json
import logging
from pathlib import Path
import platform
import maya.api.OpenMaya as om
from maya import cmds

from tikmaya.core.registry import resolve
from tikmaya.types.camera import Camera
from tikmaya.constructs import Panel

LOG = logging.getLogger(__name__)

CURRENT_PLATFORM = platform.system()

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

def get_home_dir():
    """Get the user home directory."""
    if CURRENT_PLATFORM == "Windows":
        home = os.getenv("USERPROFILE")
    else:
        home = os.getenv("HOME")

    if not home:
        home = os.path.expanduser("~")

    return os.path.normpath(home)


class ControlShapeLibrary:
    """
    Singleton-like manager for accessing and loading controller shape data.
    """

    _INSTANCE = None

    def __init__(self):
        self._cache = {}
        self._custom_paths = []

        # 1. Core Path
        current_dir = Path(__file__).absolute().parent
        root_dir = current_dir.parent
        self._core_path = root_dir / "data" / "control_shapes"

        # 2. User Path (Always defined)
        _user_root = get_home_dir()
        self._user_path = Path(_user_root, "TikWorks", "user_control_shapes")
        self._user_path.mkdir(parents=True, exist_ok=True)

    @property
    def user_path(self):
        return self._user_path

    @property
    def search_paths(self):
        """
        Returns the list of paths in resolution order:
        Core < User < Environment < Custom (API)
        """
        paths = [self._core_path, self._user_path]

        # Environment Paths
        env_paths_str = os.environ.get("TIKMAYA_SHAPES_PATH", "")
        if env_paths_str:
            for env_path_str in env_paths_str.split(os.pathsep):
                if not env_path_str:
                    continue
                path_obj = Path(env_path_str).expanduser().absolute()
                # Avoid duplicates while maintaining order
                if path_obj not in paths:
                    paths.append(path_obj)

        # Custom API Paths
        for custom_path in self._custom_paths:
            if custom_path not in paths:
                paths.append(custom_path)

        # Return only existing directories
        return [path for path in paths if path.exists()]

    @classmethod
    def get_instance(cls):
        if not cls._INSTANCE:
            cls._INSTANCE = cls()
        return cls._INSTANCE

    def add_path(self, path):
        """Add a custom search path (highest priority)."""
        if not path:
            return
        path_obj = Path(path).expanduser().absolute()
        if path_obj not in self._custom_paths:
            self._custom_paths.append(path_obj)
            self._cache = {}  # Invalidate cache

    def remove_path(self, path):
        """Remove a custom search path."""
        if not path:
            return
        path_obj = Path(path).expanduser().absolute()
        if path_obj in self._custom_paths:
            self._custom_paths.remove(path_obj)
            self._cache = {}  # Invalidate cache

    def refresh(self):
        """Scans all paths and populates the cache."""
        self._cache = {}
        # Iterating in order means later paths overwrite earlier ones (desired behavior)
        for path in self.search_paths:
            if not path.is_dir():
                continue

            for json_path in path.rglob("*.json"):
                rel_path = json_path.relative_to(path)
                category = rel_path.parts[0] if len(
                    rel_path.parts) > 1 else None

                self._cache[json_path.stem] = {
                    "path": json_path,
                    "category": category,
                }

    def list_shapes(self):
        if not self._cache:
            self.refresh()
        return list(self._cache.keys())

    def get_shape_data(self):
        if not self._cache:
            self.refresh()
        return self._cache

    def get_path(self, name):
        if not self._cache:
            self.refresh()
        data = self._cache.get(name)
        return data["path"] if data else None

    def load(self, name):
        """Returns the dictionary data for the shape."""
        path = self.get_path(name)
        if not path:
            LOG.warning(f"Shape '{name}' not found in library.")
            return None

        try:
            with path.open("r") as json_file:
                return json.load(json_file)
        except Exception as error:
            LOG.error(f"Failed to load shape '{name}': {error}")
            return None


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
    """Capture shape data from a node and save it to disk as JSON."""
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
        final_data = _normalize_data(final_data, all_points)

    return final_data


def save_to_disk(data, name, folder_path, category=None):
    """Save the given shape data to disk as JSON."""
    folder_path = _resolve_folder_path(folder_path, category)

    filename = f"{name}.json"
    full_path = folder_path / filename

    with full_path.open("w") as json_file:
        json.dump(data, json_file, indent=4)

    return str(full_path)

def capture_thumbnail(node_name, name, folder_path, category=None, camera_position=None):
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


def _normalize_data(data, all_points):
    """Fits the shape into a 1x1x1 unit cube centered at local 0,0,0."""
    xs = [point[0] for point in all_points]
    ys = [point[1] for point in all_points]
    zs = [point[2] for point in all_points]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)

    width = max_x - min_x
    height = max_y - min_y
    depth = max_z - min_z
    max_dim = max(width, height, depth)

    if max_dim < 0.0001:
        return data

    scale = 1.0 / max_dim

    for curve in data["curves"]:
        new_points = []
        for point in curve["point"]:
            new_points.append(
                (point[0] * scale, point[1] * scale, point[2] * scale))
        curve["point"] = new_points

    return data


def _resolve_folder_path(folder_path, category):
    if isinstance(folder_path, str):
        folder_path = Path(folder_path)
    if category:
        folder_path = folder_path / category
    folder_path.mkdir(parents=True, exist_ok=True)
    return folder_path

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