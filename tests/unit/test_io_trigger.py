"""Tests for tik.trigger.config.io module."""

import json
import tempfile
from pathlib import Path

import pytest


class TestConfigIOInit:
    """Tests for ConfigIO initialization."""

    def test_init_without_path(self):
        """Test ConfigIO initialization without a path."""
        from tik.trigger.config.io import ConfigIO

        io = ConfigIO()
        assert io.file_path is None
        assert io.valid_extensions == [".json"]

    def test_init_with_path(self):
        """Test ConfigIO initialization with a path."""
        from tik.trigger.config.io import ConfigIO

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            io = ConfigIO(f.name)
            assert io.file_path == Path(f.name)

    def test_init_without_extension_raises(self):
        """Test ConfigIO raises ValueError without extension."""
        from tik.trigger.config.io import ConfigIO

        with pytest.raises(ValueError, match="Missing file extension"):
            ConfigIO("no_extension_file")

    def test_init_with_unsupported_extension_raises(self):
        """Test ConfigIO raises ValueError with unsupported extension."""
        from tik.trigger.config.io import ConfigIO

        with pytest.raises(ValueError, match="Unsupported extension"):
            ConfigIO("file.txt")


class TestConfigIOSetFilePath:
    """Tests for ConfigIO.set_file_path method."""

    def test_set_file_path_json(self):
        """Test setting a valid JSON file path."""
        from tik.trigger.config.io import ConfigIO

        io = ConfigIO()
        io.set_file_path("test.json")
        assert io.file_path == Path("test.json")

    def test_set_file_path_without_extension_raises(self):
        """Test setting path without extension raises ValueError."""
        from tik.trigger.config.io import ConfigIO

        io = ConfigIO()
        with pytest.raises(ValueError, match="Missing file extension"):
            io.set_file_path("no_extension")


class TestConfigIORead:
    """Tests for ConfigIO.read method."""

    def test_read_existing_file(self):
        """Test reading an existing JSON file."""
        from tik.trigger.config.io import ConfigIO

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"key": "value", "number": 42}, f)
            temp_path = f.name

        io = ConfigIO(temp_path)
        data = io.read()
        assert data == {"key": "value", "number": 42}

    def test_read_nonexistent_file(self):
        """Test reading a nonexistent file returns None."""
        from tik.trigger.config.io import ConfigIO

        io = ConfigIO("nonexistent_file.json")
        data = io.read()
        assert data is None

    def test_read_with_custom_path(self):
        """Test reading from a custom path instead of class path."""
        from tik.trigger.config.io import ConfigIO

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"custom": "data"}, f)
            temp_path = f.name

        io = ConfigIO("other_file.json")
        data = io.read(temp_path)
        assert data == {"custom": "data"}


class TestConfigIOWrite:
    """Tests for ConfigIO.write method."""

    def test_write_dict(self):
        """Test writing a dictionary to JSON file."""
        from tik.trigger.config.io import ConfigIO

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "output.json"
            io = ConfigIO(file_path)
            io.write({"test": "value", "list": [1, 2, 3]})

            assert file_path.exists()
            with open(file_path, "r") as f:
                data = json.load(f)
            assert data == {"test": "value", "list": [1, 2, 3]}

    def test_write_with_custom_path(self):
        """Test writing to a custom path instead of class path."""
        from tik.trigger.config.io import ConfigIO

        with tempfile.TemporaryDirectory() as tmpdir:
            class_path = Path(tmpdir) / "class_path.json"
            custom_path = Path(tmpdir) / "custom_path.json"

            io = ConfigIO(class_path)
            io.write({"key": "value"}, custom_path)

            assert custom_path.exists()
            with open(custom_path, "r") as f:
                data = json.load(f)
            assert data == {"key": "value"}

    def test_write_creates_parent_folders(self):
        """Test that write creates parent folders if they don't exist."""
        from tik.trigger.config.io import ConfigIO

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "nested" / "folder" / "output.json"
            io = ConfigIO(file_path)
            io.write({"nested": True})

            assert file_path.exists()


class TestConfigIOStaticMethods:
    """Tests for ConfigIO static methods."""

    def test_file_exists_true(self):
        """Test file_exists returns True for existing file."""
        from tik.trigger.config.io import ConfigIO

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        assert ConfigIO.file_exists(temp_path) is True

    def test_file_exists_false(self):
        """Test file_exists returns False for nonexistent file."""
        from tik.trigger.config.io import ConfigIO

        assert ConfigIO.file_exists("nonexistent_file_12345.json") is False

    def test_load_json_valid(self):
        """Test _load_json with valid JSON."""
        from tik.trigger.config.io import ConfigIO

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"valid": True}, f)
            temp_path = f.name

        data = ConfigIO._load_json(temp_path)
        assert data == {"valid": True}

    def test_load_json_invalid_raises(self):
        """Test _load_json with invalid JSON raises ValueError."""
        from tik.trigger.config.io import ConfigIO

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("not valid json {")
            temp_path = f.name

        with pytest.raises(ValueError, match="Corrupted JSON file"):
            ConfigIO._load_json(temp_path)


class TestReadWriteJsonFunctions:
    """Tests for module-level read_json and write_json functions."""

    def test_read_json(self):
        """Test read_json function."""
        from tik.trigger.config.io import read_json

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"function": "test"}, f)
            temp_path = f.name

        data = read_json(temp_path)
        assert data == {"function": "test"}

    def test_write_json(self):
        """Test write_json function."""
        from tik.trigger.config.io import write_json

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "written.json"
            write_json(file_path, {"written": True})

            assert file_path.exists()
            with open(file_path, "r") as f:
                data = json.load(f)
            assert data == {"written": True}
