"""Step types shared by the planner, the session and the UI.

Pure data: no Maya. The ``Runner`` that produces and executes these lives in
``tik.trigger.maya.runner``, because running touches the scene.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .document import ActionNode

REFERENCE_TYPE = "reference"

STEP_STARTED = "step_started"
STEP_FINISHED = "step_finished"
STEP_FAILED = "step_failed"
STEP_SKIPPED = "step_skipped"


@dataclass
class Step:
    """A runnable action with its resolved context."""

    path: str
    node: ActionNode
    base_dir: str
    chain: tuple[str, ...] = ()  # referenced files leading here
    depth: int = 0
    linked: bool = False

    @property
    def display_chain(self) -> str:
        return " > ".join([*(Path(item).name for item in self.chain), self.path])


@dataclass
class StepResult:
    path: str
    status: str  # "done" | "failed" | "skipped"
    seconds: float = 0.0
    error: Optional[str] = None


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


