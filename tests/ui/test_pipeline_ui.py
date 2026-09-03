"""Pipeline UI: model tree, DnD nesting, palette, settings, statuses, main window (no Maya)."""

import pytest

from tik.core.fields import FileField
from tik.shared.ui.Qt import QtCore
from tik.trigger.core import Action, IntField, StringField, clear_registries, register_action
from tik.trigger.session import Session
from tik.trigger.ui.main import TriggerWindow
from tik.trigger.ui.model import MIME_PATH, MIME_TYPE, EnabledRole, LinkedRole, StatusRole
from tik.trigger.ui.session_view import SessionView


CALLS: list = []


class Mark(Action):
    label = "Mark"
    tag = StringField("")
    amount = IntField(1, min=0)

    def run(self, ctx):
        CALLS.append(("mark", ctx.path, self.tag))


class Boom(Action):
    label = "Boom"

    def run(self, ctx):
        raise RuntimeError("boom")


class Weights(Action):
    label = "Weights"
    file = FileField("", extensions=[".trw"])

    def run(self, ctx):
        pass

    def save_from_scene(self, ctx):
        CALLS.append(("saved", ctx.path))
        return ["x.trw"]


# Scope is stamped on the class (like ``category`` and ``icon``), so a scoped
# variant needs its own subclass rather than a second registration of ``Mark``.
class Export(Mark):
    label = "Export"


class Either(Mark):
    label = "Either"


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_action("mark", category="build")(Mark)
    register_action("export", category="utility", scope="publish")(Export)
    register_action("either", category="utility", scope="both")(Either)
    register_action("boom", category="utility")(Boom)
    register_action("weights", category="deform")(Weights)
    from tik.trigger.actions.reference.reference import Reference

    register_action("reference", category="structure")(Reference)
    yield
    clear_registries()


@pytest.fixture
def view(qapp):
    session = Session()
    view = SessionView(session)
    view.show()
    yield view
    view.close()


def _paths(model, parent=QtCore.QModelIndex(), prefix=""):
    found = []
    for row in range(model.rowCount(parent)):
        index = model.index(row, 0, parent)
        found.append(model.handle(index).path)
        found.extend(_paths(model, index))
    return found


def test_add_via_palette_and_shelf(view):
    assert view.palette.visible_keys()[:1]  # entries present
    view.add_action("mark")
    view.add_action("mark")  # after current -> sibling
    view.add_action("weights", as_child=True)
    assert _paths(view.model) == ["mark", "mark1", "mark1/weights"]
    assert view.current_path() == "mark1/weights"
    view.shelf.activated.emit("boom")
    assert _paths(view.model) == ["mark", "mark1", "mark1/weights", "mark1/boom"]
    assert view.settings.handle.path == "mark1/boom"
    view.palette.search.setText("wei")
    assert view.palette.visible_keys() == ["weights"]
    view.palette._choose(False)
    assert "mark1/weights1" in _paths(view.model)


def test_settings_panel_edits_session(view):
    handle = view.add_action("mark")
    view.settings.form.widget("amount").setValue(5)
    assert view.session["mark"].amount == 5
    view.settings.form.widget("tag").setText("hello")
    view.settings.form.widget("tag").editingFinished.emit()
    assert view.session["mark"].tag == "hello"
    assert view.session.is_modified
    weights = view.add_action("weights")
    assert view.settings.save_button.isVisible()
    view.settings.save_button.click()
    assert ("saved", "weights") in CALLS


def test_drag_drop_nesting_and_reorder(view):
    view.add_action("mark")
    view.add_action("mark")
    view.add_action("mark")
    model = view.model
    assert _paths(model) == ["mark", "mark1", "mark2"]
    data = model.mimeData([model.index_for_path("mark2")])
    assert model.dropMimeData(data, QtCore.Qt.MoveAction, -1, 0, model.index_for_path("mark"))
    assert _paths(model) == ["mark", "mark/mark2", "mark1"]
    data = model.mimeData([model.index_for_path("mark1")])
    assert model.dropMimeData(data, QtCore.Qt.MoveAction, 0, 0, QtCore.QModelIndex())
    assert _paths(model) == ["mark1", "mark", "mark/mark2"]
    mime = QtCore.QMimeData()
    mime.setData(MIME_TYPE, b"weights")
    assert model.dropMimeData(mime, QtCore.Qt.CopyAction, 1, 0, QtCore.QModelIndex())
    assert _paths(model) == ["mark1", "weights", "mark", "mark/mark2"]


