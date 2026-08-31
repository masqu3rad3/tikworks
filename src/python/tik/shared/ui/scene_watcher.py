"""Scene-change plumbing: many scriptJob events -> one debounced refresh.

Ported from creature_kit face_control ``ui/state.py``. Two guards are
load-bearing: a burst of events is coalesced into one refresh
(``QTimer.singleShot(0)``), and a refresh that touches the scene cannot
re-trigger itself (re-entrancy flag). ``mute()`` silences events the tool
causes on purpose (e.g. selecting nodes to mirror its own selection).
"""

from __future__ import annotations

import contextlib
import logging
import weakref
from typing import Callable, Iterable, Optional

from tik.shared.ui.Qt import QtCore

LOG = logging.getLogger(__name__)

DEFAULT_EVENTS = ("SelectionChanged", "DagObjectCreated", "SceneOpened", "NewSceneOpened", "Undo", "Redo")


class SceneWatcher(QtCore.QObject):
    """Debounced, re-entrancy-guarded scene observer."""

    #: Every watcher ever installed, weakly held. Relaunching a tool leaves the
    #: previous instance's watchers registered with Maya, still firing into the
    #: code they captured -- which after a module reload is stale code. The
    #: launcher clears them through :meth:`uninstall_all`.
    _live: "weakref.WeakSet" = weakref.WeakSet()

    @classmethod
    def uninstall_all(cls) -> None:
        """Stop every watcher in this interpreter. Called when a tool relaunches."""
        for watcher in list(cls._live):
            try:
                watcher.uninstall()
            except Exception:  # noqa: BLE001 - one bad watcher must not block the rest
                LOG.debug("could not uninstall a scene watcher", exc_info=True)

    def __init__(
        self,
        on_invalidate: Callable[[str], None],
        events: Iterable[str] = DEFAULT_EVENTS,
        parent=None,
        install_job: Optional[Callable[[str, Callable], int]] = None,
        kill_job: Optional[Callable[[int], None]] = None,
        owner=None,
        api_callbacks: bool = False,
    ) -> None:
        super().__init__(parent)
        self._on_invalidate = on_invalidate
        # The widget the callback ultimately touches. notify() schedules _fire
        # through a zero-timer, so the owner can be torn down in between; firing
        # into a dead Qt object raises from deep inside the callback.
        self._owner = owner
        self.events = tuple(events)
        self._jobs: list[int] = []
        self._pending: Optional[str] = None
        self._refreshing = False
        self._muted = 0
        self._install_job = install_job
        self._kill_job = kill_job
        # Node removal has no scriptJob equivalent; opt in to the OpenMaya
        # callbacks that do see it.
        self._api_wanted = api_callbacks
        self._api = None

    # ------------------------------------------------------------ lifecycle
    def install(self) -> list[int]:
        self.uninstall()
        SceneWatcher._live.add(self)
        install = self._install_job or self._maya_install
        for event in self.events:
            try:
                self._jobs.append(install(event, lambda name=event: self.notify(name)))
            except Exception as error:  # noqa: BLE001 - keep the tool alive
                LOG.debug("cannot watch %s: %s", event, error)
        if self._api_wanted:
            try:
                from tik.trigger.maya.observer import ApiCallbacks

                self._api = ApiCallbacks(self.notify)
                self._api.start()
            except Exception as error:  # noqa: BLE001 - keep the tool alive
                LOG.debug("cannot install API callbacks: %s", error)
                self._api = None
        return list(self._jobs)

    def uninstall(self) -> None:
        if self._api is not None:
            self._api.stop()
            self._api = None
        kill = self._kill_job or self._maya_kill
        while self._jobs:
            job = self._jobs.pop()
            try:
                kill(job)
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _maya_install(event: str, callback: Callable) -> int:
        from maya import cmds

        return cmds.scriptJob(event=[event, callback], protected=False)

    @staticmethod
    def _maya_kill(job: int) -> None:
        from maya import cmds

        if cmds.scriptJob(exists=job):
            cmds.scriptJob(kill=job, force=True)

    @property
    def jobs(self) -> list[int]:
        return list(self._jobs)

    @property
    def is_refreshing(self) -> bool:
        return self._refreshing

    # ------------------------------------------------------------- events
    @contextlib.contextmanager
    def mute(self):
        """Ignore events while the tool changes the scene itself."""
        self._muted += 1
        if self._api is not None:
            self._api.muted = True
        try:
            yield
        finally:
            self._muted -= 1
            if self._api is not None and not self._muted:
                self._api.muted = False

    def notify(self, event: str = "manual") -> None:
        """Feed an event (scriptJob callback or a fake backend)."""
        if self._muted or self._refreshing:
            return
        first = self._pending is None
        # SelectionChanged is cheap; anything structural wins the coalesced slot
        if self._pending in (None, "SelectionChanged"):
            self._pending = event
        if first:
            QtCore.QTimer.singleShot(0, self._fire)

    def flush(self) -> None:
        """Run a pending refresh now (tests)."""
        if self._pending is not None:
            self._fire()

    def _owner_is_alive(self) -> bool:
        """True unless the owner's C++ side has been destroyed.

        Probed by touching a trivial attribute rather than importing a binding
        module, so this works under PySide2, PySide6 and PyQt alike.
        """
        if self._owner is None:
            return True
        try:
            self._owner.objectName()
        except RuntimeError:
            return False
        return True

    def _fire(self) -> None:
        event, self._pending = self._pending, None
        if event is None or self._refreshing:
            return
        if not self._owner_is_alive():
            self.uninstall()
            return
        self._refreshing = True
        try:
            self._on_invalidate(event)
        except Exception:  # noqa: BLE001
            LOG.exception("scene refresh failed")
        finally:
            self._refreshing = False
