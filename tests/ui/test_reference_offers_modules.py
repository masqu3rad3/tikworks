"""Pointing a pipeline reference at a session offers to link its modules too.

Two different dependencies happen to share a file -- "I run their steps" and
"my rig contains their modules" -- and a rigger who wants the second should not
have to know it is a separate object. Referencing a session that has modules
and never being asked leaves a rig whose kinematics names ids nothing in the
session can resolve.
"""

import pathlib

import pytest
from toy_modules import ToyChain, ToyRoot

from tik.shared.ui import feedback
from tik.trigger.core import clear_registries, register_module, registry
from tik.trigger.core.document import Document
from tik.trigger.core.guide_document import GuideDocument, GuideRecord, ModuleEntry
from tik.trigger.session import Session
from tik.trigger.ui.session_view import SessionView


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


@pytest.fixture(autouse=True)
def _clean_handler():
    previous = feedback.set_handler(None)
    yield
    feedback.set_handler(previous)


def _base(tmp_path, with_modules=True):
    """A saved session, with or without modules of its own."""
    document = Document()
    if with_modules:
        entry = ModuleEntry(
            instance_id="bbb", module_type="toy_root", name="body", side="C"
        )
        entry.guides = [GuideRecord(role="root", position=(0.0, 0.0, 0.0))]
        document.guides = GuideDocument(modules=[entry])
    path = tmp_path / "base.tr"
    document.save(path)
    return path


def _view(tmp_path):
    session = Session()
    session.file_path = tmp_path / "hero.tr"
    session.document.save(session.file_path)
    return SessionView(session)


def _point_reference_at(view, path):
    """What the settings panel does when a reference gains its file."""
    handle = view.session.add("reference", file=str(path))
    view.settings.set_handle(handle)
    view._on_settings_edited(handle.path)
    return handle


def test_pointing_a_reference_at_a_rig_offers_to_link_its_modules(qapp, tmp_path):
    base = _base(tmp_path)
    view = _view(tmp_path)
    asked = []

    def _handler(kind, title, text, details, buttons):
        asked.append(text)
        return "Link"

    feedback.set_handler(_handler)
    _point_reference_at(view, base)

    assert asked, "a session with modules must offer to link them"
    linked = view.session.document.guides.references
    assert [pathlib.Path(item.file) for item in linked] == [pathlib.Path(base)]
    assert [entry.key for entry in view.session.document.guides.modules] == ["body"]


def test_declining_links_nothing(qapp, tmp_path):
    base = _base(tmp_path)
    view = _view(tmp_path)
    feedback.set_handler(lambda *_args: "Not now")
    _point_reference_at(view, base)
    assert view.session.document.guides.references == []


def test_a_session_with_no_modules_asks_nothing(qapp, tmp_path):
    """Nothing to link, so nothing to interrupt anybody about."""
    base = _base(tmp_path, with_modules=False)
    view = _view(tmp_path)
    asked = []
    feedback.set_handler(lambda *args: asked.append(args) or "Link")
    _point_reference_at(view, base)
    assert asked == []
    assert view.session.document.guides.references == []


def test_an_already_linked_file_asks_nothing(qapp, tmp_path):
    """The modules are already here; a second reference adds no rig."""
    base = _base(tmp_path)
    view = _view(tmp_path)
    view.session.link_modules(str(base))
    asked = []
    feedback.set_handler(lambda *args: asked.append(args) or "Link")
    _point_reference_at(view, base)
    assert asked == []
    assert len(view.session.document.guides.references) == 1


def test_an_unreadable_file_asks_nothing(qapp, tmp_path):
    view = _view(tmp_path)
    asked = []
    feedback.set_handler(lambda *args: asked.append(args) or "Link")
    _point_reference_at(view, tmp_path / "nope.tr")
    assert asked == []
