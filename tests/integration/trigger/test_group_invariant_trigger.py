"""Grouping never changes the rig.

The mechanical half of this guarantee is in
``tests/unit/test_import_boundaries.py``, which forbids the build path from
seeing a group at all. This is the behavioural half: the same members, grouped
or not, build the same rig.

The ``scene`` fixture comes from ``tests/integration/trigger/conftest.py``.
"""

from maya import cmds

from tik.trigger.maya import sandbox
from tik.trigger.maya.scaffold import TEST_ROOT


def _built_shape():
    """A stable description of what the test rig contains after a build."""
    nodes = sorted(cmds.ls(TEST_ROOT, dag=True, long=True) or [])
    return [
        (
            name.rsplit("|", 1)[-1],
            cmds.nodeType(name),
            sorted(cmds.listRelatives(name, children=True) or []),
        )
        for name in nodes
    ]


def _chains(scene, count=5):
    return [scene.add("fkchain", name=f"f{index}", side="L") for index in range(count)]


def test_a_grouped_build_matches_an_ungrouped_build(scene):
    handles = _chains(scene)
    scene.draw()
    scene.test_build()
    ungrouped = _built_shape()
    assert ungrouped, "the build produced nothing to compare"

    sandbox.clear()
    scene.group(handles, label="fingers")
    scene.test_build()

    assert _built_shape() == ungrouped


def test_ungrouping_between_builds_changes_nothing(scene):
    handles = _chains(scene)
    group = scene.group(handles, label="fingers")
    scene.draw()
    scene.test_build()
    grouped = _built_shape()
    assert grouped, "the build produced nothing to compare"

    sandbox.clear()
    scene.ungroup(group.group_id)
    scene.test_build()

    assert _built_shape() == grouped


def test_no_built_node_is_named_after_the_group(scene):
    """The group's label must not reach a node name, a tag or an attribute."""
    handles = _chains(scene)
    scene.group(handles, label="fingers")
    scene.draw()
    scene.test_build()

    assert cmds.ls("*fingers*") == []


def test_the_group_survives_the_build_untouched(scene):
    """Building reads the document; it must not edit the group either."""
    handles = _chains(scene)
    group = scene.group(handles, label="fingers")
    before = list(group.members)
    scene.draw()
    scene.test_build()

    after = scene.document.module_group(group.group_id)
    assert after is not None
    assert after.members == before
    assert after.label == "fingers"
