"""Everything a provider adds to the window, driven with a stub provider."""

from pathlib import Path

import pytest
from test_pipeline_ui import _stub_designer

from tik.shared.ui import feedback
from tik.trigger import vcs
from tik.trigger.core.document import BUILD
from tik.trigger.ui import vcs_ui
from tik.trigger.ui.main import TriggerWindow
from tik.trigger.vcs.provider import Context, VersionControl


class Stub(VersionControl):
    label = "Stub VCS"
    calls: list = []
    picked = "D:/vcs/picked.py"
    ctx = None

    def available(self):
        return True

    def context(self, session_path):
        return self.ctx

    def browse(self, kind, extensions, mode):
        self.calls.append(("browse", kind, list(extensions), mode))
        return self.picked

    def new_version(self, host):
        self.calls.append(("new_version", host.session_path))
        return host.session_path

    def open(self, host):
        self.calls.append(("open",))
        return ""

    def publish_file(self, kind, path, host):
        self.calls.append(("publish_file", kind, Path(path).name))

    def launch(self, host):
        self.calls.append(("launch",))


@pytest.fixture
def stub():
    import tik.trigger as trigger

    trigger.load_plugins()
    vcs.clear_providers()
    vcs.set_preferred(None)
    Stub.calls = []
    Stub.ctx = None
    Stub.picked = "D:/vcs/picked.py"
    vcs.register_provider("stub")(Stub)
    yield Stub
    vcs.clear_providers()
    vcs.host.detach()


@pytest.fixture
def window(qapp, stub):
    win = TriggerWindow(designer_factory=_stub_designer)
    win.show()
    yield win
    previous = feedback.set_handler(lambda *_args, **_kwargs: "discard")
    try:
        win.close()
    finally:
        feedback.set_handler(previous)


def _menu(window, title):
    for action in window.menu_bar.actions():
        if action.text() == title:
            return action.menu()
    raise AssertionError(title)


