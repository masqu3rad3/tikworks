"""Guide Designer: a mode of the Trigger window — modules · tree · graph · properties.

Tree and graph are two views of the same connections (see ``GuideScene``);
the properties panel shows the module's Inputs first. Connections are data
only: the designer never parents guide joints into each other and never
selects joints in Maya on its own — use *Select guides* for that. Scene
structure changes (new/removed/undone guides) reach the UI through a
debounced ``SceneWatcher``; our own edits are muted.

The designer is a page, not a window: it builds a ``status_strip`` and leaves
the hosting to ``SessionView``, which shows it as a sub-tab of the session
whose guides it edits. It builds no menu bar -- the window owns the one bar,
and its Guides menu dispatches to whichever designer is in front.

Everything the designer authors (connections, scene-node groups, node
positions, collapse modes) lives in ``GuideScene`` / ``GuideScene.layout`` and is
exported with the ``.trg``; only window geometry and selection are transient.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from tik.shared.ui import theme
from tik.shared.ui.binding import BindingManager
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.filter_bar import FilterBar
from tik.shared.ui.icons import glyph_icon
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.scene_watcher import SceneWatcher
from tik.shared.ui.status import StatusFields
from tik.shared.ui.theme import MODULE_COLORS
from tik.shared.ui.tile_grid import TileGrid
from tik.trigger.core.schemas import split_source

if TYPE_CHECKING:  # the scene layer imports Maya; the UI only needs the name
    from tik.trigger.guides import GuideHandle

from tik.shared.ui.feedback import Feedback
from tik.trigger.core import copies as copy_list
from tik.trigger.core.exceptions import TriggerError
from tik.trigger.ui.draw_state import DRAWN, TOOLTIPS, states_from

from ..graph import GraphView
from ..iconography import icon_for_tile, module_icon
from ..palette import SearchPalette
from ..session_view import pane
from .action_bar import DesignerActionBar
from .commands import DesignerCommands
from .delegates import DisabledRole, DrawStateRole, OriginRole, OverrideRole
from .properties import DesignerProperties
from .widgets import MIME_MODULE, GuideTree, InputRow, SceneNodesPanel, module_entries

SIDES = ("L", "R", "C", "Both", "Auto")


def _override_count(entry) -> int:
    """How many things ``entry`` differs from its source by. 0 when local."""
    if entry is None or entry.origin is None or entry.source is None:
        return 0
    from tik.trigger.core.guide_reference import overrides_for

    return len(overrides_for(entry))


def _row_tooltip(state: str, origin, overrides: int, entry) -> str:
    """Draw state, provenance and overrides -- all three, never one instead
    of another."""
    lines = [TOOLTIPS[state]]
    if origin:
        lines.append(f"Referenced from {origin}.")
    if overrides:
        plural = "" if overrides == 1 else "s"
        lines.append(
            f"{overrides} local override{plural} — upstream changes to "
            "these will not arrive."
        )
    if entry is not None and not entry.enabled:
        lines.append("Left out of this rig; it will not build.")
    return "\n".join(lines)


def diff_summary(diff) -> str:
    """One line naming everything pending, for the status strip.

    This is where the counts live now that the action bar carries none: the
    bar says there is work in a direction, the tree and graph say which
    modules, and this says how many. Both directions appear, in the order
    they are read on the bar -- out of date and not drawn are Draw's, moved
    is Sync's.
    """
    parts = []
    if diff.stale:
        parts.append(f"{len(diff.stale)} out of date")
    if diff.not_drawn:
        parts.append(f"{len(diff.not_drawn)} not drawn")
    if diff.drifted:
        parts.append(f"{len(diff.drifted)} moved")
    if diff.orphans:
        parts.append(f"{len(diff.orphans)} orphan guide(s)")
    if diff.duplicates:
        parts.append(f"{len(diff.duplicates)} duplicate guide(s)")
    return " · ".join(parts)


class GuideDesigner(DesignerCommands, DesignerProperties, QtWidgets.QWidget):
    """A plain widget on purpose.

    The designer is hosted as a *mode* of the Trigger window (``ui/main.py``).
    It builds a ``status_strip`` but installs it nowhere, so the host decides
    where it goes.
    """

    # One setting, two front doors: the bar's checkbox here, the window's menu
    # action in Task 8. Defined on the widget itself (not the commands mixin)
    # so Qt's meta-object system actually sees it.
    auto_sync_changed = QtCore.Signal(bool)

    def __init__(
        self,
        parent=None,
        events=None,
        file_browser=None,
        binding_adapter=None,
        scene=None,
    ) -> None:
        super().__init__(parent)
        # ``scene`` is an injection point for tests; normally the designer owns
        # the scene's guides.
        if scene is None:
            from tik.trigger.guides import GuideScene

            scene = GuideScene(events)
        self.guides = scene
        self.events = self.guides.events
        self.file_browser = file_browser
        self.binding_adapter = binding_adapter
        # last guide-library file touched: a file-dialog convenience, not
        # this view's identity -- the session owns the guides now
        self.last_guide_file: str = ""
        self.bindings = BindingManager()
        self._current: Optional[GuideHandle] = None
        self._multi: list[GuideHandle] = (
            []
        )  # every selected module when they share a type
        self._external: Optional[str] = None  # selected scene-nodes group (graph only)
        self._module_obj = None
        #: The current copy, as a one-copy module of its own. The copy form
        #: edits *this*, which is what keeps every control-keyed choice list
        #: inside the copy: ``control_names`` on a one-copy module returns
        #: ``ik``, not ``ik``/``c1_ik``/``c2_ik``.
        self._copy_obj = None
        self._input_rows: dict[str, InputRow] = {}
        self._syncing = False
        self._torn_down = False
        # SceneWatcher probes objectName() to notice a destroyed C++ object
        self.setObjectName("TriggerGuideDesigner")
        self.resize(1240, 680)
        self._build_central()
        self._build_actions()
        self._build_status()
        theme.apply(self)
        self.watcher = SceneWatcher(
            self._on_scene_event,
            owner=self,
            install_job=getattr(self.guides, "install_scene_job", None),
            kill_job=getattr(self.guides, "kill_scene_job", None),
            parent=self,
            # deleting a guide in the outliner has no scriptJob event
            api_callbacks=True,
        )
        self.watcher.install()
        # closeEvent is not the only teardown path; a destroyed dock leaves the
        # jobs installed and the zero-timer firing into a dead widget. Captured
        # in a closure so nothing touches self during destruction.
        watcher = self.watcher
        self.destroyed.connect(lambda *_args: watcher.uninstall())
        # Restored via _apply_auto_sync, not set_auto_sync: the latter runs a
        # full sync(), which captures, can regenerate, and calls
        # session.touch() -- opening a Designer would then mark a freshly
        # loaded, untouched session "modified" before the rigger did anything.
        # refresh() below is enough to paint the document that is already there.
        from tik.trigger.config import prefs

        from .commands import migrate_designer_settings

        migrate_designer_settings()
        self._apply_auto_sync(bool(prefs.guides.auto_sync))
        self.guides.draw_on_create = bool(prefs.guides.draw_on_create)
        # Only the button and the flag: a restore must not run the scene
        # operation, since nothing is drawn yet and set_labels() deliberately
        # does not emit. The first Draw writes labels on regardless -- the
        # preference decides where the button starts, never what Draw renders.
        labels_on = bool(prefs.guides.show_guide_labels)
        self.guides.labels_visible = labels_on
        self.action_bar.set_labels(labels_on)
        self.refresh()

    # ------------------------------------------------------------------ ui
    def _build_central(self) -> None:
        tiles, palette_entries = module_entries()
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.addWidget(self._build_side_pane(tiles))
        self.splitter.addWidget(self._build_tree_pane())
        self.splitter.addWidget(self._build_graph_pane())
        self.splitter.addWidget(self._build_properties_pane())
        for index, stretch in enumerate((0, 1, 2, 1)):
            self.splitter.setStretchFactor(index, stretch)
        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, True)
        self.splitter.setCollapsible(2, True)
        self.splitter.setCollapsible(3, False)
        self.splitter.setSizes([170, 280, 520, 270])
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.splitter, 1)
        self.action_bar = DesignerActionBar(self)
        layout.addWidget(self.action_bar)

        self.palette = SearchPalette(
            palette_entries, self, colors=MODULE_COLORS, icon_provider=icon_for_tile
        )
        self.palette.chosen.connect(lambda key, _child: self.create_guides(key))

        self._connect_signals()

    def _build_side_pane(self, tiles) -> QtWidgets.QWidget:
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)
        header = QtWidgets.QLabel("SIDE")
        header.setObjectName("PaneHeader")
        left_layout.addWidget(header)
        self.side_combo = QtWidgets.QComboBox()
        self.side_combo.addItems(SIDES)
        self.side_combo.setToolTip(
            "Side of the modules you add next "
            "(Both = L and R, Auto = follow the selected module)"
        )
        left_layout.addWidget(self.side_combo)
        modules_header = QtWidgets.QLabel("MODULES")
        modules_header.setObjectName("PaneHeader")
        left_layout.addWidget(modules_header)
        self.shelf = TileGrid(
            tiles, MIME_MODULE, colors=MODULE_COLORS, icon_provider=icon_for_tile
        )
        self.shelf.activated.connect(lambda key: self.create_guides(key))
        left_layout.addWidget(self.shelf, 1)
        return left

    def _build_tree_pane(self) -> QtWidgets.QWidget:
        self.tree = GuideTree()
        self.tree_filter = FilterBar(
            placeholder="Filter modules…  (Enter to keep a keyword)"
        )
        tree_holder = QtWidgets.QWidget()
        tree_layout = QtWidgets.QVBoxLayout(tree_holder)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(6)
        tree_layout.addWidget(self.tree_filter)
        tree_layout.addWidget(self.tree, 1)
        self.tree_pane = pane("Tree", tree_holder)
        return self.tree_pane

    def _build_graph_pane(self) -> QtWidgets.QWidget:
        self.graph = GraphView(self.guides, events=self.events)
        self.graph_pane = pane("Graph", self.graph)
        return self.graph_pane

    def _build_copy_bar(self) -> QtWidgets.QWidget:
        """One tab per copy of the selected module, plus ``[+]``.

        This edits the ``copies`` *setting*. It is emphatically not a
        selection surface: the Designer has exactly one selectable thing and
        the tree owns it, so nothing here may touch ``_current`` or the tree.
        """
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.tab_bar = QtWidgets.QTabBar()
        self.tab_bar.setMovable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.add_copy_button = QtWidgets.QToolButton()
        self.add_copy_button.setText("+")
        self.add_copy_button.setAutoRaise(True)
        self.add_copy_button.setToolTip("Add another copy of this module")
        row.addWidget(self.tab_bar)
        row.addWidget(self.add_copy_button)
        row.addStretch(1)
        return holder

    def _build_properties_pane(self) -> QtWidgets.QWidget:
        self.properties = QtWidgets.QWidget()
        props = QtWidgets.QVBoxLayout(self.properties)
        props.setContentsMargins(12, 10, 12, 10)
        props.setSpacing(8)
        head = QtWidgets.QHBoxLayout()
        self.icon = QtWidgets.QLabel()
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("instance name")
        self.type_label = QtWidgets.QLabel("")
        self.type_label.setObjectName("PanelSubtitle")
        head.addWidget(self.icon)
        head.addWidget(self.name_edit, 1)
        head.addWidget(self.type_label)
        props.addLayout(head)
        self.multi_label = QtWidgets.QLabel("")
        self.multi_label.setObjectName("LinkedNote")
        self.multi_label.setVisible(False)
        props.addWidget(self.multi_label)
        props.addWidget(self._build_reference_strip())
        # Everything below here scrolls as one column, and its order is the
        # panel's whole claim about ownership: what is above the tab bar
        # belongs to the module, what is below belongs to the copy whose tab
        # is showing. Getting a widget on the wrong side of the bar is a lie
        # about the data, so the two captions name the halves explicitly.
        body = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)

        self.module_caption = QtWidgets.QLabel("MODULE")
        self.module_caption.setObjectName("FieldCaption")
        column.addWidget(self.module_caption)
        self.form = FormBuilder()
        column.addWidget(self.form)

        column.addWidget(self._build_copy_bar())

        self.copy_caption = QtWidgets.QLabel("COPY")
        self.copy_caption.setObjectName("FieldCaption")
        column.addWidget(self.copy_caption)
        self.inputs_caption = QtWidgets.QLabel("INPUTS")
        self.inputs_caption.setObjectName("FieldCaption")
        column.addWidget(self.inputs_caption)
        self.inputs_form = QtWidgets.QFormLayout()
        self.inputs_form.setContentsMargins(4, 0, 4, 4)
        column.addLayout(self.inputs_form)
        # A second form over the same target, showing the fields the module
        # author left to the copy -- which is all of them unless they said
        # ``shared=True``.
        self.copy_form = FormBuilder()
        column.addWidget(self.copy_form)
        column.addStretch(1)

        self.form_scroll = QtWidgets.QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.form_scroll.setWidget(body)
        props.addWidget(self.form_scroll, 1)
        self.scene_panel = SceneNodesPanel(picker=self._selected_scene_nodes)
        self.scene_panel.setVisible(False)
        props.addWidget(self.scene_panel, 1)
        return self.properties

    def _build_reference_strip(self) -> QtWidgets.QWidget:
        """Where a borrowed module came from, and what is local about it.

        An override is what quietly stops an upstream fix from arriving, so
        the panel has to say there is one and offer to give it back.
        """
        self.reference_strip = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(self.reference_strip)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.reference_label = QtWidgets.QLabel("")
        self.reference_label.setObjectName("LinkedNote")
        self.enabled_box = QtWidgets.QCheckBox("Build in this rig")
        self.enabled_box.setToolTip(
            "Unticked, this module stays in the session but is left out of "
            "the rig -- and stops being offered to a kinematics action."
        )
        self.enabled_box.toggled.connect(self.set_module_enabled)
        self.revert_button = QtWidgets.QPushButton("Revert to source")
        self.revert_button.setToolTip(
            "Discard every local change to this module and take what the "
            "referenced session says."
        )
        self.revert_button.clicked.connect(self.revert_module)
        row.addWidget(self.reference_label, 1)
        row.addWidget(self.enabled_box)
        row.addWidget(self.revert_button)
        self.reference_strip.setVisible(False)
        return self.reference_strip

    def _show_reference_strip(self, handle) -> None:
        """Fill the strip for ``handle``, or hide it for a local module."""
        entry = (
            self.guides.document.module(handle.instance_id)
            if handle is not None
            else None
        )
        if entry is None or entry.origin is None:
            self.reference_strip.setVisible(False)
            return
        files = {
            item.ref_id: Path(item.file).name
            for item in self.guides.document.references
        }
        overrides = _override_count(entry)
        text = f"from {files.get(entry.origin, 'another session')}"
        if overrides:
            plural = "" if overrides == 1 else "s"
            text += f" · {overrides} local override{plural}"
        self.reference_label.setText(text)
        self.revert_button.setEnabled(bool(overrides))
        self.enabled_box.blockSignals(True)
        self.enabled_box.setChecked(entry.enabled)
        self.enabled_box.blockSignals(False)
        self.reference_strip.setVisible(True)

    def _connect_signals(self) -> None:
        self.tree_filter.filter_changed.connect(self.apply_tree_filter)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        self.tree.reparent_requested.connect(self.reparent)
        self.tree.palette_requested.connect(self.show_palette)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.graph.palette_requested.connect(self.show_palette)
        self.graph.selection_changed.connect(self._on_graph_selection)
        self.graph.external_selection_changed.connect(self._on_external_selection)
        self.graph.frame_selection_changed.connect(self._on_frame_selection)
        self.graph.node_menu_requested.connect(
            lambda _key, pos: self.module_menu().exec(pos)
        )
        self.graph.edited.connect(self.refresh)
        self.action_bar.select_requested.connect(self.select_current)
        self.action_bar.mirror_requested.connect(self.mirror_current)
        self.action_bar.draw_selected_requested.connect(self.draw_selected)
        self.action_bar.draw_all_requested.connect(self.draw_all)
        self.action_bar.build_all_requested.connect(
            lambda: self.test_build(all_modules=True)
        )
        self.action_bar.sync_requested.connect(self.sync_now)
        self.action_bar.auto_sync_toggled.connect(self.set_auto_sync)
        self.action_bar.labels_toggled.connect(self.set_labels_visible)
        self.name_edit.editingFinished.connect(self._rename_current)
        # Each form names the object it edits, so the handler never has to
        # guess which one a field came from.
        self.form.changed.connect(
            lambda name, value: self._on_setting_changed(name, value, self._module_obj)
        )
        self.copy_form.changed.connect(
            lambda name, value: self._on_setting_changed(name, value, self._copy_obj)
        )
        self.tab_bar.currentChanged.connect(self._on_copy_tab_changed)
        self.tab_bar.tabMoved.connect(self._on_copy_tabs_reordered)
        self.tab_bar.tabBarDoubleClicked.connect(self._on_copy_tab_double_clicked)
        self.tab_bar.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tab_bar.customContextMenuRequested.connect(self._on_copy_tab_menu)
        self.add_copy_button.clicked.connect(self._on_add_copy)
        self.form.error.connect(
            lambda _name, message: self.events.log(message, level="warning")
        )
        self.scene_panel.changed.connect(self._on_scene_nodes_changed)
        # on the designer, not the tree: Delete has to work from the graph too
        delete = QtWidgets.QShortcut(
            QtGui.QKeySequence("Delete"), self, self.delete_current
        )
        delete.setContext(QtCore.Qt.WidgetWithChildrenShortcut)

    def _action(self, menu, text, slot, shortcut=None, checkable=False):
        action = menu.addAction(text)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        if checkable:
            action.setCheckable(True)
        return action

    def _build_actions(self) -> None:
        """The view toggles the designer owns.

        It builds no menu bar: the window has one, and a second ``QMenuBar``
        inside a ``QMainWindow`` subtree is not merely redundant -- it takes
        the process down. The verbs live on the window's Guides menu, which
        dispatches to whichever designer is in front.
        """

        def toggle(text, slot, shortcut=None):
            action = QtWidgets.QAction(text, self)
            action.setCheckable(True)
            action.setChecked(True)
            action.triggered.connect(slot)
            if shortcut:
                action.setShortcut(QtGui.QKeySequence(shortcut))
                action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
            return action

        self.tree_action = toggle(
            "Tree",
            lambda: self.set_pane_visible(self.tree_pane, self.tree_action.isChecked()),
        )
        self.graph_action = toggle(
            "Graph",
            lambda: self.set_pane_visible(
                self.graph_pane, self.graph_action.isChecked()
            ),
        )
        self.grid_action = toggle(
            "Grid", lambda: self.graph.set_grid(self.grid_action.isChecked()), "G"
        )
        self.snap_action = toggle(
            "Snap to Grid",
            lambda: self.graph.set_snap(self.snap_action.isChecked()),
            "Shift+G",
        )
        for action in (self.grid_action, self.snap_action):
            self.graph.addAction(action)

    def module_menu(self) -> QtWidgets.QMenu:
        """Right-click menu for the selected modules; shared by tree and graph."""
        menu = QtWidgets.QMenu(self)
        handles = self.selected_handles()
        menu.addAction("Select root", self.select_root)
        menu.addAction("Select all guides", self.select_current)
        menu.addSeparator()
        menu.addAction("Mirror", self.mirror_current)
        menu.addAction("Duplicate\tCtrl+D", self.duplicate_current)
        menu.addAction("Build", lambda: self.test_build())
        menu.addSeparator()
        menu.addAction("Sever connections", self.sever_current)
        menu.addAction("Disconnect primary input", self.disconnect_primary)
        menu.addSeparator()
        menu.addAction(
            "Rename", lambda: (self.name_edit.setFocus(), self.name_edit.selectAll())
        )
        menu.addAction("Delete", self.delete_current)
        for action in menu.actions():
            if not action.isSeparator():
                action.setEnabled(bool(handles))
        return menu

    def _tree_menu(self, point) -> None:
        item = self.tree.itemAt(point)
        if item is not None and not item.isSelected():
            self.tree.setCurrentItem(item)
        self.module_menu().exec(self.tree.viewport().mapToGlobal(point))

    def _build_status(self) -> None:
        self.status_strip = QtWidgets.QWidget()
        self.status = StatusFields(
            self.status_strip,
            ("session", "modules", "connections", "guides", "file"),
        )
        self.status.set_activity("Ready")

    def set_owner(self, name: str) -> None:
        """Name the session whose guides are checked out into the scene.

        With one Designer per session tab, "whose guides am I looking at?" must
        never need inference.
        """
        self.status.set("session", name or "")

    # ------------------------------------------------------------ state
    @property
    def side(self) -> str:
        """The side new modules get (``L`` when nothing is chosen)."""
        return self.side_combo.currentText() or "L"

    def set_side(self, side: str) -> None:
        """Pick ``side`` in the side combo, if it is one of the choices."""
        index = self.side_combo.findText(side)
        if index >= 0:
            self.side_combo.setCurrentIndex(index)

    @property
    def current(self) -> Optional[GuideHandle]:
        """The module whose properties are shown, or None."""
        return self._current

    def set_pane_visible(self, widget, visible: bool) -> None:
        """Show or hide one of the designer's panes."""
        widget.setVisible(visible)

    def selected_handles(self) -> list[GuideHandle]:
        """The modules selected in the tree."""
        handles = []
        for item in self.tree.selectedItems():
            handle = self.guides.get(item.data(0, QtCore.Qt.UserRole))
            if handle is not None:
                handles.append(handle)
        return handles

    def set_file(self, path: str) -> None:
        """Remember the guide library last imported or exported."""
        self.last_guide_file = path
        self.status.set("file", Path(path).name if path else "")

    # --------------------------------------------------------------- refresh
    def refresh(self, *_args) -> None:
        """Rebuild the tree and graph from the document and restore the selection."""
        if self._syncing:
            return
        self._syncing = True
        try:
            keep = [
                handle.instance_id
                for handle in (
                    self._multi or ([self._current] if self._current else [])
                )
            ]
            handles = self.guides.instances()
            by_key = {handle.key: handle for handle in handles}
            self._clear_tree()
            items: dict[str, QtWidgets.QTreeWidgetItem] = {}
            pending = list(handles)

            # parent in the tree = the primary input's producer
            def parent_key(handle):
                primary = handle.module_class.primary_input()
                source = handle.inputs.get(primary.name) if primary else None
                key, _output = split_source(source) if source else (None, None)
                return key if key in by_key else None

            while pending:
                remaining = []
                for handle in pending:
                    p_key = parent_key(handle)
                    if p_key and by_key[p_key].instance_id not in items:
                        remaining.append(handle)
                        continue
                    # the document entry, not a scene scan: the tree describes
                    # what the rig *is*, and one refresh reads the scene once
                    entry = handle.entry
                    module_cls = handle.module_class
                    label = module_cls.display_label()
                    if module_cls.guides.multi:
                        count = sum(
                            1
                            for role, _index in entry.pairs
                            if role == module_cls.guides.multi
                        )
                        label = f"{label} · {count}"
                    primary = module_cls.primary_input()
                    primary_text = (
                        handle.inputs.get(primary.name, "") if primary else ""
                    )
                    item = QtWidgets.QTreeWidgetItem(
                        [handle.key, label, entry.side, primary_text or "—"]
                    )
                    item.setData(0, QtCore.Qt.UserRole, handle.instance_id)
                    item.setIcon(0, module_icon(module_cls, side=entry.side, size=16))
                    item.setFlags(
                        item.flags()
                        | QtCore.Qt.ItemIsDragEnabled
                        | QtCore.Qt.ItemIsDropEnabled
                    )
                    if p_key:
                        items[by_key[p_key].instance_id].addChild(item)
                    else:
                        self.tree.addTopLevelItem(item)
                    items[handle.instance_id] = item
                if len(remaining) == len(pending):
                    for handle in remaining:  # cycles / unresolved: flat
                        item = QtWidgets.QTreeWidgetItem(
                            [
                                handle.key,
                                handle.module_class.display_label(),
                                handle.side.value,
                                "?",
                            ]
                        )
                        item.setData(0, QtCore.Qt.UserRole, handle.instance_id)
                        self.tree.addTopLevelItem(item)
                        items[handle.instance_id] = item
                    break
                pending = remaining
            # One diff, four consumers: the tree's dots, the graph's
            # stripes, the bar's colours and the status field. Computing it
            # per pane would let them disagree about the same module.
            try:
                diff = self.guides.diff()
            except Exception:  # noqa: BLE001 - a stub scene has no diff()
                diff = None
            states = states_from(diff) if diff is not None else {}
            # Provenance is a *document* fact, not a scene one, so it is read
            # here rather than folded into the diff: a borrowed module can be
            # not-drawn and overridden at once, and the two must not compete
            # for the same slot.
            document = self.guides.document
            entries = {entry.instance_id: entry for entry in document.modules}
            files = {item.ref_id: Path(item.file).name for item in document.references}
            for instance_id, item in items.items():
                state = states.get(instance_id, DRAWN)
                entry = entries.get(instance_id)
                origin = files.get(entry.origin) if entry is not None else None
                overrides = _override_count(entry)
                item.setData(0, DrawStateRole, state)
                item.setData(0, OriginRole, origin)
                item.setData(0, OverrideRole, overrides)
                item.setData(0, DisabledRole, entry is not None and not entry.enabled)
                item.setToolTip(0, _row_tooltip(state, origin, overrides, entry))
            self.tree.expandAll()
            self.apply_tree_filter()
            self.graph.set_draw_states(states)
            self.graph.rebuild()
            connections = self.guides.connections()
            externals = [
                item["source"]
                for item in connections
                if split_source(item["source"])[0] not in by_key
            ]
            missing = [
                name
                for name in externals
                if getattr(self.guides, "scene_node", lambda _n: True)(name) is None
            ]
            self.status.set("modules", f"{len(handles)} module(s)")
            notes = [f"{len(connections)} connection(s)"]
            if missing:
                notes.append(f"{len(missing)} missing scene node(s)")
            self.status.set("connections", " · ".join(notes))
            kept = [items[instance_id] for instance_id in keep if instance_id in items]
            if kept:
                self.tree.setCurrentItem(
                    kept[0], 0, QtCore.QItemSelectionModel.NoUpdate
                )
                for item in kept:
                    item.setSelected(True)
                self._select_handles(
                    [self.guides.get(item.data(0, QtCore.Qt.UserRole)) for item in kept]
                )
            elif (
                self._external is not None and self._external in self.graph.graph.nodes
            ):
                self.graph.select_key(self._external)
                self._set_current_external(self._external)
            else:
                self._set_current(None)
            if diff is not None:
                self._show_state(diff)
        finally:
            self._syncing = False

    def _clear_tree(self) -> None:
        """Drop every row without Qt signalling into a half-torn-down tree.

        PySide crashed on a plain ``clear()``.
        """
        tree = self.tree
        tree.blockSignals(True)
        try:
            tree.setCurrentItem(None)
            tree.clearSelection()
            while tree.topLevelItemCount():
                item = tree.takeTopLevelItem(0)
                item.takeChildren()
        finally:
            tree.blockSignals(False)

    def apply_tree_filter(self) -> None:
        """Hide rows that match no keyword; a row stays when any descendant matches."""
        model = self.tree_filter.model

        def visit(item) -> bool:
            text = " ".join(item.text(column) for column in range(item.columnCount()))
            shown = model.matches(text)
            for index in range(item.childCount()):
                shown = visit(item.child(index)) or shown
            item.setHidden(not shown)
            return shown

        for index in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(index))
        hidden = 0
        iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            hidden += iterator.value().isHidden()
            iterator += 1
        total = len(self.guides.instances())
        self.status.set(
            "modules",
            (
                f"{total - hidden} of {total} module(s)"
                if model.is_active
                else f"{total} module(s)"
            ),
        )

    def item_for(self, instance_id: str) -> Optional[QtWidgets.QTreeWidgetItem]:
        """The tree item of ``instance_id``, or None."""
        iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, QtCore.Qt.UserRole) == instance_id:
                return item
            iterator += 1
        return None

    # ----------------------------------------------------------- selection
    def _select_handles(
        self, handles: list[GuideHandle], sync_graph: bool = True
    ) -> None:
        """Properties for one module, or several of one type edited together."""
        handles = [handle for handle in handles if handle is not None]
        if sync_graph:
            self.graph.select_keys([handle.key for handle in handles])
        if len(handles) <= 1:
            self._set_current(handles[0] if handles else None)
            return
        types = {handle.module_type for handle in handles}
        if len(types) == 1:
            self._set_current(handles[0], group=handles)
        else:
            self._set_current(None)
            self.multi_label.setText(
                f"{len(handles)} modules of {len(types)} different types "
                "— nothing to edit together."
            )
            self.multi_label.setVisible(True)
            self.status.set_activity(f"{len(handles)} modules selected (mixed types)")

    def _on_tree_selection(self) -> None:
        if self._syncing:
            return
        self._select_handles(self.selected_handles())

    def _on_frame_selection(self, ref_id: str) -> None:
        """A collapsed reference is not a module and has no properties.

        Clearing beats leaving the previous module's panel up, which would
        read as though the selection had not changed at all.
        """
        self._set_current(None)
        self.status.set_activity("Collapsed reference — click its glyph to expand it.")

    def _on_external_selection(self, name: str) -> None:
        self._syncing = True
        try:
            self.tree.clearSelection()
        finally:
            self._syncing = False
        self._set_current_external(name)

    def _set_current_external(self, name: str) -> None:
        """Properties for a scene-nodes group: its name and the nodes it exposes."""
        self._set_current(None)
        self._external = name
        self.name_edit.setText(name)
        self.name_edit.setEnabled(True)
        self.name_edit.setPlaceholderText("scene nodes group name")
        self.type_label.setText("Scene nodes")
        self.icon.setPixmap(glyph_icon("SN", MODULE_COLORS["scene"], 24).pixmap(24, 24))
        # A scene-nodes group is not a module: it has no fields, no copies
        # and no inputs, so the whole scrolling column goes away.
        for widget in (self.inputs_caption, self.copy_caption, self.form_scroll):
            widget.setVisible(False)
        self.scene_panel.set_nodes(self.guides.scene_groups().get(name, []))
        self.scene_panel.setVisible(True)
        self.status.set_activity(
            f"{name} — scene nodes (each row is an output; Delete removes the group)"
        )

    def _on_graph_selection(self, key: str) -> None:
        handle = self.guides.by_key(key)
        if handle is None:
            return
        selected = {node.key for node in self.graph.graph.selected_nodes()}
        self._syncing = True
        try:
            self.tree.clearSelection()
            first = None
            for item_handle in self.guides.instances():
                if item_handle.key in selected:
                    item = self.item_for(item_handle.instance_id)
                    if item is not None:
                        item.setSelected(True)
                        first = first or item
            if first is not None:
                self.tree.setCurrentItem(
                    first, 0, QtCore.QItemSelectionModel.NoUpdate
                )  # keep the others selected
        finally:
            self._syncing = False
        handles = self.selected_handles() or [handle]
        self._select_handles(
            handles, sync_graph=False
        )  # never fight a rubber band in progress

    def _on_scene_event(self, name: str) -> None:
        if name == "SelectionChanged":
            return  # selection is not synced; structure changes are
        if not self.guides.auto_sync:
            # Look, do not touch: report the state and leave the document
            # alone until the rigger presses Sync.
            self._show_state(self.guides.diff())
            return
        # Sync itself cannot touch the scene any more, but the refresh that
        # follows repaints from it, and muting keeps that off the watcher.
        with self.watcher.mute():
            try:
                self.guides.sync()
            except Exception as error:  # noqa: BLE001 - keep the tool alive
                self.events.log(f"Guide sync failed: {error}", level="warning")
        self.refresh()

    def _show_state(self, diff) -> None:
        """Drive every indicator from one diff.

        One scan, four consumers -- the bar, the tree, the graph and the
        status field -- which is what stops the panes disagreeing about what
        is in the scene.
        """
        if self._torn_down:
            return
        selected = {handle.instance_id for handle in self.selected_handles()}
        stale = set(diff.stale)
        self.action_bar.set_pending(
            stale_selected=bool(stale & selected),
            stale_any=bool(stale),
            moved=bool(diff.drifted),
        )
        self.status.set("guides", diff_summary(diff) or "up to date")

    def refresh_drift(self) -> None:
        """Recompute every indicator for whatever the scene looks like now.

        Dragging a guide fires nothing in Maya, so ``_on_scene_event`` never
        sees it and the "moved" half of the report is otherwise unreachable
        except by coincidence. The real workflow is "drag guides in the
        viewport, look back at the Designer", so this runs from ``showEvent``
        (and is mirrored in ``SessionView`` for the sub-tab switch, since a
        page hidden behind another tab does not always get a synchronous show
        event the first time it is built) -- one ``diff()`` per look, not a
        timer and not every ``SelectionChanged``, which would mean a full
        scene snapshot on every viewport click.

        Unlike before, this runs whatever Auto is set to: Auto only governs
        Sync, and the *Draw* side of the report has to stay current either
        way.
        """
        if self._torn_down:
            return
        try:
            self._show_state(self.guides.diff())
        except Exception:  # noqa: BLE001 - a stub scene has no diff()
            pass

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh_drift()

    # --------------------------------------------------------------- copies
    def input_port(self, input_name: str) -> str:
        """The qualified port on the current copy: ``root`` / ``c1_root``."""
        if self._module_obj is None:
            return input_name
        return type(self._module_obj).qualify(self.current_slug(), input_name)

    def current_slug(self) -> str:
        """Slug of the copy whose tab is showing; ``""`` when there is none."""
        if self._module_obj is None:
            return copy_list.EMPTY_SLUG
        slugs = self._module_obj.copy_slugs()
        index = self.tab_bar.currentIndex()
        return slugs[index] if 0 <= index < len(slugs) else slugs[0]

    def _rebuild_copy_tabs(self, current: Optional[int] = None) -> None:
        """One tab per copy. Signals blocked: this reflects state, never sets it.

        ``current`` defaults to whichever tab is already showing, so a refresh
        provoked by editing a copy does not throw the rigger back to the first
        one mid-edit.
        """
        if current is None:
            current = self.tab_bar.currentIndex()
        self.tab_bar.blockSignals(True)
        try:
            while self.tab_bar.count():
                self.tab_bar.removeTab(0)
            if self._module_obj is not None:
                for row in self._module_obj.copy_rows():
                    self.tab_bar.addTab(copy_list.copy_name(row, self._module_obj.name))
            if 0 <= current < self.tab_bar.count():
                self.tab_bar.setCurrentIndex(current)
        finally:
            self.tab_bar.blockSignals(False)
        self.add_copy_button.setEnabled(self._module_obj is not None)

    def _write_copies(self, rows, current: int = 0) -> None:
        """Store the copy list on the module and redraw the bar and form."""
        if self._current is None or self._module_obj is None:
            return
        rows = [dict(row) for row in rows]
        module_cls = type(self._module_obj)
        with self.watcher.mute():
            if len(rows) == 1:
                # One copy is just the module. Storing a copies list here
                # would strand the module-level fields: `handle.segments`
                # would read 2 while the rig built 4, and every existing
                # reader of settings["segments"] would be quietly wrong.
                for name in module_cls.per_copy_fields():
                    if name in rows[0]:
                        setattr(self._module_obj, name, rows[0][name])
                        setattr(self._current, name, rows[0][name])
                self._module_obj.copies = []
                self._current.copies = []
            else:
                self._module_obj.copies = rows
                self._current.copies = rows
        # refresh() runs _set_current, which rebuilds the bar at index 0, so
        # the wanted tab is chosen *after* it rather than before.
        self.refresh()
        self._rebuild_copy_tabs(current)
        self._show_copy_values()

    def _split_forms(self) -> None:
        """Per-copy fields into the tab form, the rest into the module form.

        By declaration, not by comparing values: ``per_copy`` is a fact about
        what a field *means*, so a field never moves between the two while the
        rigger is typing.
        """
        if self._module_obj is None:
            return
        module_cls = type(self._module_obj)
        per_copy = list(module_cls.per_copy_fields())
        # ``copies`` is hidden and always shared, so it never counts as
        # something to show: a module that shares nothing else hides the
        # whole MODULE half rather than captioning an empty box.
        shared = [
            name
            for name, field in module_cls.shared_fields().items()
            if not field.hidden
        ]
        self.form.set_visible_fields(shared)
        self.form.setVisible(bool(shared))
        self.module_caption.setVisible(bool(shared))
        self.copy_form.setVisible(bool(per_copy))

    def _show_copy_values(self) -> None:
        """Point the copy form at the current copy, as a module of its own.

        A *view* rather than the module with values poked into it, because
        the form asks its target to resolve ``choices_from``: on the module
        that yields every copy's controls (``ik``, ``c1_ik``, ``c2_ik``), and
        on the view it yields the copy's own (``ik``). A control list that
        grows with every copy is the same scope leak in the panel that the
        qualified roles were in the scene.
        """
        if self._module_obj is None:
            self._copy_obj = None
            return
        try:
            self._copy_obj = self._module_obj.for_copy(self.current_slug())
        except TriggerError:
            self._copy_obj = None
            return
        self.copy_form.set_target(self._copy_obj)
        self.copy_form.set_visible_fields(
            list(type(self._module_obj).per_copy_fields())
        )

    def _on_copy_tab_changed(self, _index: int) -> None:
        """Show another copy's values and connections.

        Touches no selection, by design: this is a settings field's editor.
        """
        self._show_copy_values()
        self._show_copy_inputs()

    def _show_copy_inputs(self) -> None:
        """Point every input row at the current copy's port."""
        if self._current is None:
            return
        sources = self._current.inputs
        for name, row in self._input_rows.items():
            row.blockSignals(True)
            row.line.blockSignals(True)
            try:
                row.set_source(sources.get(self.input_port(name), ""))
            finally:
                row.line.blockSignals(False)
                row.blockSignals(False)

    def _on_add_copy(self) -> None:
        """The ``[+]`` verb: duplicate the current copy and select its tab."""
        if self._module_obj is None:
            return
        rows = self._module_obj.copy_rows()
        taken = {copy_list.copy_name(row, self._module_obj.name) for row in rows}
        try:
            made = copy_list.duplicate_row(
                rows,
                self.current_slug(),
                type(self._module_obj).per_copy_defaults(self._module_obj.values()),
                taken,
                base=self._module_obj.name,
            )
        except TriggerError as error:
            self.events.log(str(error), level="warning")
            return
        self._write_copies(rows + [made], current=len(rows))

    def _on_remove_copy(self) -> None:
        """Drop the current copy. The last one stays: a module is a copy."""
        if self._module_obj is None:
            return
        rows = self._module_obj.copy_rows()
        if len(rows) < 2:
            self.events.log("A module always has at least one copy.", level="warning")
            return
        slug = self.current_slug()
        kept = [row for row in rows if row["slug"] != slug]
        self._write_copies(kept, current=0)

    def _on_copy_tab_double_clicked(self, index: int) -> None:
        rows = self._module_obj.copy_rows() if self._module_obj else []
        if not 0 <= index < len(rows):
            return
        entered = Feedback(parent=self).ask_text(
            title="Rename copy",
            label="Name:",
            text=copy_list.copy_name(rows[index], self._module_obj.name),
        )
        if entered:
            self._on_copy_renamed(index, entered)

    def _on_copy_renamed(self, index: int, text: str) -> None:
        """Rename one copy, refusing a name another copy already holds.

        Refused here rather than caught at build time: two copies with one
        name build their controls over each other, and the rigger should
        hear about it while they are typing, not three steps later.
        """
        if self._module_obj is None or not text:
            return
        rows = self._module_obj.copy_rows()
        if not 0 <= index < len(rows):
            return
        taken = {
            copy_list.copy_name(row, self._module_obj.name)
            for position, row in enumerate(rows)
            if position != index
        }
        if text in taken:
            self.events.log(
                f"'{text}' is already the name of another copy of "
                f"'{self._module_obj.name}'.",
                level="warning",
            )
            self._rebuild_copy_tabs(index)
            return
        rows[index]["name"] = text
        self._write_copies(rows, current=index)

    def _on_copy_tabs_reordered(self, to_index: int, from_index: int) -> None:
        """Store the tab order back as the copy order."""
        if self._module_obj is None:
            return
        rows = self._module_obj.copy_rows()
        if not (0 <= from_index < len(rows) and 0 <= to_index < len(rows)):
            return
        rows.insert(to_index, rows.pop(from_index))
        self._write_copies(rows, current=to_index)

    def copy_tab_menu(self) -> QtWidgets.QMenu:
        """The tab bar's right-click menu."""
        menu = QtWidgets.QMenu(self)
        menu.addAction("Add Copy", self._on_add_copy)
        rows = self._module_obj.copy_rows() if self._module_obj else []
        remove = menu.addAction("Remove Copy", self._on_remove_copy)
        remove.setEnabled(len(rows) > 1)
        return menu

    def _on_copy_tab_menu(self, point) -> None:
        index = self.tab_bar.tabAt(point)
        if index >= 0:
            self.tab_bar.setCurrentIndex(index)
        self.copy_tab_menu().exec_(self.tab_bar.mapToGlobal(point))

    # ---------------------------------------------------------- properties
    def _set_current(
        self, handle: Optional[GuideHandle], group: Optional[list[GuideHandle]] = None
    ) -> None:
        self._current = handle
        self._multi = list(group or [])
        self._external = None
        self.bindings.clear()
        for row in self._input_rows.values():
            row.blockSignals(True)
            row.line.blockSignals(True)
        while self.inputs_form.count():
            item = self.inputs_form.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
                item.widget().deleteLater()
        self._input_rows.clear()
        self.scene_panel.setVisible(False)
        for widget in (self.copy_caption, self.form_scroll):
            widget.setVisible(True)
        self.multi_label.setVisible(False)
        self.name_edit.setEnabled(True)
        self.name_edit.setPlaceholderText("instance name")
        if handle is None:
            self._module_obj = None
            self.reference_strip.setVisible(False)
            self.form.set_target(None)
            self.copy_form.set_target(None)
            self._rebuild_copy_tabs(0)
            self.name_edit.setText("")
            self.type_label.setText("")
            self.icon.clear()
            self.inputs_caption.setVisible(False)
            self.status.set_activity(
                "Select a module, or add one from the shelf (Tab to search)."
            )
            self.action_bar.set_selection_enabled(False)
            return
        entry = handle.entry
        module_cls = handle.module_class
        self._module_obj = module_cls(
            name=entry.name, side=entry.side, settings=entry.settings
        )
        self.name_edit.setText(entry.name)
        self.type_label.setText(f"{module_cls.display_label()} · {entry.side}")
        self.icon.setPixmap(
            module_icon(module_cls, side=entry.side, size=24).pixmap(24, 24)
        )
        multi = len(self._multi) > 1
        if multi:
            self.name_edit.setEnabled(False)
            self.name_edit.setText(", ".join(item.key for item in self._multi))
            self.multi_label.setText(
                f"Editing {len(self._multi)} {module_cls.display_label()} "
                "modules together — every change applies to all of them."
            )
            self.multi_label.setVisible(True)
            self.inputs_caption.setVisible(False)
        else:
            declared_inputs = list(module_cls.inputs) + module_cls.space_inputs(
                handle.settings
            )
            for declared in declared_inputs:
                row = InputRow(
                    declared, picker=self._pick_source, sources=self._source_choices
                )
                # The *current copy's* connection: each copy owns its inputs,
                # so the row shows and writes the port for the tab showing.
                row.set_source(handle.inputs.get(self.input_port(declared.name), ""))
                row.changed.connect(self._on_input_changed)
                label = declared.name + (" ●" if declared.primary else "")
                self.inputs_form.addRow(label, row)
                self._input_rows[declared.name] = row
            self.inputs_caption.setVisible(bool(declared_inputs))
        self.form.set_target(self._module_obj)
        self._split_forms()
        self._rebuild_copy_tabs()
        self._show_copy_values()
        # After the bar, not before: the input rows above were built from
        # whatever tab was showing a moment ago, and the bar may have landed
        # on a different one.
        self._show_copy_inputs()
        self._show_reference_strip(handle)
        if multi:
            self.status.set_activity(
                f"{len(self._multi)} × {module_cls.display_label()} selected"
            )
        else:
            self.status.set_activity(f"{handle.key} — {module_cls.display_label()}")
        selected = self._multi or ([handle] if handle else [])
        self.action_bar.set_selection_enabled(bool(selected))
        # "Draw selected" lights only when *the selection* is out of date, so
        # the two Draw buttons answer different questions.
        try:
            diff = self.guides.diff()
        except Exception:  # noqa: BLE001 - a stub scene has no diff()
            return
        stale = set(diff.stale)
        self.action_bar.set_pending(
            stale_selected=bool(stale & {item.instance_id for item in selected}),
            stale_any=bool(stale),
            moved=bool(diff.drifted),
        )

    # -------------------------------------------------------------- teardown
    def teardown(self) -> None:
        """Release bindings and scene jobs. Safe to call more than once.

        A page never gets its own close event, so the host calls this; the
        close event below still fires when the designer is shown as a window.
        """
        if self._torn_down:
            return
        self._torn_down = True
        self.bindings.clear()
        self.watcher.uninstall()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.teardown()
        super().closeEvent(event)