def test_reference_rows_are_linked_and_checkable(view, tmp_path):
    base = Session()
    base.add("mark", "kin", tag="K")
    scripts = base.add("mark", "scripts")
    scripts.add("mark", "head")
    (tmp_path / "rigs").mkdir()
    base.save(tmp_path / "rigs" / "base_v001.tr")
    view.session.save(tmp_path / "hero.tr")
    view.add_action("reference")
    view.session["reference"].file = "rigs/base_v001.tr"
    view.refresh()
    assert _paths(view.model) == ["reference", "reference/kin", "reference/scripts", "reference/scripts/head"]
    head = view.model.index_for_path("reference/scripts/head")
    assert view.model.data(head, LinkedRole) is True
    assert view.model.data(head, QtCore.Qt.CheckStateRole) == QtCore.Qt.Checked
    assert view.model.setData(head, QtCore.Qt.Unchecked, QtCore.Qt.CheckStateRole)
    assert view.session["reference"].node.settings["overrides"]["scripts/head"] == {"enabled": False}
    assert view.model.data(head, EnabledRole) is False
    # editing a linked row's setting creates an override, shown in the panel
    view.select_path("reference/kin")
    assert view.settings.linked_note.isVisible()
    view.settings.form.widget("tag").setText("OVER")
    view.settings.form.widget("tag").editingFinished.emit()
    assert view.session["reference"]["kin"].tag == "OVER"
    assert "tag" in view.settings.form._overridden
    view.settings.reset_button.click()
    assert view.session["reference"]["kin"].tag == "K"
    # cannot drop onto a linked row
    data = view.model.mimeData([view.model.index_for_path("reference")])
    assert not view.model.canDropMimeData(data, QtCore.Qt.MoveAction, -1, 0, head)


@pytest.fixture(autouse=True)
def _no_scene(monkeypatch):
    """Qt tests have no Maya, so the runner's two scene calls are stubbed."""
    import contextlib

    from tik.trigger.maya import runner

    monkeypatch.setattr(runner, "new_scene", lambda: CALLS.append(("new_scene",)))
    monkeypatch.setattr(runner, "undo_chunk", lambda label: contextlib.nullcontext())


def test_build_updates_statuses_and_log(view):
    view.add_action("mark")
    view.add_action("boom")
    view.add_action("mark")
    assert not view.build()
    model = view.model
    assert model.data(model.index_for_path("mark"), StatusRole) == "done"
    assert model.data(model.index_for_path("boom"), StatusRole) == "failed"
    assert model.data(model.index_for_path("mark1"), StatusRole) == ""
    view.session["boom"].enabled = False
    assert view.build()
    assert model.data(model.index_for_path("mark1"), StatusRole) == "done"
    assert view.counter.text().startswith("2 / 2")
    assert view.build_until("mark")
    assert model.data(model.index_for_path("mark1"), StatusRole) == ""


def _stub_designer(scene=None):
    from stub import StubScene
    from tik.trigger.ui.designer import GuideDesigner

    return GuideDesigner(scene=scene if scene is not None else StubScene())


def test_the_shell_is_one_menu_bar_over_the_session_tabs(qapp):
    """The session is the outer container; there is no mode above it."""
    window = TriggerWindow(designer_factory=_stub_designer)
    window.show()
    assert not hasattr(window, "mode_bar")
    assert window.centralWidget() is window.tabs
    assert window.menu_bar is window.menus
    assert [action.text() for action in window.menu_bar.actions()][0] == "&File"
    window.close()


def test_a_session_tab_holds_both_views(qapp):
    window = TriggerWindow(designer_factory=_stub_designer)
    window.show()
    view = window.views[0]
    titles = [view.sub_tabs.tabText(i) for i in range(view.sub_tabs.count())]
    assert titles == ["Session", "Guide Designer"]
    window.close()


