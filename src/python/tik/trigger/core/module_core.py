"""ModuleCore and GuidesCore base classes for tik.trigger modules.

Modules represent rig building blocks (like biped arms, spines, legs) that
have both a guide phase (where the user positions guides in the scene) and
a build phase (where the actual rig is constructed from those guides).

- GuidesCore: Handles guide creation and manipulation in the scene
- ModuleCore: Handles rig building based on guide data

Example:
    @register_module("bipedArm")
    class BipedArmGuide(GuidesCore):
        ...

    @register_module("bipedArm")
    class BipedArmModule(ModuleCore):
        ...
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from .schemas import GuideData, ModuleDefinition

if TYPE_CHECKING:
    from .action_core import ActionCore

logger = logging.getLogger(__name__)


class GuidesCore(ABC):
    """Base class for guide creation and manipulation.

    Guides are temporary scene elements that users position to define
    the desired structure before building the rig. Subclasses should
    implement guide creation and manipulation methods.

    Attributes:
        _module_name: The module identifier this guide belongs to.
    """

    _module_name: str = ""

    def __init__(self, name: Optional[str] = None) -> None:
        """Initialize the guides.

        Args:
            name: Optional custom name for this guide instance.
        """
        self._name = name or self.__class__.__name__
        self._guides: list[GuideData] = []
        self._selected_guide: Optional[int] = None
        logger.debug("Initialized guides: %s", self._name)

    @property
    def name(self) -> str:
        """Return the guide instance name."""
        return self._name

    @property
    def module_name(self) -> str:
        """Return the module name this guide belongs to."""
        return self._module_name

    @property
    def guides(self) -> list[GuideData]:
        """Return the list of guide data."""
        return self._guides.copy()

    def add_guide(self, guide_data: GuideData) -> None:
        """Add a guide to this module's guide list.

        Args:
            guide_data: The guide data to add.
        """
        self._guides.append(guide_data)
        logger.debug("Added guide: %s", guide_data.name)

    def remove_guide(self, index: int) -> GuideData:
        """Remove a guide by index.

        Args:
            index: The index of the guide to remove.

        Returns:
            The removed guide data.
        """
        return self._guides.pop(index)

    def clear_guides(self) -> None:
        """Remove all guides."""
        self._guides.clear()
        self._selected_guide = None

    def select_guide(self, index: Optional[int]) -> None:
        """Set the currently selected guide.

        Args:
            index: The guide index to select, or None to deselect.
        """
        self._selected_guide = index

    @property
    def selected_guide(self) -> Optional[int]:
        """Return the currently selected guide index."""
        return self._selected_guide

    def get_selected_guide_data(self) -> Optional[GuideData]:
        """Return the currently selected guide data, if any."""
        if self._selected_guide is not None and 0 <= self._selected_guide < len(self._guides):
            return self._guides[self._selected_guide]
        return None

    @abstractmethod
    def create_guides(self) -> None:
        """Create all guides in the Maya scene.

        Subclasses should implement this to create the actual Maya nodes
        representing the guides based on stored guide data.
        """
        raise NotImplementedError

    @abstractmethod
    def update_guide(self, index: int, guide_data: GuideData) -> None:
        """Update a guide at the given index.

        Args:
            index: The index of the guide to update.
            guide_data: The new guide data.
        """
        raise NotImplementedError

    @abstractmethod
    def delete_guides(self) -> None:
        """Delete all guide Maya nodes from the scene."""
        raise NotImplementedError

    def get_guide_data_from_scene(self) -> list[GuideData]:
        """Query current guide positions from the Maya scene.

        This should be implemented to sync guide data with actual Maya node
        positions after user manipulation.

        Returns:
            List of current guide data.
        """
        return self._guides.copy()

    def sync_guides_to_scene(self) -> None:
        """Sync stored guide data to Maya scene positions.

        This updates Maya guide nodes to match the stored guide data.
        """
        for index, guide_data in enumerate(self._guides):
            self.update_guide(index, guide_data)


class ModuleCore(ABC):
    """Base class for rig module building.

    Modules take guide data and produce the actual rig structure. The build()
    method is the main entry point that creates all rig nodes based on
    the guide configuration.

    Attributes:
        _module_name: The module identifier.
        _guide_class: The corresponding GuidesCore subclass.
    """

    _module_name: str = ""
    _guide_class: Optional[type[GuidesCore]] = None

    def __init__(self, guides: GuidesCore, name: Optional[str] = None) -> None:
        """Initialize the module with guide data.

        Args:
            guides: The guides instance containing guide configuration.
            name: Optional custom name for this module instance.
        """
        self._name = name or self.__class__.__name__
        self._guides = guides
        self._settings: dict = {}
        self._built: bool = False
        logger.debug("Initialized module: %s", self._name)

    @property
    def name(self) -> str:
        """Return the module instance name."""
        return self._name

    @property
    def module_name(self) -> str:
        """Return the module type name."""
        return self._module_name

    @property
    def guide_class(self) -> Optional[type[GuidesCore]]:
        """Return the corresponding GuidesCore class for this module."""
        return self._guide_class

    @property
    def settings(self) -> dict:
        """Return the current settings for this module."""
        return self._settings.copy()

    @property
    def is_built(self) -> bool:
        """Return whether the rig has been built from these guides."""
        return self._built

    def set_settings(self, settings: dict) -> None:
        """Update the module settings.

        Args:
            settings: Dictionary of settings to apply.
        """
        self._settings = settings.copy()

    def get_setting(self, key: str, default=None):
        """Get a specific setting value.

        Args:
            key: The setting key.
            default: Default value if key is not found.
        """
        return self._settings.get(key, default)

    def reset_settings(self) -> None:
        """Reset settings to default values."""
        self._settings = {}

    @abstractmethod
    def build(self) -> None:
        """Build the rig from the guide configuration.

        This is the main method that creates all Maya nodes and connections
        to form the complete rig structure based on the guides.

        Raises:
            BuildError: If the build process fails.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self) -> None:
        """Delete the built rig from the scene.

        Should remove all rig nodes created by build().
        """
        raise NotImplementedError

    @abstractmethod
    def mirror(self, source_guide_names: list[str]) -> None:
        """Mirror the rig from source guides.

        Args:
            source_guide_names: Names of source guides to mirror from.
        """
        raise NotImplementedError

    def get_build_data(self) -> dict:
        """Return data describing the built rig for serialization.

        Returns:
            A dictionary suitable for serialization.
        """
        return {
            "module_type": self._module_name,
            "name": self._name,
            "settings": self._settings.copy(),
            "guides": self._guides.get_guide_data_from_scene(),
        }

    def validate_guides(self) -> bool:
        """Validate that guides are properly configured for building.

        Returns:
            True if guides are valid, False otherwise.
        """
        return len(self._guides.guides) > 0

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self._name}')"
