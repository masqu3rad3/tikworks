"""Dependency ordering shared by the schema and regenerate code."""

from __future__ import annotations

from typing import Callable, Hashable, Iterable, Optional, TypeVar

Item = TypeVar("Item")


def dependency_order(
    items: Iterable[Item],
    dependencies: Callable[[Item], Iterable[Item]],
    identity: Callable[[Item], Hashable],
    *,
    cycle_error: Optional[Callable[[Item], str]] = None,
) -> list[Item]:
    """Return ``items`` with every item after its dependencies.

    The input order is kept wherever the dependencies allow it.

    Args:
        items: What to order.
        dependencies: The items that must come before a given one.
        identity: A hashable key per item (an instance id, say).
        cycle_error: Builds the ``ValueError`` message when a cycle is found.
            When ``None`` the cycle is broken silently: the item being
            revisited is left where it already is.
    """
    ordered: list[Item] = []
    visiting: set[Hashable] = set()
    done: set[Hashable] = set()

    def visit(item: Item) -> None:
        key = identity(item)
        if key in done:
            return
        if key in visiting:
            if cycle_error is None:
                return
            raise ValueError(cycle_error(item))
        visiting.add(key)
        for dependency in dependencies(item):
            visit(dependency)
        visiting.discard(key)
        done.add(key)
        ordered.append(item)

    for item in items:
        visit(item)
    return ordered
