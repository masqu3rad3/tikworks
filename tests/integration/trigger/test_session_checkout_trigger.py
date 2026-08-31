"""Switching sessions swaps the scene's checkout."""

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


def test_switching_sessions_swaps_the_guides_in_the_scene():
    first = Session()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    first.capture_guides()

    second = Session()
    second.checkout_guides(force=True)  # takes the scene; first's guides go away
    GuideScene().add("base", side="C", name="body")
    second.capture_guides()
    assert GuideScene().find("tail") is None

    first.checkout_guides(force=True)
    assert GuideScene().find("tail") is not None
    assert GuideScene().find("body") is None


def test_a_checkout_round_trips_poses_between_two_sessions():
    first = Session()
    scene = GuideScene()
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    target = scene.guide_nodes(handle.instance_id)[("segment", 0)]
    cmds.xform(target.long_name, worldSpace=True, translation=(8.0, 1.0, 2.0))
    scene.sync()
    first.capture_guides()

    Session().checkout_guides(force=True)  # somebody else takes the scene
    first.checkout_guides(force=True)  # and we take it back

    restored = GuideScene().guide_nodes(handle.instance_id)[("segment", 0)]
    placed = cmds.xform(restored.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([8.0, 1.0, 2.0])


def test_work_done_while_checked_out_belongs_to_that_session():
    """The question that was unanswerable with two tabs open."""
    first = Session()
    second = Session()
    first.checkout_guides(force=True)
    GuideScene().add("fkchain", side="C", name="only_in_first", segments=1)
    first.capture_guides()

    second.checkout_guides(force=True)
    GuideScene().add("base", side="C", name="only_in_second")
    second.capture_guides()

    assert [entry.name for entry in first.document.guides.modules] == ["only_in_first"]
    assert [entry.name for entry in second.document.guides.modules] == ["only_in_second"]


def test_handing_the_scene_over_captures_then_checks_out():
    """Switching tabs: the outgoing session keeps its work, the incoming one
    gets the scene. No force needed -- nothing is at risk once captured."""
    first = Session()
    first.checkout_guides()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)

    second = Session()
    Session.hand_over(first, second)

    assert second.owns_scene_guides is True
    assert GuideScene().find("tail") is None
    # and the outgoing session kept what was authored while it held the scene
    assert [entry.name for entry in first.document.guides.modules] == ["tail"]


def test_handing_back_restores_the_first_sessions_guides():
    first = Session()
    first.checkout_guides()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    second = Session()

    Session.hand_over(first, second)
    GuideScene().add("base", side="C", name="body")
    Session.hand_over(second, first)

    assert GuideScene().find("tail") is not None
    assert GuideScene().find("body") is None
    assert [entry.name for entry in second.document.guides.modules] == ["body"]


def test_a_hand_over_from_a_session_that_does_not_hold_the_scene_is_still_safe():
    """The outgoing tab may never have been activated; taking over is fine."""
    holder = Session()
    holder.checkout_guides()
    GuideScene().add("fkchain", side="C", name="tail", segments=1)
    holder.capture_guides()

    never_activated = Session()
    incoming = Session()
    # `never_activated` does not own the scene, so its capture is a no-op --
    # and the hand-over must not then force away somebody else's work
    with pytest.raises(SessionError, match="another session"):
        Session.hand_over(never_activated, incoming)
