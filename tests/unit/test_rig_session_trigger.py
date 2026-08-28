"""DCC-free tests for RigSession."""

import json

import pytest

from _fakes_trigger import FakeBackend, ToyChain, ToyRoot
from tik.trigger.core import (
    Action,
    ActionExecutionError,
    IntField,
    ParentRef,
    SessionError,
    SessionLoadError,
    clear_registries,
    register_action,
    register_module,
)
from tik.trigger.session import RigSession


class Count(Action):
    label = "Count"
    amount = IntField(1, min=0)

    def run(self, ctx):
        ctx.backend.calls.append(("count", self.amount))
        ctx.log("counted")


class Explode(Action):
    def run(self, ctx):
        raise RuntimeError("kaboom")


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    register_action("count")(Count)
    register_action("explode")(Explode)
    yield
    clear_registries()


def test_action_crud_and_unique_names():
    session = RigSession()
    first = session.add_action("count")
    second = session.add_action("count")
    assert [first.name, second.name] == ["count", "count1"]
    session.rename_action("count1", "later")
    with pytest.raises(SessionError):
        session.rename_action("later", "count")
    session.add_action("count", name="first", index=0)
    assert session.action_names() == ["first", "count", "later"]
    session.move_action("later", 0)
    assert session.action_names() == ["later", "first", "count"]
    session.set_enabled("first", False)
    assert not session.actions[1].enabled
    dup = session.duplicate_action("count")
    assert dup.name == "count1" and session.action_names()[-1] == "count1"
    session.remove_action("count1")
    assert "count1" not in session.action_names()
    with pytest.raises(SessionError):
        session.remove_action("ghost")


def test_action_settings_validated():
    session = RigSession()
    session.add_action("count")
    session.update_action_settings("count", {"amount": 5})
    assert session.action_settings("count") == {"amount": 5}
    from tik.core.fields import FieldValidationError

    with pytest.raises(FieldValidationError):
        session.update_action_settings("count", {"amount": -1})


def test_run_all_respects_enabled_until_and_wraps_errors():
    backend = FakeBackend()
    session = RigSession(backend)
    session.add_action("count", name="a")
    session.add_action("count", name="b")
    session.update_action_settings("b", {"amount": 2})
    session.add_action("count", name="c")
    session.add_action("explode", name="d")
    session.set_enabled("a", False)
    assert session.run_all(until="c") == ["b", "c"]
    assert ("count", 2) in backend.calls and ("count", 1) in backend.calls
    assert ("undo_open", "Trigger action: b") in backend.calls
    with pytest.raises(ActionExecutionError):
        session.run_all()
    assert session.run_all(until="b", reset_scene=True)[0] == "b"
    assert ("new_scene",) in backend.calls


def test_run_needs_backend():
    session = RigSession()
    session.add_action("count")
    with pytest.raises(SessionError):
        session.run_all()


def test_save_load_and_modified(tmp_path):
    session = RigSession(FakeBackend())
    assert not session.is_modified
    session.add_action("count")
    assert session.is_modified
    path = session.save(tmp_path / "my_rig")
    assert path.suffix == ".trg" and path.exists()
    assert not session.is_modified
    data = json.loads(path.read_text())
    assert data["schema"] == 3 and data["meta"]["backend"] == "fake"

    other = RigSession(file_path=str(path))
    assert other.action_names() == ["count"]
    other.new()
    assert other.file_path is None and other.actions == []
    with pytest.raises(SessionLoadError):
        RigSession(file_path=str(tmp_path / "missing.trg"))
    with pytest.raises(SessionError):
        RigSession().save()


def test_guides_snapshot_restore_export_import(tmp_path):
    backend = FakeBackend()
    root = backend.create_guides(ToyRoot(name="body"))
    backend.create_guides(
        ToyChain(name="tail", settings={"segments": 3}), parent=ParentRef(root.instance_id, "root")
    )
    session = RigSession(backend)
    snapshot = session.snapshot_guides()
    assert [item.name for item in snapshot] == ["body", "tail"]
    guides_file = session.export_guides(tmp_path / "guides")

    fresh_backend = FakeBackend()
    other = RigSession(fresh_backend)
    other.import_guides(str(guides_file))
    created = other.restore_guides()
    assert [item.name for item in created] == ["body", "tail"]
    assert created[1].parent.instance_id == created[0].instance_id
    assert created[1].settings == {"segments": 3}
    assert len(fresh_backend.instances) == 2
    other.restore_guides(clear_existing=True)
    assert len(fresh_backend.instances) == 2


def test_actions_export_import(tmp_path):
    session = RigSession()
    session.add_action("count", name="a")
    session.add_action("count", name="b")
    actions_file = session.export_actions(tmp_path / "acts")
    other = RigSession()
    other.add_action("count", name="a")
    imported = other.import_actions(str(actions_file), index=0)
    assert [item.name for item in imported] == ["a1", "b"]
    assert other.action_names() == ["a1", "b", "a"]
