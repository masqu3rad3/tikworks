"""Tests for tik.shared.prefs.store."""

import json


class TestPrefStorePath:
    """Where the file lands."""

    def test_resolves_under_folder_with_json_suffix(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger", folder=tmp_path)
        assert store.path == tmp_path / "trigger.json"

    def test_path_is_absolute(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger", folder=tmp_path)
        assert store.path.is_absolute()

    def test_defaults_to_home_tikworks(self):
        from pathlib import Path

        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger")
        assert store.path == Path.home() / "TikWorks" / "trigger.json"

    def test_constructing_writes_nothing(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        PrefStore("trigger", folder=tmp_path)
        assert list(tmp_path.iterdir()) == []


class TestPrefStoreRead:
    """Reading tolerates every kind of missing or broken file."""

    def test_missing_file_reads_empty(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        assert PrefStore("trigger", folder=tmp_path).read() == {}

    def test_reads_written_data(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger", folder=tmp_path)
        store.write({"interface.log_max_lines": 500})
        assert store.read() == {"interface.log_max_lines": 500}

    def test_corrupt_file_reads_empty(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        (tmp_path / "trigger.json").write_text("{not json", encoding="utf-8")
        assert PrefStore("trigger", folder=tmp_path).read() == {}

    def test_non_dict_file_reads_empty(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        (tmp_path / "trigger.json").write_text("[1, 2, 3]", encoding="utf-8")
        assert PrefStore("trigger", folder=tmp_path).read() == {}


class TestPrefStoreWrite:
    """Writing creates the folder and stays human-readable."""

    def test_creates_missing_folder(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger", folder=tmp_path / "nested" / "deeper")
        store.write({"a": 1})
        assert store.path.is_file()

    def test_written_file_is_sorted_and_indented(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger", folder=tmp_path)
        store.write({"b": 2, "a": 1})
        text = store.path.read_text(encoding="utf-8")
        assert text.index('"a"') < text.index('"b"')
        assert "\n" in text

    def test_write_replaces_previous_content(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger", folder=tmp_path)
        store.write({"a": 1})
        store.write({"b": 2})
        assert json.loads(store.path.read_text(encoding="utf-8")) == {"b": 2}
