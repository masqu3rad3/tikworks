"""Reading a scene back into a session. The recovery round trip."""

import pytest
from maya import cmds

from tik.trigger.core import registry
from tik.trigger.core.guide_document import ModuleEntry, expand_guides
from tik.trigger.guides import from_scene, nodes, regenerate
from tik.trigger.maya import tags


pytestmark = pytest.mark.usefixtures("trigger_plugins")


def drawn_chain(segments=2, instance_id="id1", name="tail", side="L", **settings):
    entry = ModuleEntry(instance_id, "fkchain", name, side,
                        settings={"segments": segments, **settings})
    expand_guides(entry, registry.get_module("fkchain").guides, segments)
    regenerate.regenerate(entry)
    return entry


def test_a_drawn_module_comes_back_whole():
    drawn_chain(2, name="tail", side="L")
    document, report = from_scene.read()
    entry = document.module("id1")
    assert entry.name == "tail"
    assert entry.side == "L"
    assert entry.settings["segments"] == 2
    assert report.is_lossless


def test_poses_survive_the_round_trip():
    entry = drawn_chain(2)
    joint = nodes.guide_nodes("id1")[("segment", 0)]
    cmds.xform(joint.long_name, worldSpace=True, translation=(5.0, 6.0, 7.0))
    document, _report = from_scene.read()
    assert document.module("id1").guide("segment", 0).position == pytest.approx((5.0, 6.0, 7.0))


def test_a_scene_without_breadcrumbs_still_recovers_the_modules():
    """Files drawn by an older build arrive forever; they must not be refused."""
    drawn_chain(2, name="tail")
    root = nodes.root_guide(nodes.guide_nodes("id1"), "fkchain")
    del root.meta[tags.ENTRY]
    document, report = from_scene.read()
    assert document.module("id1").module_type == "fkchain"
    assert document.module("id1").name == "fkchain"
    assert not report.is_lossless
    assert len(report.partial) == 1


def test_an_empty_scene_recovers_nothing_and_says_so():
    document, report = from_scene.read()
    assert document.modules == []
    assert not report.is_lossless