def test_the_designer_is_built_lazily(qapp):
    window = TriggerWindow(designer_factory=_stub_designer)
    window.show()
    assert window.active_designer is None
    window.views[0].sub_tabs.setCurrentIndex(1)
    assert window.active_designer is not None
    window.close()


def test_open_guide_designer_shows_the_guides_view(qapp):
    window = TriggerWindow(designer_factory=_stub_designer)
    window.show()
    designer = window.open_guide_designer()
    assert designer is window.views[0].designer
    assert window.views[0].on_designer_tab
    assert window.windowTitle().endswith("Guides")
    window.close()



def test_main_window_tabs_and_files(qapp, tmp_path):
    window = TriggerWindow()
    window.ask_discard = lambda session: True
    window.show()
    assert window.tabs.count() == 1
    view = window.current_view
    view.add_action("mark")
    window.save_session_as(str(tmp_path / "hero"))
    assert window.tabs.tabText(0) == "hero.tr"
    window.increment_session()
    assert window.tabs.tabText(0) == "hero_v001.tr"
    other = window.new_session()
    assert window.tabs.count() == 2 and window.current_view is other
    window.open_session(str(tmp_path / "hero.tr"))
    assert window.tabs.count() == 2  # the empty untitled tab was replaced
    assert window.session.name == "hero.tr"
    window.open_session(str(tmp_path / "hero.tr"))
    assert window.tabs.count() == 2  # already open -> focused
    assert window.recent_files and window.recent_files[0].endswith("hero.tr")
    window.toggle_shelf()
    assert not window.current_view.shelf_visible
    window.undo()
    assert window.menu_bar.actions()[0].text() == "&File"
    assert window.status.text("version").startswith("tik.trigger")
    assert window.close_tab(0)
    assert window.tabs.count() == 1
    window.close()


def test_session_undo_redo(view):
    view.add_action("mark")
    view.add_action("mark")
    assert view.session.paths() == ["mark", "mark1"]
    assert view.session.undo()
    assert view.session.paths() == ["mark"]
    assert view.session.redo()
    assert view.session.paths() == ["mark", "mark1"]
    view.session["mark"].amount = 4
    assert view.session.undo() and view.session["mark"].amount == 1


def test_reference_children_appear_after_file_edit(view, tmp_path):
    base = Session()
    base.add("mark", "kin")
    (tmp_path / "rigs").mkdir()
    base.save(tmp_path / "rigs" / "base.tr")
    view.session.save(tmp_path / "hero.tr")
    view.add_action("reference")
    assert _paths(view.model) == ["reference"]
    field = view.settings.form.widget("file")
    field.line.setText("rigs/base.tr")
    field.line.editingFinished.emit()
    assert _paths(view.model) == ["reference", "reference/kin"]


# ------------------------------------------------- graph view: space ports
def _graph_scene():
    from tik.trigger.ui.graph import GraphScene

    scene = GraphScene()
    scene.add_node("body", "body", "Base", [], ["root"], "#888888")
    scene.add_node("head", "head", "Base", [], ["root"], "#888888")
    scene.add_node(
        "L_arm", "L_arm", "Arm", ["root"], ["hand"], "#888888", spaces=["ik_hand"]
    )
    return scene


def test_space_port_is_marked():
    scene = _graph_scene()
    node = scene.nodes["L_arm"]
    assert node.inputs["root"].space is False
    assert node.inputs["ik_hand"].space is True


def test_single_input_port_keeps_one_wire():
    scene = _graph_scene()
    scene.add_wire("body.root", "L_arm.root", True)
    port = scene.nodes["L_arm"].inputs["root"]
    assert len(scene.wires_for_input(port)) == 1


def test_a_node_without_spaces_still_builds():
    from tik.trigger.ui.graph import GraphScene

    scene = GraphScene()
    node = scene.add_node("body", "body", "Base", ["root"], ["root"], "#888888")
    assert set(node.inputs) == {"root"}



