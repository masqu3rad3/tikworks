import os
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from maya import cmds
import maya.api.OpenMaya as om

from tikmaya.utils import control_shapes
from tikmaya.utils.control_shapes import (
    ControlShapeLibrary,
    get_home_dir,
    capture,
    capture_to_disk,
    save_to_disk,
    _normalize_data,
    _guess_camera_view,
    capture_thumbnail,
    _resolve_folder_path
)
from tikmaya.types.transform import Transform
from tikmaya.types.nurbs import Nurbs

@pytest.fixture
def clean_library():
    # Reset singleton before and after test
    ControlShapeLibrary._INSTANCE = None
    yield
    ControlShapeLibrary._INSTANCE = None

def test_get_home_dir(monkeypatch):
    # Test Windows
    monkeypatch.setattr(control_shapes, "CURRENT_PLATFORM", "Windows")
    monkeypatch.setenv("USERPROFILE", "C:\\Users\\Test")
    assert get_home_dir() == "C:\\Users\\Test"

    # Test Linux/Other
    monkeypatch.setattr(control_shapes, "CURRENT_PLATFORM", "Linux")
    monkeypatch.setenv("HOME", "/home/test")
    # os.path.normpath might convert slashes depending on the OS running the test (Windows)
    expected = os.path.normpath("/home/test")
    assert get_home_dir() == expected

    # Test fallback (when env vars are missing)
    # We can't easily test os.path.expanduser without mocking os.path,
    # but we can ensure it returns something non-empty
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    assert get_home_dir()

def test_get_home_dir_fallback(monkeypatch):
    # Ensure both env vars are missing
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.delenv("HOME", raising=False)

    # Mock os.path.expanduser to return a known value
    with patch("os.path.expanduser", return_value="/mock/home") as mock_expand:
        assert get_home_dir() == os.path.normpath("/mock/home")
        mock_expand.assert_called_with("~")

