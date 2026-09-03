"""Dockable tool-window base for tikworks tools (Maya workspace control aware).

Ported from creature_kit ``shared/widgets/maya_window.py``. Works headless:
without Maya it degrades to a plain ``QMainWindow``.
"""

from __future__ import annotations

import logging

from tik.shared.ui.qtmaya import get_main_window
from tik.shared.ui.Qt import QtWidgets

LOG = logging.getLogger(__name__)

try:  # Maya only
    from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

    HAS_MAYA = True
except Exception:  # noqa: BLE001 - ImportError or mocked maya without .app
    HAS_MAYA = False

    class MayaQWidgetDockableMixin:  # type: ignore[no-redef]
        """No-op stand-in outside Maya."""


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

    @staticmethod
    def has_maya_ui() -> bool:
        """True inside an interactive Maya session (not mayapy / headless)."""
        return HAS_MAYA and get_main_window() is not None

    def show(self, *args, **kwargs):  # noqa: D401
        """Plain show when there is no Maya UI (headless, mayapy with Qt).

        Note: ``MayaQWidgetDockableMixin.__init__`` deliberately drops a parent
        that is Maya's main window (deferred parenting), so ``self.parent()``
        says nothing about whether we are inside Maya.
        """
        if not self.has_maya_ui():
            # bypass the mixin's setVisible/show pair (it recurses without a host)
            return QtWidgets.QWidget.setVisible(self, True)
        return super().show(*args, **kwargs)

    def dockCloseEventTriggered(self) -> None:  # noqa: N802
        self._kill_script_jobs()
        self.close()

    @classmethod
    def teardown_workspace_control(cls) -> None:
        """Delete a leftover workspaceControl so relaunching does not dock twice."""
        # workspace controls only exist in an interactive session: importable
        # maya.cmds is not enough (mayapy without standalone has no such command)
        if not cls.has_maya_ui():
            return
        from maya import cmds

        control = f"{cls.WINDOW_NAME}WorkspaceControl"
        if cmds.workspaceControl(control, exists=True):
            cmds.deleteUI(control, control=True)

    def show_tool(self, dockable: bool = True) -> None:
        """Show as a dockable workspace control in Maya, plain window elsewhere."""
        if self.has_maya_ui():
            super().show(dockable=dockable, retain=False)
        else:
            QtWidgets.QWidget.setVisible(self, True)
