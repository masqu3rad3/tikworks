"""The scene observers behind the Guide Designer.

``ApiCallbacks`` is driven against real Maya -- node removal and reparenting
both fire in standalone. ``SceneObserver`` cannot be: its ``scriptJob`` events
need an idle loop, and batch Maya has none (``cmds.scriptJob`` there returns
``None`` rather than a job number). Its *registration lifecycle* is what this
class actually owns, though, so that half is driven through a fake ``cmds``;
delivering the events is Maya's job, not ours.
"""

import pytest
from maya import cmds

from tik.trigger.maya import observer as observer_module
from tik.trigger.maya.observer import EVENTS, ApiCallbacks, SceneObserver

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


class FakeCmds:
    """Enough of ``cmds.scriptJob`` to watch the observer register and clean up."""

    def __init__(self, start_at: int = 1):
        self.live: dict[int, list] = {}
        self.killed: list[int] = []
        self._next = start_at
        self.raise_on: set = set()

    def scriptJob(self, **kwargs):  # noqa: N802 - mirrors maya.cmds
        if "event" in kwargs:
            self.live[self._next] = kwargs["event"]
            self._next += 1
            return self._next - 1
        job = kwargs.get("exists", kwargs.get("kill"))
        if job in self.raise_on:
            raise RuntimeError(f"scriptJob {job} is not ours")
        if "exists" in kwargs:
            return kwargs["exists"] in self.live
        if "kill" in kwargs:
            self.killed.append(kwargs["kill"])
            self.live.pop(kwargs["kill"], None)
            return None
        raise AssertionError(f"unexpected scriptJob {kwargs}")

    def fire(self, event: str) -> None:
        """Run every job registered for ``event``, as Maya's idle loop would."""
        for name, callback in list(self.live.values()):
            if name == event:
                callback()


@pytest.fixture
def fake_cmds(monkeypatch):
    fake = FakeCmds()
    monkeypatch.setattr(observer_module, "cmds", fake)
    return fake


class TestSceneObserverRegistration:
    """One job per watched event, installed once and removed completely."""

    def test_every_event_gets_a_job(self, fake_cmds):
        observer = SceneObserver(lambda _name: None)

        observer.start()

        assert [event for event, _ in fake_cmds.live.values()] == list(EVENTS)

    def test_it_reports_itself_active(self, fake_cmds):
        observer = SceneObserver(lambda _name: None)

        observer.start()

        assert observer.active is True

    def test_starting_twice_does_not_double_register(self, fake_cmds):
        observer = SceneObserver(lambda _name: None)

        observer.start()
        observer.start()

        assert len(fake_cmds.live) == len(EVENTS)
        assert len(observer._jobs) == len(EVENTS)

    def test_stop_kills_every_job(self, fake_cmds):
        observer = SceneObserver(lambda _name: None)
        observer.start()

        observer.stop()

        assert fake_cmds.live == {}
        assert observer.active is False

    def test_stop_is_idempotent(self, fake_cmds):
        observer = SceneObserver(lambda _name: None)
        observer.start()

        observer.stop()
        observer.stop()

        assert observer.active is False

    def test_stopping_one_that_never_started_is_harmless(self, fake_cmds):
        SceneObserver(lambda _name: None).stop()

        assert fake_cmds.killed == []

    def test_one_unkillable_job_does_not_strand_the_rest(self, fake_cmds):
        """A callback that outlives its widget crashes Maya on shutdown."""
        observer = SceneObserver(lambda _name: None)
        observer.start()
        stubborn = observer._jobs[0]
        fake_cmds.raise_on = {stubborn}

        observer.stop()

        assert observer.active is False
        # Only the one that raised is left; the loop did not abandon the rest.
        assert set(fake_cmds.live) == {stubborn}

    def test_a_job_maya_already_dropped_is_skipped(self, fake_cmds):
        observer = SceneObserver(lambda _name: None)
        observer.start()
        gone = observer._jobs[0]
        fake_cmds.live.pop(gone)

        observer.stop()

        assert gone not in fake_cmds.killed
        assert observer.active is False

    def test_a_batch_maya_job_number_is_not_recorded(self, monkeypatch):
        """Batch ``cmds.scriptJob`` returns None -- an id ``stop`` could never kill."""
        monkeypatch.setattr(
            observer_module,
            "cmds",
            type("C", (), {"scriptJob": staticmethod(lambda **k: None)}),
        )
        observer = SceneObserver(lambda _name: None)

        observer.start()

        assert observer._jobs == []
        assert observer.active is False


class TestSceneObserverDispatch:
    """What reaches the callback once Maya does fire a job."""

    def test_an_event_reaches_the_callback_by_name(self, fake_cmds):
        seen: list = []
        observer = SceneObserver(seen.append)
        observer.start()

        fake_cmds.fire("SelectionChanged")

        assert seen == ["SelectionChanged"]

    def test_each_job_carries_its_own_event_name(self, fake_cmds):
        """The late-binding closure trap: every job must not report the last event."""
        seen: list = []
        observer = SceneObserver(seen.append)
        observer.start()

        for event in EVENTS:
            fake_cmds.fire(event)

        assert seen == list(EVENTS)

    def test_muting_silences_the_tools_own_edits(self, fake_cmds):
        seen: list = []
        observer = SceneObserver(seen.append)
        observer.start()

        observer.muted = True
        fake_cmds.fire("SelectionChanged")
        assert seen == []

        observer.muted = False
        fake_cmds.fire("SelectionChanged")
        assert seen == ["SelectionChanged"]

    def test_nothing_fires_after_stop(self, fake_cmds):
        seen: list = []
        observer = SceneObserver(seen.append)
        observer.start()
        observer.stop()

        fake_cmds.fire("SelectionChanged")

        assert seen == []


def test_the_observer_survives_a_real_start_and_stop():
    """Against real ``cmds``, not the fake: neither call may raise."""
    observer = SceneObserver(lambda _name: None)

    observer.start()
    observer.stop()

    assert observer.active is False
    assert cmds.objExists("persp")  # the scene is still usable
