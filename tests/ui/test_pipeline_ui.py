"""Pipeline UI: model tree, DnD nesting, palette, settings, statuses, main window (no Maya)."""

import pytest

from tik.core.fields import FileField
from tik.shared.ui.Qt import QtCore
from tik.trigger.core import Action, IntField, StringField, clear_registries, register_action
from tik.trigger.handler import Session
from tik.trigger.ui.main import TriggerWindow
from tik.trigger.ui.model import MIME_PATH, MIME_TYPE, EnabledRole, LinkedRole, StatusRole
from tik.trigger.ui.session_view import SessionView
from trigger_fakes import FakeBackend


class Mark(Action):
    label = "Mark"
    tag = StringField("")
    amount = IntField(1, min=0)

    def run(self, ctx):
        ctx.backend.calls.append(("mark", ctx.path, self.tag))


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
        ctx.backend.calls.append(("saved", ctx.path))
        return ["x.trw"]


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_action("mark", category="build")(Mark)
    register_action("boom", category="utility")(Boom)
    register_action("weights", category="deform")(Weights)
    from tik.trigger.actions.reference.reference import Reference

    register_action("reference", category="structure")(Reference)
    yield
    clear_registries()


@pytest.fixture
def view(qapp):
    backend = FakeBackend()
    session = Session(backend)
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
    view.shelf.add_requested.emit("boom")
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
    assert ("saved", "weights") in view.session.backend.calls


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
    base = Session(FakeBackend())
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
    assert view.counter.text() == "2 / 2"
    assert view.build_until("mark")
    assert model.data(model.index_for_path("mark1"), StatusRole) == ""


def test_main_window_tabs_and_files(qapp, tmp_path):
    window = TriggerWindow(FakeBackend())
    window.ask_discard = lambda session: True
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
    window.toggle_shelf()
    assert window.current_view.shelf.collapsed
    assert window.close_tab(0)
    assert window.tabs.count() == 1
    window.close()
