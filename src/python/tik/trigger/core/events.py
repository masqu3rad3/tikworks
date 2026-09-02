"""Tiny synchronous event bus so core code can report without knowing Qt."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable

PROGRESS = "progress"
LOG = "log"
ERROR = "error"

logger = logging.getLogger("tik.trigger")


class EventBus:
    """Subscribe callbacks to named events; ``emit`` calls them in order."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callable) -> Callable:
        self._subscribers[event].append(callback)
        return callback

    def unsubscribe(self, event: str, callback: Callable) -> None:
        if callback in self._subscribers.get(event, []):
            self._subscribers[event].remove(callback)

    def emit(self, event: str, **payload) -> None:
        for callback in list(self._subscribers.get(event, [])):
            callback(**payload)

    # convenience helpers -----------------------------------------------------
    def progress(self, current: int, total: int, label: str = "") -> None:
        self.emit(PROGRESS, current=current, total=total, label=label)

    def log(self, message: str, level: str = "info") -> None:
        getattr(logger, level, logger.info)(message)
        self.emit(LOG, level=level, message=message)

    def error(self, exception: BaseException, context: str = "") -> None:
        logger.error("%s: %s", context or "error", exception)
        self.emit(ERROR, exception=exception, context=context)
