"""Input/output operations for JSON configuration files in tik.trigger.

This module provides the ConfigIO class for reading and writing JSON
configuration files with proper error handling and path management.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)


class ConfigIO:
    """Input/output class for JSON configuration operations.

    This class handles reading and writing JSON configuration files,
    with support for default values and file existence checking.

    Attributes:
        valid_extensions: List of supported file extensions.
        file_path: Current file path, or None if not set.
    """

    valid_extensions = [".json"]

    def __init__(self, file_path: Optional[Union[str, Path]] = None) -> None:
        """Initialize the ConfigIO instance.

        Args:
            file_path: Optional path to the configuration file.
        """
        self.file_path: Optional[Path] = None
        if file_path is not None:
            self.set_file_path(file_path)

    def set_file_path(self, new_path: Union[str, Path]) -> None:
        """Set the file path.

        Args:
            new_path: File path to be set.

        Raises:
            ValueError: If the file has no extension or unsupported extension.
        """
        path = Path(new_path)
        ext = path.suffix

        if not ext:
            logger.error("ConfigIO requires a file extension")
            raise ValueError("Missing file extension.")
        if ext not in self.valid_extensions:
            logger.error("ConfigIO does not support extension: %s", ext)
            raise ValueError(f"Unsupported extension: {ext}")
        self._ensure_folder_exists(path)
        self.file_path = path

    def read(self, file_path: Optional[Union[str, Path]] = None) -> dict | list | str | int | float | bool | None:
        """Read data from file.

        Args:
            file_path: If defined, data will be read from this file
                instead of the class file_path. Defaults to None.

        Returns:
            The contents of the file if it exists, None otherwise.
        """
        path = Path(file_path) if file_path is not None else self.file_path
        if path is None:
            return None
        if path.is_file():
            return self._load_json(path)
        logger.debug("File does not exist: %s", path)
        return None

    def write(
        self,
        data: Any,
        file_path: Optional[Union[str, Path]] = None,
    ) -> Path:
        """Write data to the given or class-defined file_path.

        Args:
            data: Data to write.
            file_path: If defined, the data is written to this path
                rather than the class-defined path. Defaults to None.

        Returns:
            Path to the file that was written.

        Raises:
            ValueError: If file path is not set.
        """
        path = Path(file_path) if file_path is not None else self.file_path
        if path is None:
            raise ValueError("File path is not set.")
        self._dump_json(data, path)
        return path

    @staticmethod
    def _load_json(file_path: Union[str, Path]) -> dict | list | str | int | float:
        """Load the given JSON file.

        Args:
            file_path: Path to the file.

        Returns:
            Content of the JSON file.

        Raises:
            ValueError: If the file is not valid JSON.
        """
        path = Path(file_path)
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except json.JSONDecodeError as e:
            logger.error("Corrupted JSON file: %s - %s", path, e)
            raise ValueError(f"Corrupted JSON file: {path}") from e

    @staticmethod
    def file_exists(file_path: Union[str, Path]) -> bool:
        """Check if the file exists.

        Args:
            file_path: Path to the file to check.

        Returns:
            True if the file exists, False otherwise.
        """
        return Path(file_path).exists()

    @staticmethod
    def _dump_json(data: Any, file_path: Union[str, Path]) -> None:
        """Save data to a JSON file.

        Args:
            data: Data to write.
            file_path: Path to the file.
        """
        path = Path(file_path)
        ConfigIO._ensure_folder_exists(path)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            logger.debug("Written JSON to: %s", path)

    @staticmethod
    def _ensure_folder_exists(path: Union[str, Path]) -> Path:
        """Ensure the folder containing the path exists.

        Args:
            path: File or folder path to check.

        Returns:
            The path that was passed in, as a Path object.
        """
        path = Path(path)
        base_folder = path.parent if path.suffix else path
        base_folder.mkdir(parents=True, exist_ok=True)
        return path


def read_json(file_path: Union[str, Path]) -> Optional[dict]:
    """Read a JSON file and return its contents.

    Args:
        file_path: Path to the JSON file.

    Returns:
        The JSON contents, or None if file doesn't exist.
    """
    io = ConfigIO(file_path)
    return io.read()


def write_json(file_path: Union[str, Path], data: Any) -> Path:
    """Write data to a JSON file.

    Args:
        file_path: Path to the JSON file.
        data: Data to write.

    Returns:
        Path to the file that was written.
    """
    io = ConfigIO(file_path)
    return io.write(data)
