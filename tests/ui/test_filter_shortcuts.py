"""Typing in a filter must not fire the window's single-key shortcuts.

The graph binds 1/2/3 to the node display modes and F to Fit. A QAction
shortcut pre-empts the focused widget, so without claiming those keys back,
typing "arm1" in a filter changed the selected node's collapse mode.
"""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.shared.ui.filter_bar import FilterBar, FilterLineEdit
from tik.shared.ui.Qt import QtCore, QtGui
from tik.trigger.core import clear_registries, register_module
from tik.trigger.ui.graph.view import GraphView


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


def _override(widget, key, text):
    """Send the ShortcutOverride Qt sends before routing to a shortcut."""
    event = QtGui.QKeyEvent(
        QtCore.QEvent.ShortcutOverride, key, QtCore.Qt.NoModifier, text
    )
    widget.event(event)
    return event.isAccepted()


def test_a_filter_claims_a_digit_back_from_the_shortcut(qapp):
    edit = FilterLineEdit()
    assert _override(edit, QtCore.Qt.Key_1, "1") is True


def test_a_filter_claims_a_letter_back(qapp):
    edit = FilterLineEdit()
    assert _override(edit, QtCore.Qt.Key_F, "f") is True


def test_a_filter_leaves_a_real_chord_alone(qapp):
    """Ctrl+S must still save while the cursor is in a filter."""
    edit = FilterLineEdit()
    event = QtGui.QKeyEvent(
        QtCore.QEvent.ShortcutOverride,
        QtCore.Qt.Key_S,
        QtCore.Qt.ControlModifier,
        "s",
    )
    edit.event(event)
    assert event.isAccepted() is False


def test_a_filter_leaves_escape_alone(qapp):
    edit = FilterLineEdit()
    assert _override(edit, QtCore.Qt.Key_Escape, "") is False


def test_the_graph_search_box_claims_them_too(qapp):
    bar = FilterBar()
    assert _override(bar.line_edit, QtCore.Qt.Key_2, "2") is True


def test_a_nodes_port_filter_claims_them_too(qapp):
    scene = StubScene()
    handle = scene.add("toy_chain", name="arm", side="L")
    handle.copies = [
        {"slug": "", "name": "arm", "segments": 2},
        {"slug": "c1", "name": "arm1", "segments": 2},
        {"slug": "c2", "name": "arm2", "segments": 2},
    ]
    view = GraphView(guides=scene)
    view.rebuild()
    node = view.graph.nodes[handle.key]
    assert node.port_filter_widget is not None
    assert _override(node.port_filter_widget, QtCore.Qt.Key_1, "1") is True


def test_the_graph_ignores_keys_while_a_filter_has_focus(qapp):
    """Belt and braces for the path that is not a shortcut: the view's own
    key handler must defer to a text field that is being typed into."""
    scene = StubScene()
    scene.add("toy_chain", name="arm", side="L")
    view = GraphView(guides=scene)
    view.rebuild()
    view.show()
    try:
        # The offscreen platform hands out focus only to an activated
        # window, so the window has to be activated for this to mean
        # anything at all.
        qapp.setActiveWindow(view)
        view.filter_bar.line_edit.setFocus()
        qapp.processEvents()
        assert view.typing_in_a_filter() is True
    finally:
        view.close()


def test_the_graph_handles_keys_when_nothing_is_being_typed(qapp):
    scene = StubScene()
    scene.add("toy_chain", name="arm", side="L")
    view = GraphView(guides=scene)
    view.rebuild()
    view.show()
    try:
        qapp.setActiveWindow(view)
        view.setFocus()
        qapp.processEvents()
        assert view.typing_in_a_filter() is False
    finally:
        view.close()
