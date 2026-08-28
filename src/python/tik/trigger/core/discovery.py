"""Folder based discovery for modules and actions.

Each plugin is a folder ``<package>/<name>/<name>.py`` whose classes register
themselves with ``@register_module`` / ``@register_action``. An optional
``defaults.json`` beside it overrides field defaults (values only).
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


def discover(package_name: str, package_path: Iterable[str]) -> list[str]:
    """Import every ``<folder>/<folder>.py`` under ``package_path``.

    Returns the imported module names. Folders starting with ``_`` are skipped.
    """
    imported: list[str] = []
    for root in package_path:
        for folder in sorted(Path(root).iterdir()):
            if not folder.is_dir() or folder.name.startswith("_"):
                continue
            main_file = folder / f"{folder.name}.py"
            if not main_file.exists():
                continue
            module_name = f"{package_name}.{folder.name}.{folder.name}"
            try:
                module = importlib.import_module(module_name)
            except Exception as error:  # noqa: BLE001 - keep discovering others
                logger.error("Failed to import %s: %s", module_name, error)
                continue
            imported.append(module_name)
            _ensure_registered(module)
            _apply_defaults(module, folder / "defaults.json")
    return imported


def _ensure_registered(module) -> None:
    """Re-register plugin classes if the registries were cleared."""
    from . import registry

    for attr in vars(module).values():
        if isinstance(attr, type) and getattr(attr, "__module__", "") == module.__name__:
            registry.ensure_registered(attr)


def _apply_defaults(module, defaults_file: Path) -> None:
    if not defaults_file.exists():
        return
    try:
        defaults = json.loads(defaults_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        logger.error("Invalid defaults.json at %s: %s", defaults_file, error)
        return
    for attr in vars(module).values():
        if not isinstance(attr, type) or not hasattr(attr, "fields"):
            continue
        if getattr(attr, "__module__", "") != module.__name__:
            continue
        fields = attr.fields()
        for key, value in defaults.items():
            if key in fields:
                fields[key].default = fields[key].validate(value)
            else:
                logger.warning("%s: unknown default '%s'", defaults_file, key)
