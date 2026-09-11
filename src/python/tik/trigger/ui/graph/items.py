"""The things you see in the graph: ports, nodes and the wires between them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tik.shared.ui import theme
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.trigger.ui.draw_state import DRAWN, NOT_DRAWN, STALE, STALE_INK

from .constants import (
    BADGE,
    FILTERED_OPACITY,
    FRAME_INK,
    FRAME_PADDING,
    FRAME_TITLE,
    GLYPH_WIDTH,
    GRID,
    HEADER,
    MODE_CONNECTED,
    MODE_FULL,
    MODE_MINIMAL,
    NODE_WIDTH,
    PORT_FILTER_MIN,
    PORT_FILTER_ROW,
    PORT_GROUP_INK,
    PORT_RADIUS,
    PORT_SPACE,
    ROW,
    STATE_STRIPE,
    WIRE_PRIMARY,
    WIRE_SECONDARY,
)


class Port(QtWidgets.QGraphicsEllipseItem):
    """An input or output dot on a node; wires start and end here."""

    def __init__(
        self,
        node: "NodeItem",
        name: str,
        is_output: bool,
        primary: bool = False,
        space: bool = False,
        label: str = "",
    ) -> None:
        super().__init__(
            -PORT_RADIUS, -PORT_RADIUS, PORT_RADIUS * 2, PORT_RADIUS * 2, node
        )
        self.node = node
        self.name = name
        #: What the node draws for this port. Apart from ``name`` because the
        #: name is the stored key -- ``c1_start`` -- and the slug in it is
        #: bookkeeping. Keying on the slug is what makes renaming a copy free;
        #: showing it is what made the graph unreadable.
        self.label = label or name
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
        """``<node key>.<port name>``."""
        return f"{self.node.key}.{self.name}"

    def set_connected(self, connected: bool) -> None:
        """Record the connection state and recolour the dot."""
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
        if (
            event.button() != QtCore.Qt.LeftButton
            or event.modifiers() & QtCore.Qt.ControlModifier
        ):
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


@dataclass
class NodeSpec:
    """Everything a graph node is drawn from."""

    key: str
    title: str
    subtitle: str
    inputs: list
    outputs: list
    color: str
    #: A scene-nodes group: dashed, and its properties are the group's.
    external: bool = False
    #: A collapsed reference. Drawn like a group but emphatically not one --
    #: ``external`` carries the scene-nodes *meaning*, and borrowing it gave
    #: a collapsed reference that panel and its Add buttons.
    reference: bool = False
    primary_input: Optional[str] = None
    mode: int = MODE_FULL
    spaces: Optional[list] = None
    #: ``{port key: label}`` where the two differ -- a copy's ports are
    #: stored qualified and shown bare.
    port_labels: Optional[dict] = None
    #: ``[(group label, [port key, ...])]`` in draw order. A single group
    #: draws no header, so a one-copy module reads exactly as it always has.
    port_groups: Optional[list] = None
    #: This node's own port search, restored across rebuilds by the view.
    port_filter: str = ""
    #: NOT_DRAWN / DRAWN / STALE -- the same states the guide tree paints
    draw_state: str = DRAWN


#: Re-exported under the name the graph package uses for geometry.
FramePadding = FRAME_PADDING


@dataclass
class FrameSpec:
    """Everything a reference frame is drawn from."""

    ref_id: str
    title: str
    collapsed: bool = False


class FrameItem(QtWidgets.QGraphicsItem):
    """The backdrop behind one reference's modules.

    A backdrop and nothing more: it is neither movable nor selectable, because
    it sits under the nodes it encloses and dragging it would fight them. Its
    only interactive part is the glyph that collapses the reference, and
    collapsing is not a hide -- the view builds a single node instead, so
    there is no second wire path to keep correct.
    """

    def __init__(self, spec: FrameSpec) -> None:
        super().__init__()
        self.ref_id = spec.ref_id
        self.title = spec.title
        self.collapsed = spec.collapsed
        self._extent = QtCore.QRectF(0, 0, 0, 0)
        self.setZValue(-10)  # behind every node
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)

    def set_extent(self, rect: QtCore.QRectF) -> None:
        """Size the frame to enclose ``rect``, in item coordinates."""
        self.prepareGeometryChange()
        self._extent = QtCore.QRectF(rect)

    def boundingRect(self) -> QtCore.QRectF:  # noqa: N802
        return self._extent.adjusted(
            -FRAME_PADDING,
            -FRAME_PADDING - FRAME_TITLE,
            FRAME_PADDING,
            FRAME_PADDING,
        )

    def glyph_rect(self) -> QtCore.QRectF:
        """Where the collapse glyph is drawn, in item coordinates."""
        bounds = self.boundingRect()
        return QtCore.QRectF(
            bounds.right() - GLYPH_WIDTH - 6, bounds.top() + 3, GLYPH_WIDTH, FRAME_TITLE
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton and self.glyph_rect().contains(
            event.pos()
        ):
            scene = self.scene()
            if scene is not None:
                scene.frame_toggle_requested.emit(self.ref_id)
            event.accept()
            return
        event.ignore()

    def paint(self, painter, option, widget=None) -> None:
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        bounds = self.boundingRect()
        ink = QtGui.QColor(FRAME_INK)
        fill = QtGui.QColor(ink)
        fill.setAlpha(18)
        pen = QtGui.QPen(ink, 1.0)
        pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(fill)
        painter.drawRoundedRect(bounds, 6, 6)
        title = QtCore.QRectF(
            bounds.left() + 8, bounds.top() + 2, bounds.width() - 24, FRAME_TITLE
        )
        painter.setPen(ink)
        painter.drawText(
            title, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, self.title
        )
        painter.drawText(
            self.glyph_rect(), QtCore.Qt.AlignCenter, "-" if not self.collapsed else "+"
        )


class NodeItem(QtWidgets.QGraphicsItem):
    """A module or scene-nodes group drawn as a box with ports."""

    def __init__(self, spec: NodeSpec) -> None:
        super().__init__()
        self.key = spec.key
        self.title = spec.title
        self.subtitle = spec.subtitle
        self.color = spec.color
        self.external = spec.external
        self.reference = spec.reference
        self.mode = spec.mode
        self.draw_state = spec.draw_state
        # absent from the scene: the whole node recedes, which is what
        # "there is nothing here to look at in Maya" should look like
        self.setOpacity(0.45 if self.draw_state == NOT_DRAWN else 1.0)
        #: True while the graph's search rules this node out.
        self.filtered = False
        self.inputs: dict[str, Port] = {}
        self.outputs: dict[str, Port] = {}
        self._height = HEADER + 8
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsMovable
            | QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(2)
        labels = dict(spec.port_labels or {})
        for name in spec.inputs:
            self.inputs[name] = Port(
                self,
                name,
                False,
                primary=(name == spec.primary_input),
                label=labels.get(name, name),
            )
        for name in spec.spaces or []:
            self.inputs[name] = Port(
                self, name, False, space=True, label=labels.get(name, name)
            )
        for name in spec.outputs:
            self.outputs[name] = Port(self, name, True, label=labels.get(name, name))
        #: ``[(label, [port key, ...])]``; one group draws no header.
        self.port_groups: list = list(spec.port_groups or [])
        #: This node's own port search. Per node rather than per graph: you
        #: narrow one crowded node while the rest stay as they were.
        self.port_filter: str = spec.port_filter or ""
        self.port_filter_widget = None
        self._group_of: dict = {
            key: label for label, keys in self.port_groups for key in keys
        }
        if len(self.inputs) + len(self.outputs) >= PORT_FILTER_MIN:
            self._build_port_filter()
        self.relayout()

    def _build_port_filter(self) -> None:
        """A small search box under the header, for this node's ports only.

        A real ``QLineEdit`` through a proxy rather than hand-drawn text: it
        gets editing, selection and a clear button for nothing, and only
        crowded nodes carry one, so the scene does not fill with widgets.
        """
        edit = QtWidgets.QLineEdit()
        edit.setPlaceholderText("filter ports…")
        edit.setClearButtonEnabled(True)
        edit.setText(self.port_filter)
        edit.setFixedHeight(PORT_FILTER_ROW)
        edit.setFixedWidth(int(NODE_WIDTH - 16))
        edit.textChanged.connect(self.set_port_filter)
        proxy = QtWidgets.QGraphicsProxyWidget(self)
        proxy.setWidget(edit)
        proxy.setPos(8, HEADER + 3)
        proxy.setZValue(4)
        self.port_filter_widget = edit
        self._port_filter_proxy = proxy

    def matches_filter(self, port) -> bool:
        """Whether ``port`` survives this node's search.

        Matched on what the node *shows* -- the port's label and its group's
        heading -- rather than the stored key, because the key carries a copy
        slug the rigger never sees.
        """
        term = (self.port_filter or "").strip().lower()
        if not term:
            return True
        group = self._group_of.get(port.name, "")
        return term in port.label.lower() or term in group.lower()

    def set_port_filter(self, text: str) -> None:
        """Narrow this node to the ports matching ``text``."""
        self.port_filter = text or ""
        if (
            self.port_filter_widget is not None
            and self.port_filter_widget.text() != self.port_filter
        ):
            self.port_filter_widget.setText(self.port_filter)
        scene = self.scene()
        if scene is not None and hasattr(scene, "port_filter_changed"):
            scene.port_filter_changed.emit(self.key, self.port_filter)
        self.relayout()

    # --------------------------------------------------------------- layout
    def visible_ports(self) -> tuple[list[Port], list[Port]]:
        """``(inputs, outputs)`` shown in the current collapse mode."""
        if self.mode == MODE_MINIMAL:
            return [], []
        if self.mode == MODE_CONNECTED:
            return (
                [
                    port
                    for port in self.inputs.values()
                    if port.connected and self.matches_filter(port)
                ],
                [
                    port
                    for port in self.outputs.values()
                    if port.connected and self.matches_filter(port)
                ],
            )
        return (
            [port for port in self.inputs.values() if self.matches_filter(port)],
            [port for port in self.outputs.values() if self.matches_filter(port)],
        )

    def row_plan(self) -> list:
        """``[(kind, label, in port, out port)]`` -- the node's rows in order.

        ``kind`` is ``"group"`` for a copy heading or ``"ports"`` for a pair
        of dots. A module with one copy has one group and draws no heading,
        so it reads exactly as it always has; a module with five draws the
        copy's name once rather than stamping it onto every port.
        """
        ins, outs = self.visible_ports()
        shown_in = {port.name: port for port in ins}
        shown_out = {port.name: port for port in outs}
        if len(self.port_groups) < 2:
            plan = []
            for index in range(max(len(ins), len(outs))):
                plan.append(
                    (
                        "ports",
                        "",
                        ins[index] if index < len(ins) else None,
                        outs[index] if index < len(outs) else None,
                    )
                )
            return plan
        plan = []
        for label, keys in self.port_groups:
            group_in = [shown_in[key] for key in keys if key in shown_in]
            group_out = [shown_out[key] for key in keys if key in shown_out]
            if not group_in and not group_out:
                continue
            plan.append(("group", label, None, None))
            for index in range(max(len(group_in), len(group_out))):
                plan.append(
                    (
                        "ports",
                        "",
                        group_in[index] if index < len(group_in) else None,
                        group_out[index] if index < len(group_out) else None,
                    )
                )
        return plan

    def relayout(self) -> None:
        """Place ports for the current mode.

        Hidden ports sit on the header edge so wires still reach them.
        """
        self.prepareGeometryChange()
        ins, outs = self.visible_ports()
        plan = self.row_plan()
        top = HEADER + (PORT_FILTER_ROW + 6 if self.port_filter_widget else 0)
        self._height = top + (len(plan) * ROW + 8 if plan else 6)
        self._rows_top = top
        for port in self.inputs.values():
            port.setVisible(port in ins)
            port.setPos(0, HEADER / 2)
        for port in self.outputs.values():
            port.setVisible(port in outs)
            port.setPos(NODE_WIDTH, HEADER / 2)
        for index, (kind, _label, port_in, port_out) in enumerate(plan):
            if kind != "ports":
                continue
            centre = self._rows_top + 6 + index * ROW + ROW / 2
            if port_in is not None:
                port_in.setPos(0, centre)
            if port_out is not None:
                port_out.setPos(NODE_WIDTH, centre)
        self.update()
        if self.scene() is not None:
            self.scene().update_wires()

    def set_filtered(self, filtered: bool) -> None:
        """Fade the node when the search rules it out, or restore it.

        Opacity only: the node keeps its place and its wires, so a search
        never makes the graph claim a connection that is not there.
        """
        if bool(filtered) == self.filtered:
            return
        self.filtered = bool(filtered)
        base = 0.45 if self.draw_state == NOT_DRAWN else 1.0
        self.setOpacity(FILTERED_OPACITY if self.filtered else base)

    def set_mode(self, mode: int) -> None:
        """Set the collapse mode (minimal, connected or full) and relayout."""
        self.mode = max(MODE_MINIMAL, min(MODE_FULL, int(mode)))
        self.relayout()

    def glyph_rect(self) -> QtCore.QRectF:
        """Where the collapse glyph is drawn, in item coordinates."""
        return QtCore.QRectF(NODE_WIDTH - GLYPH_WIDTH - 4, 0, GLYPH_WIDTH + 4, HEADER)

    def boundingRect(self) -> QtCore.QRectF:  # noqa: N802
        return QtCore.QRectF(
            -PORT_RADIUS, 0, NODE_WIDTH + PORT_RADIUS * 2, self._height
        )

    # ---------------------------------------------------------------- paint
    def _paint_stale_badge(self, painter) -> None:
        """The out-of-date "!" at the head of the header.

        Drawn on a dark chip rather than straight onto the header: the header
        is tinted per module category, and an amber mark on the gold ``body``
        tint would be the one pairing that does not read. The chip makes it
        legible on every tint at once.
        """
        painter.save()
        try:
            top = (HEADER - BADGE) / 2.0
            chip = QtCore.QRectF(5, top, BADGE, BADGE)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(0, 0, 0, 150))
            painter.drawRoundedRect(chip, 3, 3)
            ink = QtGui.QColor(STALE_INK)
            centre = chip.center().x()
            pen = QtGui.QPen(ink, 2.0)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(
                QtCore.QPointF(centre, chip.top() + 3.0),
                QtCore.QPointF(centre, chip.top() + 7.5),
            )
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(ink)
            painter.drawEllipse(QtCore.QPointF(centre, chip.bottom() - 2.7), 1.15, 1.15)
        finally:
            painter.restore()

    def paint(self, painter, option, widget=None) -> None:
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        body = QtCore.QRectF(0, 0, NODE_WIDTH, self._height)
        pen = QtGui.QPen(
            QtGui.QColor(theme.ACCENT if self.isSelected() else "#3a3a3a"), 1.2
        )
        if self.external or self.reference:
            pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QtGui.QColor("#262626"))
        painter.drawRoundedRect(body, 4, 4)
        # The left edge is the only free surface on a node: the border is
        # already selection, the dash is already `external`, and the header
        # is full of title, subtitle and collapse glyph.
        if self.draw_state != DRAWN:
            painter.save()
            clip = QtGui.QPainterPath()
            clip.addRoundedRect(body, 4, 4)
            painter.setClipPath(clip)
            painter.setPen(QtCore.Qt.NoPen)
            if self.draw_state == STALE:
                painter.setBrush(QtGui.QColor(STALE_INK))
                painter.drawRect(QtCore.QRectF(0, 0, STATE_STRIPE, self._height))
            else:
                painter.setBrush(QtGui.QColor("#5a5a5a"))
                offset = 0.0
                while offset < self._height:
                    painter.drawRect(QtCore.QRectF(0, offset, 3, 3))
                    offset += 6
            painter.restore()
        header = QtCore.QRectF(0, 0, NODE_WIDTH, HEADER)
        painter.setPen(QtCore.Qt.NoPen)
        header_ink = self.color
        if self.reference:
            header_ink = FRAME_INK
        elif self.external:
            header_ink = "#3a4048"
        painter.setBrush(QtGui.QColor(header_ink))
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
        # The header paints over the top of the state stripe, so an out-of-date
        # node would lose its marker exactly where the eye lands first. The
        # badge carries it across: a shape, not only a colour, so it survives
        # the gold module tints it may sit on and a reader who cannot separate
        # amber from them.
        shift = BADGE + 4 if self.draw_state == STALE else 0
        if shift:
            self._paint_stale_badge(painter)
        title = metrics.elidedText(
            self.title, QtCore.Qt.ElideRight, NODE_WIDTH - GLYPH_WIDTH - 60 - shift
        )
        painter.drawText(QtCore.QPointF(8 + shift, baseline), title)
        font.setBold(False)
        painter.setFont(font)
        metrics = QtGui.QFontMetricsF(font)
        painter.drawText(
            QtCore.QPointF(
                NODE_WIDTH
                - GLYPH_WIDTH
                - 10
                - metrics.horizontalAdvance(self.subtitle),
                baseline,
            ),
            self.subtitle,
        )
        # collapse glyph: 1..3 lines (Maya node editor style)
        painter.setPen(QtGui.QPen(ink, 1.2))
        x0 = NODE_WIDTH - GLYPH_WIDTH - 2
        for line in range(self.mode + 1):
            line_y = HEADER / 2 - 4 + line * 4
            painter.drawLine(
                QtCore.QPointF(x0, line_y), QtCore.QPointF(x0 + GLYPH_WIDTH - 4, line_y)
            )
        for index, (kind, group_label, port_in, port_out) in enumerate(self.row_plan()):
            top = getattr(self, "_rows_top", HEADER) + 6 + index * ROW
            if kind == "group":
                painter.setPen(QtGui.QColor(PORT_GROUP_INK))
                painter.drawText(
                    QtCore.QRectF(8, top, NODE_WIDTH - 16, ROW),
                    QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                    group_label,
                )
                continue
            painter.setPen(QtGui.QColor("#bdbdbd"))
            indent = 12 if len(self.port_groups) < 2 else 20
            if port_in is not None:
                painter.drawText(
                    QtCore.QRectF(indent, top, NODE_WIDTH - indent - 12, ROW),
                    QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                    port_in.label + ("  ●" if port_in.primary else ""),
                )
            if port_out is not None:
                painter.drawText(
                    QtCore.QRectF(12, top, NODE_WIDTH - indent - 12, ROW),
                    QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight,
                    port_out.label,
                )

    # ------------------------------------------------------------- events
    def itemChange(self, change, value):  # noqa: N802
        scene = self.scene()
        if (
            change == QtWidgets.QGraphicsItem.ItemPositionChange
            and scene is not None
            and getattr(scene, "snap", False)
        ):
            return QtCore.QPointF(
                round(value.x() / GRID) * GRID, round(value.y() / GRID) * GRID
            )
        if (
            change == QtWidgets.QGraphicsItem.ItemPositionHasChanged
            and scene is not None
        ):
            scene.update_wires()
            scene.moved.add(self.key)
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton and self.glyph_rect().contains(
            event.pos()
        ):
            if self.reference:
                # A collapsed reference has exactly one toggle, and it is not
                # the 1/2/3 display mode: while collapsed there is no backdrop
                # to click, so this glyph is the only way back.
                self.scene().frame_toggle_requested.emit(self.key.lstrip("@"))
            else:
                self.scene().mode_change_requested.emit(self.key, (self.mode + 1) % 3)
            event.accept()
            return
        super().mousePressEvent(event)


class WireItem(QtWidgets.QGraphicsPathItem):
    """A curve from an output port to an input port."""

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
        """The input port's key."""
        return self.target.key

    @property
    def source_key(self) -> str:
        """The output port's key."""
        return self.source.key

    def shape(
        self,
    ) -> QtGui.QPainterPath:  # generous hit area so wires are easy to pick
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(10)
        return stroker.createStroke(self.path())

    def refresh(self) -> None:
        """Redraw the curve between the current port positions."""
        start = self.source.scenePos()
        end = self.target.scenePos()
        path = QtGui.QPainterPath(start)
        dx = max(abs(end.x() - start.x()) * 0.5, 40)
        path.cubicTo(start.x() + dx, start.y(), end.x() - dx, end.y(), end.x(), end.y())
        self.setPath(path)
        color = WIRE_PRIMARY if self.primary else WIRE_SECONDARY
        pen = QtGui.QPen(
            QtGui.QColor(theme.TEXT_BRIGHT) if self.isSelected() else color,
            2 if self.isSelected() else 1.6,
        )
        if self.source.node.external:
            pen.setStyle(QtCore.Qt.DashLine)
        self.setPen(pen)

    def paint(self, painter, option, widget=None) -> None:
        self.refresh()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(self.pen())
        painter.drawPath(self.path())
