# src/python/tik/trigger/vcs/folder.py
"""A version control system that is only a folder tree.

The reference provider: every verb of the contract in the simplest form that
works, and the file the integrator's guide quotes. Point ``TRIGGER_FOLDER_VCS``
at a folder and Trigger versions sessions under ``sessions/`` and published
files under ``<kind>/``, ``_v###`` style.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from tik.trigger.core import versioning
from tik.trigger.vcs import kinds, register_provider
from tik.trigger.vcs.provider import Context, VersionControl

ROOT_VAR = "TRIGGER_FOLDER_VCS"


@register_provider("folder")
class FolderProvider(VersionControl):
    """Versioned folders, no server, no dialogs of its own."""

    label = "Folder"

    def __init__(self, root=None) -> None:
        self.root = Path(root or os.environ.get(ROOT_VAR, ""))

    def available(self) -> bool:
        return bool(str(self.root) != ".") and self.root.is_dir()

    def context(self, session_path: str) -> Optional[Context]:
        path = Path(session_path)
        if not session_path or self.root.resolve() not in path.resolve().parents:
            return None
        stem, version, _suffix = versioning.parse(path)
        latest = versioning.latest_version(path)
        latest_number = versioning.parse(latest)[1] if latest else version
        return Context(
            label=stem,
            version=version,
            is_latest=version is None or version >= (latest_number or 0),
            detail=str(path),
        )

    def browse(self, kind: str, extensions: list, mode: str) -> str:
        from tik.trigger.vcs import host

        folder = self.root / ("sessions" if kind == kinds.SESSION else kind)
        if mode == "save":
            return host.feedback.browse_save(
                "Save a file", str(folder), tuple(extensions)
            )
        return host.feedback.browse_open("Pick a file", str(folder), tuple(extensions))

    def new_version(self, host) -> str:
        session = host.session
        if session is None:
            return ""
        folder = self.root / "sessions"
        folder.mkdir(parents=True, exist_ok=True)
        target = versioning.next_version(folder / session.name)
        return str(host.save_as(target)).replace("\\", "/")

    def open(self, host) -> str:
        picked = self.browse(kinds.SESSION, [".tr"], "open")
        if picked:
            host.open(picked)
        return picked

    def publish_file(self, kind: str, path, host) -> None:
        source = Path(path)
        folder = self.root / kind
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, versioning.next_version(folder / source.name))

    def launch(self, host) -> None:
        from tik.shared.io import open_external

        open_external(self.root)
