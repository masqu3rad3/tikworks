"""Qt user interface for tik.trigger."""

from __future__ import annotations

from .main import TriggerWindow

_WINDOW = None


def show(backend=None):
    """Open the Trigger window inside Maya (creates the Maya backend when omitted)."""
    global _WINDOW
    import tik.trigger as trigger
    from tik.shared.ui.qtmaya import get_main_window

    backend = backend or trigger.maya_backend()
    if _WINDOW is not None:
        try:
            _WINDOW.close()
            _WINDOW.deleteLater()
        except RuntimeError:
            pass
    _WINDOW = TriggerWindow(backend, parent=get_main_window())
    _WINDOW.show()
    return _WINDOW


__all__ = ["TriggerWindow", "show"]
