"""Import asset action for tik.trigger.

This action imports external files (Maya, OBJ, FBX, Alembic, USD) into the scene.
"""

from __future__ import annotations

import os
from typing import Any

from tik.trigger.core import ActionCore, register_action


@register_action("import_asset")
class ImportAssetAction(ActionCore):
    """Action to import external files into Maya.

    Supports file formats: .ma, .mb, .obj, .fbx, .abc, .usd, .usda, .usdc
    """

    _action_name = "import_asset"

    def __init__(self, name: str | None = None) -> None:
        """Initialize the import asset action."""
        super().__init__(name)
        self.file_path: str = ""
        self.scale: float = 1.0
        self.root_suffix: str = ""
        self.parent_under: str = ""

    def feed(self, selection: list) -> dict:
        """Validate the file path and prepare import data.

        Args:
            selection: List of selected Maya node names (not used for this action).

        Returns:
            Dictionary with validated file path and settings.

        Raises:
            ActionFeedError: If file path is empty or file doesn't exist.
        """
        from tik.trigger.core.exceptions import ActionFeedError

        self.file_path = self.get_setting("import_file_path", "")
        self.scale = self.get_setting("scale", 1.0)
        self.root_suffix = self.get_setting("root_suffix", "")
        self.parent_under = self.get_setting("parent_under", "")

        if not self.file_path:
            raise ActionFeedError("Import path is not defined.")

        if not os.path.exists(self.file_path):
            raise ActionFeedError(f"File does not exist: {self.file_path}")

        return {
            "file_path": self.file_path,
            "scale": self.scale,
            "root_suffix": self.root_suffix,
            "parent_under": self.parent_under,
        }

    def action(self, feed_data: dict) -> list[str]:
        """Execute the import action.

        Args:
            feed_data: Data from feed() containing file path and settings.

        Returns:
            List of newly created node names.

        Note:
            This is a placeholder. Actual Maya file import operations
            would go here when running in Maya context.
        """
        file_path = feed_data["file_path"]
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".abc":
            return self._import_alembic(file_path)
        elif ext == ".obj":
            return self._import_obj(file_path)
        elif ext == ".fbx":
            return self._import_fbx(file_path)
        elif ext in (".usd", ".usdc", ".usda"):
            return self._import_usd(file_path)
        elif ext in (".ma", ".mb"):
            return self._import_scene(file_path)
        else:
            from tik.trigger.core.exceptions import ActionExecutionError

            raise ActionExecutionError(f"Unrecognized file format: {ext}")

    def save_action(self, feed_data: dict) -> dict:
        """Save the import asset action configuration.

        Args:
            feed_data: The feed data dictionary.

        Returns:
            Dictionary suitable for serialization.
        """
        return {
            "action_type": self.action_type,
            "settings": self._settings.copy(),
            "feed_data": feed_data.copy(),
        }

    # -------------------------------------------------------------------------
    # Import methods - placeholders that would use tik.maya in real implementation
    # -------------------------------------------------------------------------

    def _import_scene(self, file_path: str) -> list[str]:
        """Import Maya scene file (.ma, .mb).

        Args:
            file_path: Path to the Maya scene file.

        Returns:
            List of newly created node names.
        """
        # Placeholder - actual implementation would use:
        # return cmds.file(file_path, i=True, returnNewNodes=True)
        return []

    def _import_obj(self, file_path: str) -> list[str]:
        """Import OBJ file.

        Args:
            file_path: Path to the OBJ file.

        Returns:
            List of newly created node names.
        """
        # Placeholder - actual implementation would use:
        # return cmds.file(file_path, i=True, op="lo=0 mo=1", returnNewNodes=True)
        return []

    def _import_alembic(self, file_path: str) -> list[str]:
        """Import Alembic file (.abc).

        Args:
            file_path: Path to the Alembic file.

        Returns:
            List of newly created node names.
        """
        # Placeholder - actual implementation would use:
        # cmds.AbcImport(file_path, ftr=False, sts=False)
        return []

    def _import_usd(self, file_path: str) -> list[str]:
        """Import USD file (.usd, .usda, .usdc).

        Args:
            file_path: Path to the USD file.

        Returns:
            List of newly created node names.
        """
        # Placeholder - actual implementation would use:
        # return cmds.file(file_path, i=True, type="USD Import", ...)
        return []

    def _import_fbx(self, file_path: str) -> list[str]:
        """Import FBX file.

        Args:
            file_path: Path to the FBX file.

        Returns:
            List of newly created node names.
        """
        # Placeholder - actual implementation would use mel.eval FBXImport commands
        return []

    @staticmethod
    def post_process(
        new_nodes: list[str],
        scale: float = 1.0,
        suffix: str = "",
        parent_under: str = "",
    ) -> None:
        """Post-process imported nodes (scale, rename, parent).

        Args:
            new_nodes: List of imported node names.
            scale: Scale factor to apply.
            suffix: Suffix to add to root nodes.
            parent_under: Parent to put imported nodes under.
        """
        # Placeholder - actual implementation would scale, rename, and parent nodes
        pass
