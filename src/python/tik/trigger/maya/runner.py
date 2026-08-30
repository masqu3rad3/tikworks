"""Turn a document into ordered steps and run them.

Planning is pure; running resets the scene and wraps each step in an undo
chunk, which is why this lives in the Maya layer rather than in ``core``.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from tik.trigger.core import registry
from tik.trigger.core.action import ActionContext
from tik.trigger.core.document import Document, join_path
from tik.trigger.core.events import EventBus
from tik.trigger.core.exceptions import ActionExecutionError, SessionError
from tik.trigger.core.steps import (
    REFERENCE_TYPE,
    STEP_FAILED,
    STEP_FINISHED,
    STEP_SKIPPED,
    STEP_STARTED,
    Plan,
    Step,
    StepResult,
)

def new_scene() -> None:
    """Start a build from an empty scene."""
    from tik.trigger.guides import nodes

    nodes.new_scene()


def undo_chunk(label: str):
    """One undo step per action, so a failed build rolls back cleanly."""
    from tik.trigger.guides import nodes

    return nodes.undo_chunk(label)


class Runner:
    """Plans and executes a document."""

    def __init__(self, events: Optional[EventBus] = None, loader: Optional[Callable] = None) -> None:
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
            new_scene()
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
            with undo_chunk(f"Trigger: {step.path}"):
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
