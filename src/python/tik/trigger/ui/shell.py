"""Floating home for a detached Guide Designer.

The Designer is a page (``ui/designer/window.py``); this is the frame it lives
in when you tear it off. The bundle — menu bar, page, status strip — is only
ever *reparented*, never installed with ``setMenuBar`` / ``setStatusBar``, so Qt
never takes ownership of a widget the host expects to get back.

A plain floating window, deliberately not a ``MayaToolWindow``: showing one of
those hands the widget to a Maya workspace control, which reparents it — and
the bundle came apart into three separate windows. The shell is parented to the
Trigger window, so it follows it and dies with it.
"""

from __future__ import annotations

from tik.shared.ui import theme
from tik.shared.ui.Qt import QtCore, QtWidgets


class DesignerShell(QtWidgets.QMainWindow):
    def __init__(self, host, designer) -> None:
        super().__init__(host)
        self.setWindowFlag(QtCore.Qt.Window, True)
        self.setObjectName("TriggerDesignerShell")
        self.host = host
        self.designer = designer
        body = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(designer.menu_bar)
        layout.addWidget(designer, 1)
        layout.addWidget(designer.status_strip)
        self.setCentralWidget(body)
        self.setWindowTitle(designer.title)
        self.resize(1240, 680)
        theme.apply(self)

    def open(self) -> None:
        self.show()
        self.raise_()

    def release(self) -> None:
        """Give the bundle back to the host before this window goes away."""
        self.designer.menu_bar.setParent(None)
        self.designer.status_strip.setParent(None)
        self.designer.setParent(None)

    def closeEvent(self, event) -> None:  # noqa: N802
        # re-attach rather than destroy: the watcher, bindings and graph state
        # all live on the page. A no-op once the host has already released us.
        self.host.set_designer_detached(False)
        super().closeEvent(event)
