"""Node graph of module instances: input ports left, output ports right, wires between.

The graph edits the same connections the tree does (through ``Guides``), and
stores its own state (node positions, collapse modes, scene-node groups) in
``Guides.layout`` so it lands in the ``.trg`` and undoes with Maya.

* drag from an output port to an input port to connect;
* drag a connected input port away to unplug it (drop on another input to
  re-plug, drop on empty space to disconnect);
* select wires and press Delete / Backspace to disconnect;
* Ctrl + left drag draws a slice line: every wire it crosses is disconnected;
* 1 / 2 / 3 (or the ≡ glyph in a node header) set the collapse mode:
  1 = header only, 2 = connected plugs, 3 = everything;
* **Scene Nodes** groups (dashed) expose arbitrary Maya nodes as outputs.

Navigation follows Maya: Alt + middle drag pans, Alt + right drag zooms
around the point you pressed, the wheel zooms under the pointer, F fits.
"""

from __future__ import annotations

from typing import Optional

from tik.shared.ui import theme
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.core.builder import split_source
from tik.trigger.core.exceptions import TriggerError

NODE_WIDTH = 150
ROW = 18
HEADER = 22
PORT_RADIUS = 5
GLYPH_WIDTH = 16
WIRE_PRIMARY = QtGui.QColor(theme.ACCENT)
WIRE_SECONDARY = QtGui.QColor("#8fa4c0")
WORLD = 100000.0  # scene rect half-size: effectively infinite canvas so panning is never clamped
GRID = 20
MODE_MINIMAL, MODE_CONNECTED, MODE_FULL = 0, 1, 2
COLUMN_GAP = 60
ROW_GAP = 24


class Port(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, node: "NodeItem", name: str, is_output: bool, primary: bool = False) -> None:
        super().__init__(-PORT_RADIUS, -PORT_RADIUS, PORT_RADIUS * 2, PORT_RADIUS * 2, node)
        self.node = node
        self.name = name
        self.is_output = is_output
        self.primary = primary
        self.connected = False
        self.setBrush(QtGui.QColor("#7b7b7b"))
        self.setPen(QtGui.QPen(QtGui.QColor("#111111"), 1))
        self.setZValue(3)
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"{node.key}.{name}")

    @property
    def key(self) -> str:
        return f"{self.node.key}.{self.name}"

    def set_connected(self, connected: bool) -> None:
        self.connected = connected
        self.setBrush(QtGui.QColor(theme.ACCENT if connected else "#7b7b7b"))

    def hoverEnterEvent(self, event) -> None:  # noqa: N802
        self.setPen(QtGui.QPen(QtGui.QColor(theme.ACCENT), 1.5))

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802
        self.setPen(QtGui.QPen(QtGui.QColor("#111111"), 1))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != QtCore.Qt.LeftButton or event.modifiers() & QtCore.Qt.ControlModifier:
            event.ignore()
            return
        scene = self.scene()
        wire = scene.wire_for_input(self) if not self.is_output else None
        if wire is not None:
            scene.pick_up_wire(wire, event.scenePos())  # unplug from the input end
        else:
            scene.start_wire(self, event.scenePos())
        event.accept()


