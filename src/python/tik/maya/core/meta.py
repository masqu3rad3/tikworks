"""Typed metadata storage on Maya nodes.

Each key becomes a hidden string attribute ``tikMeta_<key>`` holding a JSON
payload. This keeps arbitrary, typed metadata on any node without inventing
node types, and survives renames because it is attribute based.

Example:
    node.meta["kind"] = "guide"
    node.meta["settings"] = {"segments": 3}
    find_by_meta("kind", "guide", node_type="joint")
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

from maya import cmds

from .registry import resolve

META_PREFIX = "tikMeta_"
_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ANY = object()


def _attr_name(key: str) -> str:
    """Return the Maya attribute name for ``key``; validate the key."""
    if not isinstance(key, str) or not _KEY_PATTERN.match(key):
        raise ValueError(f"Invalid meta key '{key}'.")
    return f"{META_PREFIX}{key}"


class MetaStore:
    """Mapping-like access to a node's metadata attributes."""

    def __init__(self, node) -> None:
        self._node = node

    def _plug_path(self, key: str) -> str:
        return f"{self._node.long_name}.{_attr_name(key)}"

    def _exists(self, key: str) -> bool:
        return cmds.attributeQuery(
            _attr_name(key), node=self._node.long_name, exists=True
        )

    def __getitem__(self, key: str) -> Any:
        if not self._exists(key):
            raise KeyError(key)
        raw = cmds.getAttr(self._plug_path(key))
        return json.loads(raw) if raw else None

    def __setitem__(self, key: str, value: Any) -> None:
        attr = _attr_name(key)
        if not self._exists(key):
            cmds.addAttr(
                self._node.long_name, longName=attr, dataType="string", hidden=True
            )
        cmds.setAttr(self._plug_path(key), json.dumps(value), type="string")

    def __delitem__(self, key: str) -> None:
        if not self._exists(key):
            raise KeyError(key)
        cmds.deleteAttr(self._plug_path(key))

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str) or not _KEY_PATTERN.match(key):
            return False
        return self._exists(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self.keys())

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for ``key`` or ``default`` when missing."""
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> list[str]:
        """Return all metadata keys stored on the node."""
        attrs = cmds.listAttr(self._node.long_name, userDefined=True) or []
        prefix_length = len(META_PREFIX)
        return [attr[prefix_length:] for attr in attrs if attr.startswith(META_PREFIX)]

    def items(self) -> list[tuple[str, Any]]:
        """Return ``(key, value)`` pairs."""
        return list(self.as_dict().items())

    def as_dict(self) -> dict:
        """Read every metadata key in one go (one ``listAttr`` + one ``getAttr`` per key).

        Much cheaper than ``meta[key]`` in a loop, which pays an
        ``attributeQuery`` per key; use it when several keys are needed.
        """
        name = self._node.long_name
        attrs = cmds.listAttr(name, userDefined=True) or []
        prefix_length = len(META_PREFIX)
        result = {}
        for attr in attrs:
            if not attr.startswith(META_PREFIX):
                continue
            raw = cmds.getAttr(f"{name}.{attr}")
            result[attr[prefix_length:]] = json.loads(raw) if raw else None
        return result

    def update(self, mapping: dict) -> None:
        """Set several keys at once."""
        for key, value in mapping.items():
            self[key] = value

    def clear(self) -> None:
        """Remove every metadata attribute from the node."""
        for key in self.keys():
            del self[key]

    def __repr__(self) -> str:
        return f"MetaStore({dict(self.items())!r})"


def find_by_meta(key: str, value: Any = _ANY, node_type: str | None = None) -> list:
    """Return wrapped nodes carrying meta ``key``.

    Args:
        key: Metadata key to look for.
        value: When given, only nodes whose stored value equals it are returned.
        node_type: Optional Maya node type filter (e.g. ``"joint"``).
    """
    attr = _attr_name(key)
    kwargs = {"long": True, "objectsOnly": True}
    if node_type:
        kwargs["type"] = node_type
    candidates = cmds.ls(f"*.{attr}", **kwargs) or []
    found = []
    for name in candidates:
        node = resolve(name)
        if value is _ANY or node.meta.get(key) == value:
            found.append(node)
    return found
