"""Registry system for actions and modules with explicit decorator-based registration.

This module provides the registry infrastructure for tik.trigger. Actions and modules
register themselves using the @register_action and @register_module decorators,
enabling explicit, discoverable plugin registration without circular imports.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Type, TypeVar

from .exceptions import DuplicateRegistrationError, NotFoundError

if TYPE_CHECKING:
    from .action_core import ActionCore
    from .module_core import ModuleCore

logger = logging.getLogger(__name__)

T = TypeVar("T")

_ACTIONS_REGISTRY: dict[str, Type[ActionCore]] = {}
_MODULES_REGISTRY: dict[str, Type[ModuleCore]] = {}


def register_action(name: str) -> Callable[[Type[T]], Type[T]]:
    """Decorator to register an action class.

    Args:
        name: Unique identifier for the action.

    Returns:
        A decorator function that registers the class.

    Raises:
        DuplicateRegistrationError: If an action with this name is already registered.

    Example:
        @register_action("jointify")
        class JointifyAction(ActionCore):
            pass
    """

    def inner(cls: Type[T]) -> Type[T]:
        if name in _ACTIONS_REGISTRY:
            raise DuplicateRegistrationError(name, kind="action")
        _ACTIONS_REGISTRY[name] = cls  # type: ignore[assignment]
        logger.debug("Registered action: %s", name)
        return cls

    return inner


def register_module(name: str) -> Callable[[Type[T]], Type[T]]:
    """Decorator to register a module class.

    Args:
        name: Unique identifier for the module.

    Returns:
        A decorator function that registers the class.

    Raises:
        DuplicateRegistrationError: If a module with this name is already registered.

    Example:
        @register_module("bipedArm")
        class BipedArmModule(ModuleCore):
            pass
    """

    def inner(cls: Type[T]) -> Type[T]:
        if name in _MODULES_REGISTRY:
            raise DuplicateRegistrationError(name, kind="module")
        _MODULES_REGISTRY[name] = cls  # type: ignore[assignment]
        logger.debug("Registered module: %s", name)
        return cls

    return inner


def get_action(name: str) -> Type[ActionCore]:
    """Retrieve a registered action class by name.

    Args:
        name: The action identifier.

    Returns:
        The registered action class.

    Raises:
        NotFoundError: If no action with this name is registered.
    """
    if name not in _ACTIONS_REGISTRY:
        raise NotFoundError(name, kind="action")
    return _ACTIONS_REGISTRY[name]


def get_module(name: str) -> Type[ModuleCore]:
    """Retrieve a registered module class by name.

    Args:
        name: The module identifier.

    Returns:
        The registered module class.

    Raises:
        NotFoundError: If no module with this name is registered.
    """
    if name not in _MODULES_REGISTRY:
        raise NotFoundError(name, kind="module")
    return _MODULES_REGISTRY[name]


def list_actions() -> list[str]:
    """Return a list of all registered action names."""
    return list(_ACTIONS_REGISTRY.keys())


def list_modules() -> list[str]:
    """Return a list of all registered module names."""
    return list(_MODULES_REGISTRY.keys())


def is_action_registered(name: str) -> bool:
    """Check if an action is registered.

    Args:
        name: The action identifier.

    Returns:
        True if the action is registered, False otherwise.
    """
    return name in _ACTIONS_REGISTRY


def is_module_registered(name: str) -> bool:
    """Check if a module is registered.

    Args:
        name: The module identifier.

    Returns:
        True if the module is registered, False otherwise.
    """
    return name in _MODULES_REGISTRY


def clear_registries() -> None:
    """Clear all registries. Primarily for testing purposes."""
    _ACTIONS_REGISTRY.clear()
    _MODULES_REGISTRY.clear()
    logger.debug("Registries cleared")
