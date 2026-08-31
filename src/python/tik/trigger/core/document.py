"""The session document: a tree of actions (``.tr`` schema 4)."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from .exceptions import SessionError, SessionLoadError, SessionSaveError
from .guide_document import GuideDocument

SCHEMA_VERSION = 5
EXTENSION = ".tr"
SEPARATOR = "/"


@dataclass
class ActionNode:
    """One action in the pipeline; may hold children."""

    name: str
    type: str
    enabled: bool = True
    settings: dict = field(default_factory=dict)
    children: list["ActionNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "enabled": self.enabled,
            "settings": copy.deepcopy(self.settings),
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActionNode":
        settings = data.get("settings")
        if settings is None:  # old flat format used "data"
            settings = data.get("data", {})
        return cls(
            name=data["name"],
            type=data["type"],
            enabled=bool(data.get("enabled", True)),
            settings=dict(settings or {}),
            children=[cls.from_dict(item) for item in data.get("children", [])],
        )

    def copy(self) -> "ActionNode":
        return ActionNode.from_dict(self.to_dict())


def join_path(*parts: str) -> str:
    return SEPARATOR.join(part for part in parts if part)


def split_path(path: str) -> list[str]:
    return [part for part in path.split(SEPARATOR) if part]


@dataclass
class Document:
    """Root of a ``.tr`` file."""

    schema: int = SCHEMA_VERSION
    meta: dict = field(default_factory=dict)
    actions: list[ActionNode] = field(default_factory=list)
    #: The rig's guides. A live ``GuideDocument``: the session is their only
    #: store, so the Maya scene holds nothing but a rendering of them, and a
    #: ``.tr`` is a self-contained rig description.
    guides: GuideDocument = field(default_factory=GuideDocument)

    # ---------------------------------------------------------- serialize
    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "meta": dict(self.meta),
            "actions": [node.to_dict() for node in self.actions],
            "guides": self.guides.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        if isinstance(data, list):  # very old: bare list of actions
            data = {"actions": data}
        schema = int(data.get("schema", 0))
        if schema > SCHEMA_VERSION:
            raise SessionLoadError(
                f"Session schema {schema} is newer than supported {SCHEMA_VERSION}."
            )
        return cls(
            schema=SCHEMA_VERSION,
            meta=dict(data.get("meta", {})),
            actions=[ActionNode.from_dict(item) for item in data.get("actions", [])],
            guides=GuideDocument.from_dict(data.get("guides") or {}),
        )

    @classmethod
    def load(cls, file_path) -> "Document":
        path = Path(file_path)
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError) as error:
            raise SessionLoadError(f"Cannot load '{path}': {error}") from error

    def save(self, file_path) -> Path:
        path = Path(file_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        except OSError as error:
            raise SessionSaveError(f"Cannot write '{path}': {error}") from error
        return path

    def copy(self) -> "Document":
        return Document.from_dict(self.to_dict())

    # --------------------------------------------------------------- tree
    def walk(self) -> Iterator[tuple[str, ActionNode, Optional[ActionNode]]]:
        """Yield ``(path, node, parent)`` depth-first."""

        def _walk(nodes, parent, prefix):
            for node in nodes:
                path = join_path(prefix, node.name)
                yield path, node, parent
                yield from _walk(node.children, node, path)

        yield from _walk(self.actions, None, "")

    def paths(self) -> list[str]:
        return [path for path, _node, _parent in self.walk()]

    def find(self, path: str) -> Optional[ActionNode]:
        nodes = self.actions
        node = None
        for part in split_path(path):
            node = next((item for item in nodes if item.name == part), None)
            if node is None:
                return None
            nodes = node.children
        return node

    def require(self, path: str) -> ActionNode:
        node = self.find(path)
        if node is None:
            raise SessionError(f"No action at '{path}'.")
        return node

    def parent_of(self, path: str) -> Optional[ActionNode]:
        parts = split_path(path)
        return self.find(join_path(*parts[:-1])) if len(parts) > 1 else None

    def siblings(self, parent_path: Optional[str]) -> list[ActionNode]:
        if not parent_path:
            return self.actions
        return self.require(parent_path).children

    def path_of(self, node: ActionNode) -> Optional[str]:
        for path, candidate, _parent in self.walk():
            if candidate is node:
                return path
        return None

    def unique_name(self, parent_path: Optional[str], base: str) -> str:
        names = {node.name for node in self.siblings(parent_path)}
        if base not in names:
            return base
        stem = base.rstrip("0123456789") or base
        digits = base[len(stem):]
        counter = int(digits) if digits else 0
        while True:
            counter += 1
            candidate = f"{stem}{counter}"
            if candidate not in names:
                return candidate

    def add(
        self,
        node: ActionNode,
        parent: Optional[str] = None,
        index: Optional[int] = None,
    ) -> str:
        """Insert ``node`` and return its path (name made unique among siblings)."""
        siblings = self.siblings(parent)
        node.name = self.unique_name(parent, node.name)
        if index is None:
            siblings.append(node)
        else:
            siblings.insert(index, node)
        return join_path(parent or "", node.name)

    def remove(self, path: str) -> ActionNode:
        node = self.require(path)
        parent = self.parent_of(path)
        siblings = parent.children if parent is not None else self.actions
        siblings.remove(node)
        return node

    def move(
        self,
        path: str,
        parent: Optional[str] = None,
        index: Optional[int] = None,
        after: Optional[str] = None,
    ) -> str:
        """Move an action (and its subtree).

        ``after`` places it right after that sibling (its parent wins);
        otherwise it goes under ``parent`` at ``index`` (end when omitted).
        """
        node = self.require(path)
        if after is not None:
            after_node = self.require(after)
            parts = split_path(after)
            parent = join_path(*parts[:-1]) or None
        if parent and (parent == path or parent.startswith(path + SEPARATOR)):
            raise SessionError("Cannot move an action under itself.")
        old_parent = self.parent_of(path)
        old_siblings = old_parent.children if old_parent is not None else self.actions
        old_index = old_siblings.index(node)
        old_siblings.pop(old_index)
        new_siblings = self.siblings(parent)
        if after is not None:
            index = new_siblings.index(after_node) + 1
        elif index is None:
            index = len(new_siblings)
        elif new_siblings is old_siblings and index > old_index:
            index -= 1
        if new_siblings is not old_siblings:
            node.name = self.unique_name(parent, node.name)
        new_siblings.insert(index, node)
        return join_path(parent or "", node.name)

    def rename(self, path: str, new_name: str) -> str:
        node = self.require(path)
        if SEPARATOR in new_name or not new_name.strip():
            raise SessionError(f"Invalid action name '{new_name}'.")
        parent = self.parent_of(path)
        siblings = parent.children if parent is not None else self.actions
        if any(item is not node and item.name == new_name for item in siblings):
            raise SessionError(f"An action named '{new_name}' already exists here.")
        node.name = new_name
        parent_path = join_path(*split_path(path)[:-1])
        return join_path(parent_path, new_name)

    def duplicate(self, path: str) -> str:
        node = self.require(path)
        parent = self.parent_of(path)
        siblings = parent.children if parent is not None else self.actions
        clone = node.copy()
        parent_path = join_path(*split_path(path)[:-1])
        return self.add(clone, parent=parent_path or None, index=siblings.index(node) + 1)
