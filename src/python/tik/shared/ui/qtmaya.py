"""Maya-specific Qt helpers."""

from __future__ import annotations

from typing import Optional

from tik.shared.ui.Qt import QtCompat, QtWidgets


def get_main_window() -> Optional[QtWidgets.QMainWindow]:
    """Maya's main window as a QWidget, or ``None`` when headless."""
    try:
        from maya import OpenMayaUI

        pointer = OpenMayaUI.MQtUtil.mainWindow()
    except Exception:  # noqa: BLE001 - no Maya, or a mocked one without UI
        return None
    if pointer is None:
        return None
    return QtCompat.wrapInstance(int(pointer), QtWidgets.QMainWindow)
