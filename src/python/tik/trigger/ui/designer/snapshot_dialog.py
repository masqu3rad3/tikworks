"""The report a snapshot shows before it replaces anything (spec 5.3).

Snapshot is destructive to the module list, so it reports first. The part that
matters is the honest degradation: a scene drawn by an older build carries no
``trg_entry`` breadcrumb, and this dialog says exactly what will not come back
rather than quietly restoring a module called "fkchain" with default settings.
Scenes are files, and old files keep arriving.
"""

from __future__ import annotations

from tik.shared.ui.Qt import QtWidgets

#: What a module without a breadcrumb loses. Kept as prose, not a table: it is
#: read once, under pressure, by someone who has already lost their session.
LOSSES = (
    "names fall back to the module type, settings reset to their defaults, "
    "input connections are lost, and the graph will be auto-laid out"
)


class SnapshotDialog(QtWidgets.QDialog):
    """Show a ``RecoveryReport`` and ask whether to commit it."""

    def __init__(self, report, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Snapshot Guides From Scene")
        self.report = report
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)

        blurb = QtWidgets.QLabel(
            "Read the guide joints in the Maya scene and rebuild this session's "
            "modules from them. The session's current modules are replaced."
        )
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        count = len(report.modules)
        self.found_label = QtWidgets.QLabel(
            f"{count} module{'s' if count != 1 else ''}"
            f"  ·  {report.guide_count} guide joints"
        )
        self.found_label.setObjectName("PanelTitle")
        layout.addWidget(self.found_label)

        recovered = QtWidgets.QLabel("RECOVERED FROM THE SCENE")
        recovered.setObjectName("FieldCaption")
        layout.addWidget(recovered)
        self.recovered_label = QtWidgets.QLabel(self._recovered_text())
        self.recovered_label.setWordWrap(True)
        layout.addWidget(self.recovered_label)

        # Only ever shown when something really is lost: a permanently visible
        # warning teaches people to stop reading warnings.
        self.losses_group = QtWidgets.QWidget()
        losses_layout = QtWidgets.QVBoxLayout(self.losses_group)
        losses_layout.setContentsMargins(0, 0, 0, 0)
        losses_layout.setSpacing(4)
        caption = QtWidgets.QLabel("NOT STORED IN THE SCENE")
        caption.setObjectName("FieldCaption")
        losses_layout.addWidget(caption)
        self.losses_label = QtWidgets.QLabel(self._losses_text())
        self.losses_label.setObjectName("FilterPillLabel")
        self.losses_label.setWordWrap(True)
        losses_layout.addWidget(self.losses_label)
        self.losses_group.setVisible(bool(report.partial or report.unknown_types))
        layout.addWidget(self.losses_group)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.confirm_button = QtWidgets.QPushButton(
            f"Snapshot {count} module{'s' if count != 1 else ''}"
        )
        self.confirm_button.setObjectName("PrimaryButton")
        self.confirm_button.setEnabled(bool(count))
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)

    def _recovered_text(self) -> str:
        whole = len(self.report.complete)
        if not self.report.modules:
            return "No tagged guide joints were found in the scene."
        lines = [
            f"Guide positions, rotations and attributes  ·  "
            f"{self.report.guide_count} joints",
            "Module type, side and guide hierarchy  ·  "
            f"{len(self.report.modules)} modules",
        ]
        if whole:
            lines.append(
                f"Names, settings and connections  ·  {whole} of "
                f"{len(self.report.modules)} modules"
            )
        return "\n".join(lines)

    def _losses_text(self) -> str:
        parts = []
        if self.report.partial:
            count = len(self.report.partial)
            parts.append(
                f"{count} module{'s' if count != 1 else ''} "
                f"({', '.join(item.key for item in self.report.partial)}) "
                f"came from an older scene and carry no saved entry — {LOSSES}."
            )
        if self.report.unknown_types:
            parts.append(
                "Skipped, because this build has no such module: "
                + ", ".join(self.report.unknown_types)
                + "."
            )
        return " ".join(parts)
