"""Shared fixtures for trigger integration tests."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.backends.maya import MayaBackend
from tik.trigger.core import get_module


@pytest.fixture(autouse=True, scope="session")
def _plugins():
    """Modules must be registered before any test reads the registry."""
    trigger.load_plugins()


@pytest.fixture
def backend():
    cmds.file(new=True, force=True)
    trigger.load_plugins()
    return MayaBackend()


@pytest.fixture
def build_context(backend):
    """Build a real MayaBuildContext for any module type.

    The module is not built — only its groups and context exist — so a system
    or module body can be driven directly.
    """

    def _make(module_type: str = "base", name: str = "probe", side: str = "C", settings=None):
        module = get_module(module_type)(name=name, side=side, settings=settings or {})
        instance = backend.create_guides(module)
        rig_root = backend.ensure_rig_root("test")
        built = get_module(module_type).from_instance(instance)
        return backend.build_context(built, instance, rig_root)

    return _make
