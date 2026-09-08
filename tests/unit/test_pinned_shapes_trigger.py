"""The build resolves shapes through a library a preference cannot reach."""

from __future__ import annotations

import pytest

from tik.trigger.core import shapes


@pytest.fixture(autouse=True)
def _reset():
    shapes.reset()
    yield
    shapes.reset()


def test_shipped_shapes_resolve():
    assert shapes.has_shape("Circle")
    assert shapes.has_shape("Cube")
    assert shapes.has_shape("FkikSwitch")
    assert not shapes.has_shape("NoSuchShape")


def test_shape_names_are_sorted_and_unique():
    names = shapes.shape_names()
    assert names == tuple(sorted(set(names)))
    assert "Diamond" in names


def test_the_user_path_is_not_searched(tmp_path, monkeypatch):
    """A personal folder is a preference; a preference cannot change a rig."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    user_shapes = tmp_path / "TikWorks" / "user_control_shapes"
    user_shapes.mkdir(parents=True)
    (user_shapes / "PersonalOnly.json").write_text('{"name": "x", "curves": []}')
    shapes.reset()

    assert not shapes.has_shape("PersonalOnly")
    assert user_shapes not in shapes.library().search_paths


def test_a_user_shape_cannot_shadow_a_shipped_one(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    user_shapes = tmp_path / "TikWorks" / "user_control_shapes"
    user_shapes.mkdir(parents=True)
    (user_shapes / "Circle.json").write_text('{"name": "Circle", "curves": []}')
    shapes.reset()

    loaded = shapes.library().load("Circle")
    assert loaded["curves"], "the shipped Circle must win over a personal one"


def test_studio_paths_are_honoured(tmp_path, monkeypatch):
    """A deployed path is the same for everyone, so it may add shapes."""
    studio = tmp_path / "studio_shapes"
    studio.mkdir()
    (studio / "StudioPin.json").write_text('{"name": "StudioPin", "curves": []}')
    monkeypatch.setenv(shapes.SHAPES_ENV, str(studio))
    shapes.reset()

    assert shapes.has_shape("StudioPin")
