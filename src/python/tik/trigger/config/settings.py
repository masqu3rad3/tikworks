"""User settings management for tik.trigger.

This module provides the UserSettings class for managing user configuration
settings, and the trigger_settings singleton facade for application-wide access.

The settings system follows the labelmatic pattern:
- FACTORY_DEFAULTS provides immutable default values
- UserSettings manages a per-user JSON settings file
- The facade ensures defaults are applied on first run
"""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional, Union

from .defaults import FACTORY_DEFAULTS
from .io import ConfigIO

logger = logging.getLogger(__name__)

SETTINGS_FILE_NAME = "tik_trigger_settings.json"


class UserSettings:
    """Dict-like settings with file persistence.

    This class manages user settings that are persisted to a JSON file.
    It supports default values, change tracking, and file I/O.

    Attributes:
        file_path: Path to the settings file.
    """

    def __init__(self, file_path: Union[str, Path]) -> None:
        """Initialize UserSettings with a file path.

        Args:
            file_path: Path to the settings file. Can be absolute or relative.
                If no suffix is provided, .json will be added.
        """
        path = Path(file_path)
        if path.suffix == "":
            path = path.with_suffix(".json")

        self._file_path: Path = path
        self._io: ConfigIO = ConfigIO(self._file_path)
        self._original_value: dict = {}
        self._current_value: dict = {}
        self._fallback: Optional[Path] = None

        self._load()

    @property
    def file_path(self) -> Path:
        """Return the settings file path."""
        return self._file_path

    @property
    def keys(self) -> list[str]:
        """Return all keys in the current data."""
        return list(self._current_value.keys())

    @property
    def values(self) -> list[Any]:
        """Return all values in the current data."""
        return list(self._current_value.values())

    @property
    def properties(self) -> dict[str, Any]:
        """Return the current dictionary data."""
        return self._current_value

    def _load(self) -> None:
        """Load settings from file or use empty dict if file doesn't exist."""
        data = self._io.read()
        if data is not None:
            self._original_value = dict(data)
            self._current_value = dict(data)
        else:
            self._original_value = {}
            self._current_value = {}

    def update(
        self,
        data: Union[dict, "UserSettings"],
        add_missing_keys: bool = False,
    ) -> None:
        """Update the settings data.

        Args:
            data: Dictionary or UserSettings to update with.
            add_missing_keys: If True, missing keys will be added.
                Otherwise only existing keys will be updated.
        """
        if isinstance(data, UserSettings):
            data = data.get_data()

        if not add_missing_keys:
            self._current_value.update(
                (k, data[k]) for k in self._current_value.keys() & data.keys()
            )
        else:
            self._current_value.update(data)

    def is_changed(self) -> bool:
        """Check if settings have changed since last save.

        Returns:
            True if settings have changed, False otherwise.
        """
        return self._current_value != self._original_value

    def save(self, force: bool = False) -> bool:
        """Save the current settings to file.

        Args:
            force: If True, save even if settings haven't changed.

        Returns:
            True if file was written, False otherwise.
        """
        if not self.is_changed() and not force:
            logger.debug("No changes detected, skipping write.")
            return False

        self._original_value = deepcopy(self._current_value)
        self._io.write(self._current_value)
        logger.debug("Settings written to: %s", self._file_path)
        return True

    def reset(self) -> None:
        """Revert unsaved changes to the last saved state."""
        self._current_value = deepcopy(self._original_value)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value.

        Args:
            key: Setting key to retrieve.
            default: Default value if key is missing.

        Returns:
            The setting value or default.
        """
        return self._current_value.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a setting value.

        Does not save immediately.

        Args:
            key: Setting key to set.
            value: New value for the setting.
        """
        self._current_value[key] = value

    def get_data(self) -> dict:
        """Return the complete current data.

        Returns:
            Dictionary of all current settings.
        """
        return self._current_value.copy()

    def set_data(self, data: dict) -> None:
        """Set the raw data directly.

        Args:
            data: Dictionary to set as current data.
        """
        self._current_value = dict(data)

    def set_fallback(self, fallback_path: Union[str, Path]) -> None:
        """Set a fallback file to use if main file is not found.

        Args:
            fallback_path: Path to fallback JSON file.
        """
        self._fallback = Path(fallback_path)
        if not self._io.file_exists(self._file_path) and self._fallback.exists():
            self._use_fallback()

    def _use_fallback(self) -> None:
        """Use the fallback file to initialize settings."""
        if self._fallback and self._fallback.exists():
            data = self._io.read(self._fallback)
            if data is not None:
                self._original_value = dict(data)
                self._current_value = dict(data)
                self.save(force=True)
                logger.info("Initialized settings from fallback: %s", self._fallback)

    def __repr__(self) -> str:
        return f"UserSettings({self._file_path.name})"


