"""JSON I/O utilities for tik.shared.

Provides the IO base class for reading and writing JSON files.
Delegates to tik.core.jsonio for actual I/O operations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, Union

from tik.core.jsonio import load as _json_load, save as _json_save

LOG = logging.getLogger(__name__)


class IO:
    """Input/output class for JSON operations."""

    def __init__(
        self,
        file_path: Union[str, Path],
        valid_extensions: Optional[list[str]] = None,
    ) -> None:
        """Initialize the IO instance.

        Args:
            file_path: Path to the file. Must have extension.
            valid_extensions: List of valid file extensions. Defaults to [".json"].
        """
        self.valid_extensions = valid_extensions or [".json"]
        self.file_path: Optional[Path] = None
        self.set_file_path(file_path)

    def set_file_path(self, new_path: Union[str, Path]) -> None:
        """Set the file path.

        Args:
            new_path: File path to be set. Can be None to clear the path.

        Raises:
            Exception: If the extension is not defined.
            Exception: If the extension is not among valid extensions.
        """
        if new_path is None:
            self.file_path = None
            return

        path = Path(new_path)
        ext = path.suffix

        if not ext:
            LOG.error("IO module needs to know the extension")
            raise Exception("Missing file extension.")
        if ext not in self.valid_extensions:
            LOG.error("IO module does not support this extension (%s)", ext)
            raise Exception(f"Unsupported extension: {ext}")
        self.folder_check(path)
        self.file_path = path

    def read(
        self, file_path: Optional[Union[str, Path]] = None
    ) -> Union[dict, list, str, int, float, bool]:
        """Read data from file.

        Args:
            file_path: If defined, data will be read from this file
                instead of the class variable. Defaults to None.

        Returns:
            dict | list | str | int | float | bool: Contents of the file
                if it exists. Returns False if the file does not exist.
        """
        path = Path(file_path) if file_path is not None else self.file_path
        if path is None:
            return False
        if path.is_file():
            return self._load_json(path)
        return False

    def write(self, data: Any, file_path: Optional[Union[str, Path]] = None) -> Path:
        """Write data to the given or class-defined file_path.

        Args:
            data: Data to write.
            file_path: If defined, the data is written into the specified path
                rather than the class defined. Defaults to None.

        Returns:
            Path: Path to the file.

        Raises:
            Exception: If file path is not set.
        """
        path = Path(file_path) if file_path is not None else self.file_path
        if path is None:
            raise Exception("File path is not set.")
        self._dump_json(data, path)
        return path

    @staticmethod
    def _load_json(
        file_path: Union[str, Path],
    ) -> Union[dict, list, str, int, float]:
        """Load the given JSON file.

        Args:
            file_path: Path to the file.

        Returns:
            dict | list | str | int | float: Content of the JSON file.

        Raises:
            Exception: If the file is not following JSON standards.
        """
        try:
            return _json_load(file_path)
        except Exception as e:
            LOG.error("Corrupted file => %s", file_path)
            raise Exception(f"Corrupted file => {file_path}") from e

    @staticmethod
    def file_exists(file_path: Union[str, Path]) -> bool:
        """Check if the file exists.

        Args:
            file_path: Path to the file to check.

        Returns:
            bool: True if the file exists, False otherwise.
        """
        return Path(file_path).exists()

    @staticmethod
    def _dump_json(data: Any, file_path: Union[str, Path]) -> None:
        """Save data to the JSON file.

        Args:
            data: Data to write into JSON file.
            file_path: Path to the file.
        """
        _json_save(file_path, data)

    @staticmethod
    def folder_check(checkpath: Union[str, Path]) -> Path:
        """Check if the folder exists and create if it doesn't.

        Args:
            checkpath: File or folder path to check.

        Returns:
            Path: Passes checkpath input back as Path.
        """
        path = Path(checkpath)
        base_folder = path.parent if path.suffix else path
        base_folder.mkdir(parents=True, exist_ok=True)
        return path


def ensure_extension(file_path: Path, extension: str) -> Path:
    """Ensure a file path has the correct extension.

    Args:
        file_path: The file path to check.
        extension: The expected extension (e.g., '.trg').

    Returns:
        The file path with the correct extension.
    """
    if not file_path.suffix:
        return file_path.with_suffix(extension)
    if file_path.suffix != extension:
        return file_path.with_suffix(extension)
    return file_path
