"""Grab a Trigger UI widget to a PNG, for comparing against the design mockups.

Two environments, two purposes:

* headless (``mayapy tools/uishot.py out.png``) has **no fonts at all**, so text
  comes out as tofu. Use it for geometry: margins, alignment, control heights,
  colour.
* inside a running Maya, the same ``capture()`` has the real font stack. Use it
  for anything about type.

Not a test: nothing here asserts. It produces an image for a human -- or a model
with eyes -- to compare against the mockups.

``--widget designer`` and ``--widget window`` both need a ``GuideScene``, which
needs Maya. Rather than branch on whether Maya happens to be available, both
always build on ``tests/ui/stub.py``'s ``StubScene`` -- the same Maya-free UI
test double ``tests/ui/conftest.py`` wires in for the Qt test suite. That keeps
this script identical in a live Maya session and headless, and it is why a
"window" capture never touches the real scene: nothing here is a guide-authoring
tool, it exists to compare paint against the mockups.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

TESTS_UI = str(Path(__file__).resolve().parent.parent / "tests" / "ui")


def _headless_maya() -> bool:
    """True in a batch/standalone ``mayapy`` process with no real Maya UI.

    ``mayapy`` without an interactive session initializes just enough of
    Maya that ``import maya.cmds`` and ordinary ``scriptJob``s work, but
    registering an OpenMaya API message callback (the Guide Designer's
    node-removed watcher) segfaults the interpreter outright rather than
    raising -- nothing in Python can catch that, so the callback must never
    be registered in the first place. A live Maya session has a real main
    window and does not hit this.
    """
    try:
        from maya import cmds  # noqa: F401
    except Exception:  # noqa: BLE001 - no maya module at all
        return False
    from tik.shared.ui.maya_window import get_main_window

    return get_main_window() is None


def _guard_api_callbacks() -> None:
    """Neutralise ``ApiCallbacks`` under a headless ``mayapy``; a no-op in live Maya."""
    if not _headless_maya():
        return
    from tik.trigger.maya import observer

    observer.ApiCallbacks.start = lambda self: None
    observer.ApiCallbacks.stop = lambda self: None


def _stub_scene():
    """A fresh ``StubScene``, importing the double from ``tests/ui``."""
    if TESTS_UI not in sys.path:
        sys.path.insert(0, TESTS_UI)
    from stub import StubScene

    return StubScene()


def _designer_widget():
    """A ``GuideDesigner`` over a ``StubScene`` -- never a real ``GuideScene``."""
    _guard_api_callbacks()
    from tik.trigger.ui.designer import GuideDesigner

    return GuideDesigner(scene=_stub_scene())


def _window_widget():
    """A ``TriggerWindow`` whose sessions hand out ``StubScene``s for their guides.

    ``Session.guides`` normally builds a real (Maya-only) ``GuideScene`` lazily
    on first access. Patched the same way ``tests/ui/conftest.py`` patches it,
    so opening a session's Guide Designer sub-tab here never needs Maya.
    """
    _guard_api_callbacks()
    from tik.trigger.session import Session
    from tik.trigger.ui.designer import GuideDesigner
    from tik.trigger.ui.main import TriggerWindow

    scenes: dict = {}

    def guides(self):
        if id(self) not in scenes:
            scene = _stub_scene()
            scene.session = self
            scenes[id(self)] = scene
        return scenes[id(self)]

    Session.guides = property(guides)

    def factory(scene=None):
        return GuideDesigner(scene=scene if scene is not None else _stub_scene())

    window = TriggerWindow(designer_factory=factory)
    # Guide Designer selected: the tab strip and sub-tab strip together is
    # what the mockups show, and what got called out by name.
    window.views[0].sub_tabs.setCurrentIndex(1)
    return window


def capture(out_path: str, which: str = "bar", width: int = 1240, height: int = 760) -> str:
    """Render one widget offscreen and save it. Returns the path."""
    from tik.shared.ui import theme
    from tik.shared.ui.Qt import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if which == "bar":
        from tik.trigger.ui.designer.action_bar import DesignerActionBar

        widget = DesignerActionBar()
        widget.set_selection(["L_arm"])
        widget.resize(width, widget.sizeHint().height())
    elif which == "designer":
        widget = _designer_widget()
        widget.resize(width, height)
    else:  # "window"
        widget = _window_widget()
        widget.resize(width, height)
    theme.apply(widget)
    widget.show()
    app.processEvents()
    widget.grab().save(out_path)
    widget.close()
    return out_path


if __name__ == "__main__":
    os.environ.setdefault("TIK_TESTS_NO_MAYA", "1")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "python"))
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--widget", default="bar", choices=("bar", "designer", "window"))
    args = parser.parse_args()
    print("saved:", capture(args.out, args.widget))