class NodeItem(QtWidgets.QGraphicsItem):
    def __init__(self, key: str, title: str, subtitle: str, inputs: list, outputs: list, color: str,
                 external: bool = False, primary_input: Optional[str] = None, mode: int = MODE_FULL) -> None:
        super().__init__()
        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.color = color
        self.external = external
        self.mode = mode
        self.inputs: dict[str, Port] = {}
        self.outputs: dict[str, Port] = {}
        self._height = HEADER + 8
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable | QtWidgets.QGraphicsItem.ItemIsSelectable
                      | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(2)
        for name in inputs:
            self.inputs[name] = Port(self, name, False, primary=(name == primary_input))
        for name in outputs:
            self.outputs[name] = Port(self, name, True)
        self.relayout()

    # --------------------------------------------------------------- layout
    def visible_ports(self) -> tuple[list[Port], list[Port]]:
        if self.mode == MODE_MINIMAL:
            return [], []
        if self.mode == MODE_CONNECTED:
            return ([p for p in self.inputs.values() if p.connected], [p for p in self.outputs.values() if p.connected])
        return list(self.inputs.values()), list(self.outputs.values())

    def relayout(self) -> None:
        """Place ports for the current mode; hidden ports sit on the header edge so wires still reach them."""
        self.prepareGeometryChange()
        ins, outs = self.visible_ports()
        rows = max(len(ins), len(outs))
        self._height = HEADER + (rows * ROW + 8 if rows else 6)
        for port in self.inputs.values():
            port.setVisible(port in ins)
            port.setPos(0, HEADER / 2)
        for port in self.outputs.values():
            port.setVisible(port in outs)
            port.setPos(NODE_WIDTH, HEADER / 2)
        for index, port in enumerate(ins):
            port.setPos(0, HEADER + 6 + index * ROW + ROW / 2)
        for index, port in enumerate(outs):
            port.setPos(NODE_WIDTH, HEADER + 6 + index * ROW + ROW / 2)
        self.update()
        if self.scene() is not None:
            self.scene().update_wires()

    def set_mode(self, mode: int) -> None:
        self.mode = max(MODE_MINIMAL, min(MODE_FULL, int(mode)))
        self.relayout()

    def glyph_rect(self) -> QtCore.QRectF:
        return QtCore.QRectF(NODE_WIDTH - GLYPH_WIDTH - 4, 0, GLYPH_WIDTH + 4, HEADER)

    def boundingRect(self) -> QtCore.QRectF:  # noqa: N802
        return QtCore.QRectF(-PORT_RADIUS, 0, NODE_WIDTH + PORT_RADIUS * 2, self._height)

    # ---------------------------------------------------------------- paint
    def paint(self, painter, option, widget=None) -> None:
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        body = QtCore.QRectF(0, 0, NODE_WIDTH, self._height)
        pen = QtGui.QPen(QtGui.QColor(theme.ACCENT if self.isSelected() else "#3a3a3a"), 1.2)
        if self.external:
            pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QtGui.QColor("#262626"))
        painter.drawRoundedRect(body, 4, 4)
        header = QtCore.QRectF(0, 0, NODE_WIDTH, HEADER)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor("#3a4048" if self.external else self.color))
        path = QtGui.QPainterPath()
        path.setFillRule(QtCore.Qt.WindingFill)
        path.addRoundedRect(header, 4, 4)
        if self._height > HEADER + 6:
            path.addRect(QtCore.QRectF(0, HEADER / 2, NODE_WIDTH, HEADER / 2))
        painter.drawPath(path)
        ink = QtGui.QColor("#c0c0c0" if self.external else "#1a1a1a")
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(ink)
        metrics = QtGui.QFontMetricsF(font)
        baseline = HEADER / 2 + metrics.capHeight() / 2
        title = metrics.elidedText(self.title, QtCore.Qt.ElideRight, NODE_WIDTH - GLYPH_WIDTH - 60)
        painter.drawText(QtCore.QPointF(8, baseline), title)
        font.setBold(False)
        painter.setFont(font)
        metrics = QtGui.QFontMetricsF(font)
        painter.drawText(QtCore.QPointF(NODE_WIDTH - GLYPH_WIDTH - 10 - metrics.horizontalAdvance(self.subtitle), baseline), self.subtitle)
        # collapse glyph: 1..3 lines (Maya node editor style)
        painter.setPen(QtGui.QPen(ink, 1.2))
        x0 = NODE_WIDTH - GLYPH_WIDTH - 2
        for line in range(self.mode + 1):
            y = HEADER / 2 - 4 + line * 4
            painter.drawLine(QtCore.QPointF(x0, y), QtCore.QPointF(x0 + GLYPH_WIDTH - 4, y))
        painter.setPen(QtGui.QColor("#bdbdbd"))
        ins, outs = self.visible_ports()
        for port in ins:
            label = port.name + ("  ●" if port.primary else "")
            painter.drawText(QtCore.QRectF(12, port.pos().y() - ROW / 2, NODE_WIDTH - 24, ROW), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, label)
        for port in outs:
            painter.drawText(QtCore.QRectF(12, port.pos().y() - ROW / 2, NODE_WIDTH - 24, ROW), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight, port.name)

    # ------------------------------------------------------------- events
    def itemChange(self, change, value):  # noqa: N802
        scene = self.scene()
        if change == QtWidgets.QGraphicsItem.ItemPositionChange and scene is not None and getattr(scene, "snap", False):
            return QtCore.QPointF(round(value.x() / GRID) * GRID, round(value.y() / GRID) * GRID)
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged and scene is not None:
            scene.update_wires()
            scene.moved.add(self.key)
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton and self.glyph_rect().contains(event.pos()):
            self.scene().mode_change_requested.emit(self.key, (self.mode + 1) % 3)
            event.accept()
            return
        super().mousePressEvent(event)


