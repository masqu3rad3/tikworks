"""Status bar helper: one activity label, then permanent fields with separators."""

from __future__ import annotations

from typing import Sequence

from tik.shared.ui.Qt import QtWidgets


class StatusFields:
    """Fields on a ``QStatusBar``, or on a plain widget used as a strip.

    The strip form lets a window keep one status bar while each mode owns its
    own set of fields (see ``tik.trigger.ui.main``).
    """

    def __init__(self, host, fields: Sequence[str]) -> None:
        self.bar = host if isinstance(host, QtWidgets.QStatusBar) else None
        self._layout = None
        if self.bar is not None:
            self.bar.setSizeGripEnabled(False)
        else:
            self._layout = QtWidgets.QHBoxLayout(host)
            self._layout.setContentsMargins(6, 0, 6, 0)
            self._layout.setSpacing(6)
        self.activity = QtWidgets.QLabel("")
        self.activity.setObjectName("StatusActivity")
        self._add(self.activity, stretch=1)
        self.labels: dict[str, QtWidgets.QLabel] = {}
        for index, name in enumerate(fields):
            if index:
                separator = QtWidgets.QLabel("·")
                separator.setObjectName("StatusSeparator")
                self._add(separator, permanent=True)
            label = QtWidgets.QLabel("")
            label.setObjectName(f"Status_{name}")
            self._add(label, permanent=True)
            self.labels[name] = label

    def _add(self, widget, stretch: int = 0, permanent: bool = False) -> None:
        if self.bar is None:
            self._layout.addWidget(widget, stretch)
        elif permanent:
            self.bar.addPermanentWidget(widget)
        else:
            self.bar.addWidget(widget, stretch)

    def set_activity(self, text: str, timeout_ms: int = 0) -> None:
        """Show ``text`` in the activity slot, cleared after ``timeout_ms`` when given."""
        self.activity.setText(text)
        if timeout_ms and self.bar is not None:
            self.bar.showMessage("", timeout_ms)

    def set(self, name: str, text: str) -> None:
        """Show ``text`` in the field called ``name``."""
        self.labels[name].setText(text)

    def text(self, name: str) -> str:
        """The text shown in the field called ``name``."""
        return self.labels[name].text()
