"""The shared JSON I/O helper and the external-open launcher.

``tik.shared.io`` is reached today only sideways -- through the trigger tests
that happen to save a file, and one ``open_external`` test in
``test_script_space_trigger.py``. That left every guard in ``IO`` uncovered and
``ensure_extension`` (which decides what a saved ``.trg`` is actually called)
untested outright.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tik.core.jsonio import JsonDecodeError, loads
from tik.shared import io
from tik.shared.io import IO, ensure_extension, open_external


class TestFilePath:
    """``set_file_path`` validates the extension and prepares the folder."""

    def test_a_valid_path_is_kept(self, tmp_path):
        target = tmp_path / "rig.json"

        assert IO(target).file_path == target

    def test_a_string_is_accepted(self, tmp_path):
        assert IO(str(tmp_path / "rig.json")).file_path == tmp_path / "rig.json"

    def test_a_missing_extension_is_rejected(self, tmp_path):
        with pytest.raises(Exception, match="Missing file extension"):
            IO(tmp_path / "rig")

    def test_an_unsupported_extension_is_rejected(self, tmp_path):
        with pytest.raises(Exception, match="Unsupported extension"):
            IO(tmp_path / "rig.txt")

    def test_a_declared_extension_is_accepted(self, tmp_path):
        target = tmp_path / "hero.trg"

        assert IO(target, valid_extensions=[".trg"]).file_path == target

    def test_declaring_extensions_replaces_the_json_default(self, tmp_path):
        with pytest.raises(Exception, match="Unsupported extension"):
            IO(tmp_path / "rig.json", valid_extensions=[".trg"])

    def test_the_parent_folder_is_created(self, tmp_path):
        IO(tmp_path / "deep" / "nested" / "rig.json")

        assert (tmp_path / "deep" / "nested").is_dir()

    def test_the_path_can_be_cleared(self, tmp_path):
        handler = IO(tmp_path / "rig.json")

        handler.set_file_path(None)

        assert handler.file_path is None


class TestReading:
    """``read`` returns the contents, or False when there is nothing to read."""

    def test_it_reads_what_was_written(self, tmp_path):
        handler = IO(tmp_path / "rig.json")
        handler.write({"modules": ["arm"]})

        assert handler.read() == {"modules": ["arm"]}

    def test_a_missing_file_reads_false(self, tmp_path):
        assert IO(tmp_path / "absent.json").read() is False

    def test_no_path_at_all_reads_false(self, tmp_path):
        handler = IO(tmp_path / "rig.json")
        handler.set_file_path(None)

        assert handler.read() is False

    def test_an_explicit_path_overrides_the_stored_one(self, tmp_path):
        other = tmp_path / "other.json"
        other.write_text(json.dumps({"from": "other"}), encoding="utf-8")
        handler = IO(tmp_path / "rig.json")
        handler.write({"from": "stored"})

        assert handler.read(other) == {"from": "other"}

    def test_a_folder_is_not_a_file(self, tmp_path):
        assert IO(tmp_path / "rig.json").read(tmp_path) is False

    def test_a_corrupt_file_is_reported_by_name(self, tmp_path):
        """The rigger needs to know *which* file to go and fix."""
        target = tmp_path / "rig.json"
        target.write_text("{not json", encoding="utf-8")

        with pytest.raises(Exception, match="Corrupted file"):
            IO(target).read()

    def test_the_corruption_report_names_the_path(self, tmp_path):
        target = tmp_path / "rig.json"
        target.write_text("{not json", encoding="utf-8")

        with pytest.raises(Exception) as info:
            IO(target).read()

        assert str(target) in str(info.value)


class TestWriting:
    """``write`` needs a path, and hands one back."""

    def test_it_returns_the_path_written(self, tmp_path):
        target = tmp_path / "rig.json"

        assert IO(target).write({"a": 1}) == target

    def test_writing_without_a_path_is_rejected(self, tmp_path):
        handler = IO(tmp_path / "rig.json")
        handler.set_file_path(None)

        with pytest.raises(Exception, match="File path is not set"):
            handler.write({"a": 1})

    def test_an_explicit_path_overrides_the_stored_one(self, tmp_path):
        handler = IO(tmp_path / "rig.json")
        other = tmp_path / "other.json"

        handler.write({"a": 1}, other)

        assert other.is_file() and not (tmp_path / "rig.json").is_file()

    def test_writing_replaces_the_previous_content(self, tmp_path):
        handler = IO(tmp_path / "rig.json")
        handler.write({"first": True})

        handler.write({"second": True})

        assert handler.read() == {"second": True}

    @pytest.mark.parametrize("data", [{"a": 1}, [1, 2, 3], "text", 42, 3.5, True, None])
    def test_any_json_value_round_trips(self, tmp_path, data):
        handler = IO(tmp_path / "rig.json")
        handler.write(data)

        assert handler.read() == data


class TestHelpers:
    """The static helpers."""

    def test_file_exists_sees_a_file(self, tmp_path):
        target = tmp_path / "rig.json"
        target.write_text("{}", encoding="utf-8")

        assert IO.file_exists(target)

    def test_file_exists_denies_a_missing_one(self, tmp_path):
        assert not IO.file_exists(tmp_path / "absent.json")

    def test_folder_check_creates_a_missing_tree(self, tmp_path):
        IO.folder_check(tmp_path / "a" / "b" / "rig.json")

        assert (tmp_path / "a" / "b").is_dir()

    def test_folder_check_treats_a_suffixless_path_as_a_folder(self, tmp_path):
        IO.folder_check(tmp_path / "just_a_folder")

        assert (tmp_path / "just_a_folder").is_dir()

    def test_folder_check_is_happy_when_it_already_exists(self, tmp_path):
        assert IO.folder_check(tmp_path) == tmp_path


class TestEnsureExtension:
    """What a saved file ends up called."""

    def test_a_bare_name_gains_the_extension(self):
        assert ensure_extension(Path("hero"), ".trg") == Path("hero.trg")

    def test_a_wrong_extension_is_replaced(self):
        assert ensure_extension(Path("hero.json"), ".trg") == Path("hero.trg")

    def test_the_right_extension_is_left_alone(self):
        assert ensure_extension(Path("hero.trg"), ".trg") == Path("hero.trg")

    def test_the_folder_is_preserved(self):
        result = ensure_extension(Path("rigs/chars/hero"), ".trg")

        assert result == Path("rigs/chars/hero.trg")

    def test_a_dotted_name_only_loses_its_last_segment(self):
        """``hero.v002`` reads as suffix ``.v002`` -- documented Path behaviour."""
        assert ensure_extension(Path("hero.v002"), ".trg") == Path("hero.trg")


class TestOpenExternal:
    """Launching the user's editor, or the OS default handler."""

    @pytest.fixture
    def launched(self, monkeypatch):
        calls: list = []
        monkeypatch.setattr(
            io.subprocess, "Popen", lambda args, **kw: calls.append(args)
        )
        monkeypatch.setattr(io.os, "startfile", calls.append, raising=False)
        return calls

    def test_a_placeholder_is_substituted(self, launched, tmp_path):
        target = tmp_path / "a.py"

        open_external(target, command="code --goto {path}")

        assert launched == [["code", "--goto", str(target)]]

    def test_without_a_placeholder_the_path_is_appended(self, launched, tmp_path):
        target = tmp_path / "a.py"

        open_external(target, command="subl")

        assert launched == [["subl", str(target)]]

    def test_a_quoted_command_survives_its_spaces(self, launched, tmp_path):
        """A Windows editor path almost always has a space in it."""
        target = tmp_path / "a.py"

        open_external(target, command='"C:/Program Files/App/app.exe" --wait {path}')

        assert launched == [["C:/Program Files/App/app.exe", "--wait", str(target)]]

    def test_a_blank_command_falls_back_to_the_os(
        self, launched, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(io.sys, "platform", "win32")
        target = tmp_path / "a.py"

        open_external(target, command="   ")

        assert launched == [str(target)]

    @pytest.mark.parametrize(
        "platform,expected",
        [("darwin", "open"), ("linux", "xdg-open"), ("freebsd12", "xdg-open")],
    )
    def test_each_platform_gets_its_own_handler(
        self, launched, tmp_path, monkeypatch, platform, expected
    ):
        monkeypatch.setattr(io.sys, "platform", platform)
        target = tmp_path / "a.py"

        open_external(target)

        assert launched == [[expected, str(target)]]

    def test_windows_uses_the_shell_association(self, launched, tmp_path, monkeypatch):
        monkeypatch.setattr(io.sys, "platform", "win32")
        target = tmp_path / "a.py"

        open_external(target)

        assert launched == [str(target)]


class TestJsonText:
    """``jsonio.loads`` is the text-side counterpart of the file helpers."""

    def test_it_parses_valid_text(self):
        assert loads('{"a": 1}') == {"a": 1}

    def test_invalid_text_raises_the_libraries_own_error(self):
        with pytest.raises(JsonDecodeError, match="Invalid JSON text"):
            loads("{not json")
