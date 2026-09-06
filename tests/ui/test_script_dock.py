"""The read-only Script viewer dock follows the selected script action."""

import pytest
from test_pipeline_ui import _stub_designer

from tik.trigger.core.registry import clear_registries, register_action
from tik.trigger.session import Session
from tik.trigger.ui.main import TriggerWindow
from tik.trigger.ui.script_dock import PLACEHOLDER, ScriptViewer


@pytest.fixture(autouse=True)
def _script_registered():
    clear_registries()
    from tik.trigger.actions.script.script import Script

    register_action("script", category="structure", scope="both")(Script)
    yield
    clear_registries()


@pytest.fixture
def window(qapp):
    win = TriggerWindow(designer_factory=_stub_designer)
    win.show()
    yield win
    # the session is dirty: never let the close dialog hang the run
    win.ask_save_discard = lambda session: "discard"
    win.close()


def _session_with_script(tmp_path, body, **settings):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "scripts" / "lib_v001.py").write_text(body, encoding="utf-8")
    session = Session()
    session.file_path = tmp_path / "hero_v001.tr"
    session.add("script", "lib", file_path="scripts/lib_v001.py", **settings)
    return session


def test_viewer_shows_file_then_code_and_a_placeholder_otherwise(qapp, tmp_path):
    session = _session_with_script(tmp_path, "def f():\n    pass\n", code="lib.f()")
    viewer = ScriptViewer()
    viewer.show_handle(session["lib"], session.directory)
    text = viewer.text.toPlainText()
    assert "def f():" in text and "lib.f()" in text
    assert text.index("def f()") < text.index("lib.f()")
    assert "lib_v001.py" in viewer.path_label.text()
    assert viewer.open_button.isEnabled()
    viewer.show_handle(None, "")
    assert viewer.text.toPlainText() == PLACEHOLDER
    assert not viewer.open_button.isEnabled()


def test_viewer_reloads_when_the_file_changes(qapp, tmp_path):
    session = _session_with_script(tmp_path, "A = 1\n")
    viewer = ScriptViewer()
    viewer.show_handle(session["lib"], session.directory)
    assert "A = 1" in viewer.text.toPlainText()
    (tmp_path / "scripts" / "lib_v001.py").write_text("A = 2\n", encoding="utf-8")
    viewer._reload()  # what the QFileSystemWatcher slot calls
    assert "A = 2" in viewer.text.toPlainText()


def test_viewer_reports_a_missing_file(qapp, tmp_path):
    session = Session()
    session.file_path = tmp_path / "hero_v001.tr"
    session.add("script", "lib", file_path="scripts/nope_v001.py", code="x = 1")
    viewer = ScriptViewer()
    viewer.show_handle(session["lib"], session.directory)
    assert "missing" in viewer.path_label.text()
    assert "x = 1" in viewer.text.toPlainText()


def test_the_window_hosts_the_dock_and_follows_the_selection(window):
    view = window.current_view
    assert window.script_dock.isHidden()
    window.script_action.trigger()
    assert window.script_dock.isVisible()
    assert window.script_action.isChecked()
    view.add_action("script")
    assert window.script_viewer.text.toPlainText() != PLACEHOLDER
    view.settings.set_handle(None)
    assert window.script_viewer.text.toPlainText() == PLACEHOLDER
    window.script_action.trigger()
    assert window.script_dock.isHidden()
