"""The graph widget: navigation, layout, and the edits that go back to the scene.

Navigation follows Maya: Alt + middle drag pans, Alt + right drag zooms
around the point you pressed, the wheel zooms under the pointer, F fits.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tik.shared.ui import theme
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.core.exceptions import TriggerError
from tik.trigger.core.schemas import split_source
from tik.trigger.ui.draw_state import DRAWN

from .constants import (
    COLUMN_GAP,
    GRID,
    HEADER,
    MODE_FULL,
    NODE_WIDTH,
    PORT_RADIUS,
    ROW,
    ROW_GAP,
    WORLD,
)
from .items import FrameSpec, NodeItem, NodeSpec, WireItem
from .scene import GraphScene

#: Separates a member's key from its port on a collapsed reference node.
#: Deliberately not a dot -- ``add_wire`` splits a port key on the last one.
MEMBER_SEPARATOR = ":"


class GraphView(QtWidgets.QGraphicsView):
    """Renders a ``GuideScene``'s instances and connections; edits go through it."""

    selection_changed = QtCore.Signal(str)
    external_selection_changed = QtCore.Signal(str)
    frame_selection_changed = QtCore.Signal(str)  # reference id
    node_menu_requested = QtCore.Signal(str, object)  # module key, global QPoint
    palette_requested = QtCore.Signal()
    edited = QtCore.Signal()

    def __init__(self, guides, parent=None, events=None) -> None:
        super().__init__(parent)
        self.setObjectName("GraphView")
        self.guides = guides
        self.events = events
        # {instance_id: draw state}; the Designer pushes it, see set_draw_states
        self.draw_states: dict = {}
        self.graph = GraphScene(self)
        self.setScene(self.graph)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        # Maya-style navigation: no scrollbars, pan with the middle button anywhere
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.graph.setSceneRect(QtCore.QRectF(-WORLD, -WORLD, 2 * WORLD, 2 * WORLD))
        self._fitted = False
        self._navigated = False  # once the user pans/zooms, resizes stop re-fitting
        self._nav: Optional[str] = None  # "pan" | "zoom" | "slice"
        self._nav_last = QtCore.QPoint()
        self._zoom_anchor = QtCore.QPointF()
        self._zoom_origin = QtCore.QPoint()
        self._slice_item: Optional[QtWidgets.QGraphicsLineItem] = None
        self._ctrl_press: Optional[QtCore.QPoint] = (
            None  # Ctrl+LMB pressed, not yet a drag
        )
        self.graph.connect_requested.connect(self.connect_input)
        self.graph.disconnect_requested.connect(self.disconnect_input)
        self.graph.remove_group_requested.connect(self.remove_scene_group)
        self.graph.node_selected.connect(self.selection_changed)
        self.graph.external_selected.connect(self.external_selection_changed)
        self.graph.frame_selected.connect(self.frame_selection_changed)
        self.graph.mode_change_requested.connect(self.set_mode)
        self.graph.nodes_moved.connect(self.save_positions)
        self.graph.frame_toggle_requested.connect(self.toggle_frame)

    # ------------------------------------------------------------ building
    def set_draw_states(self, states: dict) -> None:
        """``{instance_id: draw state}``, pushed in by the Designer.

        Pushed rather than computed here on purpose: the tree and the graph
        paint from *one* diff, so the graph must never go and scan the scene
        for a second opinion.
        """
        self.draw_states = dict(states or {})

    def rebuild(self) -> None:
        """Redraw every node and wire from the document and its layout."""
        layout = self.guides.layout
        positions = dict(layout.get("positions", {}))
        collapse = dict(layout.get("collapse", {}))
        groups = {
            name: list(nodes) for name, nodes in layout.get("scene_nodes", {}).items()
        }
        self.graph.clear_graph()
        handles = self.guides.instances()
        by_key = {handle.key: handle for handle in handles}
        origin_of, collapsed, files = self._reference_state(handles)
        # A collapsed reference is not *hidden*: its members are simply not
        # built, and one node is built in their place. Two builds rather than
        # a hide-and-reroute means there is no second wire path to keep right.
        hidden = {key for key, origin in origin_of.items() if origin in collapsed}
        drawn = [handle for handle in handles if handle.key not in hidden]
        # scene sources nobody grouped yet -> implicit "scene" group (shown, not
        # written)
        grouped = {node for nodes in groups.values() for node in nodes}
        for handle in handles:
            for source in handle.inputs.values():
                key, _output = split_source(source)
                if (key is None or key not in by_key) and source not in grouped:
                    groups.setdefault("scene", []).append(source)
                    grouped.add(source)
        depth = self._depths(handles, by_key)
        auto = self._auto_positions(handles, groups, depth)
        placed: list[QtCore.QRectF] = (
            []
        )  # rects of nodes with a stored position; new nodes avoid them

        def rect_at(pos, height):
            return QtCore.QRectF(pos[0], pos[1], NODE_WIDTH + PORT_RADIUS * 2, height)

        def free_pos(key, height):
            stored = positions.get(key)
            if stored:
                placed.append(rect_at(stored, height))
                return stored
            # a collapsed reference has no auto slot: it is not a module
            pos = list(auto.get(key, (20.0, 30.0)))
            candidate = rect_at(pos, height)
            for _ in range(200):
                hit = next(
                    (
                        rect
                        for rect in placed
                        if rect.intersects(candidate.adjusted(-8, -8, 8, 8))
                    ),
                    None,
                )
                if hit is None:
                    break
                pos[1] = hit.bottom() + ROW_GAP
                candidate = rect_at(pos, height)
            if self.graph.snap:
                pos = [round(pos[0] / GRID) * GRID, round(pos[1] / GRID) * GRID]
            placed.append(rect_at(pos, height))
            return tuple(pos)

        for name in sorted(groups):
            pos = free_pos(name, HEADER + len(groups[name]) * ROW + 8)
            node = self.graph.add_node(
                NodeSpec(
                    key=name,
                    title=name,
                    subtitle="scene",
                    inputs=[],
                    outputs=groups[name],
                    color="",
                    external=True,
                    mode=collapse.get(name, MODE_FULL),
                ),
                pos=pos,
            )
            exists = getattr(self.guides, "scene_node", lambda _n: True)
            missing = [item for item in groups[name] if exists(item) is None]
            node.subtitle = "scene ✗ missing" if missing else "scene ✓"
        crossings = self._crossings(handles, by_key, origin_of, collapsed)
        for ref_id in sorted(collapsed):
            ports = crossings.get(ref_id, {"inputs": [], "outputs": []})
            rows = max(len(ports["inputs"]), len(ports["outputs"]), 1)
            frame_key = "@" + ref_id
            stored = self.guides.frames.get(ref_id, {}).get("position")
            pos = (
                tuple(stored)
                if stored
                else free_pos(frame_key, HEADER + rows * ROW + 8)
            )
            self.graph.add_node(
                NodeSpec(
                    key=frame_key,
                    title=files.get(ref_id, "reference"),
                    subtitle="reference",
                    inputs=list(ports["inputs"]),
                    outputs=list(ports["outputs"]),
                    color="",
                    reference=True,
                    mode=MODE_FULL,
                ),
                pos=pos,
            )
        for handle in sorted(
            drawn, key=lambda item: (depth.get(item.key, 1), item.key)
        ):
            module_cls = handle.module_class
            space_names = [
                item.name for item in module_cls.space_inputs(handle.settings)
            ]
            rows = max(
                len(module_cls.inputs) + len(space_names), len(handle.outputs), 1
            )
            pos = free_pos(handle.key, HEADER + rows * ROW + 8)
            primary = module_cls.primary_input()
            self.graph.add_node(
                NodeSpec(
                    key=handle.key,
                    title=handle.key,
                    subtitle=module_cls.display_label(),
                    inputs=[item.name for item in module_cls.inputs],
                    outputs=list(handle.outputs),
                    color=theme.SIDE.get(handle.side.value, theme.SIDE["C"]),
                    primary_input=primary.name if primary else None,
                    mode=collapse.get(handle.key, MODE_FULL),
                    spaces=space_names,
                    draw_state=self.draw_states.get(handle.instance_id, DRAWN),
                ),
                pos=pos,
            )
        self._add_frames(origin_of, collapsed, files)
        node_group = {node: name for name, nodes in groups.items() for node in nodes}
        for handle in handles:
            primary = handle.module_class.primary_input()
            for input_name, source in handle.inputs.items():
                key, output = split_source(source)
                if key is not None and key in by_key:
                    source_key = f"{key}.{output}"
                else:
                    source_key = f"{node_group.get(source, 'scene')}.{source}"
                target_key = f"{handle.key}.{input_name}"
                source_key = self._through_frame(source_key, origin_of, collapsed)
                target_key = self._through_frame(target_key, origin_of, collapsed)
                if source_key.split(".")[0] == target_key.split(".")[0]:
                    continue  # both ends inside one collapsed reference
                self.graph.add_wire(
                    source_key,
                    target_key,
                    primary is not None and input_name == primary.name,
                )
        self.graph.finish_build()
        if not self._fitted:
            self.fit()

    def _auto_positions(self, handles, groups, depth) -> dict[str, tuple]:
        """Column per dependency depth, nodes stacked by their real height."""
        columns: dict[int, float] = {}
        result: dict[str, tuple] = {}

        def place(key, column, height):
            top = columns.get(column, 0.0)
            result[key] = (20 + column * (NODE_WIDTH + COLUMN_GAP), 30 + top)
            columns[column] = top + height + ROW_GAP

        for name in sorted(groups):
            place(name, 0, HEADER + len(groups[name]) * ROW + 8)
        for handle in sorted(
            handles, key=lambda item: (depth.get(item.key, 1), item.key)
        ):
            rows = max(
                len(handle.module_class.inputs)
                + len(handle.module_class.space_inputs(handle.settings)),
                len(handle.outputs),
                1,
            )
            place(handle.key, depth.get(handle.key, 1), HEADER + rows * ROW + 8)
        return result

    def auto_layout(self) -> None:
        """Lay every node out by dependency depth and store it (one Maya undo step)."""
        handles = self.guides.instances()
        by_key = {handle.key: handle for handle in handles}
        groups = self.guides.scene_groups()
        depth = self._depths(handles, by_key)
        positions = {
            key: list(position)
            for key, position in self._auto_positions(handles, groups, depth).items()
        }
        self.guides.update_layout(positions=positions)
        self.rebuild()
        self.fit()

    def toggle_frame(self, ref_id: str) -> None:
        """Collapse an expanded reference, or expand a collapsed one."""
        frames = getattr(self.guides, "frames", {}) or {}
        collapsed = bool(frames.get(ref_id, {}).get("collapsed"))
        self.guides.set_frame(ref_id, collapsed=not collapsed)
        self.rebuild()

    def save_positions(self) -> None:
        """Persist node positions after a drag (undoable in Maya)."""
        positions = self.guides.layout.get("positions", {})
        for key, node in self.graph.nodes.items():
            if key.startswith("@"):
                # a collapsed reference is not a module: its position lives in
                # the frames section, which a layout write does not replace
                self.guides.set_frame(
                    key[1:], position=(node.pos().x(), node.pos().y())
                )
                continue
            positions[key] = [node.pos().x(), node.pos().y()]
        self.guides.update_layout(positions=positions)
        self.graph.moved = set()

    def set_mode(self, key: str, mode: int) -> None:
        """Set the collapse mode of node ``key`` and store it in the layout."""
        node = self.graph.nodes.get(key)
        if node is None:
            return
        node.set_mode(mode)
        collapse = self.guides.layout.get("collapse", {})
        collapse[key] = node.mode
        self.guides.update_layout(collapse=collapse)

    def set_selected_mode(self, mode: int) -> None:
        """Set the collapse mode of every selected node."""
        for node in self.graph.selected_nodes():
            self.set_mode(node.key, mode)

    def fit(self) -> None:
        """Show the whole graph, never zoomed in past 1:1."""
        rect = self.graph.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        view = self.viewport().rect()
        if rect.isEmpty() or view.width() < 60 or view.height() < 60:
            return
        self.resetTransform()
        scale = min(
            1.0,
            (view.width() - 20) / max(rect.width(), 1),
            (view.height() - 20) / max(rect.height(), 1),
        )
        self.scale(max(scale, 0.3), max(scale, 0.3))
        self.centerOn(rect.center())
        self._fitted = True

    # ---------------------------------------------------------- references
    def _reference_state(self, handles) -> tuple:
        """``({module key: ref_id}, {collapsed ref ids}, {ref id: file name})``."""
        document = getattr(self.guides, "document", None)
        if document is None:
            return {}, set(), {}
        entries = {entry.instance_id: entry for entry in document.modules}
        origin_of = {}
        for handle in handles:
            entry = entries.get(handle.instance_id)
            if entry is not None and entry.origin is not None:
                origin_of[handle.key] = entry.origin
        frames = getattr(self.guides, "frames", {}) or {}
        borrowed = set(origin_of.values())
        collapsed = {
            ref_id
            for ref_id, frame in frames.items()
            if frame.get("collapsed") and ref_id in borrowed
        }
        files = {item.ref_id: Path(item.file).name for item in document.references}
        return origin_of, collapsed, files

    @staticmethod
    def _through_frame(port_key: str, origin_of: dict, collapsed: set) -> str:
        """Re-address a port that now sits inside a collapsed reference.

        The port keeps its member's own key (``L_arm.end``), so a wire still
        names its real producer and expanding restores the same connection
        with no translation table to keep in step.
        """
        node, _dot, port = port_key.rpartition(".")
        ref_id = origin_of.get(node)
        if ref_id is None or ref_id not in collapsed:
            return port_key
        # ``:`` and not ``.``: the port name carries its member's key, and a
        # dot inside it would be read as the node/port split by ``add_wire``.
        return f"@{ref_id}.{node}{MEMBER_SEPARATOR}{port}"

    def _crossings(self, handles, by_key, origin_of: dict, collapsed: set) -> dict:
        """Which ports a collapsed reference has to expose.

        Only the connections that *cross* its boundary: hiding what is
        internal is the entire reason to collapse one.
        """
        found = {ref_id: {"inputs": [], "outputs": []} for ref_id in collapsed}
        for handle in handles:
            inside = origin_of.get(handle.key)
            consumer_in = inside if inside in collapsed else None
            for input_name, source in handle.inputs.items():
                key, output = split_source(source)
                producer = origin_of.get(key) if key in by_key else None
                producer_in = producer if producer in collapsed else None
                if producer_in == consumer_in:
                    continue  # both ends in the same place: nothing crosses
                if producer_in is not None:
                    port = f"{key}{MEMBER_SEPARATOR}{output}"
                    if port not in found[producer_in]["outputs"]:
                        found[producer_in]["outputs"].append(port)
                if consumer_in is not None:
                    port = f"{handle.key}{MEMBER_SEPARATOR}{input_name}"
                    if port not in found[consumer_in]["inputs"]:
                        found[consumer_in]["inputs"].append(port)
        return found

    def _add_frames(self, origin_of: dict, collapsed: set, files: dict) -> None:
        """A backdrop behind each expanded reference, sized to its members."""
        members: dict = {}
        for key, ref_id in origin_of.items():
            if ref_id in collapsed:
                continue
            node = self.graph.nodes.get(key)
            if node is not None:
                members.setdefault(ref_id, []).append(node)
        for ref_id, nodes in members.items():
            extent = nodes[0].sceneBoundingRect()
            for node in nodes[1:]:
                extent = extent.united(node.sceneBoundingRect())
            self.graph.add_frame(
                FrameSpec(ref_id=ref_id, title=files.get(ref_id, "reference")),
                extent,
            )

    @staticmethod
    def _depths(handles, by_key) -> dict[str, int]:
        depth: dict[str, int] = {}

        def visit(handle, seen=()):
            if handle.key in depth:
                return depth[handle.key]
            level = 1
            for source in handle.inputs.values():
                key, _output = split_source(source)
                if key in by_key and key not in seen:
                    level = max(level, visit(by_key[key], seen + (handle.key,)) + 1)
            depth[handle.key] = level
            return level

        for handle in handles:
            visit(handle)
        return depth

    # ------------------------------------------------------------- editing
    def _apply(self, action) -> bool:
        try:
            action()
        except TriggerError as error:
            if self.events is not None:
                self.events.log(str(error), level="warning")
            self.rebuild()
            return False
        self.rebuild()
        self.edited.emit()
        return True

    def resolve_source(self, source_key: str) -> str:
        """``group.node`` on a scene-nodes group -> plain scene node name.

        Module sources are returned unchanged.
        """
        node_key, _dot, port = source_key.rpartition(".")
        node = self.graph.nodes.get(node_key)
        if node is not None and node.external:
            return port
        return source_key

    def connect_input(self, input_key: str, source_key: str) -> None:
        """Connect ``input_key`` to ``source_key`` through the guides."""
        source = self.resolve_source(source_key)
        self._apply(lambda: self.guides.connect(input_key, source))

    def disconnect_input(self, input_key: str) -> None:
        """Clear ``input_key`` through the guides."""
        self._apply(lambda: self.guides.disconnect(input_key))

    def sever(self, key: str) -> None:
        """Drop every connection into or out of node ``key`` (module or group)."""
        group_nodes = set(self.guides.scene_groups().get(key, []))

        def run():
            for item in self.guides.connections():
                source_key, _output = split_source(item["source"])
                if (
                    item["input"].startswith(f"{key}.")
                    or source_key == key
                    or item["source"] in group_nodes
                ):
                    self.guides.disconnect(item["input"])

        self._apply(run)

    # ----------------------------------------------------- scene groups
    def add_scene_group(self, name: str = "", nodes: Optional[list] = None) -> str:
        """Create a scene-nodes group, redraw and select it."""
        name = self.guides.add_scene_group(name, nodes)
        self.rebuild()
        self.graph.select_key(name)
        return name

    def add_scene_node(self, name: str, group: str = "scene") -> None:
        """Put scene node ``name`` into ``group``, creating the group if needed."""
        groups = self.guides.scene_groups()
        if group not in groups:
            self.guides.add_scene_group(group, [name])
        elif name not in groups[group]:
            self.guides.set_scene_group(group, groups[group] + [name])
        self.rebuild()

    def remove_scene_group(self, name: str) -> None:
        """Delete a scene-nodes group through the guides."""
        self._apply(lambda: self.guides.remove_scene_group(name))

    def scene_nodes(self) -> list[tuple[str, str]]:
        """``[(group, node), ...]`` for source menus."""
        return [
            (group, node)
            for group, nodes in sorted(self.guides.scene_groups().items())
            for node in nodes
        ]

    def delete_selected(self) -> bool:
        """Disconnect selected wires and remove selected groups."""
        return self.graph.delete_selected()

    def select_key(self, key: Optional[str]) -> None:
        """Select only the node with ``key`` (None clears)."""
        self.graph.select_key(key)

    def select_keys(self, keys) -> None:
        """Select exactly the nodes with ``keys``."""
        self.graph.select_keys(keys)

    def set_grid(self, visible: bool) -> None:
        """Show or hide the background grid."""
        self.graph.show_grid = bool(visible)
        self.viewport().update()

    def set_snap(self, enabled: bool) -> None:
        """Snap dragged nodes to the grid or not."""
        self.graph.snap = bool(enabled)

    # ---------------------------------------------------------- navigation
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._fitted:
            QtCore.QTimer.singleShot(0, self.fit)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._navigated:
            self.fit()

    def focusNextPrevChild(self, next_child: bool) -> bool:  # noqa: N802
        return False  # keep Tab for the palette

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == QtCore.Qt.Key_Tab:
            self.palette_requested.emit()
        elif key == QtCore.Qt.Key_F:
            self.fit()
        elif key in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            self.delete_selected()
        elif key in (QtCore.Qt.Key_1, QtCore.Qt.Key_2, QtCore.Qt.Key_3):
            self.set_selected_mode(key - QtCore.Qt.Key_1)
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        self._navigated = True
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        origin = (
            event.position().toPoint() if hasattr(event, "position") else event.pos()
        )
        self.zoom_at(factor, origin)

    def pan_by(self, dx: int, dy: int) -> None:
        """Pan by viewport pixels (works anywhere on the infinite canvas)."""
        self.setTransformationAnchor(QtWidgets.QGraphicsView.NoAnchor)
        try:
            self.translate(dx / self.transform().m11(), dy / self.transform().m22())
        finally:
            self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

    def zoom_at(
        self,
        factor: float,
        origin: QtCore.QPoint,
        anchor: Optional[QtCore.QPointF] = None,
    ) -> None:
        """Scale by ``factor``, keeping scene ``anchor`` under viewport ``origin``."""
        anchor = self.mapToScene(origin) if anchor is None else anchor
        self.setTransformationAnchor(QtWidgets.QGraphicsView.NoAnchor)
        try:
            self.scale(factor, factor)
            shifted = self.mapToScene(origin)
            self.translate(shifted.x() - anchor.x(), shifted.y() - anchor.y())
        finally:
            self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        alt = bool(event.modifiers() & QtCore.Qt.AltModifier)
        ctrl = bool(event.modifiers() & QtCore.Qt.ControlModifier)
        if event.button() == QtCore.Qt.MiddleButton or (
            alt and event.button() == QtCore.Qt.LeftButton
        ):
            self._nav = "pan"
        elif alt and event.button() == QtCore.Qt.RightButton:
            self._nav = "zoom"
            self._zoom_origin = event.pos()
            self._zoom_anchor = self.mapToScene(event.pos())
        elif ctrl and event.button() == QtCore.Qt.LeftButton:
            # click = toggle the node under the cursor; drag = slice (decided on move)
            self._ctrl_press = event.pos()
            event.accept()
            return
        if self._nav:
            self._navigated = self._navigated or self._nav != "slice"
            self._nav_last = event.pos()
            self.setCursor(
                {
                    "pan": QtCore.Qt.ClosedHandCursor,
                    "zoom": QtCore.Qt.SizeHorCursor,
                    "slice": QtCore.Qt.CrossCursor,
                }[self._nav]
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def _begin_slice(self, origin: QtCore.QPoint) -> None:
        self._nav = "slice"
        self._nav_last = origin
        start = self.mapToScene(origin)
        self._slice_item = QtWidgets.QGraphicsLineItem(QtCore.QLineF(start, start))
        self._slice_item.setPen(
            QtGui.QPen(QtGui.QColor("#e05555"), 1.5, QtCore.Qt.DashLine)
        )
        self._slice_item.setZValue(5)
        self.graph.addItem(self._slice_item)
        self.setCursor(QtCore.Qt.CrossCursor)

    def toggle_node_at(self, pos: QtCore.QPoint) -> None:
        """Flip the selection of the node under viewport point ``pos``."""
        item = self.itemAt(pos)
        while item is not None and not isinstance(item, NodeItem):
            item = item.parentItem()
        if item is not None:
            item.setSelected(not item.isSelected())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._ctrl_press is not None:
            if (event.pos() - self._ctrl_press).manhattanLength() < 6:
                event.accept()
                return
            origin, self._ctrl_press = self._ctrl_press, None
            self._begin_slice(origin)
        if self._nav:
            delta = event.pos() - self._nav_last
            self._nav_last = event.pos()
            if self._nav == "pan":
                self.pan_by(delta.x(), delta.y())
            elif self._nav == "zoom":
                factor = 1.0 + (delta.x() - delta.y()) * 0.01
                factor = min(max(factor, 0.5), 2.0)
                self.zoom_at(factor, self._zoom_origin, self._zoom_anchor)
            elif self._slice_item is not None:
                line = self._slice_item.line()
                line.setP2(self.mapToScene(event.pos()))
                self._slice_item.setLine(line)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._ctrl_press is not None:
            self._ctrl_press = None
            self.toggle_node_at(event.pos())
            event.accept()
            return
        if self._nav:
            if self._nav == "slice" and self._slice_item is not None:
                line = self._slice_item.line()
                self.graph.removeItem(self._slice_item)
                self._slice_item = None
                if line.length() > 4:
                    self.graph.slice_wires(line)
            self._nav = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & QtCore.Qt.AltModifier:
            return
        item = self.itemAt(event.pos())
        while item is not None and not isinstance(item, (NodeItem, WireItem)):
            item = item.parentItem()
        if isinstance(item, NodeItem) and not item.external:
            if not item.isSelected():
                self.graph.select_key(item.key)
            self.node_menu_requested.emit(item.key, event.globalPos())
            return
        menu = QtWidgets.QMenu(self)
        if isinstance(item, WireItem):
            menu.addAction(
                "Disconnect", lambda key=item.target_key: self.disconnect_input(key)
            )
        elif isinstance(item, NodeItem):
            menu.addAction(
                "Sever all connections", lambda key=item.key: self.sever(key)
            )
            menu.addAction(
                "Remove scene nodes", lambda key=item.key: self.remove_scene_group(key)
            )
        else:
            menu.addAction("Add scene nodes", lambda: self.add_scene_group())
        menu.addSeparator()
        menu.addAction("Auto layout", self.auto_layout)
        menu.addAction("Fit view\tF", self.fit)
        menu.exec(event.globalPos())
