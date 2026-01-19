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
    yield
    maya.standalone.uninitialize()

# make sure every test happens on a fresh scene
@pytest.fixture(scope='function', autouse=True)
def new_scene():
    """Create a new scene before each test."""
    from maya import cmds
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)