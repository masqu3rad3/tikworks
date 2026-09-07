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
#: Guide module category -> tint. Lives beside SIDE/CATEGORY (not in
#: trigger/ui/designer/widgets.py, where it used to live) because
#: iconography.py needs it and importing it from a designer widget module
#: risks a circular import once anything the designer imports pulls in
#: iconography.py itself.
MODULE_COLORS = {
    "body": "#c9a24a",
    "limbs": "#5b8fd0",
    "generic": "#7fa86a",
    "face": "#b86b9a",
    "scene": "#8a93a0",
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
#FilterInput { min-height: 20px; }
#FilterPill { background-color: #3a2e1f; border: 1px solid #FE7E00; border-radius: 9px; min-height: 18px; }
#FilterPillLabel { color: #e0c8a8; font-size: 10px; background: transparent; border: none; }
#FilterPillClose { color: #e0c8a8; background: transparent; border: none; font-size: 9px; padding: 0 2px; }
#FilterPillClose:hover { color: #ffffff; }
/* --- the filterable tick list (CheckListEditor) --- */
#CheckList { background-color: #151515; border: 1px solid #353535; border-radius: 3px; }
/* the accent is the only thing telling a short list that rows are hidden --
   loud enough to notice on the left edge, quiet enough not to shout */
#CheckList[onlySelected="true"] { border-color: #4a3a26; border-left: 3px solid #FE7E00; background-color: #191512; }
#CheckListHeader { background: transparent; }
#CheckListOnlySelected { color: #b4b4b4; font-size: 11px; }
#CheckListCount { color: #7b7b7b; font-size: 10px; }
/* an untouched picker should not read as a finished one */
#CheckListCount[empty="true"] { color: #c9a24a; }
/* rows: room to click, and a hover that says the row is the target */
#CheckList::item { padding: 2px 5px; border-radius: 2px; color: #c8c8c8; }
#CheckList::item:hover { background-color: #232323; }
#CheckList::item:selected { background-color: #2b2b2b; color: #ececec; }
/* Item-view indicators inherit nothing from the QCheckBox rules above, so
   without these they are whatever the host style draws -- in Maya, a dark box
   on the darkest ground in the app. The unchecked border is deliberately
   lighter than the house checkbox's: this one sits on #151515. */
#CheckList::indicator { width: 13px; height: 13px; margin-right: 4px; border-radius: 2px; }
#CheckList::indicator:unchecked { background-color: #0f0f0f; border: 1px solid #5a5a5a; }
#CheckList::indicator:unchecked:hover { background-color: #1a1a1a; border: 1px solid #FE7E00; }
#CheckList::indicator:checked { background-color: #FE7E00; border: 1px solid #FE7E00; }
#CheckList::indicator:checked:hover { background-color: #FF9500; border: 1px solid #FF9500; }
/* the header's own box sits on the same dark ground and needs the same help;
   the house QCheckBox rule sizes it 9px, so re-assert the whole box */
#CheckListOnlySelected::indicator { width: 11px; height: 11px; border-radius: 2px; }
#CheckListOnlySelected::indicator:unchecked { background-color: #0f0f0f; border: 1px solid #5a5a5a; width: 11px; height: 11px; }
#CheckListOnlySelected::indicator:unchecked:hover { background-color: #1a1a1a; border: 1px solid #FE7E00; width: 11px; height: 11px; }
#CheckListOnlySelected::indicator:checked { background-color: #FE7E00; border: 1px solid #FE7E00; width: 11px; height: 11px; }
#BuildBar { background-color: #1e1e1e; border-top: 1px solid #353535; }
#BuildBar QPushButton { width: auto; min-width: 110px; }
#BuildBar QPushButton#SyncButton { min-width: 92px; }
#BarRule { background-color: #353535; min-width: 1px; max-width: 1px; border: none; }
#BuildBar QPushButton[quiet="true"] { color: #8f8f8f; }
/* Amber, matching trigger.ui.draw_state.STALE_INK -- the bar says the same
   thing the tree dot and the graph node say, and never in the accent. */
#BuildBar QPushButton[alert="true"] { border-color: #EDC13A; color: #e6d5a8; }
#BuildBar #FilterPillLabel { background-color: #3a2e1f; border: 1px solid #FE7E00; border-radius: 9px; padding: 2px 10px; }
QPushButton#PrimaryButton { background-color: #FE7E00; color: #1a1a1a; font-weight: 500; }
QPushButton#PrimaryButton:hover { background-color: #FF9500; }
QProgressBar { background-color: #0f0f0f; border: none; border-radius: 2px; height: 4px; }
QProgressBar::chunk { background-color: #FE7E00; border-radius: 2px; }
CollapsibleGroup > QToolButton { background-color: #2f2f2f; color: #e6e6e6; font-weight: bold; text-align: left; padding: 4px 8px; border: 1px solid #353535; border-radius: 3px; }
CollapsibleGroup > QToolButton:hover { background-color: #383838; }
#SearchPalette { background-color: #0f0f0f; border: 1px solid #353535; border-radius: 6px; }
QTabBar::tab { background-color: #1f1f1f; color: #8a8a8a; padding: 5px 12px; margin-right: 2px; border: 1px solid #303030; border-bottom: none; border-top-left-radius: 3px; border-top-right-radius: 3px; }
/* the base theme's own :selected rule (above, in theme.qss) still contributes
   a gradient border-color and 1px border-width on every side; re-asserting
   the full border here (not just border-top) is what keeps that gradient
   from bleeding onto the selected tab's left/right edges */
QTabBar::tab:selected { background-color: #2a2a2a; color: #ececec; border: 1px solid #303030; border-top: 2px solid #FE7E00; border-bottom: none; }
QTabWidget::pane { border: 1px solid #303030; }
/* the Guide Designer's sub-tab strip, inset from the session tab strip above it */
QTabWidget#SessionSubTabs::tab-bar { left: 14px; }
QTabWidget#SessionSubTabs QTabBar { border-bottom: 1px solid #303030; }
QToolButton { background-color: transparent; border: 1px solid transparent; border-radius: 3px; padding: 2px 6px; color: #c0c0c0; }
QToolButton:hover { background-color: #353535; border-color: #454545; }
QMenuBar::item { padding: 4px 10px; }
QTreeView::branch:selected, QTreeView::branch:selected:active, QTreeView::branch:hover { background-color: transparent; }
#PipelineTree::item:selected, #PipelineTree::item:selected:active, #PipelineTree::item:hover { background-color: transparent; }
#LogWidget { background-color: #151515; color: #c0c0c0; border: none; font-family: Consolas, "Roboto Mono", monospace; font-size: 11px; }
QDockWidget::title { background-color: #1e1e1e; padding: 4px 8px; color: #7b7b7b; }
/* --- the animator Switches dock --- */
#SwitchContext { background-color: #2a2a2a; border-top: 1px solid #303030; border-bottom: 1px solid #303030; }
#SwitchName { color: #ececec; font-family: Consolas, "Roboto Mono", monospace; font-size: 11px; }
#SwitchSides { font-size: 13px; }
#SwitchNote { color: #7b7b7b; font-size: 11px; }
/* the base theme gives every QPushButton width: 100px; a chip is as wide as
   its label, so both the fixed width and the inherited min-width go */
#SwitchChip { background-color: #282828; border: 1px solid #353535; border-radius: 3px; color: #c8c8c8; width: auto; min-width: 0px; min-height: 20px; padding: 2px 12px; }
#SwitchChip:hover { border-color: #FE7E00; }
#SwitchChip[state="current"] { background-color: #3a2e1f; border-color: #FE7E00; color: #e0c8a8; }
#SwitchChip[state="pending"] { border-color: #FE7E00; color: #e0c8a8; }
#SwitchChip[state="mixed"] { border-style: dashed; border-color: #6a5a44; color: #a89478; }
#SwitchChip:checked { background-color: #3a2e1f; border-color: #FE7E00; color: #e0c8a8; }
#SwitchBar { background-color: #1e1e1e; border-top: 1px solid #353535; }
#SwitchBar QPushButton#PrimaryButton { width: auto; min-width: 64px; }
"""


def stylesheet() -> str:
    """Return the theme stylesheet text (house theme + tool additions)."""
    return _QSS.read_text(encoding="utf-8") + TOOL_QSS


def apply(widget) -> None:
    """Apply the theme to a widget. Call AFTER the widget tree is built."""
    widget.setStyleSheet(stylesheet())
