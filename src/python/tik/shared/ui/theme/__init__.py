"""The tikworks Qt theme (dark ground, one warm accent) and its colour tokens."""

from __future__ import annotations

from pathlib import Path

_QSS = Path(__file__).with_name("theme.qss")

# Palette tokens (mirror theme.qss so painters/delegates stay consistent)
GROUND = "#242424"
PANEL = "#2f2f2f"
PANEL_ALT = "#353535"
INPUT = "#0f0f0f"
LINE = "#353535"
TEXT = "#c0c0c0"
TEXT_BRIGHT = "#ffffff"
TEXT_DIM = "#8f8f8f"
ACCENT = "#FE7E00"
ACCENT_HOVER = "#FF9500"

STATUS = {
    "": "#4f4f4f",
    "pending": "#4f4f4f",
    "running": ACCENT,
    "done": "#5ec48a",
    "failed": "#e06666",
    "skipped": "#575757",
}
LINKED = "#8fa4c0"
SIDE = {"L": "#5b8fd0", "R": "#d06a66", "C": "#d4b04a"}
CATEGORY = {
    "structure": "#8fa4c0",
    "build": "#c9a24a",
    "deform": "#b86b9a",
    "finish": "#7fa86a",
    "utility": "#6a6a6a",
}


def stylesheet() -> str:
    """Return the theme stylesheet text."""
    return _QSS.read_text(encoding="utf-8")


def apply(widget) -> None:
    """Apply the theme to a widget (usually the top-level window)."""
    widget.setStyleSheet(stylesheet())
