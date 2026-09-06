"""Interface preferences reach the widgets that hold them."""

import pytest
from test_pipeline_ui import _stub_designer

from tik.shared.ui.Qt import QtCore
from tik.trigger.ui.main import TriggerWindow


@pytest.fixture
def window(qapp):
    made = TriggerWindow(designer_factory=_stub_designer)
    yield made
    made.close()


class TestWindowState:
    """Geometry blobs round-trip through QSettings, gated by the preference."""

    def test_save_writes_geometry(self, window):
        window.save_window_state()
        stored = QtCore.QSettings("tikworks", "trigger").value("window/geometry")
        assert stored is not None

    def test_save_writes_dock_state(self, window):
        window.save_window_state()
        stored = QtCore.QSettings("tikworks", "trigger").value("window/state")
        assert stored is not None

    def test_restore_is_a_no_op_when_disabled(self, window, monkeypatch):
        from tik.trigger.config import prefs

        window.save_window_state()
        monkeypatch.setattr(prefs.interface, "restore_geometry", False)
        monkeypatch.setattr(prefs.interface, "restore_dock_layout", False)
        window.restore_window_state()
        assert window.isEnabled()

    def test_restore_accepts_a_missing_blob(self, window):
        QtCore.QSettings("tikworks", "trigger").remove("window/geometry")
        QtCore.QSettings("tikworks", "trigger").remove("window/state")
        window.restore_window_state()
        assert window.isEnabled()

    def test_restore_applies_both_blobs_when_enabled(self, window, monkeypatch):
        """The offscreen platform never applies real geometry, so assert the
        calls rather than the resulting window size."""
        from tik.trigger.config import prefs

        window.save_window_state()
        monkeypatch.setattr(prefs.interface, "restore_geometry", True)
        monkeypatch.setattr(prefs.interface, "restore_dock_layout", True)
        called = []
        monkeypatch.setattr(
            window, "restoreGeometry", lambda blob: called.append("geometry")
        )
        monkeypatch.setattr(window, "restoreState", lambda blob: called.append("state"))
        window.restore_window_state()
        assert called == ["geometry", "state"]

    def test_restore_skips_the_blob_its_preference_disables(self, window, monkeypatch):
        from tik.trigger.config import prefs

        window.save_window_state()
        monkeypatch.setattr(prefs.interface, "restore_geometry", False)
        monkeypatch.setattr(prefs.interface, "restore_dock_layout", True)
        called = []
        monkeypatch.setattr(
            window, "restoreGeometry", lambda blob: called.append("geometry")
        )
        monkeypatch.setattr(window, "restoreState", lambda blob: called.append("state"))
        window.restore_window_state()
        assert called == ["state"]


class TestLogPreferences:
    """The log widget follows its preferences."""

    def test_max_lines_pushed_on_apply(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.interface, "log_max_lines", 321)
        window._on_prefs_applied(["interface.log_max_lines"])
        assert window.log.maximumBlockCount() == 321

    def test_verbosity_pushed_on_apply(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.interface, "log_verbosity", "Error")
        window._on_prefs_applied(["interface.log_verbosity"])
        window.log.append_message("chatty", "info")
        assert window.log.toPlainText().strip() == ""

    def test_error_raises_the_dock_when_enabled(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.interface, "log_open_on_error", True)
        window.log_dock.hide()
        window._on_error(RuntimeError("boom"), "build")
        assert window.log_dock.isVisibleTo(window)

    def test_error_leaves_the_dock_alone_when_disabled(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.interface, "log_open_on_error", False)
        window.log_dock.hide()
        window._on_error(RuntimeError("boom"), "build")
        assert not window.log_dock.isVisibleTo(window)

    def test_the_error_is_still_logged_when_the_dock_stays_shut(
        self, window, monkeypatch
    ):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.interface, "log_open_on_error", False)
        window._on_error(RuntimeError("boom"), "build")
        assert "boom" in window.log.toPlainText()


class TestLogWidgetLevels:
    """LogWidget filters by level."""

    def test_set_level_filters_lower_messages(self, qapp):
        from tik.trigger.ui.widgets import LogWidget

        widget = LogWidget()
        widget.set_level("Error")
        widget.append_message("chatty", "info")
        assert widget.toPlainText().strip() == ""

    def test_set_level_keeps_higher_messages(self, qapp):
        from tik.trigger.ui.widgets import LogWidget

        widget = LogWidget()
        widget.set_level("Error")
        widget.append_message("broken", "error")
        assert "broken" in widget.toPlainText()

    def test_default_level_shows_info(self, qapp):
        from tik.trigger.ui.widgets import LogWidget

        widget = LogWidget()
        widget.append_message("hello", "info")
        assert "hello" in widget.toPlainText()

    def test_debug_hidden_at_info_level(self, qapp):
        from tik.trigger.ui.widgets import LogWidget

        widget = LogWidget()
        widget.set_level("Info")
        widget.append_message("noisy", "debug")
        assert widget.toPlainText().strip() == ""

    def test_unknown_level_name_falls_back_to_info(self, qapp):
        from tik.trigger.ui.widgets import LogWidget

        widget = LogWidget()
        widget.set_level("Nonsense")
        widget.append_message("hello", "info")
        assert "hello" in widget.toPlainText()
