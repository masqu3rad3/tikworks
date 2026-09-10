"""Module copies against a real scene.

The ``scene`` fixture comes from ``tests/integration/trigger/conftest.py``.
"""

from maya import cmds


def _two_copies(scene):
    handle = scene.add("fkchain", name="fingers", side="L", segments=2)
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 1, "spacing": 5.0},
    ]
    return handle


def test_one_copy_draws_todays_guides(scene):
    """The zero-change guarantee, in the scene."""
    handle = scene.add("fkchain", name="tail", side="C", segments=3)
    scene.draw()
    roles = sorted(role for role, _index in scene.guide_nodes(handle.instance_id))
    assert roles == ["root", "segment", "segment", "segment"]


def test_a_second_copy_draws_its_own_guides(scene):
    handle = _two_copies(scene)
    scene.draw()
    pairs = set(scene.guide_nodes(handle.instance_id))
    assert ("root", 0) in pairs
    assert ("segment", 1) in pairs
    assert ("c1_root", 0) in pairs
    assert ("c1_segment", 0) in pairs
    assert ("c1_segment", 1) not in pairs  # the thumb has one segment


def test_a_copys_guide_joint_is_named_after_the_copy(scene):
    """Not after the slug: the slug keys the document, the name reaches Maya."""
    handle = _two_copies(scene)
    scene.draw()
    node = scene.guide_node(handle.instance_id, "c1_root")
    assert "thumb" in node.name
    assert "c1" not in node.name


def test_each_copy_has_its_own_root(scene):
    """Copy two must not parent under copy one's root."""
    handle = _two_copies(scene)
    scene.draw()
    second = scene.guide_node(handle.instance_id, "c1_root")
    first = scene.guide_node(handle.instance_id, "root")
    assert second.parent.long_name != first.long_name


def test_adding_a_copy_leaves_the_first_copys_pose_alone(scene):
    handle = scene.add("fkchain", name="fingers", side="L", segments=2)
    scene.draw()
    node = scene.guide_node(handle.instance_id, "root").long_name
    cmds.xform(node, worldSpace=True, translation=(7.0, 8.0, 9.0))
    scene.sync()
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 2, "spacing": 5.0},
    ]
    scene.draw()
    moved = scene.guide_node(handle.instance_id, "root").long_name
    assert cmds.xform(moved, query=True, worldSpace=True, translation=True) == [
        7.0,
        8.0,
        9.0,
    ]


def test_removing_a_copy_takes_its_guides_with_it(scene):
    handle = _two_copies(scene)
    scene.draw()
    assert ("c1_root", 0) in set(scene.guide_nodes(handle.instance_id))
    handle.copies = [{"slug": "", "name": "index", "segments": 2, "spacing": 5.0}]
    scene.draw()
    assert ("c1_root", 0) not in set(scene.guide_nodes(handle.instance_id))


# ------------------------------------------------------------ naming
def test_a_copy_name_is_taken_for_naming_purposes(scene):
    """The module name never reaches the rig, so two modules each holding a
    copy called `index` would build colliding controls."""
    handle = scene.add("fkchain", name="fingers", side="L")
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 2, "spacing": 5.0},
    ]
    assert scene.unique_name("index", "L") != "index"
    assert scene.unique_name("thumb", "L") != "thumb"
    assert scene.unique_name("index", "R") == "index"


def test_a_blank_copy_name_reserves_the_module_name(scene):
    scene.add("fkchain", name="tail", side="C")
    assert scene.unique_name("tail", "C") != "tail"


def test_two_copies_with_one_name_are_a_warning(scene):
    from tik.trigger.core import registry

    handle = scene.add("fkchain", name="fingers", side="L")
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "index", "segments": 2, "spacing": 5.0},
    ]
    module = registry.get_module("fkchain").from_instance(handle.instance)
    assert any("index" in item for item in module.warnings())


def test_distinct_copy_names_warn_about_nothing(scene):
    from tik.trigger.core import registry

    handle = scene.add("fkchain", name="fingers", side="L")
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 2, "spacing": 5.0},
    ]
    module = registry.get_module("fkchain").from_instance(handle.instance)
    assert not [item for item in module.warnings() if "called" in item]
