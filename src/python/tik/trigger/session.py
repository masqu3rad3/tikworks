"""The TD-facing handler: ``Session`` and ``ActionHandle``.

    from tik import trigger
    rig = trigger.Session.open("hero.tr")
    base = rig.add("reference", file="baseRig.tr")
    base["scripts/head_rotation"].enabled = False
    rig.build(until="weights")
    rig.save(increment=True)
"""

from __future__ import annotations

import datetime
import getpass
from pathlib import Path
from typing import Any, Optional

from tik.trigger.core import registry, versioning
from tik.trigger.core.document import EXTENSION, ActionNode, Document, join_path, split_path
from tik.trigger.core.events import EventBus
from tik.trigger.core.exceptions import SessionError, SessionSaveError
from tik.trigger.core.steps import REFERENCE_TYPE, StepResult

_SETTINGS_ONLY = {"_session", "_node", "_path", "_linked", "_ref_handle", "_ref_path"}


class ActionHandle:
    """Attribute-style access to one action in a session.

    ``handle.some_field`` reads/writes a validated setting. For actions inside
    a reference (``is_linked``), writes become overrides on the reference.
    """

    def __init__(self, session: "Session", node: ActionNode, path: str,
                 ref_handle: Optional["ActionHandle"] = None, ref_path: str = "") -> None:
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "_node", node)
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "_ref_handle", ref_handle)
        object.__setattr__(self, "_ref_path", ref_path)
        object.__setattr__(self, "_linked", ref_handle is not None)

    # ---------------------------------------------------------- identity
    @property
    def name(self) -> str:
        return self._node.name

    @property
    def type(self) -> str:
        return self._node.type

    @property
    def path(self) -> str:
        return self._path

    @property
    def node(self) -> ActionNode:
        return self._node

    @property
    def is_linked(self) -> bool:
        return self._linked

    @property
    def action_class(self) -> type:
        return registry.get_action(self._node.type)

    def __repr__(self) -> str:
        flag = " linked" if self._linked else ""
        return f"<Action {self._path} ({self._node.type}){flag}>"

    # ----------------------------------------------------------- enabled
    @property
    def enabled(self) -> bool:
        if self._linked:
            override = self._override().get("enabled")
            return self._node.enabled if override is None else bool(override)
        return self._node.enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if self._linked:
            self._override()["enabled"] = bool(value)
            self._session._touch()
        else:
            self._node.enabled = bool(value)
            self._session._touch()

    # ---------------------------------------------------------- settings
    def _override(self) -> dict:
        overrides = self._ref_handle._node.settings.setdefault("overrides", {})
        return overrides.setdefault(self._ref_path, {})

    @property
    def settings(self) -> dict:
        """Effective settings (defaults + stored + overrides)."""
        action = self.action_class(settings=self._node.settings)
        if self._linked:
            action.apply(self._override().get("settings", {}), strict=False)
        return action.values()

    def __getattr__(self, item: str) -> Any:
        if item.startswith("_"):
            raise AttributeError(item)
        fields = self.action_class.fields()
        if item not in fields:
            raise AttributeError(f"'{self._node.type}' has no setting '{item}'.")
        return self.settings[item]

    def __setattr__(self, item: str, value: Any) -> None:
        if isinstance(getattr(type(self), item, None), property):
            object.__setattr__(self, item, value)
            return
        fields = self.action_class.fields()
        if item not in fields:
            raise AttributeError(f"'{self._node.type}' has no setting '{item}'.")
        validated = fields[item].validate(value)
        if self._linked:
            self._override().setdefault("settings", {})[item] = validated
        else:
            self._node.settings[item] = validated
        self._session._touch()

    def set(self, **settings) -> "ActionHandle":
        for key, value in settings.items():
            setattr(self, key, value)
        return self

    def reset(self, field_name: Optional[str] = None) -> None:
        """Drop overrides (linked) or restore defaults (own action)."""
        if self._linked:
            override = self._override()
            if field_name is None:
                override.clear()
            else:
                override.get("settings", {}).pop(field_name, None)
        else:
            if field_name is None:
                self._node.settings.clear()
            else:
                self._node.settings.pop(field_name, None)
        self._session._touch()

    # ---------------------------------------------------------- children
    @property
    def children(self) -> list["ActionHandle"]:
        if self._linked:
            return [
                ActionHandle(self._session, child, join_path(self._path, child.name),
                             self._ref_handle, join_path(self._ref_path, child.name))
                for child in self._node.children
            ]
        own = [ActionHandle(self._session, child, join_path(self._path, child.name)) for child in self._node.children]
        if self._node.type == REFERENCE_TYPE:
            return self._referenced_children() + own
        return own

    def _referenced_children(self) -> list["ActionHandle"]:
        try:
            document = self._session._referenced_document(self)
        except SessionError:
            return []
        return [
            ActionHandle(self._session, child, join_path(self._path, child.name), self, child.name)
            for child in document.actions
        ]

    def __getitem__(self, sub_path: str) -> "ActionHandle":
        parts = split_path(sub_path)
        handle = self
        for part in parts:
            match = next((child for child in handle.children if child.name == part), None)
            if match is None:
                raise SessionError(f"No action at '{join_path(handle.path, part)}'.")
            handle = match
        return handle

    def add(self, action_type: str, name: Optional[str] = None, index: Optional[int] = None, **settings) -> "ActionHandle":
        if self._linked:
            raise SessionError("Cannot add actions inside a referenced session; open it instead.")
        return self._session.add(action_type, name, parent=self._path, index=index, **settings)


