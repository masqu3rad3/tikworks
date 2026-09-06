"""Explicit registry for preference pages.

Mirrors ``tik.trigger.core.registry``: pages opt in with ``@register_page``
rather than being discovered by scanning.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PAGES: dict[str, type] = {}


def register_page(cls: type) -> type:
    """Register a ``PrefPage`` subclass under its own ``name``.

    Raises:
        ValueError: If ``name`` is empty, or another class already claims it.
    """
    name = getattr(cls, "name", "")
    if not name:
        raise ValueError(f"{cls.__name__} must declare a non-empty 'name'.")
    existing = _PAGES.get(name)
    if existing is not None and existing is not cls:
        raise ValueError(f"A preferences page named '{name}' is already registered.")
    _PAGES[name] = cls
    logger.debug("Registered preferences page: %s", name)
    return cls


def pages() -> list[type]:
    """Every registered page, ordered by ``order`` then ``name``."""
    return sorted(_PAGES.values(), key=lambda page: (page.order, page.name))


def page(name: str) -> type:
    """The page class registered under ``name``.

    Raises:
        KeyError: If no page is registered under that name.
    """
    return _PAGES[name]


def clear_pages() -> None:
    """Empty the registry. For tests."""
    _PAGES.clear()
