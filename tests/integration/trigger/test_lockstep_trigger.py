"""Lockstep: the scene and the document are never knowingly apart."""

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.guides import GuideScene
from tik.trigger.maya import tags


@pytest.fixture
def scene():
    """A session's guides. The session owns them; the scene renders them."""
    from tik.trigger.session import Session

    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield Session().guides
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


def test_sync_return_value_reflects_what_it_just_fixed(scene):
    """Regression: ``GuideDiff.structural`` is a property over fixed
    ``ModuleDiff`` records computed *before* regenerate ran -- nothing
    recomputes it just because the loop that follows mutated the scene. A
    manual Sync that finds and fixes structurally stale modules must not
    hand back a diff that still calls them stale: the drift pill reads this
    return value directly, and a Sync button that appears to have done
    nothing is worse than the extra scan needed to prove it worked.
    """
    handle = scene.add("fkchain", side="C", name="tail", segments=3)
    cmds.delete(scene.guide_nodes(handle.instance_id)[("segment", 1)].long_name)
    diff = scene.sync()
    assert diff.structural == []  # sync() just redrew it -- the return value must say so
    assert diff.drifted == []
    assert scene.diff().is_clean  # and a fresh scan agrees: not a stale answer


def test_sync_on_a_dismissed_document_still_reports_outstanding_staleness(scene):
    """``dismissed`` forces ``regenerate_stale`` off (afterlife='delete'), so
    the rendering legitimately stays absent -- the returned diff must keep
    saying so, not get rescanned into a false "clean". Companion to
    ``test_a_build_that_deletes_the_guides_keeps_them_deleted`` above, which
    already covers this through a build; this drives it directly through
    ``dismissed`` so the contract does not depend on ``Builder``.
    """
    handle = scene.add("fkchain", side="C", name="tail", segments=1)
    for joint in list(scene.guide_nodes(handle.instance_id).values()):
        cmds.delete(joint.long_name)
    scene.dismissed = True  # the policy a build with afterlife='delete' sets
    diff = scene.sync()
    assert diff.structural == [handle.instance_id]  # unregenerated: still the pre-sync truth
    assert scene.guide_nodes(handle.instance_id) == {}  # confirms nothing was redrawn


def test_a_settings_change_undoes_with_the_session(scene):
    """Structure is a session edit, so Trigger's undo takes it back.

    The rendering follows on the next sync, exactly as it does for any other
    structural change.
    """
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    handle.segments = 4
    assert ("segment", 3) in scene.guide_nodes(handle.instance_id)
    scene.session.undo()
    assert scene.get(handle.instance_id).segments == 2
    scene.sync()
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
    assert scene.get(child.instance_id).inputs["root"] == f"{parent.key}.root"


def test_maya_duplicating_a_module_reports_duplicates_instead_of_merging(scene):
    """Duplicating a guide hierarchy copies trg_instance; that must not merge."""
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    root = scene.guide_nodes(handle.instance_id)[("root", 0)]
    cmds.duplicate(root.long_name, renameChildren=True)
    diff = scene.sync()
    assert diff.duplicates, "the copied joints should be reported"
    # the original module is untouched: not rebuilt, not merged, not malformed
    assert diff.modules[handle.instance_id].needs_regenerate is False
    assert scene.get(handle.instance_id).name == "tail"
    assert len(scene.document.modules) == 1


def test_a_build_that_deletes_the_guides_keeps_them_deleted(scene):
    """afterlife='delete' is intent, not an accident to repair."""
    from tik.trigger.maya.build import Builder

    handle = scene.add("base", side="C", name="body")
    Builder().build(document=scene.document, rig_name="afterlife", afterlife="delete")
    diff = scene.sync()
    assert scene.guide_nodes(handle.instance_id) == {}
    assert scene.dismissed is True
    # reconcile still reports the rendering as absent -- that is honest; the
    # dismissal is the policy that decides not to act on it
    assert diff.structural == [handle.instance_id]
    # the module itself survives: the document is not the rendering
    assert scene.get(handle.instance_id).name == "body"


