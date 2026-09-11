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
    assert len(_rows(handle)) == 2
    designer.tab_bar.setCurrentIndex(1)
    designer._on_remove_copy()
    assert designer.tab_bar.count() == 1
    # Back to an implicit single copy: no copies list at all, so the module
    # reads exactly as it did before anyone pressed [+].
    assert _rows(handle) == []
    assert handle.settings["segments"] == 2


def test_the_last_copy_cannot_be_removed(designer):
    """A module always has at least one copy: itself."""
    _chain(designer)
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


# ------------------------------------------------- the two halves of the form
def test_a_per_copy_field_renders_in_the_copy_form(designer):
    _chain(designer)
    assert designer.copy_form.widget("segments") is not None
    assert designer.copy_form.widget("segments").isVisible()


def test_a_shared_field_renders_in_the_module_form(designer):
    _chain(designer)
    module_cls = type(designer._module_obj)
    assert "segments" in module_cls.per_copy_fields()
    assert "controller_size" in module_cls.shared_fields()
    assert designer.form.widget("controller_size").isVisible()
    assert not designer.form.widget("segments").isVisible()


def test_editing_a_per_copy_field_writes_to_the_current_copy(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer.tab_bar.setCurrentIndex(1)
    designer._module_obj.segments = 9
    designer._on_setting_changed("segments", 9)
    rows = _rows(handle)
    assert rows[1]["segments"] == 9
    assert rows[0]["segments"] != 9


def test_editing_a_shared_field_writes_to_the_module(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer._module_obj.controller_size = 4.0
    designer._on_setting_changed("controller_size", 4.0)
    assert handle.settings["controller_size"] == 4.0
    assert "controller_size" not in _rows(handle)[0]


def test_switching_tabs_shows_that_copys_values(designer):
    _chain(designer)
    designer._on_add_copy()
    designer.tab_bar.setCurrentIndex(1)
    designer._module_obj.segments = 9
    designer._on_setting_changed("segments", 9)
    designer.tab_bar.setCurrentIndex(0)
    assert designer._module_obj.segments != 9
    designer.tab_bar.setCurrentIndex(1)
    assert designer._module_obj.segments == 9


# ---------------------------------------------- the rule that broke before
def test_switching_tabs_does_not_change_the_selection(designer):
    """The Designer has exactly one selectable thing and the tree owns it."""
    handle = _chain(designer)
    designer._on_add_copy()
    before = [item.instance_id for item in designer.selected_handles()]
    assert before == [handle.instance_id]
    designer.tab_bar.setCurrentIndex(1)
    assert [item.instance_id for item in designer.selected_handles()] == before
    assert designer._current.instance_id == handle.instance_id


def test_draw_selected_works_while_a_copy_tab_is_showing(designer):
    """'Draw Selected did nothing' was the symptom that started all this."""
    handle = _chain(designer)
    designer._on_add_copy()
    designer.tab_bar.setCurrentIndex(1)
    designer.draw_selected()
    drawn = [call for call in designer.guides.calls if call[0] == "draw"]
    assert drawn
    assert handle.instance_id in (drawn[-1][1] or [])


def test_a_module_with_copies_is_one_tree_row(designer):
    """Copies are one module, so the tree says one module."""
    handle = _chain(designer)
    designer._on_add_copy()
    designer._on_add_copy()
    designer.refresh()
    assert designer.tree.topLevelItemCount() == 1
    row = designer.tree.topLevelItem(0)
    assert row.text(0) == handle.key
    assert row.childCount() == 0


def test_a_module_with_copies_is_one_graph_node(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer.refresh()
    assert handle.key in designer.graph.graph.nodes
    assert len(designer.graph.graph.nodes) == 1


def test_the_graph_node_exposes_every_copys_outputs(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer.refresh()
    node = designer.graph.graph.nodes[handle.key]
    assert any(name.startswith("c1_") for name in node.outputs)


# ---------------------------------------------------- per-copy connections
def test_each_copy_shows_its_own_input_row(designer):
    handle = _chain(designer)
    other = designer.guides.add("toy_root", name="hand")
    output = list(other.outputs)[0]
    _select(designer, handle)
    designer._on_add_copy()

    designer.tab_bar.setCurrentIndex(1)
    designer._on_input_changed("root", f"{other.key}.{output}")
    assert handle.instance.inputs.get("c1_root") == f"{other.key}.{output}"
    assert "root" not in handle.instance.inputs


def test_the_first_copys_input_stays_unqualified(designer):
    handle = _chain(designer)
    other = designer.guides.add("toy_root", name="hand")
    output = list(other.outputs)[0]
    _select(designer, handle)
    designer._on_add_copy()

    designer.tab_bar.setCurrentIndex(0)
    designer._on_input_changed("root", f"{other.key}.{output}")
    assert handle.instance.inputs.get("root") == f"{other.key}.{output}"


def test_the_input_row_shows_the_current_copys_source(designer):
    handle = _chain(designer)
    other = designer.guides.add("toy_root", name="hand")
    output = list(other.outputs)[0]
    _select(designer, handle)
    designer._on_add_copy()
    designer.tab_bar.setCurrentIndex(1)
    designer._on_input_changed("root", f"{other.key}.{output}")

    designer.tab_bar.setCurrentIndex(0)
    assert designer._input_rows["root"].line.text() == ""
    designer.tab_bar.setCurrentIndex(1)
    assert designer._input_rows["root"].line.text() == f"{other.key}.{output}"


def test_the_graph_node_offers_a_port_per_copy(designer):
    handle = _chain(designer)
    designer._on_add_copy()
    designer.refresh()
    node = designer.graph.graph.nodes[handle.key]
    assert "root" in node.inputs
    assert "c1_root" in node.inputs


# --------------------------------------------------- the panel tells the truth
def _order(designer):
    """Top-to-bottom order of the panel's landmarks inside the scroll column."""
    column = designer.form_scroll.widget().layout()
    names = {
        id(designer.module_caption): "MODULE",
        id(designer.form): "shared fields",
        id(designer.tab_bar.parent()): "tab bar",
        id(designer.copy_caption): "COPY",
        id(designer.inputs_caption): "INPUTS",
        id(designer.copy_form): "per-copy fields",
    }
    found = []
    for index in range(column.count()):
        item = column.itemAt(index)
        widget = item.widget()
        if widget is not None and id(widget) in names:
            found.append(names[id(widget)])
        elif item.layout() is designer.inputs_form:
            found.append("input rows")
    return found


def test_everything_per_copy_sits_below_the_tab_bar(designer):
    """The layout is the panel's claim about ownership. Inputs are the
    copy's, so an input row above the bar would be a lie about the data."""
    _chain(designer)
    order = _order(designer)
    bar = order.index("tab bar")
    assert order.index("MODULE") < bar
    assert order.index("shared fields") < bar
    for below in ("COPY", "INPUTS", "input rows", "per-copy fields"):
        assert order.index(below) > bar, below


def test_the_module_half_hides_when_nothing_is_shared(designer):
    """fkchain shares nothing, so captioning an empty box would be noise."""
    handle = designer.guides.add("toy_root", name="spine")
    _select(designer, handle)
    module_cls = type(designer._module_obj)
    visible_shared = [
        name for name, f in module_cls.shared_fields().items() if not f.hidden
    ]
    assert visible_shared == []
    assert not designer.module_caption.isVisible()


def test_the_three_tables_are_the_copys(designer):
    """They sit below the bar because that is where they belong."""
    _chain(designer)
    module_cls = type(designer._module_obj)
    for name in ("anim_spaces", "pivot_presets", "control_shape_overrides"):
        assert name in module_cls.per_copy_fields(), name


def test_a_table_edited_on_one_tab_leaves_the_other_alone(designer):
    """The behaviour the layout was promising all along."""
    handle = _chain(designer)
    designer._on_add_copy()
    designer.tab_bar.setCurrentIndex(1)
    designer._module_obj.control_shape_overrides = [
        {"control": "fk0", "shape": "Cube", "size": ""}
    ]
    designer._on_setting_changed("control_shape_overrides", None)

    rows = _rows(handle)
    assert rows[1]["control_shape_overrides"][0]["shape"] == "Cube"
    assert rows[0]["control_shape_overrides"] == []


# ------------------------------------------------------------ naming copies
def test_a_new_copy_is_the_module_name_numbered_up(designer):
    """arm / arm1 / arm2, the way Maya names a duplicate."""
    handle = designer.guides.add("toy_chain", name="arm", side="L")
    _select(designer, handle)
    designer._on_add_copy()
    designer._on_add_copy()
    assert [designer.tab_bar.tabText(i) for i in range(3)] == ["arm", "arm1", "arm2"]


def test_the_number_follows_the_module_not_the_showing_tab(designer):
    handle = designer.guides.add("toy_chain", name="arm", side="L")
    _select(designer, handle)
    designer._on_add_copy()
    designer._on_copy_renamed(1, "thumb")
    designer._on_add_copy()
    assert designer.tab_bar.tabText(2) == "arm1"


def test_renaming_a_tab_to_an_existing_name_is_refused(designer):
    """It used to be allowed and blew up at build time instead."""
    handle = _chain(designer, name="arm")
    designer._on_add_copy()
    designer._on_copy_renamed(1, "arm")
    assert designer.tab_bar.tabText(1) == "arm1"
    assert [row["name"] for row in _rows(handle)][1] == "arm1"


def test_renaming_a_tab_to_its_own_name_is_fine(designer):
    _chain(designer, name="arm")
    designer._on_add_copy()
    designer._on_copy_renamed(1, "arm1")
    assert designer.tab_bar.tabText(1) == "arm1"


def test_a_refused_rename_says_why(designer):
    from tik.trigger.core import events

    _chain(designer, name="arm")
    designer._on_add_copy()
    seen = []
    designer.events.subscribe(events.LOG, lambda **kw: seen.append(kw))
    designer._on_copy_renamed(1, "arm")
    assert any("already the name" in str(item.get("message")) for item in seen)