class WireItem(QtWidgets.QGraphicsPathItem):
    def __init__(self, source: Port, target: Port, primary: bool) -> None:
        super().__init__()
        self.source = source
        self.target = target
        self.primary = primary
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable)
        self.setZValue(1)
        self.refresh()

    @property
    def target_key(self) -> str:
        return self.target.key

    @property
    def source_key(self) -> str:
        return self.source.key

    def shape(self) -> QtGui.QPainterPath:  # generous hit area so wires are easy to pick
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(10)
        return stroker.createStroke(self.path())

    def refresh(self) -> None:
        start = self.source.scenePos()
        end = self.target.scenePos()
        path = QtGui.QPainterPath(start)
        dx = max(abs(end.x() - start.x()) * 0.5, 40)
        path.cubicTo(start.x() + dx, start.y(), end.x() - dx, end.y(), end.x(), end.y())
        self.setPath(path)
        color = WIRE_PRIMARY if self.primary else WIRE_SECONDARY
        pen = QtGui.QPen(QtGui.QColor(theme.TEXT_BRIGHT) if self.isSelected() else color, 2 if self.isSelected() else 1.6)
        if self.source.node.external:
            pen.setStyle(QtCore.Qt.DashLine)
        self.setPen(pen)

    def paint(self, painter, option, widget=None) -> None:
        self.refresh()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(self.pen())
        painter.drawPath(self.path())


