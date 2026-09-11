"""The two guarantees the copy model rests on.

The ``scene`` fixture comes from ``tests/integration/trigger/conftest.py``.
"""

from maya import cmds

from tik.trigger.maya import sandbox
from tik.trigger.maya.scaffold import TEST_NAMESPACE, TEST_ROOT


def _built(fragment):
    """Built nodes whose name contains ``fragment``.

    Through the test namespace explicitly: ``cmds.ls`` does not cross a
    namespace on a bare wildcard, so ``ls("*tail_fk0*")`` finds nothing at
    all in the sandbox rig.
    """
    return cmds.ls(f"{TEST_NAMESPACE}:*{fragment}*") or []


def _limb_groups():
    """Short names of the module groups hanging directly off trigger_grp."""
    found = []
    for node in cmds.ls(f"{TEST_NAMESPACE}:*_grp", long=True) or []:
        parent = (cmds.listRelatives(node, parent=True) or [""])[0]
        if parent.endswith("trigger_grp"):
            found.append(node.rsplit(":", 1)[-1])
    return sorted(found)


def _shape():
    """A stable description of the built test rig."""
    nodes = sorted(cmds.ls(TEST_ROOT, dag=True, long=True) or [])
    return [
        (
            name.rsplit("|", 1)[-1],
            cmds.nodeType(name),
            sorted(cmds.listRelatives(name, children=True) or []),
        )
        for name in nodes
    ]


def test_one_copy_builds_todays_rig(scene):
    """No migration, no schema bump, nothing renamed."""
    scene.add("fkchain", name="tail", side="C", segments=3)
    scene.draw()
    scene.test_build()
    assert _shape(), "the build produced nothing to compare"
    assert _built("tail_fk0"), "a one-copy module builds under its own name"


def test_copies_build_the_same_controls_as_separate_modules(scene):
    """The naming decision, made falsifiable: an existing rig rebuilt as one
    module with N copies keeps every *control* name, so animation and
    published caches survive.

    Controls only, deliberately. The hierarchy differs and is meant to: N
    separate modules stand up N group trees, while N copies of one module
    share its single ``L_fingers_grp``. That is the whole point of copies --
    the earlier version of this test compared the full hierarchy and would
    now fail for the right reason.
    """
    for name in ("index", "middle", "thumb"):
        scene.add("fkchain", name=name, side="L", segments=2)
    scene.draw()
    scene.test_build()
    separate = sorted(
        name.rsplit(":", 1)[-1] for name in cmds.ls(f"{TEST_NAMESPACE}:*_ctrl") or []
    )
    assert separate, "the build produced nothing to compare"

    sandbox.clear()
    scene.clear()
    handle = scene.add("fkchain", name="fingers", side="L", segments=2)
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "middle", "segments": 2, "spacing": 5.0},
        {"slug": "c2", "name": "thumb", "segments": 2, "spacing": 5.0},
    ]
    scene.draw()
    scene.test_build()
    copied = sorted(
        name.rsplit(":", 1)[-1] for name in cmds.ls(f"{TEST_NAMESPACE}:*_ctrl") or []
    )

    assert copied == separate


def test_copies_collapse_three_group_trees_into_one(scene):
    """The other half of the same fact, asserted rather than implied."""
    for name in ("index", "middle", "thumb"):
        scene.add("fkchain", name=name, side="L", segments=1)
    scene.draw()
    scene.test_build()
    assert len(_limb_groups()) == 3

    sandbox.clear()
    scene.clear()
    grouped = scene.add("fkchain", name="fingers", side="L", segments=1)
    grouped.copies = [
        {"slug": "", "name": "index", "segments": 1, "spacing": 5.0},
        {"slug": "c1", "name": "middle", "segments": 1, "spacing": 5.0},
        {"slug": "c2", "name": "thumb", "segments": 1, "spacing": 5.0},
    ]
    scene.draw()
    scene.test_build()
    assert _limb_groups() == ["L_fingers_grp"]