class Session:
    """A ``.tr`` document and the runner that builds it."""

    EXTENSION = EXTENSION

    def __init__(self, file_path: Optional[str] = None, events: Optional[EventBus] = None) -> None:
        self.events = events or EventBus()
        self.document = Document()
        self.file_path: Optional[Path] = None
        self._saved_state = self.document.to_dict()
        self._reference_cache: dict[str, Document] = {}
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._last_state = self.document.to_dict()
        if file_path:
            self.load(file_path)

    @classmethod
    def open(cls, file_path: str, events: Optional[EventBus] = None) -> "Session":
        return cls(file_path=file_path, events=events)

    # ------------------------------------------------------------ state
    UNDO_LIMIT = 50

    def _touch(self) -> None:
        """Record an undo step when the document changed since the last touch."""
        self._reference_cache.clear()
        state = self.document.to_dict()
        if state != self._last_state:
            self._undo.append(self._last_state)
            del self._undo[: -self.UNDO_LIMIT]
            self._redo.clear()
            self._last_state = state

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.document.to_dict())
        self.document = Document.from_dict(self._undo.pop())
        self._last_state = self.document.to_dict()
        self._reference_cache.clear()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.document.to_dict())
        self.document = Document.from_dict(self._redo.pop())
        self._last_state = self.document.to_dict()
        self._reference_cache.clear()
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def is_modified(self) -> bool:
        return self.document.to_dict() != self._saved_state

    @property
    def directory(self) -> str:
        return str(self.file_path.parent) if self.file_path else ""

    @property
    def name(self) -> str:
        return self.file_path.name if self.file_path else "untitled"

    def new(self) -> None:
        self.document = Document()
        self.file_path = None
        self._saved_state = self.document.to_dict()
        self._last_state = self._saved_state
        self._undo.clear()
        self._redo.clear()
        self._reference_cache.clear()

    def load(self, file_path: str) -> None:
        path = Path(file_path)
        self.document = Document.load(path)
        self.file_path = path
        self._saved_state = self.document.to_dict()
        self._last_state = self._saved_state
        self._undo.clear()
        self._redo.clear()
        self._reference_cache.clear()
        self.events.log(f"Session loaded: {path}")

    def save(self, file_path: Optional[str] = None, increment: bool = False) -> Path:
        target = Path(file_path) if file_path else self.file_path
        if target is None:
            raise SessionSaveError("No file path given for the session.")
        if target.suffix != EXTENSION:
            target = target.with_suffix(EXTENSION)
        if increment:
            target = versioning.next_version(target)
        now = datetime.datetime.now().isoformat(timespec="seconds")
        self.document.meta.setdefault("created_at", now)
        self.document.meta.setdefault("author", getpass.getuser())
        self.document.meta["modified_at"] = now
        self.document.save(target)
        self.file_path = target
        self._saved_state = self.document.to_dict()
        self.events.log(f"Session saved: {target}")
        return target

    def increment(self) -> Path:
        return self.save(increment=True)

    # -------------------------------------------------------------- tree
    @property
    def actions(self) -> list[ActionHandle]:
        return [ActionHandle(self, node, node.name) for node in self.document.actions]

    def walk(self) -> list[ActionHandle]:
        """Every handle depth-first, including referenced (linked) ones."""
        found: list[ActionHandle] = []

        def _visit(handle: ActionHandle) -> None:
            found.append(handle)
            for child in handle.children:
                _visit(child)

        for handle in self.actions:
            _visit(handle)
        return found

    def __getitem__(self, path: str) -> ActionHandle:
        parts = split_path(path)
        if not parts:
            raise SessionError("Empty action path.")
        root = next((handle for handle in self.actions if handle.name == parts[0]), None)
        if root is None:
            raise SessionError(f"No action at '{parts[0]}'.")
        return root[join_path(*parts[1:])] if len(parts) > 1 else root

    def find(self, path: str) -> Optional[ActionHandle]:
        try:
            return self[path]
        except SessionError:
            return None

    def __contains__(self, path: str) -> bool:
        return self.find(path) is not None

    def paths(self) -> list[str]:
        return self.document.paths()

    def add(
        self,
        action_type: str,
        name: Optional[str] = None,
        *,
        parent: Optional[str | ActionHandle] = None,
        after: Optional[str | ActionHandle] = None,
        index: Optional[int] = None,
        **settings,
    ) -> ActionHandle:
        """Add an action; ``after`` places it next to a sibling, ``parent`` nests it."""
        action_cls = registry.get_action(action_type)
        action = action_cls(settings=settings)  # validates
        parent_path = parent.path if isinstance(parent, ActionHandle) else parent
        if after is not None:
            after_path = after.path if isinstance(after, ActionHandle) else after
            parts = split_path(after_path)
            parent_path = join_path(*parts[:-1]) or None
            siblings = self.document.siblings(parent_path)
            index = [node.name for node in siblings].index(parts[-1]) + 1
        node = ActionNode(name=name or action_type, type=action_type, settings=action.values())
        path = self.document.add(node, parent=parent_path, index=index)
        self._touch()
        return self[path]

    def remove(self, path: str | ActionHandle) -> None:
        self.document.remove(path.path if isinstance(path, ActionHandle) else path)
        self._touch()

    def move(self, path: str | ActionHandle, *, parent: Optional[str] = None,
             index: Optional[int] = None, after: Optional[str] = None) -> ActionHandle:
        path = path.path if isinstance(path, ActionHandle) else path
        new_path = self.document.move(path, parent=parent, index=index, after=after)
        self._touch()
        return self[new_path]

    def rename(self, path: str | ActionHandle, new_name: str) -> ActionHandle:
        path = path.path if isinstance(path, ActionHandle) else path
        new_path = self.document.rename(path, new_name)
        self._touch()
        return self[new_path]

    def duplicate(self, path: str | ActionHandle) -> ActionHandle:
        path = path.path if isinstance(path, ActionHandle) else path
        new_path = self.document.duplicate(path)
        self._touch()
        return self[new_path]

    # ------------------------------------------------------- references
    def _referenced_document(self, handle: ActionHandle) -> Document:
        from tik.trigger.actions.reference.reference import Reference

        key = handle.path
        if key not in self._reference_cache:
            document, _dir, _file = Reference.expand(handle.node, self.directory)
            self._reference_cache[key] = document
        return self._reference_cache[key]

    # ------------------------------------------------------------ running
    def _runner(self):
        from tik.trigger.maya.runner import Runner

        return Runner(self.events)

    def validate(self) -> list[str]:
        """Pre-flight problems for every runnable step (files missing, etc.)."""
        runner = self._runner()
        problems: list[str] = []
        try:
            plan = runner.plan(self.document, self.directory)
        except SessionError as error:
            return [str(error)]
        problems.extend(plan.problems)
        for step in plan.steps:
            action = registry.get_action(step.node.type)(settings=step.node.settings)
            from tik.trigger.core.action import ActionContext

            ctx = ActionContext(session=self, events=self.events,
                                base_dir=step.base_dir, path=step.path)
            problems.extend(f"{step.path}: {item}" for item in action.validate(ctx))
        return problems

    def build(self, until: Optional[str | ActionHandle] = None, reset_scene: bool = True) -> list[StepResult]:
        """Reset the scene and run every enabled action (optionally stopping after ``until``)."""
        until = until.path if isinstance(until, ActionHandle) else until
        self.events.log(f"Building {self.name}")
        return self._runner().run(self.document, self.directory, until=until, reset_scene=reset_scene, session=self)

    def run(self, path: str | ActionHandle) -> StepResult:
        """Run a single action in the current scene (no reset)."""
        path = path.path if isinstance(path, ActionHandle) else path
        return self._runner().run(self.document, self.directory, only=path, reset_scene=False, session=self)[0]

    def steps(self, until: Optional[str] = None):
        """The planned steps (what Build would run)."""
        return self._runner().plan(self.document, self.directory, until=until).steps

    def __repr__(self) -> str:
        return f"Session({self.name}, {len(self.document.actions)} actions)"
