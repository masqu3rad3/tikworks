"""Module groups: the pure record, the operations, and shared-value derivation."""

from tik.trigger.core.module_group import ModuleGroup


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
