"""Registry for Maya node wrappers."""

from typing import Any, Callable, Dict, Optional, Type, TypeVar

import maya.cmds as cmds

T = TypeVar("T")

_NODE_TYPES: Dict[str, Type[Any]] = {}
_DEFAULT_FACTORY: Optional[Type[Any]] = None  # set by set_default_factory(Node)


def register(node_type: str) -> Callable[[Type[T]], Type[T]]:
    """Register a Maya node wrapper class for a given node type.

    Args:
        node_type (str): Maya node type string to register the wrapper for.

    Returns:
        Callable[[Type[T]], Type[T]]: Decorator that registers the class.
    """

    def inner(cls: Type[T]) -> Type[T]:
        """Store the class in the registry keyed by node type.

        Args:
            cls (Type[T]): Class to register for the node type.

        Returns:
            Type[T]: The registered class.
        """
        _NODE_TYPES[node_type] = cls
        return cls

    return inner


def set_default_factory(factory: Type[T]) -> None:
    """Set the fallback factory (e.g., Node) without importing it here.

    Args:
        factory (Type[T]): Default factory class to instantiate when no match is found.

    Returns:
        None
    """
    global _DEFAULT_FACTORY
    _DEFAULT_FACTORY = factory  # type: ignore[assignment]


def resolve_node_class(name: str):
    """Resolve the most specific registered class for a given Maya node.

    Args:
        name (str): Maya node name to resolve.

    Raises:
        ValueError: If the node does not exist.
        LookupError: If no wrapper or default factory is registered.

    Returns:
        Type[Any]: Registered wrapper class for the node.
    """
    if not cmds.objExists(name):
        raise ValueError(f"Node '{name}' does not exist.")

    node_type = cmds.nodeType(name)
    cls = _NODE_TYPES.get(node_type)
    if cls:
        return cls

    # Inheritance fallback. Reverse the order to get most specific first.
    for inherited_type in reversed(cmds.nodeType(name, inherited=True) or []):
        # for inherited_type in (cmds.nodeType(name, inherited=True) or []):
        cls = _NODE_TYPES.get(inherited_type)
        if cls:
            return cls

    if _DEFAULT_FACTORY:
        return _DEFAULT_FACTORY

    raise LookupError(
        f"No wrapper registered for '{node_type}' and no default factory set."
    )


def resolve(name: str) -> Any:
    """Instantiate the correct Node subclass based on Maya node type.

    Args:
        name (str): Maya node name to wrap.

    Raises:
        ValueError: If the node does not exist.
        LookupError: If no wrapper or default factory is registered.

    Returns:
        Any: Instance of the resolved Node subclass.
    """
    cls = resolve_node_class(name)
    return cls(name)

# def resolve(name: str) -> Any:
#     """Return an instance of the correct Node subclass based on Maya node type."""
#     if not cmds.objExists(name):
#         raise ValueError(f"Node '{name}' does not exist.")
#
#     node_type = cmds.nodeType(name)
#     cls = _NODE_TYPES.get(node_type)
#     if cls is not None:
#         return cls(name)
#
#     # Try inherited types (e.g., 'dagNode', 'dependNode', etc.)
#     for n_t in (cmds.nodeType(name, inherited=True) or []):
#         cls = _NODE_TYPES.get(n_t)
#         if cls is not None:
#             return cls(name)
#
#     if _DEFAULT_FACTORY is not None:
#         return _DEFAULT_FACTORY(name)
#
#     raise LookupError(f"No wrapper registered for '{node_type}' and no default factory set.")
