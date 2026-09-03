"""The graph canvas: wire dragging, slicing and selection."""

from __future__ import annotations

from typing import Optional

from tik.shared.ui import theme
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets

from .constants import GRID, MODE_FULL
from .items import NodeItem, Port, WireItem


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

    def add_node(self, key, title, subtitle, inputs, outputs, color, external=False, primary_input=None, pos=None, mode=MODE_FULL, spaces=None) -> NodeItem:
        node = NodeItem(key, title, subtitle, inputs, outputs, color, external, primary_input, mode, spaces)
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

    def wires_for_input(self, port: Port) -> list[WireItem]:
        """Every wire landing on ``port``."""
        return [wire for wire in self.wires if wire.target is port]

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
        sliced = [wire for wire in list(self.wires) if wire.path().intersects(blade)]
        for wire in sliced:
            self.disconnect_requested.emit(wire.target_key)
        return [wire.target_key for wire in sliced]

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            if self.delete_selected():
                event.accept()
                return
            # Nothing here to delete -- a selected *module* is the designer's to
            # remove, so let the key through rather than swallowing it.
            event.ignore()
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
