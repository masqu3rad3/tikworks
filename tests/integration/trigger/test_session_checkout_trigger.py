"""Switching sessions swaps the scene's checkout."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core.exceptions import SessionError
from tik.trigger.session import Session


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def drawn_names():
    """The module names the scene is actually rendering, whoever owns them."""
    from tik.trigger.guides.snapshot import snapshot

    return {guide.instance_id for guide in snapshot()}


def test_switching_sessions_swaps_the_guides_in_the_scene():
    first = Session()
    first.checkout_guides()
    tail = first.guides.add("fkchain", side="C", name="tail", segments=1)

    second = Session()
    second.checkout_guides(force=True)  # takes the scene; first's guides go away
    body = second.guides.add("base", side="C", name="body")
    assert drawn_names() == {body.instance_id}

    Session.hand_over(second, first)
    assert drawn_names() == {tail.instance_id}


def test_a_checkout_round_trips_poses_between_two_sessions():
    first = Session()
    first.checkout_guides()
    handle = first.guides.add("fkchain", side="C", name="tail", segments=2)
    target = first.guides.guide_nodes(handle.instance_id)[("segment", 0)]
    cmds.xform(target.long_name, worldSpace=True, translation=(8.0, 1.0, 2.0))
    first.capture_guides()

    Session().checkout_guides(force=True)  # somebody else takes the scene
    first.checkout_guides(force=True)  # and we take it back

    restored = first.guides.guide_nodes(handle.instance_id)[("segment", 0)]
    placed = cmds.xform(restored.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([8.0, 1.0, 2.0])


def test_work_done_while_checked_out_belongs_to_that_session():
    """The question that was unanswerable with two tabs open."""
    first = Session()
    second = Session()

    first.checkout_guides()
    first.guides.add("fkchain", side="C", name="only_in_first", segments=1)

    Session.hand_over(first, second)
    second.guides.add("base", side="C", name="only_in_second")

    assert [entry.name for entry in first.document.guides.modules] == ["only_in_first"]
    assert [entry.name for entry in second.document.guides.modules] == ["only_in_second"]


def test_handing_over_captures_then_checks_out():
    first = Session()
    first.checkout_guides()
    first.guides.add("fkchain", side="C", name="tail", segments=1)

    second = Session()
    Session.hand_over(first, second)

    assert second.owns_scene_guides is True
    assert drawn_names() == set()
    assert [entry.name for entry in first.document.guides.modules] == ["tail"]


def test_handing_back_restores_the_first_sessions_guides():
    first = Session()
    first.checkout_guides()
    tail = first.guides.add("fkchain", side="C", name="tail", segments=1)
    second = Session()

    Session.hand_over(first, second)
    body = second.guides.add("base", side="C", name="body")
    Session.hand_over(second, first)

    assert drawn_names() == {tail.instance_id}
    assert [entry.name for entry in second.document.guides.modules] == ["body"]


def test_a_hand_over_from_a_session_that_does_not_hold_the_scene_is_still_safe():
    """The outgoing tab may never have been activated; taking over is not free."""
    holder = Session()
    holder.checkout_guides()
    holder.guides.add("fkchain", side="C", name="tail", segments=1)
    holder.capture_guides()

    never_activated = Session()
    incoming = Session()
    with pytest.raises(SessionError, match="another session"):
        Session.hand_over(never_activated, incoming)
