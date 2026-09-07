"""The Switches dock: four fixed zones, one tab per switch.

The shell owns the chips, the keying, the frame scope and the status line.
A switch supplies states, the current one, and what to do -- so a new tab adds
labels rather than a user interface.

Nothing here touches Maya. The scene is reached in exactly two places, both
behind ``HAS_MAYA``: the selection watcher that feeds :meth:`set_context`, and
the default ``times_provider``. That is what lets ``tests/ui`` drive the whole
window offscreen against a fabricated context.
"""

from __future__ import annotations

from typing import Optional

from tik.shared.ui import theme
from tik.shared.ui.maya_window import HAS_MAYA, MayaToolWindow
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets

from .context import SwitchContext
from .registry import iter_switches

PLACEHOLDER_NOTE = "Not built yet."
EMPTY_NOTE = "Select a rig control. Switches follow whatever is selected."


def dot_icon(color: str, size: int = 10) -> QtGui.QIcon:
    """A filled circle, for a tab's availability marker."""
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor(color))
    inset = size / 3.0
    painter.drawEllipse(QtCore.QRectF(inset, inset, size - inset * 2, size - inset * 2))
    painter.end()
    return QtGui.QIcon(pixmap)


class SwitchesWindow(MayaToolWindow):
    """A non-modal, dockable picker for the switches a selection can use."""

    WINDOW_NAME = "TikSwitchesWindow"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Switches")
        self.setStyleSheet(theme.stylesheet())

        self._switches = [cls() for cls in iter_switches()]
        self._context = SwitchContext()
        self._states: list[str] = []
        self._current: Optional[str] = None
        self._pending: Optional[str] = None
        self._chips: list[QtWidgets.QPushButton] = []
        #: Replaced by tests; the default is the only other Maya reach here.
        self.times_provider = self._scene_times

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)

        self._build_tabs(layout)
        self._build_context(layout)
        self._build_body(layout)
        self._build_bar(layout)

        self.resize(380, 430)
        self._install_watcher()
        self.set_context(SwitchContext())

    # ------------------------------------------------------------- building
    def _build_tabs(self, layout) -> None:
        self.tabs = QtWidgets.QTabBar()
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.setIconSize(QtCore.QSize(10, 10))
        for switch in self._switches:
            self.tabs.addTab(switch.display_label())
        self.tabs.currentChanged.connect(lambda _index: self._refresh())
        layout.addWidget(self.tabs)

    def _build_context(self, layout) -> None:
        frame = QtWidgets.QFrame()
        frame.setObjectName("SwitchContext")
        row = QtWidgets.QHBoxLayout(frame)
        row.setContentsMargins(10, 7, 10, 7)
        row.setSpacing(8)
        self.side_strip = QtWidgets.QLabel()
        self.side_strip.setObjectName("SwitchSides")
        self.context_label = QtWidgets.QLabel()
        self.context_label.setObjectName("SwitchName")
        self.module_label = QtWidgets.QLabel()
        self.module_label.setObjectName("SwitchNote")
        row.addWidget(self.side_strip)
        row.addWidget(self.context_label, 1)
        row.addWidget(self.module_label)
        layout.addWidget(frame)

    def _build_body(self, layout) -> None:
        body = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(body)
        column.setContentsMargins(10, 12, 10, 12)
        column.setSpacing(9)
        self.body_caption = QtWidgets.QLabel()
        self.body_caption.setObjectName("PaneHeader")
        column.addWidget(self.body_caption)
        self.chip_row = QtWidgets.QHBoxLayout()
        self.chip_row.setSpacing(6)
        self.chip_row.addStretch(1)
        column.addLayout(self.chip_row)
        self.body_note = QtWidgets.QLabel()
        self.body_note.setObjectName("SwitchNote")
        self.body_note.setWordWrap(True)
        column.addWidget(self.body_note)
        column.addStretch(1)
        layout.addWidget(body, 1)

    def _build_bar(self, layout) -> None:
        bar = QtWidgets.QFrame()
        bar.setObjectName("SwitchBar")
        column = QtWidgets.QVBoxLayout(bar)
        column.setContentsMargins(10, 7, 10, 7)
        column.setSpacing(6)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        self.key_box = QtWidgets.QCheckBox("Key")
        self.key_box.setChecked(True)
        row.addWidget(self.key_box)
        row.addStretch(1)
        self.frame_button = QtWidgets.QPushButton("Frame")
        self.range_button = QtWidgets.QPushButton("Range")
        self.scope_group = QtWidgets.QButtonGroup(self)
        self.scope_group.setExclusive(True)
        for button in (self.frame_button, self.range_button):
            button.setObjectName("SwitchChip")
            button.setCheckable(True)
            self.scope_group.addButton(button)
            row.addWidget(button)
        self.frame_button.setChecked(True)
        self.apply_button = QtWidgets.QPushButton("Apply")
        self.apply_button.setObjectName("PrimaryButton")
        self.apply_button.clicked.connect(self.apply)
        row.addWidget(self.apply_button)
        column.addLayout(row)

        status = QtWidgets.QHBoxLayout()
        status.setSpacing(7)
        self.status_dot = QtWidgets.QLabel()
        self.status_dot.setFixedSize(8, 8)
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setObjectName("SwitchNote")
        status.addWidget(self.status_dot)
        status.addWidget(self.status_label, 1)
        column.addLayout(status)
        layout.addWidget(bar)
        self._set_status("", "")

    # -------------------------------------------------------------- reading
    @property
    def switch(self):
        """The switch behind the current tab."""
        index = self.tabs.currentIndex()
        return self._switches[index] if 0 <= index < len(self._switches) else None

    @property
    def states(self) -> list[str]:
        """The states the current tab offers for the current context."""
        return list(self._states)

    @property
    def current(self) -> Optional[str]:
        """The state the selection is in; None when it has none or they differ."""
        return self._current

    @property
    def pending(self) -> Optional[str]:
        """The state chosen but not yet applied."""
        return self._pending

    @property
    def can_apply(self) -> bool:
        """True when a pending state differs from the current one."""
        return bool(self._pending) and self._pending != self._current

    # -------------------------------------------------------------- writing
    def set_context(self, context: SwitchContext) -> None:
        """Render ``context``: tab availability, the selection strip, the chips."""
        self._context = context
        self._pending = None
        self._refresh_tabs()
        self._refresh()

    def choose(self, state: str) -> None:
        """Mark ``state`` pending. Choosing the current state clears it."""
        self._pending = None if state == self._current else state
        self._paint_chips()
        self._refresh_apply()

    def apply(self) -> None:
        """Run the pending switch on the current context."""
        if not self.can_apply:
            return
        switch, state = self.switch, self._pending
        report = switch.apply(
            self._context,
            state,
            key=self.key_box.isChecked(),
            times=self.times_provider(),
        )
        self._pending = None
        self._refresh()
        self._set_status(report, "done")

    def set_playback_range(self, start: float, end: float) -> None:
        """Name the range on its button, so the scope is never a mystery."""
        self.range_button.setText(f"Range {start:g}–{end:g}")

    # ------------------------------------------------------------ internals
    def _refresh_tabs(self) -> None:
        for index, switch in enumerate(self._switches):
            lit = bool(switch.available and switch.states(self._context))
            colour = theme.ACCENT if lit else theme.STATUS[""]
            self.tabs.setTabIcon(index, dot_icon(colour))

    def _refresh(self) -> None:
        switch = self.switch
        self._states = list(switch.states(self._context)) if switch else []
        self._current = switch.current(self._context) if switch else None
        if self._pending not in self._states:
            self._pending = None
        self._paint_context()
        self._paint_chips()
        self._paint_note()
        self._refresh_apply()

    def _paint_context(self) -> None:
        context = self._context
        if context.is_empty:
            self.side_strip.setText("")
            self.context_label.setText("Nothing selected")
            self.module_label.setText("")
            return
        marks = "".join(
            f'<span style="color:{theme.SIDE.get(side, theme.SIDE["C"])}">▌</span>'
            for side in context.sides
        )
        self.side_strip.setText(marks)
        controls = context.controls
        if len(controls) == 1:
            self.context_label.setText(controls[0].node.rsplit("|", 1)[-1])
        else:
            self.context_label.setText(f"{len(controls)} controls")
        self.module_label.setText(", ".join(context.keys))

    def _paint_chips(self) -> None:
        while self._chips:
            chip = self._chips.pop()
            self.chip_row.removeWidget(chip)
            chip.deleteLater()
        for position, state in enumerate(self._states):
            chip = QtWidgets.QPushButton(state)
            chip.setObjectName("SwitchChip")
            chip.setCheckable(True)
            if state == self._pending:
                chip.setProperty("state", "pending")
                chip.setChecked(True)
            elif state == self._current:
                chip.setProperty("state", "current")
                chip.setChecked(True)
            elif self._current is None and not self._context.is_empty:
                chip.setProperty("state", "mixed")
            chip.clicked.connect(lambda _checked=False, name=state: self.choose(name))
            self.chip_row.insertWidget(position, chip)
            self._chips.append(chip)

    def _paint_note(self) -> None:
        switch = self.switch
        if switch is None:
            self.body_caption.setText("")
            self.body_note.setText("")
            return
        self.body_caption.setText(switch.display_label().upper())
        if not switch.available:
            self.body_note.setText(f"{PLACEHOLDER_NOTE} {switch.help}")
        elif self._context.is_empty:
            self.body_note.setText(EMPTY_NOTE)
        elif not self._states:
            self.body_note.setText(
                f"Nothing selected can use this switch. {switch.help}"
            )
        else:
            self.body_note.setText(switch.help)

    def _refresh_apply(self) -> None:
        self.apply_button.setEnabled(self.can_apply)
        for chip in self._chips:
            chip.style().unpolish(chip)
            chip.style().polish(chip)

    def _set_status(self, text: str, tone: str) -> None:
        self.status_label.setText(text)
        colour = theme.STATUS.get(tone, theme.STATUS[""])
        self.status_dot.setStyleSheet(
            f"background-color: {colour}; border-radius: 4px;"
        )

    # ----------------------------------------------------------------- maya
    def _install_watcher(self) -> None:
        """Follow the selection. Undo and Redo are in the list because undoing
        a switch changes a control's state, and the chips would go stale."""
        if not HAS_MAYA:
            return
        from tik.shared.ui.scene_watcher import SceneWatcher

        self._watcher = SceneWatcher(
            lambda _event: self.set_context(SwitchContext.from_scene()),
            events=("SelectionChanged", "Undo", "Redo"),
            parent=self,
        )
        self._watcher.install()
        for job in getattr(self._watcher, "jobs", ()):
            self.register_script_job(job)
        self.set_context(SwitchContext.from_scene())

    def _scene_times(self) -> tuple:
        """Frame: now. Range: every key on any channel of the selection."""
        if not HAS_MAYA:
            return (0.0,)
        import tik.maya as tm
        from tik.trigger.maya import pivot as ops

        if not self.range_button.isChecked():
            return (float(tm.currentTime(query=True)),)
        start, end = ops.playback_range()
        self.set_playback_range(start, end)
        found: set = set()
        for control in self._context.controls:
            found.update(ops.key_times(control.node, start, end))
        return tuple(sorted(found)) or (float(tm.currentTime(query=True)),)
