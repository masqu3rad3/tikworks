"""Regenerate: rebuild a module's guide joints from its document entry."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core import registry
from tik.trigger.core.guide_document import GuideDocument, ModuleEntry, expand_guides
from tik.trigger.guides import regenerate, snapshot
from tik.trigger.maya import tags


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def chain_entry(segments=3, instance_id="id1", name="tail"):
    entry = ModuleEntry(instance_id, "fkchain", name, "C", settings={"segments": segments})
    expand_guides(entry, registry.get_module("fkchain").guides, segments)
    return entry


def test_regenerate_draws_every_declared_guide():
    entry = chain_entry(3)
    joints = regenerate.regenerate(entry)
    assert sorted(joints) == sorted(entry.pairs)
    assert all(cmds.objExists(joint.long_name) for joint in joints.values())


def test_regenerated_joints_carry_the_stored_uuid():
    entry = chain_entry(2)
    for joint in regenerate.regenerate(entry).values():
        assert joint.meta[tags.INSTANCE] == "id1"


def test_regenerate_restores_stored_poses():
    entry = chain_entry(2)
    entry.guide("segment", 0).position = (12.0, 3.0, 0.0)
    joints = regenerate.regenerate(entry)
    placed = cmds.xform(joints[("segment", 0)].long_name, query=True,
                        worldSpace=True, translation=True)
    assert placed == pytest.approx([12.0, 3.0, 0.0])


def test_unposed_guides_land_at_their_draw_guides_pose():
    """A guide the document has never seen posed must not collapse to the origin."""
    entry = chain_entry(2)
    joints = regenerate.regenerate(entry)
    placed = cmds.xform(joints[("segment", 1)].long_name, query=True,
                        worldSpace=True, translation=True)
    assert placed != pytest.approx([0.0, 0.0, 0.0])


def test_growing_the_chain_keeps_the_poses_of_survivors():
    """The case that decides whether lockstep is helpful or hostile."""
    entry = chain_entry(2)
    entry.guide("segment", 0).position = (12.0, 3.0, 0.0)
    regenerate.regenerate(entry)
    entry.settings["segments"] = 4
    expand_guides(entry, registry.get_module("fkchain").guides, 4)
    joints = regenerate.regenerate(entry)
    kept = cmds.xform(joints[("segment", 0)].long_name, query=True,
                      worldSpace=True, translation=True)
    assert kept == pytest.approx([12.0, 3.0, 0.0])
    assert ("segment", 3) in joints


def test_regenerate_replaces_rather_than_duplicating():
    entry = chain_entry(2)
    regenerate.regenerate(entry)
    regenerate.regenerate(entry)
    rendered = [guide for guide in snapshot.snapshot() if guide.instance_id == "id1"]
    assert len(rendered) == len(entry.pairs)


def test_regenerate_rebuilds_the_intra_module_dag():
    entry = chain_entry(2)
    joints = regenerate.regenerate(entry)
    assert joints[("segment", 0)].parent.meta[tags.ROLE] == "root"


def test_regenerate_parents_the_root_under_its_primary_input_producer():
    """The DAG is a rendering of the primary input (spec 4.4)."""
    producer = chain_entry(1, "producer", "spine")
    child = chain_entry(1, "child", "tail")
    child.inputs = {"root": "producer.root"}
    document = GuideDocument(modules=[producer, child])
    regenerate.regenerate(producer, document)
    joints = regenerate.regenerate(child, document)
    assert joints[("root", 0)].parent.meta[tags.INSTANCE] == "producer"


def test_regenerate_all_builds_producers_first():
    producer = chain_entry(1, "producer", "spine")
    child = chain_entry(1, "child", "tail")
    child.inputs = {"root": "producer.root"}
    # child listed first, so ordering has to be derived rather than assumed
    document = GuideDocument(modules=[child, producer])
    regenerate.regenerate_all(document)
    from tik.trigger.guides import nodes
    root = nodes.guide_nodes("child")[("root", 0)]
    assert root.parent.meta[tags.INSTANCE] == "producer"


def test_regenerate_restores_guide_attrs():
    entry = ModuleEntry("id1", "twist", "twist", "C", settings={"segments": 2})
    expand_guides(entry, registry.get_module("twist").guides, 2)
    record = entry.guide("twist", 0)
    record.attrs = {"twistWeight": 0.75}
    joints = regenerate.regenerate(entry)
    assert joints[("twist", 0)]["twistWeight"].value == pytest.approx(0.75)


def test_regenerate_stamps_the_entry_on_the_root_guide():
    """Snapshot's only way back: what the module *is*, parked on its root joint."""
    entry = chain_entry(2, name="tail")
    entry.inputs["parent"] = "other-id.root"
    joints = regenerate.regenerate(entry)
    root = joints[(registry.get_module("fkchain").guides.root, 0)]
    stored = root.meta[tags.ENTRY]
    assert stored["name"] == "tail"
    assert stored["module_type"] == "fkchain"
    assert stored["settings"]["segments"] == 2
    assert stored["inputs"]["parent"] == "other-id.root"


def test_the_breadcrumb_never_carries_poses():
    """A guide moves with no document write, so a stored pose would rot in place."""
    entry = chain_entry(2)
    entry.guide("segment", 0).position = (12.0, 3.0, 0.0)
    joints = regenerate.regenerate(entry)
    root = joints[(registry.get_module("fkchain").guides.root, 0)]
    assert "guides" not in root.meta[tags.ENTRY]


def test_only_the_root_guide_carries_the_breadcrumb():
    entry = chain_entry(3)
    joints = regenerate.regenerate(entry)
    root_role = registry.get_module("fkchain").guides.root
    for (role, index), joint in joints.items():
        assert (tags.ENTRY in joint.meta) is ((role, index) == (root_role, 0))