def test_a_copys_outputs_are_addressable(scene):
    handle = scene.add("fkchain", name="fingers", side="L", segments=2)
    handle.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 2, "spacing": 5.0},
    ]
    assert "end" in handle.outputs
    assert "c1_end" in handle.outputs


def test_a_downstream_module_can_consume_one_copys_output(scene):
    """Which is the point of qualifying the outputs rather than merging them."""
    hand = scene.add("fkchain", name="fingers", side="L", segments=2)
    hand.copies = [
        {"slug": "", "name": "index", "segments": 2, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 2, "spacing": 5.0},
    ]
    tip = scene.add("fkchain", name="nail", side="L", segments=1)
    scene.connect(f"{tip.key}.root", f"{hand.key}.c1_end")
    scene.draw()
    scene.test_build()
    assert _built("nail_fk0")


def test_every_copy_is_wired_to_the_modules_input(scene):
    """Inputs belong to the module, so each copy's socket is driven by the
    one thing the rigger wired."""
    root = scene.add("base", name="body", side="C")
    hand = scene.add("fkchain", name="fingers", side="L", segments=1)
    hand.copies = [
        {"slug": "", "name": "index", "segments": 1, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 1, "spacing": 5.0},
    ]
    scene.connect(f"{hand.key}.root", f"{root.key}.root")
    scene.draw()
    scene.test_build()
    assert _built("index_fk0")
    assert _built("thumb_fk0")


# ------------------------------------------------ what a copy shares
def _fingers(scene, count=2):
    handle = scene.add("fkchain", name="fkchain", side="L", segments=1)
    handle.copies = [
        {"slug": "", "name": "index", "segments": 1, "spacing": 5.0},
        {"slug": "c1", "name": "thumb", "segments": 1, "spacing": 5.0},
    ][:count]
    return handle


def test_each_copy_builds_on_its_own_guides(scene):
    """The bug: build_context scanned by instance id and handed every copy
    the same map, so copy two built on copy one's joints -- both rigs landed
    in the same place however far apart the guides were moved."""
    handle = _fingers(scene)
    scene.draw()
    first = scene.guide_node(handle.instance_id, "root").long_name
    second = scene.guide_node(handle.instance_id, "c1_root").long_name
    cmds.xform(first, worldSpace=True, translation=(0.0, 0.0, 0.0))
    cmds.xform(second, worldSpace=True, translation=(50.0, 0.0, 0.0))
    scene.sync()
    scene.test_build()

    index = _built("index_fk0_ctrl")[0]
    thumb = _built("thumb_fk0_ctrl")[0]
    at_index = cmds.xform(index, query=True, worldSpace=True, translation=True)
    at_thumb = cmds.xform(thumb, query=True, worldSpace=True, translation=True)
    assert at_index != at_thumb
    assert round(at_thumb[0] - at_index[0]) == 50


def test_copies_share_one_module_group(scene):
    """Copies are one module, so they hang under one module group -- named
    after the module, not after any copy."""
    _fingers(scene)
    scene.draw()
    scene.test_build()

    assert _limb_groups() == ["L_fkchain_grp"]


def test_each_copy_keeps_its_own_socket(scene):
    """Inside the shared socket group, but its own: ``rig.socket(match=...)``
    aligns a socket to that copy's guide, so one shared socket would be
    dragged to the last copy's guide, taking every rig under it along."""
    _fingers(scene)
    scene.draw()
    scene.test_build()
    assert _built("index_root_socket")
    assert _built("thumb_root_socket")
    parents = {
        cmds.listRelatives(node, parent=True)[0] for node in _built("root_socket")
    }
    assert len(parents) == 1


def test_a_copys_controls_still_carry_its_own_name(scene):
    """Only the groups are shared; the controls are the copy's."""
    _fingers(scene)
    scene.draw()
    scene.test_build()
    assert _built("index_fk0_ctrl")
    assert _built("thumb_fk0_ctrl")