def test_restoring_brings_dismissed_guides_back(scene):
    from tik.trigger.maya.build import Builder

    handle = scene.add("base", side="C", name="body")
    root = scene.guide_nodes(handle.instance_id)[("root", 0)]
    cmds.xform(root.long_name, worldSpace=True, translation=(3.0, 4.0, 5.0))
    scene.sync()
    Builder().build(document=scene.document, rig_name="afterlife", afterlife="delete")
    scene.restore()
    restored = scene.guide_nodes(handle.instance_id)[("root", 0)]
    placed = cmds.xform(restored.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([3.0, 4.0, 5.0])


def test_authoring_again_after_a_build_un_dismisses(scene):
    """Adding a module means you want to see guides again."""
    from tik.trigger.maya.build import Builder

    scene.add("base", side="C", name="body")
    Builder().build(document=scene.document, rig_name="afterlife", afterlife="delete")
    handle = scene.add("fkchain", side="C", name="tail", segments=1)
    assert scene.guide_nodes(handle.instance_id)
    assert scene.dismissed is False


def test_keeping_the_guides_does_not_dismiss_them(scene):
    from tik.trigger.maya.build import Builder

    handle = scene.add("base", side="C", name="body")
    Builder().build(document=scene.document, rig_name="afterlife", afterlife="keep")
    assert scene.dismissed is False
    assert scene.guide_nodes(handle.instance_id)


def test_a_new_scene_leaves_the_modules_and_redraws_them(scene):
    """The reported failure: New Scene emptied the Designer."""
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    root = scene.guide_nodes(handle.instance_id)[("root", 0)]
    cmds.xform(root.long_name, worldSpace=True, translation=(2.0, 3.0, 4.0))
    scene.sync()

    cmds.file(new=True, force=True)

    assert scene.get(handle.instance_id).name == "tail"   # never left
    scene.sync()
    restored = scene.guide_nodes(handle.instance_id)[("root", 0)]
    placed = cmds.xform(restored.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([2.0, 3.0, 4.0])


def test_deleting_scene_groups_cannot_destroy_a_module(scene):
    """Nothing in the scene is authority, so nothing in it can take a module."""
    handle = scene.add("fkchain", side="C", name="tail", segments=1)
    for group in ("trigger_guides_grp", "trigger_modules_grp"):
        if cmds.objExists(group):
            cmds.delete(group)
    assert scene.get(handle.instance_id).name == "tail"
    scene.sync()
    assert scene.guide_nodes(handle.instance_id)


def test_the_scene_holds_no_module_nodes_at_all(scene):
    scene.add("fkchain", side="C", name="tail", segments=1)
    assert not cmds.objExists("trigger_modules_grp")


# ------------------------------------------------------- posing is not lost
#
# None of these call sync(). That is deliberate: nothing in Maya fires when a
# guide is dragged, so the app does not sync either -- and a redraw that did not
# capture first threw the rigger's posing away. Adding sync() to these tests
# would hide exactly the bug they exist to catch.

def _posed(scene, handle, pair=("segment", 0), where=(11.0, 2.0, 3.0)):
    cmds.xform(scene.guide_nodes(handle.instance_id)[pair].long_name,
               worldSpace=True, translation=where)
    return where


def _placed(scene, handle, pair=("segment", 0)):
    return cmds.xform(scene.guide_nodes(handle.instance_id)[pair].long_name,
                      query=True, worldSpace=True, translation=True)


def test_changing_a_property_keeps_the_pose(scene):
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    where = _posed(scene, handle)
    handle.spacing = 7.0
    assert _placed(scene, handle) == pytest.approx(list(where))


def test_growing_the_chain_keeps_the_pose_without_a_sync(scene):
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    where = _posed(scene, handle)
    handle.segments = 5
    assert _placed(scene, handle) == pytest.approx(list(where))


def test_renaming_keeps_the_pose(scene):
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    where = _posed(scene, handle)
    handle.name = "renamed"
    assert _placed(scene, handle) == pytest.approx(list(where))


def test_connecting_keeps_the_pose(scene):
    parent = scene.add("fkchain", side="C", name="spine", segments=1)
    child = scene.add("fkchain", side="L", name="tail", segments=2)
    where = _posed(scene, child)
    scene.connect(f"{child.key}.root", f"{parent.key}.root")
    assert _placed(scene, child) == pytest.approx(list(where))


def test_a_pose_reaches_the_document_without_a_sync(scene):
    """The document is what gets saved, so it has to learn the pose too."""
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    where = _posed(scene, handle)
    handle.spacing = 7.0
    record = scene.document.module(handle.instance_id).guide("segment", 0)
    assert record.position == pytest.approx(where)


def test_auto_sync_off_still_captures_before_a_write(scene):
    """The fence for spec 3.1.

    Auto governs the *watcher*, never capture-before-regenerate. If capture ever
    moves behind the flag, changing a property throws the posing away again --
    the exact bug this codebase already shipped once.
    """
    scene.auto_sync = False
    handle = scene.add("fkchain", side="C", name="tail", segments=2)
    joint = scene.guide_nodes(handle.instance_id)[("segment", 0)]
    cmds.xform(joint.long_name, worldSpace=True, translation=(9.0, 0.0, 0.0))
    scene.write_settings(handle.instance_id, {"segments": 3})
    moved = scene.guide_nodes(handle.instance_id)[("segment", 0)]
    placed = cmds.xform(moved.long_name, query=True, worldSpace=True, translation=True)
    assert placed == pytest.approx([9.0, 0.0, 0.0])


def test_auto_sync_defaults_to_on(scene):
    assert scene.auto_sync is True
