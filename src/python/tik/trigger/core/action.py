"""Action base class and its run context."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from tik.core.fields import Schema


@dataclass
class ActionContext:
    """What an action gets when it runs."""

    session: Any = None
    events: Any = None
    paths: dict = field(default_factory=dict)
    base_dir: str = ""
    path: str = ""  # action path in the running document (for logs)
    depth: int = 0
    rig: Any = None  # the RigScaffold, set by the Maya runner; core never reads it
    scripts: Any = None  # the run's ScriptSpace, set by the Maya runner; core ignores

    def resolve(self, file_path: str) -> Path:
        """Return an absolute path; relative paths are resolved from ``base_dir``."""
        path = Path(file_path)
        if not path.is_absolute() and self.base_dir:
            path = Path(self.base_dir) / path
        return path

    def log(self, message: str, level: str = "info") -> None:
        """Emit a log line to the UI, if an event bus is attached."""
        if self.events is not None:
            self.events.emit("log", level=level, message=message)


class Action(Schema):
    """Base class for pipeline actions: typed fields + ``run(ctx)``."""

    label: str = ""
    action_type: str = ""  # stamped by @register_action
    category: str = "utility"  # stamped by @register_action
    scope: str = "build"  # stamped by @register_action: build | publish | both
    icon: str = ""  # stamped by @register_action
    info: str = ""  # shown by the "?" button; defaults to the class docstring

    def __init__(self, settings: Optional[dict] = None) -> None:
        if settings:
            self.apply(settings, strict=False)

    @classmethod
    def display_label(cls) -> str:
        """The label shown in the UI (falls back to the type name)."""
        return cls.label or cls.action_type.replace("_", " ").title() or cls.__name__

    @classmethod
    def description(cls) -> str:
        """The help text shown in the UI (falls back to the class docstring)."""
        return cls.info or (cls.__doc__ or "").strip()

    def summary(self) -> str:
        """Short text shown next to the action name in the pipeline."""
        for name, field_obj in self.fields().items():
            if field_obj.type_name == "file":
                value = getattr(self, name)
                if value:
                    return Path(value).name
        return ""

    def validate(self, ctx: ActionContext) -> list[str]:
        """Return pre-flight problems (empty = ok)."""
        problems: list[str] = []
        for name, field_obj in self.fields().items():
            if (
                field_obj.type_name == "file"
                and getattr(field_obj, "mode", "") == "open"
            ):
                value = getattr(self, name)
                if value and not ctx.resolve(value).exists():
                    problems.append(f"{name}: file not found ({value})")
        return problems

    def run(self, ctx: ActionContext) -> None:
        """Execute the action."""
        raise NotImplementedError

    def save_from_scene(self, ctx: ActionContext) -> list[str]:
        """Write side files from the current scene (weights, shapes...). Optional."""
        return []
