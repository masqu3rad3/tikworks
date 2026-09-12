"""Shared fixtures for trigger integration tests."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core import get_module
from tik.trigger.guides import GuideScene
from tik.trigger.maya import build
from tik.trigger.maya import scaffold as scaffold_module


@pytest.fixture(autouse=True, scope="session")
def _plugins():
    """Modules must be registered before any test reads the registry."""
    trigger.load_plugins()


@pytest.fixture
def scene():
    cmds.file(new=True, force=True)
    trigger.load_plugins()
    return GuideScene()


@pytest.fixture
def build_context(scene):
    """Build a real ModuleRig for any module type.

    The module is not built — only its groups and context exist — so a system
    or module body can be driven directly.
    """

    def _make(
        module_type: str = "base", name: str = "probe", side: str = "C", settings=None
    ):
        module = get_module(module_type)(name=name, side=side, settings=settings or {})
        instance = scene.create_guides(module)
        rig = scaffold_module.ensure_rig()
        built = get_module(module_type).from_instance(instance)
        return build.build_context(built, instance, rig)

    return _make


@pytest.fixture
def mirrored_pair(scene):
    """Build the same module on both sides and hand back both contexts.

    Mirroring is the most common source of limb bugs and every test has been
    asserting it ad hoc. ``poses`` are the LEFT side's world positions; the
    right gets the same triples with X negated, which is what "mirrored" has
    to mean for a comparison to say anything.

    Both sides are built in one pass so the comparison cannot be poisoned by
    two different scene states.
    """
    from tik.trigger.core import ParentRef, get_module
    from tik.trigger.maya import Builder

    def _make(module_type: str, poses: dict, **settings):
        body = scene.create_guides(get_module("base")(name="body"))
        cmds.xform(
            scene.guide_node(body.instance_id, "root").long_name,
            ws=True,
            t=(0, 0, 0),
        )
        instances = {}
        for side in ("L", "R"):
            instance = scene.create_guides(
                get_module(module_type)(name=module_type, side=side, settings=settings),
                parent=ParentRef(body.instance_id, "root"),
            )
            mult = -1 if side == "R" else 1
            for role, (x, y, z) in poses.items():
                cmds.xform(
                    scene.guide_node(instance.instance_id, role).long_name,
                    ws=True,
                    t=(x * mult, y, z),
                )
            instances[side] = instance
        report = Builder().build(document=scene.document, afterlife="keep")
        return (
            report.rigs[instances["L"].instance_id],
            report.rigs[instances["R"].instance_id],
        )

    return _make
