"""Dockable tool-window base for tikworks tools (Maya workspace control aware).

Ported from creature_kit ``shared/widgets/maya_window.py``. Works headless:
without Maya it degrades to a plain ``QMainWindow``.

Closing has two entrances that end in different places:

* the Qt ``closeEvent`` (a plain window, headless runs) -- vetoed the usual
  way, with ``event.ignore()``;
* Maya's workspace control (the title-bar X, or ``File > Quit`` asking the
  control to close) -- Maya runs :meth:`dockCloseEventTriggered` *before* it
  acts, and returning early from the callback does not keep the control open.

So the control is created with ``retain=True``: closing only hides it, and a
cancelled close re-shows it once Maya is done. A confirmed close deletes the
control itself, deferred, since deleting it from inside its own close callback
is what leaves an emptied frame behind.
"""

from __future__ import annotations

import logging

from tik.shared.ui.Qt import QtWidgets
from tik.shared.ui.qtmaya import get_main_window

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
        self._shutting_down = False

    # ---------------------------------------------------------- scriptjobs
    def register_script_job(self, job_id: int) -> int:
        """Remember a scriptJob so it is killed when the window closes."""
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
    def confirm_close(self) -> bool:
        """True when the window may close. Override to ask about unsaved work."""
        return True

    def teardown(self) -> None:
        """Release what the window holds; runs once, right before it goes."""
        self._kill_script_jobs()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._shutting_down and not self.confirm_close():
            event.ignore()
            return
        self.teardown()
        super().closeEvent(event)

    def close(self) -> bool:
        """Close the window, asking first; False when the user kept it open.

        Inside a workspace control the question is asked here, in Python,
        because once Maya is told to close the control nothing can stop it.
        """
        if self._workspace_control() is None:
            return QtWidgets.QWidget.close(self)
        if not self.confirm_close():
            return False
        self.shutdown()
        return True

    def shutdown(self) -> None:
        """Tear down for good and delete the workspace control, deferred."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self.teardown()
        control = self._workspace_control()
        if control is None:
            return
        from maya import cmds

        def delete() -> None:
            if cmds.workspaceControl(control, q=True, exists=True):
                cmds.deleteUI(control, control=True)

        # deleting the control also fires its close callback, and deleting it
        # from inside that callback is what leaves an emptied frame behind
        cmds.evalDeferred(delete)

    def dockCloseEventTriggered(self) -> None:  # noqa: N802
        """Maya is closing the workspace control; it cannot be vetoed here.

        With ``retain=True`` the control is only hidden, so a cancel re-shows
        it once Maya has finished. Deleting the control (a confirmed close, or
        a relaunch) fires this too, hence the guard.
        """
        if self._shutting_down:
            return
        control = self._workspace_control()
        if self.confirm_close():
            self.shutdown()
            return
        if control is None:
            return
        from maya import cmds

        def restore() -> None:
            try:
                still_ours = self._workspace_control() == control
            except RuntimeError:  # destroyed with its control meanwhile
                return
            if still_ours:
                cmds.workspaceControl(control, e=True, restore=True)

        cmds.evalDeferred(restore)

    def _workspace_control(self):
        """The name of the workspace control hosting this window, or None."""
        if not HAS_MAYA:
            return None
        from maya import cmds

        parent = self.parent()
        name = parent.objectName() if parent is not None else ""
        if name and cmds.workspaceControl(name, q=True, exists=True):
            return name
        return None

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
            # retained: closing hides the control, so a cancelled close can
            # bring it back -- see dockCloseEventTriggered
            super().show(dockable=dockable, retain=True)
        else:
            QtWidgets.QWidget.setVisible(self, True)
