"""Draw-state aggregation: what a group row shows."""

from tik.trigger.ui.draw_state import DRAWN, NOT_DRAWN, STALE, worst_state


def test_stale_wins_over_everything():
    """A group row says the most urgent thing any member is saying."""
    assert worst_state([DRAWN, STALE, NOT_DRAWN]) == STALE


def test_drawn_wins_over_not_drawn():
    assert worst_state([NOT_DRAWN, DRAWN]) == DRAWN


def test_all_undrawn_is_undrawn():
    assert worst_state([NOT_DRAWN, NOT_DRAWN]) == NOT_DRAWN


def test_no_members_reads_as_undrawn():
    assert worst_state([]) == NOT_DRAWN


def test_it_takes_any_iterable():
    """The tree passes a generator over its members."""
    assert worst_state(state for state in (DRAWN, STALE)) == STALE
