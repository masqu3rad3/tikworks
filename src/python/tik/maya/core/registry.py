"""Registry for Maya node wrappers."""

from typing import Any, Callable, Dict, Optional, Type, TypeVar

import maya.cmds as cmds

from . import apicommon as api

T = TypeVar("T")

_NODE_TYPES: Dict[str, Type[Any]] = {}
_DEFAULT_FACTORY: Optional[Type[Any]] = None  # set by set_default_factory(Node)

def register(node_type: str) -> Callable[[Type[T]], Type[T]]:
    """Decorator for registering Maya node wrappers.

    Args:
        node_type: The Maya node type to register (e.g., 'transform', 'joint').

    Returns:
        A decorator function that registers the class.

    Example::

        @register("transform")
        class Transform(DagNode):
            pass
    """

    def inner(cls: Type[T]) -> Type[T]:
        """Register the class for the given node type."""
        _NODE_TYPES[node_type] = cls
        return cls

    return inner


def set_default_factory(factory: Type[T]) -> None:
    """Set the fallback factory for unregistered node types.

    Args:
        factory: The default wrapper class (typically Node) to use when no
            specific wrapper is registered for a node type.
    """
    global _DEFAULT_FACTORY
    _DEFAULT_FACTORY = factory  # type: ignore[assignment]


def resolve_node_class(name: str):
    """Return the most specific registered class for a given Maya node.

    Args:
        name: Name of the Maya node.

    Returns:
        Type: The registered wrapper class for the node.

    Raises:
        ValueError: If the node doesn't exist.
        LookupError: If no wrapper is registered and no default factory is set.
    """
    if not api.obj_exists(name):
        raise ValueError(f"Node '{name}' does not exist.")

    node_type = api.node_type(name)
    cls = _NODE_TYPES.get(node_type)
    if cls:
        return cls

    # Inheritance fallback. Reverse the order to get most specific first.
    for inherited_type in reversed(cmds.nodeType(name, inherited=True) or []):
        cls = _NODE_TYPES.get(inherited_type)
        if cls:
            return cls

    if _DEFAULT_FACTORY:
        return _DEFAULT_FACTORY

    raise LookupError(
        f"No wrapper registered for '{node_type}' and no default factory set."
    )


def resolve(name: str, class_name=None) -> Any:
    """Return an instance of the correct Node subclass based on Maya node type.

    Args:
        name: Name of the Maya node, or an existing wrapper instance.
        class_name: Optional specific class name to use from registry.

    Returns:
        A wrapper instance for the node.

    Raises:
        LookupError: If class_name is specified but not registered.
    """
    if class_name:
        cls = _NODE_TYPES.get(class_name)
        if not cls:
            raise LookupError(f"No wrapper registered for class name '{class_name}'.")
        return cls(name)
    if isinstance(name, tuple(_NODE_TYPES.values())):
        return name
    cls = resolve_node_class(name)
    return cls(name)


def is_registered(node_type: str) -> bool:
    """Check if a node type is registered in the registry.

    Args:
        node_type: The Maya node type to check.

    Returns:
        bool: True if the node type has a registered wrapper, False otherwise.
    """
    return node_type in _NODE_TYPES
