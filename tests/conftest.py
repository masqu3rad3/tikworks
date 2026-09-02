"""Pytest configuration for Maya tests."""

import os
import sys
import types
from pathlib import Path

import pytest

# shared test helpers (toy modules etc.)
sys.path.insert(0, str(Path(__file__).parent / "helpers"))

# IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"

_maya_available = False
# TIK_TESTS_NO_MAYA=1 runs Maya-free suites (e.g. Qt UI tests) under mayapy
# without initializing Maya standalone, which cannot host a QApplication.
if not os.environ.get("TIK_TESTS_NO_MAYA"):
    try:
        import maya.standalone
        _maya_available = True
    except ImportError:
        pass


def _create_mock_maya():
    """Create a mock maya module for headless test environments."""
    mock_maya = types.ModuleType("maya")
    mock_maya.cmds = types.ModuleType("maya.cmds")
    mock_maya.cmds.file = lambda *a, **k: ""
    mock_maya.cmds.select = lambda *a, **k: None
    mock_maya.standalone = types.ModuleType("maya.standalone")
    mock_maya.standalone.initialize = lambda: None
    mock_maya.standalone.uninitialize = lambda: None
    mock_api = types.ModuleType("maya.api")
    mock_api.OpenMaya = types.ModuleType("maya.api.OpenMaya")
    mock_api.OpenMaya.MPxCommand = type("MPxCommand", (), {})
    mock_maya.api = mock_api
    sys.modules["maya"] = mock_maya
    sys.modules["maya.cmds"] = mock_maya.cmds
    sys.modules["maya.standalone"] = mock_maya.standalone
    sys.modules["maya.api"] = mock_api
    sys.modules["maya.api.OpenMaya"] = mock_api.OpenMaya
    return mock_maya


# Always create mock maya FIRST, before any real imports happen.
# This ensures tik/__init__.py can import maya even in headless environments.
if not _maya_available:
    _create_mock_maya()


@pytest.fixture(scope='session', autouse=True)
def initialize():
    """Initialize Maya standalone session before running tests.

    Only runs if Maya is available. Maya-independent tests (e.g. tik.trigger)
    can run without Maya.
    """
    if not _maya_available:
        yield
        return

    try:
        maya.standalone.initialize()
    except RuntimeError:
        # Maya is already initialized
        pass
    # Import tik.maya to ensure all node wrappers and the default factory are registered
    import tik.maya  # noqa: F401
    from maya import cmds  # noqa: F401
    yield
    maya.standalone.uninitialize()


@pytest.fixture(scope="function", autouse=True)
def new_scene():
    """Reset Maya + tik.maya global state before/after each test.

    Maya's selection, current scene, and tik.maya's registry/default-factory are
    all process-global. If they leak between tests, you can get order-dependent
    failures.

    Only runs if Maya is available.
    """
    if not _maya_available:
        yield
        return

    from maya import cmds

    # Fresh scene and empty selection
    cmds.file(new=True, force=True)
    cmds.select(clear=True)

    # Restore tik.maya default factory and node registry in case a test altered them.
    from tik.maya.core import registry as node_registry
    from tik.maya.core.node import Node
    from tik.maya.core.registry import set_default_factory

    set_default_factory(Node)
    registry_snapshot = dict(node_registry._NODE_TYPES)

    yield

    node_registry._NODE_TYPES.clear()
    node_registry._NODE_TYPES.update(registry_snapshot)

    # Clean up again so the next test always starts from a known state.
    cmds.file(new=True, force=True)
    cmds.select(clear=True)
    set_default_factory(Node)
