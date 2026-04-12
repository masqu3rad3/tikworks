"""Action session management for tik.trigger.

Manages the action pipeline including:
- Adding/removing actions from the build pipeline
- Configuring action settings
- Running actions in sequence
- Saving/loading action sessions
"""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from ..core.schemas import ActionInstanceData
from ..actions import list_discovered_actions, get_action_definition, get_action_class
from tik.trigger.core.io import IO, ACTION_SESSION_EXT
from tik.shared.io import ensure_extension

logger = logging.getLogger(__name__)


class ActionSession:
    """Manages the action build pipeline for a rigging session.

    ActionSession handles the workflow of:
    1. Adding actions to the build pipeline
    2. Configuring action settings
    3. Running actions in sequence
    4. Saving/loading action sessions

    Example:
        session = ActionSession()
        session.add_action("jointify", order=1)
        session.add_action("skinweights", order=2)
        session.run_all()

        # Save/load
        session.save("my_pipeline.tra")
    """

    def __init__(self, file_path: Optional[str] = None) -> None:
        """Initialize the action session.

        Args:
            file_path: Optional default file path for save/load operations.
        """
        self._io = IO()
        self._file_path: Optional[Path] = Path(file_path) if file_path else None
        self._actions: list[dict] = []
        self._action_classes: dict = {}
        self._current_file: Optional[Path] = None
        self._compare_actions: list = []

        if file_path:
            self._io.file_path = self._file_path

    @property
    def file_path(self) -> Optional[Path]:
        """Return the current session file path."""
        return self._file_path

    @property
    def actions(self) -> list[dict]:
        """Return the list of actions in the pipeline."""
        return deepcopy(self._actions)

    def _register_action_class(self, action_type: str, action_class: type) -> None:
        """Register an action class for use in this session.

        Args:
            action_type: The action type identifier.
            action_class: The ActionCore subclass.
        """
        self._action_classes[action_type] = action_class

    def _get_action_class(self, action_type: str) -> Optional[type]:
        """Get a registered action class by type.

        Args:
            action_type: The action type identifier.

        Returns:
            The action class or None if not registered.
        """
        return self._action_classes.get(action_type)

    def load_action_definitions(self) -> None:
        """Load all available action definitions from the registry.

        This populates the session with all discovered actions and their
        default settings from ui_definition.json.
        """
        for action_type in list_discovered_actions():
            action_def = get_action_definition(action_type)
            if action_def:
                # Extract default settings from ui_definition
                defaults = {}
                for uid in action_def.ui_definition:
                    if uid.value is not None:
                        defaults[uid.key] = uid.value
                self._action_classes[action_type] = {
                    "defaults": defaults,
                    "definition": action_def,
                }
        logger.debug("Loaded %d action definitions", len(self._action_classes))

    def list_valid_actions(self) -> list[str]:
        """Return all available action types.

        Returns:
            Sorted list of valid action type names.
        """
        return sorted(self._action_classes.keys())

    def new_session(self) -> None:
        """Clear the session and start fresh."""
        logger.info("Creating new action session")
        self._actions = []
        self._compare_actions = []
        self._current_file = None

    def add_action(
        self,
        action_type: str,
        order: Optional[int] = None,
        name: Optional[str] = None,
        settings: Optional[dict] = None,
        enabled: bool = True,
    ) -> Optional[dict]:
        """Add an action to the session pipeline.

        Args:
            action_type: The action type to add.
            order: Optional execution order. If None, appends to end.
            name: Optional custom name for this action instance.
            settings: Optional initial settings.
            enabled: Whether the action is enabled (default True).

        Returns:
            The created action dictionary, or None if action type is invalid.
        """
        if action_type not in self._action_classes:
            logger.error("Invalid action type: %s", action_type)
            return None

        # Generate unique name if not provided
        if not name:
            name = self._generate_action_name(action_type)

        # Get default settings from action definition
        action_info = self._action_classes.get(action_type, {})
        defaults = action_info.get("defaults", {}) if isinstance(action_info, dict) else {}

        # Merge with provided settings
        merged_settings = deepcopy(defaults)
        if settings:
            merged_settings.update(settings)

        action = {
            "name": name,
            "action_type": action_type,
            "order": order if order is not None else len(self._actions),
            "settings": merged_settings,
            "enabled": enabled,
        }

        if order is not None:
            self._actions.insert(order, action)
            # Update order numbers for subsequent actions
            for i, a in enumerate(self._actions):
                a["order"] = i
        else:
            self._actions.append(action)

        logger.info("Added action: %s (%s)", name, action_type)
        return action

    def _generate_action_name(self, action_type: str) -> str:
        """Generate a unique action name.

        Args:
            action_type: The action type.

        Returns:
            A unique name for the action.
        """
        base_name = f"{action_type}"
        existing_names = self.list_action_names()

        if base_name not in existing_names:
            return base_name

        counter = 1
        while f"{base_name}{counter}" in existing_names:
            counter += 1
        return f"{base_name}{counter}"

    def get_action(self, name: str) -> Optional[dict]:
        """Get an action by name.

        Args:
            name: The action name.

        Returns:
            The action dictionary or None if not found.
        """
        for action in self._actions:
            if action["name"] == name:
                return action
        return None

    def list_action_names(self) -> list[str]:
        """Return all action names in the pipeline.

        Returns:
            List of action names in order.
        """
        return [a["name"] for a in self._actions]

    def remove_action(self, name: str) -> bool:
        """Remove an action from the pipeline.

        Args:
            name: The action name to remove.

        Returns:
            True if action was removed, False if not found.
        """
        action = self.get_action(name)
        if action:
            self._actions.remove(action)
            # Update order numbers
            for i, a in enumerate(self._actions):
                a["order"] = i
            logger.info("Removed action: %s", name)
            return True
        return False

    def rename_action(self, name: str, new_name: str) -> bool:
        """Rename an action.

        Args:
            name: Current action name.
            new_name: New action name.

        Returns:
            True if renamed successfully, False otherwise.
        """
        if name == new_name:
            return True

        if self.get_action(new_name):
            logger.error("Action name already exists: %s", new_name)
            return False

        action = self.get_action(name)
        if not action:
            logger.error("Action not found: %s", name)
            return False

        action["name"] = new_name
        logger.info("Renamed action: %s -> %s", name, new_name)
        return True

    def duplicate_action(self, name: str) -> Optional[dict]:
        """Duplicate an action.

        Args:
            name: The action name to duplicate.

        Returns:
            The new action dictionary, or None if source not found.
        """
        action = self.get_action(name)
        if not action:
            logger.error("Action not found: %s", name)
            return None

        new_name = self._generate_action_name(action["action_type"])
        new_action = deepcopy(action)
        new_action["name"] = new_name

        # Insert after the original
        index = self._actions.index(action)
        self._actions.insert(index + 1, new_action)

        # Update order numbers
        for i, a in enumerate(self._actions):
            a["order"] = i

        logger.info("Duplicated action: %s -> %s", name, new_name)
        return new_action

    def edit_action_settings(self, name: str, settings: dict) -> bool:
        """Update action settings.

        Args:
            name: The action name.
            settings: Dictionary of settings to update.

        Returns:
            True if updated successfully, False otherwise.
        """
        action = self.get_action(name)
        if not action:
            logger.error("Action not found: %s", name)
            return False

        action["settings"].update(settings)
        logger.debug("Updated settings for action: %s", name)
        return True

    def get_action_settings(self, name: str) -> Optional[dict]:
        """Get action settings.

        Args:
            name: The action name.

        Returns:
            The settings dictionary or None if action not found.
        """
        action = self.get_action(name)
        return action["settings"].copy() if action else None

    def enable_action(self, name: str) -> bool:
        """Enable an action.

        Args:
            name: The action name.

        Returns:
            True if enabled, False if action not found.
        """
        action = self.get_action(name)
        if action:
            action["enabled"] = True
            return True
        return False

    def disable_action(self, name: str) -> bool:
        """Disable an action.

        Args:
            name: The action name.

        Returns:
            True if disabled, False if action not found.
        """
        action = self.get_action(name)
        if action:
            action["enabled"] = False
            return True
        return False

    def is_enabled(self, name: str) -> bool:
        """Check if an action is enabled.

        Args:
            name: The action name.

        Returns:
            True if enabled, False otherwise.
        """
        action = self.get_action(name)
        return action.get("enabled", True) if action else False

    def move_action(self, name: str, new_index: int) -> bool:
        """Move an action to a new position.

        Args:
            name: The action name.
            new_index: The new position index.

        Returns:
            True if moved, False otherwise.
        """
        action = self.get_action(name)
        if not action:
            return False

        old_index = self._actions.index(action)
        if old_index == new_index:
            return True

        self._actions.pop(old_index)
        self._actions.insert(new_index, action)

        # Update order numbers
        for i, a in enumerate(self._actions):
            a["order"] = i

        logger.info("Moved action %s from %d to %d", name, old_index, new_index)
        return True

    def move_up(self, name: str) -> bool:
        """Move an action up in the pipeline.

        Args:
            name: The action name.

        Returns:
            True if moved, False if already at top.
        """
        action = self.get_action(name)
        if not action:
            return False

        index = self._actions.index(action)
        if index == 0:
            return False

        return self.move_action(name, index - 1)

    def move_down(self, name: str) -> bool:
        """Move an action down in the pipeline.

        Args:
            name: The action name.

        Returns:
            True if moved, False if already at bottom.
        """
        action = self.get_action(name)
        if not action:
            return False

        index = self._actions.index(action)
        if index == len(self._actions) - 1:
            return False

        return self.move_action(name, index + 1)

    def run_action(self, name: str) -> bool:
        """Run a single action.

        Args:
            name: The action name to run.

        Returns:
            True if successful, False otherwise.
        """
        action = self.get_action(name)
        if not action:
            logger.error("Action not found: %s", name)
            return False

        if not action.get("enabled", True):
            logger.info("Skipping disabled action: %s", name)
            return True

        action_type = action["action_type"]
        action_class_info = self._action_classes.get(action_type)

        if not action_class_info:
            logger.error("Action class not registered: %s", action_type)
            return False

        # Get the actual class
        if isinstance(action_class_info, dict):
            # It's a registered action definition
            action_class = get_action_class(action_type)
        else:
            action_class = action_class_info

        if not action_class:
            logger.error("Could not find action class for: %s", action_type)
            return False

        logger.info(f"=== Running action: {name} ===")

        try:
            instance = action_class(name=name)
            instance.set_settings(action["settings"])

            # Get selection for feed
            from maya import cmds
            selection = cmds.ls(sl=True, type="transform") or []

            feed_data = instance.feed(selection)
            instance.action(feed_data)

            logger.info("Action completed successfully: %s", name)
            return True

        except Exception as e:
            logger.error("Action failed: %s - %s", name, e)
            raise

    def run_all_actions(self, reset_scene: bool = True) -> bool:
        """Run all enabled actions in sequence.

        Args:
            reset_scene: If True, reset the scene before running actions.

        Returns:
            True if all actions completed successfully.

        Raises:
            Exception: If any action fails.
        """
        if reset_scene:
            from maya import cmds
            try:
                cmds.file(new=True, force=True)
            except Exception:
                pass  # May fail in non-Maya environment

        logger.info("=" * 50)
        logger.info("=== BUILDING ===")

        success = True
        for action in self._actions:
            if not action.get("enabled", True):
                continue

            try:
                self.run_action(action["name"])
            except Exception as e:
                logger.error("Action failed: %s - %s", action["name"], e)
                raise

        logger.info("=== BUILDING COMPLETE ===")
        return success

    def save(self, file_path: Optional[str] = None) -> Optional[Path]:
        """Save the action session to a file.

        Args:
            file_path: Optional override file path.

        Returns:
            The path the session was saved to, or None on failure.
        """
        target = Path(file_path) if file_path else self._file_path
        if not target:
            logger.error("No file path specified for saving")
            return None

        target = ensure_extension(target, ACTION_SESSION_EXT)
        self._io.file_path = target

        session_data = {
            "version": "2.0",
            "actions": deepcopy(self._actions),
        }

        result = self._io.write(session_data)
        if result:
            self._file_path = target
            self._current_file = target
            self._compare_actions = deepcopy(self._actions)
            logger.info("Action session saved: %s", target)

        return result

    def load(self, file_path: str) -> bool:
        """Load an action session from a file.

        Args:
            file_path: Path to the session file to load.

        Returns:
            True if loaded successfully, False otherwise.
        """
        target = Path(file_path)
        self._io.file_path = target

        data = self._io.read()
        if not data:
            logger.error("Failed to load action session from: %s", target)
            return False

        self._actions = data.get("actions", [])
        self._current_file = target
        self._compare_actions = deepcopy(self._actions)

        logger.info("Action session loaded: %s", target)
        return True

    def is_modified(self) -> bool:
        """Check if the session has unsaved changes.

        Returns:
            True if there are unsaved changes.
        """
        return self._compare_actions != self._actions

    def get_session_data(self) -> dict:
        """Get the session data as a dictionary.

        Returns:
            Dictionary containing all session data.
        """
        return {
            "version": "2.0",
            "actions": deepcopy(self._actions),
        }

    def __repr__(self) -> str:
        return f"ActionSession(actions={len(self._actions)}, file={self._file_path})"
