"""Files & Sessions preferences."""

import pytest
from test_pipeline_ui import _stub_designer

from tik.trigger.ui.main import TriggerWindow


@pytest.fixture
def window(qapp):
    made = TriggerWindow(designer_factory=_stub_designer)
    yield made
    made.close()


class TestRecentSessions:
    """The recent list persists and respects its length preference."""

    def test_remember_appends_to_the_front(self, window):
        window._remember("D:/one.tr")
        window._remember("D:/two.tr")
        assert window.recent_files[0].endswith("two.tr")

    def test_remember_deduplicates(self, window):
        window._remember("D:/one.tr")
        window._remember("D:/one.tr")
        assert len(window.recent_files) == 1

    def test_list_is_trimmed_to_the_preference(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "max_recent", 3)
        for index in range(6):
            window._remember(f"D:/file{index}.tr")
        assert len(window.recent_files) == 3

    def test_remember_persists_to_the_store(self, window):
        from tik.trigger.config import prefs

        window._remember("D:/one.tr")
        assert prefs.store.read()["files.recent_sessions"]

    def test_disabled_preference_stores_nothing(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "remember_recent", False)
        window._remember("D:/one.tr")
        assert prefs.store.read().get("files.recent_sessions", []) == []

    def test_load_restores_the_list(self, window):
        from tik.trigger.config import prefs

        prefs.files.recent_sessions = ["D:/kept.tr"]
        window._load_recent()
        assert window.recent_files == ["D:/kept.tr"]

    def test_load_ignores_stored_list_when_disabled(self, window, monkeypatch):
        from tik.trigger.config import prefs

        prefs.files.recent_sessions = ["D:/kept.tr"]
        monkeypatch.setattr(prefs.files, "remember_recent", False)
        window._load_recent()
        assert window.recent_files == []

    def test_max_recent_change_trims_the_live_menu(self, window, monkeypatch):
        from tik.trigger.config import prefs

        for index in range(6):
            window._remember(f"D:/file{index}.tr")
        monkeypatch.setattr(prefs.files, "max_recent", 2)
        window._on_prefs_applied(["files.max_recent"])
        assert len(window.recent_files) == 2


class TestBrowseFolder:
    """Where a file browser opens."""

    def test_prefers_the_last_folder(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "last_folder", "D:/last")
        assert window.browse_folder() == "D:/last"

    def test_falls_back_to_the_default_folder(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "last_folder", "")
        monkeypatch.setattr(prefs.files, "default_folder", "D:/projects")
        assert window.browse_folder() == "D:/projects"

    def test_ignores_the_last_folder_when_disabled(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "remember_last_folder", False)
        monkeypatch.setattr(prefs.files, "last_folder", "D:/last")
        monkeypatch.setattr(prefs.files, "default_folder", "D:/projects")
        assert window.browse_folder() == "D:/projects"

    def test_empty_when_nothing_is_configured(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "last_folder", "")
        monkeypatch.setattr(prefs.files, "default_folder", "")
        assert window.browse_folder() == ""

    def test_remembering_a_file_stores_its_folder(self, window):
        from tik.trigger.config import prefs

        window._remember("D:/projects/rig.tr")
        assert prefs.files.last_folder.replace("\\", "/") == "D:/projects"

    def test_folder_is_not_stored_when_disabled(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "remember_last_folder", False)
        window._remember("D:/projects/rig.tr")
        assert prefs.files.last_folder == ""


class TestUnsavedCloseConfirmation:
    """The warning can be turned off, and then closing discards."""

    def test_asks_by_default(self, window, monkeypatch):
        from tik.shared.ui import feedback

        asked = []
        monkeypatch.setattr(
            feedback, "set_handler", lambda handler: None, raising=False
        )
        monkeypatch.setattr(
            window,
            "_ask_save_discard_dialog",
            lambda session: asked.append(1) or "cancel",
        )
        window.ask_save_discard(window.session)
        assert asked == [1]

    def test_discards_without_asking_when_disabled(self, window, monkeypatch):
        from tik.trigger.config import prefs

        asked = []
        monkeypatch.setattr(prefs.files, "confirm_unsaved_close", False)
        monkeypatch.setattr(
            window,
            "_ask_save_discard_dialog",
            lambda session: asked.append(1) or "cancel",
        )
        assert window.ask_save_discard(window.session) == "discard"
        assert asked == []
