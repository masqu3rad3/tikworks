"""Configuration system for tik.trigger.

This package provides the settings management system including:
- FACTORY_DEFAULTS: Immutable default values
- UserSettings: Per-user settings with file persistence
- ConfigIO: JSON file I/O operations
- trigger_settings: Singleton facade for application-wide settings
"""

from tik.trigger.config.defaults import FACTORY_DEFAULTS
from tik.trigger.config.io import ConfigIO, read_json, write_json
from tik.trigger.config.settings import UserSettings, trigger_settings

__all__ = [
    "FACTORY_DEFAULTS",
    "ConfigIO",
    "UserSettings",
    "trigger_settings",
    "read_json",
    "write_json",
]
