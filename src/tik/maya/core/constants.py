"""Constants for the Tik Maya Core module."""
from maya import cmds


class _NodeNamesConfig:
    """
    Internal configuration for node names that vary between versions.
    Acts as a singleton to allow lazy property evaluation.
    """

    _cached_version: int | None = None
    _lookdevkit_loaded: bool = False

    @property
    def maya_version(self) -> int:
        """
        Lazily retrieves the Maya version.
        Safe for use with pytest because it executes only on access, not import.
        """
        if self._cached_version is None:
            try:
                self._cached_version = int(cmds.about(version=True))
            except (AttributeError, RuntimeError, ValueError):
                # Default to 2026 if accessed during uninitialized states (e.g., test collection)
                self._cached_version = 2026
        return self._cached_version

    def ensure_lookdevkit_loaded(self) -> None:
        """
        Ensure the lookdevKit plugin is loaded (required for floatMath node).

        Only checks and loads once per session for performance.
        """
        if self._lookdevkit_loaded:
            return
        if not cmds.pluginInfo("lookdevKit", query=True, loaded=True):
            cmds.loadPlugin("lookdevKit", quiet=True)
        self._lookdevkit_loaded = True

    @property
    def MULT_DOUBLE_LINEAR(self) -> str:
        """Name for the keyable multDoubleLinear node."""
        return "multDL" if self.maya_version >= 2026 else "multDoubleLinear"

    @property
    def ADD_DOUBLE_LINEAR(self) -> str:
        """Name for the keyable addDoubleLinear node."""
        return "addDL" if self.maya_version >= 2026 else "addDoubleLinear"

    @property
    def uses_native_math_nodes(self) -> bool:
        """Check if native subtract/divide nodes are available (Maya 2025+)."""
        return self.maya_version >= 2025


# Export as a singleton instance.
# Usage remains consistent: NodeNames.MULT_DOUBLE_LINEAR
NodeNames = _NodeNamesConfig()
