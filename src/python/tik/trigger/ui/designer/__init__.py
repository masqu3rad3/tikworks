"""The Guide Designer window, split by responsibility.

``window`` holds the shell and the views; ``widgets`` the leaf widgets;
``commands`` the verbs; ``properties`` the properties panel and its bindings.
"""

from .widgets import GuideTree, InputRow, SceneNodesPanel, module_entries
from .window import GuideDesigner

__all__ = ["GuideDesigner", "GuideTree", "InputRow", "SceneNodesPanel", "module_entries"]
