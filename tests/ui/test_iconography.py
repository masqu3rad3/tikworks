"""Family rules: actions keep their colour, modules take a tint."""

import pytest

import tik.trigger as trigger
from tik.shared.ui import theme
from tik.shared.ui.Qt import QtGui
from tik.trigger.core import registry
from tik.trigger.ui import iconography

# Snapshot the registries as they stood before this file added anything, so
# `_restore_registries` below can undo this file's registrations once every
# test here has run. Taken *before* the `trigger.load_plugins()` call right
# below, and outside any fixture, because pytest fully collects every test
# file (running this module-level code) before running any test in any of
# them -- a fixture, of any scope, only ever sees the registries after this
# line has already populated them, so only a plain module-level snapshot can
# capture the true "before this file" baseline.
_modules_before_this_file = dict(registry._MODULES)
_actions_before_this_file = dict(registry._ACTIONS)

# Must precede the parametrize lists below: nothing populates the registries on
# import, and an empty list would make every parametrized case vanish silently.
trigger.load_plugins()


@pytest.fixture(autouse=True)
def _plugins_loaded():
    """``tests/ui/test_guide_designer.py`` calls ``clear_registries()`` and
    pytest ordering is not guaranteed, so restore the real plugins per test."""
    trigger.load_plugins()


@pytest.fixture(scope="module", autouse=True)
def _restore_registries():
    """Undo this file's registrations once every test here has run.

    This is the only ui test file that registers the real shipped modules
    and actions (others use throwaway toy classes via ``clear_registries()``
    + ``register_module``). Without this, they would stay registered for
    every ui test file that runs afterward in the same session, which
    previously only ever saw an empty or toy-only registry.
    """
    yield
    registry._MODULES.clear()
    registry._MODULES.update(_modules_before_this_file)
    registry._ACTIONS.clear()
    registry._ACTIONS.update(_actions_before_this_file)


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
    from tik.shared.ui.theme import MODULE_COLORS

    # "arm" (category "limbs") can't prove this branch on its own: its
    # category colour and theme.SIDE["L"] are both "#5b8fd0", so a test built
    # around it would still pass even if the ``if side:`` branch in
    # ``module_colour`` were deleted outright. "base" (category "body",
    # "#c9a24a") is distinct from every SIDE colour, so it actually exercises
    # the category branch.
    base = registry.get_module("base")
    expected = MODULE_COLORS[base.category]
    _assert_single_tint(iconography.module_icon(base, size=22), 22, expected)


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
