"""Registry for Maya node wrappers."""
from typing import Any, Callable, Dict, Iterable, Type, TypeVar, Optional

import maya.cmds as cmds

T = TypeVar("T")

_NODE_TYPES: Dict[str, Type[Any]] = {}
_DEFAULT_FACTORY: Optional[Type[Any]] = None  # set by set_default_factory(Node)

def register(node_type: str) -> Callable[[Type[T]], Type[T]]:
    """Decorator for registering Maya node wrappers."""
    def inner(cls: Type[T]) -> Type[T]:
        _NODE_TYPES[node_type] = cls
        return cls
    return inner

def set_default_factory(factory: Type[T]) -> None:
    """Set the fallback factory (e.g., Node) without importing it here."""
    global _DEFAULT_FACTORY
    _DEFAULT_FACTORY = factory  # type: ignore[assignment]

def get_node(name: str) -> Any:
    """Return an instance of the correct Node subclass based on Maya node type."""
    if not cmds.objExists(name):
        raise ValueError(f"Node '{name}' does not exist.")

    node_type = cmds.nodeType(name)
    cls = _NODE_TYPES.get(node_type)
    if cls is not None:
        return cls(name)

    # Try inherited types (e.g., 'dagNode', 'dependNode', etc.)
    for n_t in (cmds.nodeType(name, inherited=True) or []):
        cls = _NODE_TYPES.get(n_t)
        if cls is not None:
            return cls(name)

    if _DEFAULT_FACTORY is not None:
        return _DEFAULT_FACTORY(name)

    raise LookupError(f"No wrapper registered for '{node_type}' and no default factory set.")
