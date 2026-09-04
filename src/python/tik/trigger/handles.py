"""What a TD holds while editing a session: ``ActionHandle`` and ``PhaseView``.

Both are views onto the session's document. They keep no state of their own,
so undo, the dirty flag and the reference cache behave the same through them
as through ``Session`` itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from tik.trigger.core import registry
from tik.trigger.core.document import BUILD, ActionNode, join_path, split_path
from tik.trigger.core.exceptions import SessionError
from tik.trigger.core.steps import REFERENCE_TYPE

if TYPE_CHECKING:
    from tik.trigger.session import Session

_SETTINGS_ONLY = {
    "_session",
    "_node",
    "_path",
    "_linked",
    "_ref_handle",
    "_ref_path",
    "_phase",
}


class ActionHandle:
    """Attribute-style access to one action in a session.

    ``handle.some_field`` reads/writes a validated setting. For actions inside
    a reference (``is_linked``), writes become overrides on the reference.
    """

    def __init__(
        self,
        session: "Session",
        node: ActionNode,
        path: str,
        ref_handle: Optional["ActionHandle"] = None,
        ref_path: str = "",
        phase: str = BUILD,
    ) -> None:
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "_node", node)
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "_ref_handle", ref_handle)
        object.__setattr__(self, "_ref_path", ref_path)
        object.__setattr__(self, "_phase", phase)
        object.__setattr__(self, "_linked", ref_handle is not None)

    # ---------------------------------------------------------- identity
    @property
    def name(self) -> str:
        """The action's name, the last segment of its path."""
        return self._node.name

    @property
    def type(self) -> str:
        """The registered action type this node runs."""
        return self._node.type

    @property
    def path(self) -> str:
        """``parent/child`` path of this action inside its phase list."""
        return self._path

    @property
    def node(self) -> ActionNode:
        """The underlying document node."""
        return self._node

    @property
    def is_linked(self) -> bool:
        """True when the action lives in a referenced session (read-only tree)."""
        return self._linked

    @property
    def phase(self) -> str:
        """Which of the session's two lists this handle came from."""
        return self._phase

    @property
    def action_class(self) -> type:
        """The ``Action`` subclass registered for this node's type."""
        return registry.get_action(self._node.type)

    def __repr__(self) -> str:
        flag = " linked" if self._linked else ""
        where = "" if self._phase == BUILD else f" [{self._phase}]"
        return f"<Action {self._path} ({self._node.type}){flag}{where}>"

    # ----------------------------------------------------------- enabled
    @property
    def enabled(self) -> bool:
        """Whether the runner executes this action; overrides apply for linked ones."""
        if self._linked:
            override = self._override().get("enabled")
            return self._node.enabled if override is None else bool(override)
        return self._node.enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if self._linked:
            self._override()["enabled"] = bool(value)
            self._session.touch()
        else:
            self._node.enabled = bool(value)
            self._session.touch()

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
        self._session.touch()

    def set(self, **settings) -> "ActionHandle":
        """Assign several settings at once; returns the handle for chaining."""
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
        self._session.touch()

    # ---------------------------------------------------------- children
    @property
    def children(self) -> list["ActionHandle"]:
        """Child actions, including a reference's own actions when linked."""
        if self._linked:
            return [
                ActionHandle(
                    self._session,
                    child,
                    join_path(self._path, child.name),
                    self._ref_handle,
                    join_path(self._ref_path, child.name),
                    phase=self._phase,
                )
                for child in self._node.children
            ]
        own = [
            ActionHandle(
                self._session,
                child,
                join_path(self._path, child.name),
                phase=self._phase,
            )
            for child in self._node.children
        ]
        if self._node.type == REFERENCE_TYPE:
            return self._referenced_children() + own
        return own

    def _referenced_children(self) -> list["ActionHandle"]:
        try:
            document = self._session._referenced_document(self)
        except SessionError:
            return []
        return [
            ActionHandle(
                self._session,
                child,
                join_path(self._path, child.name),
                self,
                child.name,
                phase=self._phase,
            )
            for child in document.actions
        ]

    def __getitem__(self, sub_path: str) -> "ActionHandle":
        parts = split_path(sub_path)
        handle = self
        for part in parts:
            match = next(
                (child for child in handle.children if child.name == part), None
            )
            if match is None:
                raise SessionError(f"No action at '{join_path(handle.path, part)}'.")
            handle = match
        return handle

    def add(
        self,
        action_type: str,
        name: Optional[str] = None,
        index: Optional[int] = None,
        **settings,
    ) -> "ActionHandle":
        """Add a child action under this one (not allowed inside a reference)."""
        if self._linked:
            raise SessionError(
                "Cannot add actions inside a referenced session; open it instead."
            )
        return self._session.add(
            action_type,
            name,
            parent=self._path,
            index=index,
            phase=self._phase,
            **settings,
        )


class PhaseView:
    """The tree API of one of a session's two action lists.

    ``session.publish`` is one of these. It holds no state of its own -- every
    verb delegates to the session with its phase attached -- so undo, the dirty
    flag and the reference cache behave identically in both lists.
    """

    def __init__(self, session: "Session", phase: str) -> None:
        self._session = session
        self._phase = phase

    @property
    def phase(self) -> str:
        """``build`` or ``publish``."""
        return self._phase

    @property
    def actions(self) -> list[ActionHandle]:
        """The root actions of this phase, in run order."""
        return self._session.root_handles(self._phase)

    def __getitem__(self, path: str) -> ActionHandle:
        return self._session.handle(path, phase=self._phase)

    def find(self, path: str) -> Optional[ActionHandle]:
        """The action at ``path``, or None when there is none."""
        try:
            return self[path]
        except SessionError:
            return None

    def __contains__(self, path: str) -> bool:
        return self.find(path) is not None

    def __iter__(self):
        return iter(self.actions)

    def __len__(self) -> int:
        return len(self._session.document.roots(self._phase))

    def paths(self) -> list[str]:
        """Every action path in this phase, depth first."""
        return self._session.document.paths(self._phase)

    def walk(self) -> list[ActionHandle]:
        """Every action handle in this phase, depth first."""
        return self._session.walk(phase=self._phase)

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
        return self._session.add(
            action_type,
            name,
            parent=parent,
            after=after,
            index=index,
            phase=self._phase,
            **settings,
        )

    def remove(self, path: str | ActionHandle) -> None:
        """Remove the action at ``path`` and everything under it."""
        self._session.remove(path, phase=self._phase)

    def move(
        self,
        path: str | ActionHandle,
        *,
        parent: Optional[str] = None,
        index: Optional[int] = None,
        after: Optional[str] = None,
    ) -> ActionHandle:
        """Move an action under ``parent``, to ``index``, or ``after`` a sibling."""
        return self._session.move(
            path, parent=parent, index=index, after=after, phase=self._phase
        )

    def rename(self, path: str | ActionHandle, new_name: str) -> ActionHandle:
        """Rename an action; returns the handle at its new path."""
        return self._session.rename(path, new_name, phase=self._phase)

    def duplicate(self, path: str | ActionHandle) -> ActionHandle:
        """Copy an action next to itself with a unique name."""
        return self._session.duplicate(path, phase=self._phase)

    def __repr__(self) -> str:
        return f"<PhaseView {self._phase}: {len(self)} actions>"
