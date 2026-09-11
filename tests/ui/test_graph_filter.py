"""The graph's search overlay: find a node without losing the picture."""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module
from tik.trigger.ui.graph.constants import FILTERED_OPACITY
from tik.trigger.ui.graph.view import GraphView


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


@pytest.fixture
def view(qapp):
    scene = StubScene()
    scene.add("toy_chain", name="index", side="L")
    scene.add("toy_chain", name="thumb", side="L")
    scene.add("toy_root", name="spine")
    made = GraphView(guides=scene)
    made.rebuild()
    made.show()
    yield made
    made.close()


def _dimmed(view):
    return sorted(key for key, node in view.graph.nodes.items() if node.filtered)


def test_an_empty_filter_dims_nothing(view):
    assert _dimmed(view) == []


def test_typing_dims_what_does_not_match(view):
    view.filter_bar.set_text("thumb")
    view.apply_filter()
    assert _dimmed(view) == ["L_index", "spine"]


def test_a_match_keeps_full_opacity(view):
    view.filter_bar.set_text("thumb")
    view.apply_filter()
    assert view.graph.nodes["L_thumb"].opacity() == 1.0
    assert view.graph.nodes["spine"].opacity() == FILTERED_OPACITY


def test_clearing_the_filter_restores_everything(view):
    view.filter_bar.set_text("thumb")
    view.apply_filter()
    view.filter_bar.clear()
    view.apply_filter()
    assert _dimmed(view) == []
    assert view.graph.nodes["spine"].opacity() == 1.0


def test_a_committed_keyword_filters_too(view):
    view.filter_bar.set_text("index")
    view.filter_bar.commit()
    assert _dimmed(view) == ["L_thumb", "spine"]


def test_the_filter_matches_the_module_type_as_well_as_the_name(view):
    view.filter_bar.set_text("Toy Root")
    view.apply_filter()
    assert "spine" not in _dimmed(view)


def test_filtering_hides_nothing_and_moves_nothing(view):
    """A hidden node would take its wires with it and leave the graph
    claiming connections that are not there."""
    before = {key: node.pos() for key, node in view.graph.nodes.items()}
    view.filter_bar.set_text("thumb")
    view.apply_filter()
    for key, node in view.graph.nodes.items():
        assert node.isVisible()
        assert node.pos() == before[key]


def test_a_rebuild_keeps_the_filter_applied(view):
    view.filter_bar.set_text("thumb")
    view.apply_filter()
    view.rebuild()
    assert _dimmed(view) == ["L_index", "spine"]


def test_focus_filter_readies_the_box_to_type_over(view):
    """Asserted through the selection rather than hasFocus(): the offscreen
    platform does not hand out focus without an activated window, and the
    behaviour that matters is that the next keystroke replaces the term."""
    view.filter_bar.set_text("thumb")
    view.focus_filter()
    assert view.filter_bar.line_edit.selectedText() == "thumb"


def test_the_bar_stays_in_the_corner_when_the_view_resizes(view):
    """The placement lives in the view's one resizeEvent; a second
    definition of it would silently win and never run."""
    from tik.trigger.ui.graph.constants import FILTER_MARGIN

    view.resize(900, 700)
    assert view.filter_bar.pos().x() == FILTER_MARGIN
    assert view.filter_bar.pos().y() == FILTER_MARGIN