class GraphScene(QtWidgets.QGraphicsScene):
    connect_requested = QtCore.Signal(str, str)  # input key, source key (node.port)
    disconnect_requested = QtCore.Signal(str)  # input key
    remove_group_requested = QtCore.Signal(str)  # scene-nodes group name
    node_selected = QtCore.Signal(str)  # instance key
    external_selected = QtCore.Signal(str)  # scene-nodes group name
    mode_change_requested = QtCore.Signal(str, int)  # node key, mode
    nodes_moved = QtCore.Signal()  # a drag finished and at least one node moved

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setBackgroundBrush(QtGui.QColor("#151515"))
        self.nodes: dict[str, NodeItem] = {}
        self.wires: list[WireItem] = []
        self.moved: set[str] = set()
        self.show_grid = True
        self.snap = True
        self._drag_from: Optional[Port] = None
        self._drag_line: Optional[QtWidgets.QGraphicsPathItem] = None
        self._detached: Optional[str] = None  # input key of a picked-up wire
        self.selectionChanged.connect(self._on_selection)

    # ------------------------------------------------------------ building
    def clear_graph(self) -> None:
        # clearing selected items emits selectionChanged; nobody must react mid-rebuild
        self.blockSignals(True)
        try:
            self.clear()
        finally:
            self.blockSignals(False)
        self.nodes = {}
        self.wires = []
        self.moved = set()
        self._drag_from = None
        self._drag_line = None
        self._detached = None

    def add_node(self, key, title, subtitle, inputs, outputs, color, external=False, primary_input=None, pos=None, mode=MODE_FULL) -> NodeItem:
        node = NodeItem(key, title, subtitle, inputs, outputs, color, external, primary_input, mode)
        if pos is not None:
            node.setPos(*pos)
        self.addItem(node)
        self.nodes[key] = node
        self.moved.discard(key)
        return node

    def add_wire(self, source_key: str, target_key: str, primary: bool) -> Optional[WireItem]:
        s_node, _dot, s_port = source_key.rpartition(".")
        t_node, _dot, t_port = target_key.rpartition(".")
        source = self.nodes[s_node].outputs.get(s_port) if s_node in self.nodes else None
        target = self.nodes[t_node].inputs.get(t_port) if t_node in self.nodes else None
        if source is None or target is None:
            return None
        wire = WireItem(source, target, primary)
        self.addItem(wire)
        self.wires.append(wire)
        source.set_connected(True)
        target.set_connected(True)
        return wire

    def finish_build(self) -> None:
        """Apply collapse modes now that connections are known."""
        for node in self.nodes.values():
            node.relayout()
        self.update_wires()
        self.moved = set()

    def wire_for_input(self, port: Port) -> Optional[WireItem]:
        return next((wire for wire in self.wires if wire.target is port), None)

    def update_wires(self) -> None:
        for wire in self.wires:
            wire.refresh()

    # ---------------------------------------------------------------- grid
    def drawBackground(self, painter, rect) -> None:  # noqa: N802
        super().drawBackground(painter, rect)
        if not self.show_grid:
            return
        painter.setPen(QtGui.QPen(QtGui.QColor("#202020"), 0))
        left = int(rect.left()) - int(rect.left()) % GRID
        top = int(rect.top()) - int(rect.top()) % GRID
        lines = []
        x = left
        while x < rect.right():
            lines.append(QtCore.QLineF(x, rect.top(), x, rect.bottom()))
            x += GRID
        y = top
        while y < rect.bottom():
            lines.append(QtCore.QLineF(rect.left(), y, rect.right(), y))
            y += GRID
        painter.drawLines(lines)
        painter.setPen(QtGui.QPen(QtGui.QColor("#2a2a2a"), 0))
        painter.drawLines([QtCore.QLineF(0, rect.top(), 0, rect.bottom()), QtCore.QLineF(rect.left(), 0, rect.right(), 0)])

    # ------------------------------------------------------ interactions
    def start_wire(self, port: Port, pos) -> None:
        self._drag_from = port
        self._drag_line = QtWidgets.QGraphicsPathItem()
        self._drag_line.setPen(QtGui.QPen(QtGui.QColor(theme.ACCENT), 1.5, QtCore.Qt.DashLine))
        self._drag_line.setZValue(4)
        self.addItem(self._drag_line)
        self._update_drag(pos)

    def pick_up_wire(self, wire: WireItem, pos) -> None:
        """Unplug ``wire`` from its input and keep dragging it from the source."""
        self._detached = wire.target_key
        wire.target.set_connected(False)
        self.wires.remove(wire)
        self.removeItem(wire)
        self.start_wire(wire.source, pos)

    def _update_drag(self, pos) -> None:
        if self._drag_from is None or self._drag_line is None:
            return
        start = self._drag_from.scenePos()
        path = QtGui.QPainterPath(start)
        path.lineTo(pos)
        self._drag_line.setPath(path)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_from is not None:
            self._update_drag(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_from is not None:
            port = self._port_at(event.scenePos())
            self.finish_wire(port)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self.moved:
            self.nodes_moved.emit()

    def _port_at(self, pos) -> Optional[Port]:
        for item in self.items(pos):
            if isinstance(item, Port):
                return item
        return None

    def finish_wire(self, port: Optional[Port]) -> None:
        origin, self._drag_from = self._drag_from, None
        detached, self._detached = self._detached, None
        if self._drag_line is not None:
            self.removeItem(self._drag_line)
            self._drag_line = None
        if origin is None:
            return
        target = None
        if port is not None:
            if origin.is_output and not port.is_output:
                target = (port.key, origin.key)
            elif not origin.is_output and port.is_output:
                target = (origin.key, port.key)
        if detached is not None and (target is None or target[0] != detached):
            self.disconnect_requested.emit(detached)
        if target is not None:
            self.connect_requested.emit(*target)
        elif detached is None:
            self.update()

    def slice_wires(self, line: QtCore.QLineF) -> list[str]:
        """Disconnect every wire crossing ``line``; returns the input keys cut."""
        blade = QtGui.QPainterPath(line.p1())
        blade.lineTo(line.p2())
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(2)
        blade = stroker.createStroke(blade)
        cut = [wire.target_key for wire in list(self.wires) if wire.path().intersects(blade)]
        for key in cut:
            self.disconnect_requested.emit(key)
        return cut

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            self.delete_selected()
            event.accept()
            return
        super().keyPressEvent(event)

    def delete_selected(self) -> bool:
        """Disconnect selected wires and remove selected scene-node groups. True when anything was selected."""
        wires = [item for item in self.selectedItems() if isinstance(item, WireItem)]
        externals = [item for item in self.selectedItems() if isinstance(item, NodeItem) and item.external]
        for wire in wires:
            self.disconnect_requested.emit(wire.target_key)
        for node in externals:
            self.remove_group_requested.emit(node.key)
        return bool(wires or externals)

    def selected_nodes(self) -> list[NodeItem]:
        return [item for item in self.selectedItems() if isinstance(item, NodeItem)]

    def _on_selection(self) -> None:
        for item in self.selectedItems():
            if isinstance(item, NodeItem):
                (self.external_selected if item.external else self.node_selected).emit(item.key)
                return

    def select_key(self, key: Optional[str]) -> None:
        self.select_keys([key] if key else [])

    def select_keys(self, keys) -> None:
        wanted = set(keys)
        self.blockSignals(True)
        try:
            for item in self.nodes.values():
                item.setSelected(item.key in wanted)
        finally:
            self.blockSignals(False)


class GraphView(QtWidgets.QGraphicsView):
    """Renders a ``Guides`` handler's instances and connections; edits go back through it."""

    selection_changed = QtCore.Signal(str)
    external_selection_changed = QtCore.Signal(str)
    node_menu_requested = QtCore.Signal(str, object)  # module key, global QPoint
    palette_requested = QtCore.Signal()
    edited = QtCore.Signal()

    def __init__(self, guides, parent=None, events=None) -> None:
        super().__init__(parent)
        self.setObjectName("GraphView")
        self.guides = guides
        self.events = events
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
        self._ctrl_press: Optional[QtCore.QPoint] = None  # Ctrl+LMB pressed, not yet a drag
        self.graph.connect_requested.connect(self.connect_input)
        self.graph.disconnect_requested.connect(self.disconnect_input)
        self.graph.remove_group_requested.connect(self.remove_scene_group)
        self.graph.node_selected.connect(self.selection_changed)
        self.graph.external_selected.connect(self.external_selection_changed)
        self.graph.mode_change_requested.connect(self.set_mode)
        self.graph.nodes_moved.connect(self.save_positions)

    # ------------------------------------------------------------ building
    def rebuild(self) -> None:
        layout = self.guides.layout
        positions = dict(layout.get("positions", {}))
        collapse = dict(layout.get("collapse", {}))
        groups = {name: list(nodes) for name, nodes in layout.get("scene_nodes", {}).items()}
        self.graph.clear_graph()
        handles = self.guides.instances()
        by_key = {handle.key: handle for handle in handles}
        # scene sources nobody grouped yet -> implicit "scene" group (shown, not written)
        grouped = {node for nodes in groups.values() for node in nodes}
        for handle in handles:
            for source in handle.inputs.values():
                key, _output = split_source(source)
                if (key is None or key not in by_key) and source not in grouped:
                    groups.setdefault("scene", []).append(source)
                    grouped.add(source)
        depth = self._depths(handles, by_key)
        auto = self._auto_positions(handles, groups, depth)
        placed: list[QtCore.QRectF] = []  # rects of nodes with a stored position; new nodes avoid them

        def rect_at(pos, height):
            return QtCore.QRectF(pos[0], pos[1], NODE_WIDTH + PORT_RADIUS * 2, height)

        def free_pos(key, height):
            stored = positions.get(key)
            if stored:
                placed.append(rect_at(stored, height))
                return stored
            pos = list(auto[key])
            candidate = rect_at(pos, height)
            for _ in range(200):
                hit = next((r for r in placed if r.intersects(candidate.adjusted(-8, -8, 8, 8))), None)
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
            node = self.graph.add_node(name, name, "scene", [], groups[name], "", external=True, pos=pos, mode=collapse.get(name, MODE_FULL))
            exists = getattr(self.guides.backend, "scene_node", lambda _n: True)
            missing = [item for item in groups[name] if exists(item) is None]
            node.subtitle = "scene ✗ missing" if missing else "scene ✓"
        for handle in sorted(handles, key=lambda item: (depth.get(item.key, 1), item.key)):
            module_cls = handle.module_class
            rows = max(len(module_cls.inputs), len(handle.outputs), 1)
            pos = free_pos(handle.key, HEADER + rows * ROW + 8)
            primary = module_cls.primary_input()
            self.graph.add_node(
                handle.key, handle.key, module_cls.display_label(), module_cls.input_names(), list(handle.outputs),
                theme.SIDE.get(handle.side.value, theme.SIDE["C"]), primary_input=primary.name if primary else None, pos=pos,
                mode=collapse.get(handle.key, MODE_FULL),
            )
        node_group = {node: name for name, nodes in groups.items() for node in nodes}
        for handle in handles:
            primary = handle.module_class.primary_input()
            for input_name, source in handle.inputs.items():
                key, output = split_source(source)
                if key is not None and key in by_key:
                    source_key = f"{key}.{output}"
                else:
                    source_key = f"{node_group.get(source, 'scene')}.{source}"
                self.graph.add_wire(source_key, f"{handle.key}.{input_name}", primary is not None and input_name == primary.name)
        self.graph.finish_build()
        if not self._fitted:
            self.fit()

    def _auto_positions(self, handles, groups, depth) -> dict[str, tuple]:
        """Column per dependency depth, nodes stacked by their real height."""
        columns: dict[int, float] = {}
        result: dict[str, tuple] = {}

        def place(key, column, height):
            y = columns.get(column, 0.0)
            result[key] = (20 + column * (NODE_WIDTH + COLUMN_GAP), 30 + y)
            columns[column] = y + height + ROW_GAP

        for name in sorted(groups):
            place(name, 0, HEADER + len(groups[name]) * ROW + 8)
        for handle in sorted(handles, key=lambda item: (depth.get(item.key, 1), item.key)):
            rows = max(len(handle.module_class.inputs), len(handle.outputs), 1)
            place(handle.key, depth.get(handle.key, 1), HEADER + rows * ROW + 8)
        return result

    def auto_layout(self) -> None:
        """Lay every node out by dependency depth and store it (one Maya undo step)."""
        handles = self.guides.instances()
        by_key = {handle.key: handle for handle in handles}
        groups = self.guides.scene_groups()
        depth = self._depths(handles, by_key)
        positions = {key: [x, y] for key, (x, y) in self._auto_positions(handles, groups, depth).items()}
        self.guides.update_layout(positions=positions)
        self.rebuild()
        self.fit()

    def save_positions(self) -> None:
        """Persist node positions after a drag (undoable in Maya)."""
        positions = self.guides.layout.get("positions", {})
        for key, node in self.graph.nodes.items():
            positions[key] = [node.pos().x(), node.pos().y()]
        self.guides.update_layout(positions=positions)
        self.graph.moved = set()

    def set_mode(self, key: str, mode: int) -> None:
        node = self.graph.nodes.get(key)
        if node is None:
            return
        node.set_mode(mode)
        collapse = self.guides.layout.get("collapse", {})
        collapse[key] = node.mode
        self.guides.update_layout(collapse=collapse)

    def set_selected_mode(self, mode: int) -> None:
        for node in self.graph.selected_nodes():
            self.set_mode(node.key, mode)

    def fit(self) -> None:
        """Show the whole graph, never zoomed in past 1:1."""
        rect = self.graph.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        view = self.viewport().rect()
        if rect.isEmpty() or view.width() < 60 or view.height() < 60:
            return
        self.resetTransform()
        scale = min(1.0, (view.width() - 20) / max(rect.width(), 1), (view.height() - 20) / max(rect.height(), 1))
        self.scale(max(scale, 0.3), max(scale, 0.3))
        self.centerOn(rect.center())
        self._fitted = True

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
        """``group.node`` on a scene-nodes group -> plain scene node name; module sources unchanged."""
        node_key, _dot, port = source_key.rpartition(".")
        node = self.graph.nodes.get(node_key)
        if node is not None and node.external:
            return port
        return source_key

    def connect_input(self, input_key: str, source_key: str) -> None:
        source = self.resolve_source(source_key)
        self._apply(lambda: self.guides.connect(input_key, source))

    def disconnect_input(self, input_key: str) -> None:
        self._apply(lambda: self.guides.disconnect(input_key))

    def sever(self, key: str) -> None:
        """Drop every connection into or out of the node ``key`` (module or scene-nodes group)."""
        group_nodes = set(self.guides.scene_groups().get(key, []))

        def run():
            for item in self.guides.connections():
                source_key, _output = split_source(item["source"])
                if item["input"].startswith(f"{key}.") or source_key == key or item["source"] in group_nodes:
                    self.guides.disconnect(item["input"])

        self._apply(run)

    # ----------------------------------------------------- scene groups
    def add_scene_group(self, name: str = "", nodes: Optional[list] = None) -> str:
        name = self.guides.add_scene_group(name, nodes)
        self.rebuild()
        self.graph.select_key(name)
        return name

    def add_scene_node(self, name: str, group: str = "scene") -> None:
        """Convenience: put scene node ``name`` into ``group`` (created when missing)."""
        groups = self.guides.scene_groups()
        if group not in groups:
            self.guides.add_scene_group(group, [name])
        elif name not in groups[group]:
            self.guides.set_scene_group(group, groups[group] + [name])
        self.rebuild()

    def remove_scene_group(self, name: str) -> None:
        self._apply(lambda: self.guides.remove_scene_group(name))

    def scene_nodes(self) -> list[tuple[str, str]]:
        """``[(group, node), ...]`` for source menus."""
        return [(group, node) for group, nodes in sorted(self.guides.scene_groups().items()) for node in nodes]

    def delete_selected(self) -> bool:
        return self.graph.delete_selected()

    def select_key(self, key: Optional[str]) -> None:
        self.graph.select_key(key)

    def select_keys(self, keys) -> None:
        self.graph.select_keys(keys)

    def set_grid(self, visible: bool) -> None:
        self.graph.show_grid = bool(visible)
        self.viewport().update()

    def set_snap(self, enabled: bool) -> None:
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
        origin = event.position().toPoint() if hasattr(event, "position") else event.pos()
        self.zoom_at(factor, origin)

    def pan_by(self, dx: int, dy: int) -> None:
        """Pan by viewport pixels (works anywhere on the infinite canvas)."""
        self.setTransformationAnchor(QtWidgets.QGraphicsView.NoAnchor)
        try:
            self.translate(dx / self.transform().m11(), dy / self.transform().m22())
        finally:
            self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

    def zoom_at(self, factor: float, origin: QtCore.QPoint, anchor: Optional[QtCore.QPointF] = None) -> None:
        """Scale by ``factor`` keeping scene point ``anchor`` under viewport point ``origin``."""
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
        if event.button() == QtCore.Qt.MiddleButton or (alt and event.button() == QtCore.Qt.LeftButton):
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
            self.setCursor({"pan": QtCore.Qt.ClosedHandCursor, "zoom": QtCore.Qt.SizeHorCursor, "slice": QtCore.Qt.CrossCursor}[self._nav])
            event.accept()
            return
        super().mousePressEvent(event)

    def _begin_slice(self, origin: QtCore.QPoint) -> None:
        self._nav = "slice"
        self._nav_last = origin
        start = self.mapToScene(origin)
        self._slice_item = QtWidgets.QGraphicsLineItem(QtCore.QLineF(start, start))
        self._slice_item.setPen(QtGui.QPen(QtGui.QColor("#e05555"), 1.5, QtCore.Qt.DashLine))
        self._slice_item.setZValue(5)
        self.graph.addItem(self._slice_item)
        self.setCursor(QtCore.Qt.CrossCursor)

    def toggle_node_at(self, pos: QtCore.QPoint) -> None:
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
            menu.addAction("Disconnect", lambda key=item.target_key: self.disconnect_input(key))
        elif isinstance(item, NodeItem):
            menu.addAction("Sever all connections", lambda key=item.key: self.sever(key))
            menu.addAction("Remove scene nodes", lambda key=item.key: self.remove_scene_group(key))
        else:
            menu.addAction("Add scene nodes", lambda: self.add_scene_group())
        menu.addSeparator()
        menu.addAction("Auto layout", self.auto_layout)
        menu.addAction("Fit view\tF", self.fit)
        menu.exec(event.globalPos())
