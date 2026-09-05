"""The three draw states, and the ink each one gets.

Shared by the guide tree's dot and the graph node's stripe. It lives here
rather than in either of them because the two panes must say the same thing:
they are fed from one ``GuideDiff`` and paint from one palette, so they cannot
drift into disagreeing about what is in the scene.

    not drawn    in the session, absent from Maya. The ordinary state of a new
                 module, and of every module in a session you just opened --
                 not damage, and never coloured as a warning.
    drawn        the joints match the document's structure.
    out of date  the joints are there and no longer match. Only this one earns
                 the accent: the scene *contradicts* the session.
"""

from __future__ import annotations

NOT_DRAWN = "not_drawn"
DRAWN = "drawn"
STALE = "stale"

#: Marker colour per state. NOT_DRAWN is stroked as a ring rather than filled
#: -- an outline for something that is not there reads before any legend does.
COLORS = {
    NOT_DRAWN: "#5a5a5a",
    DRAWN: "#3f3f3f",
    STALE: "#FE7E00",
}

#: Text colour for a row whose module has no rendering.
DIMMED_TEXT = "#757575"

TOOLTIPS = {
    NOT_DRAWN: "Not drawn — this module has no guides in the scene.",
    DRAWN: "Drawn — the scene matches the session.",
    STALE: "Out of date — the guides in the scene no longer match the session.",
}


def state_of(module_diff) -> str:
    """The state one :class:`~tik.trigger.core.reconcile.ModuleDiff` is in."""
    if module_diff is None:
        return DRAWN
    if module_diff.absent:
        return NOT_DRAWN
    return STALE if module_diff.is_stale else DRAWN


def states_from(diff) -> dict:
    """``{instance_id: state}`` for a whole :class:`GuideDiff`.

    The single place the diff becomes something to paint, so the tree and the
    graph cannot classify the same module differently.
    """
    return {
        instance_id: state_of(module_diff)
        for instance_id, module_diff in diff.modules.items()
    }
