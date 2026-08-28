"""Dockable tool-window base for tikworks tools (Maya workspace control aware).

Ported from creature_kit ``shared/widgets/maya_window.py``. Works headless:
without Maya it degrades to a plain ``QMainWindow``.
"""

from __future__ import annotations

import logging

from tik.shared.ui.Qt import QtCompat, QtWidgets

LOG = logging.getLogger(__name__)

try:  # Maya only
    from maya import cmds  # noqa: F401
    from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

    HAS_MAYA = True
except Exception:  # noqa: BLE001 - ImportError or mocked maya without .app
    HAS_MAYA = False

    class MayaQWidgetDockableMixin:  # type: ignore[no-redef]
        """No-op stand-in outside Maya."""


def get_main_window():
    """Maya's main window as a QWidget, or ``None`` when headless."""
    if not HAS_MAYA:
        return None
    try:
        from maya import OpenMayaUI

        ptr = OpenMayaUI.MQtUtil.mainWindow()
    except Exception:  # noqa: BLE001
        return None
    if ptr is None:
        return None
    return QtCompat.wrapInstance(int(ptr), QtWidgets.QMainWindow)


class MayaToolWindow(MayaQWidgetDockableMixin, QtWidgets.QMainWindow):
    """Dockable base: workspace-control teardown, scriptJob cleanup, theme."""

    WINDOW_NAME = "TikToolWindow"

    def __init__(self, parent=None) -> None:
        super().__init__(parent if parent is not None else get_main_window())
        self.setObjectName(self.WINDOW_NAME)
        self._script_jobs: list[int] = []

    # ---------------------------------------------------------- scriptjobs
    def register_script_job(self, job_id: int) -> int:
        self._script_jobs.append(job_id)
        return job_id

    def _kill_script_jobs(self) -> None:
        if not HAS_MAYA:
            self._script_jobs.clear()
            return
        from maya import cmds

        while self._script_jobs:
            job = self._script_jobs.pop()
            try:
                if cmds.scriptJob(exists=job):
                    cmds.scriptJob(kill=job, force=True)
            except RuntimeError:
                LOG.debug("scriptJob %s already gone", job)

    # ------------------------------------------------------------- close
    def closeEvent(self, event) -> None:  # noqa: N802
        self._kill_script_jobs()
        super().closeEvent(event)

    def close(self):
        if self.parent() is None:
            return QtWidgets.QWidget.close(self)
        return super().close()

    def dockCloseEventTriggered(self) -> None:  # noqa: N802
        self._kill_script_jobs()
        self.close()

    @classmethod
    def teardown_workspace_control(cls) -> None:
        """Delete a leftover workspaceControl so relaunching does not dock twice."""
        if not HAS_MAYA:
            return
        from maya import cmds

        control = f"{cls.WINDOW_NAME}WorkspaceControl"
        if cmds.workspaceControl(control, exists=True):
            cmds.deleteUI(control, control=True)

    def show_tool(self, dockable: bool = True) -> None:
        """Show as a dockable workspace control in Maya, plain window elsewhere."""
        if HAS_MAYA and self.parent() is not None:
            self.show(dockable=dockable, retain=False)
        else:
            self.show()
