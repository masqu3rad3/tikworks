"""The shape picker, offscreen. No Maya: it reads the pure core library."""

from __future__ import annotations

from tik.shared.ui.shape_picker import ShapeButton, ShapePicker


def test_picker_lists_shipped_shapes(qapp):
    picker = ShapePicker()
    names = picker.names()
    assert "Circle" in names
    assert "Cube" in names
    assert "FkikSwitch" in names


def test_picker_never_imports_maya():
    import ast
    from pathlib import Path

    import tik.shared.ui.shape_picker as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
    assert not [
        name
        for name in imported
        if name == "maya" or name.startswith(("maya.", "tik.maya"))
    ]


def test_filtering_narrows_the_list(qapp):
    picker = ShapePicker()
    picker.set_filter("cub")
    assert "Cube" in picker.visible_names()
    assert "Circle" not in picker.visible_names()
    picker.set_filter("")
    assert "Circle" in picker.visible_names()


def test_choosing_emits_the_name(qapp):
    picker = ShapePicker()
    seen = []
    picker.shapeChosen.connect(seen.append)
    picker.choose("Diamond")
    assert seen == ["Diamond"]


def test_button_round_trips_a_value(qapp):
    button = ShapeButton()
    button.setValue("Cube")
    assert button.value() == "Cube"
    button.setValue("")
    assert button.value() == ""


def test_button_emits_when_the_picker_chooses(qapp):
    button = ShapeButton()
    seen = []
    button.shapeChosen.connect(seen.append)
    button.picker.choose("Star")
    assert seen == ["Star"]
    assert button.value() == "Star"


def test_button_shows_a_placeholder_when_unset(qapp):
    """An unset row draws the module default, greyed."""
    button = ShapeButton()
    button.setPlaceholder("CurvedCircle")
    assert button.value() == ""
    assert "CurvedCircle" in button.toolTip()


def test_a_button_builds_no_picker_until_it_is_opened(qapp):
    """The picker is 86 tiles with icons; a fold builds one button per control.

    Building them all eagerly cost ~60ms per button, so selecting a module
    with 14 controls stalled the Designer for most of a second on every
    selection change.
    """
    button = ShapeButton()
    assert button._picker is None

    opened = button.picker  # the property builds it on demand
    assert isinstance(opened, ShapePicker)
    assert button.picker is opened, "the picker must be built once, then kept"


def test_many_buttons_share_one_library_scan(qapp):
    """Each button rescanning the shape folder is per-control waste."""
    first, second = ShapeButton(), ShapeButton()
    assert first.library is second.library


def test_the_icon_cache_does_not_confuse_two_libraries(qapp, tmp_path, monkeypatch):
    """Polish searches the artist's folder; the rig build does not.

    Both can hold a 'Circle', so an icon cache keyed by name alone would hand
    one library the other's thumbnail.
    """
    from tik.core.control_shapes import ControlShapeLibrary
    from tik.shared.ui.shape_picker import default_library, thumbnail_for

    other = tmp_path / "other_shapes"
    other.mkdir()
    (other / "Circle.json").write_text('{"name": "Circle", "curves": []}')

    private = ControlShapeLibrary(include_user_path=False)
    private.add_path(other)

    shipped = default_library()
    assert shipped.get_path("Circle") != private.get_path("Circle")
    # The shipped Circle has a thumbnail; this stand-in has none, and must not
    # inherit one from the cache.
    assert thumbnail_for(shipped, "Circle") is not None
    assert thumbnail_for(private, "Circle") is None
