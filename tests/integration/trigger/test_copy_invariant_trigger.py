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


def test_copies_build_what_separate_modules_build(scene):
    """The naming decision, made falsifiable: an existing rig rebuilt as one
    module with N copies keeps every control name."""
    for name in ("index", "middle", "thumb"):
        scene.add("fkchain", name=name, side="L", segments=2)
    scene.draw()
    scene.test_build()
    separate = _shape()
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

    assert _shape() == separate


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
