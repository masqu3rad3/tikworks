"""The properties panel for a group: the tab bar, and what sits above it."""

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


def _select(designer, handle):
    """Select through the tree -- that is where selected_handles() reads."""
    designer.refresh()
    item = designer.item_for(handle.instance_id)
    designer.tree.setCurrentItem(item)
    item.setSelected(True)


@pytest.fixture
def designer(qapp):
    window = GuideDesigner(scene=StubScene())
    window.show()
    yield window
    window.close()


def _grouped(designer, count=3, **settings):
    scene = designer.guides
    handles = [
        scene.add("toy_chain", name=f"f{index}", side="L") for index in range(count)
    ]
    for handle in handles:
        for name, value in settings.items():
            setattr(handle, name, value)
    group = scene.group(handles, label="fingers")
    _select(designer, handles[0])
    return scene, group, handles


# ------------------------------------------------------------- the tab bar
def test_a_lone_module_still_shows_a_tab_bar_with_a_plus(designer):
    handle = designer.guides.add("toy_chain", name="index", side="L")
    _select(designer, handle)
    assert designer.tab_bar.count() == 1
    assert designer.tab_bar.tabText(0) == "index"
    assert designer.add_copy_button.isEnabled()


def test_a_group_shows_one_tab_per_member_in_order(designer):
    _scene, _group, _handles = _grouped(designer)
    assert designer.tab_bar.count() == 3
    assert [designer.tab_bar.tabText(i) for i in range(3)] == ["f0", "f1", "f2"]


def test_plus_adds_a_tab_and_selects_it(designer):
    _scene, _group, _handles = _grouped(designer)
    designer._on_add_copy()
    assert designer.tab_bar.count() == 4
    assert designer.tab_bar.currentIndex() == 3


def test_plus_on_a_lone_module_creates_the_group(designer):
    handle = designer.guides.add("toy_chain", name="index", side="L")
    _select(designer, handle)
    designer._on_add_copy()
    assert designer.tab_bar.count() == 2
    assert designer.guides.group_of(handle.instance_id) is not None


def test_switching_tabs_changes_the_current_module(designer):
    _scene, _group, handles = _grouped(designer)
    designer.tab_bar.setCurrentIndex(2)
    assert designer._current.instance_id == handles[2].instance_id


def test_renaming_a_tab_renames_the_member(designer):
    _scene, _group, handles = _grouped(designer)
    designer._on_tab_renamed(1, "middle")
    assert handles[1].instance.name == "middle"
    assert designer.tab_bar.tabText(1) == "middle"


def test_removing_the_last_but_one_member_dissolves_the_group(designer):
    scene, _group, handles = _grouped(designer, count=2)
    scene.remove_from_group(handles[1])
    _select(designer, handles[0])
    assert scene.group_of(handles[0].instance_id) is None
    assert designer.tab_bar.count() == 1


# --------------------------------------------------------- common vs per-tab
def test_a_setting_every_member_agrees_on_is_common(designer):
    _grouped(designer, segments=3)
    assert designer._is_common("segments") is True


def test_a_setting_one_member_differs_on_drops_into_the_tabs(designer):
    _scene, _group, handles = _grouped(designer, segments=3)
    handles[1].segments = 5
    _select(designer, handles[0])
    assert designer._is_common("segments") is False


def test_name_is_never_common(designer):
    """Member names must stay unique, so the field is fixed per-tab."""
    _grouped(designer)
    assert designer._is_common("name") is False


def test_a_lone_module_shares_nothing(designer):
    handle = designer.guides.add("toy_chain", name="index", side="L")
    _select(designer, handle)
    assert designer._is_common("segments") is False


def test_editing_a_common_setting_writes_to_every_member(designer):
    _scene, _group, handles = _grouped(designer, segments=3)
    designer._module_obj.segments = 7
    designer._on_setting_changed("segments", 7)
    assert [handle.settings["segments"] for handle in handles] == [7, 7, 7]


def test_editing_a_varying_setting_writes_to_the_current_tab_only(designer):
    _scene, _group, handles = _grouped(designer, segments=3)
    handles[1].segments = 5
    _select(designer, handles[0])
    designer._module_obj.segments = 9
    designer._on_setting_changed("segments", 9)
    assert handles[0].settings["segments"] == 9
    assert handles[1].settings["segments"] == 5
    assert handles[2].settings["segments"] == 3