class TestControlShapeLibrary:
    def test_singleton(self, clean_library):
        lib1 = ControlShapeLibrary.get_instance()
        lib2 = ControlShapeLibrary.get_instance()
        assert lib1 is lib2

    def test_paths(self, clean_library, tmp_path, monkeypatch):
        lib = ControlShapeLibrary.get_instance()

        # Mock _core_path and _user_path to point to tmp_path so they "exist"
        core_dir = tmp_path / "core"
        core_dir.mkdir()
        user_dir = tmp_path / "user"
        user_dir.mkdir()

        lib._core_path = core_dir
        lib._user_path = user_dir

        paths = lib.search_paths
        assert core_dir in paths
        assert user_dir in paths

        # Test Environment Path
        env_dir = tmp_path / "env"
        env_dir.mkdir()
        monkeypatch.setenv("TIKMAYA_SHAPES_PATH", str(env_dir))

        assert env_dir in lib.search_paths

        # Test Custom Path
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        lib.add_path(custom_dir)
        assert custom_dir in lib.search_paths

        # Test remove path
        lib.remove_path(custom_dir)
        assert custom_dir not in lib.search_paths

        # Test add_path with None
        lib.add_path(None) # Should not crash

        # Test remove_path with None
        lib.remove_path(None) # Should not crash

    def test_search_paths_empty_env_segment(clean_library, tmp_path, monkeypatch):
        lib = ControlShapeLibrary.get_instance()

        # Create a valid env path
        env_dir = tmp_path / "env_valid"
        env_dir.mkdir()

        # Set env var with empty segment (e.g. path;;path)
        sep = os.pathsep
        monkeypatch.setenv("TIKMAYA_SHAPES_PATH", f"{env_dir}{sep}{sep}invalid_path")

        paths = lib.search_paths
        assert env_dir in paths
        # The empty segment should be skipped, and invalid_path (if it doesn't exist) might be in the list
        # but filtered out later or just added as Path object.
        # The code splits by pathsep and checks `if not env_path_str: continue`.
        # So we just verify it doesn't crash and handles the valid one.

    def test_refresh_skips_non_dirs(self, clean_library, tmp_path):
        lib = ControlShapeLibrary.get_instance()

        # Mock core and user paths to be empty to avoid picking up real shapes
        lib._core_path = tmp_path / "core_empty"
        lib._core_path.mkdir()
        lib._user_path = tmp_path / "user_empty"
        lib._user_path.mkdir()

        # Add a file as a path
        file_path = tmp_path / "not_a_dir"
        file_path.touch()
        lib.add_path(file_path)

        # Add a non-existent path
        non_existent = tmp_path / "does_not_exist"
        lib.add_path(non_existent)

        # Should not crash
        lib.refresh()

        # Verify they are not scanned (cache should be empty if no other paths have shapes)
        assert not lib._cache

    def test_refresh_handles_root_json(clean_library, tmp_path):
        lib = ControlShapeLibrary.get_instance()
        user_path = tmp_path / "user_root"
        user_path.mkdir()
        lib._user_path = user_path

        # Create a json at root
        shape_file = user_path / "root_shape.json"
        with open(shape_file, "w") as f:
            json.dump({"name": "root_shape"}, f)

        lib.refresh()

        assert "root_shape" in lib._cache
        # Category should be None for root files
        assert lib._cache["root_shape"]["category"] is None

    def test_list_shapes_auto_refresh(clean_library, tmp_path):
        lib = ControlShapeLibrary.get_instance()
        user_path = tmp_path / "user_auto"
        user_path.mkdir()
        lib._user_path = user_path

        # Create shape
        shape_file = user_path / "auto_shape.json"
        with open(shape_file, "w") as f:
            json.dump({"name": "auto_shape"}, f)

        # Manually clear cache to simulate uninitialized state
        lib._cache = {}

        # list_shapes should trigger refresh
        shapes = lib.list_shapes()
        assert "auto_shape" in shapes

    def test_list_and_load_shapes(self, clean_library, tmp_path):
        lib = ControlShapeLibrary.get_instance()
        lib._user_path = tmp_path / "user"
        lib._user_path.mkdir()

        # Create a dummy shape file
        shape_data = {"name": "test_shape", "curves": []}
        shape_file = lib._user_path / "test_shape.json"
        with open(shape_file, "w") as f:
            json.dump(shape_data, f)

        # Refresh and list
        lib.refresh()
        shapes = lib.list_shapes()
        assert "test_shape" in shapes

        # Load
        loaded_data = lib.load("test_shape")
        assert loaded_data == shape_data

        # Get path
        assert lib.get_path("test_shape") == shape_file

        # Test missing
        assert lib.load("non_existent") is None

        # Test get_shape_data
        data_map = lib.get_shape_data()
        assert "test_shape" in data_map
        assert data_map["test_shape"]["path"] == shape_file

    def test_load_malformed_json(self, clean_library, tmp_path):
        lib = ControlShapeLibrary.get_instance()
        lib._user_path = tmp_path / "user"
        lib._user_path.mkdir()

        bad_file = lib._user_path / "bad.json"
        with open(bad_file, "w") as f:
            f.write("{invalid_json")

        lib.refresh()
        assert lib.load("bad") is None

    def test_load_missing_shape_logs_warning(self, clean_library):
        lib = ControlShapeLibrary.get_instance()

        with patch("tikmaya.utils.control_shapes.LOG") as mock_log:
            result = lib.load("missing_shape")
            assert result is None
            mock_log.warning.assert_called()

def test_capture_and_normalize():
    cmds.file(new=True, force=True)
    # Create a curve
    circle = cmds.circle(name="testCircle", nr=(0, 1, 0), r=10)[0]

    data = capture(circle, normalize=True)
    assert data["name"] == "testCircle"
    assert len(data["curves"]) == 1

    # Check normalization (radius 10 -> diameter 20. Scale should be 1/20 = 0.05)
    points = data["curves"][0]["point"]
    # Max coordinate value should be scaled down
    max_val = max(max(abs(c) for c in p) for p in points)
    assert max_val <= 0.5 + 0.0001

    # Test capture without normalization
    data_raw = capture(circle, normalize=False)
    points_raw = data_raw["curves"][0]["point"]
    max_val_raw = max(max(abs(c) for c in p) for p in points_raw)
    assert max_val_raw > 5.0 # Radius is 10

