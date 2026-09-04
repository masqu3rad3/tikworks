"""The leaf widgets of the Guide Designer: the tree, an input row, scene nodes."""

from __future__ import annotations

from typing import Optional

from tik.shared.ui import theme
from tik.shared.ui.icons import glyph_icon
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.tile_grid import TileEntry
from tik.trigger.core import registry

from ..palette import PaletteEntry

MIME_MODULE = "application/x-trigger-module-type"
SCENE_NODE = "__scene_node__"  # pseudo module: a group of arbitrary scene nodes modules can connect to
MODULE_COLORS = {"body": "#c9a24a", "limbs": "#5b8fd0", "generic": "#7fa86a", "face": "#b86b9a", "scene": "#8a93a0"}


def module_entries():
    tiles, palette = [], []
    for module_cls in registry.iter_modules():
        category = getattr(module_cls, "category", "generic")
        tiles.append(TileEntry(module_cls.module_type, module_cls.display_label(), category))
        palette.append(PaletteEntry(module_cls.module_type, module_cls.display_label(), category))
    tiles.append(TileEntry(SCENE_NODE, "Scene", "scene"))
    palette.append(PaletteEntry(SCENE_NODE, "Scene Nodes", "scene"))
    return tiles, palette


class GuideTree(QtWidgets.QTreeWidget):
    """Instances tree; dragging a row onto another sets its primary input."""

    reparent_requested = QtCore.Signal(str, object)  # instance_id, parent instance_id or None
    palette_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideTree")
        self.setHeaderLabels(["Module", "Type", "Side", "Primary input"])
        header = self.header()
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(30)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)
        self.setColumnWidth(0, 150)
        for column in (1, 2):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == QtCore.Qt.Key_Tab:
            self.palette_requested.emit()
            return
        super().keyPressEvent(event)

    def focusNextPrevChild(self, next_child: bool) -> bool:  # noqa: N802
        return False

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != QtCore.Qt.LeftButton:
            # middle/right must never start a drag (a middle drag crashed Maya)
            self.setDragEnabled(False)
            try:
                super().mousePressEvent(event)
            finally:
                self.setDragEnabled(True)
            return
        super().mousePressEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        target = self.itemAt(position)
        moved = self.currentItem()
        event.setDropAction(QtCore.Qt.IgnoreAction)
        event.accept()
        if moved is None:
            return
        moved_id = moved.data(0, QtCore.Qt.UserRole)
        target_id = target.data(0, QtCore.Qt.UserRole) if target is not None else None
        if target_id != moved_id:
            # rebuilding the tree while Qt is still inside the drop crashes; do it next tick
            QtCore.QTimer.singleShot(0, lambda: self.reparent_requested.emit(moved_id, target_id))


class InputRow(QtWidgets.QWidget):
    """One input: source editor + "from selection" + clear.

    Right-click the field for a menu of every other module (submenu = its
    outputs) and the scene nodes of every group.
    """

    changed = QtCore.Signal(str, str)  # input name, source ("" = disconnect)

    def __init__(self, input_decl, parent=None, picker=None, sources=None) -> None:
        super().__init__(parent)
        self.input = input_decl
        self.picker = picker
        self.sources = sources  # callable -> (modules: [(key, label, [outputs])], scene_nodes: [(group, node)])
        self._last = ""  # last source we showed or reported; editingFinished fires on focus loss too
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.line = QtWidgets.QLineEdit()
        self.line.setPlaceholderText("module.output or scene node" + ("  (optional)" if input_decl.optional else ""))
        self.pick = QtWidgets.QToolButton()
        self.pick.setText("◦")
        self.pick.setToolTip("Use the selected guide (its module output) or scene node")
        self.clear = QtWidgets.QToolButton()
        self.clear.setText("×")
        self.clear.setToolTip("Disconnect")
        layout.addWidget(self.line, 1)
        layout.addWidget(self.pick)
        layout.addWidget(self.clear)
        self.line.editingFinished.connect(self._edited)
        self.line.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.line.customContextMenuRequested.connect(self._menu)
        self.pick.clicked.connect(self._pick)
        self.clear.clicked.connect(lambda: self.choose(""))

    def set_source(self, source: str) -> None:
        self._last = source or ""
        self.line.setText(self._last)

    def _edited(self) -> None:
        text = self.line.text().strip()
        if text == self._last:
            return
        self._last = text
        self.changed.emit(self.input.name, text)

    def choose(self, source: str) -> None:
        self._last = source
        self.line.setText(source)
        self.changed.emit(self.input.name, source)

    def build_menu(self, parent=None) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(parent or self)
        modules, scene_nodes = self.sources() if self.sources else ([], [])
        for key, label, outputs in modules:
            sub = menu.addMenu(f"{key}  ·  {label}")
            for output in outputs:
                sub.addAction(output, lambda source=f"{key}.{output}": self.choose(source))
        if scene_nodes:
            if modules:
                menu.addSeparator()
            groups: dict[str, QtWidgets.QMenu] = {}
            for group, node in scene_nodes:
                sub = groups.get(group)
                if sub is None:
                    sub = groups[group] = menu.addMenu(f"{group}  ·  scene nodes")
                sub.addAction(node, lambda source=node: self.choose(source))
        if not modules and not scene_nodes:
            menu.addAction("No other modules or scene nodes").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Disconnect", lambda: self.choose(""))
        return menu

    def _menu(self, point) -> None:
        self.build_menu().exec(self.line.mapToGlobal(point))

    def _pick(self) -> None:
        if self.picker is None:
            return
        source = self.picker()
        if source:
            self.line.setText(source)
            self.changed.emit(self.input.name, source)


