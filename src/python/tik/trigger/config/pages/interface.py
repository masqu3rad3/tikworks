"""Window, log and graph preferences."""

from __future__ import annotations

from tik.core.fields import BoolField, ChoiceField, FieldGroup, IntField
from tik.shared.prefs import PrefPage, register_page

#: Log verbosity choices, in the order the combo box shows them.
VERBOSITY = ["Error", "Warning", "Info", "Debug"]

#: What a newly placed graph node collapses to.
COLLAPSE = ["Header Only", "Connected Plugs", "Everything"]


@register_page
class InterfacePrefs(PrefPage):
    """How the Trigger window looks and what it remembers."""

    name, label, order = "interface", "Interface", 10

    WINDOW = FieldGroup("Window")
    LOG = FieldGroup("Log")
    GRAPH = FieldGroup("Graph")

    restore_geometry = BoolField(
        True,
        group=WINDOW,
        label="Restore size and position",
        help="Reopen the Trigger window where you last left it.",
    )
    restore_dock_layout = BoolField(
        True,
        group=WINDOW,
        label="Restore dock layout",
        help="Reopen the Log and Script docks where and as they were.",
    )
    log_open_on_error = BoolField(
        True,
        group=LOG,
        label="Open log on error",
        help="Raise the Log dock automatically when a build reports an error.",
    )
    log_max_lines = IntField(
        2000,
        min=100,
        max=100000,
        group=LOG,
        label="Maximum lines",
        help="Lines kept in the Log dock before the oldest are dropped.",
    )
    log_verbosity = ChoiceField(
        "Info",
        VERBOSITY,
        group=LOG,
        label="Verbosity",
        help="Lowest message level the Log dock shows. Debug is the noisiest.",
    )
    graph_snap = BoolField(
        True,
        group=GRAPH,
        label="Snap to grid",
        help="Snap nodes to the grid while dragging them in the Guide Designer.",
    )
    graph_show_grid = BoolField(
        True,
        group=GRAPH,
        label="Show grid",
        help="Draw the background grid in the Guide Designer graph.",
    )
    graph_collapse_mode = ChoiceField(
        "Everything",
        COLLAPSE,
        group=GRAPH,
        label="New node collapse",
        help="How much of a node is shown when it first appears in the graph.",
    )
