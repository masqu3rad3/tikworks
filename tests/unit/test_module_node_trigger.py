"""Module document nodes: the scene-side home of a ModuleEntry."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core import registry
from tik.trigger.core.guide_document import GuideRecord, ModuleEntry
from tik.trigger.guides import module_node


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def make_entry(instance_id="id1"):
    return ModuleEntry(
        instance_id, "fkchain", "tail", "C",
        settings={"segments": 3, "spacing": 5.0},
        inputs={"root": "other.end"},
        guides=[GuideRecord("root", position=(0.0, 0.0, 0.0))],
    )


def make_module(entry):
    return registry.get_module("fkchain")(
        instance_id=entry.instance_id, name=entry.name, settings=entry.settings
    )


def test_create_makes_one_node_under_the_holder():
    entry = make_entry()
    node = module_node.create(entry, make_module(entry))
    assert node.parent.name == module_node.MODULE_NODES_GRP
    assert module_node.find("id1").long_name == node.long_name


def test_round_trip_preserves_the_entry():
    entry = make_entry()
    node = module_node.create(entry, make_module(entry))
    restored = module_node.read(node)
    assert restored.instance_id == "id1"
    assert restored.module_type == "fkchain"
    assert restored.name == "tail"
    assert restored.inputs == {"root": "other.end"}
    assert restored.settings["segments"] == 3
    assert restored.guide("root").position == (0.0, 0.0, 0.0)


def test_scalar_settings_become_real_attributes():
    entry = make_entry()
    node = module_node.create(entry, make_module(entry))
    assert node.has_attr("segments")
    assert node["segments"].value == 3
    assert module_node.settings_plug("id1", "segments") is not None


def test_channel_box_edit_wins_over_the_meta_copy():
    """The attribute is an authoring surface, so a channel-box edit must read back."""
    entry = make_entry()
    node = module_node.create(entry, make_module(entry))
    node["segments"].value = 7
    assert module_node.read(node).settings["segments"] == 7


def test_deleting_guide_joints_leaves_the_module_node_alone():
    """The whole point: guides are a rendering, the node is the identity."""
    entry = make_entry()
    module_node.create(entry, make_module(entry))
    joint = cmds.joint(name="some_guide")
    cmds.delete(joint)
    assert module_node.find("id1") is not None
    assert module_node.read(module_node.find("id1")).name == "tail"


def test_remove_deletes_the_node():
    entry = make_entry()
    module_node.create(entry, make_module(entry))
    module_node.remove("id1")
    assert module_node.find("id1") is None


def test_find_all_returns_every_module_node():
    for index in range(3):
        entry = make_entry(f"id{index}")
        entry.name = f"tail{index}"
        module_node.create(entry, make_module(entry))
    assert len(module_node.find_all()) == 3


def test_find_returns_none_for_an_unknown_instance():
    assert module_node.find("nosuch") is None
