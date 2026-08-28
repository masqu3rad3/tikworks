"""Explicit registry for modules and actions.

Classes opt in with ``@register_module("name")`` / ``@register_action("name")``.
The decorators also stamp ``module_type`` / ``action_type`` on the class so an
instance always knows its registered name.
"""

from __future__ import annotations

import logging
from typing import Callable, Type, TypeVar

from .exceptions import DuplicateRegistrationError, NotFoundError

logger = logging.getLogger(__name__)

T = TypeVar("T")

_MODULES: dict[str, type] = {}
_ACTIONS: dict[str, type] = {}


def register_module(name: str) -> Callable[[Type[T]], Type[T]]:
    """Register a ``Module`` subclass under ``name``."""

    def inner(cls: Type[T]) -> Type[T]:
        existing = _MODULES.get(name)
        if existing is not None and existing is not cls:
            raise DuplicateRegistrationError(name, kind="module")
        cls.module_type = name  # type: ignore[attr-defined]
        _MODULES[name] = cls
        logger.debug("Registered module: %s", name)
        return cls

    return inner


def register_action(name: str) -> Callable[[Type[T]], Type[T]]:
    """Register an ``Action`` subclass under ``name``."""

    def inner(cls: Type[T]) -> Type[T]:
        existing = _ACTIONS.get(name)
        if existing is not None and existing is not cls:
            raise DuplicateRegistrationError(name, kind="action")
        cls.action_type = name  # type: ignore[attr-defined]
        _ACTIONS[name] = cls
        logger.debug("Registered action: %s", name)
        return cls

    return inner


def get_module(name: str) -> type:
    """Return the module class registered as ``name``."""
    try:
        return _MODULES[name]
    except KeyError:
        raise NotFoundError(name, kind="module") from None


def get_action(name: str) -> type:
    """Return the action class registered as ``name``."""
    try:
        return _ACTIONS[name]
    except KeyError:
        raise NotFoundError(name, kind="action") from None


def list_modules() -> list[str]:
    """Return registered module names (sorted)."""
    return sorted(_MODULES)


def list_actions() -> list[str]:
    """Return registered action names (sorted)."""
    return sorted(_ACTIONS)


def iter_modules() -> list[type]:
    """Return registered module classes."""
    return [_MODULES[name] for name in list_modules()]


def iter_actions() -> list[type]:
    """Return registered action classes."""
    return [_ACTIONS[name] for name in list_actions()]


def is_module_registered(name: str) -> bool:
    return name in _MODULES


def is_action_registered(name: str) -> bool:
    return name in _ACTIONS


def unregister_module(name: str) -> None:
    """Remove a module registration (testing / hot reload)."""
    _MODULES.pop(name, None)


def unregister_action(name: str) -> None:
    """Remove an action registration (testing / hot reload)."""
    _ACTIONS.pop(name, None)


def clear_registries() -> None:
    """Drop every registration. Primarily for tests."""
    _MODULES.clear()
    _ACTIONS.clear()