def test_capture_no_shapes():
    cmds.file(new=True, force=True)
    empty = cmds.createNode("transform", name="empty")
    assert capture(empty) is None

def test_save_to_disk(tmp_path):
    data = {"test": "data"}
    path = save_to_disk(data, "test_save", tmp_path)
    assert os.path.exists(path)
    with open(path, "r") as f:
        loaded = json.load(f)
    assert loaded == data

def test_capture_to_disk(tmp_path, clean_library):
    cmds.file(new=True, force=True)
    circle = cmds.circle(name="diskCircle")[0]

    # Mock capture_thumbnail to avoid playblast issues
    with patch("tikmaya.utils.control_shapes.capture_thumbnail") as mock_thumb:
        path = capture_to_disk("diskCircle", folder_path=tmp_path, thumbnail=True)

    assert path
    assert os.path.exists(path)
    assert mock_thumb.called

    # Test capture failure
    with patch("tikmaya.utils.control_shapes.capture", return_value=None):
        with patch("tikmaya.utils.control_shapes.LOG") as mock_log:
            result = capture_to_disk("some_node", folder_path=tmp_path)
            assert result is None
            mock_log.error.assert_called()

def test_guess_camera_view():
    cmds.file(new=True, force=True)

    # Flat object (Plane)
    plane = cmds.polyPlane(w=10, h=10)[0]
    view = _guess_camera_view(plane)
    assert view == "top"

    # Cube
    cube = cmds.polyCube(w=10, h=10, d=10)[0]
    view = _guess_camera_view(cube)
    assert view == "oneThird"

    # Irregular
    cube2 = cmds.polyCube(w=10, h=5, d=2)[0]
    view = _guess_camera_view(cube2)
    assert view == "iso"

def test_resolve_folder_path(tmp_path):
    p = _resolve_folder_path(tmp_path, "category")
    assert p == tmp_path / "category"
    assert p.exists()

    p2 = _resolve_folder_path(str(tmp_path), None)
    assert p2 == tmp_path

def test_capture_thumbnail(tmp_path):
    cmds.file(new=True, force=True)
    cube = cmds.polyCube(name="thumbCube")[0]

    # Mock playblast to avoid headless issues and verify it's called
    with patch("maya.cmds.playblast") as mock_playblast:
        # Mock Panel to avoid modelPanel creation issues in headless
        with patch("tikmaya.utils.control_shapes.Panel") as MockPanel:
            mock_panel_instance = MockPanel.return_value
            mock_panel_instance.name = "mockPanel"

            # Mock Camera creation to avoid side effects
            with patch("tikmaya.utils.control_shapes.Camera") as MockCamera:
                mock_cam_instance = MockCamera.create.return_value
                mock_cam_instance.transform = MagicMock()
                mock_cam_instance.aim = MagicMock()

                # Side effect for playblast to create the file
                def side_effect(*args, **kwargs):
                    filename = kwargs.get("completeFilename")
                    with open(filename, "w") as f:
                        f.write("dummy image")
                    return filename
                mock_playblast.side_effect = side_effect

                path = capture_thumbnail("thumbCube", "thumb_test", tmp_path)

                assert os.path.exists(path)
                assert mock_playblast.called

                # Verify camera setup
                MockCamera.create.assert_called()
                mock_cam_instance.set_controls.assert_called_with("cameraAndAim")

def test_normalize_data_small_dim():
    # Test that small dimensions are not scaled
    data = {"curves": [{"point": [(0,0,0), (0.00001, 0, 0)]}]}
    all_points = [(0,0,0), (0.00001, 0, 0)]

    normalized = _normalize_data(data, all_points)
    # Should be unchanged because max_dim < 0.0001
    assert normalized == data

