"""Scene observer: selection / DAG changes -> callbacks (for the Guide Designer)."""

from __future__ import annotations

from typing import Callable

from maya import cmds

EVENTS = (
    "SelectionChanged",
    "DagObjectCreated",
    "SceneOpened",
    "NewSceneOpened",
    "Undo",
    "Redo",
)


class SceneObserver:
    """Registers Maya script jobs and forwards to ``callback(event_name)``."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        self.callback = callback
        self._jobs: list[int] = []
        self.muted = False

    def start(self) -> None:
        """Install one scriptJob per watched scene event."""
        self.stop()
        for event in EVENTS:
            job = cmds.scriptJob(
                event=[event, lambda name=event: self._fire(name)], protected=False
            )
            # Batch Maya hands back None instead of a job number (there is no
            # idle loop to run the job on). Recording that would only give
            # ``stop`` an id it can never kill, and claim an ``active``
            # observer that is watching nothing.
            if job:
                self._jobs.append(job)

    def stop(self) -> None:
        """Remove the installed scriptJobs."""
        # Emptied up front, and every id tried on its own: one job that cannot
        # be killed must not strand the ones after it. A callback outliving the
        # widget it fires into crashes Maya on shutdown, so a half-done stop is
        # the failure this class exists to prevent.
        jobs, self._jobs = self._jobs, []
        for job in jobs:
            try:
                if cmds.scriptJob(exists=job):
                    cmds.scriptJob(kill=job, force=True)
            except (RuntimeError, TypeError):
                pass

    def _fire(self, name: str) -> None:
        if not self.muted:
            self.callback(name)

    @property
    def active(self) -> bool:
        """True while the scriptJobs are installed."""
        return bool(self._jobs)


class ApiCallbacks:
    """The scene events ``scriptJob`` cannot see: node removal and reparenting.

    Maya offers no generic node-deleted ``scriptJob`` event, which is why the
    Guide Designer was blind to a rigger deleting a guide in the outliner. One
    scene-wide ``MDGMessage`` callback covers every removal and -- unlike
    per-node ``scriptJob(nodeDeleted=...)`` -- needs no re-registration as
    guides come and go.

    Raw OpenMaya here is a deliberate exception to the consume-tik.maya rule:
    there is no ``cmds`` equivalent. ``stop()`` must be called on teardown; a
    live callback firing into a destroyed widget crashes Maya on shutdown.
    """

    def __init__(self, callback: Callable[[str], None]) -> None:
        self.callback = callback
        self._ids: list[int] = []
        self.muted = False

    def start(self) -> None:
        """Install the API callbacks for node removal and reparenting."""
        import maya.api.OpenMaya as om

        self.stop()
        self._ids.append(
            om.MDGMessage.addNodeRemovedCallback(
                lambda *_args: self._fire("NodeRemoved"), "dependNode"
            )
        )
        self._ids.append(
            om.MDagMessage.addParentAddedCallback(
                lambda *_args: self._fire("ParentChanged")
            )
        )

    def stop(self) -> None:
        """Remove the installed API callbacks."""
        import maya.api.OpenMaya as om

        while self._ids:
            try:
                om.MMessage.removeCallback(self._ids.pop())
            except RuntimeError:
                pass

    def _fire(self, name: str) -> None:
        if not self.muted:
            self.callback(name)

    @property
    def active(self) -> bool:
        """True while the callbacks are installed."""
        return bool(self._ids)