def _entries(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def test_without_a_provider_nothing_is_added(qapp):
    vcs.clear_providers()
    win = TriggerWindow(designer_factory=_stub_designer)
    try:
        assert win.vcs_menu is None
        assert win.status.text("vcs") == ""
        # the strip must look exactly as it did before version control: no
        # empty label, and no dangling separator in front of it
        assert win.status.labels["vcs"].isHidden()
        assert win.status.separators["vcs"].isHidden()
        assert vcs_ui.form_vcs_slot(lambda: "") is None
    finally:
        win.close()
        vcs.host.detach()


def test_the_window_attaches_itself_as_the_host(window):
    assert vcs.host.session is window.session
    window.close()
    window.teardown()
    assert vcs.host.session is None


def test_file_menu_gets_the_provider_submenu(window, stub):
    file_menu = _menu(window, "&File")
    assert "Stub VCS" in _entries(file_menu)
    entries = _entries(window.vcs_menu)
    assert entries == [
        "Open from Stub VCS…",
        "Save New Version",
        "Publish…",
        "Open Stub VCS",
    ]
    publish = next(a for a in window.vcs_menu.actions() if a.text() == "Publish…")
    assert publish.isEnabled() is False  # no publish action in the session
    window.session.publish.add("publish", "out")
    # opening the File menu re-asks the session: an edit never leaves it stale
    file_menu.aboutToShow.emit()
    assert publish.isEnabled() is True
    window.session.publish.remove("out")
    file_menu.aboutToShow.emit()
    assert publish.isEnabled() is False
    next(
        a for a in window.vcs_menu.actions() if a.text() == "Open from Stub VCS…"
    ).trigger()
    next(a for a in window.vcs_menu.actions() if a.text() == "Open Stub VCS").trigger()
    assert ("open",) in stub.calls and ("launch",) in stub.calls


def test_status_chip_follows_the_context(window, stub, tmp_path):
    stub.ctx = None
    window.session.save(tmp_path / "hero.tr")
    vcs_ui.refresh_chip(window)
    assert window.status.text("vcs") == "Not a Stub VCS work"
    stub.ctx = Context(label="hero / rig", version=3, is_latest=False)
    vcs_ui.refresh_chip(window)
    assert window.status.text("vcs") == "hero / rig · v003"
    assert "#f0b45c" in window.status.labels["vcs"].styleSheet()
    stub.ctx = Context(label="hero / rig", version=4, is_latest=True)
    vcs_ui.refresh_chip(window)
    assert "#9fd8b3" in window.status.labels["vcs"].styleSheet()
    assert not window.status.labels["vcs"].isHidden()


def test_a_provider_that_raises_does_not_break_the_window(
    window, stub, tmp_path, monkeypatch
):
    """``context`` is third-party code on the save path; it may not take it down."""

    def _boom(_self, _session_path):
        raise RuntimeError("the server is down")

    monkeypatch.setattr(stub, "context", _boom)
    window.session.save(tmp_path / "hero.tr")
    window._update_title()  # the hot path: every tab change, save and open
    assert window.status.text("vcs") == "Not a Stub VCS work"


def test_a_folder_field_is_never_offered_for_publish(window, stub, tmp_path):
    from tik.core.fields import FileField
    from tik.shared.ui.versioned_field import VersionedFileField

    field = FileField("", mode="dir")
    widget = VersionedFileField([], mode="dir")
    widget.setValue(str(tmp_path))
    assert vcs_ui.field_actions("folder", field, widget, str(tmp_path)) == []


def test_field_actions_browse_and_publish(window, stub, tmp_path):
    from tik.core.fields import FileField
    from tik.shared.ui.versioned_field import VersionedFileField

    field = FileField("", extensions=[".py"], kind="script")
    widget = VersionedFileField([".py"])
    stub.picked = r"D:\vcs\picked.py"
    entries = vcs_ui.field_actions("file_path", field, widget, str(tmp_path))
    assert [text for text, _ in entries] == ["Browse Stub VCS…"]
    entries[0][1]()
    assert widget.value() == "D:/vcs/picked.py"  # backslashes normalised
    assert stub.calls[-1] == ("browse", "script", [".py"], "open")

    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    widget.setValue("a.py")
    entries = vcs_ui.field_actions("file_path", field, widget, str(tmp_path))
    assert [text for text, _ in entries] == [
        "Browse Stub VCS…",
        "Publish a.py to Stub VCS…",
    ]
    entries[1][1]()
    assert stub.calls[-1] == ("publish_file", "script", "a.py")


def test_settings_panel_file_fields_carry_the_button(window, stub, tmp_path):
    window.session.save(tmp_path / "hero.tr")
    handle = window.session.add("script", "lib", file_path="a.py")
    view = window.current_view
    view.refresh()
    view.select_path(handle.path)
    widget = view.settings.form.widget("file_path")
    assert widget.vcs_button is not None
    assert widget.vcs_button.toolTip() == "From Stub VCS"


def test_pipeline_right_click_lists_the_publishable_files(window, stub, tmp_path):
    window.session.save(tmp_path / "hero.tr")
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    handle = window.session.add("script", "lib", file_path="a.py")
    view = window.current_view
    labels = [a.text() for a in view.context_menu_actions(BUILD, handle)]
    assert "Publish to Stub VCS" in labels
    submenu = next(
        a for a in view._menu.actions() if a.text() == "Publish to Stub VCS"
    ).menu()
    assert _entries(submenu) == ["a.py"]
    submenu.actions()[0].trigger()
    assert stub.calls[-1] == ("publish_file", "script", "a.py")
    inline = window.session.add("script", "inline", code="pass")
    labels = [a.text() for a in view.context_menu_actions(BUILD, inline)]
    assert "Publish to Stub VCS" not in labels


def test_pick_file_offers_the_provider(window, stub, monkeypatch):
    stub.picked = "D:/vcs/guides.trg"
    monkeypatch.setattr(vcs_ui, "_popup", lambda parent, entries: entries[1][1]())
    assert vcs_ui.pick_file(window, "guides", [".trg"], "open") == "D:/vcs/guides.trg"
    assert stub.calls[-1] == ("browse", "guides", [".trg"], "open")


def test_a_provider_that_never_answers_context_gets_no_chip(window, stub, tmp_path):
    """No ``context`` is no verdict: the chip says nothing rather than "not a work"."""

    class Quiet(VersionControl):
        label = "Quiet VCS"

        def available(self):
            return True

    vcs.clear_providers()
    vcs.register_provider("quiet")(Quiet)
    window.session.save(tmp_path / "hero.tr")
    vcs_ui.refresh_chip(window)
    assert vcs_ui.provider().display_label() == "Quiet VCS"
    assert window.status.text("vcs") == ""
    assert window.status.labels["vcs"].isHidden()
    assert window.status.separators["vcs"].isHidden()
