"""Module groups against a real scene: the [+] verb, mirroring, teardown.

The ``scene`` fixture comes from ``tests/integration/trigger/conftest.py``.
"""

import pytest

from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.module_group import GroupError


def _three_chains(scene):
    return [scene.add("fkchain", name=name, side="L") for name in ("a", "b", "c")]


def test_group_makes_one_group_of_the_handles(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    assert [h.instance_id for h in scene.group_members(group.group_id)] == [
        handles[0].instance_id,
        handles[1].instance_id,
    ]
    assert scene.group_of(handles[0].instance_id).group_id == group.group_id


def test_group_defaults_its_label_to_the_first_members_name(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2])
    assert group.label == "a"


def test_add_copy_duplicates_the_member_and_joins_it(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    copy = scene.add_copy(handles[0])
    assert copy.instance_id in group.members
    assert group.members[-1] == copy.instance_id


def test_add_copy_on_a_lone_module_creates_the_group(scene):
    """A group springs into existence around the pair; nothing to learn."""
    handle = scene.add("fkchain", name="index", side="L")
    assert scene.group_of(handle.instance_id) is None
    copy = scene.add_copy(handle)
    group = scene.group_of(handle.instance_id)
    assert group is not None
    assert group.members == [handle.instance_id, copy.instance_id]
    assert group.label == "index"


def test_add_copy_carries_settings_and_poses(scene):
    handle = scene.add("fkchain", name="index", side="L")
    handle.segments = 5
    copy = scene.add_copy(handle)
    assert copy.settings["segments"] == 5
    assert [record.pair for record in copy.entry.guides] == [
        record.pair for record in handle.entry.guides
    ]


def test_removing_a_member_down_to_one_dissolves_the_group(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    scene.remove(handles[1])
    assert scene.document.module_group(group.group_id) is None


def test_deleting_a_member_of_three_leaves_the_group_standing(scene):
    handles = _three_chains(scene)
    group = scene.group(handles, label="fingers")
    scene.remove(handles[2])
    assert scene.document.module_group(group.group_id).members == [
        handles[0].instance_id,
        handles[1].instance_id,
    ]


def test_ungroup_keeps_every_module(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    scene.ungroup(group.group_id)
    assert scene.document.module_groups == []
    assert len(scene.instances()) == 3


def test_group_refuses_mixed_types(scene):
    chain = scene.add("fkchain", name="index", side="L")
    arm = scene.add("arm", name="arm", side="L")
    with pytest.raises(GroupError, match="same type"):
        scene.group([chain, arm])


def test_mirror_group_builds_the_opposite_group_whole(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    mirrored = scene.mirror_group(group.group_id)
    assert mirrored.group_id != group.group_id
    assert len(mirrored.members) == 2
    sides = {scene.document.module(m).side for m in mirrored.members}
    assert sides == {"R"}
    assert mirrored.label == "fingers"


def test_mirror_group_twice_updates_rather_than_duplicates(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    first = scene.mirror_group(group.group_id)
    second = scene.mirror_group(group.group_id)
    assert first.group_id == second.group_id
    assert len(scene.document.module_groups) == 2


def test_ungroup_is_refused_for_a_referenced_group(scene):
    """Which modules belong together is upstream's word."""
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    for member in group.members:
        scene.document.module(member).origin = "ref1"
    with pytest.raises(GuideError, match="referenced"):
        scene.ungroup(group.group_id)
    assert scene.document.module_group(group.group_id) is not None


def test_add_copy_is_refused_for_a_referenced_group(scene):
    handles = _three_chains(scene)
    group = scene.group(handles[:2], label="fingers")
    for member in group.members:
        scene.document.module(member).origin = "ref1"
    with pytest.raises(GroupError, match="wholly local or wholly referenced"):
        scene.add_copy(handles[0])
