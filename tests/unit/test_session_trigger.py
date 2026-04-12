"""Tests for tik.trigger.session module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestIO:
    """Tests for tik.trigger.core.io.IO (session IO)."""

    def test_io_init_with_path(self):
        """Test IO initialization with file path."""
        from tik.trigger.session import IO

        io = IO(file_path=Path("test.trg"))
        assert io.file_path == Path("test.trg")

    def test_io_init_without_path(self):
        """Test IO initialization without file path."""
        from tik.trigger.session import IO

        io = IO()
        assert io.file_path is None

    def test_io_write_and_read(self):
        """Test writing and reading JSON data."""
        from tik.trigger.session import IO

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.trg"
            io = IO(file_path=file_path)

            data = {"version": "2.0", "modules": []}
            result = io.write(data)
            assert result == file_path

            read_data = io.read()
            assert read_data == data

    def test_io_write_with_override_path(self):
        """Test writing with override file path."""
        from tik.trigger.session import IO

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path1 = Path(tmpdir) / "test1.trg"
            file_path2 = Path(tmpdir) / "test2.trg"

            io = IO(file_path=file_path1)
            data = {"test": "data"}

            result = io.write(data, file_path=file_path2)
            assert result == file_path2
            assert io.read(file_path2) == data

    def test_io_read_nonexistent_file(self):
        """Test reading a nonexistent file returns None."""
        from tik.trigger.session import IO

        io = IO(file_path=Path("/nonexistent/file.trg"))
        assert io.read() is None

    def test_io_read_invalid_json(self):
        """Test reading invalid JSON returns None."""
        from tik.trigger.session import IO

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "invalid.json"
            file_path.write_text("not valid json {")

            io = IO(file_path=file_path)
            assert io.read() is None

    def test_ensure_extension_trg(self):
        """Test ensure_extension for .trg files."""
        from tik.shared.io import ensure_extension

        path = ensure_extension(Path("test"), ".trg")
        assert path == Path("test.trg")

        path = ensure_extension(Path("test.xyz"), ".trg")
        assert path == Path("test.trg")

        path = ensure_extension(Path("test.trg"), ".trg")
        assert path == Path("test.trg")

    def test_ensure_extension_tra(self):
        """Test ensure_extension for .tra files."""
        from tik.shared.io import ensure_extension

        path = ensure_extension(Path("test"), ".tra")
        assert path == Path("test.tra")

        path = ensure_extension(Path("test.trg"), ".tra")
        assert path == Path("test.tra")


class TestGuideSessionInit:
    """Tests for GuideSession initialization."""

    def test_guide_session_init(self):
        """Test GuideSession initializes correctly."""
        from tik.trigger.session.guide_session import GuideSession

        session = GuideSession()
        assert session.file_path is None
        assert session.modules == {}

    def test_guide_session_init_with_path(self):
        """Test GuideSession with file path."""
        from tik.trigger.session.guide_session import GuideSession

        session = GuideSession(file_path="test.trg")
        assert session.file_path == Path("test.trg")


class TestActionSessionInit:
    """Tests for ActionSession initialization."""

    def test_action_session_init(self):
        """Test ActionSession initializes correctly."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        assert session.file_path is None
        assert session.actions == []

    def test_action_session_init_with_path(self):
        """Test ActionSession with file path."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession(file_path="test.tra")
        assert session.file_path == Path("test.tra")

    def test_list_valid_actions(self):
        """Test listing valid action types."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        session.load_action_definitions()
        actions = session.list_valid_actions()
        assert isinstance(actions, list)

    def test_new_session(self):
        """Test new_session clears actions."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        session.new_session()
        assert session.actions == []


class TestGuideSessionCollectGuides:
    """Tests for GuideSession.collect_guides()."""

    def test_collect_guides_empty_session(self):
        """Test collecting guides from empty session."""
        from tik.trigger.session.guide_session import GuideSession

        session = GuideSession()
        data = session.collect_guides()
        assert data == []


class TestActionSessionActions:
    """Tests for ActionSession action management."""

    def test_add_action_invalid_type(self):
        """Test adding an invalid action type returns None."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        session.load_action_definitions()
        result = session.add_action("nonexistent_action")
        assert result is None

    def test_get_action_not_found(self):
        """Test get_action returns None for nonexistent action."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        result = session.get_action("nonexistent")
        assert result is None

    def test_list_action_names_empty(self):
        """Test list_action_names returns empty list for empty session."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        assert session.list_action_names() == []

    def test_remove_action_not_found(self):
        """Test remove_action returns False for nonexistent action."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        result = session.remove_action("nonexistent")
        assert result is False

    def test_rename_action_not_found(self):
        """Test rename_action returns False for nonexistent action."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        result = session.rename_action("old", "new")
        assert result is False

    def test_enable_action_not_found(self):
        """Test enable_action returns False for nonexistent action."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        result = session.enable_action("nonexistent")
        assert result is False

    def test_disable_action_not_found(self):
        """Test disable_action returns False for nonexistent action."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        result = session.disable_action("nonexistent")
        assert result is False

    def test_is_enabled_not_found(self):
        """Test is_enabled returns False for nonexistent action."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        result = session.is_enabled("nonexistent")
        assert result is False

    def test_move_action_not_found(self):
        """Test move_action returns False for nonexistent action."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        result = session.move_action("nonexistent", 0)
        assert result is False


class TestActionSessionSaveLoad:
    """Tests for ActionSession save/load."""

    def test_save_load_empty_session(self):
        """Test saving and loading an empty session."""
        from tik.trigger.session.action_session import ActionSession

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.tra"

            # Create and save session
            session = ActionSession()
            session.load_action_definitions()
            result = session.save(str(file_path))
            assert result == file_path

            # Load session
            new_session = ActionSession()
            new_session.load_action_definitions()
            loaded = new_session.load(str(file_path))
            assert loaded is True
            assert new_session.actions == []

    def test_is_modified_false_after_new(self):
        """Test is_modified returns False for new session."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        assert session.is_modified() is False

    def test_is_modified_true_after_change(self):
        """Test is_modified returns True after adding action."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        session.load_action_definitions()

        # Add an action if available
        valid_actions = session.list_valid_actions()
        if valid_actions:
            session.add_action(valid_actions[0])
            assert session.is_modified() is True
        else:
            # No actions available, skip
            pass


class TestSessionDataIntegrity:
    """Tests for session data structures."""

    def test_action_session_get_session_data(self):
        """Test get_session_data returns correct structure."""
        from tik.trigger.session.action_session import ActionSession

        session = ActionSession()
        data = session.get_session_data()
        assert "version" in data
        assert "actions" in data
        assert data["version"] == "2.0"
        assert data["actions"] == []


class TestSessionModuleImports:
    """Tests for session module imports."""

    def test_import_guide_session(self):
        """Test GuideSession can be imported."""
        from tik.trigger.session import GuideSession
        assert GuideSession is not None

    def test_import_action_session(self):
        """Test ActionSession can be imported."""
        from tik.trigger.session import ActionSession
        assert ActionSession is not None

    def test_import_io(self):
        """Test IO can be imported."""
        from tik.trigger.session import IO
        assert IO is not None

    def test_import_extensions(self):
        """Test extension constants can be imported."""
        from tik.trigger.session import GUIDE_SESSION_EXT, ACTION_SESSION_EXT
        assert GUIDE_SESSION_EXT == ".trg"
        assert ACTION_SESSION_EXT == ".tra"
