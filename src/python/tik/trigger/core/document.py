"""The session document: build + publish actions and guides (``.tr`` schema 7)."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from .exceptions import SessionError, SessionLoadError, SessionSaveError
from .guide_document import GuideDocument

SCHEMA_VERSION = 7
EXTENSION = ".tr"
SEPARATOR = "/"

#: The two action lists a session holds. ``build`` makes the rig; ``publish``
#: runs only as the tail of a full build (see the 2026-09-03 design).
BUILD = "build"
PUBLISH = "publish"
PHASES = (BUILD, PUBLISH)


@dataclass
class ActionNode:
    """One action in the pipeline; may hold children."""

    name: str
    type: str
    enabled: bool = True
    settings: dict = field(default_factory=dict)
    children: list["ActionNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        """The JSON form stored in the ``.tr`` file."""
        return {
            "name": self.name,
            "type": self.type,
            "enabled": self.enabled,
            "settings": copy.deepcopy(self.settings),
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActionNode":
        """Rebuild a node from its JSON form (the old flat ``data`` key is accepted)."""
        settings = data.get("settings")
        if settings is None:  # old flat format used "data"
            settings = data.get("data", {})
        settings = _migrate_settings(data["type"], dict(settings or {}))
        return cls(
            name=data["name"],
            type=data["type"],
            enabled=bool(data.get("enabled", True)),
            settings=settings,
            children=[cls.from_dict(item) for item in data.get("children", [])],
        )

    def copy(self) -> "ActionNode":
        """A deep copy, children included."""
        return ActionNode.from_dict(self.to_dict())


def _migrate_settings(action_type: str, settings: dict) -> dict:
    """Let a registered action translate its own legacy settings."""
    from . import registry  # local: registry imports this module

    if not registry.is_action_registered(action_type):
        return settings
    return registry.get_action(action_type).migrate_settings(settings)


def join_path(*parts: str) -> str:
    """Join path parts with the separator, skipping empty ones."""
    return SEPARATOR.join(part for part in parts if part)


def split_path(path: str) -> list[str]:
    """Split an action path into its parts, skipping empty ones."""
    return [part for part in path.split(SEPARATOR) if part]


@dataclass
class Document:
    """Root of a ``.tr`` file."""

    schema: int = SCHEMA_VERSION
    meta: dict = field(default_factory=dict)
    actions: list[ActionNode] = field(default_factory=list)
    #: Post-build actions. Never run on their own: a publish action only ever
    #: executes as the tail of a fresh build, so it is guaranteed to see a
    #: scene that build just produced.
    publish: list[ActionNode] = field(default_factory=list)
    #: The rig's guides. A live ``GuideDocument``: the session is their only
    #: store, so the Maya scene holds nothing but a rendering of them, and a
    #: ``.tr`` is a self-contained rig description.
    guides: GuideDocument = field(default_factory=GuideDocument)

    # ---------------------------------------------------------- serialize
    def to_dict(self) -> dict:
        """The JSON form stored in the ``.tr`` file."""
        return {
            "schema": self.schema,
            "meta": dict(self.meta),
            "actions": [node.to_dict() for node in self.actions],
            "publish": [node.to_dict() for node in self.publish],
            "guides": self.guides.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Document":
        """Rebuild a document from its JSON form, migrating older schemas."""
        if isinstance(data, list):  # very old: bare list of actions
            data = {"actions": data}
        schema = int(data.get("schema", 0))
        if schema > SCHEMA_VERSION:
            raise SessionLoadError(
                f"Session schema {schema} is newer than supported {SCHEMA_VERSION}."
            )
        document = cls(
            schema=SCHEMA_VERSION,
            meta=dict(data.get("meta", {})),
            actions=[ActionNode.from_dict(item) for item in data.get("actions", [])],
            publish=[ActionNode.from_dict(item) for item in data.get("publish", [])],
            guides=GuideDocument.from_dict(data.get("guides") or {}),
        )
        if schema < 7:
            # A kinematics scope can only be translated with the guides in
            # hand, which the per-action ``migrate_settings`` hook cannot see.
            # Gated on the *stored* schema, so undo, redo and copy -- which all
            # round-trip through here with the schema already current -- never
            # re-run it.
            from .kinematics_migration import migrate_kinematics

            migrate_kinematics(document.actions, document.guides)
            migrate_kinematics(document.publish, document.guides)
        return document

    @classmethod
    def load(cls, file_path) -> "Document":
        """Read a ``.tr`` file; raises ``SessionLoadError`` on a bad file."""
        path = Path(file_path)
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError) as error:
            raise SessionLoadError(f"Cannot load '{path}': {error}") from error

    def save(self, file_path) -> Path:
        """Write the document as JSON, creating the folder if needed."""
        path = Path(file_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        except OSError as error:
            raise SessionSaveError(f"Cannot write '{path}': {error}") from error
        return path

    def copy(self) -> "Document":
        """A deep copy of the whole document."""
        return Document.from_dict(self.to_dict())

    # --------------------------------------------------------------- tree
    def roots(self, phase: str = BUILD) -> list[ActionNode]:
        """The top-level actions of one phase.

        The single seam between the two lists: every tree method below resolves
        its root through this, so there is one implementation, not two.
        """
        if phase == BUILD:
            return self.actions
        if phase == PUBLISH:
            return self.publish
        raise SessionError(f"Unknown phase '{phase}'.")

    def walk(
        self, phase: str = BUILD
    ) -> Iterator[tuple[str, ActionNode, Optional[ActionNode]]]:
        """Yield ``(path, node, parent)`` depth-first."""

        def _walk(nodes, parent, prefix):
            for node in nodes:
                path = join_path(prefix, node.name)
                yield path, node, parent
                yield from _walk(node.children, node, path)

        yield from _walk(self.roots(phase), None, "")

    def paths(self, phase: str = BUILD) -> list[str]:
        """Every action path in ``phase``, depth first."""
        return [path for path, _node, _parent in self.walk(phase)]

    def find(self, path: str, phase: str = BUILD) -> Optional[ActionNode]:
        """The node at ``path`` in ``phase``, or None."""
        nodes = self.roots(phase)
        node = None
        for part in split_path(path):
            node = next((item for item in nodes if item.name == part), None)
            if node is None:
                return None
            nodes = node.children
        return node

    def require(self, path: str, phase: str = BUILD) -> ActionNode:
        """The node at ``path``; raises ``SessionError`` when there is none."""
        node = self.find(path, phase)
        if node is None:
            raise SessionError(f"No action at '{path}'.")
        return node

    def parent_of(self, path: str, phase: str = BUILD) -> Optional[ActionNode]:
        """The parent node of ``path``, or None for a root."""
        parts = split_path(path)
        return self.find(join_path(*parts[:-1]), phase) if len(parts) > 1 else None

    def siblings(
        self, parent_path: Optional[str], phase: str = BUILD
    ) -> list[ActionNode]:
        """The children of ``parent_path``, or the roots when it is empty."""
        if not parent_path:
            return self.roots(phase)
        return self.require(parent_path, phase).children

    def path_of(self, node: ActionNode, phase: str = BUILD) -> Optional[str]:
        """The path at which ``node`` sits, or None when it is not in ``phase``."""
        for path, candidate, _parent in self.walk(phase):
            if candidate is node:
                return path
        return None

    def unique_name(
        self, parent_path: Optional[str], base: str, phase: str = BUILD
    ) -> str:
        """``base`` if free among the siblings, else the next numbered name."""
        names = {node.name for node in self.siblings(parent_path, phase)}
        if base not in names:
            return base
        stem = base.rstrip("0123456789") or base
        digits = base[len(stem) :]
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
        phase: str = BUILD,
    ) -> str:
        """Insert ``node`` and return its path (name made unique among siblings)."""
        siblings = self.siblings(parent, phase)
        node.name = self.unique_name(parent, node.name, phase)
        if index is None:
            siblings.append(node)
        else:
            siblings.insert(index, node)
        return join_path(parent or "", node.name)

    def remove(self, path: str, phase: str = BUILD) -> ActionNode:
        """Detach and return the node at ``path``."""
        node = self.require(path, phase)
        parent = self.parent_of(path, phase)
        siblings = parent.children if parent is not None else self.roots(phase)
        siblings.remove(node)
        return node

    def move(
        self,
        path: str,
        parent: Optional[str] = None,
        index: Optional[int] = None,
        after: Optional[str] = None,
        phase: str = BUILD,
    ) -> str:
        """Move an action (and its subtree) *within one phase*.

        ``after`` places it right after that sibling (its parent wins);
        otherwise it goes under ``parent`` at ``index`` (end when omitted).

        There is no cross-phase move: the caller removes from one list and adds
        to the other, which is what a drag between the two trees performs.
        """
        node = self.require(path, phase)
        if after is not None:
            after_node = self.require(after, phase)
            parts = split_path(after)
            parent = join_path(*parts[:-1]) or None
        if parent and (parent == path or parent.startswith(path + SEPARATOR)):
            raise SessionError("Cannot move an action under itself.")
        old_parent = self.parent_of(path, phase)
        old_siblings = (
            old_parent.children if old_parent is not None else self.roots(phase)
        )
        old_index = old_siblings.index(node)
        old_siblings.pop(old_index)
        new_siblings = self.siblings(parent, phase)
        if after is not None:
            index = new_siblings.index(after_node) + 1
        elif index is None:
            index = len(new_siblings)
        elif new_siblings is old_siblings and index > old_index:
            index -= 1
        if new_siblings is not old_siblings:
            node.name = self.unique_name(parent, node.name, phase)
        new_siblings.insert(index, node)
        return join_path(parent or "", node.name)

    def rename(self, path: str, new_name: str, phase: str = BUILD) -> str:
        """Rename the node at ``path``; returns its new path."""
        node = self.require(path, phase)
        if SEPARATOR in new_name or not new_name.strip():
            raise SessionError(f"Invalid action name '{new_name}'.")
        parent = self.parent_of(path, phase)
        siblings = parent.children if parent is not None else self.roots(phase)
        if any(item is not node and item.name == new_name for item in siblings):
            raise SessionError(f"An action named '{new_name}' already exists here.")
        node.name = new_name
        parent_path = join_path(*split_path(path)[:-1])
        return join_path(parent_path, new_name)

    def duplicate(self, path: str, phase: str = BUILD) -> str:
        """Copy the node at ``path`` next to itself; returns the copy's path."""
        node = self.require(path, phase)
        parent = self.parent_of(path, phase)
        siblings = parent.children if parent is not None else self.roots(phase)
        clone = node.copy()
        parent_path = join_path(*split_path(path)[:-1])
        return self.add(
            clone,
            parent=parent_path or None,
            index=siblings.index(node) + 1,
            phase=phase,
        )
