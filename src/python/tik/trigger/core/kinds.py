"""The kind vocabulary shared by publishing, browsing and the publish set.

A kind is a plain string a version control provider maps to its own element
types. Actions may add their own (``"weights"``); a provider that does not
know a kind treats it as a generic file.
"""

from __future__ import annotations

from typing import Sequence

SESSION = "session"
GUIDES = "guides"
RIG = "rig"
SCRIPT = "script"
MODEL = "model"
FILE = "file"

#: The extensions each kind usually carries, for fields that declare none.
EXTENSIONS: dict[str, tuple[str, ...]] = {
    SESSION: (".tr",),
    GUIDES: (".trg",),
    SCRIPT: (".py",),
    MODEL: (".ma", ".mb", ".fbx", ".obj", ".abc", ".usd"),
    RIG: (".ma", ".mb"),
}

#: Resolution order when an extension belongs to more than one kind: a bare
#: ``.mb`` field is more likely a model an action imports than a rig.
ORDER: tuple[str, ...] = (SESSION, GUIDES, SCRIPT, MODEL, RIG)


def kind_for(extensions: Sequence[str], declared: str = "") -> str:
    """``declared`` when given; else the first kind sharing an extension; else FILE."""
    if declared:
        return declared
    wanted = {ext if ext.startswith(".") else f".{ext}" for ext in extensions}
    for kind in ORDER:
        if wanted & set(EXTENSIONS[kind]):
            return kind
    return FILE
