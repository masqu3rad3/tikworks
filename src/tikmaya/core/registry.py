"""Registry for Maya node wrappers."""
from typing import Any, Callable, Dict, Optional, Type, TypeVar

import maya.cmds as cmds

T = TypeVar("T")

_NODE_TYPES: Dict[str, Type[Any]] = {}
_DEFAULT_FACTORY: Optional[Type[Any]] = None  # set by set_default_factory(Node)


def register(node_type: str) -> Callable[[Type[T]], Type[T]]:
    """Decorator for registering Maya node wrappers."""

    def inner(cls: Type[T]) -> Type[T]:
        """Register the class for the given node type."""
        _NODE_TYPES[node_type] = cls
        return cls

    return inner


def set_default_factory(factory: Type[T]) -> None:
    """Set the fallback factory (e.g., Node) without importing it here."""
    global _DEFAULT_FACTORY
    _DEFAULT_FACTORY = factory  # type: ignore[assignment]


def resolve_node_class(name: str):
    """Return the most specific registered class for a given Maya node."""
    # if the name is already a class, defined in _NODE_TYPES, return it directly
    if not cmds.objExists(name):
        raise ValueError(f"Node '{name}' does not exist.")

    node_type = cmds.nodeType(name)
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


def resolve(name: str) -> Any:
    """Return an instance of the correct Node subclass based on Maya node type."""
    if isinstance(name, tuple(_NODE_TYPES.values())):
        return name
    cls = resolve_node_class(name)
    return cls(name)

def is_registered(node_type: str) -> bool:
    """Check if a node type is registered in the registry."""
    return node_type in _NODE_TYPES