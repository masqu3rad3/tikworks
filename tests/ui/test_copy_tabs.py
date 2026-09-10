"""The copy tab bar. It edits a settings field and nothing else.

The rule the superseded group design broke, and the reason this file exists:
the Designer has exactly one selectable thing and the tree owns the selection.
Switching a tab must not touch it.
"""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module
from tik.trigger.ui.designer import GuideDesigner


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


def _select(designer, handle):
    """Select through the tree -- that is where selected_handles() reads."""
    designer.refresh()
    item = designer.item_for(handle.instance_id)
    designer.tree.setCurrentItem(item)
    item.setSelected(True)


def _chain(designer, name="fingers"):
    handle = designer.guides.add("toy_chain", name=name, side="L")
    _select(designer, handle)
    return handle


def _rows(handle):
    return handle.settings.get("copies") or []


# --------------------------------------------------------------- the bar
def test_an_untouched_module_shows_one_tab(designer):
    _chain(designer, name="arm")
    assert designer.tab_bar.count() == 1
    assert designer.tab_bar.tabText(0) == "arm"
    assert designer.add_copy_button.isEnabled()


def test_plus_adds_a_copy_and_selects_its_tab(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    assert designer.tab_bar.count() == 2
    assert designer.tab_bar.currentIndex() == 1
    assert len(_rows(handle)) == 2


def test_the_new_copy_carries_the_current_copys_values(designer):
    """A fifth finger wants the fourth finger's settings, not the module's."""
    handle = _chain(designer)
    handle.segments = 7
    _select(designer, handle)
    designer._on_add_copy()
    assert _rows(handle)[1]["segments"] == 7


def test_the_new_copy_gets_a_free_name(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    names = [row["name"] for row in _rows(handle)]
    assert len(set(names)) == 2


def test_the_new_copy_gets_a_fresh_slug(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    slugs = [row["slug"] for row in _rows(handle)]
    assert slugs[0] == ""
    assert slugs[1] == "c1"


def test_renaming_a_tab_renames_the_copy(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer._on_copy_renamed(1, "thumb")
    assert _rows(handle)[1]["name"] == "thumb"
    assert designer.tab_bar.tabText(1) == "thumb"


def test_removing_a_copy_drops_its_row(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer.tab_bar.setCurrentIndex(1)
    designer._on_remove_copy()
    assert len(_rows(handle)) == 1
    assert designer.tab_bar.count() == 1


def test_the_last_copy_cannot_be_removed(designer):
    """A module always has at least one copy: itself."""
    handle = _chain(designer)
    designer._on_remove_copy()
    assert designer.tab_bar.count() == 1


def test_reordering_tabs_reorders_the_rows(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer._on_copy_renamed(0, "a")
    designer._on_copy_renamed(1, "b")
    designer.tab_bar.moveTab(0, 1)
    assert [row["name"] for row in _rows(handle)] == ["b", "a"]


def test_the_tab_bar_survives_deselecting(designer):
    """Clicking into the graph and back used to leave the panel empty."""
    handle = _chain(designer)
    designer._on_add_copy()
    designer._set_current(None)
    assert designer.tab_bar.count() == 0
    _select(designer, handle)
    assert designer.tab_bar.count() == 2
