"""Every shipped plugin has artwork, and that artwork is Qt-safe.

Pure text checks -- no Qt here, so this runs in the plain unit suite.
"""

import pytest

import tik.trigger as trigger
from tik.trigger.core import icons, registry

# Nothing populates the registries on import; only an explicit call does. This
# must run before the parametrize lists below are built, or they come out empty
# and every case below passes while asserting nothing.
trigger.load_plugins()

# Qt renders SVG Tiny 1.2. These elements and attributes are silently ignored,
# so a file using them looks right in a browser and wrong (or blank) in Maya.
FORBIDDEN = (
    "<filter",
    "<mask",
    "<text",
    "<foreignObject",
    "<use",
    "currentColor",
    "@import",
)


def _plugins():
    return [(cls, "action") for cls in registry.iter_actions()] + [
        (cls, "module") for cls in registry.iter_modules()
    ]


@pytest.fixture(autouse=True)
def _plugins_loaded():
    """Re-register after any test that called ``clear_registries()``."""
    trigger.load_plugins()


def test_the_plugin_list_is_not_empty():
    """Guard against the whole suite below silently collecting zero cases."""
    assert len(_plugins()) >= 9


@pytest.mark.parametrize(
    "cls,family", _plugins(), ids=lambda item: getattr(item, "__name__", item)
)
def test_every_plugin_ships_an_icon(cls, family):
    found = icons.find(cls)
    assert found is not None, f"{cls.__name__} has no icon file beside its .py"
    assert found.family == family


@pytest.mark.parametrize(
    "cls,_family", _plugins(), ids=lambda item: getattr(item, "__name__", item)
)
def test_icons_stay_inside_the_qt_svg_subset(cls, _family):
    found = icons.find(cls)
    if found is None or found.is_raster:
        pytest.skip("no icon, or a raster one the subset rules do not govern")
    text = found.path.read_text(encoding="utf-8")
    used = [token for token in FORBIDDEN if token in text]
    assert used == [], f"{found.path.name} uses {used}, which Qt will ignore"


@pytest.mark.parametrize(
    "cls,_family", _plugins(), ids=lambda item: getattr(item, "__name__", item)
)
def test_icons_share_the_24_unit_grid(cls, _family):
    found = icons.find(cls)
    if found is None or found.is_raster:
        pytest.skip("no icon, or a raster one drawn on no grid")
    assert 'viewBox="0 0 24 24"' in found.path.read_text(encoding="utf-8")
