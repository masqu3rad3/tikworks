"""Status bar helper: one activity label, then permanent fields with separators."""

from __future__ import annotations

from typing import Sequence

from tik.shared.ui.Qt import QtWidgets


class StatusFields:
    def __init__(self, status_bar: QtWidgets.QStatusBar, fields: Sequence[str]) -> None:
        self.bar = status_bar
        self.bar.setSizeGripEnabled(False)
        self.activity = QtWidgets.QLabel("")
        self.activity.setObjectName("StatusActivity")
        self.bar.addWidget(self.activity, 1)
        self.labels: dict[str, QtWidgets.QLabel] = {}
        for index, name in enumerate(fields):
            if index:
                separator = QtWidgets.QLabel("·")
                separator.setObjectName("StatusSeparator")
                self.bar.addPermanentWidget(separator)
            label = QtWidgets.QLabel("")
            label.setObjectName(f"Status_{name}")
            self.bar.addPermanentWidget(label)
            self.labels[name] = label

    def set_activity(self, text: str, timeout_ms: int = 0) -> None:
        self.activity.setText(text)
        if timeout_ms:
            self.bar.showMessage("", timeout_ms)

    def set(self, name: str, text: str) -> None:
        self.labels[name].setText(text)

    def text(self, name: str) -> str:
        return self.labels[name].text()
