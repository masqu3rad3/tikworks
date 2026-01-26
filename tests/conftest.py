"""Pytest configuration for Maya tests."""

import pytest

# IN_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"

@pytest.fixture(scope='session', autouse=True)
def initialize():
    """Initialize Maya standalone session before running tests."""
    import maya.standalone
    try:
        maya.standalone.initialize()
    except RuntimeError:
        # Maya is already initialized
        pass
    # Import tik.maya to ensure all node wrappers and the default factory are registered
    import tik.maya  # noqa: F401
    from maya import cmds # noqa: F401
    yield
    maya.standalone.uninitialize()


# make sure every test happens on a fresh scene
@pytest.fixture(scope="function", autouse=True)
def new_scene():
    """Reset Maya + tik.maya global state before/after each test.

    Maya's selection, current scene, and tik.maya's registry/default-factory are
    all process-global. If they leak between tests, you can get order-dependent
    failures.
    """
    from maya import cmds

    # Fresh scene and empty selection
    cmds.file(new=True, force=True)
    cmds.select(clear=True)

    # Restore tik.maya default factory in case a test altered it.
    from tik.maya.core.node import Node
    from tik.maya.core.registry import set_default_factory

    set_default_factory(Node)

    yield

    # Clean up again so the next test always starts from a known state.
    cmds.file(new=True, force=True)
    cmds.select(clear=True)
    set_default_factory(Node)
