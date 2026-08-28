"""Turn a document into ordered steps and run them."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from . import registry
from .action import ActionContext
from .document import ActionNode, Document, join_path
from .events import EventBus
from .exceptions import ActionExecutionError, SessionError

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


class Runner:
    """Plans and executes a document."""

    def __init__(self, backend, events: Optional[EventBus] = None, loader: Optional[Callable] = None) -> None:
        self.backend = backend
        self.events = events or EventBus()
        self.loader = loader or Document.load

    # ------------------------------------------------------------- planning
    def plan(
        self,
        document: Document,
        base_dir: str = "",
        until: Optional[str] = None,
        only: Optional[str] = None,
    ) -> Plan:
        """Flatten ``document`` depth-first into steps, expanding references."""
        plan = Plan()
        self._collect(document.actions, "", base_dir, (), 0, False, plan)
        if only is not None:
            plan.steps = [step for step in plan.steps if step.path == only]
            if not plan.steps:
                raise SessionError(f"No runnable action at '{only}'.")
        elif until is not None:
            if not any(step.path == until for step in plan.steps):
                raise SessionError(f"No runnable action at '{until}'.")
            kept = []
            for step in plan.steps:
                kept.append(step)
                if step.path == until:
                    break
            plan.steps = kept
        return plan

    def _collect(self, nodes, prefix, base_dir, chain, depth, linked, plan) -> None:
        for node in nodes:
            path = join_path(prefix, node.name)
            if not node.enabled:
                continue
            if node.type == REFERENCE_TYPE:
                self._collect_reference(node, path, base_dir, chain, depth, plan)
                continue
            plan.steps.append(Step(path, node, base_dir, chain, depth, linked))
            self._collect(node.children, path, base_dir, chain, depth + 1, linked, plan)

    def _collect_reference(self, node, path, base_dir, chain, depth, plan) -> None:
        from tik.trigger.actions.reference.reference import Reference  # local: avoids cycle

        try:
            expanded, ref_dir, ref_file = Reference.expand(node, base_dir, self.loader, chain)
        except SessionError as error:
            plan.problems.append(f"{path}: {error}")
            self.events.log(f"{path}: {error}", level="error")
            raise
        self._collect(expanded.actions, path, ref_dir, chain + (ref_file,), depth + 1, True, plan)
        # a reference may also carry its own (local) children, run after the referenced ones
        self._collect(node.children, path, base_dir, chain, depth + 1, False, plan)

    # -------------------------------------------------------------- running
    def run(
        self,
        document: Document,
        base_dir: str = "",
        until: Optional[str] = None,
        only: Optional[str] = None,
        reset_scene: bool = True,
        session: Any = None,
    ) -> list[StepResult]:
        plan = self.plan(document, base_dir, until=until, only=only)
        if reset_scene and only is None:
            self.backend.new_scene()
        results: list[StepResult] = []
        total = len(plan.steps)
        for number, step in enumerate(plan.steps, start=1):
            self.events.progress(number, total, step.path)
            results.append(self._run_step(step, session))
        return results

    def _run_step(self, step: Step, session) -> StepResult:
        action_cls = registry.get_action(step.node.type)
        action = action_cls(settings=step.node.settings)
        ctx = ActionContext(
            backend=self.backend,
            session=session,
            events=self.events,
            paths={"directory": step.base_dir},
            base_dir=step.base_dir,
            path=step.path,
            depth=step.depth,
        )
        self.events.emit(STEP_STARTED, path=step.path)
        started = time.perf_counter()
        problems = action.validate(ctx)
        if problems:
            message = "; ".join(problems)
            self.events.emit(STEP_FAILED, path=step.path, error=message)
            raise ActionExecutionError(f"{step.display_chain}: {message}", action_name=step.path)
        try:
            with self.backend.undo_chunk(f"Trigger: {step.path}"):
                action.run(ctx)
        except Exception as error:  # noqa: BLE001 - report then wrap
            seconds = time.perf_counter() - started
            self.events.emit(STEP_FAILED, path=step.path, error=str(error), seconds=seconds)
            self.events.error(error, context=step.display_chain)
            raise ActionExecutionError(f"{step.display_chain}: {error}", action_name=step.path) from error
        seconds = time.perf_counter() - started
        self.events.emit(STEP_FINISHED, path=step.path, seconds=seconds)
        self.events.log(f"{step.path} done in {seconds:.2f} s")
        return StepResult(step.path, "done", seconds)
