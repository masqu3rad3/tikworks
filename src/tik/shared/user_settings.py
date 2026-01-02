"""Generic class to store and retrieve user preferences.

This module provides the UserSettings class for managing user configuration
settings and a generic SettingsManager for handling application-specific defaults.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, MutableMapping, Optional, Union

from .io import IO

LOG = logging.getLogger(__name__)



class UserSettings:
    """Generic Settings class to hold, read, and compare dictionary data."""

    def __init__(self, file_name: Union[str, Path]) -> None:
        """Initialize the UserSettings instance.

        Args:
            file_name: Name of the file. Can have the .json extension or just
                the base name.
        """
        path = Path(file_name)
        if path.suffix == "":
            path = path.with_suffix(".json")

        home = Path.home()
        self._file_path: Path = home / "TikWorks" / path.name
        self._io: IO = IO(self._file_path)

        self._properties: List[str] = []
        self._original_value: Dict[str, Any] = {}
        self._current_value: Dict[str, Any] = {}
        self._time_stamp: Optional[float] = None
        self._fallback: Optional[Union[str, Path]] = None

        self.initialize(self._io.read())

    # ------------------------------------------------------------------ #
    # Simple dict-like views
    # ------------------------------------------------------------------ #

    @property
    def keys(self) -> List[str]:
        """Return all keys in the current data.

        Returns:
            list: List of all keys.
        """
        return list(self._current_value.keys())

    @property
    def values(self) -> List[Any]:
        """Return all values in the current data.

        Returns:
            list: List of all values.
        """
        return list(self._current_value.values())

    @property
    def properties(self) -> Dict[str, Any]:
        """Return the current dictionary data.

        Returns:
            dict: Dictionary of all properties.
        """
        return self._current_value

    # ------------------------------------------------------------------ #
    # Core data lifecycle
    # ------------------------------------------------------------------ #

    def initialize(self, data: Optional[MutableMapping[str, Any]]) -> None:
        """Initialize the settings data.

        Args:
            data: Dictionary data to feed into the class.
        """
        data = dict(data or {})
        self._original_value = {}
        self._current_value = {}
        self._current_value.update(data)
        self._original_value = deepcopy(self._current_value)

    def update(
        self,
        data: Union[MutableMapping[str, Any], "UserSettings"],
        add_missing_keys: bool = False,
    ) -> None:
        """Update the settings data.

        Args:
            data: Dictionary (or another UserSettings) to update the existing
                data.
            add_missing_keys: If True, all missing keys will be added.
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

    def is_settings_changed(self) -> bool:
        """Check if the settings changed since initialization.

        Returns:
            bool: True if settings have changed, False otherwise.
        """
        return self._current_value != self._original_value

    def apply_settings(self, force: bool = False) -> bool:
        """Apply the changed settings and write them to file.

        Args:
            force: If True, force writing even if settings did not change.

        Returns:
            True if the file has been written, False otherwise.
        """
        if not self.is_settings_changed() and not force:
            LOG.debug("No changes detected in settings. Skipping write.")
            return False
        self._original_value = deepcopy(self._current_value)
        self._io.write(self._original_value)
        LOG.debug("Settings written to file: %s", self._file_path)
        return True

    def reset_settings(self) -> None:
        """Revert unsaved changes to the original state."""
        self._current_value = deepcopy(self._original_value)

    # ------------------------------------------------------------------ #
    # Property manipulation helpers
    # ------------------------------------------------------------------ #

    def edit_property(self, key: str, val: Any) -> None:
        """Update the property key with given value.

        Args:
            key: Property name.
            val: New value for the property.
        """
        self._current_value.update({key: val})

    def edit_sub_property(self, sub_keys: Iterable[str], new_val: Any) -> None:
        """Edit nested properties.

        Args:
            sub_keys: Iterable of sub-keys. Each item must be the parent
                of the next item in the hierarchy.
            new_val: Value of the resolved key.
        """
        iterator = iter(sub_keys)
        val: Any = self._current_value
        path: List[str] = []

        try:
            key = next(iterator)
        except StopIteration:
            return

        for key in iterator:
            path.append(key)
            val = val[key]

        # Assign a new value to the final key
        val[key] = new_val

    def add_property(self, key: str, val: Any, force: bool = True) -> bool:
        """Create a property key with given value.

        Args:
            key: Name of the property.
            val: Value for the property. Must be JSON-serializable.
            force: If False, existing keys will not be overwritten.

        Returns:
            True if property was changed/created, False otherwise.
        """
        if key in self._current_value and not force:
            return False
        self._current_value.update({key: val})
        return True

    def delete_property(self, key: str) -> None:
        """Delete the given property key.

        Args:
            key: Name of the key to be deleted.
        """
        self._current_value.pop(key, None)

    # ------------------------------------------------------------------ #
    # Dict-like access helpers
    # ------------------------------------------------------------------ #

    def get_property(self, key: str, default: Any = None) -> Any:
        """Return the value of the property key.

        Args:
            key: Name of the property to query.
            default: Default value if key is missing.

        Returns:
            Dictionary value of the property.
        """
        return self._current_value.get(key, default)

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style alias for get_property."""
        return self._current_value.get(key, default)

    def get_sub_property(self, sub_keys: Iterable[str]) -> Any:
        """Return the value of a nested property.

        Args:
            sub_keys: Iterable of nested keys.

        Returns:
            Any: Dictionary value of the nested property.
        """
        val: Any = self._current_value
        for key in sub_keys:
            val = val[key]
        return val

    # ------------------------------------------------------------------ #
    # Raw data access
    # ------------------------------------------------------------------ #

    def set_data(self, data: Dict[str, Any]) -> None:
        """Feed the raw data directly.

        Args:
            data: Dictionary that will be fed into the class directly.
                Must have JSON-serializable values.
        """
        self._current_value = data

    def get_data(self) -> Dict[str, Any]:
        """Return the whole current data.

        Returns:
            dict: Complete current data dictionary.
        """
        return self._current_value

    # ------------------------------------------------------------------ #
    # Fallback handling
    # ------------------------------------------------------------------ #

    def set_fallback(self, file_path: Union[str, Path]) -> None:
        """Use this file in case the main file is not found.

        Args:
            file_path: Path to a json file location.
        """
        self._fallback = file_path
        if not self._io.file_exists(self._file_path):
            self.use_fallback()

    def use_fallback(self) -> None:
        """Use the fallback file."""
        if self._fallback:
            data = self._io.read(self._fallback)
            self.initialize(data)
            self.apply_settings(force=True)

    # ------------------------------------------------------------------ #
    # Representation
    # ------------------------------------------------------------------ #

    def __str__(self) -> str:
        """Return the type of the class and current data.

        Returns:
            str: String representation of the instance.
        """
        return f"{type(self).__name__}({self._current_value})"

    def __repr__(self) -> str:
        """Return the current data representation.

        Returns:
            str: Representation of current data.
        """
        return repr(self._current_value)


class SettingsManager:
    """Manager class for user-configured settings."""

    def __init__(self, settings_file_name: str, defaults: Dict[str, Any]) -> None:
        """Initialize the SettingsManager.

        Args:
            settings_file_name: Name of the application. Used for the settings filename.
            defaults: Dictionary of default settings.
        """
        LOG.debug("Initializing SettingsManager for %s...", settings_file_name)
        self._defaults = deepcopy(defaults)
        self._file_name = f"{settings_file_name}_settings.json"
        self._user_settings = UserSettings(self._file_name)
        self._ensure_defaults_applied()

    def _ensure_defaults_applied(self) -> None:
        """Ensure settings file has default values if new/empty."""
        current_data = self._user_settings.get_data()
        if not current_data:
            LOG.info(
                "Settings file '%s' is empty or new. Applying default settings.",
                self._file_name,
            )
            self._user_settings.set_data(deepcopy(self._defaults))
            self._user_settings.apply_settings(force=True)
        else:
            made_changes = False
            for key, default_value in self._defaults.items():
                if key not in current_data:
                    LOG.info(
                        "Adding missing default setting '%s': %s",
                        key,
                        default_value,
                    )
                    self._user_settings.edit_property(key, default_value)
                    made_changes = True
            if made_changes:
                self._user_settings.apply_settings(force=True)

    def get(self, key: str, default_override: Any = None) -> Any:
        """Get a setting value.

        Uses defaults as the ultimate fallback.

        Args:
            key: Setting key to retrieve.
            default_override: Override default value if provided.

        Returns:
            Any: The setting value.
        """
        if default_override is not None:
            return self._user_settings.get_property(key, default_override)
        return self._user_settings.get_property(key, self._defaults.get(key))

    def set(self, key: str, value: Any) -> None:
        """Edit a setting.

        Does not save immediately.

        Args:
            key: Setting key to set.
            value: New value for the setting.
        """
        self._user_settings.edit_property(key, value)

    def save(self) -> bool:
        """Save any pending changes to the settings file.

        Returns:
            bool: True if file was written, False otherwise.
        """
        return self._user_settings.apply_settings()

    def is_changed(self) -> bool:
        """Check if current settings differ from the last saved state.

        Returns:
            bool: True if settings have changed, False otherwise.
        """
        return self._user_settings.is_settings_changed()

    def reset(self) -> None:
        """Reset settings to their last saved state."""
        self._user_settings.reset_settings()

    def reset_to_factory_defaults(self) -> None:
        """Reset the values to the defaults."""
        self._user_settings.set_data(deepcopy(self._defaults))

    def get_all_settings(self) -> Dict[str, Any]:
        """Return all current setting data.

        Returns:
            dict: Dictionary of all settings.
        """
        return self._user_settings.get_data()

    def __getitem__(self, key: str) -> Any:
        """Dict-style access to settings."""
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Dict-style assignment to settings."""
        self.set(key, value)

    def __repr__(self) -> str:
        """Return the current settings representation."""
        return repr(self.get_all_settings())


