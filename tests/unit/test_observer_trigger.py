"""API callbacks for the scene events scriptJob cannot see."""

import pytest
from maya import cmds

from tik.trigger.maya.observer import ApiCallbacks


pytestmark = pytest.mark.usefixtures("trigger_plugins")


def test_node_removal_fires_a_callback():
    """The signal Maya's scriptJob has no equivalent for."""
    seen = []
    callbacks = ApiCallbacks(seen.append)
    callbacks.start()
    try:
        joint = cmds.joint(name="doomed")
        cmds.delete(joint)
    finally:
        callbacks.stop()
    assert "NodeRemoved" in seen


def test_reparenting_fires_a_callback():
    seen = []
    parent = cmds.group(empty=True, name="parent")
    child = cmds.group(empty=True, name="child")
    callbacks = ApiCallbacks(seen.append)
    callbacks.start()
    try:
        cmds.parent(child, parent)
    finally:
        callbacks.stop()
    assert "ParentChanged" in seen


def test_stop_deregisters_everything():
    callbacks = ApiCallbacks(lambda _name: None)
    callbacks.start()
    assert callbacks.active is True
    callbacks.stop()
    assert callbacks.active is False


def test_stop_is_idempotent():
    callbacks = ApiCallbacks(lambda _name: None)
    callbacks.start()
    callbacks.stop()
    callbacks.stop()
    assert callbacks.active is False


def test_no_callbacks_fire_after_stop():
    """A live callback into a destroyed widget crashes Maya on shutdown."""
    seen = []
    callbacks = ApiCallbacks(seen.append)
    callbacks.start()
    callbacks.stop()
    joint = cmds.joint(name="doomed")
    cmds.delete(joint)
    assert seen == []


def test_muting_silences_the_tools_own_edits():
    seen = []
    callbacks = ApiCallbacks(seen.append)
    callbacks.start()
    try:
        callbacks.muted = True
        joint = cmds.joint(name="doomed")
        cmds.delete(joint)
        assert seen == []
        callbacks.muted = False
        second = cmds.joint(name="doomed2")
        cmds.delete(second)
        assert "NodeRemoved" in seen
    finally:
        callbacks.stop()


def test_start_twice_does_not_double_register():
    seen = []
    callbacks = ApiCallbacks(seen.append)
    callbacks.start()
    callbacks.start()
    try:
        joint = cmds.joint(name="doomed")
        cmds.delete(joint)
    finally:
        callbacks.stop()
    assert seen.count("NodeRemoved") == 1
