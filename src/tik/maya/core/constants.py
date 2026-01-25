"""Constants for the Tik Maya Core module."""
from maya import cmds


class _NodeNamesConfig:
    """
    Internal configuration for node names that vary between versions.
    Acts as a singleton to allow lazy property evaluation.
    """

    _cached_version: int | None = None

    @property
    def _maya_version(self) -> int:
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

    @property
    def MULT_DOUBLE_LINEAR(self) -> str:
        """Name for the keyable multDoubleLinear node."""
        return "multDL" if self._maya_version >= 2026 else "multDoubleLinear"

    @property
    def ADD_DOUBLE_LINEAR(self) -> str:
        """Name for the keyable addDoubleLinear node."""
        return "addDL" if self._maya_version >= 2026 else "addDoubleLinear"


# Export as a singleton instance.
# Usage remains consistent: NodeNames.MULT_DOUBLE_LINEAR
NodeNames = _NodeNamesConfig()
