"""TriggerWindow driven with the fake backend (no Maya)."""

import pytest

from tik.shared.ui.Qt import QtCore
from tik.trigger.core import Action, IntField, ParentRef, clear_registries, register_action, register_module
from tik.trigger.session import RigSession
from tik.trigger.ui import TriggerWindow
from trigger_fakes import FakeBackend, ToyChain, ToyRoot


class Count(Action):
    label = "Count"
    amount = IntField(1, min=0)

    def run(self, ctx):
        ctx.backend.calls.append(("count", self.amount))


@pytest.fixture
def window(qapp):
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    register_action("count")(Count)
    backend = FakeBackend()
    win = TriggerWindow(backend, RigSession(backend))
    win.ask_discard = lambda: True  # never block on the modal in tests
    yield win
    win.close()
    clear_registries()


def _select_module(panel, module_type):
    for row in range(panel.module_list.count()):
        item = panel.module_list.item(row)
        if item.data(QtCore.Qt.UserRole) == module_type:
            panel.module_list.setCurrentItem(item)
            return
    raise AssertionError(module_type)


def test_guides_create_tree_and_properties(window):
    panel = window.guides_panel
    backend = window.backend
    _select_module(panel, "toy_root")
    root = panel.create_guides()[0]
    assert root.module_type == "toy_root"
    backend.selection = ParentRef(root.instance_id, "root")
    _select_module(panel, "toy_chain")
    panel.side_combo.setCurrentText("Both")
    created = panel.create_guides()
    assert [item.side for item in created] == ["L", "R"]
    assert created[0].parent.instance_id == root.instance_id
    assert panel.tree.topLevelItemCount() == 1
    assert panel.tree.topLevelItem(0).childCount() == 2

    # property editor writes settings through the backend
    assert panel.current.instance_id == created[-1].instance_id
    panel.form.widget("segments").setValue(5)
    assert backend.settings[created[-1].instance_id] == {"segments": 5}

    panel.name_edit.set_name("tail")
    panel.name_edit.setText("tail_R")
    panel.name_edit.editingFinished.emit()
    assert any(item.name == "tail_R" for item in backend.instances)

    panel.delete_current()
    assert len(backend.instances) == 2


def test_build_from_panel_logs(window):
    panel = window.guides_panel
    _select_module(panel, "toy_root")
    panel.create_guides()
    panel.rig_name.setText("hero")
    report = panel.build()
    assert report.count == 1
    assert ("rig_root", "hero") in window.backend.calls
    assert "Built 1 module(s)" in window.log.toPlainText()


def test_actions_panel_crud_and_run(window, tmp_path):
    panel = window.actions_panel
    first = panel.add_action()
    second = panel.add_action()
    assert [first.name, second.name] == ["count", "count1"]
    assert panel.current_name() == "count1"
    panel.move_current(-1)
    assert window.session.action_names() == ["count1", "count"]
    panel.form.widget("amount").setValue(4)
    assert window.session.action_settings("count1") == {"amount": 4}
    panel.list.item(1).setCheckState(QtCore.Qt.Unchecked)
    assert not window.session.actions[1].enabled
    panel.run_all()
    assert ("count", 4) in window.backend.calls
    assert ("count", 1) not in window.backend.calls
    panel.duplicate_current()
    assert window.session.action_names() == ["count1", "count2", "count"]
    panel.remove_current()
    assert window.session.action_names() == ["count1", "count"]

    window.save_session_as(str(tmp_path / "ui_session"))
    assert window.windowTitle() == "Trigger - ui_session.trg"
    window.new_session()
    assert window.session.actions == []
    window.open_session(str(tmp_path / "ui_session.trg"))
    assert window.actions_panel.list.count() == 2
