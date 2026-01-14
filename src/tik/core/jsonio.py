"""Generic JSON I/O utilities."""

from pathlib import Path
import json
from json import JSONDecodeError

class JsonIOError(Exception):
    pass

class JsonDecodeError(JsonIOError):
    pass

def load(path: Path | str) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
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
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as _f:
        json.dump(
            data,
            _f,
            indent=indent,
            sort_keys=sort_keys,
            ensure_ascii=ensure_ascii,
        )
