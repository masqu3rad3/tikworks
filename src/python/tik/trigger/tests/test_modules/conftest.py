"""Fixtures for rig module tests."""

from __future__ import annotations

import pytest

_maya_available = True
try:
    import maya.standalone
    maya.standalone.initialize(name="test_trigger")
except ImportError:
    _maya_available = False


@pytest.fixture
def guide_session():
    """Fresh GuideSession with clean Maya scene."""
    import maya.cmds as cmds

    # Clear Maya scene
    cmds.file(new=True, force=True)

    from tik.trigger.session import GuideSession
    session = GuideSession()
    yield session

    # Cleanup
    session.clear()
    cmds.file(new=True, force=True)


@pytest.fixture
def base_module(guide_session):
    """Base module instance."""
    return guide_session.create_module("base", "test_base")


@pytest.fixture
def connector_module(guide_session):
    """Connector module instance."""
    return guide_session.create_module("connector", "test_connector")


@pytest.fixture
def pushpull_module(guide_session):
    """PushPull module instance."""
    return guide_session.create_module("pushpull", "test_pushpull")


@pytest.fixture
def arm_module(guide_session):
    """Arm module instance."""
    return guide_session.create_module("arm", "test_arm_L")


@pytest.fixture
def clean_scene():
    """Ensure a clean Maya scene."""
    import maya.cmds as cmds
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)