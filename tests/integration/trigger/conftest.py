"""Shared fixtures for trigger integration tests."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core import get_module
from tik.trigger.guides import GuideScene
from tik.trigger.maya import build


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
        rig_root = build.ensure_rig_root("test")
        built = get_module(module_type).from_instance(instance)
        return build.build_context(built, instance, rig_root)

    return _make
