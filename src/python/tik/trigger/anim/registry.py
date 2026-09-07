"""Switch discovery: ``@register_switch``, mirroring the action registry."""

from __future__ import annotations

import logging
from typing import Callable

from tik.trigger.core.exceptions import DuplicateRegistrationError, NotFoundError

from .switch import Switch

logger = logging.getLogger(__name__)

_SWITCHES: dict[str, type[Switch]] = {}


def register_switch(name: str, icon: str = "") -> Callable[[type], type]:
    """Register a ``Switch`` subclass under ``name``.

    Args:
        name: Unique switch type name.
        icon: Icon name (defaults to ``name``).
    """

    def inner(cls: type) -> type:
        existing = _SWITCHES.get(name)
        if existing is not None and existing is not cls:
            raise DuplicateRegistrationError(name, kind="switch")
        cls.switch_type = name
        cls.icon = icon or name
        _SWITCHES[name] = cls
        logger.debug("Registered switch: %s", name)
        return cls

    return inner


def get_switch(name: str) -> type[Switch]:
    """The switch class registered under ``name``."""
    try:
        return _SWITCHES[name]
    except KeyError:
        raise NotFoundError(name, kind="switch") from None


def iter_switches() -> list[type[Switch]]:
    """Every registered switch, by ``order`` then label."""
    return sorted(_SWITCHES.values(), key=lambda cls: (cls.order, cls.display_label()))


def registered() -> dict[str, type[Switch]]:
    """A copy of the registry, for a test that needs to put it back."""
    return dict(_SWITCHES)


def restore(entries: dict) -> None:
    """Replace the registry wholesale (tests)."""
    _SWITCHES.clear()
    _SWITCHES.update(entries)


def unregister_switch(name: str) -> None:
    """Drop one registration (tests)."""
    _SWITCHES.pop(name, None)


def clear_switches() -> None:
    """Drop every registration (tests)."""
    _SWITCHES.clear()
