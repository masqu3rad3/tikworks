"""The graph's search overlay grows to hold its keyword pills.

Enter commits a keyword into a pill. The overlay was pinned to a fixed
width, so the pills ran outside the box the moment there were two.
"""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module
from tik.trigger.ui.graph.constants import FILTER_MARGIN, FILTER_WIDTH
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
    scene.add("toy_chain", name="shoulder", side="L")
    scene.add("toy_chain", name="clavicle", side="L")
    made = GraphView(guides=scene)
    made.rebuild()
    made.resize(900, 600)
    made.show()
    yield made
    made.close()


def _commit(view, qapp, term):
    view.filter_bar.set_text(term)
    view.filter_bar.commit()
    qapp.processEvents()


def test_an_empty_bar_keeps_its_base_width(view):
    assert view.filter_bar.width() == FILTER_WIDTH


def test_the_bar_grows_to_hold_its_pills(view, qapp):
    before = view.filter_bar.width()
    _commit(view, qapp, "shoulder")
    _commit(view, qapp, "clavicle")
    assert view.filter_bar.width() > before


def test_no_pill_is_left_outside_the_box(view, qapp):
    """The bug: the pill row wanted more width than the box allowed."""
    _commit(view, qapp, "shoulder")
    _commit(view, qapp, "clavicle")
    wanted = view.filter_bar._pill_row.sizeHint().width()
    assert view.filter_bar.width() >= wanted


def test_the_bar_never_runs_off_the_canvas(view, qapp):
    for term in ("shoulder", "clavicle", "scapula", "humerus", "sternum"):
        _commit(view, qapp, term)
    assert view.filter_bar.width() <= view.viewport().width() - FILTER_MARGIN * 2


def test_clearing_shrinks_it_back(view, qapp):
    """Back to about the base width, not exactly it: QLineEdit's own hint
    grows by the width of its clear button once text has been typed and
    does not give it back. What matters is that the pills' width goes."""
    _commit(view, qapp, "shoulder")
    _commit(view, qapp, "clavicle")
    grown = view.filter_bar.width()
    view.filter_bar.clear()
    qapp.processEvents()
    assert view.filter_bar.width() < grown
    assert view.filter_bar.width() <= FILTER_WIDTH + 32
    assert not view.filter_bar._pill_row.isVisible()


def test_it_stays_in_the_corner_as_it_grows(view, qapp):
    _commit(view, qapp, "shoulder")
    _commit(view, qapp, "clavicle")
    assert view.filter_bar.pos().x() == FILTER_MARGIN
    assert view.filter_bar.pos().y() == FILTER_MARGIN


def test_a_committed_pill_still_filters(view, qapp):
    _commit(view, qapp, "shoulder")
    dimmed = [key for key, node in view.graph.nodes.items() if node.filtered]
    assert dimmed == ["L_clavicle"]
