"""The session owns its guides; the scene is a checkout of one at a time."""

import json

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core.exceptions import SessionError
from tik.trigger.guides import GuideScene
from tik.trigger.session import Session


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def test_a_session_has_a_stable_id():
    session = Session()
    assert session.session_id
    assert session.session_id == session.session_id
    assert session.document.meta["session_id"] == session.session_id


def test_capture_puts_the_scene_guides_into_the_document():
    session = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=2)
    assert session.capture_guides() is True
    assert session.document.guides["modules"][0]["name"] == "tail"


def test_capture_stamps_the_scene_with_the_session():
    session = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    session.capture_guides()
    assert session.owns_scene_guides is True


def test_checkout_projects_the_document_into_an_empty_scene():
    session = Session()
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    session.capture_guides()
    scene.clear()
    session.checkout_guides()
    restored = GuideScene()
    assert restored.get(handle.instance_id) is not None
    assert len(restored.guide_nodes(handle.instance_id)) == 3


def test_checkout_restores_authored_poses():
    session = Session()
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    target = scene.guide_nodes(handle.instance_id)[("segment", 0)]
    cmds.xform(target.long_name, worldSpace=True, translation=(4.0, 5.0, 6.0))
    scene.sync()
    session.capture_guides()
    cmds.file(new=True, force=True)
    session.checkout_guides()
    restored = GuideScene().guide_nodes(handle.instance_id)[("segment", 0)]
    placed = cmds.xform(restored.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([4.0, 5.0, 6.0])


def test_a_scene_stamped_for_another_session_is_reported_not_adopted():
    first = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    first.capture_guides()
    second = Session()
    assert second.owns_scene_guides is False
    with pytest.raises(SessionError, match="another session"):
        second.checkout_guides()


def test_forcing_a_checkout_takes_the_scene_over():
    first = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    first.capture_guides()
    second = Session()
    second.checkout_guides(force=True)
    assert second.owns_scene_guides is True
    assert GuideScene().instances() == []


def test_an_empty_scene_is_owned_by_nobody():
    assert Session().owns_scene_guides is True


def test_save_captures_the_guides_first(tmp_path):
    session = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    path = session.save(tmp_path / "hero.tr")
    data = json.loads(path.read_text())
    assert data["guides"]["modules"][0]["name"] == "tail"


def test_save_does_not_capture_another_sessions_guides(tmp_path):
    first = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    first.capture_guides()
    second = Session()
    second.save(tmp_path / "other.tr")
    assert second.document.guides == {}


def test_a_saved_session_round_trips_its_guides(tmp_path):
    session = Session()
    handle = GuideScene().add("fkchain", side="C", name="tail", segments=2)
    path = session.save(tmp_path / "hero.tr")
    cmds.file(new=True, force=True)
    reopened = Session.open(str(path))
    reopened.checkout_guides()
    assert GuideScene().get(handle.instance_id).name == "tail"


def test_guide_work_makes_the_session_dirty(tmp_path):
    """The close guard the Designer never had."""
    session = Session()
    path = session.save(tmp_path / "hero.tr")
    assert session.is_modified is False
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    session.capture_guides()
    assert session.is_modified is True


def test_capture_does_not_wipe_a_document_when_the_scene_is_empty(tmp_path):
    """Reopening a saved session in a fresh scene must not lose its guides."""
    session = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    path = session.save(tmp_path / "hero.tr")
    cmds.file(new=True, force=True)
    reopened = Session.open(str(path))
    assert reopened.capture_guides() is False
    assert reopened.document.guides["modules"][0]["name"] == "tail"


def test_capture_records_a_deletion_when_the_scene_is_ours():
    """Our own stamp means the scene is authoritative, empty or not."""
    session = Session()
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=1)
    session.capture_guides()
    assert session.document.guides["modules"]
    scene.remove(handle)
    session.capture_guides()
    assert session.document.guides["modules"] == []
