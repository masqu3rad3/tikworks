"""Scene observer: selection / DAG changes -> callbacks (for the Guide Designer)."""

from __future__ import annotations

from typing import Callable

from maya import cmds

EVENTS = ("SelectionChanged", "DagObjectCreated", "SceneOpened", "NewSceneOpened", "Undo", "Redo")


class SceneObserver:
    """Registers Maya script jobs and forwards to ``callback(event_name)``."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        self.callback = callback
        self._jobs: list[int] = []
        self.muted = False

    def start(self) -> None:
        self.stop()
        for event in EVENTS:
            job = cmds.scriptJob(event=[event, lambda name=event: self._fire(name)], protected=False)
            self._jobs.append(job)

    def stop(self) -> None:
        for job in self._jobs:
            try:
                if cmds.scriptJob(exists=job):
                    cmds.scriptJob(kill=job, force=True)
            except RuntimeError:
                pass
        self._jobs = []

    def _fire(self, name: str) -> None:
        if not self.muted:
            self.callback(name)

    @property
    def active(self) -> bool:
        return bool(self._jobs)
