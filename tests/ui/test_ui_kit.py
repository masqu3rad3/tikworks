"""Shared UI kit: versioned field, tile grid, collapsible, watcher, window."""

from tik.shared.ui.collapsible import CollapsibleGroup
from tik.shared.ui.maya_window import HAS_MAYA, MayaToolWindow
from tik.shared.ui.Qt import QtWidgets
from tik.shared.ui.scene_watcher import SceneWatcher
from tik.shared.ui.status import StatusFields
from tik.shared.ui.tile_grid import TileEntry, TileGrid
from tik.shared.ui.versioned_field import VersionedFileField


def test_versioned_field_states_and_stepping(qapp, tmp_path):
    for number in (1, 2, 4):
        (tmp_path / f"hero_v{number:03d}.tr").write_text("{}")
    (tmp_path / "plain.tr").write_text("{}")
    field = VersionedFileField([".tr"], base_dir=lambda: str(tmp_path))
    seen = []
    field.changed.connect(seen.append)
    field.setValue("hero_v002.tr")
    assert field.state == "older" and "latest v004" in field.badge.text()
    assert field.step(1) and field.value() == "hero_v004.tr" and field.state == "latest"
    assert not field.step(1)
    assert field.step(-1) and field.value() == "hero_v002.tr"
    assert field.step(-1) and field.value() == "hero_v001.tr"
    assert seen[-1] == "hero_v001.tr"
    field.setValue("plain.tr")
    assert field.state == "plain" and not field.badge.isVisible()
    field.setValue("hero_v009.tr")
    assert field.state == "missing"
    field.setValue("")
    assert field.state == "empty"


def test_tile_grid_reflows(qapp):
    entries = [
        TileEntry(f"a{index}", f"Action {index}", "build" if index < 4 else "deform")
        for index in range(6)
    ]
    grid = TileGrid(entries, "application/x-test", columns_hint=2)
    grid.resize(400, 300)
    grid.show()
    qapp.processEvents()
    assert grid.columns >= 4
    grid.resize(120, 300)
    qapp.processEvents()
    assert grid.columns == 1
    clicked = []
    grid.activated.connect(clicked.append)
    grid.tiles["a2"].click()
    assert clicked == ["a2"]
    grid.close()


def test_collapsible_group(qapp):
    group = CollapsibleGroup("Inputs")
    label = QtWidgets.QLabel("x")
    group.content_layout.addWidget(label)
    group.show()
    assert group.is_expanded()
    group.set_expanded(False)
    assert not group.is_expanded() and not label.isVisibleTo(group)
    group.close()


def test_scene_watcher_debounces_and_guards(qapp):
    calls = []
    installed = []

    def install(event, callback):
        installed.append(event)
        return len(installed)

    watcher = SceneWatcher(
        lambda event: calls.append(event),
        install_job=install,
        kill_job=lambda job: None,
    )
    watcher.install()
    assert installed and watcher.jobs
    watcher.notify("SelectionChanged")
    watcher.notify("DagObjectCreated")
    watcher.notify("SelectionChanged")
    assert calls == []
    watcher.flush()
    assert calls == ["DagObjectCreated"]  # coalesced, structural event wins
    with watcher.mute():
        watcher.notify("SelectionChanged")
    watcher.flush()
    assert calls == ["DagObjectCreated"]

    reentrant = []

    def refresh(event):
        reentrant.append(event)
        watcher.notify("Undo")  # must not recurse

    watcher._on_invalidate = refresh
    watcher.notify("SceneOpened")
    watcher.flush()
    assert reentrant == ["SceneOpened"]
    watcher.uninstall()
    assert watcher.jobs == []


def test_tool_window_headless(qapp):
    class Tool(MayaToolWindow):
        WINDOW_NAME = "TestTool"

    window = Tool()
    window.register_script_job(42)
    window.show_tool()
    assert window.objectName() == "TestTool" and window.isVisible()
    assert not HAS_MAYA
    window.close()
    assert window._script_jobs == []


def test_filter_bar_keywords_or_together(qapp):
    from tik.shared.ui.filter_bar import FilterBar

    bar = FilterBar()
    assert bar.matches("anything")
    bar.set_text("arm")
    assert bar.matches("L_arm") and not bar.matches("spine")
    bar.commit()
    bar.set_text("spi")
    assert bar.keywords == ["arm"] and bar.matches("spine") and bar.matches("R_arm")
    bar.commit()
    bar.commit()  # duplicate/empty commits are absorbed
    assert bar.keywords == ["arm", "spi"]
    bar._remove_last()
    assert bar.keywords == ["arm"]
    bar.clear()
    assert bar.keywords == [] and bar.matches("zzz")


def test_status_fields_on_a_plain_strip(qapp):
    strip = QtWidgets.QWidget()
    fields = StatusFields(strip, ("modules", "file"))
    fields.set("modules", "3 module(s)")
    fields.set_activity("Ready")
    assert fields.text("modules") == "3 module(s)"
    assert fields.activity.text() == "Ready"
    # activity, separator and both field labels all live on the strip
    assert len(strip.findChildren(QtWidgets.QLabel)) == 4
