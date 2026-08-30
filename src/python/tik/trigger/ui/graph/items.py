"""The things you see in the graph: ports, nodes and the wires between them."""

from __future__ import annotations

from typing import Optional

from tik.shared.ui import theme
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets

from .constants import (
    GLYPH_WIDTH,
    GRID,
    HEADER,
    MODE_CONNECTED,
    MODE_FULL,
    MODE_MINIMAL,
    NODE_WIDTH,
    PORT_RADIUS,
    PORT_SPACE,
    ROW,
    WIRE_PRIMARY,
    WIRE_SECONDARY,
)


class Port(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, node: "NodeItem", name: str, is_output: bool, primary: bool = False,
                 space: bool = False) -> None:
        super().__init__(-PORT_RADIUS, -PORT_RADIUS, PORT_RADIUS * 2, PORT_RADIUS * 2, node)
        self.node = node
        self.name = name
        self.is_output = is_output
        self.primary = primary
        self.space = space  # an animation-space port: coloured apart
        self.connected = False
        self.setBrush(QtGui.QColor(PORT_SPACE if space else "#7b7b7b"))
        self.setPen(QtGui.QPen(QtGui.QColor("#111111"), 1))
        self.setZValue(3)
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"{node.key}.{name}" + (" (space)" if space else ""))

    @property
    def key(self) -> str:
        return f"{self.node.key}.{self.name}"

    def set_connected(self, connected: bool) -> None:
        self.connected = connected
        if self.space:
            self.setBrush(QtGui.QColor(PORT_SPACE))
            return
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
        wires = scene.wires_for_input(self) if not self.is_output else []
        wire = wires[0] if wires else None
        if wire is not None:
            scene.pick_up_wire(wire, event.scenePos())  # unplug from the input end
        else:
            scene.start_wire(self, event.scenePos())
        event.accept()


class NodeItem(QtWidgets.QGraphicsItem):
    def __init__(self, key: str, title: str, subtitle: str, inputs: list, outputs: list, color: str,
                 external: bool = False, primary_input: Optional[str] = None, mode: int = MODE_FULL,
                 spaces: Optional[list] = None) -> None:
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
        for name in spaces or []:
            self.inputs[name] = Port(self, name, False, space=True)
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
