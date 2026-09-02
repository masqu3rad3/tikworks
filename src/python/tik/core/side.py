"""Side designation shared by rigging tools."""

from __future__ import annotations

from enum import Enum


class Side(str, Enum):
    """Left / right / center designation."""

    CENTER = "C"
    LEFT = "L"
    RIGHT = "R"

    @classmethod
    def from_value(cls, value) -> "Side":
        """Accept a ``Side``, a letter (``"L"``) or a word (``"left"``)."""
        if isinstance(value, cls):
            return value
        text = str(value).strip()
        lookup = {
            "c": cls.CENTER,
            "center": cls.CENTER,
            "centre": cls.CENTER,
            "l": cls.LEFT,
            "left": cls.LEFT,
            "r": cls.RIGHT,
            "right": cls.RIGHT,
        }
        try:
            return lookup[text.lower()]
        except KeyError:
            raise ValueError(f"Unknown side '{value}'.") from None

    @property
    def mirror(self) -> "Side":
        """Return the opposite side (center mirrors to itself)."""
        if self is Side.LEFT:
            return Side.RIGHT
        if self is Side.RIGHT:
            return Side.LEFT
        return Side.CENTER

    @property
    def multiplier(self) -> int:
        """Return ``-1`` for right, ``1`` otherwise."""
        return -1 if self is Side.RIGHT else 1

    def __str__(self) -> str:
        return self.value
