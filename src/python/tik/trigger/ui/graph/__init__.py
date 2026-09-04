"""Node graph of module instances: input ports left, output ports right, wires between.

The graph edits the same connections the tree does (through ``GuideScene``), and
stores its own state (node positions, collapse modes, scene-node groups) in
``GuideScene.layout`` so it lands in the ``.trg`` and undoes with Maya.

* drag from an output port to an input port to connect;
* drag a connected input port away to unplug it (drop on another input to
  re-plug, drop on empty space to disconnect);
* select wires and press Delete / Backspace to disconnect;
* Ctrl + left drag draws a slice line: every wire it crosses is disconnected;
* 1 / 2 / 3 (or the identity glyph in a node header) set the collapse mode:
  1 = header only, 2 = connected plugs, 3 = everything;
* **Scene Nodes** groups (dashed) expose arbitrary Maya nodes as outputs.
"""

from .constants import MODE_CONNECTED, MODE_FULL, MODE_MINIMAL
from .items import NodeItem, Port, WireItem
from .scene import GraphScene
from .view import GraphView

__all__ = [
    "GraphScene",
    "GraphView",
    "NodeItem",
    "Port",
    "WireItem",
    "MODE_MINIMAL",
    "MODE_CONNECTED",
    "MODE_FULL",
]
