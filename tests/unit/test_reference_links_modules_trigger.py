"""Referencing a session brings its modules too, unless you say otherwise.

Running another session's actions and containing its modules stay two objects
-- the same session can be referenced twice for a split pipeline run, and a
module exists once -- but wanting both is the ordinary case, so a reference
links the modules by default and says so with a checkbox.
"""

import pytest
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module, registry
from tik.trigger.core.document import Document
from tik.trigger.core.guide_document import GuideDocument, GuideRecord, ModuleEntry
from tik.trigger.session import Session


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    from tik.trigger.actions.kinematics.kinematics import Kinematics
    from tik.trigger.actions.reference.reference import Reference

    registry.ensure_registered(Kinematics)
    registry.ensure_registered(Reference)
    yield
    clear_registries()


def _base(tmp_path, *names):
    """A saved session holding one module per name."""
    document = Document()
    modules = []
    for index, name in enumerate(names):
        entry = ModuleEntry(
            instance_id=f"id{index}", module_type="toy_root", name=name, side="C"
        )
        entry.guides = [GuideRecord(role="root", position=(0.0, 0.0, 0.0))]
        modules.append(entry)
    document.guides = GuideDocument(modules=modules)
    path = tmp_path / "base.tr"
    document.save(path)
    return path


def _host(tmp_path):
    session = Session()
    session.file_path = tmp_path / "hero.tr"
    return session


def test_adding_a_reference_brings_its_modules(tmp_path):
    base = _base(tmp_path, "body", "arm")
    host = _host(tmp_path)
    host.add("reference", file=str(base))
    assert sorted(item.key for item in host.document.guides.modules) == ["arm", "body"]
    assert len(host.document.guides.references) == 1


def test_an_existing_reference_links_on_open(tmp_path):
    """The session that was saved before this behaviour existed."""
    base = _base(tmp_path, "body")
    host = _host(tmp_path)
    host.add("reference", file=str(base))
    # strip the link, leaving exactly the shape an older .tr has on disk
    host.document.guides.references = []
    host.document.guides.modules = []
    path = host.save(tmp_path / "hero.tr")

    reopened = Session.open(str(path))
    assert [item.key for item in reopened.document.guides.modules] == ["body"]
    assert reopened.validate() == []


def test_unticking_link_modules_drops_them(tmp_path):
    base = _base(tmp_path, "body")
    host = _host(tmp_path)
    handle = host.add("reference", file=str(base))
    assert host.document.guides.modules

    handle.link_modules = False
    host.resolve_references()
    assert host.document.guides.modules == []
    assert host.document.guides.references == []


def test_the_same_file_referenced_twice_links_once(tmp_path):
    """A split pipeline run: two references, one rig."""
    base = _base(tmp_path, "body")
    host = _host(tmp_path)
    host.add("reference", name="first", file=str(base))
    host.add("reference", name="second", file=str(base))
    assert len(host.document.guides.references) == 1
    assert [item.key for item in host.document.guides.modules] == ["body"]


def test_a_disabled_reference_links_nothing(tmp_path):
    base = _base(tmp_path, "body")
    host = _host(tmp_path)
    handle = host.add("reference", file=str(base))
    handle.enabled = False
    host.resolve_references()
    assert host.document.guides.modules == []


def test_a_hand_made_link_is_not_removed(tmp_path):
    """File > Reference Modules... has no pipeline reference behind it."""
    base = _base(tmp_path, "body")
    host = _host(tmp_path)
    host.link_modules(str(base))
    host.resolve_references()
    assert [item.key for item in host.document.guides.modules] == ["body"]


def test_a_missing_file_links_nothing_and_does_not_raise(tmp_path):
    host = _host(tmp_path)
    host.add("reference", file=str(tmp_path / "nope.tr"))
    assert host.document.guides.modules == []


def test_deleting_the_reference_action_removes_its_modules(tmp_path):
    """They are a link, not a copy: nothing keeps them once nothing wants them."""
    base = _base(tmp_path, "body")
    host = _host(tmp_path)
    handle = host.add("reference", file=str(base))
    assert [item.key for item in host.document.guides.modules] == ["body"]

    host.remove(handle.path)
    assert host.document.guides.modules == []
    assert host.document.guides.references == []


def test_deleting_a_reference_leaves_a_hand_made_link_alone(tmp_path):
    """One made through File > Reference Modules... answers to nobody."""
    base = _base(tmp_path, "body")
    host = _host(tmp_path)
    host.link_modules(str(base))
    handle = host.add("reference", file=str(base))
    host.remove(handle.path)
    assert [item.key for item in host.document.guides.modules] == ["body"]


def test_the_file_never_stores_the_borrowed_modules(tmp_path):
    """A reference is a link. The .tr holds the link and the overrides only."""
    import json

    base = _base(tmp_path, "body", "arm")
    host = _host(tmp_path)
    host.add("reference", file=str(base))
    path = host.save(tmp_path / "hero.tr")

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["guides"]["modules"] == []
    assert len(stored["guides"]["references"]) == 1