def test_space_rows_become_ports():
    from tik.trigger.core import Input, Module

    class Spaced(Module):
        inputs = (Input("root", primary=True),)
        space_controls = ("ik",)

    settings = {"anim_spaces": [{"control": "ik", "mode": "parent", "label": "chest"}]}
    assert Spaced.input_names(settings) == ["root", "ik_chest"]
    assert [item.name for item in Spaced.space_inputs(settings)] == ["ik_chest"]


# ------------------------------------------------------------ build/publish
def test_model_can_be_built_on_the_publish_phase(qapp):
    from tik.trigger.core.document import BUILD, PUBLISH
    from tik.trigger.ui.model import PipelineModel

    session = Session()
    session.add("mark", "kine")
    session.publish.add("export", "fbx")

    build_model = PipelineModel(session)
    publish_model = PipelineModel(session, phase=PUBLISH)
    assert build_model.phase == BUILD
    assert publish_model.phase == PUBLISH
    assert build_model.rowCount() == 1
    assert publish_model.rowCount() == 1
    assert publish_model.data(publish_model.index(0, 0)) == "fbx"


def test_shelf_drop_of_a_build_only_action_is_refused_by_the_publish_model(qapp):
    from tik.trigger.core.document import PUBLISH
    from tik.trigger.ui.model import MIME_TYPE, PipelineModel

    session = Session()
    model = PipelineModel(session, phase=PUBLISH)
    data = QtCore.QMimeData()
    data.setData(MIME_TYPE, b"mark")  # build-only
    assert not model.canDropMimeData(data, QtCore.Qt.CopyAction, -1, -1, QtCore.QModelIndex())
    assert not model.dropMimeData(data, QtCore.Qt.CopyAction, -1, -1, QtCore.QModelIndex())
    assert session.publish.paths() == []

    ok = QtCore.QMimeData()
    ok.setData(MIME_TYPE, b"export")
    assert model.canDropMimeData(ok, QtCore.Qt.CopyAction, -1, -1, QtCore.QModelIndex())
    assert model.dropMimeData(ok, QtCore.Qt.CopyAction, -1, -1, QtCore.QModelIndex())
    assert session.publish.paths() == ["export"]


def test_mime_paths_carry_their_phase(qapp):
    from tik.trigger.ui.model import MIME_PATH, PipelineModel

    session = Session()
    session.add("mark", "kine")
    model = PipelineModel(session)
    data = model.mimeData([model.index(0, 0)])
    assert bytes(data.data(MIME_PATH)).decode("utf-8") == "build:kine"


def test_dragging_a_both_scoped_action_between_the_two_trees(qapp):
    from tik.trigger.core.document import PUBLISH
    from tik.trigger.ui.model import PipelineModel

    session = Session()
    session.add("either", "hook")
    build_model = PipelineModel(session)
    publish_model = PipelineModel(session, phase=PUBLISH)

    data = build_model.mimeData([build_model.index(0, 0)])
    assert publish_model.dropMimeData(data, QtCore.Qt.MoveAction, -1, -1, QtCore.QModelIndex())
    assert session.paths() == []
    assert session.publish.paths() == ["hook"]


def test_dragging_a_build_only_action_into_publish_is_refused_and_changes_nothing(qapp):
    from tik.trigger.core.document import PUBLISH
    from tik.trigger.ui.model import PipelineModel

    session = Session()
    session.add("mark", "kine")
    build_model = PipelineModel(session)
    publish_model = PipelineModel(session, phase=PUBLISH)

    data = build_model.mimeData([build_model.index(0, 0)])
    assert not publish_model.dropMimeData(data, QtCore.Qt.MoveAction, -1, -1, QtCore.QModelIndex())
    assert session.paths() == ["kine"]
    assert session.publish.paths() == []


def test_session_view_has_two_trees(qapp):
    from tik.trigger.core.document import BUILD, PUBLISH

    session = Session()
    session.add("mark", "kine")
    session.publish.add("export", "fbx")
    view = SessionView(session)

    assert view.trees[BUILD] is view.tree
    assert view.trees[PUBLISH] is view.publish_tree
    assert view.models[PUBLISH].rowCount() == 1
    assert view.focus_phase == BUILD


