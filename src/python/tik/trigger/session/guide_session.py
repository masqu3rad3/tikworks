"""Guide session management for tik.trigger.

Manages the guide creation workflow including:
- Creating guides for modules
- Collecting guide data from the scene
- Saving/loading guide sessions
- Rebuilding guides from saved data
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..core.schemas import GuideData, ModuleInstanceData
from ..modules import get_guide_class, get_module_class
from tik.trigger.core.io import IO, GUIDE_SESSION_EXT
from tik.shared.io import ensure_extension

if TYPE_CHECKING:
    from ..modules import GuidesCore

logger = logging.getLogger(__name__)


class GuideSession:
    """Manages guide creation and persistence for a rigging session.

    GuideSession handles the workflow of:
    1. Creating guide joints for modules
    2. Collecting guide data from the scene
    3. Saving guide sessions to disk
    4. Loading and rebuilding guides from saved sessions

    Example:
        session = GuideSession()
        session.create_guides("bipedArm", side="L")
        session.save("my_character.trg")

        # Later...
        session.load("my_character.trg")
    """

    def __init__(self, file_path: Optional[str] = None) -> None:
        """Initialize the guide session.

        Args:
            file_path: Optional default file path for save/load operations.
        """
        self._io = IO()
        self._file_path = Path(file_path) if file_path else None
        self._modules: dict[str, "GuidesCore"] = {}
        if file_path:
            self._io.file_path = self._file_path

    @property
    def file_path(self) -> Optional[Path]:
        """Return the current session file path."""
        return self._file_path

    @property
    def modules(self) -> dict[str, "GuidesCore"]:
        """Return the registered guide modules."""
        return self._modules.copy()

    def create_guides(self, module_type: str, name: Optional[str] = None, **kwargs) -> "GuidesCore":
        """Create guides for a module type.

        Args:
            module_type: The module type to create guides for (e.g., 'bipedArm').
            name: Optional custom name for this guide instance.
            **kwargs: Additional arguments passed to the guide constructor.

        Returns:
            The created GuidesCore instance.

        Raises:
            ValueError: If the module type is not found.
        """
        guide_class = get_guide_class(module_type)
        if not guide_class:
            raise ValueError(f"Unknown module type: {module_type}")

        instance_name = name or f"{module_type}_{len(self._modules)}"
        guide = guide_class(name=instance_name, **kwargs)
        guide.create_guides()
        self._modules[instance_name] = guide

        logger.info("Created guides for %s: %s", module_type, instance_name)
        return guide

    def add_guide_module(self, instance_id: str, guide: "GuidesCore") -> None:
        """Add an existing guide module to the session.

        Args:
            instance_id: Unique identifier for this guide instance.
            guide: The GuidesCore instance to add.
        """
        self._modules[instance_id] = guide
        logger.debug("Added guide module: %s", instance_id)

    def get_guide_module(self, instance_id: str) -> Optional["GuidesCore"]:
        """Get a guide module by instance ID.

        Args:
            instance_id: The instance identifier.

        Returns:
            The GuidesCore instance or None if not found.
        """
        return self._modules.get(instance_id)

    def remove_guide_module(self, instance_id: str) -> None:
        """Remove a guide module from the session.

        Args:
            instance_id: The instance identifier to remove.
        """
        if instance_id in self._modules:
            guide = self._modules[instance_id]
            guide.delete_guides()
            del self._modules[instance_id]
            logger.info("Removed guide module: %s", instance_id)

    def clear(self) -> None:
        """Clear all guide modules from the session."""
        for instance_id, guide in self._modules.items():
            guide.delete_guides()
        self._modules.clear()
        logger.info("Cleared all guide modules")

    def collect_guides(self) -> list[dict]:
        """Collect all guide data from the scene.

        Returns guide data for all modules including position, rotation,
        side, parent relationships, and any custom user attributes.

        Returns:
            List of guide data dictionaries suitable for JSON serialization.
        """
        all_guide_data = []

        for instance_id, guide in self._modules.items():
            # Get fresh guide data from scene
            scene_guides = guide.get_guide_data_from_scene()

            module_instance_data = {
                "module_type": guide.module_name,
                "instance_id": instance_id,
                "guides": [self._guide_data_to_dict(gd) for gd in scene_guides],
                "settings": guide.settings if hasattr(guide, "settings") else {},
            }
            all_guide_data.append(module_instance_data)

        logger.debug("Collected guide data for %d modules", len(all_guide_data))
        return all_guide_data

    def _guide_data_to_dict(self, guide_data: GuideData) -> dict:
        """Convert GuideData to a serializable dictionary.

        Args:
            guide_data: The GuideData instance.

        Returns:
            Dictionary representation of the guide data.
        """
        return {
            "name": guide_data.name,
            "position": guide_data.position,
            "rotation": guide_data.rotation,
            "side": guide_data.side,
            "parent": guide_data.parent,
            "children": guide_data.children,
        }

    def rebuild_guides(self, guide_session_data: list[dict]) -> None:
        """Rebuild guides from saved session data.

        Args:
            guide_session_data: List of module instance dictionaries
                from a previously saved session.
        """
        # Clear existing guides first
        self.clear()

        for module_data in guide_session_data:
            module_type = module_data["module_type"]
            instance_id = module_data["instance_id"]
            guides_list = module_data.get("guides", [])
            settings = module_data.get("settings", {})

            # Get the guide class and create new instance
            guide_class = get_guide_class(module_type)
            if not guide_class:
                logger.warning("Unknown module type: %s, skipping", module_type)
                continue

            guide = guide_class(name=instance_id)
            guide.set_settings(settings) if hasattr(guide, "set_settings") else None

            # Rebuild each guide
            for gd in guides_list:
                guide_data = GuideData(
                    name=gd["name"],
                    position=tuple(gd["position"]),
                    rotation=tuple(gd["rotation"]),
                    side=gd.get("side", "C"),
                    parent=gd.get("parent"),
                    children=gd.get("children", []),
                )
                guide.add_guide(guide_data)

            # Create the actual Maya nodes
            guide.create_guides()
            self._modules[instance_id] = guide

            logger.info("Rebuilt guides for module: %s (%s)", instance_id, module_type)

    def save(self, file_path: Optional[str] = None) -> Optional[Path]:
        """Save the guide session to a file.

        Args:
            file_path: Optional override file path.

        Returns:
            The path the session was saved to, or None on failure.
        """
        target = Path(file_path) if file_path else self._file_path
        if not target:
            logger.error("No file path specified for saving")
            return None

        target = ensure_extension(target, GUIDE_SESSION_EXT)
        self._io.file_path = target

        session_data = {
            "version": "2.0",
            "modules": self.collect_guides(),
        }

        result = self._io.write(session_data)
        if result:
            self._file_path = target
            logger.info("Guide session saved: %s", target)

        return result

    def load(self, file_path: str, reset_scene: bool = False) -> bool:
        """Load a guide session from a file.

        Args:
            file_path: Path to the session file to load.
            reset_scene: If True, clear existing guides before loading.

        Returns:
            True if the session was loaded successfully, False otherwise.
        """
        target = Path(file_path)
        self._io.file_path = target

        data = self._io.read()
        if not data:
            logger.error("Failed to load guide session from: %s", target)
            return False

        if reset_scene:
            self.clear()

        modules_data = data.get("modules", [])
        self.rebuild_guides(modules_data)

        self._file_path = target
        logger.info("Guide session loaded: %s", target)
        return True

    def get_scene_roots(self) -> list[dict]:
        """Get all root guide joints in the current scene.

        Returns:
            List of dictionaries containing root joint information.
        """
        roots = []
        for instance_id, guide in self._modules.items():
            scene_guides = guide.get_guide_data_from_scene()
            if scene_guides:
                # First guide is typically the root
                root_guide = scene_guides[0]
                roots.append({
                    "instance_id": instance_id,
                    "module_type": guide.module_name,
                    "root_joint": root_guide.name,
                    "side": root_guide.side,
                })
        return roots

    def test_build(self, instance_id: Optional[str] = None) -> Optional[object]:
        """Test build a module to verify guide setup.

        Args:
            instance_id: The module instance to test build. If None,
                uses the first module in the session.

        Returns:
            The built module instance, or None on failure.

        Raises:
            ValueError: If the module instance is not found.
        """
        if instance_id:
            guide = self._modules.get(instance_id)
            if not guide:
                raise ValueError(f"Module instance not found: {instance_id}")
        else:
            if not self._modules:
                logger.warning("No modules to test build")
                return None
            instance_id, guide = next(iter(self._modules.items()))

        module_class = get_module_class(guide.module_name)
        if not module_class:
            logger.error("No module class found for: %s", guide.module_name)
            return None

        module = module_class(guide)
        module.build()
        logger.info("Test build completed for: %s", instance_id)
        return module
