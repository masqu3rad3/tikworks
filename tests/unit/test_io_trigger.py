"""Tests for tik.trigger.io module - ConfigIO and related functions are now in tik.shared.io and tik.core.jsonio."""

import json
import tempfile
from pathlib import Path

import pytest


class TestSharedIOInit:
    """Tests for tik.shared.io.IO initialization."""

    def test_init_without_path(self):
        """Test IO initialization without a path - using tik.shared.io.IO."""
        from tik.shared.io import IO

        io = IO("test.json")  # path is required for tik.shared.io.IO
        assert io.file_path is not None

    def test_init_with_path(self):
        """Test IO initialization with a path."""
        from tik.shared.io import IO

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            io = IO(f.name)
            assert io.file_path == Path(f.name)

    def test_init_without_extension_raises(self):
        """Test IO raises Exception without extension."""
        from tik.shared.io import IO

        with pytest.raises(Exception, match="Missing file extension"):
            IO("no_extension_file")

    def test_init_with_unsupported_extension_raises(self):
        """Test IO raises Exception with unsupported extension."""
        from tik.shared.io import IO

        with pytest.raises(Exception, match="Unsupported extension"):
            IO("file.txt")


class TestSharedIOSetFilePath:
    """Tests for tik.shared.io.IO.set_file_path method."""

    def test_set_file_path_json(self):
        """Test setting a valid JSON file path."""
        from tik.shared.io import IO

        io = IO("dummy.json")  # need valid path to init first
        io.set_file_path("test.json")
        assert io.file_path == Path("test.json")

    def test_set_file_path_without_extension_raises(self):
        """Test setting path without extension raises Exception."""
        from tik.shared.io import IO

        io = IO("dummy.json")
        with pytest.raises(Exception, match="Missing file extension"):
            io.set_file_path("no_extension")


class TestSharedIORead:
    """Tests for tik.shared.io.IO.read method."""

    def test_read_existing_file(self):
        """Test reading an existing JSON file."""
        from tik.shared.io import IO

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"key": "value", "number": 42}, f)
            temp_path = f.name

        io = IO(temp_path)
        data = io.read()
        assert data == {"key": "value", "number": 42}

    def test_read_nonexistent_file(self):
        """Test reading a nonexistent file returns False."""
        from tik.shared.io import IO

        io = IO("nonexistent_file.json")
        data = io.read()
        assert data is False

    def test_read_with_custom_path(self):
        """Test reading from a custom path instead of class path."""
        from tik.shared.io import IO

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"custom": "data"}, f)
            temp_path = f.name

        io = IO("other_file.json")
        data = io.read(temp_path)
        assert data == {"custom": "data"}


class TestSharedIOWrite:
    """Tests for tik.shared.io.IO.write method."""

    def test_write_dict(self):
        """Test writing a dictionary to JSON file."""
        from tik.shared.io import IO

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "output.json"
            io = IO(file_path)
            io.write({"test": "value", "list": [1, 2, 3]})

            assert file_path.exists()
            with open(file_path, "r") as f:
                data = json.load(f)
            assert data == {"test": "value", "list": [1, 2, 3]}

    def test_write_with_custom_path(self):
        """Test writing to a custom path instead of class path."""
        from tik.shared.io import IO

        with tempfile.TemporaryDirectory() as tmpdir:
            class_path = Path(tmpdir) / "class_path.json"
            custom_path = Path(tmpdir) / "custom_path.json"

            io = IO(class_path)
            io.write({"key": "value"}, custom_path)

            assert custom_path.exists()
            with open(custom_path, "r") as f:
                data = json.load(f)
            assert data == {"key": "value"}

    def test_write_creates_parent_folders(self):
        """Test that write creates parent folders if they don't exist."""
        from tik.shared.io import IO

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "nested" / "folder" / "output.json"
            io = IO(file_path)
            io.write({"nested": True})

            assert file_path.exists()


class TestSharedIOStaticMethods:
    """Tests for tik.shared.io.IO static methods."""

    def test_file_exists_true(self):
        """Test file_exists returns True for existing file."""
        from tik.shared.io import IO

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        assert IO.file_exists(temp_path) is True

    def test_file_exists_false(self):
        """Test file_exists returns False for nonexistent file."""
        from tik.shared.io import IO

        assert IO.file_exists("nonexistent_file_12345.json") is False

    def test_load_json_valid(self):
        """Test _load_json with valid JSON."""
        from tik.shared.io import IO

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"valid": True}, f)
            temp_path = f.name

        data = IO._load_json(temp_path)
        assert data == {"valid": True}

    def test_load_json_invalid_raises(self):
        """Test _load_json with invalid JSON raises Exception."""
        from tik.shared.io import IO

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("not valid json {")
            temp_path = f.name

        with pytest.raises(Exception):
            IO._load_json(temp_path)


class TestJsonIOFunctions:
    """Tests for tik.core.jsonio module-level functions."""

    def test_load_function(self):
        """Test tik.core.jsonio.load function."""
        from tik.core.jsonio import load

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"function": "test"}, f)
            temp_path = f.name

        data = load(temp_path)
        assert data == {"function": "test"}

    def test_save_function(self):
        """Test tik.core.jsonio.save function."""
        from tik.core.jsonio import save

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "written.json"
            save(file_path, {"written": True})

            assert file_path.exists()
            with open(file_path, "r") as f:
                data = json.load(f)
            assert data == {"written": True}
