"""Unit tests for tik.core.jsonio module."""

import pytest

from tik.core.jsonio import JsonDecodeError, JsonIOError, load, save


class TestJsonIOExceptions:
    """Tests for JSON I/O exception classes."""

    def test_json_io_error_is_exception(self):
        """Test JsonIOError inherits from Exception."""
        assert issubclass(JsonIOError, Exception)

    def test_json_decode_error_is_json_io_error(self):
        """Test JsonDecodeError inherits from JsonIOError."""
        assert issubclass(JsonDecodeError, JsonIOError)


class TestJsonLoad:
    """Tests for the load function."""

    def test_load_valid_json(self, tmp_path):
        """Test loading valid JSON file."""
        json_file = tmp_path / "test.json"
        json_file.write_text('{"key": "value", "number": 42}', encoding="utf-8")

        data = load(json_file)
        assert data == {"key": "value", "number": 42}

    def test_load_with_string_path(self, tmp_path):
        """Test loading JSON using string path instead of Path object."""
        json_file = tmp_path / "string_path.json"
        json_file.write_text('{"test": true}', encoding="utf-8")

        data = load(str(json_file))
        assert data == {"test": True}

    def test_load_nonexistent_file_raises_file_not_found(self, tmp_path):
        """Test load raises FileNotFoundError for missing file."""
        nonexistent = tmp_path / "does_not_exist.json"
        with pytest.raises(FileNotFoundError):
            load(nonexistent)

    def test_load_invalid_json_raises_decode_error(self, tmp_path):
        """Test load raises JsonDecodeError for invalid JSON content."""
        invalid_json = tmp_path / "invalid.json"
        invalid_json.write_text("{ not valid json }", encoding="utf-8")

        with pytest.raises(JsonDecodeError, match="Invalid JSON"):
            load(invalid_json)


class TestJsonSave:
    """Tests for the save function."""

    def test_save_basic_dict(self, tmp_path):
        """Test saving basic dictionary to JSON."""
        json_file = tmp_path / "output.json"
        data = {"key": "value", "number": 123}

        save(json_file, data)

        assert json_file.exists()
        content = json_file.read_text(encoding="utf-8")
        assert '"key": "value"' in content
        assert '"number": 123' in content

    def test_save_with_string_path(self, tmp_path):
        """Test saving JSON using string path instead of Path object."""
        json_file = tmp_path / "string_output.json"
        data = {"test": "data"}

        save(str(json_file), data)

        assert json_file.exists()

    def test_save_creates_parent_directories(self, tmp_path):
        """Test save creates parent directories if they don't exist."""
        nested_path = tmp_path / "nested" / "dir" / "file.json"
        data = {"nested": True}

        save(nested_path, data)

        assert nested_path.exists()
        assert nested_path.parent.exists()

    def test_save_with_custom_indent(self, tmp_path):
        """Test save respects custom indent parameter."""
        json_file = tmp_path / "indented.json"
        data = {"key": "value"}

        save(json_file, data, indent=4)

        content = json_file.read_text(encoding="utf-8")
        # With indent=4, there should be 4 spaces
        assert "    " in content

    def test_save_with_sort_keys_false(self, tmp_path):
        """Test save respects sort_keys=False parameter."""
        json_file = tmp_path / "unsorted.json"
        # Use dict with keys that would be reordered if sorted
        data = {"zebra": 1, "alpha": 2}

        save(json_file, data, sort_keys=False)

        content = json_file.read_text(encoding="utf-8")
        # Keys should appear in insertion order
        zebra_pos = content.find("zebra")
        alpha_pos = content.find("alpha")
        assert zebra_pos < alpha_pos

    def test_save_with_ensure_ascii_true(self, tmp_path):
        """Test save with ensure_ascii=True escapes unicode."""
        json_file = tmp_path / "ascii.json"
        data = {"unicode": "日本語"}

        save(json_file, data, ensure_ascii=True)

        content = json_file.read_text(encoding="utf-8")
        # Unicode should be escaped with ensure_ascii=True
        assert "\\u" in content

    def test_save_unicode_default(self, tmp_path):
        """Test save preserves unicode characters by default (ensure_ascii=False)."""
        json_file = tmp_path / "unicode.json"
        data = {"unicode": "日本語"}

        save(json_file, data)

        content = json_file.read_text(encoding="utf-8")
        # Unicode should be preserved
        assert "日本語" in content
