"""Modules discovery and registry for tik.trigger.

This module implements folder-based discovery for modules:
1. Scans only direct child directories of the modules folder
2. Each module folder must contain a .py file matching the folder name
3. Registers RigModule subclasses (unified guide + build class)

Example folder structure:
    modules/
    ├── __init__.py
    ├── _base.py
    └── bipedArm/
        ├── bipedArm.py      # Must match folder name
        ├── ui_definition.json  # (optional)
        └── data.json          # (optional) Module-specific data
"""

from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from tik.trigger.core.rig_module import RigModule
from tik.trigger.core.registry import _MODULES_REGISTRY
from tik.trigger.core.schemas import ModuleDefinition, UIDefinition
from tik.core.jsonio import load as _json_load

if TYPE_CHECKING:
    pass  # RigModule is imported at module level for subclasses

logger = logging.getLogger(__name__)

# Cache for discovered module definitions
_MODULE_DEFINITIONS: dict[str, ModuleDefinition] = {}
_LOADED_MODULE_FOLDERS: set[str] = set()


def _find_module_classes(module) -> Optional[type[RigModule]]:
    """Find RigModule subclass in a module.

    Args:
        module: The module to search.

    Returns:
        The RigModule subclass found, or None.
    """
    rig_module_cls = None

    for name, obj in inspect.getmembers(module, inspect.isclass):
        if obj is RigModule:
            continue
        if issubclass(obj, RigModule):
            rig_module_cls = obj
            break

    return rig_module_cls


def _load_module_json(folder_path: Path, module_name: str) -> tuple[Optional[dict], Optional[dict]]:
    """Load ui_definition.json and data.json from module folder.

    Args:
        folder_path: Path to the module folder.
        module_name: Name of the module.

    Returns:
        Tuple of (ui_definition dict, data dict) or (None, None) if files don't exist.
    """
    ui_definition = None
    data = None

    ui_def_path = folder_path / "ui_definition.json"
    if ui_def_path.exists():
        ui_definition = _json_load(ui_def_path)
        logger.debug("Loaded ui_definition for %s", module_name)

    data_path = folder_path / "data.json"
    if data_path.exists():
        data = _json_load(data_path)
        logger.debug("Loaded data for %s", module_name)

    return ui_definition, data


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


def _register_module_from_folder(module_dir: Path) -> bool:
    """Register a module from a folder.

    Args:
        module_dir: Path to the module folder.

    Returns:
        True if registration succeeded, False otherwise.
    """
    module_name = module_dir.name

    # Check if folder has matching .py file
    main_py = module_dir / f"{module_name}.py"
    if not main_py.exists():
        logger.warning(
            "Module folder '%s' does not contain '%s.py', skipping",
            module_name,
            module_name,
        )
        return False

    # Import the module
    try:
        module = importlib.import_module(f"tik.trigger.modules.{module_name}.{module_name}")
    except ImportError as e:
        logger.error("Failed to import module '%s': %s", module_name, e)
        return False

    # Find module class (unified RigModule)
    rig_module_cls = _find_module_classes(module)
    if rig_module_cls is None:
        logger.warning(
            "No RigModule subclass found in module '%s', skipping",
            module_name,
        )
        return False

    # Register in the global registry (if not already registered via decorator)
    if module_name not in _MODULES_REGISTRY:
        _MODULES_REGISTRY[module_name] = rig_module_cls
        logger.debug("Auto-registered module: %s", module_name)

    # Load JSON definitions
    ui_def_json, data_json = _load_module_json(module_dir, module_name)

    # Store definition cache
    _MODULE_DEFINITIONS[module_name] = ModuleDefinition(
        name=module_name,
        ui_definition=[_create_uid(k, v) for k, v in (ui_def_json or {}).items()],
        data=data_json or {},
    )
    _LOADED_MODULE_FOLDERS.add(module_name)

    return True


def discover_modules() -> list[str]:
    """Discover and register all modules in the modules folder.

    This scans only direct child directories (not nested folders) and
    registers any valid RigModule subclasses found.

    Returns:
        List of registered module names.
    """
    modules_base = Path(__file__).parent
    excluded = {"_base", "_TEMPLATE", "__pycache__"}
    registered = []

    for module_dir in modules_base.iterdir():
        if not module_dir.is_dir():
            continue
        if module_dir.name in excluded:
            continue
        if module_dir.name.startswith("_"):
            continue

        if _register_module_from_folder(module_dir):
            registered.append(module_dir.name)

    logger.info("Discovered %d modules: %s", len(registered), registered)
    return registered


def get_module_definition(name: str) -> Optional[ModuleDefinition]:
    """Get the definition for a module.

    Args:
        name: The module name.

    Returns:
        The ModuleDefinition, or None if not found.
    """
    return _MODULE_DEFINITIONS.get(name)


def get_module_class(name: str) -> Optional[type[RigModule]]:
    """Get the RigModule class for a module.

    Args:
        name: The module name.

    Returns:
        The RigModule subclass, or None if not found.
    """
    return _MODULES_REGISTRY.get(name)


def list_discovered_modules() -> list[str]:
    """Return list of all discovered module names.

    Returns:
        List of module names that have been discovered.
    """
    return list(_LOADED_MODULE_FOLDERS)


# Discover modules on module import
_discovered = discover_modules()

__all__ = [
    "discover_modules",
    "get_module_definition",
    "get_module_class",
    "list_discovered_modules",
]
