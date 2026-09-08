"""What a session needs to be published: artifacts, dependencies, bundles.

Pure Python. Knows files and hashes; never Maya, Qt or a provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Artifact:
    """One file a publish carries as a named element."""

    kind: str
    path: Path
    label: str = ""
