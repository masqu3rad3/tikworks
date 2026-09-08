# src/python/tik/trigger/vcs/host.py
"""The one object Trigger exposes outward.

Providers never import the window. The window attaches itself here; a
headless script attaches a ``Session``. Both look the same from a provider.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional


class Host:
    """Session access, open and save, a refresh hook, and dialogs."""

    def __init__(self) -> None:
        self._session: Any = None
        self._open: Optional[Callable] = None
        self._save_as: Optional[Callable] = None
        self._refresh: Optional[Callable] = None
        self._feedback: Optional[Callable] = None

    def attach(
        self,
        session=None,
        open: Optional[Callable] = None,  # noqa: A002 - the verb is the name
        save_as: Optional[Callable] = None,
        refresh: Optional[Callable] = None,
        feedback: Optional[Callable] = None,
    ) -> None:
        """Bind the host. ``session`` may be a Session or a callable returning one."""
        self._session = session
        self._open = open
        self._save_as = save_as
        self._refresh = refresh
        self._feedback = feedback

    def detach(self) -> None:
        """Forget everything; the host answers as if nothing were open."""
        self.attach()

    # ---------------------------------------------------------- session
    @property
    def session(self):
        """The active ``Session`` or ``None``."""
        if callable(self._session):
            return self._session()
        return self._session

    @property
    def session_path(self) -> str:
        """The active session's file, or ``""``."""
        session = self.session
        if session is None or session.file_path is None:
            return ""
        return str(session.file_path).replace("\\", "/")

    @property
    def is_modified(self) -> bool:
        session = self.session
        return bool(session is not None and session.is_modified)

    # ------------------------------------------------------------ verbs
    def open(self, path) -> None:
        """Open a ``.tr``: through the window when attached, else on the session."""
        if self._open is not None:
            self._open(path)
            return
        session = self.session
        if session is None:
            from tik.trigger.session import Session

            self._session = Session(str(path))
            return
        session.load(str(path))

    def save_as(self, path) -> Path:
        """Save the active session at ``path``; returns where it went."""
        if self._save_as is not None:
            return Path(self._save_as(path))
        session = self.session
        if session is None:
            from tik.trigger.core.exceptions import VersionControlError

            raise VersionControlError("No session to save.")
        return session.save(str(path))

    def refresh(self) -> None:
        """Tell the window the VCS context may have changed."""
        if self._refresh is not None:
            self._refresh()

    @property
    def feedback(self):
        """A correctly parented ``Feedback`` for a provider's own questions."""
        if self._feedback is not None:
            return self._feedback()
        from tik.shared.ui.feedback import Feedback

        return Feedback()
