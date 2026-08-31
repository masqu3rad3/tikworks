"""Lockstep: the scene and the document are never knowingly apart."""

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.guides import GuideScene
from tik.trigger.maya import tags


@pytest.fixture
def scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield GuideScene()
    cmds.file(new=True, force=True)


def test_deleting_a_guide_redraws_it(scene):
    """The defect this whole design exists to fix."""
    handle = scene.add("fkchain", side="C", name="tail", segments=3)
    joints = scene.guide_nodes(handle.instance_id)
    cmds.delete(joints[("segment", 1)].long_name)
    scene.sync()
    assert ("segment", 1) in scene.guide_nodes(handle.instance_id)


def test_a_deleted_guide_comes_back_where_it_was(scene):
    handle = scene.add("fkchain", side="C", name="tail", segments=3)
    target = scene.guide_nodes(handle.instance_id)[("segment", 1)]
    cmds.xform(target.long_name, worldSpace=True, translation=(13.0, 4.0, 0.0))
    scene.sync()  # capture the move
    cmds.delete(scene.guide_nodes(handle.instance_id)[("segment", 1)].long_name)
    scene.sync()  # regenerate it
    restored = scene.guide_nodes(handle.instance_id)[("segment", 1)]
    placed = cmds.xform(restored.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([13.0, 4.0, 0.0])


def test_deleting_the_root_guide_does_not_destroy_the_module(scene):
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    cmds.delete(scene.guide_nodes(handle.instance_id)[("root", 0)].long_name)
    scene.sync()
    assert scene.get(handle.instance_id) is not None
    assert scene.get(handle.instance_id).name == "tail"
    assert ("root", 0) in scene.guide_nodes(handle.instance_id)


def test_deleting_every_guide_keeps_the_module_and_redraws_it(scene):
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    for joint in list(scene.guide_nodes(handle.instance_id).values()):
        cmds.delete(joint.long_name)
    scene.sync()
    assert scene.get(handle.instance_id).name == "tail"
    assert len(scene.guide_nodes(handle.instance_id)) == 3


def test_moving_a_guide_never_triggers_a_redraw(scene):
    """Pose drift is captured, never regenerated -- it must not snap back."""
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    target = scene.guide_nodes(handle.instance_id)[("segment", 0)]
    cmds.xform(target.long_name, worldSpace=True, translation=(9.0, 9.0, 0.0))
    diff = scene.sync()
    assert diff.structural == []
    placed = cmds.xform(target.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([9.0, 9.0, 0.0])


def test_growing_the_chain_draws_the_new_guides_immediately(scene):
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    handle.segments = 4
    assert ("segment", 3) in scene.guide_nodes(handle.instance_id)


def test_growing_the_chain_keeps_existing_poses(scene):
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    target = scene.guide_nodes(handle.instance_id)[("segment", 0)]
    cmds.xform(target.long_name, worldSpace=True, translation=(11.0, 2.0, 0.0))
    scene.sync()
    handle.segments = 4
    kept = scene.guide_nodes(handle.instance_id)[("segment", 0)]
    placed = cmds.xform(kept.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([11.0, 2.0, 0.0])


def test_shrinking_the_chain_removes_the_extra_guides(scene):
    handle = scene.add("fkchain", side="C", name="tail", segments=4)
    handle.segments = 2
    pairs = set(scene.guide_nodes(handle.instance_id))
    assert ("segment", 3) not in pairs and ("segment", 1) in pairs


def test_orphans_are_reported_and_left_alone(scene):
    """Untracked scene content is a rigger's business, not ours to delete."""
    scene.add("fkchain", side="C", name="tail", segments=1)
    ghost = cmds.joint(name="ghost_guide")
    tm.Joint(ghost).meta.update({
        tags.KIND: tags.GUIDE, tags.MODULE: "fkchain",
        tags.INSTANCE: "nosuchmodule", tags.ROLE: "root", tags.INDEX: 0, tags.SIDE: "C",
    })
    diff = scene.sync()
    assert diff.orphans
    assert cmds.objExists("ghost_guide")


def test_sync_on_a_clean_scene_changes_nothing(scene):
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    before = {pair: node.long_name for pair, node in scene.guide_nodes(handle.instance_id).items()}
    diff = scene.sync()
    assert diff.structural == []
    after = {pair: node.long_name for pair, node in scene.guide_nodes(handle.instance_id).items()}
    assert after == before  # nothing was rebuilt


def test_a_settings_change_and_its_redraw_undo_together(scene):
    """One Ctrl+Z takes back both the setting and the joints it drew."""
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    handle.segments = 4
    assert ("segment", 3) in scene.guide_nodes(handle.instance_id)
    cmds.undo()
    scene.reload()
    assert scene.get(handle.instance_id).segments == 2
    assert ("segment", 3) not in scene.guide_nodes(handle.instance_id)


def test_sync_does_not_re_enter_itself(scene):
    """Regenerate deletes joints, which is exactly what wakes a sync."""
    scene.add("fkchain", side="C", name="tail", segments=2)
    calls = []
    original = GuideScene.sync

    def counting(self, *args, **kwargs):
        calls.append(1)
        return original(self, *args, **kwargs)

    GuideScene.sync = counting
    try:
        scene.sync()
    finally:
        GuideScene.sync = original
    assert len(calls) == 1


def test_capture_cannot_run_inside_a_regenerate(scene):
    """A capture mid-rebuild would record a half-built rendering."""
    from tik.trigger.core.exceptions import GuideError
    from tik.trigger.guides.capture import capture, regenerating

    scene.add("fkchain", side="C", name="tail", segments=2)
    with regenerating():
        with pytest.raises(GuideError, match="half-built"):
            capture(scene.document)
    # and the flag lifts again afterwards
    capture(scene.document)


def test_regenerate_raises_the_guard_for_its_whole_rebuild(scene):
    from tik.trigger.guides import capture as capture_module
    from tik.trigger.guides.regenerate import regenerate

    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    seen = []
    entry = scene.document.module(handle.instance_id)
    module_cls = type(scene._module_for(entry))
    original = module_cls.wire_guides

    def watching(self, guides):
        seen.append(capture_module.is_regenerating())
        return original(self, guides)

    module_cls.wire_guides = watching
    try:
        regenerate(entry, scene.document)
    finally:
        module_cls.wire_guides = original
    assert seen == [True]
    assert not capture_module.is_regenerating()


def test_document_survives_a_full_round_trip(scene):
    """The guarantee the whole design rests on."""
    handle = scene.add("fkchain", side="C", name="tail", segments=3)
    target = scene.guide_nodes(handle.instance_id)[("segment", 1)]
    cmds.xform(target.long_name, worldSpace=True, translation=(6.0, 7.0, 8.0))
    scene.sync()
    before = scene.document.to_dict()

    # tear the whole rendering down and rebuild it from the document alone
    for joint in list(scene.guide_nodes(handle.instance_id).values()):
        cmds.delete(joint.long_name)
    scene.sync()

    scene.reload()
    assert scene.document.to_dict() == before
    restored = scene.guide_nodes(handle.instance_id)[("segment", 1)]
    placed = cmds.xform(restored.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([6.0, 7.0, 8.0])


def test_connections_survive_a_rename_in_maya(scene):
    """Connections are uuid-keyed, so joint names are free to change."""
    parent = scene.add("fkchain", side="C", name="spine", segments=1)
    child = scene.add("fkchain", side="L", name="tail", segments=1)
    scene.connect(f"{child.key}.root", f"{parent.key}.root")
    cmds.rename(parent.root.long_name, "renamed_by_hand")
    scene.reload()
    assert scene.get(child.instance_id).inputs["root"] == f"{parent.key}.root"
