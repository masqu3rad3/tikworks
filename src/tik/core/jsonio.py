"""Generic JSON I/O utilities."""

import json
from json import JSONDecodeError
from pathlib import Path


class JsonIOError(Exception):
    """Base exception for JSON I/O operations."""

    pass


class JsonDecodeError(JsonIOError):
    """Exception raised when JSON decoding fails."""

    pass


def load(path: Path | str) -> dict:
    """Load JSON data from a file.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed JSON data as a dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        JsonDecodeError: If the file contains invalid JSON.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    try:
        with path.open("r", encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except JSONDecodeError as exc:
        raise JsonDecodeError(f"Invalid JSON: {path}") from exc


def save(
    path: Path | str,
    data: dict,
    *,
    indent: int = 2,
    sort_keys: bool = True,
    ensure_ascii: bool = False,
):
    """Save dictionary data to a JSON file.

    Args:
        path: Path where the JSON file will be saved.
        data: Dictionary data to save.
        indent: Number of spaces for indentation (default: 2).
        sort_keys: Whether to sort dictionary keys (default: True).
        ensure_ascii: Whether to escape non-ASCII characters (default: False).

    Note:
        Parent directories will be created automatically if they don't exist.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(
            data,
            file_handle,
            indent=indent,
            sort_keys=sort_keys,
            ensure_ascii=ensure_ascii,
        )


def loads(content: str) -> dict:
    """Parse JSON text into a dictionary.

    Args:
        content: JSON text payload.

    Returns:
        Parsed JSON data as a dictionary.

    Raises:
        JsonDecodeError: If the text contains invalid JSON.
    """
    try:
        return json.loads(content)
    except JSONDecodeError as exc:
        raise JsonDecodeError("Invalid JSON text") from exc


def dumps(
    data: dict,
    *,
    indent: int = 2,
    sort_keys: bool = True,
    ensure_ascii: bool = False,
) -> str:
    """Serialize a dictionary into JSON text.

    Args:
        data: Dictionary data to serialize.
        indent: Number of spaces for indentation (default: 2).
        sort_keys: Whether to sort dictionary keys (default: True).
        ensure_ascii: Whether to escape non-ASCII characters (default: False).

    Returns:
        JSON text payload.
    """
    return json.dumps(
        data,
        indent=indent,
        sort_keys=sort_keys,
        ensure_ascii=ensure_ascii,
    )
