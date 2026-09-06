"""The preferences file: one flat, hand-editable JSON dict.

Deliberately dumb. Defaults, staging and change tracking live in
``Preferences``; this class only knows how to read and write the file, and
how to survive finding it missing or mangled.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

from tik.core import jsonio

LOG = logging.getLogger(__name__)

#: Everything tikworks writes for a user lives here.
DEFAULT_FOLDER = Path.home() / "TikWorks"


class PrefStore:
    """A named JSON preferences file under ``folder``."""

    def __init__(self, name: str, folder: Union[str, Path, None] = None) -> None:
        """
        Args:
            name: File stem, without the extension (e.g. ``"trigger"``).
            folder: Where the file lives. Defaults to ``~/TikWorks``.
        """
        base = Path(folder) if folder is not None else DEFAULT_FOLDER
        self._path = (base / name).with_suffix(".json")

    @property
    def path(self) -> Path:
        """The absolute path of the preferences file."""
        return self._path

    def read(self) -> dict:
        """The stored mapping, or ``{}`` when it is missing or unreadable.

        A broken preferences file must never stop a tool from opening, so
        every failure here degrades to "no preferences stored yet".
        """
        try:
            data = jsonio.load(self._path)
        except FileNotFoundError:
            return {}
        except Exception:  # noqa: BLE001 - corrupt, unreadable, wrong perms
            LOG.warning("Ignoring unreadable preferences file: %s", self._path)
            return {}
        if not isinstance(data, dict):
            LOG.warning("Preferences file is not an object: %s", self._path)
            return {}
        return data

    def write(self, data: dict) -> None:
        """Replace the file's contents with ``data``, creating the folder."""
        jsonio.save(self._path, dict(data))

    def __repr__(self) -> str:
        return f"PrefStore({self._path})"
