"""Autosave writes a recovery sidecar, never the user's own file."""

import os
import time

import pytest
from test_pipeline_ui import _stub_designer

from tik.trigger.ui.main import TriggerWindow


@pytest.fixture
def window(qapp):
    made = TriggerWindow(designer_factory=_stub_designer)
    yield made
    made.close()


class TestSidecarPath:
    """Naming."""

    def test_appends_the_suffix(self, tmp_path):
        from tik.trigger.ui.autosave import sidecar_path

        assert sidecar_path(tmp_path / "rig.tr").name == "rig.tr.autosave"

    def test_sits_beside_the_session(self, tmp_path):
        from tik.trigger.ui.autosave import sidecar_path

        assert sidecar_path(tmp_path / "rig.tr").parent == tmp_path


class TestRecoverable:
    """When a sidecar is worth offering."""

    def test_none_when_no_sidecar(self, tmp_path):
        from tik.trigger.ui.autosave import recoverable

        session = tmp_path / "rig.tr"
        session.write_text("{}", encoding="utf-8")
        assert recoverable(session) is None

    def test_none_when_sidecar_is_older(self, tmp_path):
        from tik.trigger.ui.autosave import recoverable, sidecar_path

        session = tmp_path / "rig.tr"
        sidecar_path(session).write_text("{}", encoding="utf-8")
        time.sleep(0.01)
        session.write_text("{}", encoding="utf-8")
        os.utime(session, None)
        assert recoverable(session) is None

    def test_found_when_sidecar_is_newer(self, tmp_path):
        from tik.trigger.ui.autosave import recoverable, sidecar_path

        session = tmp_path / "rig.tr"
        session.write_text("{}", encoding="utf-8")
        time.sleep(0.01)
        side = sidecar_path(session)
        side.write_text("{}", encoding="utf-8")
        os.utime(side, None)
        assert recoverable(session) == side

    def test_none_for_an_unsaved_session(self):
        from tik.trigger.ui.autosave import recoverable

        assert recoverable("") is None


class TestClear:
    """A real save removes the recovery copy."""

    def test_removes_the_sidecar(self, tmp_path):
        from tik.trigger.ui.autosave import clear, sidecar_path

        session = tmp_path / "rig.tr"
        side = sidecar_path(session)
        side.write_text("{}", encoding="utf-8")
        clear(session)
        assert not side.exists()

    def test_missing_sidecar_is_not_an_error(self, tmp_path):
        from tik.trigger.ui.autosave import clear

        clear(tmp_path / "rig.tr")

    def test_empty_path_is_not_an_error(self):
        from tik.trigger.ui.autosave import clear

        clear("")


class FakeWindow:
    """The three things AutosaveTimer asks a window for."""

    def __init__(self, path="", modified=True):
        self.path = path
        self.modified = modified
        self.written = []

    def autosave_target(self):
        return self.path

    def is_modified(self):
        return self.modified

    def write_autosave(self, target):
        self.written.append(target)