class SceneNodesPanel(QtWidgets.QWidget):
    """Outputs of a scene-nodes group: one scene node per row, pickable from the Maya selection."""

    changed = QtCore.Signal(list)  # new node list

    def __init__(self, parent=None, picker=None) -> None:
        super().__init__(parent)
        self.picker = picker  # callable -> [selected scene node names]
        self.rows: list[QtWidgets.QLineEdit] = []
        self._last: list[str] = []
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        caption = QtWidgets.QLabel("SCENE NODES")
        caption.setObjectName("FieldCaption")
        layout.addWidget(caption)
        self.rows_layout = QtWidgets.QVBoxLayout()
        self.rows_layout.setSpacing(4)
        layout.addLayout(self.rows_layout)
        buttons = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton("+ Add")
        self.add_button.setToolTip("Add a row (pre-filled from the Maya selection)")
        self.add_selected_button = QtWidgets.QPushButton("< Add selected")
        self.add_selected_button.setToolTip("One row per selected Maya node")
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.add_selected_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)
        self.add_button.clicked.connect(lambda: self._add_rows([self._picked()[:1] or [""]][0] or [""]))
        self.add_selected_button.clicked.connect(lambda: self._add_rows(self._picked() or [""]))

    def _picked(self) -> list[str]:
        return list(self.picker() or []) if self.picker else []

    def set_nodes(self, nodes: list[str]) -> None:
        self._last = [node for node in nodes if node]
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.rows = []
        for node in nodes:
            self._append_row(node)

    def nodes(self) -> list[str]:
        return [row.text().strip() for row in self.rows if row.text().strip()]

    def _append_row(self, node: str) -> QtWidgets.QLineEdit:
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        line = QtWidgets.QLineEdit(node)
        line.setPlaceholderText("scene node name")
        pick = QtWidgets.QToolButton()
        pick.setText("<")
        pick.setToolTip("Use the selected Maya node")
        remove = QtWidgets.QToolButton()
        remove.setText("×")
        row.addWidget(line, 1)
        row.addWidget(pick)
        row.addWidget(remove)
        self.rows_layout.addWidget(holder)
        self.rows.append(line)
        line.editingFinished.connect(self._emit)
        pick.clicked.connect(lambda: (line.setText((self._picked() or [line.text()])[0]), self._emit()))
        remove.clicked.connect(lambda: self._remove(line, holder))
        return line

    def _add_rows(self, names: list[str]) -> None:
        for name in names:
            self._append_row(name)
        if names and not names[-1]:
            self.rows[-1].setFocus()
        self._emit()

    def _remove(self, line, holder) -> None:
        self.rows.remove(line)
        holder.deleteLater()
        self._emit()

    def _emit(self) -> None:
        nodes = self.nodes()
        if nodes == self._last:
            return  # focus loss / teardown, nothing changed
        self._last = nodes
        self.changed.emit(nodes)
