"""pick: paths in, Qt objects out, with an exact-colour tint."""

import pytest

from tik.shared.ui import pick
from tik.shared.ui.Qt import QtGui

MONO = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
    '<circle cx="12" cy="12" r="9" fill="#93a8c4"/></svg>'
)


@pytest.fixture
def mono_svg(tmp_path):
    path = tmp_path / "dot.svg"
    path.write_text(MONO, encoding="utf-8")
    pick.clear_cache()
    return path


def _first_opaque(image):
    for y in range(image.height()):
        for x in range(image.width()):
            colour = QtGui.QColor(image.pixelColor(x, y))
            if colour.alpha() > 200:
                return colour.name()
    return None


def test_renders_an_icon_at_the_requested_size(qapp, mono_svg):
    result = pick.pixmap(mono_svg, 16)
    assert not result.isNull()
    assert (result.width(), result.height()) == (16, 16)


def test_tint_replaces_every_opaque_pixel_exactly(qapp, mono_svg):
    tinted = pick.tinted_icon(mono_svg, "#5b8fd0", 22)
    assert _first_opaque(tinted.pixmap(22, 22).toImage()) == "#5b8fd0"


def test_tint_keeps_the_silhouette(qapp, mono_svg):
    plain = pick.pixmap(mono_svg, 22).toImage()
    tinted = pick.tinted_icon(mono_svg, "#d06a66", 22).pixmap(22, 22).toImage()

    def drawn(image):
        return sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if QtGui.QColor(image.pixelColor(x, y)).alpha() > 200
        )

    assert drawn(tinted) == drawn(plain)


def test_icons_are_cached_by_path(qapp, mono_svg):
    assert pick.icon(mono_svg) is pick.icon(mono_svg)


def test_tints_are_cached_per_colour_and_size(qapp, mono_svg):
    assert pick.tinted_icon(mono_svg, "#5b8fd0", 16) is pick.tinted_icon(
        mono_svg, "#5b8fd0", 16
    )
    assert pick.tinted_icon(mono_svg, "#5b8fd0", 16) is not pick.tinted_icon(
        mono_svg, "#d06a66", 16
    )


def test_style_file_opens_the_theme(qapp):
    handle = pick.style_file()
    try:
        assert handle.isOpen()
        assert b"QWidget" in bytes(handle.readAll())
    finally:
        handle.close()
