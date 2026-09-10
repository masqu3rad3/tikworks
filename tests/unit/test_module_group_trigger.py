"""Module groups: the pure record, the operations, and shared-value derivation."""

import pytest

from tik.trigger.core.guide_document import GuideDocument, ModuleEntry
from tik.trigger.core.module_group import (
    GroupError,
    ModuleGroup,
    dissolve_group,
    join_group,
    leave_group,
    make_group,
    shared_values,
    varying_names,
)


def test_group_holds_members_in_tab_order():
    group = ModuleGroup(group_id="g1", label="fingers", members=["a", "b", "c"])
    assert group.members == ["a", "b", "c"]


def test_group_key_follows_side_like_a_module():
    """A group and a module name themselves by one rule: instance_key."""
    group = ModuleGroup(group_id="g1", label="fingers", members=["a"])
    assert group.key("L") == "L_fingers"
    assert group.key("C") == "fingers"
    assert group.key("") == "fingers"


def test_group_round_trips_through_dict():
    group = ModuleGroup(group_id="g1", label="fingers", members=["a", "b"])
    restored = ModuleGroup.from_dict(group.to_dict())
    assert restored == group


def test_group_from_dict_tolerates_a_missing_member_list():
    restored = ModuleGroup.from_dict({"group_id": "g1", "label": "toes"})
    assert restored.members == []


# --------------------------------------------------------------- operations


def _document():
    document = GuideDocument()
    document.modules = [
        ModuleEntry("a", "fkchain", "index", "L"),
        ModuleEntry("b", "fkchain", "middle", "L"),
        ModuleEntry("c", "fkchain", "ring", "L"),
    ]
    return document


def test_make_group_registers_the_members_in_order():
    document = _document()
    group = make_group(document, "fingers", ["a", "b"])
    assert document.module_groups == [group]
    assert group.members == ["a", "b"]
    assert group.label == "fingers"
    assert group.group_id


def test_make_group_refuses_mixed_types():
    document = _document()
    document.modules.append(ModuleEntry("d", "arm", "arm", "L"))
    with pytest.raises(GroupError, match="same type"):
        make_group(document, "mixed", ["a", "d"])


def test_make_group_refuses_mixed_sides():
    """A shared value stops being shared the moment the sides differ."""
    document = _document()
    document.modules.append(ModuleEntry("d", "fkchain", "index", "R"))
    with pytest.raises(GroupError, match="same side"):
        make_group(document, "mixed", ["a", "d"])


def test_make_group_refuses_fewer_than_two_members():
    document = _document()
    with pytest.raises(GroupError, match="two"):
        make_group(document, "lonely", ["a"])


def test_make_group_refuses_a_module_already_in_a_group():
    document = _document()
    make_group(document, "fingers", ["a", "b"])
    with pytest.raises(GroupError, match="already"):
        make_group(document, "other", ["b", "c"])


def test_make_group_refuses_mixing_local_and_borrowed_modules():
    """A half-borrowed group has a membership list that is partly this file's
    word and partly upstream's, with no answer when upstream drops a member."""
    document = _document()
    document.module("b").origin = "ref1"
    with pytest.raises(GroupError, match="referenced"):
        make_group(document, "fingers", ["a", "b"])


def test_make_group_refuses_an_unknown_module():
    document = _document()
    with pytest.raises(GroupError, match="No module"):
        make_group(document, "fingers", ["a", "nope"])


def test_join_appends_to_the_group():
    document = _document()
    group = make_group(document, "fingers", ["a", "b"])
    join_group(document, group.group_id, "c")
    assert group.members == ["a", "b", "c"]


def test_join_refuses_a_different_type():
    document = _document()
    document.modules.append(ModuleEntry("d", "arm", "arm", "L"))
    group = make_group(document, "fingers", ["a", "b"])
    with pytest.raises(GroupError, match="same type"):
        join_group(document, group.group_id, "d")


def test_leave_returns_the_group_it_left():
    document = _document()
    group = make_group(document, "fingers", ["a", "b", "c"])
    assert leave_group(document, "c") == group.group_id
    assert group.members == ["a", "b"]


def test_leave_dissolves_a_group_that_drops_to_one_member():
    """A group of one is a module."""
    document = _document()
    group = make_group(document, "fingers", ["a", "b"])
    leave_group(document, "b")
    assert document.module_group(group.group_id) is None
    assert document.module_groups == []


def test_leave_is_silent_for_a_module_in_no_group():
    document = _document()
    assert leave_group(document, "a") is None


def test_dissolve_removes_the_group_and_leaves_the_modules():
    document = _document()
    group = make_group(document, "fingers", ["a", "b"])
    dissolve_group(document, group.group_id)
    assert document.module_groups == []
    assert [entry.instance_id for entry in document.modules] == ["a", "b", "c"]


def test_dissolve_drops_the_groups_frame():
    document = _document()
    group = make_group(document, "fingers", ["a", "b"])
    document.frames[group.group_id] = {"position": [10.0, 20.0], "collapsed": True}
    dissolve_group(document, group.group_id)
    assert group.group_id not in document.frames


# ---------------------------------------------------------- shared values
def _members(*settings_and_inputs):
    found = []
    for index, (settings, inputs) in enumerate(settings_and_inputs):
        entry = ModuleEntry(f"m{index}", "fkchain", f"f{index}", "L")
        entry.settings = dict(settings)
        entry.inputs = dict(inputs)
        found.append(entry)
    return found


def test_a_setting_every_member_agrees_on_is_shared():
    members = _members(
        ({"segments": 3, "stretch": True}, {}),
        ({"segments": 3, "stretch": True}, {}),
    )
    assert shared_values(members) == {"segments": 3, "stretch": True}
    assert varying_names(members) == set()


def test_a_setting_one_member_differs_on_is_not_shared():
    members = _members(
        ({"segments": 3, "stretch": True}, {}),
        ({"segments": 5, "stretch": True}, {}),
    )
    assert shared_values(members) == {"stretch": True}
    assert varying_names(members) == {"segments"}


def test_a_setting_missing_from_one_member_is_not_shared():
    members = _members(({"segments": 3}, {}), ({}, {}))
    assert shared_values(members) == {}
    assert varying_names(members) == {"segments"}


def test_inputs_share_under_an_at_input_key():
    members = _members(({}, {"root": "hand.hand"}), ({}, {"root": "hand.hand"}))
    assert shared_values(members) == {"@input:root": "hand.hand"}


def test_a_differing_input_is_not_shared():
    members = _members(({}, {"root": "hand.hand"}), ({}, {"root": "other.out"}))
    assert shared_values(members) == {}
    assert varying_names(members) == {"@input:root"}


def test_an_unwired_input_still_counts_as_a_value():
    """Leaving an input unwired is an ordinary state, not an absence."""
    members = _members(({}, {"root": ""}), ({}, {"root": ""}))
    assert shared_values(members) == {"@input:root": ""}


def test_a_table_setting_compares_by_value_not_identity():
    rows = [{"control": "fk", "mode": "parent", "label": "world"}]
    members = _members(
        ({"anim_spaces": [dict(row) for row in rows]}, {}),
        ({"anim_spaces": [dict(row) for row in rows]}, {}),
    )
    assert shared_values(members) == {"anim_spaces": rows}


def test_one_member_shares_everything_it_has():
    members = _members(({"segments": 3}, {"root": "a.b"}))
    assert shared_values(members) == {"segments": 3, "@input:root": "a.b"}


def test_no_members_share_nothing():
    assert shared_values([]) == {}
    assert varying_names([]) == set()
