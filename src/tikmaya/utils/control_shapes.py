import os
import json
import logging
from pathlib import Path
import maya.api.OpenMaya as om

LOGGER = logging.getLogger(__name__)


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
        user_path = os.environ.get("TIKMAYA_SHAPES_PATH")
        if user_path:
            self.register_path(user_path)

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

            for json_path in path.glob("*.json"):
                self._cache[json_path.stem] = json_path

    def get_path(self, name):
        if not self._cache:
            self.refresh()
        return self._cache.get(name)

    def load(self, name):
        """Returns the dictionary data for the shape."""
        path = self.get_path(name)
        if not path:
            LOGGER.warning(f"Shape '{name}' not found in library.")
            return None

        try:
            with path.open('r') as f:
                return json.load(f)
        except Exception as e:
            LOGGER.error(f"Failed to load shape '{name}': {e}")
            return None

    # ----------------------------------------------------------------
    # IO & CAPTURE UTILS
    # ----------------------------------------------------------------

    @staticmethod
    def capture(node_name, normalize=True):
        """
        Scrapes curve data from a transform.
        """
        sel = om.MSelectionList()
        try:
            sel.add(node_name)
            obj = sel.getDependNode(0)
        except:
            raise ValueError(f"Node {node_name} not found.")

        dag_path = sel.getDagPath(0)

        shapes_data = []
        all_points = []

        # Iterate over shapes
        child_count = dag_path.childCount()
        for idx in range(child_count):
            child = dag_path.child(idx)
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
            "name": node_name,
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
            for point in curve["points"]:
                new_points.append((point[0] * scale, point[1] * scale, point[2] * scale))
            curve["points"] = new_points

        return data

    @staticmethod
    def save_to_disk(data, name, folder_path=None):
        if not folder_path:
            folder_path = Path(os.getenv("TEMP") or Path.cwd())
        else:
            folder_path = Path(folder_path)

        filename = f"{name}.json"
        full_path = folder_path / filename

        with full_path.open('w') as f:
            json.dump(data, f, indent=4)

        return str(full_path)
