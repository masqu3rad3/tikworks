"""ActionCore base class for tik.trigger actions.

All action classes must inherit from ActionCore. Actions are data-driven
operations that operate on selected nodes or guides. The ActionCore provides
the standard interface: feed(), action(), and save_action().

Example:
    @register_action("jointify")
    class JointifyAction(ActionCore):
        def feed(self, selection: list) -> dict:
            # Validate and extract data from selection
            return {"joints": joints}

        def action(self, feed_data: dict) -> None:
            # Perform the actual Maya operation
            pass
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from .schemas import ActionDefinition

logger = logging.getLogger(__name__)


class ActionCore(ABC):
    """Base class for all trigger actions.

    Actions are operations that can be applied to selected nodes or guides.
    They follow a feed -> action -> save pattern where:
    - feed(): Validates selection and extracts necessary data
    - action(): Performs the actual Maya operation
    - save_action(): Persists action configuration to session

    Subclasses must implement feed() and action().
    """

    _action_name: str = ""
    _defaults: dict = {}

    def __init__(self, name: Optional[str] = None) -> None:
        """Initialize the action.

        Args:
            name: Optional custom name for this action instance.
        """
        self._name = name or self.__class__.__name__
        self._settings: dict = {}
        self._feed_cache: Optional[dict] = None
        logger.debug("Initialized action: %s", self._name)

    @property
    def name(self) -> str:
        """Return the action instance name."""
        return self._name

    @property
    def action_type(self) -> str:
        """Return the action type name used in registration."""
        return self._action_name or self.__class__.__name__

    @property
    def defaults(self) -> dict:
        """Return the default settings for this action."""
        return self._defaults.copy()

    @property
    def settings(self) -> dict:
        """Return the current settings for this action instance."""
        return self._settings.copy()

    def set_settings(self, settings: dict) -> None:
        """Update the action settings.

        Args:
            settings: Dictionary of settings to apply.
        """
        self._settings = settings.copy()
        self._feed_cache = None  # Invalidate feed cache when settings change

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a specific setting value.

        Args:
            key: The setting key.
            default: Default value if key is not found.
        """
        return self._settings.get(key, default)

    def reset_settings(self) -> None:
        """Reset settings to default values."""
        self._settings = self.defaults
        self._feed_cache = None

    @abstractmethod
    def feed(self, selection: list) -> dict:
        """Validate selection and extract data for the action.

        This method is called before action() to validate the user's selection
        and extract any necessary data needed for execution.

        Args:
            selection: List of currently selected Maya node names.

        Returns:
            A dictionary of extracted feed data for use in action().

        Raises:
            ActionFeedError: If the selection is invalid for this action.
        """
        raise NotImplementedError

    @abstractmethod
    def action(self, feed_data: dict) -> None:
        """Execute the action using the provided feed data.

        This is the main execution method. It should only be called after
        a successful feed() call.

        Args:
            feed_data: Data extracted and returned by feed().

        Raises:
            ActionExecutionError: If the action fails during execution.
        """
        raise NotImplementedError

    def save_action(self, feed_data: dict) -> dict:
        """Save the action configuration to session data.

        Override this method if the action needs to persist additional
        data beyond the standard feed_data.

        Args:
            feed_data: The feed data dictionary.

        Returns:
            A dictionary suitable for serialization to session file.
        """
        return {
            "action_type": self.action_type,
            "settings": self._settings.copy(),
            "feed_data": feed_data.copy(),
        }

    def load_action(self, data: dict) -> None:
        """Load action configuration from session data.

        Args:
            data: The saved action data dictionary.
        """
        self._settings = data.get("settings", {})

    def validate(self) -> bool:
        """Validate that the action is properly configured.

        Override this method to add custom validation logic for
        settings or other state.

        Returns:
            True if the action is valid, False otherwise.
        """
        return True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self._name}')"
