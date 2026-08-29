"""Node graph of module instances: input ports left, output ports right, wires between.

The graph edits the same connections the tree does (through ``Guides``):

* drag from an output port to an input port to connect;
* drag a connected input port away to unplug it (drop on another input to
  re-plug, drop on empty space to disconnect);
* select wires and press Delete / Backspace to disconnect;
* shake a node to sever all of its connections (Houdini style);
* right-click the background to add a scene node (an arbitrary Maya node
  modules can connect to); Delete removes a selected scene node again.

Navigation follows Maya: Alt + middle drag pans, Alt + right drag zooms,
the wheel zooms, F fits the graph.
"""

from __future__ import annotations

import time
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
SHAKE_REVERSALS = 4  # direction changes needed to sever
SHAKE_WINDOW = 0.6  # seconds


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
        if event.button() != QtCore.Qt.LeftButton:
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
                 external: bool = False, primary_input: Optional[str] = None) -> None:
        super().__init__()
        self.key = key
        self.title = title
        self.subtitle = subtitle
        self.color = color
        self.external = external
        self.inputs: dict[str, Port] = {}
        self.outputs: dict[str, Port] = {}
        self._shake: list[tuple[float, float]] = []  # (time, x)
        self._shake_dir = 0
        self._shake_turns = 0
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
        path.setFillRule(QtCore.Qt.WindingFill)
        path.addRoundedRect(header, 4, 4)
        path.addRect(QtCore.QRectF(0, HEADER / 2, NODE_WIDTH, HEADER / 2))
        painter.drawPath(path)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#c0c0c0" if self.external else "#1a1a1a"))
        metrics = QtGui.QFontMetricsF(font)
        baseline = HEADER / 2 + metrics.capHeight() / 2
        painter.drawText(QtCore.QPointF(8, baseline), self.title)
        font.setBold(False)
        painter.setFont(font)
        metrics = QtGui.QFontMetricsF(font)
        painter.drawText(QtCore.QPointF(NODE_WIDTH - 8 - metrics.horizontalAdvance(self.subtitle), baseline), self.subtitle)
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

    # ------------------------------------------------------------- shake
    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._shake = []
        self._shake_dir = 0
        self._shake_turns = 0
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        super().mouseMoveEvent(event)
        self.track_shake(event.scenePos().x())

    def track_shake(self, x: float, now: Optional[float] = None) -> bool:
        """Feed a horizontal position; returns True (once) when a shake is detected."""
        now = time.monotonic() if now is None else now
        self._shake = [(t, px) for t, px in self._shake if now - t <= SHAKE_WINDOW]
        if self._shake:
            delta = x - self._shake[-1][1]
            direction = (delta > 0) - (delta < 0)
            if direction and self._shake_dir and direction != self._shake_dir:
                self._shake_turns += 1
            if direction:
                self._shake_dir = direction
        self._shake.append((now, x))
        if self._shake_turns >= SHAKE_REVERSALS and self.scene() is not None:
            self._shake_turns = 0
            self._shake = []
            self.scene().sever_requested.emit(self.key)
            return True
        return False


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
    connect_requested = QtCore.Signal(str, str)  # input key, source
    disconnect_requested = QtCore.Signal(str)  # input key
    sever_requested = QtCore.Signal(str)  # node key: drop every connection touching it
    remove_external_requested = QtCore.Signal(str)  # scene node name
    node_selected = QtCore.Signal(str)  # instance key

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setBackgroundBrush(QtGui.QColor("#151515"))
        self.nodes: dict[str, NodeItem] = {}
        self.wires: list[WireItem] = []
        self._drag_from: Optional[Port] = None
        self._drag_line: Optional[QtWidgets.QGraphicsPathItem] = None
        self._detached: Optional[str] = None  # input key of a picked-up wire
        self.selectionChanged.connect(self._on_selection)

    # ------------------------------------------------------------ building
    def clear_graph(self) -> None:
        self.clear()
        self.nodes = {}
        self.wires = []
        self._drag_from = None
        self._drag_line = None
        self._detached = None

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

    def wire_for_input(self, port: Port) -> Optional[WireItem]:
        return next((wire for wire in self.wires if wire.target is port), None)

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
            self.update()  # nothing happened; repaint the dropped drag line away

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            self.delete_selected()
            event.accept()
            return
        super().keyPressEvent(event)

    def delete_selected(self) -> bool:
        """Disconnect selected wires and remove selected scene nodes. True when anything was selected."""
        wires = [item for item in self.selectedItems() if isinstance(item, WireItem)]
        externals = [item for item in self.selectedItems() if isinstance(item, NodeItem) and item.external]
        for wire in wires:
            self.disconnect_requested.emit(wire.target_key)
        for node in externals:
            self.remove_external_requested.emit(node.key)
        return bool(wires or externals)

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
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        # Maya-style navigation: no scrollbars, pan with the middle button
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._positions: dict[str, tuple] = {}
        self.externals: set[str] = set()  # scene nodes added by hand (kept even when unconnected)
        self._nav: Optional[str] = None  # "pan" | "zoom"
        self._nav_last = QtCore.QPoint()
        self.graph.connect_requested.connect(self.connect_input)
        self.graph.disconnect_requested.connect(self.disconnect_input)
        self.graph.sever_requested.connect(self.sever)
        self.graph.remove_external_requested.connect(self.remove_scene_node)
        self.graph.node_selected.connect(self.selection_changed)

    # ------------------------------------------------------------ building
    def rebuild(self) -> None:
        for key, node in self.graph.nodes.items():
            self._positions[key] = (node.pos().x(), node.pos().y())
        first = not self._positions
        self.graph.clear_graph()
        handles = self.guides.instances()
        by_key = {handle.key: handle for handle in handles}
        # external sources: connected scene nodes + the ones added by hand
        externals: set[str] = set(self.externals)
        for handle in handles:
            for source in handle.inputs.values():
                key, output = split_source(source)
                if key is None or key not in by_key:
                    externals.add(source)
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
            pos = self._positions.get(handle.key) or (20 + column * (NODE_WIDTH + 60), 30 + columns.get(column, 0) * 96)
            columns[column] = columns.get(column, 0) + 1
            primary = module_cls.primary_input()
            self.graph.add_node(
                handle.key, handle.key, module_cls.display_label(), module_cls.input_names(), list(handle.outputs),
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
        # a roomy scene rect so panning is not clamped to the nodes
        self.graph.setSceneRect(self.graph.itemsBoundingRect().adjusted(-600, -600, 600, 600))
        if first:
            self.fit()

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

    def connect_input(self, input_key: str, source: str) -> None:
        source = source[:-5] if source.endswith(".node") else source
        self._apply(lambda: self.guides.connect(input_key, source))

    def disconnect_input(self, input_key: str) -> None:
        self._apply(lambda: self.guides.disconnect(input_key))

    def sever(self, key: str) -> None:
        """Drop every connection into or out of the node ``key``."""

        def run():
            for item in self.guides.connections():
                source_key, _output = split_source(item["source"])
                if item["input"].startswith(f"{key}.") or item["source"] == key or source_key == key:
                    self.guides.disconnect(item["input"])

        self._apply(run)

    def add_scene_node(self, name: str) -> None:
        name = (name or "").strip()
        if not name:
            return
        self.externals.add(name)
        self.rebuild()

    def remove_scene_node(self, name: str) -> None:
        self.externals.discard(name)
        self.sever(name)

    def ask_scene_node(self) -> None:
        default = getattr(self.guides.backend, "selected_node_name", lambda: "")() or ""
        name, ok = QtWidgets.QInputDialog.getText(self, "Add scene node", "Scene node modules may connect to:", text=default)
        if ok:
            self.add_scene_node(name)

    def delete_selected(self) -> bool:
        return self.graph.delete_selected()

    def select_key(self, key: Optional[str]) -> None:
        self.graph.select_key(key)

    # ---------------------------------------------------------- navigation
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self.fit)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == QtCore.Qt.Key_F:
            self.fit()
            return
        if event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            self.delete_selected()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        alt = bool(event.modifiers() & QtCore.Qt.AltModifier)
        if event.button() == QtCore.Qt.MiddleButton or (alt and event.button() == QtCore.Qt.LeftButton):
            self._nav = "pan"
        elif alt and event.button() == QtCore.Qt.RightButton:
            self._nav = "zoom"
        if self._nav:
            self._nav_last = event.pos()
            self.setCursor(QtCore.Qt.ClosedHandCursor if self._nav == "pan" else QtCore.Qt.SizeHorCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._nav:
            delta = event.pos() - self._nav_last
            self._nav_last = event.pos()
            if self._nav == "pan":
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            else:
                factor = 1.0 + (delta.x() - delta.y()) * 0.01
                factor = min(max(factor, 0.5), 2.0)
                self.scale(factor, factor)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._nav:
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
        menu = QtWidgets.QMenu(self)
        if isinstance(item, WireItem):
            menu.addAction("Disconnect", lambda key=item.target_key: self.disconnect_input(key))
        elif isinstance(item, NodeItem):
            menu.addAction("Sever all connections", lambda key=item.key: self.sever(key))
            if item.external:
                menu.addAction("Remove scene node", lambda key=item.key: self.remove_scene_node(key))
        else:
            menu.addAction("Add scene node…", self.ask_scene_node)
        menu.addSeparator()
        menu.addAction("Fit view\tF", self.fit)
        menu.exec_(event.globalPos())
