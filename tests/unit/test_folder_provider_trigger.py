"""FolderProvider: the shipped reference provider (a versioned folder tree)."""

import pytest

from tik.trigger import vcs
from tik.trigger.session import Session
from tik.trigger.vcs.folder import FolderProvider


@pytest.fixture
def provider(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIGGER_FOLDER_VCS", str(tmp_path / "vcs"))
    (tmp_path / "vcs").mkdir()
    made = FolderProvider()
    vcs.host.detach()
    yield made
    vcs.host.detach()


def test_available_only_when_the_root_exists(tmp_path, monkeypatch):
    monkeypatch.delenv("TRIGGER_FOLDER_VCS", raising=False)
    assert FolderProvider().available() is False
    monkeypatch.setenv("TRIGGER_FOLDER_VCS", str(tmp_path / "missing"))
    assert FolderProvider().available() is False
    (tmp_path / "missing").mkdir()
    assert FolderProvider().available() is True


def test_context_reads_the_version_suffix(provider, tmp_path):
    folder = provider.root / "sessions"
    folder.mkdir()
    (folder / "hero_v001.tr").write_text("{}", encoding="utf-8")
    (folder / "hero_v002.tr").write_text("{}", encoding="utf-8")
    assert provider.context(str(tmp_path / "elsewhere.tr")) is None
    older = provider.context(str(folder / "hero_v001.tr"))
    assert older.label == "hero" and older.version == 1 and older.is_latest is False
    latest = provider.context(str(folder / "hero_v002.tr"))
    assert latest.version == 2 and latest.is_latest is True


def test_new_version_saves_the_next_number_under_sessions(provider, tmp_path):
    session = Session()
    session.save(tmp_path / "work" / "hero.tr")
    vcs.host.attach(session=session)
    first = provider.new_version(vcs.host)
    assert first.endswith("sessions/hero_v001.tr")
    second = provider.new_version(vcs.host)
    assert second.endswith("sessions/hero_v002.tr")
    assert (provider.root / "sessions" / "hero_v002.tr").exists()


def test_publish_file_copies_under_its_kind_versioned(provider, tmp_path):
    script = tmp_path / "a.py"
    script.write_text("x", encoding="utf-8")
    provider.publish_file("script", script, vcs.host)
    provider.publish_file("script", script, vcs.host)
    names = sorted(item.name for item in (provider.root / "script").iterdir())
    assert names == ["a_v001.py", "a_v002.py"]


def test_browse_and_open_go_through_the_host_feedback(provider, tmp_path):
    target = provider.root / "sessions" / "hero_v001.tr"
    target.parent.mkdir()
    Session().save(target)
    opened = []

    class _Feedback:
        def browse_open(self, caption, start, extensions):
            assert start.endswith("sessions") and extensions == (".tr",)
            return str(target)

        def browse_save(self, caption, start, extensions):
            return f"{start}/new.tr"

    vcs.host.attach(session=lambda: None, open=opened.append, feedback=_Feedback)
    assert provider.browse("session", [".tr"], "open") == str(target)
    assert provider.open(vcs.host) == str(target)
    assert opened == [str(target)]


def test_browse_asks_for_a_save_dialog_when_the_field_saves(provider):
    """``mode`` is the field's, not the provider's: a save field saves."""
    seen = []

    class _Feedback:
        def browse_open(self, caption, start, extensions):
            seen.append(("open", start))
            return ""

        def browse_save(self, caption, start, extensions):
            seen.append(("save", start))
            return f"{start}/hero.trg"

    vcs.host.attach(session=lambda: None, feedback=_Feedback)
    saved = provider.browse("guides", [".trg"], "save")
    assert saved.endswith("guides/hero.trg")
    assert provider.browse("guides", [".trg"], "open") == ""
    assert [mode for mode, _start in seen] == ["save", "open"]
    assert all(start.endswith("guides") for _mode, start in seen)
