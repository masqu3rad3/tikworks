"""Scene-node groups: Maya nodes that modules connect to, stored in the layout."""

from __future__ import annotations

from typing import Optional

from tik.trigger.core.exceptions import GuideError


class SceneGroupsMixin:
    """Mixed into :class:`~.scene.GuideScene`; reads and writes through ``self``."""

    # ------------------------------------------------------ scene nodes
    def scene_groups(self) -> dict[str, list[str]]:
        """``{group name: [scene node, ...]}``: Maya nodes modules connect to."""
        return {
            name: list(nodes)
            for name, nodes in self.layout.get("scene_nodes", {}).items()
        }

    def add_scene_group(self, name: str = "", nodes: Optional[list[str]] = None) -> str:
        """Create a scene-nodes group; unnamed ones get a free ``sceneNodesN``."""
        groups = self.scene_groups()
        taken = set(groups) | {handle.key for handle in self.instances()}
        if not name:
            index = 1
            while f"sceneNodes{index}" in taken:
                index += 1
            name = f"sceneNodes{index}"
        elif name in taken:
            raise GuideError(f"'{name}' is already used.")
        groups[name] = list(nodes or [])
        self.update_layout(scene_nodes=groups)
        return name

    def set_scene_group(self, name: str, nodes: list[str]) -> None:
        """Replace a group's nodes, dropping connections to the removed ones."""
        groups = self.scene_groups()
        if name not in groups:
            raise GuideError(f"No scene-nodes group '{name}'.")
        removed = set(groups[name]) - set(nodes)
        groups[name] = [node for node in nodes if node]
        self.update_layout(scene_nodes=groups)
        for item in self.connections():
            if item["source"] in removed and not self.scene_node_group(item["source"]):
                self.disconnect(item["input"])

    def rename_scene_group(self, old: str, new: str) -> None:
        """Rename a scene-nodes group and the connections and layout that use it."""
        new = (new or "").strip()
        groups = self.scene_groups()
        if old not in groups:
            raise GuideError(f"No scene-nodes group '{old}'.")
        if not new or new == old:
            return
        if new in groups or self.by_key(new) is not None:
            raise GuideError(f"'{new}' is already used.")
        # Rename inside one display-key layout and write it back in a single
        # pass. Renaming the document tables directly does not work: they are
        # id-keyed, and ``update_layout`` re-projects them through the *current*
        # group names, so an entry already moved to ``new`` fails to project and
        # the group silently loses its graph position.
        layout = self.layout
        layout["scene_nodes"] = {
            new if name == old else name: nodes for name, nodes in groups.items()
        }
        for section in ("positions", "collapse"):
            table = layout.get(section) or {}
            if old in table:
                table[new] = table.pop(old)
        self.set_layout(layout)

    def remove_scene_group(self, name: str) -> None:
        """Delete a scene-nodes group and the connections that used its nodes."""
        groups = self.scene_groups()
        nodes = set(groups.pop(name, []))
        self.update_layout(scene_nodes=groups)
        for item in self.connections():
            if item["source"] in nodes and not self.scene_node_group(item["source"]):
                self.disconnect(item["input"])
        document = self.document
        document.positions.pop(name, None)
        document.collapse.pop(name, None)
        self._touch()

    def scene_node_group(self, node: str) -> Optional[str]:
        """The group that lists scene node ``node`` (first match)."""
        for name, members in self.scene_groups().items():
            if node in members:
                return name
        return None