class _TriggerSettingsFacade:
    """Facade for trigger settings with automatic default application.

    This class provides a singleton interface to trigger settings,
    ensuring FACTORY_DEFAULTS are applied on first run and missing
    keys are merged properly.
    """

    def __init__(self) -> None:
        logger.debug("Initializing TriggerSettingsFacade...")
        self._user_settings = UserSettings(SETTINGS_FILE_NAME)
        self._ensure_defaults_applied()

    def _ensure_defaults_applied(self) -> None:
        """Ensure settings file has default values if new/empty."""
        current_data = self._user_settings.get_data()

        if not current_data:
            logger.info(
                "Settings file '%s' is empty or new. Applying defaults.",
                SETTINGS_FILE_NAME,
            )
            self._user_settings.set_data(deepcopy(FACTORY_DEFAULTS))
            self._user_settings.save(force=True)
        else:
            made_changes = False
            for key, default_value in FACTORY_DEFAULTS.items():
                if key not in current_data:
                    logger.info(
                        "Adding missing default setting '%s': %s",
                        key,
                        default_value,
                    )
                    self._user_settings.set(key, default_value)
                    made_changes = True
            if made_changes:
                self._user_settings.save(force=True)

    def get(self, key: str, default_override: Any = None) -> Any:
        """Get a setting value.

        Uses FACTORY_DEFAULTS as ultimate fallback.

        Args:
            key: Setting key to retrieve.
            default_override: Override default value if provided.

        Returns:
            The setting value.
        """
        if default_override is not None:
            return self._user_settings.get(key, default_override)
        return self._user_settings.get(key, FACTORY_DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        """Set a setting value.

        Does not save immediately.

        Args:
            key: Setting key to set.
            value: New value for the setting.
        """
        self._user_settings.set(key, value)

    def save(self) -> bool:
        """Save any pending changes to the settings file.

        Returns:
            True if file was written, False otherwise.
        """
        return self._user_settings.save()

    def is_changed(self) -> bool:
        """Check if current settings differ from last saved state.

        Returns:
            True if settings have changed, False otherwise.
        """
        return self._user_settings.is_changed()

    def reset(self) -> None:
        """Reset settings to their last saved state."""
        self._user_settings.reset()

    def reset_to_factory_defaults(self) -> None:
        """Reset the values to factory defaults.

        Preserves recent_sessions since those shouldn't be wiped.
        """
        vanilla_settings = deepcopy(FACTORY_DEFAULTS)
        recent = self.get("recent_sessions", [])
        vanilla_settings["recent_sessions"] = recent
        self._user_settings.set_data(vanilla_settings)

    def get_all_settings(self) -> dict:
        """Return all current setting data.

        Returns:
            Dictionary of all settings.
        """
        return self._user_settings.get_data()

    def add_recent_session(self, file_path: Union[str, Path]) -> None:
        """Add a file path to recent sessions.

        Args:
            file_path: File path to add.
        """
        recent_sessions = self.get("recent_sessions", [])
        file_str = str(file_path)
        if file_str in recent_sessions:
            recent_sessions.remove(file_str)
        recent_sessions.append(file_str)
        max_recent = self.get("max_number_of_recent_sessions", 10)
        if len(recent_sessions) > max_recent:
            recent_sessions.pop(0)
        self.set("recent_sessions", recent_sessions)
        self.save()

    def __getitem__(self, key: str) -> Any:
        """Dict-style access to settings.

        Args:
            key: Setting key to retrieve.

        Returns:
            The setting value.
        """
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Dict-style assignment to settings.

        Does not persist to disk.

        Args:
            key: Setting key to set.
            value: New value for the setting.
        """
        self.set(key, value)

    def __repr__(self) -> str:
        return repr(self.get_all_settings())


# Singleton instance
trigger_settings = _TriggerSettingsFacade()