def test_a_common_input_wires_every_member(designer):
    _scene, _group, handles = _grouped(designer)
    other = designer.guides.add("toy_root", name="hand")
    output = list(other.outputs)[0]
    designer._on_input_changed("root", f"{other.key}.{output}")
    assert [handle.instance.inputs.get("root") for handle in handles] == [
        f"{other.key}.{output}"
    ] * 3


def test_a_varying_input_is_wired_on_the_current_tab_only(designer):
    _scene, _group, handles = _grouped(designer)
    first = designer.guides.add("toy_root", name="hand")
    second = designer.guides.add("toy_root", name="other")
    output = list(first.outputs)[0]
    handles[1].set_input("root", f"{second.key}.{output}")
    _select(designer, handles[0])
    designer._on_input_changed("root", f"{first.key}.{output}")
    assert handles[0].instance.inputs["root"] == f"{first.key}.{output}"
    assert handles[1].instance.inputs["root"] == f"{second.key}.{output}"


def test_the_two_forms_split_the_fields_between_them(designer):
    """Every field is on exactly one side; none is shown twice or lost."""
    _scene, _group, handles = _grouped(designer, segments=3)
    handles[1].segments = 5
    _select(designer, handles[0])
    every = set(type(designer._module_obj).fields())
    common = {name for name in every if designer._is_common(name)}
    assert "segments" in every - common
    assert common and common < every


# --------------------------------------------------------------- the tree
def test_the_tree_shows_a_group_as_a_parent_of_its_members(designer):
    _scene, group, _handles = _grouped(designer)
    parent = designer.item_for_group(group.group_id)
    assert parent is not None
    assert parent.text(0) == "L_fingers"
    children = [parent.child(i).text(0) for i in range(parent.childCount())]
    assert children == ["L_f0", "L_f1", "L_f2"]


def test_a_grouped_member_is_not_also_a_top_level_row(designer):
    _grouped(designer)
    top = [
        designer.tree.topLevelItem(i).text(0)
        for i in range(designer.tree.topLevelItemCount())
    ]
    assert "L_f0" not in top
    assert "L_fingers" in top


def test_a_member_row_still_carries_its_instance_id(designer):
    """Every existing read of the selection goes through Qt.UserRole."""
    from tik.shared.ui.Qt import QtCore

    _scene, group, handles = _grouped(designer)
    parent = designer.item_for_group(group.group_id)
    child = parent.child(1)
    assert child.data(0, QtCore.Qt.UserRole) == handles[1].instance_id


def test_the_group_row_takes_the_worst_state_of_its_members(designer):
    from tik.trigger.core.reconcile import GuideDiff, ModuleDiff
    from tik.trigger.ui.designer.delegates import DrawStateRole
    from tik.trigger.ui.draw_state import STALE

    _scene, group, handles = _grouped(designer)
    designer.guides.diff = lambda: GuideDiff(
        modules={
            handles[1].instance_id: ModuleDiff(
                handles[1].instance_id, missing=[("root", 0)]
            )
        }
    )
    designer.refresh()
    parent = designer.item_for_group(group.group_id)
    assert parent.data(0, DrawStateRole) == STALE


def test_ungrouping_puts_the_members_back_where_they_were(designer):
    _scene, group, handles = _grouped(designer)
    designer.guides.ungroup(group.group_id)
    designer.refresh()
    assert designer.item_for_group(group.group_id) is None
    top = [
        designer.tree.topLevelItem(i).text(0)
        for i in range(designer.tree.topLevelItemCount())
    ]
    assert {"L_f0", "L_f1", "L_f2"} <= set(top)


# ------------------------------------------------------- the varies mark
def test_a_field_the_members_disagree_on_is_marked(designer):
    from tik.shared.ui.fields import VARIES_MARK

    _scene, _group, handles = _grouped(designer, segments=3)
    handles[1].segments = 5
    _select(designer, handles[0])
    assert designer.form._labels["segments"].text().endswith(VARIES_MARK)


def test_a_field_they_agree_on_carries_no_mark(designer):
    from tik.shared.ui.fields import VARIES_MARK

    _grouped(designer, segments=3)
    labels = designer.common_form._labels
    assert not labels["segments"].text().endswith(VARIES_MARK)


def test_the_mark_clears_when_they_agree_again(designer):
    from tik.shared.ui.fields import VARIES_MARK

    _scene, _group, handles = _grouped(designer, segments=3)
    handles[1].segments = 5
    _select(designer, handles[0])
    assert designer.form._labels["segments"].text().endswith(VARIES_MARK)
    handles[1].segments = 3
    _select(designer, handles[0])
    assert not designer.form._labels["segments"].text().endswith(VARIES_MARK)


