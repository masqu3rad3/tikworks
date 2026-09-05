"""Draw is manual, and it asks before it discards posing."""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.shared.ui import feedback
from tik.trigger.core import clear_registries, register_module
from tik.trigger.core.reconcile import GuideDiff, ModuleDiff
from tik.trigger.ui.designer import GuideDesigner


@pytest.fixture(autouse=True)
def _clean_handler():
    previous = feedback.set_handler(None)
    yield
    feedback.set_handler(previous)


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


@pytest.fixture
def designer(qapp):
    window = GuideDesigner(scene=StubScene())
    window.show()
    yield window
    window.close()


def _drifting(designer, instance_id):
    """Make the scene look like the rigger has dragged that module's guides."""
    diff = GuideDiff(modules={instance_id: ModuleDiff(instance_id, drifted=[("root", 0)])})
    designer.guides.diff = lambda: diff
    return diff


def _select(designer, handle):
    """Select through the tree -- that is where selected_handles() reads."""
    item = designer.item_for(handle.instance_id)
    designer.tree.setCurrentItem(item)
    item.setSelected(True)


def _draws(designer):
    return [call for call in designer.guides.calls if call[0] == "draw"]


def test_draw_all_draws_everything(designer):
    designer.draw_all()
    assert ("draw", None, "keep") in designer.guides.calls


def test_draw_selected_scopes_to_the_selection(designer):
    handle = designer.guides.add("toy_chain", name="tail", side="L")
    designer.refresh()
    _select(designer, handle)
    designer.draw_selected()
    assert ("draw", [handle.instance_id], "keep") in designer.guides.calls


def test_draw_selected_with_nothing_selected_does_nothing(designer):
    designer.tree.clearSelection()
    designer.draw_selected()
    assert _draws(designer) == []


def test_a_clean_scene_is_never_asked_about(designer):
    """No drift, no question -- and that covers the first draw too, since a
    module with no joints cannot have drifted."""
    asked = []
    feedback.set_handler(lambda *args: asked.append(args) or "cancel")
    designer.draw_all()
    assert asked == []
    assert _draws(designer)


def test_drift_asks_and_sync_is_the_default_answer(designer):
    handle = designer.guides.add("toy_chain", name="tail", side="L")
    _drifting(designer, handle.instance_id)
    asked = []

    def handler(kind, title, text, details, buttons):
        asked.append(buttons)
        return "yes"

    feedback.set_handler(handler)
    designer.draw_all()
    assert asked == [["yes", "discard", "cancel"]]
    assert ("draw", None, "keep") in designer.guides.calls


def test_discard_is_passed_down(designer):
    handle = designer.guides.add("toy_chain", name="tail", side="L")
    _drifting(designer, handle.instance_id)
    feedback.set_handler(lambda *args: "discard")
    designer.draw_all()
    assert ("draw", None, "discard") in designer.guides.calls


def test_cancel_draws_nothing(designer):
    handle = designer.guides.add("toy_chain", name="tail", side="L")
    _drifting(designer, handle.instance_id)
    feedback.set_handler(lambda *args: "cancel")
    designer.draw_all()
    assert _draws(designer) == []


def test_drift_outside_the_scope_is_not_asked_about(designer):
    """Drawing one module must not raise a question about another's posing."""
    kept = designer.guides.add("toy_chain", name="tail", side="L")
    dragged = designer.guides.add("toy_chain", name="neck", side="R")
    designer.refresh()
    _drifting(designer, dragged.instance_id)
    asked = []
    feedback.set_handler(lambda *args: asked.append(args) or "cancel")

    _select(designer, kept)
    designer.draw_selected()

    assert asked == []
    assert ("draw", [kept.instance_id], "keep") in designer.guides.calls
