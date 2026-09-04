"""``name_v###`` file versioning helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_VERSION = re.compile(r"^(?P<stem>.*?)_v(?P<version>\d+)$")
PADDING = 3


def parse(file_path) -> tuple[str, Optional[int], str]:
    """Return ``(stem, version, suffix)``; version is ``None`` when unversioned."""
    path = Path(file_path)
    match = _VERSION.match(path.stem)
    if not match:
        return path.stem, None, path.suffix
    return match.group("stem"), int(match.group("version")), path.suffix


def with_version(file_path, version: int) -> Path:
    """``path`` renamed to version ``version`` (``name_v003.tr``)."""
    path = Path(file_path)
    stem, _current, suffix = parse(path)
    return path.with_name(f"{stem}_v{version:0{PADDING}d}{suffix}")


def versions(file_path) -> list[Path]:
    """Existing sibling versions of ``file_path`` sorted ascending."""
    path = Path(file_path)
    stem, _current, suffix = parse(path)
    if not path.parent.exists():
        return []
    found = []
    for candidate in path.parent.glob(f"{stem}_v*{suffix}"):
        c_stem, c_version, c_suffix = parse(candidate)
        if c_stem == stem and c_version is not None and c_suffix == suffix:
            found.append((c_version, candidate))
    return [candidate for _version, candidate in sorted(found)]


def latest_version(file_path) -> Optional[Path]:
    """Highest existing version, or ``None``."""
    found = versions(file_path)
    return found[-1] if found else None


def next_version(file_path) -> Path:
    """Path for the version after the highest existing one (v001 when none)."""
    latest = latest_version(file_path)
    if latest is None:
        _stem, current, _suffix = parse(file_path)
        return with_version(file_path, (current or 0) + 1)
    return with_version(latest, parse(latest)[1] + 1)


def resolve(file_path, version: str = "") -> Path:
    """Resolve ``version``.

    ``""`` or ``"pinned"`` keep the file as given; ``"latest"`` picks the
    newest; ``"v007"`` or ``7`` pick that version.
    """
    path = Path(file_path)
    if not version or version == "pinned":
        return path
    if version == "latest":
        return latest_version(path) or path
    number = int(str(version).lstrip("v"))
    return with_version(path, number)
