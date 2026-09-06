"""Periodic recovery copies of the open session.

Autosave never touches the file the user is working on. It writes a sidecar
next to it -- ``rig.tr.autosave`` -- and only while the session is modified
and already has a path. Opening a session whose sidecar is newer than the
session offers recovery; saving the session for real clears the sidecar.

Writing the user's own file on a timer would make an accidental edit permanent
without anyone asking for it, which is exactly the failure autosave is
supposed to prevent. That is also why the write goes through
``Document.save``: ``Session.save`` reassigns ``Session.file_path``, so using
it here would silently rename the open session to its own recovery file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

from tik.shared.ui.Qt import QtCore

LOG = logging.getLogger(__name__)

#: Appended to the session file's full name, so ``rig.tr`` keeps its suffix
#: and the sidecar can never be mistaken for a session by a file browser.
SUFFIX = ".autosave"


def sidecar_path(session_path: Union[str, Path]) -> Path:
    """The recovery file that belongs to ``session_path``."""
    path = Path(session_path)
    return path.with_name(path.name + SUFFIX)


def recoverable(session_path: Union[str, Path]) -> Optional[Path]:
    """The sidecar for ``session_path`` when it is newer than the session.

    Returns None when there is no session path, no sidecar, or the sidecar is
    older -- meaning the user saved after the last autosave and there is
    nothing to recover.
    """
    if not session_path:
        return None
    session = Path(session_path)
    side = sidecar_path(session)
    if not side.is_file():
        return None
    if session.is_file() and side.stat().st_mtime <= session.stat().st_mtime:
        return None
    return side


def clear(session_path: Union[str, Path]) -> None:
    """Delete the sidecar for ``session_path`` if there is one."""
    if not session_path:
        return
    side = sidecar_path(session_path)
    try:
        side.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        LOG.warning("Could not remove the autosave file: %s", side)


class AutosaveTimer(QtCore.QTimer):
    """Writes a recovery sidecar for ``window``'s session on an interval.

    ``window`` must provide ``autosave_target() -> str``,
    ``is_modified() -> bool`` and ``write_autosave(path)``.
    """

    def __init__(self, window, interval_seconds: int = 300) -> None:
        super().__init__(window if isinstance(window, QtCore.QObject) else None)
        self._window = window
        self.setInterval(max(1, int(interval_seconds)) * 1000)
        self.timeout.connect(self.tick)

    def tick(self) -> None:
        """Write the sidecar, if there is anything worth writing."""
        target = self._window.autosave_target()
        if not target or not self._window.is_modified():
            return
        try:
            self._window.write_autosave(sidecar_path(target))
        except Exception:  # noqa: BLE001 - autosave must never interrupt work
            LOG.warning("Autosave failed for %s", target, exc_info=True)

    def reconfigure(self) -> None:
        """Match the timer to the current preferences."""
        from tik.trigger.config import prefs

        self.setInterval(max(1, int(prefs.files.autosave_interval)) * 1000)
        if prefs.files.autosave:
            self.start()
        else:
            self.stop()
