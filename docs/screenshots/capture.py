"""Render the documentation screenshots of the Trigger UI, offscreen.

Everything here runs without Maya. The Qt widgets are real; the guide scene
behind them is ``tests/ui/stub.py``'s ``StubScene``, the same Maya-free double
the Qt test-suite uses, so the pictures show real widgets over fake guides.

Run from the repository root::

    TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen python docs/screenshots/capture.py

PNGs land in ``docs/source/_static/screenshots/``. Anything that needs a Maya
viewport (guides, a built rig) is written as a labelled placeholder image, so a
page never shows a broken figure; replace those by hand from a Maya session.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import weakref
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "source" / "_static" / "screenshots"
sys.path.insert(0, str(REPO / "src" / "python"))
sys.path.insert(0, str(REPO / "tests" / "ui"))

os.environ.setdefault("TIK_TESTS_NO_MAYA", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

WIDTH, HEIGHT = 1400, 820


def _install_fake_maya() -> None:
    """Let ``tik.maya`` import without Maya, so the real modules register.

    The built-in modules import ``tik.maya`` at module level, and ``tik.maya``
    imports ``maya.cmds`` and ``OpenMaya``. A ``MagicMock`` package satisfies
    every attribute lookup those imports make at import time; nothing here
    ever *builds* a rig, so no mocked call is ever exercised. ``maya.app`` is
    blocked so the dockable-window mixin falls back to a plain ``QMainWindow``,
    exactly as it does in a Maya-less interpreter.
    """
    from unittest import mock

    if "maya" in sys.modules:
        return
    maya = mock.MagicMock(name="maya")
    maya.api.OpenMaya.MPxCommand = type("MPxCommand", (), {})
    for name in ("maya", "maya.cmds", "maya.mel", "maya.api", "maya.api.OpenMaya",
                 "maya.OpenMayaUI"):
        sys.modules[name] = maya if name == "maya" else getattr_path(maya, name)
    sys.modules["maya.app"] = None  # type: ignore[assignment]  # ImportError on purpose


def getattr_path(root, dotted: str):
    """``getattr_path(maya, "maya.api.OpenMaya")`` -> ``maya.api.OpenMaya``."""
    found = root
    for part in dotted.split(".")[1:]:
        found = getattr(found, part)
    return found

# Maya viewport pictures cannot be produced here. Each entry becomes a
# labelled placeholder so the pages render; take the real shot in Maya later.
PLACEHOLDERS = {
    "maya_guides_arm": (
        "Maya viewport: arm guides",
        "L_arm guides drawn by GuideScene.add('arm', side='L'):\n"
        "collar, shoulder, elbow, hand and the neutral guide, coloured per side.",
    ),
    "maya_built_arm": (
        "Maya viewport: a built arm",
        "The result of Session.build(): collar, IK and pole controllers, the\n"
        "four module groups in the outliner, bind joints under the rig root.",
    ),
    "maya_controller_shapes": (
        "Maya viewport: Controller shapes",
        "A few Controller.create() results side by side: Circle, CubePin,\n"
        "Arrow and Cog from the shape library, with colour overrides.",
    ),
    "maya_plug_math_network": (
        "Maya Node Editor: a plug arithmetic network",
        "The nodes created by (driver['tx'] * 2.0 + 5) >> follower['ty']:\n"
        "one multDoubleLinear, one addDoubleLinear, connected in order.",
    ),
    "maya_ribbon": (
        "Maya viewport: the Ribbon construct",
        "tm.Ribbon.create() between two locators: start and end plugs,\n"
        "one mid plug and five deformer joints following the strip.",
    ),
    "maya_space_switch": (
        "Maya viewport: a SpaceSwitch enum in the channel box",
        "The 'space' enum on a hand controller listing world, chest and root.",
    ),
    "maya_trigger_docked": (
        "Maya: the Trigger window docked next to the viewport",
        "The Session sub-tab of a rig session with a build in progress.",
    ),
    "maya_polish_shape_library": (
        "Maya: the Polish controller shape library",
        "tik.tools.polish shape browser with category tree and thumbnails.",
    ),
}


# --------------------------------------------------------------------------- setup
def _sandbox_qsettings(directory: Path) -> None:
    """Keep the Trigger window's QSettings out of the real user profile."""
    from tik.shared.ui.Qt import QtCore

    real = QtCore.QSettings
    real.setDefaultFormat(real.IniFormat)
    real.setPath(real.IniFormat, real.UserScope, str(directory))

    class _Sandboxed(real):  # type: ignore[misc,valid-type]
        def __init__(self, *args, **kwargs):
            if len(args) == 2 and not kwargs and all(isinstance(a, str) for a in args):
                super().__init__(real.IniFormat, real.UserScope, *args)
            else:
                super().__init__(*args, **kwargs)

    QtCore.QSettings = _Sandboxed


