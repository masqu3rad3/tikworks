"""
color.py

A lightweight, object-oriented color manipulation library.
Internal storage is strictly RGB Float (0.0 - 1.0).
"""

from __future__ import annotations

import colorsys
import math
import random


class Color:
    """Lightweight, object-oriented color manipulation library.

    Internal storage uses RGB Float values (0.0 - 1.0).
    Supports creation from color names, hex codes, and RGB tuples.
    """

    # --- Human-readable color names ---
    NAMES = {
        "black": (0, 0, 0),
        "white": (1, 1, 1),
        "red": (1, 0, 0),
        "lime": (0, 1, 0),
        "blue": (0, 0, 1),
        "yellow": (1, 1, 0),
        "cyan": (0, 1, 1),
        "magenta": (1, 0, 1),
        "silver": (0.75, 0.75, 0.75),
        "gray": (0.5, 0.5, 0.5),
        "grey": (0.5, 0.5, 0.5),
        "maroon": (0.5, 0, 0),
        "olive": (0.5, 0.5, 0),
        "green": (0, 0.5, 0),
        "purple": (0.5, 0, 0.5),
        "teal": (0, 0.5, 0.5),
        "navy": (0, 0, 0.5),
        "orange": (1, 0.65, 0),
        "gold": (1, 0.84, 0),
        "pink": (1, 0.75, 0.8),
        "violet": (0.93, 0.51, 0.93),
        "darkgrey": (0.2, 0.2, 0.2),
    }

    # --- Randomization modes (enum-like constants) ---
    RANDOM_ANY = "any"
    RANDOM_PASTEL = "pastel"
    RANDOM_NEON = "neon"
    RANDOM_METALLIC = "metallic"
    RANDOM_DARK = "dark"

    _EPSILON = 1e-6

    def __init__(self, value=None):
        self._r = 0.0
        self._g = 0.0
        self._b = 0.0

        if value is None:
            return

        if isinstance(value, Color):
            self._r, self._g, self._b = value.rgb
            return

        if isinstance(value, str):
            self._from_string(value)
            return

        if isinstance(value, (tuple, list)):
            self._from_sequence(value)
            return

        raise TypeError(f"Unsupported type for Color: {type(value)}")

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _from_string(self, value: str):
        value = value.strip().lower()

        if value.startswith("#"):
            self._from_hex(value)
            return

        if value in self.NAMES:
            self._r, self._g, self._b = self.NAMES[value]
            return

        raise ValueError(f"Unknown color name or format: {value}")

    def _from_hex(self, hex_str: str):
        hex_str = hex_str.lstrip("#")

        if len(hex_str) == 3:
            hex_str = "".join(char * 2 for char in hex_str)

        if len(hex_str) != 6:
            raise ValueError(f"Invalid Hex String: {hex_str}")

        try:
            red = int(hex_str[0:2], 16)
            green = int(hex_str[2:4], 16)
            blue = int(hex_str[4:6], 16)
        except ValueError:
            raise ValueError(f"Invalid Hex String: {hex_str}")

        self._r = red / 255.0
        self._g = green / 255.0
        self._b = blue / 255.0

    def _from_sequence(self, seq):
        if len(seq) < 3:
            raise ValueError("Sequence must contain at least 3 values")

        red, green, blue = seq[:3]

        is_int_format = any(value > 1.0 for value in (red, green, blue)) or all(
            isinstance(value, int) for value in (red, green, blue)
        )

        if is_int_format:
            self._r = float(red) / 255.0
            self._g = float(green) / 255.0
            self._b = float(blue) / 255.0
        else:
            self._r = float(red)
            self._g = float(green)
            self._b = float(blue)

    # ------------------------------------------------------------------
    # Properties / Conversions
    # ------------------------------------------------------------------

    @property
    def rgb(self):
        """Return color as RGB float tuple (0.0-1.0)."""
        return (self._r, self._g, self._b)

    @property
    def rgb255(self):
        """Return color as RGB integer tuple (0-255)."""
        return (
            int(self._r * 255),
            int(self._g * 255),
            int(self._b * 255),
        )

    @property
    def hex(self):
        """Return color as hexadecimal string (e.g., '#FF00AA')."""
        return "#{:02X}{:02X}{:02X}".format(*self.rgb255)

    @property
    def hsv(self):
        """Return color as HSV tuple (hue, saturation, value)."""
        return colorsys.rgb_to_hsv(self._r, self._g, self._b)

    # ------------------------------------------------------------------
    # Randomization (with some sugar)
    # ------------------------------------------------------------------

    @classmethod
    def random(cls, mode=RANDOM_ANY, seed=None):
        """Generate a random color with optional mode and seed.

        Args:
                mode: One of RANDOM_ANY, RANDOM_PASTEL, RANDOM_NEON,
                    RANDOM_METALLIC, RANDOM_DARK
            seed: Optional random seed for reproducibility

        Returns:
            Color: A new randomly generated Color instance
        """
        if seed is not None:
            random.seed(seed)

        if mode == cls.RANDOM_PASTEL:
            hue = random.random()
            saturation = random.uniform(0.2, 0.5)
            value = random.uniform(0.8, 1.0)
            return cls(colorsys.hsv_to_rgb(hue, saturation, value))

        if mode == cls.RANDOM_NEON:
            hue = random.random()
            saturation = random.uniform(0.8, 1.0)
            value = 1.0
            return cls(colorsys.hsv_to_rgb(hue, saturation, value))

        if mode == cls.RANDOM_METALLIC:
            metallic_hues = [
                random.uniform(0.0, 0.15),
                random.uniform(0.5, 0.66),
            ]
            hue = random.choice(metallic_hues)
            saturation = random.uniform(0.0, 0.25)
            value = random.uniform(0.6, 0.9)

            if hue < 0.2:
                saturation = random.uniform(0.4, 0.7)

            return cls(colorsys.hsv_to_rgb(hue, saturation, value))

        if mode == cls.RANDOM_DARK:
            hue = random.random()
            saturation = random.random()
            value = random.uniform(0.0, 0.3)
            return cls(colorsys.hsv_to_rgb(hue, saturation, value))

        return cls((random.random(), random.random(), random.random()))

    # ------------------------------------------------------------------
    # Modifiers
    # ------------------------------------------------------------------

    def set_hsv(self, hue=None, saturation=None, value=None):
        """Modify color using HSV values.

        Args:
            hue: Hue (0.0-1.0), None to keep current
            saturation: Saturation (0.0-1.0), None to keep current
            value: Value/brightness (0.0-1.0), None to keep current

        Returns:
            self: For method chaining
        """
        current_hue, current_saturation, current_value = self.hsv
        self._r, self._g, self._b = colorsys.hsv_to_rgb(
            hue if hue is not None else current_hue,
            saturation if saturation is not None else current_saturation,
            value if value is not None else current_value,
        )
        return self

    # ------------------------------------------------------------------
    # Magic methods
    # ------------------------------------------------------------------

    def __repr__(self):
        return f"<Color {self.hex} (R:{self._r:.2f} G:{self._g:.2f} B:{self._b:.2f})>"

    def __eq__(self, other):
        if not isinstance(other, Color):
            return NotImplemented

        return (
            math.isclose(self._r, other._r, abs_tol=self._EPSILON)
            and math.isclose(self._g, other._g, abs_tol=self._EPSILON)
            and math.isclose(self._b, other._b, abs_tol=self._EPSILON)
        )

    def __add__(self, other):
        other = Color(other)
        return Color(
            (
                self._clamp(self._r + other._r),
                self._clamp(self._g + other._g),
                self._clamp(self._b + other._b),
            )
        )

    def __mul__(self, factor):
        if not isinstance(factor, (int, float)):
            raise TypeError("Can only multiply color by a scalar")

        return Color(
            (
                self._clamp(self._r * factor),
                self._clamp(self._g * factor),
                self._clamp(self._b * factor),
            )
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp(val):
        return max(0.0, min(1.0, val))
