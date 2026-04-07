"""Actions discovery and registry for tik.trigger.

This module implements corrected folder-based discovery for actions:
1. Scans only direct child directories of the actions folder
2. Each action folder must contain a .py file matching the folder name
3. Imports the action class and registers it via the @register_action decorator
4. Optionally loads ui_definition.json

Example folder structure:
    actions/
    ├── __init__.py
    ├── _base.py
    └── jointify/
        ├── jointify.py      # Must match folder name
        └── ui_definition.json  # (optional)
"""

from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path
from typing import Optional

from tik.trigger.core.action_core import ActionCore
from tik.trigger.core.registry import _ACTIONS_REGISTRY
from tik.trigger.core.schemas import ActionDefinition, UIDefinition
from tik.trigger.config.io import ConfigIO

logger = logging.getLogger(__name__)

# Cache for discovered action definitions
_ACTION_DEFINITIONS: dict[str, ActionDefinition] = {}
_LOADED_ACTION_FOLDERS: set[str] = set()


def _find_action_class(module) -> Optional[type[ActionCore]]:
    """Find the first ActionCore subclass in a module.

    Args:
        module: The module to search.

    Returns:
        The ActionCore subclass, or None if not found.
    """
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, ActionCore) and obj is not ActionCore:
            return obj
    return None


def _load_action_json(folder_path: Path, action_name: str) -> Optional[dict]:
    """Load ui_definition.json from action folder.

    Args:
        folder_path: Path to the action folder.
        action_name: Name of the action.

    Returns:
        The ui_definition dict, or None if file doesn't exist.
    """
    ui_def_path = folder_path / "ui_definition.json"
    if ui_def_path.exists():
        ui_definition = ConfigIO._load_json(ui_def_path)
        logger.debug("Loaded ui_definition for %s", action_name)
        return ui_definition
    return None


def _create_uid(key: str, data: dict) -> UIDefinition:
    """Create a UIDefinition from a ui_definition.json entry.

    Args:
        key: The settings key (from JSON dict key).
        data: The settings dict with display_name, type, value, etc.

    Returns:
        A UIDefinition instance.
    """
    return UIDefinition(
        key=key,
        display_name=data.get("display_name", key),
        setting_type=data.get("type", "string"),
        value=data.get("value"),
        items=data.get("items"),
        min_value=data.get("min_value"),
        max_value=data.get("max_value"),
    )


def _register_action_from_folder(action_dir: Path) -> bool:
    """Register an action from a folder.

    Args:
        action_dir: Path to the action folder.

    Returns:
        True if registration succeeded, False otherwise.
    """
    action_name = action_dir.name

    # Check if folder has matching .py file
    main_py = action_dir / f"{action_name}.py"
    if not main_py.exists():
        logger.warning(
            "Action folder '%s' does not contain '%s.py', skipping",
            action_name,
            action_name,
        )
        return False

    # Import the module
    try:
        module = importlib.import_module(f"tik.trigger.actions.{action_name}.{action_name}")
    except ImportError as e:
        logger.error("Failed to import action '%s': %s", action_name, e)
        return False

    # Find ActionCore subclass
    action_cls = _find_action_class(module)
    if action_cls is None:
        logger.warning(
            "No ActionCore subclass found in action '%s', skipping",
            action_name,
        )
        return False

    # Register in the global registry (if not already registered via decorator)
    if action_name not in _ACTIONS_REGISTRY:
        _ACTIONS_REGISTRY[action_name] = action_cls
        logger.debug("Auto-registered action: %s", action_name)

    # Load JSON definitions
    ui_def_json = _load_action_json(action_dir, action_name)

    # Store definition cache
    _ACTION_DEFINITIONS[action_name] = ActionDefinition(
        name=action_name,
        ui_definition=[_create_uid(k, v) for k, v in (ui_def_json or {}).items()],
    )
    _LOADED_ACTION_FOLDERS.add(action_name)

    return True


def discover_actions() -> list[str]:
    """Discover and register all actions in the actions folder.

    This scans only direct child directories (not nested folders) and
    registers any valid ActionCore subclasses found.

    Returns:
        List of registered action names.
    """
    actions_base = Path(__file__).parent
    excluded = {"_base", "_TEMPLATE", "__pycache__"}
    registered = []

    for action_dir in actions_base.iterdir():
        if not action_dir.is_dir():
            continue
        if action_dir.name in excluded:
            continue
        if action_dir.name.startswith("_"):
            continue

        if _register_action_from_folder(action_dir):
            registered.append(action_dir.name)

    logger.info("Discovered %d actions: %s", len(registered), registered)
    return registered


def get_action_definition(name: str) -> Optional[ActionDefinition]:
    """Get the definition for an action.

    Args:
        name: The action name.

    Returns:
        The ActionDefinition, or None if not found.
    """
    return _ACTION_DEFINITIONS.get(name)


def list_discovered_actions() -> list[str]:
    """Return list of all discovered action names.

    Returns:
        List of action names that have been discovered.
    """
    return list(_LOADED_ACTION_FOLDERS)


# Discover actions on module import
_discovered = discover_actions()

__all__ = [
    "discover_actions",
    "get_action_definition",
    "list_discovered_actions",
]
