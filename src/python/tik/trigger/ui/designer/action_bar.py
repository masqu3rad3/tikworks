"""The Guide Designer's bottom bar (spec 2).

Six controls that do not share a scope, grouped so the difference is visible:
what acts on the SELECTION, what acts on the SCENE, and what acts on the
SESSION. Build all sits alone past a rule, where it cannot be read as "build
what I picked".

The bar knows nothing about the scene: it emits, the Designer acts.
"""

from __future__ import annotations

from tik.shared.ui.Qt import QtCore, QtWidgets


class DesignerActionBar(QtWidgets.QFrame):
    """The full-width action row under the Designer's four panes."""

    select_requested = QtCore.Signal()
    mirror_requested = QtCore.Signal()
    build_selected_requested = QtCore.Signal()
    build_all_requested = QtCore.Signal()
    sync_requested = QtCore.Signal()
    auto_sync_toggled = QtCore.Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # the Session sub-tab's build bar wears the same object name; one look
        # for both sub-tabs is the point
        self.setObjectName("BuildBar")
        # tracked so the "up to date" trailing label -- Auto off and nothing
        # to sync -- can be derived from both without either setter needing
        # to know the other's last value
        self._auto = True
        self._drift = 0
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)

        self.selection_label = self._caption("SELECTION  none")
        self.select_button = QtWidgets.QPushButton("Select guides")
        self.mirror_button = QtWidgets.QPushButton("Mirror")
        self.build_selected_button = QtWidgets.QPushButton("Build selected")
        layout.addWidget(self.selection_label)
        for button in (
            self.select_button,
            self.mirror_button,
            self.build_selected_button,
        ):
            layout.addWidget(button)

        layout.addStretch(1)

        layout.addWidget(self._caption("SCENE"))
        self.sync_button = QtWidgets.QPushButton("Sync")
        self.sync_button.setObjectName("SyncButton")
        self.sync_button.setToolTip("Read the guides in the scene into this session")
        layout.addWidget(self.sync_button)
        self.auto_check = QtWidgets.QCheckBox("Auto")
        self.auto_check.setChecked(True)
        self.auto_check.setToolTip(
            "Follow the scene automatically. Off, the session updates only when you press Sync."
        )
        layout.addWidget(self.auto_check)
        self.drift_pill = QtWidgets.QLabel("")
        self.drift_pill.setObjectName("FilterPillLabel")
        self.drift_pill.setVisible(False)
        layout.addWidget(self.drift_pill)
        # Spec 2.3: with Auto off and nothing to sync, say so rather than
        # leaving the SCENE group silent -- same grey as the rest of the
        # chrome, no pill, no new colour.
        self.up_to_date_label = QtWidgets.QLabel("up to date")
        self.up_to_date_label.setObjectName("PanelSubtitle")
        self.up_to_date_label.setVisible(False)
        layout.addWidget(self.up_to_date_label)

        # a QFrame.VLine here does not paint under QSS `color:` and ignores
        # `max-width`; a plain QFrame with an explicit fixed width is what
        # actually renders a crisp 1px divider
        self.rule = QtWidgets.QFrame()
        self.rule.setObjectName("BarRule")
        self.rule.setMinimumWidth(1)
        self.rule.setMaximumWidth(1)
        layout.addWidget(self.rule)

        layout.addWidget(self._caption("SESSION"))
        self.build_all_button = QtWidgets.QPushButton("▶  Build all")
        self.build_all_button.setObjectName("PrimaryButton")
        layout.addWidget(self.build_all_button)

        self.select_button.clicked.connect(self.select_requested)
        self.mirror_button.clicked.connect(self.mirror_requested)
        self.build_selected_button.clicked.connect(self.build_selected_requested)
        self.build_all_button.clicked.connect(self.build_all_requested)
        self.sync_button.clicked.connect(self.sync_requested)
        self.auto_check.toggled.connect(self.auto_sync_toggled)

        self.set_selection([])

    @staticmethod
    def _caption(text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setObjectName("FieldCaption")
        return label

    # ------------------------------------------------------------- state
    def set_selection(self, keys: list[str]) -> None:
        """Name what the selection group is pointed at, and enable it or not.

        The label is why the buttons are greyed out -- today they simply are,
        with nothing on screen to say so.
        """
        if not keys:
            text = "none"
        elif len(keys) == 1:
            text = keys[0]
        else:
            text = f"{len(keys)} modules"
        self.selection_label.setText(f"SELECTION  {text}")
        for button in (
            self.select_button,
            self.mirror_button,
            self.build_selected_button,
        ):
            button.setEnabled(bool(keys))

    def set_auto_sync(self, on: bool) -> None:
        """Reflect the setting without reporting it back as a user action.

        The menu action and this checkbox are one setting with two front doors;
        without the block they would ping-pong.
        """
        self.auto_check.blockSignals(True)
        try:
            self.auto_check.setChecked(bool(on))
        finally:
            self.auto_check.blockSignals(False)
        self.sync_button.setProperty("quiet", bool(on))
        self._repolish(self.sync_button)
        self._auto = bool(on)
        self._update_up_to_date()

    def set_drift(self, count: int) -> None:
        """Report scene changes the document has not been told about."""
        self.drift_pill.setVisible(bool(count))
        self.drift_pill.setText(
            f"{count} module{'s' if count != 1 else ''} changed" if count else ""
        )
        self.sync_button.setProperty("alert", bool(count))
        self._repolish(self.sync_button)
        self._drift = int(count)
        self._update_up_to_date()

    def _update_up_to_date(self) -> None:
        """Spec 2.3: say the scene is clean only when Auto cannot say it for us."""
        self.up_to_date_label.setVisible(not self._auto and not self._drift)

    @staticmethod
    def _repolish(widget) -> None:
        """Qt does not restyle on a property change unless asked."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)
