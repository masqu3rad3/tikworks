"""Action base class and its run context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from tik.core.fields import Schema

from .schemas import ActionInstance


@dataclass
class ActionContext:
    """What an action gets when it runs."""

    backend: Any
    session: Any = None
    events: Any = None
    paths: dict = field(default_factory=dict)

    def log(self, message: str, level: str = "info") -> None:
        if self.events is not None:
            self.events.emit("log", level=level, message=message)


class Action(Schema):
    """Base class for pipeline actions.

    Subclasses declare fields for their settings and implement ``run``.
    """

    label: str = ""
    action_type: str = ""  # stamped by @register_action

    def __init__(self, settings: Optional[dict] = None) -> None:
        if settings:
            self.apply(settings, strict=False)

    @classmethod
    def display_label(cls) -> str:
        return cls.label or cls.action_type or cls.__name__

    def run(self, ctx: ActionContext) -> None:
        """Execute the action."""
        raise NotImplementedError

    def save_assets(self, directory: str) -> list[str]:
        """Persist side files (weights, shapes...) next to the session. Optional."""
        return []

    def to_instance(self, name: str, enabled: bool = True) -> ActionInstance:
        return ActionInstance(
            action_type=self.action_type, name=name, enabled=enabled, settings=self.values()
        )

    @classmethod
    def from_instance(cls, instance: ActionInstance) -> "Action":
        return cls(settings=instance.settings)
