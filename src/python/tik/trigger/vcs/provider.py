# src/python/tik/trigger/vcs/provider.py
"""The contract a version control system implements, from outside the repo.

Every verb has a working default, so a provider implements what it supports
and the UI shows only what the provider answers (``supports``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Context:
    """What a session path is to the VCS, for the status chip and tooltips."""

    label: str
    version: Optional[int] = None
    is_latest: bool = True
    detail: str = ""


class VersionControl:
    """Base class for providers. Register with ``@register_provider(name)``."""

    name: str = ""
    label: str = ""
    icon: str = ""

    # ------------------------------------------------------------ verbs
    def available(self) -> bool:
        """Installed and configured? Only available providers are ever used."""
        return False

    def context(self, session_path: str) -> Optional[Context]:
        """What ``session_path`` is in the VCS; ``None`` when it is not a work."""
        return None

    def browse(self, kind: str, extensions: list, mode: str) -> str:
        """The VCS's own picker; the chosen path or ``""`` when cancelled."""
        return ""

    def new_version(self, host) -> str:
        """Save the host's session as the next version; the new path or ``""``."""
        return ""

    def open(self, host) -> str:
        """Pick a session in the VCS and open it through ``host``; path or ``""``."""
        return ""

    def publish_file(self, kind: str, path, host) -> None:
        """Hand one file to the VCS's own publish/ingest dialog."""
        return None

    def launch(self, host) -> None:
        """Open the VCS's main window."""
        return None

    # ---------------------------------------------------------- helpers
    def supports(self, verb: str) -> bool:
        """True when this provider overrides ``verb``."""
        return getattr(type(self), verb) is not getattr(VersionControl, verb)

    def display_label(self) -> str:
        """The label shown in menus and tooltips."""
        return self.label or self.name.replace("_", " ").title() or type(self).__name__

    def icon_path(self) -> Optional[Path]:
        """``<icon>.png`` or ``<icon>.svg`` beside the provider's file, if any."""
        import inspect

        stem = self.icon or self.name
        if not stem:
            return None
        try:
            folder = Path(inspect.getfile(type(self))).parent
        except (TypeError, OSError):
            return None
        for suffix in (".png", ".svg"):
            candidate = folder / f"{stem}{suffix}"
            if candidate.exists():
                return candidate
        return None