@contextlib.contextmanager
def _stubbed_sessions():
    """Every ``Session`` hands out a ``StubScene``; scene I/O becomes a no-op."""
    from stub import StubScene
    from tik.trigger.session import Session

    original = {
        name: Session.__dict__[name]
        for name in ("guides", "checkout_guides", "capture_guides", "hand_over")
    }
    scenes: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()

    def guides(self):
        if self not in scenes:
            scene = StubScene()
            scene.session = self
            scenes[self] = scene
        return scenes[self]

    Session.guides = property(guides)
    Session.checkout_guides = lambda self, force=False: None
    Session.capture_guides = lambda self: False
    Session.hand_over = staticmethod(lambda outgoing, incoming: None)
    try:
        yield
    finally:
        for name, value in original.items():
            setattr(Session, name, value)


def _write_base_rig(directory: Path) -> Path:
    """A small referenced session, so the pipeline shows linked rows."""
    from tik.trigger.session import Session

    base = Session()
    base.add("import_asset", "import_model", file_path="geo/base_body.ma")
    base.add("kinematics", "kinematics", rig_name="base")
    scripts = base.add("script", "scripts")
    base.add("script", "head_rotation", parent=scripts, code="# fix head rotation order")
    base.add("script", "finalize", parent=scripts, code="# lock and hide")
    return base.save(str(directory / "baseRig.tr"))


def _hero_session(directory: Path):
    """The session every window screenshot is taken from."""
    from tik.trigger.session import Session

    base_path = _write_base_rig(directory)
    rig = Session()
    rig.add("import_asset", "import_model", file_path="geo/hero_v02.ma")
    base = rig.add("reference", "baseRig", file=str(base_path))
    base["scripts/head_rotation"].enabled = False
    rig.add("kinematics", "build_rig", rig_name="hero")
    rig.add("script", "fix_namespaces", parent="import_model", code="print(ctx.path)")
    rig.add("script", "finalize", code="# lock attributes, set default pose")
    rig.save(str(directory / "hero_v002.tr"))

    guides = rig.guides
    body = guides.add("base", name="body")
    guides.add("arm", side="L", name="arm", parent=body)
    guides.add("arm", side="R", name="arm", parent=body)
    guides.add("fkchain", name="tail", parent=body, segments=4)
    guides.add(
        "twist", side="L", name="upperarmTwist",
        inputs={"base": "L_arm.upperarm", "end": "L_arm.lowerarm"},
    )
    guides.add(
        "ribbon", side="L", name="forearmRibbon",
        inputs={"start": "L_arm.lowerarm", "end": "L_arm.hand"},
    )
    # the stub only "knows" scene nodes it has been told about
    guides.scene_nodes.update({"prop_ctrl", "prop_jnt"})
    guides.add_scene_group("props", ["prop_ctrl", "prop_jnt"])
    return rig


# ------------------------------------------------------------------------ captures
def _grab(widget, name: str, app) -> Path:
    from tik.shared.ui import theme

    theme.apply(widget)
    widget.show()
    for _ in range(3):
        app.processEvents()
    path = OUT / f"{name}.png"
    widget.grab().save(str(path))
    print("saved:", path.relative_to(REPO))
    return path


def capture_window(rig, app) -> None:
    from tik.trigger.ui.designer import GuideDesigner
    from tik.trigger.ui.main import TriggerWindow

    def factory(scene=None):
        return GuideDesigner(scene=scene if scene is not None else rig.guides)

    # A blank session counts as modified once the window has stamped it with
    # a session id, and a QMessageBox would block an offscreen run forever.
    TriggerWindow.ask_discard = lambda self, session: True
    window = TriggerWindow(designer_factory=factory)
    view = window.add_session(rig)
    window.close_tab(0)  # the untitled tab the window opens with
    window.resize(WIDTH, HEIGHT)

    # Session sub-tab, the kinematics step selected so its form is visible.
    view.sub_tabs.setCurrentIndex(0)
    view.select_path("build_rig")
    window.status.set_activity("")
    window.status.set("maya", "Maya 2026")  # the fake maya has no version
    _grab(window, "trigger_window_session", app)

    # Guide Designer sub-tab with L_arm selected and the graph laid out.
    view.sub_tabs.setCurrentIndex(1)
    designer = view.ensure_designer()
    designer.refresh()
    designer.graph.auto_layout()
    designer.graph.fit()
    designer._select_handles([rig.guides.by_key("L_arm")])
    for _ in range(3):
        app.processEvents()
    designer.graph.fit()
    _grab(window, "trigger_window_designer", app)
    window.close()


