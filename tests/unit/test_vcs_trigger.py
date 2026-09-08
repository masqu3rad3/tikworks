"""The provider contract, its registry, and the host the outside world drives."""

from __future__ import annotations

import pytest

from tik.trigger import vcs
from tik.trigger.core.exceptions import (
    DuplicateRegistrationError,
    NotFoundError,
    VersionControlError,
)
from tik.trigger.session import Session
from tik.trigger.vcs.provider import Context, VersionControl

pytestmark = pytest.mark.usefixtures("trigger_plugins")


@pytest.fixture(autouse=True)
def _clean(trigger_plugins):
    # after the plug-ins, not before: ``load_plugins`` registers the shipped
    # folder provider, and every test here wants a registry holding only what
    # it put there itself
    vcs.clear_providers()
    vcs.set_preferred(None)
    vcs.host.detach()
    yield
    vcs.clear_providers()
    vcs.set_preferred(None)
    vcs.host.detach()


def _provider(name, is_available=True, **overrides):
    body = {"available": lambda self: is_available}
    body.update(overrides)
    cls = type(name.title(), (VersionControl,), body)
    return vcs.register_provider(name)(cls)


def test_register_stamps_name_and_refuses_a_second_class():
    cls = _provider("alpha")
    assert cls.name == "alpha"
    assert cls().display_label() == "Alpha"
    assert vcs.provider_names() == ["alpha"]
    with pytest.raises(DuplicateRegistrationError):
        vcs.register_provider("alpha")(type("Other", (VersionControl,), {}))
    with pytest.raises(NotFoundError):
        vcs.get_provider("missing")


def test_active_is_none_without_an_available_provider():
    assert vcs.active() is None
    _provider("off", is_available=False)
    assert vcs.active() is None


def test_active_picks_the_only_available_provider():
    _provider("off", is_available=False)
    _provider("on")
    assert vcs.active().name == "on"
    assert vcs.active() is vcs.active()  # one instance


def test_preference_breaks_ties_else_first_by_name():
    _provider("beta")
    _provider("alpha")
    assert vcs.active().name == "alpha"
    vcs.set_preferred("beta")
    assert vcs.active().name == "beta"
    vcs.set_preferred("nope")
    assert vcs.active().name == "alpha"


def test_defaults_are_detectable_no_ops():
    base = VersionControl()
    assert base.available() is False
    assert base.context("x.tr") is None
    assert base.browse("script", [".py"], "open") == ""
    assert base.new_version(vcs.host) == ""
    assert base.open(vcs.host) == ""
    assert base.publish_file("script", "a.py", vcs.host) is None
    assert base.launch(vcs.host) is None
    for verb in ("context", "browse", "new_version", "open", "publish_file", "launch"):
        assert base.supports(verb) is False
    cls = _provider("partial", browse=lambda self, kind, ext, mode: "picked.py")
    assert cls().supports("browse") is True
    assert cls().supports("open") is False


def test_context_is_a_plain_record():
    ctx = Context(label="hero / rig", version=3, is_latest=False, detail="…")
    assert ctx.version == 3 and ctx.is_latest is False


def test_headless_host_over_a_session(tmp_path):
    session = Session()
    assert vcs.host.session is None and vcs.host.session_path == ""
    vcs.host.attach(session=session)
    assert vcs.host.session is session
    assert vcs.host.is_modified is False
    saved = vcs.host.save_as(tmp_path / "hero.tr")
    assert saved == tmp_path / "hero.tr" and vcs.host.session_path.endswith("hero.tr")
    session.add("script", "a", code="pass")
    assert vcs.host.is_modified is True
    other = Session()
    other.save(tmp_path / "other.tr")
    vcs.host.open(tmp_path / "other.tr")
    assert vcs.host.session_path.endswith("other.tr")


def test_host_callables_win_over_the_session(tmp_path):
    calls = []
    vcs.host.attach(
        session=lambda: None,
        open=lambda path: calls.append(("open", str(path))),
        save_as=lambda path: calls.append(("save", str(path))) or path,
        refresh=lambda: calls.append(("refresh",)),
    )
    vcs.host.open("a.tr")
    vcs.host.save_as("b.tr")
    vcs.host.refresh()
    assert calls == [("open", "a.tr"), ("save", "b.tr"), ("refresh",)]


def test_headless_verbs_need_an_active_provider():
    with pytest.raises(VersionControlError):
        vcs.open()
    with pytest.raises(VersionControlError):
        vcs.publish_file("script", "a.py")
    seen = []
    _provider(
        "tm",
        open=lambda self, host: seen.append("open") or "x.tr",
        new_version=lambda self, host: seen.append("new") or "x_v002.tr",
        publish_file=lambda self, kind, path, host: seen.append((kind, str(path))),
        launch=lambda self, host: seen.append("launch"),
    )
    assert vcs.open() == "x.tr"
    assert vcs.new_version() == "x_v002.tr"
    vcs.publish_file("script", "a.py")
    vcs.launch()
    assert seen == ["open", "new", ("script", "a.py"), "launch"]


def test_kinds_are_re_exported():
    from tik.trigger.vcs import kinds

    assert kinds.SESSION == "session" and kinds.kind_for([".trg"]) == "guides"


def test_load_plugins_registers_the_shipped_folder_provider(monkeypatch):
    """The reference provider is a built-in, and inert until it is configured.

    ``load_plugins`` registers it every time, not only on the first import, so
    a cleared registry (this module's own fixture, or a reload) gets it back.
    """
    import tik.trigger as trigger

    vcs.clear_providers()
    assert "folder" not in vcs.provider_names()
    trigger.load_plugins()
    assert "folder" in vcs.provider_names()
    assert vcs.get_provider("folder").__name__ == "FolderProvider"
    # registering is not activating: without TRIGGER_FOLDER_VCS it is unusable
    monkeypatch.delenv("TRIGGER_FOLDER_VCS", raising=False)
    assert vcs.get_provider("folder")().available() is False
