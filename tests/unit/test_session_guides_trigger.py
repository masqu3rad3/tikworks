"""The session owns its guides; the Maya scene only renders them."""

import json

import pytest
from maya import cmds

from tik.trigger.core.exceptions import SessionError
from tik.trigger.guides import GuideScene
from tik.trigger.session import Session

pytestmark = pytest.mark.usefixtures("trigger_plugins")


def test_a_session_hands_out_a_guide_scene_bound_to_itself():
    session = Session()
    scene = session.guides
    assert scene is session.guides  # built once
    assert scene.document is session.document.guides  # the same object


def test_an_unbound_guide_scene_owns_its_own_document():
    """Scripting without a session still works, and sees nobody else's guides."""
    session = Session()
    session.guides.add("fkchain", side="C", name="tail", segments=1)
    assert GuideScene().instances() == []


def test_a_session_has_a_stable_id():
    session = Session()
    assert session.session_id == session.session_id
    assert session.document.meta["session_id"] == session.session_id


# ----------------------------------------------------------------- undo
def test_a_structural_edit_pushes_an_undo_step():
    session = Session()
    session.guides.add("fkchain", side="C", name="tail", segments=1)
    assert session.can_undo is True
    session.undo()
    assert session.document.guides.modules == []


def test_undo_then_redo_puts_the_module_back():
    session = Session()
    session.guides.add("fkchain", side="C", name="tail", segments=1)
    session.undo()
    session.redo()
    assert [entry.name for entry in session.document.guides.modules] == ["tail"]


def test_a_settings_change_undoes():
    session = Session()
    handle = session.guides.add("fkchain", side="C", name="tail", segments=2)
    handle.segments = 5
    session.undo()
    assert session.document.guides.module(handle.instance_id).settings["segments"] == 2


def test_snapshot_replaces_the_guides_in_one_undo_step():
    """A real divergence: a module the document knows but the scene never drew."""
    session = Session()
    session.guides.add("fkchain", side="C", name="original", segments=1)
    extra = session.guides.add("fkchain", side="C", name="extra", segments=1)
    # its guides never rendered again -- exactly what Snapshot must drop
    session.guides.delete_guides(extra.instance_id)
    assert [entry.name for entry in session.document.guides.modules] == [
        "original",
        "extra",
    ]

    document, _report = session.guides.snapshot_from_scene()
    session.snapshot_guides_from_scene(document)
    assert [entry.name for entry in session.document.guides.modules] == ["original"]

    session.undo()
    assert [entry.name for entry in session.document.guides.modules] == [
        "original",
        "extra",
    ]


# --------------------------------------------------------------- the scene
def test_guides_survive_a_new_scene():
    """The failure this whole design exists to remove."""
    session = Session()
    handle = session.guides.add("fkchain", side="C", name="tail", segments=1)
    cmds.file(new=True, force=True)
    assert [entry.name for entry in session.document.guides.modules] == ["tail"]
    assert session.guides.get(handle.instance_id).name == "tail"


def test_a_new_scene_redraws_the_guides_on_the_next_sync():
    session = Session()
    handle = session.guides.add("fkchain", side="C", name="tail", segments=2)
    cmds.file(new=True, force=True)
    session.guides.sync()
    assert len(session.guides.guide_nodes(handle.instance_id)) == 3


def test_capture_against_an_empty_scene_leaves_the_modules_alone():
    """Capture cannot add or remove a module, so it cannot wipe the document."""
    session = Session()
    session.guides.add("fkchain", side="C", name="tail", segments=1)
    cmds.file(new=True, force=True)
    session.capture_guides()
    assert [entry.name for entry in session.document.guides.modules] == ["tail"]


def test_capture_records_a_moved_guide():
    session = Session()
    handle = session.guides.add("fkchain", side="C", name="tail", segments=1)
    target = session.guides.guide_nodes(handle.instance_id)[("segment", 0)]
    cmds.xform(target.long_name, worldSpace=True, translation=(7.0, 8.0, 9.0))
    session.capture_guides()
    record = session.document.guides.module(handle.instance_id).guide("segment", 0)
    assert record.position == pytest.approx((7.0, 8.0, 9.0))


# ------------------------------------------------------------- checkout
def test_a_scene_stamped_for_another_session_is_reported_not_adopted():
    first = Session()
    first.guides.add("fkchain", side="C", name="tail", segments=1)
    first.capture_guides()
    second = Session()
    assert second.owns_scene_guides is False
    with pytest.raises(SessionError, match="another session"):
        second.checkout_guides()


def test_forcing_a_checkout_takes_the_scene_over():
    first = Session()
    first.guides.add("fkchain", side="C", name="tail", segments=1)
    first.capture_guides()
    second = Session()
    second.checkout_guides(force=True)
    assert second.owns_scene_guides is True
    assert first.guides.guide_nodes(first.document.guides.modules[0].instance_id) == {}


def test_handing_over_captures_then_checks_out():
    first = Session()
    first.checkout_guides()
    first.guides.add("fkchain", side="C", name="tail", segments=1)
    second = Session()
    Session.hand_over(first, second)
    assert second.owns_scene_guides is True
    # the outgoing session kept its work
    assert [entry.name for entry in first.document.guides.modules] == ["tail"]


# ----------------------------------------------------------------- files
def test_save_writes_the_guides(tmp_path):
    session = Session()
    session.guides.add("fkchain", side="C", name="tail", segments=1)
    path = session.save(tmp_path / "hero.tr")
    data = json.loads(path.read_text())
    assert data["guides"]["modules"][0]["name"] == "tail"


def test_a_saved_session_round_trips_its_guides(tmp_path):
    session = Session()
    handle = session.guides.add("fkchain", side="C", name="tail", segments=2)
    path = session.save(tmp_path / "hero.tr")
    cmds.file(new=True, force=True)
    reopened = Session.open(str(path))
    assert reopened.document.guides.module(handle.instance_id).name == "tail"
    reopened.checkout_guides()
    assert len(reopened.guides.guide_nodes(handle.instance_id)) == 3


def test_guide_work_makes_the_session_dirty(tmp_path):
    """The close guard the Designer never had."""
    session = Session()
    session.save(tmp_path / "hero.tr")
    assert session.is_modified is False
    session.guides.add("fkchain", side="C", name="tail", segments=1)
    assert session.is_modified is True
