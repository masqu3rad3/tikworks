"""Explicit registry for modules and actions.

Classes opt in with ``@register_module("name")`` / ``@register_action("name")``.
The decorators also stamp ``module_type`` / ``action_type`` on the class so an
instance always knows its registered name.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, Type, TypeVar

from .document import BUILD, PUBLISH
from .exceptions import DuplicateRegistrationError, NotFoundError, RegistryError

logger = logging.getLogger(__name__)

T = TypeVar("T")

_MODULES: dict[str, type] = {}
_ACTIONS: dict[str, type] = {}

#: An action's scope says which list it may be placed in. This is a *placement*
#: rule for the UI and ``Session.add``; the runner never checks it.
BOTH = "both"
SCOPES = (BUILD, PUBLISH, BOTH)


def register_module(
    name: str, category: str = "generic", icon: str = ""
) -> Callable[[Type[T]], Type[T]]:
    """Register a ``Module`` subclass under ``name``.

    Args:
        name: Unique module type name.
        category: Shelf/palette group (``body``, ``limbs``, ``generic``,
            ``face``). Drives the tile colour and the icon tint.
        icon: Icon file name beside the module's ``.py`` (defaults to ``name``).
    """

    def inner(cls: Type[T]) -> Type[T]:
        existing = _MODULES.get(name)
        if existing is not None and existing is not cls:
            raise DuplicateRegistrationError(name, kind="module")
        cls.module_type = name  # type: ignore[attr-defined]
        cls.category = category  # type: ignore[attr-defined]
        cls.icon = icon or name  # type: ignore[attr-defined]
        _MODULES[name] = cls
        logger.debug("Registered module: %s", name)
        return cls

    return inner


def register_action(
    name: str, category: str = "utility", icon: str = "", scope: str = BUILD
) -> Callable[[Type[T]], Type[T]]:
    """Register an ``Action`` subclass under ``name``.

    Args:
        name: Unique action type name.
        category: Shelf/palette group (``structure``, ``build``, ``deform``,
            ``finish``, ``utility``).
        icon: Icon name (defaults to ``name``).
        scope: Which action list this may live in -- ``build`` (the default),
            ``publish`` or ``both``.
    """

    if scope not in SCOPES:
        raise RegistryError(f"Unknown action scope '{scope}'; expected one of {SCOPES}.")

    def inner(cls: Type[T]) -> Type[T]:
        existing = _ACTIONS.get(name)
        if existing is not None and existing is not cls:
            raise DuplicateRegistrationError(name, kind="action")
        cls.action_type = name  # type: ignore[attr-defined]
        cls.category = category  # type: ignore[attr-defined]
        cls.icon = icon or name  # type: ignore[attr-defined]
        cls.scope = scope  # type: ignore[attr-defined]
        _ACTIONS[name] = cls
        logger.debug("Registered action: %s", name)
        return cls

    return inner


def ensure_registered(cls: type) -> None:
    """Re-register a class that carries ``module_type``/``action_type``.

    Needed after ``clear_registries()`` when the defining module is already
    imported (decorators do not run again on re-import).
    """
    module_type = getattr(cls, "module_type", "")
    action_type = getattr(cls, "action_type", "")
    if module_type and module_type not in _MODULES and _is_module(cls):
        _MODULES[module_type] = cls
    if action_type and action_type not in _ACTIONS and _is_action(cls):
        _ACTIONS[action_type] = cls


def _is_module(cls: type) -> bool:
    return any(base.__name__ == "Module" for base in cls.__mro__[1:])


def _is_action(cls: type) -> bool:
    return any(base.__name__ == "Action" for base in cls.__mro__[1:])


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


def iter_actions(scope: Optional[str] = None) -> list[type]:
    """Return registered action classes, optionally only those fitting ``scope``."""
    classes = [_ACTIONS[name] for name in list_actions()]
    if scope is None:
        return classes
    return [cls for cls in classes if _scope_allows(getattr(cls, "scope", BUILD), scope)]


def _scope_allows(scope: str, phase: str) -> bool:
    return scope == BOTH or scope == phase


def allows(action_type: str, phase: str) -> bool:
    """Whether ``action_type`` may be placed in the ``phase`` list.

    ``False`` for an unregistered type, so callers can use this as a plain
    guard without catching :class:`NotFoundError`.
    """
    try:
        cls = get_action(action_type)
    except NotFoundError:
        return False
    return _scope_allows(getattr(cls, "scope", BUILD), phase)


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