def capture_action_bar(app) -> None:
    from tik.trigger.ui.designer.action_bar import DesignerActionBar

    bar = DesignerActionBar()
    bar.set_selection(["L_arm"])
    bar.resize(WIDTH, bar.sizeHint().height())
    _grab(bar, "designer_action_bar", app)

    bar.set_selection(["L_arm", "R_arm"])
    bar.set_auto_sync(False)
    bar.set_drift(2)
    _grab(bar, "designer_action_bar_drift", app)


def capture_palette(app) -> None:
    from tik.shared.ui.Qt import QtCore
    from tik.trigger.ui.session_view import action_entries
    from tik.trigger.ui.palette import SearchPalette

    palette = SearchPalette(action_entries())
    palette.popup(QtCore.QPoint(0, 0))
    _grab(palette, "search_palette", app)
    palette.close()


def capture_snapshot_dialog(app) -> None:
    from tik.trigger.core.scene_recovery import RecoveredModule, RecoveryReport
    from tik.trigger.ui.designer.snapshot_dialog import SnapshotDialog

    report = RecoveryReport(
        modules=[
            RecoveredModule("a1", "body", "base", True, 1),
            RecoveredModule("a2", "L_arm", "arm", True, 5),
            RecoveredModule("a3", "R_arm", "arm", True, 5),
            RecoveredModule("a4", "tail", "fkchain", False, 3),
        ],
        guide_count=14,
        unknown_types=["legacy_spine"],
    )
    dialog = SnapshotDialog(report)
    dialog.resize(560, dialog.sizeHint().height())
    _grab(dialog, "snapshot_dialog", app)
    dialog.close()


def capture_form(app) -> None:
    from tik.shared.ui.fields import FormBuilder
    from tik.trigger.core import get_module

    arm = get_module("arm")(name="arm", side="L")
    form = FormBuilder(target=arm)
    form.group_widget("Auto Collar").set_expanded(True)
    form.resize(460, form.sizeHint().height())
    _grab(form, "form_builder_arm", app)


def capture_versioned_field(app, directory: Path) -> None:
    from tik.shared.ui.Qt import QtWidgets
    from tik.shared.ui.versioned_field import VersionedFileField

    for name in ("hero_v001.tr", "hero_v002.tr", "hero_v003.tr"):
        (directory / name).write_text("{}", encoding="utf-8")
    host = QtWidgets.QWidget()
    layout = QtWidgets.QFormLayout(host)
    for label, value in (
        ("latest", "hero_v003.tr"),
        ("older", "hero_v001.tr"),
        ("missing", "hero_v009.tr"),
    ):
        field = VersionedFileField(extensions=(".tr",), base_dir=lambda: str(directory))
        field.setValue(value)
        field.refresh_state()
        layout.addRow(label, field)
    host.resize(520, host.sizeHint().height())
    _grab(host, "versioned_file_field", app)


def write_placeholders(app) -> None:
    from tik.shared.ui.Qt import QtCore, QtGui

    for name, (title, hint) in PLACEHOLDERS.items():
        image = QtGui.QImage(1200, 640, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor("#242424"))
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor("#5a5a5a"), 3, QtCore.Qt.DashLine)
        painter.setPen(pen)
        painter.drawRoundedRect(20, 20, 1160, 600, 18, 18)
        painter.setPen(QtGui.QColor("#FE7E00"))
        painter.setFont(QtGui.QFont("DejaVu Sans", 30, QtGui.QFont.Bold))
        painter.drawText(QtCore.QRect(60, 180, 1080, 80), QtCore.Qt.AlignCenter, title)
        painter.setPen(QtGui.QColor("#c0c0c0"))
        painter.setFont(QtGui.QFont("DejaVu Sans", 17))
        painter.drawText(QtCore.QRect(60, 280, 1080, 160), QtCore.Qt.AlignCenter, hint)
        painter.setPen(QtGui.QColor("#8f8f8f"))
        painter.setFont(QtGui.QFont("DejaVu Sans", 14))
        painter.drawText(
            QtCore.QRect(60, 500, 1080, 60), QtCore.Qt.AlignCenter,
            "placeholder — replace with a capture from a Maya session",
        )
        painter.end()
        path = OUT / f"{name}.png"
        image.save(str(path))
        print("placeholder:", path.relative_to(REPO))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _install_fake_maya()
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        _sandbox_qsettings(directory / "qsettings")
        from tik.shared.ui.Qt import QtWidgets

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        import tik.trigger as trigger

        trigger.load_plugins()
        write_placeholders(app)
        with _stubbed_sessions():
            rig = _hero_session(directory)
            capture_window(rig, app)
        capture_action_bar(app)
        capture_palette(app)
        capture_snapshot_dialog(app)
        capture_form(app)
        capture_versioned_field(app, directory)


if __name__ == "__main__":
    main()
