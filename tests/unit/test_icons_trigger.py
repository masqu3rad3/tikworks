"""Icon file resolution: PNG beats SVG, declared name beats registered type."""

import sys
import types

import pytest

from tik.trigger.core import icons


@pytest.fixture
def plugin(tmp_path):
    """Build a throwaway plugin folder plus a class that claims to live in it."""
    created = []

    def make(name, *, family="action", icon="", files=()):
        folder = tmp_path / name
        folder.mkdir(exist_ok=True)
        for file_name in files:
            (folder / file_name).write_bytes(b"x")
        module_name = f"_tik_icon_probe_{name}"
        module = types.ModuleType(module_name)
        module.__file__ = str(folder / f"{name}.py")
        sys.modules[module_name] = module
        created.append(module_name)
        namespace = {"__module__": module_name, "icon": icon}
        namespace["action_type" if family == "action" else "module_type"] = name
        return folder, type(name.title(), (), namespace)

    yield make
    for module_name in created:
        sys.modules.pop(module_name, None)


def test_finds_svg_beside_the_module(plugin):
    folder, cls = plugin("kinematics", files=["kinematics.svg"])
    found = icons.find(cls)
    assert found is not None
    assert found.path == folder / "kinematics.svg"
    assert found.family == icons.ACTION
    assert found.is_raster is False


def test_png_wins_over_svg(plugin):
    folder, cls = plugin("kinematics", files=["kinematics.svg", "kinematics.png"])
    found = icons.find(cls)
    assert found.path == folder / "kinematics.png"
    assert found.is_raster is True


def test_declared_icon_name_beats_registered_type(plugin):
    folder, cls = plugin(
        "script", icon="terminal", files=["script.svg", "terminal.svg"]
    )
    assert icons.find(cls).path == folder / "terminal.svg"


def test_falls_back_to_registered_type_when_declared_name_has_no_file(plugin):
    folder, cls = plugin("script", icon="terminal", files=["script.svg"])
    assert icons.find(cls).path == folder / "script.svg"


def test_returns_none_when_nothing_on_disk(plugin):
    _folder, cls = plugin("ribbon", family="module")
    assert icons.find(cls) is None


def test_reports_the_module_family(plugin):
    _folder, cls = plugin("arm", family="module", files=["arm.svg"])
    assert icons.find(cls).family == icons.MODULE


def test_unregistered_class_has_no_icon():
    class Loose:
        pass

    assert icons.find(Loose) is None
