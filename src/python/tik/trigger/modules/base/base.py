"""Base module for tik.trigger.

This is the simplest module - it creates a single root joint with no controls.

Note: Module configuration is defined in data.json, not in Python code.
"""

from __future__ import annotations

from tik.trigger.core import GuidesCore, ModuleCore, register_module
from tik.trigger.core.exceptions import BuildError
from tik.trigger.core.schemas import GuideData


@register_module("base_guide")
class Guides(GuidesCore):
    """Guide class for the base module.

    Creates a single guide joint at the origin.
    """

    _module_name = "base"

    def create_guides(self) -> None:
        """Create the base guide joint.

        Creates a single root guide joint at the world origin.
        """
        self.clear_guides()

        guide = GuideData(
            name="root_jnt",
            position=(0.0, 0.0, 0.0),
            rotation=(0.0, 0.0, 0.0),
            side="C",
        )
        self.add_guide(guide)

    def update_guide(self, index: int, guide_data: GuideData) -> None:
        """Update a guide at the given index.

        Args:
            index: The index of the guide to update.
            guide_data: The new guide data.
        """
        if 0 <= index < len(self._guides):
            self._guides[index] = guide_data

    def delete_guides(self) -> None:
        """Delete all guide nodes from the Maya scene."""
        self.clear_guides()


@register_module("base")
class Base(ModuleCore):
    """Module class for the base rig.

    Builds a simple rig with a single root joint and placement controller.
    """

    _module_name = "base"
    _guide_class = Guides

    def __init__(self, guides: GuidesCore, name: str | None = None) -> None:
        """Initialize the base module.

        Args:
            guides: The guides instance containing guide configuration.
            name: Optional custom name for this module instance.
        """
        super().__init__(guides, name)
        self.module_name = name or "base"
        self.base_jnt: str | None = None
        self._built_controls: bool = False

    def build(self) -> None:
        """Build the base rig.

        Creates a single root joint at the guide position.
        """
        if not self.validate_guides():
            raise BuildError("Cannot build base: no guides found.")

        self._built_controls = self.get_setting("build_controls", True)
        self._built = True

    def delete(self) -> None:
        """Delete the built rig from the scene."""
        self._built = False
        self._built_controls = False

    def mirror(self, source_guide_names: list[str]) -> None:
        """Mirror is not applicable for base module.

        Args:
            source_guide_names: Not used.
        """
        # Base module has no mirrorable content
        pass
