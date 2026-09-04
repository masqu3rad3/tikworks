"""Family rules: actions keep their colour, modules take a tint."""

import sys

import pytest

import tik.trigger as trigger
from tik.shared.ui import theme
from tik.shared.ui.Qt import QtGui
from tik.trigger.core import registry
from tik.trigger.ui import iconography


def _maya_module_keys() -> list[str]:
    """Every ``sys.modules`` key under the ``maya`` package right now."""
    return [key for key in sys.modules if key == "maya" or key.startswith("maya.")]


def _load_plugins_with_real_maya_api() -> None:
    """Import the shipped plugins once, through a real (uninitialized) ``maya``.

    ``tests/conftest.py`` fakes ``maya`` for ``TIK_TESTS_NO_MAYA=1`` runs: a
    ``maya.cmds`` with only ``file``/``select`` stubbed (real ``cmds`` needs
    ``maya.standalone.initialize()`` to do anything, which UI tests skip
    because it cannot coexist with a ``QApplication``), and a bare
    ``maya.api.OpenMaya`` carrying only ``MPxCommand`` -- enough for
    ``tik/__init__.py`` to import, deliberately no more. But class bodies
    across ``tik.maya`` read real API *constants* at import time
    (``OpenMaya.MFn.kAttribute3Double`` in ``tik/maya/core/plug.py``), and
    ``tik/maya/types/camera.py`` imports ``maya.mel`` outright, so the
    shipped guide modules -- which ``import tik.maya`` -- fail to import
    through that mock, and ``registry.iter_modules()`` stays empty.

    ``mayapy`` itself ships a real, complete ``maya`` package that imports
    and reads constants from just fine without ``maya.standalone.
    initialize()`` -- only *calling* a live scene/callback function on it is
    unsafe pre-init. So this drops every mocked ``maya*`` entry from
    ``sys.modules`` (forcing a genuine import to replace it), imports the
    plugin folders through the real thing, then deletes *every* ``maya*``
    key the real import chain left behind (not just the ones the mock had --
    a real submodule like ``maya.api.OpenMayaAnim``, pulled in as a side
    effect of importing ``tik.maya``, has no mock counterpart to overwrite
    it, and would otherwise dangle in ``sys.modules`` after this function
    returns) and puts the original mocked objects back. Verified the hard
    way that this scoping matters: leaving real bindings in place for a
    whole session (by editing ``tests/conftest.py`` instead of scoping the
    swap here) let an unrelated test construct a real ``MDGMessage`` scene
    callback with no Maya session behind it and crash the interpreter with
    an access violation, in ``tik/trigger/maya/observer.py``. Every later
    ``trigger.load_plugins()`` call in this file (see ``_plugins_loaded``
    below) only re-registers already-imported classes -- see
    ``discovery.discover()``'s use of ``importlib.import_module``, which
    returns the cached module without touching ``maya`` again -- so the
    restore below only has to hold up until this module finishes collecting.
    """
    saved = {key: sys.modules[key] for key in _maya_module_keys()}
    for key in saved:
        del sys.modules[key]
    try:
        import maya.api.OpenMaya  # noqa: F401 - pulls in real maya + maya.api too
        import maya.mel  # noqa: F401 - tik/maya/types/camera.py imports this

        trigger.load_plugins()
    finally:
        for key in _maya_module_keys():
            del sys.modules[key]
        sys.modules.update(saved)


# Must precede the parametrize lists below: nothing populates the registries on
# import, and an empty list would make every parametrized case vanish silently.
_load_plugins_with_real_maya_api()


@pytest.fixture(autouse=True)
def _plugins_loaded():
    """``tests/ui/test_guide_designer.py`` calls ``clear_registries()`` and
    pytest ordering is not guaranteed, so restore the real plugins per test."""
    trigger.load_plugins()


def test_the_registries_are_populated():
    """Guard against the parametrized suites below collecting zero cases."""
    assert len(registry.iter_actions()) >= 4
    assert len(registry.iter_modules()) >= 5


def _drawn(icon, size):
    image = icon.pixmap(size, size).toImage()
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if QtGui.QColor(image.pixelColor(x, y)).alpha() > 40
    )


