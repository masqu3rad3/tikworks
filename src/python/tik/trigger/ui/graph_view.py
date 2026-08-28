"""Node graph of module instances: input ports left, output ports right, wires between.

The graph edits the same connections the tree does (through ``Guides``):
drag from an output port to an input port to connect, drop on empty space to
type a scene node name, select a wire and press Delete to disconnect.
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
WIRE_PRIMARY = QtGui.QColor(theme.ACCENT)
WIRE_SECONDARY = QtGui.QColor("#8fa4c0")


class Port(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, node: "NodeItem", name: str, is_output: bool, primary: bool = False) -> None:
        super().__init__(-PORT_RADIUS, -PORT_RADIUS, PORT_RADIUS * 2, PORT_RADIUS * 2, node)
        self.node = node
        self.name = name
        self.is_output = is_output
        self.primary = primary
        self.setBrush(QtGui.QColor("#7b7b7b"))
        self.setPen(QtGui.QPen(QtGui.QColor("#111111"), 1))
        self.setZValue(3)
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"{node.key}.{name}")

    @property
    def key(self) -> str:
        return f"{self.node.key}.{self.name}"

    def set_connected(self, connected: bool) -> None:
        self.setBrush(QtGui.QColor(theme.ACCENT if connected else "#7b7b7b"))

    def hoverEnterEvent(self, event) -> None:  # noqa: N802
        self.setPen(QtGui.QPen(QtGui.QColor(theme.ACCENT), 1.5))

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802
        self.setPen(QtGui.QPen(QtGui.QColor("#111111"), 1))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.scene().start_wire(self, event.scenePos())
        event.accept()


class NodeItem(QtWidgets.QGraphicsItem):
    def __init__(self, key: str, title: str, subtitle: str, inputs: list, outputs: list, color: str,
                 external: bool = False, primary_input: Optional[str] = None) -> None:
        super().__init__()
        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.color = color
        self.external = external
        self.inputs: dict[str, Port] = {}
        self.outputs: dict[str, Port] = {}
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable | QtWidgets.QGraphicsItem.ItemIsSelectable
                      | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(2)
        rows = max(len(inputs), len(outputs), 1)
        self._height = HEADER + rows * ROW + 8
        for index, name in enumerate(inputs):
            port = Port(self, name, False, primary=(name == primary_input))
            port.setPos(0, HEADER + 6 + index * ROW + ROW / 2)
            self.inputs[name] = port
        for index, name in enumerate(outputs):
            port = Port(self, name, True)
            port.setPos(NODE_WIDTH, HEADER + 6 + index * ROW + ROW / 2)
            self.outputs[name] = port

    def boundingRect(self) -> QtCore.QRectF:  # noqa: N802
        return QtCore.QRectF(-PORT_RADIUS, 0, NODE_WIDTH + PORT_RADIUS * 2, self._height)

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
        path.addRoundedRect(header, 4, 4)
        path.addRect(QtCore.QRectF(0, HEADER / 2, NODE_WIDTH, HEADER / 2))
        painter.drawPath(path)
        font = painter.font()
        font.setBold(True)
        font.setPointSizeF(max(font.pointSizeF() - 1, 7))
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#c0c0c0" if self.external else "#1a1a1a"))
        painter.drawText(header.adjusted(8, 0, -4, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, self.title)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(header.adjusted(4, 0, -8, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight, self.subtitle)
        painter.setPen(QtGui.QColor("#bdbdbd"))
        for port in self.inputs.values():
            label = port.name + ("  ●" if port.primary else "")
            painter.drawText(QtCore.QRectF(12, port.pos().y() - ROW / 2, NODE_WIDTH - 24, ROW), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, label)
        for port in self.outputs.values():
            painter.drawText(QtCore.QRectF(12, port.pos().y() - ROW / 2, NODE_WIDTH - 24, ROW), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight, port.name)

    def itemChange(self, change, value):  # noqa: N802
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged and self.scene() is not None:
            self.scene().update_wires()
        return super().itemChange(change, value)


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
    connect_requested = QtCore.Signal(str, str)  # input key, source
    disconnect_requested = QtCore.Signal(str)  # input key
    node_selected = QtCore.Signal(str)  # instance key
    scene_node_requested = QtCore.Signal(str)  # input key (ask user for a scene node name)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setBackgroundBrush(QtGui.QColor("#151515"))
        self.nodes: dict[str, NodeItem] = {}
        self.wires: list[WireItem] = []
        self._drag_from: Optional[Port] = None
        self._drag_line: Optional[QtWidgets.QGraphicsPathItem] = None
        self.selectionChanged.connect(self._on_selection)

    # ------------------------------------------------------------ building
    def clear_graph(self) -> None:
        self.clear()
        self.nodes = {}
        self.wires = []

    def add_node(self, key, title, subtitle, inputs, outputs, color, external=False, primary_input=None, pos=None) -> NodeItem:
        node = NodeItem(key, title, subtitle, inputs, outputs, color, external, primary_input)
        if pos is not None:
            node.setPos(*pos)
        self.addItem(node)
        self.nodes[key] = node
        return node

    def add_wire(self, source_key: str, target_key: str, primary: bool) -> Optional[WireItem]:
        s_node, _dot, s_port = source_key.rpartition(".")
        t_node, _dot, t_port = target_key.rpartition(".")
        source = self.nodes.get(s_node, NodeItem("", "", "", [], [], "")).outputs.get(s_port)
        target = self.nodes.get(t_node, NodeItem("", "", "", [], [], "")).inputs.get(t_port)
        if source is None or target is None:
            return None
        wire = WireItem(source, target, primary)
        self.addItem(wire)
        self.wires.append(wire)
        source.set_connected(True)
        target.set_connected(True)
        return wire

    def update_wires(self) -> None:
        for wire in self.wires:
            wire.refresh()

    # ------------------------------------------------------ interactions
    def start_wire(self, port: Port, pos) -> None:
        self._drag_from = port
        self._drag_line = QtWidgets.QGraphicsPathItem()
        self._drag_line.setPen(QtGui.QPen(QtGui.QColor(theme.ACCENT), 1.5, QtCore.Qt.DashLine))
        self._drag_line.setZValue(4)
        self.addItem(self._drag_line)
        self._update_drag(pos)

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

    def _port_at(self, pos) -> Optional[Port]:
        for item in self.items(pos):
            if isinstance(item, Port):
                return item
        return None

    def finish_wire(self, port: Optional[Port]) -> None:
        origin, self._drag_from = self._drag_from, None
        if self._drag_line is not None:
            self.removeItem(self._drag_line)
            self._drag_line = None
        if origin is None:
            return
        if port is None:
            if not origin.is_output:
                self.scene_node_requested.emit(origin.key)
            return
        if origin.is_output and not port.is_output:
            self.connect_requested.emit(port.key, origin.key)
        elif not origin.is_output and port.is_output:
            self.connect_requested.emit(origin.key, port.key)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            for item in self.selectedItems():
                if isinstance(item, WireItem):
                    self.disconnect_requested.emit(item.target_key)
            return
        super().keyPressEvent(event)

    def _on_selection(self) -> None:
        for item in self.selectedItems():
            if isinstance(item, NodeItem) and not item.external:
                self.node_selected.emit(item.key)
                return

    def select_key(self, key: Optional[str]) -> None:
        self.blockSignals(True)
        try:
            for item in self.nodes.values():
                item.setSelected(item.key == key)
        finally:
            self.blockSignals(False)


class GraphView(QtWidgets.QGraphicsView):
    """Renders a ``Guides`` handler's instances and connections; edits go back through it."""

    selection_changed = QtCore.Signal(str)
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
        self._positions: dict[str, tuple] = {}
        self.graph.connect_requested.connect(self.connect_input)
        self.graph.disconnect_requested.connect(self.disconnect_input)
        self.graph.node_selected.connect(self.selection_changed)
        self.graph.scene_node_requested.connect(self._ask_scene_node)

    # ------------------------------------------------------------ building
    def rebuild(self) -> None:
        for key, node in self.graph.nodes.items():
            self._positions[key] = (node.pos().x(), node.pos().y())
        self.graph.clear_graph()
        handles = self.guides.instances()
        by_key = {handle.key: handle for handle in handles}
        # external sources
        externals: dict[str, set] = {}
        for handle in handles:
            for source in handle.inputs.values():
                key, output = split_source(source)
                if key is None or key not in by_key:
                    externals.setdefault(source, set()).add("world")
        depth = self._depths(handles, by_key)
        columns: dict[int, int] = {}
        for name in sorted(externals):
            pos = self._positions.get(name) or (20, 40 + columns.get(0, 0) * 90)
            columns[0] = columns.get(0, 0) + 1
            node = self.graph.add_node(name, name, "scene", [], ["node"], "", external=True, pos=pos)
            exists = self.guides.backend.scene_node(name) is not None if hasattr(self.guides.backend, "scene_node") else True
            node.subtitle = "scene ✓" if exists else "scene ✗ missing"
        for handle in sorted(handles, key=lambda item: (depth.get(item.key, 1), item.key)):
            module_cls = handle.module_class
            column = depth.get(handle.key, 1)
            pos = self._positions.get(handle.key) or (20 + column * (NODE_WIDTH + 90), 40 + columns.get(column, 0) * 110)
            columns[column] = columns.get(column, 0) + 1
            primary = module_cls.primary_input()
            self.graph.add_node(
                handle.key, handle.key, module_cls.display_label(), module_cls.input_names(), list(module_cls.outputs),
                theme.SIDE.get(handle.side.value, theme.SIDE["C"]), primary_input=primary.name if primary else None, pos=pos,
            )
        for handle in handles:
            primary = handle.module_class.primary_input()
            for input_name, source in handle.inputs.items():
                key, output = split_source(source)
                source_key = source if key is None or key not in by_key else f"{key}.{output}"
                if key is None or key not in by_key:
                    source_key = f"{source}.node"
                self.graph.add_wire(source_key, f"{handle.key}.{input_name}", primary is not None and input_name == primary.name)
        self.graph.setSceneRect(self.graph.itemsBoundingRect().adjusted(-40, -40, 80, 80))

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
    def connect_input(self, input_key: str, source: str) -> None:
        source = source[:-5] if source.endswith(".node") else source
        try:
            self.guides.connect(input_key, source)
        except TriggerError as error:
            if self.events is not None:
                self.events.log(str(error), level="warning")
            return
        self.rebuild()
        self.edited.emit()

    def disconnect_input(self, input_key: str) -> None:
        try:
            self.guides.disconnect(input_key)
        except TriggerError as error:
            if self.events is not None:
                self.events.log(str(error), level="warning")
            return
        self.rebuild()
        self.edited.emit()

    def _ask_scene_node(self, input_key: str) -> None:
        name, ok = QtWidgets.QInputDialog.getText(self, "Connect to scene node", f"Scene node for {input_key}:")
        if ok and name.strip():
            self.connect_input(input_key, name.strip())

    def select_key(self, key: Optional[str]) -> None:
        self.graph.select_key(key)

    def wheelEvent(self, event) -> None:  # noqa: N802
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
