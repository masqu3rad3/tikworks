# src/python/tik/trigger/vcs/__init__.py
"""Version control for Trigger: the provider registry and the host.

A VCS integrates from outside the repository: it registers a
:class:`VersionControl` subclass with ``@register_provider`` from a plugin on
``TRIGGER_PLUGIN_PATH`` and drives Trigger through ``host``. Only the UI and
publish actions import this package; nothing on the build path does, and this
package never reads preferences (the window tells it which provider is
preferred through ``set_preferred``).
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from tik.trigger.core.exceptions import (
    DuplicateRegistrationError,
    NotFoundError,
    VersionControlError,
)

from . import kinds  # noqa: F401 - part of the public surface
from .host import Host
from .provider import Context, VersionControl

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, type] = {}
_INSTANCES: dict[str, VersionControl] = {}
_preferred: Optional[str] = None
_last_pick: Optional[str] = None

#: The one host. The window attaches itself; scripts attach a Session.
host = Host()


def register_provider(name: str) -> Callable[[type], type]:
    """Register a ``VersionControl`` subclass under ``name``."""

    def inner(cls: type) -> type:
        existing = _PROVIDERS.get(name)
        if existing is not None and existing is not cls:
            raise DuplicateRegistrationError(name, kind="provider")
        cls.name = name
        _PROVIDERS[name] = cls
        _INSTANCES.pop(name, None)
        logger.debug("Registered version control provider: %s", name)
        return cls

    return inner


def providers() -> list[type]:
    """Registered provider classes, by name."""
    return [_PROVIDERS[name] for name in provider_names()]


def provider_names() -> list[str]:
    return sorted(_PROVIDERS)


def get_provider(name: str) -> type:
    try:
        return _PROVIDERS[name]
    except KeyError:
        raise NotFoundError(name, kind="provider") from None


def clear_providers() -> None:
    """Drop every registration (tests)."""
    _PROVIDERS.clear()
    _INSTANCES.clear()


def set_preferred(name: Optional[str]) -> None:
    """Name the provider to use when several are available (the window sets it)."""
    global _preferred
    _preferred = name or None


def preferred() -> Optional[str]:
    return _preferred


def _instance(name: str) -> VersionControl:
    if name not in _INSTANCES:
        _INSTANCES[name] = _PROVIDERS[name]()
    return _INSTANCES[name]


def active() -> Optional[VersionControl]:
    """The provider in use, or ``None`` when no available provider exists."""
    global _last_pick
    candidates = []
    for name in provider_names():
        try:
            if _instance(name).available():
                candidates.append(name)
        except Exception as error:  # noqa: BLE001 - a broken provider is unavailable
            logger.error("vcs: provider %s failed availability check: %s", name, error)
    if not candidates:
        return None
    if len(candidates) == 1:
        pick = candidates[0]
    elif _preferred in candidates:
        pick = _preferred
    else:
        pick = candidates[0]
        if _last_pick != pick:
            logger.info(
                "vcs: several providers available (%s); using %s",
                ", ".join(candidates),
                pick,
            )
    _last_pick = pick
    return _instance(pick)


def require() -> VersionControl:
    """``active()`` or a ``VersionControlError``."""
    provider = active()
    if provider is None:
        raise VersionControlError("No version control provider is active.")
    return provider


# ------------------------------------------------------------ headless verbs
def open() -> str:  # noqa: A001 - the verb is the name
    """Pick and open a session through the active provider; the path or ``""``."""
    return require().open(host)


def new_version() -> str:
    """Save the active session as its next version in the VCS."""
    return require().new_version(host)


def publish_file(kind: str, path) -> None:
    """Hand one file to the VCS's own dialog."""
    require().publish_file(kind, path, host)


def launch() -> None:
    """Open the VCS's main window."""
    require().launch(host)


__all__ = [
    "Context",
    "Host",
    "VersionControl",
    "VersionControlError",
    "active",
    "clear_providers",
    "get_provider",
    "host",
    "kinds",
    "launch",
    "new_version",
    "open",
    "preferred",
    "provider_names",
    "providers",
    "publish_file",
    "register_provider",
    "require",
    "set_preferred",
]
