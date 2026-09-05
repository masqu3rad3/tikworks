"""Cancel must survive Maya's workspace-control close, which cannot be vetoed.

Inside Maya the Trigger window lives in a ``workspaceControl``. Its title-bar
X and ``File > Quit`` both end in Maya closing that control, and Maya runs the
close callback *before* it acts: returning early from the callback does not
keep the control open. The control is therefore created with ``retain=True``
(closing hides it), the callback re-shows it on Cancel, and a confirmed close
deletes it itself. These tests drive that path with a fake ``maya.cmds``.
"""

from __future__ import annotations

import sys

import pytest

from tik.shared.ui import maya_window
from tik.shared.ui.Qt import QtWidgets
from tik.trigger.core import Action, StringField, clear_registries, register_action
from tik.trigger.ui.main import TriggerWindow

CONTROL = f"{TriggerWindow.WINDOW_NAME}WorkspaceControl"


class Mark(Action):
    label = "Mark"
    tag = StringField("")

    def run(self, ctx):
        pass


class FakeCmds:
    """Just enough of ``maya.cmds`` for a retained, floating workspace control."""

    def __init__(self):
        self.controls = {CONTROL: {"visible": True}}
        self.deferred = []
        self.edits = []

    def workspaceControl(self, name, q=False, e=False, **flags):  # noqa: N802
        if q:
            if flags.get("exists"):
                return name in self.controls
            if "visible" in flags:
                return self.controls[name]["visible"]
        if e:
            self.edits.append((name, tuple(sorted(flags))))
            if flags.get("close"):
                self.controls[name]["visible"] = False
            if flags.get("restore") or flags.get("visible"):
                self.controls[name]["visible"] = True
        return None

    def deleteUI(self, name, control=False):  # noqa: N802
        self.edits.append(("deleteUI", name))
        self.controls.pop(name, None)

    def evalDeferred(self, callback):  # noqa: N802
        self.deferred.append(callback)

    def scriptJob(self, **_flags):  # noqa: N802
        return False

    def flush(self):
        while self.deferred:
            self.deferred.pop(0)()


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_action("mark", category="build")(Mark)
    yield
    clear_registries()


@pytest.fixture
def cmds(monkeypatch):
    fake = FakeCmds()
    module = sys.modules["maya"].cmds
    for name in ("workspaceControl", "deleteUI", "evalDeferred", "scriptJob"):
        monkeypatch.setattr(module, name, getattr(fake, name), raising=False)
    monkeypatch.setattr(maya_window, "HAS_MAYA", True)
    return fake


@pytest.fixture
def hosted(qapp, cmds):
    """A dirty Trigger window parented under a (fake) workspace control."""
    host = QtWidgets.QWidget()
    host.setObjectName(CONTROL)
    window = TriggerWindow(parent=host)
    window.current_view.add_action("mark")
    asked = []

    def ask(session):
        asked.append(session.name)
        return window.answer

    window.answer = "cancel"
    window.ask_save_discard = ask
    window.asked = asked
    yield window
    window.answer = "discard"
    window._shutting_down = True
    host.deleteLater()


def test_quit_with_cancel_keeps_the_control(hosted, cmds):
    hosted.close()
    cmds.flush()
    assert hosted.asked == ["untitled"]
    assert CONTROL in cmds.controls
    assert cmds.controls[CONTROL]["visible"] is True
    assert hosted.tabs.count() == 1 and hosted.current_view.session.is_modified


def test_quit_with_discard_deletes_the_control_after_teardown(hosted, cmds):
    hosted.answer = "discard"
    torn = []
    for view in hosted.views:
        view.teardown = lambda view=view: torn.append(view)
    hosted.close()
    assert torn == hosted.views
    assert CONTROL in cmds.controls  # deletion waits for the event loop
    cmds.flush()
    assert CONTROL not in cmds.controls


def test_maya_close_with_cancel_reshows_the_control(hosted, cmds):
    """Maya has already decided to close: hide the control, then re-show it."""
    cmds.controls[CONTROL]["visible"] = False
    hosted.dockCloseEventTriggered()
    assert hosted.asked == ["untitled"]
    assert cmds.controls[CONTROL]["visible"] is False  # not inside the callback
    cmds.flush()
    assert cmds.controls[CONTROL]["visible"] is True
    assert hosted.current_view.session.is_modified


def test_maya_close_with_discard_deletes_the_control(hosted, cmds):
    hosted.answer = "discard"
    hosted.dockCloseEventTriggered()
    cmds.flush()
    assert CONTROL not in cmds.controls


def test_deleting_the_control_does_not_ask_again(hosted, cmds):
    """``deleteUI`` fires the close callback too; a confirmed close must not
    prompt a second time from inside its own teardown."""
    hosted.answer = "discard"
    hosted.dockCloseEventTriggered()
    hosted.dockCloseEventTriggered()  # what Maya does when deleteUI runs
    cmds.flush()
    assert hosted.asked == ["untitled"]
    assert CONTROL not in cmds.controls


def test_a_stale_reshow_leaves_a_relaunched_control_alone(hosted, cmds):
    """Relaunching deletes the control from under an instance that asked and
    was cancelled; its deferred re-show must not touch the new control."""
    hosted.dockCloseEventTriggered()
    hosted.setParent(None)  # what the deletion of the old control amounts to
    cmds.controls[CONTROL]["visible"] = False
    cmds.flush()
    assert cmds.controls[CONTROL]["visible"] is False