def test_focus_phase_drives_the_current_row(qapp):
    from tik.trigger.core.document import BUILD, PUBLISH

    session = Session()
    session.add("mark", "kine")
    session.publish.add("export", "fbx")
    view = SessionView(session)

    view.tree.setCurrentIndex(view.model.index(0, 0))
    view.set_focus_phase(BUILD)
    assert view.current_path() == "kine"
    assert view.current_phase == BUILD

    view.publish_tree.setCurrentIndex(view.publish_model.index(0, 0))
    view.set_focus_phase(PUBLISH)
    assert view.current_path() == "fbx"
    assert view.current_phase == PUBLISH


def test_the_shelf_offers_only_actions_that_fit_the_focused_phase(qapp):
    from tik.trigger.core.document import BUILD, PUBLISH

    view = SessionView(Session())
    build_keys = set(view.shelves[BUILD].tiles)
    publish_keys = set(view.shelves[PUBLISH].tiles)
    assert "mark" in build_keys and "mark" not in publish_keys
    assert "export" in publish_keys and "export" not in build_keys
    assert "either" in build_keys and "either" in publish_keys

    view.set_focus_phase(PUBLISH)
    assert view.shelf_stack.currentWidget() is view.shelves[PUBLISH]
    assert {entry.key for entry in view.palette.entries} == publish_keys


def test_adding_from_the_shelf_lands_in_the_focused_phase(qapp):
    from tik.trigger.core.document import PUBLISH

    session = Session()
    view = SessionView(session)
    view.set_focus_phase(PUBLISH)
    view.add_action("export")
    assert session.publish.paths() == ["export"]
    assert session.paths() == []


def test_publish_rows_offer_no_run_affordance(qapp):
    from tik.trigger.core.document import BUILD, PUBLISH

    session = Session()
    session.publish.add("export", "fbx")
    view = SessionView(session)
    handle = view.models[PUBLISH].handle(view.publish_model.index(0, 0))

    view.settings.set_handle(handle)
    # isVisibleTo, not isVisible: the window was never shown, so isVisible() is
    # False for every widget and would pass this assertion vacuously
    assert not view.settings.run_button.isVisibleTo(view.settings)

    assert view.run_step("fbx") is False  # refused by the session, reported not raised

    labels = [item.text() for item in view.context_menu_actions(PUBLISH, handle)]
    assert "Run step" not in labels
    assert "Build until here" not in labels
    assert "Delete" in labels  # the rest of the menu is unchanged

    session.add("mark", "kine")
    view.refresh()
    build_handle = view.models[BUILD].handle(view.model.index(0, 0))
    view.settings.set_handle(build_handle)
    assert view.settings.run_button.isVisibleTo(view.settings)
    build_labels = [item.text() for item in view.context_menu_actions(BUILD, build_handle)]
    assert "Run step" in build_labels


def test_build_and_publish_button_is_wired(qapp):
    session = Session()
    session.add("mark", "kine")
    session.publish.add("either", "fbx")
    view = SessionView(session)

    assert view.publish_button.isEnabled()
    CALLS.clear()
    view.publish_button.click()
    assert [item[1] for item in CALLS if item[0] == "mark"] == ["kine", "fbx"]


def test_build_alone_leaves_the_publish_list_alone(qapp):
    session = Session()
    session.add("mark", "kine")
    session.publish.add("either", "fbx")
    view = SessionView(session)

    CALLS.clear()
    assert view.build()
    assert [item[1] for item in CALLS if item[0] == "mark"] == ["kine"]


def test_statuses_are_routed_to_the_right_tree(qapp):
    from tik.trigger.core.document import BUILD, PUBLISH

    session = Session()
    session.add("mark", "kine")
    session.publish.add("either", "fbx")
    view = SessionView(session)
    assert view.build_and_publish()

    assert view.models[BUILD].data(view.model.index(0, 0), StatusRole) == "done"
    assert view.models[PUBLISH].data(view.publish_model.index(0, 0), StatusRole) == "done"
    view.clear_statuses()
    assert view.models[PUBLISH].data(view.publish_model.index(0, 0), StatusRole) == ""