def _colours(icon, size):
    image = icon.pixmap(size, size).toImage()
    return {
        QtGui.QColor(image.pixelColor(x, y)).name()
        for y in range(image.height())
        for x in range(image.width())
        if QtGui.QColor(image.pixelColor(x, y)).alpha() > 200
    }


def _assert_single_tint(icon, size, expected):
    """All solid pixels are ``expected``, within Qt's own AA rounding noise.

    Qt's raster engine composites antialiased curves (``pick.tinted_icon``'s
    ``SourceIn`` stamp, ``topology_icon``'s overlapping line/ellipse strokes)
    through 8-bit premultiplied-alpha storage: converting a colour to
    premultiplied form and back is not always bit-exact, so a handful of
    pixels -- occasionally even fully opaque ones, where two same-colour
    antialiased strokes overlapped -- land 1-2 levels off per channel.
    Verified empirically against this repo's PySide6 build: real off-tint
    pixels (a second colour entirely, e.g. a raster PNG or a raw SVG) differ
    by far more than this and still fail the check below.
    """
    colours = _colours(icon, size)
    assert colours, "icon has no solid pixels"
    target = QtGui.QColor(expected)
    for colour in colours:
        actual = QtGui.QColor(colour)
        assert (
            abs(actual.red() - target.red()) <= 2
            and abs(actual.green() - target.green()) <= 2
            and abs(actual.blue() - target.blue()) <= 2
        ), f"{colour} is not a same-tint pixel of {expected}"


@pytest.mark.parametrize(
    "action_cls", registry.iter_actions(), ids=lambda c: c.action_type
)
def test_every_action_renders_at_tree_size(qapp, action_cls):
    assert _drawn(iconography.action_icon(action_cls, size=16), 16) > 20


@pytest.mark.parametrize(
    "module_cls", registry.iter_modules(), ids=lambda c: c.module_type
)
def test_every_module_renders_at_tree_size(qapp, module_cls):
    assert _drawn(iconography.module_icon(module_cls, size=16), 16) > 20


def test_actions_keep_their_own_colour(qapp):
    icon = iconography.action_icon(registry.get_action("import_asset"), size=64)
    assert len(_colours(icon, 64)) > 8, "an action must not be flattened to one tint"


def test_modules_take_the_side_tint(qapp):
    arm = registry.get_module("arm")
    left_icon = iconography.module_icon(arm, side="L", size=22)
    right_icon = iconography.module_icon(arm, side="R", size=22)
    _assert_single_tint(left_icon, 22, theme.SIDE["L"])
    _assert_single_tint(right_icon, 22, theme.SIDE["R"])


def test_module_without_a_side_takes_its_category_colour(qapp):
    from tik.trigger.ui.designer.widgets import MODULE_COLORS

    arm = registry.get_module("arm")
    expected = MODULE_COLORS[arm.category]
    _assert_single_tint(iconography.module_icon(arm, size=22), 22, expected)


def test_a_raster_module_icon_is_never_tinted(qapp, tmp_path, monkeypatch):
    from tik.trigger.core import icons

    png = tmp_path / "fake.png"
    pixmap = QtGui.QPixmap(22, 22)
    pixmap.fill(QtGui.QColor("#ff00ff"))
    pixmap.save(str(png), "PNG")
    monkeypatch.setattr(icons, "find", lambda cls: icons.IconFile(png, icons.MODULE))
    icon = iconography.module_icon(registry.get_module("arm"), side="L", size=22)
    assert _colours(icon, 22) == {"#ff00ff"}


def test_module_with_no_artwork_falls_back_to_its_topology(qapp, monkeypatch):
    from tik.trigger.core import icons

    monkeypatch.setattr(icons, "find", lambda cls: None)
    icon = iconography.module_icon(registry.get_module("fkchain"), side="L", size=22)
    assert _drawn(icon, 22) > 10
    _assert_single_tint(icon, 22, theme.SIDE["L"])


def test_action_with_no_artwork_falls_back_to_initials(qapp, monkeypatch):
    from tik.trigger.core import icons

    monkeypatch.setattr(icons, "find", lambda cls: None)
    icon = iconography.action_icon(registry.get_action("script"), size=22)
    assert _drawn(icon, 22) > 100, "the initials chip is a filled square"
