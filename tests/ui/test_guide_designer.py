"""Guide Designer + binding, driven by the fake backend (no Maya)."""

import pytest

from tik.shared.ui.binding import Binder, BindingManager, bind
from tik.shared.ui.Qt import QtCore, QtWidgets
from tik.trigger.core import clear_registries, register_module
from tik.trigger.core.schemas import ParentRef
from tik.trigger.ui.guide_designer import GuideDesigner
from trigger_fakes import FakeBackend, ToyChain, ToyRoot


class FakeAdapter:
    store: dict = {}
    observers: dict = {}

    def __init__(self, plug_path):
        self.plug_path = plug_path

    def exists(self):
        return self.plug_path in FakeAdapter.store

    def get(self):
        return FakeAdapter.store[self.plug_path]

    def set(self, value):
        FakeAdapter.store[self.plug_path] = value

    def observe(self, callback):
        FakeAdapter.observers[self.plug_path] = callback

    def unobserve(self):
        FakeAdapter.observers.pop(self.plug_path, None)

    @classmethod
    def poke(cls, plug_path, value):
        cls.store[plug_path] = value
        if plug_path in cls.observers:
            cls.observers[plug_path]()


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    FakeAdapter.store.clear()
    FakeAdapter.observers.clear()
    yield
    clear_registries()


def test_binders_both_directions(qapp):
    FakeAdapter.store["node.count"] = 3
    spin = QtWidgets.QSpinBox()
    manager = BindingManager()
    binder = manager.add(bind("node.count", spin, adapter=FakeAdapter("node.count")))
    assert binder.active and spin.value() == 3
    spin.setValue(7)
    assert FakeAdapter.store["node.count"] == 7
    FakeAdapter.poke("node.count", 9)
    assert spin.value() == 9
    check = QtWidgets.QCheckBox()
    FakeAdapter.store["node.flag"] = True
    manager.add(bind("node.flag", check, direction="to_widget", adapter=FakeAdapter("node.flag")))
    assert check.isChecked()
    check.setChecked(False)
    assert FakeAdapter.store["node.flag"] is True  # one-way
    missing = manager.add(bind("node.later", QtWidgets.QLineEdit(), adapter=FakeAdapter("node.later")))
    assert not missing.active and not missing.widget.isEnabled()
    FakeAdapter.store["node.later"] = "hi"
    assert manager.reconnect() == 0 and missing.widget.text() == "hi"
    manager.clear()
    assert len(manager) == 0 and "node.count" not in FakeAdapter.observers


@pytest.fixture
def designer(qapp):
    backend = FakeBackend()

    def adapter_factory(plug_path):
        FakeAdapter.store.setdefault(plug_path, 2 if plug_path.endswith("segments") else True)
        return FakeAdapter(plug_path)

    window = GuideDesigner(backend, binding_adapter=adapter_factory)
    window.show()
    yield window
    window.close()


def test_create_side_parent_tree(designer):
    backend = designer.backend
    designer.set_side("C")
    roots = designer.create_guides("toy_root")
    assert len(roots) == 1 and designer.tree.topLevelItemCount() == 1
    designer.set_side("Both")
    chains = designer.create_guides("toy_chain")
    assert [item.side.value for item in chains] == ["L", "R"]
    assert all(item.instance.parent.instance_id == roots[0].instance_id for item in chains)
    assert designer.tree.topLevelItem(0).childCount() == 2
    assert designer.current.instance_id == chains[-1].instance_id
    assert designer.type_label.text().startswith("Toy Chain")
    assert ("select", chains[-1].instance_id) in backend.calls


def test_properties_edit_and_binding_refresh(designer):
    designer.set_side("L")
    chain = designer.create_guides("toy_chain")[0]
    spin = designer.form.widget("segments")
    spin.setValue(4)
    assert designer.backend.settings[chain.instance_id]["segments"] == 4
    FakeAdapter.poke(f"{chain.instance_id}.segments", 6)
    assert spin.value() == 6
    designer.inherit_orientation.setChecked(False)
    assert FakeAdapter.store[f"{chain.instance_id}.useRefOri"] is False
    designer.name_edit.setText("tail")
    designer.name_edit.editingFinished.emit()
    assert designer.current.name == "tail"
    assert designer.tree.currentItem().text(0) == "tail"


def test_reparent_mirror_delete(designer):
    designer.set_side("C")
    root = designer.create_guides("toy_root")[0]
    designer.tree.clearSelection()
    designer._set_current(None)
    designer.set_side("L")
    chain = designer.create_guides("toy_chain")[0]
    assert chain.instance.parent is None
    designer.reparent(chain.instance_id, root.instance_id)
    assert designer.guides.get(chain.instance_id).instance.parent.instance_id == root.instance_id
    designer.reparent(chain.instance_id, None)
    assert designer.guides.get(chain.instance_id).instance.parent is None
    designer.tree.setCurrentItem(designer.item_for(chain.instance_id))
    designer.mirror_current()
    sides = sorted(handle.side.value for handle in designer.guides.instances() if handle.module_type == "toy_chain")
    assert sides == ["L", "R"]
    designer.tree.setCurrentItem(designer.item_for(chain.instance_id))
    designer.delete_current()
    assert all(handle.instance_id != chain.instance_id for handle in designer.guides.instances())


def test_scene_selection_syncs_tree(designer):
    designer.set_side("C")
    root = designer.create_guides("toy_root")[0]
    designer.set_side("L")
    chain = designer.create_guides("toy_chain")[0]
    designer.backend.selection = ParentRef(root.instance_id, "root")
    designer.backend.observer_callback("SelectionChanged")
    assert designer.current.instance_id == root.instance_id
    designer.backend.observer_callback("DagObjectCreated")
    assert designer.tree.topLevelItemCount() == 1


def test_export_import_and_test_build(designer, tmp_path, monkeypatch):
    designer.set_side("C")
    designer.create_guides("toy_root")
    calls = []
    monkeypatch.setattr(designer.guides, "export", lambda path, *handles: calls.append(("export", str(path), len(handles))) or tmp_path / "g.trg")
    monkeypatch.setattr(designer.guides, "import_", lambda path, reset=False: calls.append(("import", str(path), reset)) or [])
    designer.export_file(str(tmp_path / "g.trg"))
    assert calls[-1] == ("export", str(tmp_path / "g.trg"), 1)
    assert designer.file_label.text() == "g.trg"
    designer.import_file(str(tmp_path / "g.trg"), reset=True)
    assert calls[-1] == ("import", str(tmp_path / "g.trg"), True)
    report = designer.test_build()
    assert report.count == 1 and ("rig_root", "test") in designer.backend.calls