class TestAutosaveTimer:
    """Ticking writes only when it should."""

    def test_tick_writes_the_sidecar(self, qapp, tmp_path):
        from tik.trigger.ui.autosave import AutosaveTimer, sidecar_path

        window = FakeWindow(path=str(tmp_path / "rig.tr"))
        AutosaveTimer(window, 300).tick()
        assert window.written == [sidecar_path(tmp_path / "rig.tr")]

    def test_tick_skips_an_unmodified_session(self, qapp, tmp_path):
        from tik.trigger.ui.autosave import AutosaveTimer

        window = FakeWindow(path=str(tmp_path / "rig.tr"), modified=False)
        AutosaveTimer(window, 300).tick()
        assert window.written == []

    def test_tick_skips_a_session_with_no_path(self, qapp):
        from tik.trigger.ui.autosave import AutosaveTimer

        window = FakeWindow(path="")
        AutosaveTimer(window, 300).tick()
        assert window.written == []

    def test_a_failing_write_does_not_raise(self, qapp, tmp_path):
        from tik.trigger.ui.autosave import AutosaveTimer

        window = FakeWindow(path=str(tmp_path / "rig.tr"))

        def boom(target):
            raise OSError("disk full")

        window.write_autosave = boom
        AutosaveTimer(window, 300).tick()

    def test_reconfigure_stops_when_disabled(self, qapp, tmp_path, monkeypatch):
        from tik.trigger.config import prefs
        from tik.trigger.ui.autosave import AutosaveTimer

        monkeypatch.setattr(prefs.files, "autosave", False)
        timer = AutosaveTimer(FakeWindow(path=str(tmp_path / "rig.tr")), 300)
        timer.reconfigure()
        assert not timer.isActive()

    def test_reconfigure_starts_when_enabled(self, qapp, tmp_path, monkeypatch):
        from tik.trigger.config import prefs
        from tik.trigger.ui.autosave import AutosaveTimer

        monkeypatch.setattr(prefs.files, "autosave", True)
        monkeypatch.setattr(prefs.files, "autosave_interval", 60)
        timer = AutosaveTimer(FakeWindow(path=str(tmp_path / "rig.tr")), 300)
        timer.reconfigure()
        assert timer.isActive()
        assert timer.interval() == 60000
        timer.stop()


class TestWindowHooks:
    """What the window gives the timer, and what it does on open."""

    def test_target_is_empty_for_an_unsaved_session(self, window):
        assert window.autosave_target() == ""

    def test_write_autosave_does_not_move_the_session(self, window, tmp_path):
        session = window.session
        real = tmp_path / "rig.tr"
        session.save(str(real))
        window.write_autosave(tmp_path / "rig.tr.autosave")
        assert session.file_path == real

    def test_write_autosave_writes_the_document(self, window, tmp_path):
        window.session.save(str(tmp_path / "rig.tr"))
        target = tmp_path / "rig.tr.autosave"
        window.write_autosave(target)
        assert target.is_file()

    def test_saving_clears_the_sidecar(self, window, tmp_path):
        from tik.trigger.ui.autosave import sidecar_path

        real = tmp_path / "rig.tr"
        window.session.save(str(real))
        side = sidecar_path(real)
        side.write_text("{}", encoding="utf-8")
        window._save_view(window.current_view)
        assert not side.exists()

    def test_open_offers_a_newer_autosave(self, window, tmp_path, monkeypatch):
        from tik.shared.ui import feedback
        from tik.trigger.ui.autosave import sidecar_path

        real = tmp_path / "rig.tr"
        real.write_text("{}", encoding="utf-8")
        side = sidecar_path(real)
        time.sleep(0.01)
        side.write_text("{}", encoding="utf-8")
        os.utime(side, None)

        monkeypatch.setattr(
            feedback.Feedback, "pop_question", lambda *a, **k: "open autosave"
        )
        assert window._offer_recovery(str(real)) == str(side)

    def test_open_keeps_the_session_when_declined(self, window, tmp_path, monkeypatch):
        from tik.shared.ui import feedback
        from tik.trigger.ui.autosave import sidecar_path

        real = tmp_path / "rig.tr"
        real.write_text("{}", encoding="utf-8")
        side = sidecar_path(real)
        time.sleep(0.01)
        side.write_text("{}", encoding="utf-8")
        os.utime(side, None)

        monkeypatch.setattr(
            feedback.Feedback, "pop_question", lambda *a, **k: "open session"
        )
        assert window._offer_recovery(str(real)) == str(real)

    def test_no_prompt_without_a_sidecar(self, window, tmp_path, monkeypatch):
        from tik.shared.ui import feedback

        real = tmp_path / "rig.tr"
        real.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(
            feedback.Feedback,
            "pop_question",
            lambda *a, **k: pytest.fail("should not ask"),
        )
        assert window._offer_recovery(str(real)) == str(real)
