"""JSON I/O utilities for tik.trigger.

Provides file reading/writing functionality for saving and loading
guide sessions and action sessions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from tik.shared.io import IO as _BaseIO

logger = logging.getLogger(__name__)

# File extensions
GUIDE_SESSION_EXT = ".trg"
ACTION_SESSION_EXT = ".tra"


class IO(_BaseIO):
    """JSON file I/O handler for session files.

    Extends tik.shared.io.IO with session-specific extensions.
    Handles reading and writing of session data to JSON files with
    proper error handling and metadata preservation.
    """

    def __init__(self, file_path: Optional[Path] = None) -> None:
        """Initialize the IO handler.

        Args:
            file_path: Optional default file path for read/write operations.
        """
        valid_exts = [GUIDE_SESSION_EXT, ACTION_SESSION_EXT, ".json"]
        # Initialize with valid_extensions first, then set file_path separately
        # This allows file_path to be None without validation errors
        self.valid_extensions = valid_exts
        self._file_path: Optional[Path] = None
        if file_path:
            self.file_path = file_path

    @property
    def file_path(self) -> Optional[Path]:
        """Return the current file path."""
        return self._file_path

    @file_path.setter
    def file_path(self, path: Optional[Path]) -> None:
        """Set the file path.

        Args:
            path: The new file path or None to clear.
        """
        self._file_path = Path(path) if path else None

    def read(self, file_path: Optional[Path] = None) -> Optional[dict]:
        """Read session data from a JSON file.

        Args:
            file_path: Optional override file path. Uses self._file_path if not provided.

        Returns:
            The parsed JSON data as a dictionary, or None if the file cannot be read.
        """
        target = Path(file_path) if file_path is not None else self._file_path
        if not target:
            logger.error("No file path specified for reading")
            return None

        if target.suffix not in self.valid_extensions:
            # Try appending .json for backward compatibility
            target = target.with_suffix(".json")

        try:
            data = self._load_json(target)
            logger.debug("Successfully read session from: %s", target)
            return data
        except FileNotFoundError:
            logger.error("Session file not found: %s", target)
            return None
        except Exception as e:
            logger.error("Error reading session file %s: %s", target, e)
            return None

    def write(self, data: dict, file_path: Optional[Path] = None) -> Optional[Path]:
        """Write session data to a JSON file.

        Args:
            data: The session data dictionary to write.
            file_path: Optional override file path. Uses self._file_path if not provided.

        Returns:
            The file path that was written to, or None on failure.
        """
        target = Path(file_path) if file_path is not None else self._file_path
        if not target:
            logger.error("No file path specified for writing")
            return None

        try:
            self.folder_check(target)
            self._dump_json(data, target)
            logger.debug("Successfully wrote session to: %s", target)
            return target
        except Exception as e:
            logger.error("Error writing session file %s: %s", target, e)
            return None


def read_session(file_path: Path) -> Optional[dict]:
    """Convenience function to read a session file.

    Args:
        file_path: Path to the session file.

    Returns:
        The parsed session data or None on failure.
    """
    io = IO(file_path=file_path)
    return io.read()


def write_session(file_path: Path, data: dict) -> Optional[Path]:
    """Convenience function to write a session file.

    Args:
        file_path: Path for the session file.
        data: Session data to write.

    Returns:
        The written file path or None on failure.
    """
    io = IO(file_path=file_path)
    return io.write(data)