def test_a_lone_module_marks_nothing(designer):
    from tik.shared.ui.fields import VARIES_MARK

    handle = designer.guides.add("toy_chain", name="index", side="L")
    _select(designer, handle)
    assert not designer.form._labels["segments"].text().endswith(VARIES_MARK)


def test_the_varies_mark_is_not_the_override_mark(designer):
    """They sit in the same panel and mean different things."""
    from tik.shared.ui.fields import VARIES_MARK

    assert "\u25c7" not in VARIES_MARK


# ----------------------------------------------------- the tab right-click
def _menu_texts(designer):
    return [action.text() for action in designer.tab_menu().actions()]


def test_the_tab_menu_offers_the_group_verbs_when_grouped(designer):
    _grouped(designer)
    texts = _menu_texts(designer)
    assert "Remove From Group" in texts
    assert "Ungroup" in texts


def test_the_tab_menu_hides_the_group_verbs_when_alone(designer):
    handle = designer.guides.add("toy_chain", name="index", side="L")
    _select(designer, handle)
    texts = _menu_texts(designer)
    assert "Remove From Group" not in texts
    assert "Ungroup" not in texts
    assert "Add Copy" in texts


def test_remove_from_group_keeps_the_module(designer):
    _scene, group, handles = _grouped(designer)
    designer.remove_current_from_group()
    assert designer.guides.group_of(handles[0].instance_id) is None
    assert designer.guides.get(handles[0].instance_id) is not None
    assert len(designer.guides.groups()[0].members) == 2


def test_ungroup_from_the_tab_menu_keeps_every_module(designer):
    _scene, group, handles = _grouped(designer)
    designer.ungroup_current()
    assert designer.guides.groups() == []
    assert len(designer.guides.instances()) == 3


# --------------------------------------------------------------- mirroring
def test_mirroring_a_grouped_module_mirrors_the_whole_group(designer):
    """Mirroring one finger of five and leaving four behind is never meant."""
    _scene, group, handles = _grouped(designer)
    designer.mirror_current()
    groups = designer.guides.groups()
    assert len(groups) == 2
    other = next(item for item in groups if item.group_id != group.group_id)
    assert len(other.members) == 3


def test_mirroring_a_group_twice_does_not_stack_up_groups(designer):
    _scene, _group, _handles = _grouped(designer)
    designer.mirror_current()
    designer.mirror_current()
    assert len(designer.guides.groups()) == 2


def test_mirroring_an_ungrouped_module_is_unchanged(designer):
    handle = designer.guides.add("toy_chain", name="index", side="L")
    _select(designer, handle)
    designer.mirror_current()
    assert designer.guides.groups() == []
    assert designer.guides.find("index", "R") is not None


# ------------------------------------------------------- deleting a group
def _answer(reply):
    """Answer the next Feedback question with ``reply``."""
    from tik.shared.ui import feedback

    return feedback.set_handler(lambda *args, **kwargs: reply)


def test_delete_group_offers_both_answers(designer):
    from tik.shared.ui import feedback

    _scene, _group, _handles = _grouped(designer)
    seen = {}

    def handler(kind, title, text, details, buttons):
        seen["buttons"] = list(buttons)
        return "cancel"

    previous = feedback.set_handler(handler)
    try:
        designer.delete_current_group()
    finally:
        feedback.set_handler(previous)
    assert seen["buttons"] == ["ungroup", "delete", "cancel"]


def test_delete_group_ungroup_keeps_every_module(designer):
    from tik.shared.ui import feedback

    _scene, _group, _handles = _grouped(designer)
    previous = _answer("ungroup")
    try:
        designer.delete_current_group()
    finally:
        feedback.set_handler(previous)
    assert designer.guides.groups() == []
    assert len(designer.guides.instances()) == 3


def test_delete_group_delete_removes_the_modules(designer):
    from tik.shared.ui import feedback

    _scene, _group, _handles = _grouped(designer)
    previous = _answer("delete")
    try:
        designer.delete_current_group()
    finally:
        feedback.set_handler(previous)
    assert designer.guides.groups() == []
    assert designer.guides.instances() == []


def test_cancelling_delete_group_changes_nothing(designer):
    from tik.shared.ui import feedback

    _scene, group, _handles = _grouped(designer)
    previous = _answer("cancel")
    try:
        designer.delete_current_group()
    finally:
        feedback.set_handler(previous)
    assert designer.guides.group_of(_handles[0].instance_id).group_id == group.group_id
    assert len(designer.guides.instances()) == 3
