"""Control shape library: the name -> curve-data index.

Pure paths and JSON, so both ``tik.maya`` (which cannot import ``tik.shared``)
and the headless Qt picker (which cannot import ``tik.maya``, since importing
it requires a live Maya) can reach it. Curve capture lives in
``tik.maya.utils.control_shapes``; nothing here touches a scene.
"""

from __future__ import annotations

import json
import logging
import os
import platform
from pathlib import Path

LOG = logging.getLogger(__name__)

CURRENT_PLATFORM = platform.system()


def get_home_dir():
    """Get the user home directory.

    Returns:
        str: Normalized path to the user's home directory.
    """
    if CURRENT_PLATFORM == "Windows":
        home = os.getenv("USERPROFILE")
    else:
        home = os.getenv("HOME")

    if not home:
        home = str(Path.home())

    return os.path.normpath(home)


class ControlShapeLibrary:
    """Singleton manager for accessing and loading controller shape data.

    The library searches for shape definitions in multiple locations:
    1. Core path: Built-in shapes shipped with TikWorks
    2. User path: User-specific shapes in ~/TikWorks/user_control_shapes
    3. Environment paths: Additional paths from TIKMAYA_SHAPES_PATH env variable
    4. Custom paths: Paths added via API

    Later paths override earlier ones for shapes with the same name.
    """

    _INSTANCE = None

    def __init__(self, include_user_path: bool = True):
        """Initialize the shape library with default search paths.

        Args:
            include_user_path: Search ``~/TikWorks/user_control_shapes``.
                A rig build passes ``False``: a per-user folder is a
                preference, and a preference must never change a rig.
        """
        self._cache = {}
        self._custom_paths = []
        self._include_user_path = include_user_path

        # 1. Core Path -- the shipped catalogue, beside this module.
        self._core_path = Path(__file__).absolute().parent / "data" / "control_shapes"

        # 2. User Path (always *defined*, only conditionally searched). Not
        # created here: making a directory as an import side effect is wrong.
        self._user_path = Path(get_home_dir(), "TikWorks", "user_control_shapes")

    @property
    def user_path(self):
        """Get the user-specific shape library path.

        Returns:
            Path: Path to the user's shape library directory.
        """
        return self._user_path

    @property
    def search_paths(self):
        """Get the list of paths searched for shapes, in resolution order.

        Resolution order (lowest to highest priority):
        1. Core path
        2. User path (only when ``include_user_path`` was set)
        3. Environment paths (from TIKMAYA_SHAPES_PATH)
        4. Custom paths (added via API)

        Returns:
            list: List of Path objects that exist on disk.
        """
        paths = [self._core_path]
        if self._include_user_path:
            paths.append(self._user_path)

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
        """Get or create the singleton instance of the library.

        Returns:
            ControlShapeLibrary: The singleton instance.
        """
        if not cls._INSTANCE:
            cls._INSTANCE = cls()
        return cls._INSTANCE

    def add_path(self, path):
        """Add a custom search path with highest priority.

        Args:
            path: Path to add to the search paths.

        Note:
            Invalidates the cache, forcing a refresh on next access.
        """
        if not path:
            return
        path_obj = Path(path).expanduser().absolute()
        if path_obj not in self._custom_paths:
            self._custom_paths.append(path_obj)
            self._cache = {}  # Invalidate cache

    def remove_path(self, path):
        """Remove a custom search path.

        Args:
            path: Path to remove from the search paths.

        Note:
            Invalidates the cache, forcing a refresh on next access.
        """
        if not path:
            return
        path_obj = Path(path).expanduser().absolute()
        if path_obj in self._custom_paths:
            self._custom_paths.remove(path_obj)
            self._cache = {}  # Invalidate cache

    def refresh(self):
        """Scan all search paths and populate the shape cache.

        Shapes in later paths override those in earlier paths.
        """
        self._cache = {}
        # Iterating in order means later paths overwrite earlier ones (desired behavior)
        for path in self.search_paths:
            if not path.is_dir():
                continue

            for json_path in path.rglob("*.json"):
                rel_path = json_path.relative_to(path)
                category = rel_path.parts[0] if len(rel_path.parts) > 1 else None

                self._cache[json_path.stem] = {
                    "path": json_path,
                    "category": category,
                }

    def list_shapes(self):
        """Get a list of all available shape names.

        Returns:
            list: List of shape names (str).
        """
        if not self._cache:
            self.refresh()
        return list(self._cache.keys())

    def get_shape_data(self):
        """Get cached shape metadata for all shapes.

        Returns:
            dict: Shape name -> metadata dict with 'path' and 'category' keys.
        """
        if not self._cache:
            self.refresh()
        return self._cache

    def get_path(self, name):
        """Get the file path for a shape by name.

        Args:
            name: Name of the shape.

        Returns:
            Path or None: Path to the shape's JSON file, or None if not found.
        """
        if not self._cache:
            self.refresh()
        data = self._cache.get(name)
        return data["path"] if data else None

    def load(self, name):
        """Load and return the curve data dictionary for a shape.

        Args:
            name: Name of the shape to load.

        Returns:
            dict or None: The shape data, or None when missing or unreadable.
        """
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


def save_to_disk(data, name, folder_path, category=None):
    """Save the given shape data to disk as JSON."""
    folder_path = _resolve_folder_path(folder_path, category)

    filename = f"{name}.json"
    full_path = folder_path / filename

    with full_path.open("w") as json_file:
        json.dump(data, json_file, indent=4)

    return str(full_path)


def _normalize_ratio(all_points):
    """Calculate the normalization ratio for fitting into a unit cube."""
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
        return 1.0

    return 1.0 / max_dim


def _scale_data(data, scale):
    """Scales the shape data by the given uniform scale factor."""
    for curve in data["curves"]:
        new_points = []
        for point in curve["point"]:
            new_points.append((point[0] * scale, point[1] * scale, point[2] * scale))
        curve["point"] = new_points

    return data


def _resolve_folder_path(folder_path, category):
    if isinstance(folder_path, str):
        folder_path = Path(folder_path)
    if category:
        folder_path = folder_path / category
    folder_path.mkdir(parents=True, exist_ok=True)
    return folder_path
