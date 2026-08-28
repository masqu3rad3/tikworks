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


TOOL_QSS = """
/* --- tool additions on top of theme.qss (scoped by object name) --- */
QStatusBar { background-color: #1e1e1e; border-top: 1px solid #353535; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: #7b7b7b; }
#StatusActivity { color: #c0c0c0; }
#StatusSeparator { color: #4a4a4a; }
QSplitter::handle { background-color: #1f1f1f; }
QSplitter::handle:horizontal { width: 6px; border-left: 1px solid #303030; border-right: 1px solid #303030; }
QSplitter::handle:vertical { height: 6px; border-top: 1px solid #303030; border-bottom: 1px solid #303030; }
#PipelineTree, #GuideTree, #GraphView { background-color: #151515; border: 1px solid #353535; border-radius: 3px; alternate-background-color: #191919; }
#PaneHeader, #ShelfHeader, #FieldCaption { color: #7b7b7b; font-size: 10px; letter-spacing: 1px; }
#ShelfHeader { margin-top: 6px; }
#ShelfTile { background-color: #282828; border: 1px solid #353535; border-radius: 3px; color: #c8c8c8; font-size: 10px; }
#ShelfTile:hover { background-color: #2b2b2b; border-color: #FE7E00; }
#ShelfTile:pressed { background-color: #3a2e1f; }
#PanelTitle { font-size: 14px; font-weight: 500; color: #ececec; }
#PanelSubtitle { color: #7b7b7b; font-size: 11px; }
#LinkedNote { color: #a8b3c2; font-size: 11px; }
#BuildBar { background-color: #1e1e1e; border-top: 1px solid #353535; }
#BuildBar QPushButton { width: auto; min-width: 110px; }
QPushButton#PrimaryButton { background-color: #FE7E00; color: #1a1a1a; font-weight: 500; }
QPushButton#PrimaryButton:hover { background-color: #FF9500; }
QProgressBar { background-color: #0f0f0f; border: none; border-radius: 2px; height: 4px; }
QProgressBar::chunk { background-color: #FE7E00; border-radius: 2px; }
CollapsibleGroup > QToolButton { background-color: #2f2f2f; color: #e6e6e6; font-weight: bold; text-align: left; padding: 4px 8px; border: 1px solid #353535; border-radius: 3px; }
CollapsibleGroup > QToolButton:hover { background-color: #383838; }
#SearchPalette { background-color: #0f0f0f; border: 1px solid #353535; border-radius: 6px; }
QTabBar::tab { background-color: #1f1f1f; color: #8a8a8a; padding: 5px 12px; border: 1px solid #303030; border-bottom: none; border-top-left-radius: 3px; border-top-right-radius: 3px; }
QTabBar::tab:selected { background-color: #2a2a2a; color: #ececec; border-top: 2px solid #FE7E00; }
QTabWidget::pane { border: 1px solid #303030; }
QToolButton { background-color: transparent; border: 1px solid transparent; border-radius: 3px; padding: 2px 6px; color: #c0c0c0; }
QToolButton:hover { background-color: #353535; border-color: #454545; }
QMenuBar::item { padding: 4px 10px; }
QTreeView::branch:selected, QTreeView::branch:selected:active, QTreeView::branch:hover { background-color: transparent; }
#PipelineTree::item:selected, #PipelineTree::item:selected:active, #PipelineTree::item:hover { background-color: transparent; }
#LogWidget { background-color: #151515; color: #c0c0c0; border: none; font-family: Consolas, "Roboto Mono", monospace; font-size: 11px; }
QDockWidget::title { background-color: #1e1e1e; padding: 4px 8px; color: #7b7b7b; }
"""


def stylesheet() -> str:
    """Return the theme stylesheet text (house theme + tool additions)."""
    return _QSS.read_text(encoding="utf-8") + TOOL_QSS


def apply(widget) -> None:
    """Apply the theme to a widget. Call AFTER the widget tree is built."""
    widget.setStyleSheet(stylesheet())
