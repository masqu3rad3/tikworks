"""The Guide Designer's bottom bar (spec 8).

Two directions, one at each end, with a rule between them. The caption on each
end names where that group's data *lands*, so "which button writes to my
scene?" is answerable from the bar alone, without reading a spec::

    -> SCENE     Draw    the session into Maya
    -> SESSION   Sync    Maya back into the session

What is deliberately absent is as much of the design as what is here. There is
no selection label -- the tree and the graph already show the selection -- and
no count pills: the button's colour says there is work pending in that
direction, the tree and graph say *which* modules, and the status bar carries
the numbers. Nothing on the bar repeats what a panel already shows.

The bar knows nothing about the scene: it emits, the Designer acts.
"""

from __future__ import annotations

from tik.shared.ui.Qt import QtCore, QtWidgets


class DesignerActionBar(QtWidgets.QFrame):
    """The full-width action row under the Designer's four panes."""

    draw_selected_requested = QtCore.Signal()
    draw_all_requested = QtCore.Signal()
    select_requested = QtCore.Signal()
    mirror_requested = QtCore.Signal()
    sync_requested = QtCore.Signal()
    auto_sync_toggled = QtCore.Signal(bool)
    build_all_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # the Session sub-tab's build bar wears the same object name; one look
        # for both sub-tabs is the point
        self.setObjectName("BuildBar")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)

        layout.addWidget(self._caption("→ SCENE"))
        self.draw_selected_button = QtWidgets.QPushButton("Draw selected")
        self.draw_selected_button.setToolTip(
            "Draw the selected modules' guides into the scene"
        )
        self.draw_all_button = QtWidgets.QPushButton("Draw all")
        self.draw_all_button.setToolTip("Draw every module's guides into the scene")
        layout.addWidget(self.draw_selected_button)
        layout.addWidget(self.draw_all_button)

        self.selection_rule = self._rule()
        layout.addWidget(self.selection_rule)
        self.select_button = QtWidgets.QPushButton("Select")
        self.select_button.setToolTip("Select the selected modules' guides in Maya")
        self.mirror_button = QtWidgets.QPushButton("Mirror")
        self.mirror_button.setToolTip("Mirror the selected modules to the other side")
        layout.addWidget(self.select_button)
        layout.addWidget(self.mirror_button)

        layout.addStretch(1)

        layout.addWidget(self._caption("→ SESSION"))
        self.sync_button = QtWidgets.QPushButton("Sync")
        self.sync_button.setObjectName("SyncButton")
        self.sync_button.setToolTip("Read the guides in the scene into this session")
        layout.addWidget(self.sync_button)
        self.auto_check = QtWidgets.QCheckBox("Auto")
        self.auto_check.setChecked(True)
        self.auto_check.setToolTip(
            "Follow the scene automatically. "
            "Off, the session updates only when you press Sync."
        )
        layout.addWidget(self.auto_check)

        self.build_rule = self._rule()
        layout.addWidget(self.build_rule)
        self.build_all_button = QtWidgets.QPushButton("▶  Build all")
        self.build_all_button.setObjectName("PrimaryButton")
        self.build_all_button.setToolTip(
            "Sync, draw anything missing or out of date, then build"
        )
        layout.addWidget(self.build_all_button)

        self.draw_selected_button.clicked.connect(self.draw_selected_requested)
        self.draw_all_button.clicked.connect(self.draw_all_requested)
        self.select_button.clicked.connect(self.select_requested)
        self.mirror_button.clicked.connect(self.mirror_requested)
        self.sync_button.clicked.connect(self.sync_requested)
        self.auto_check.toggled.connect(self.auto_sync_toggled)
        self.build_all_button.clicked.connect(self.build_all_requested)

        self.set_selection_enabled(False)
        self.set_pending(False, False, False)
        self.set_auto_sync(True)

    @staticmethod
    def _caption(text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setObjectName("FieldCaption")
        return label

    @staticmethod
    def _rule() -> QtWidgets.QFrame:
        # a QFrame.VLine here does not paint under QSS `color:` and ignores
        # `max-width`; a plain QFrame with an explicit fixed width is what
        # actually renders a crisp 1px divider
        rule = QtWidgets.QFrame()
        rule.setObjectName("BarRule")
        rule.setMinimumWidth(1)
        rule.setMaximumWidth(1)
        return rule

    # ------------------------------------------------------------- state
    def set_selection_enabled(self, on: bool) -> None:
        """Enable the three controls that act on the selected modules."""
        for button in (
            self.draw_selected_button,
            self.select_button,
            self.mirror_button,
        ):
            button.setEnabled(bool(on))

    def set_pending(self, stale_selected: bool, stale_any: bool, moved: bool) -> None:
        """Colour each end for the work waiting in *its* direction.

        Out of date only. Not-drawn deliberately lights nothing: a freshly
        opened session is entirely not-drawn, and that is its resting state,
        not a warning. Out of date means the scene *contradicts* the session;
        not drawn means the scene is merely silent, and silence does not earn
        colour.
        """
        self._set_alert(self.draw_selected_button, stale_selected)
        self._set_alert(self.draw_all_button, stale_any)
        self._set_alert(self.sync_button, moved)

    def set_auto_sync(self, on: bool) -> None:
        """Reflect the setting without reporting it back as a user action.

        The menu action and this checkbox are one setting with two front
        doors; without the block they would ping-pong.
        """
        self.auto_check.blockSignals(True)
        try:
            self.auto_check.setChecked(bool(on))
        finally:
            self.auto_check.blockSignals(False)
        self.sync_button.setProperty("quiet", bool(on))
        self._repolish(self.sync_button)

    @classmethod
    def _set_alert(cls, button, on: bool) -> None:
        button.setProperty("alert", bool(on))
        cls._repolish(button)

    @staticmethod
    def _repolish(widget) -> None:
        """Qt does not restyle on a property change unless asked."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)
