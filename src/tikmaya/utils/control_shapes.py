import os
import json
import logging
from pathlib import Path
import platform
import maya.api.OpenMaya as om

from tikmaya.core.registry import resolve

LOG = logging.getLogger(__name__)

CURRENT_PLATFORM = platform.system()

def get_home_dir():
    """Get the user home directory."""
    # expanduser does not always return the same result (in Maya it returns user/Documents).
    # This returns the true user folder for all platforms and dccs"""
    if CURRENT_PLATFORM == "Windows":
        return os.path.normpath(os.getenv("USERPROFILE"))
    return os.path.normpath(os.getenv("HOME"))

class ControlShapeLibrary:
    """
    Singleton-like manager for accessing controller shape data.
    """
    _INSTANCE = None

    def __init__(self):
        self._cache = {}
        self.search_paths = []

        # 1. Add Core Path (tikmaya/data/shapes)
        # Assumes this file is in tikmaya/utils/shapes.py
        current_dir = Path(__file__).absolute().parent
        root_dir = current_dir.parent
        core_path = root_dir / "data" / "control_shapes"
        self.register_path(core_path)

        # 2. Add User Path (Env Var Override)
        self.user_path = self.resolve_user_path()
        # if self.user_path:
        self.register_path(self.user_path)

    def resolve_user_path(self):
        user_path = os.environ.get("TIKMAYA_SHAPES_PATH")
        if user_path:
            return Path(user_path).absolute()
        else:
            _user_root = get_home_dir()
            _user_dir = Path(_user_root, "TikWorks", "user_control_shapes")
            # ensure it exists
            _user_dir.mkdir(parents=True, exist_ok=True)
            return _user_dir

    @classmethod
    def get_instance(cls):
        if not cls._INSTANCE:
            cls._INSTANCE = cls()
        return cls._INSTANCE

    def register_path(self, path):
        if not path:
            return
        path_obj = Path(path).expanduser().absolute()
        if path_obj.exists() and path_obj not in self.search_paths:
            self.search_paths.append(path_obj)

    def refresh(self):
        """Scans all paths and populates the cache. Later paths override earlier ones."""
        self._cache = {}
        # Iterate in order so last path overwrites previous keys
        for path in self.search_paths:
            if not path.is_dir():
                continue

            # get all .json files recursively
            for json_path in path.rglob("*.json"):
                self._cache[json_path.stem] = json_path

    def list_shapes(self):
        if not self._cache:
            self.refresh()
        return list(self._cache.keys())

    def get_path(self, name):
        if not self._cache:
            self.refresh()
        return self._cache.get(name)

    def load(self, name):
        """Returns the dictionary data for the shape."""
        path = self.get_path(name)
        if not path:
            LOG.warning(f"Shape '{name}' not found in library.")
            return None

        try:
            with path.open('r') as f:
                return json.load(f)
        except Exception as e:
            LOG.error(f"Failed to load shape '{name}': {e}")
            return None

    # ----------------------------------------------------------------
    # IO & CAPTURE UTILS
    # ----------------------------------------------------------------

    @staticmethod
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
                points = [(p.x, p.y, p.z) for p in points_array]
                all_points.extend(points)

                shapes_data.append({
                    "point": points,
                    "knot": list(fn_curve.knots()),
                    "degree": int(fn_curve.degree),
                    "periodic": fn_curve.form == om.MFnNurbsCurve.kPeriodic
                })

        if not shapes_data:
            return None

        final_data = {
            "name": name or node.name,
            "curves": shapes_data
        }

        if normalize and all_points:
            final_data = ControlShapeLibrary._normalize_data(final_data, all_points)

        return final_data

    @staticmethod
    def _normalize_data(data, all_points):
        """
        Fits the shape into a 1x1x1 unit cube centered at local 0,0,0.
        """
        # 1. Calculate Bounding Box
        xs = [point[0] for point in all_points]
        ys = [point[1] for point in all_points]
        zs = [point[2] for point in all_points]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)

        # 2. Determine Scale Factor (fit largest dimension to 1.0)
        width = max_x - min_x
        height = max_y - min_y
        depth = max_z - min_z
        max_dim = max(width, height, depth)

        if max_dim < 0.0001:
            return data  # Too small to normalize safely

        scale = 1.0 / max_dim

        # 3. Apply Scale to all points
        # Note: We do NOT re-center. Controllers are usually designed relative
        # to the pivot. If the user drew it offset, they probably want it offset.
        for curve in data["curves"]:
            new_points = []
            for point in curve["point"]:
                new_points.append((point[0] * scale, point[1] * scale, point[2] * scale))
            curve["point"] = new_points

        return data

    @staticmethod
    def save_to_disk(data, name, folder_path, category=None):
        if isinstance(folder_path, str):
            folder_path = Path(folder_path)
        if category:
            folder_path = folder_path / category
        folder_path.mkdir(parents=True, exist_ok=True)

        filename = f"{name}.json"
        full_path = folder_path / filename

        with full_path.open('w') as f:
            json.dump(data, f, indent=4)

        return str(full_path)

    def capture_to_disk(self, node_name, name=None, folder_path=None, category=None, normalize=True):
        """Capture shape data from a node and save it to disk as JSON."""
        data = self.capture(node_name, name=name, normalize=normalize)
        if not data:
            LOG.error(f"No curve data found on node '{node_name}'.")
            return None

        if not name:
            name = node_name.split("|")[-1]

        return self.save_to_disk(data, name, folder_path=folder_path or self.user_path, category=category)
