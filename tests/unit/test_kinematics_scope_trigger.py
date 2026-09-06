"""The kinematics action builds exactly the modules it names."""

import pytest

from tik.trigger.actions.kinematics.kinematics import Kinematics
from tik.trigger.core import clear_registries, register_module, registry
from tik.trigger.core.exceptions import ActionExecutionError
from tik.trigger.core.guide_document import GuideDocument, ModuleEntry
from tik.trigger.session import Session
from toy_modules import ToyChain, ToyRoot


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    registry.ensure_registered(Kinematics)
    yield
    clear_registries()


def _entry(instance_id, module_type="toy_root", name="thing", side="C"):
    return ModuleEntry(
        instance_id=instance_id, module_type=module_type, name=name, side=side
    )


def _session_with(*entries) -> Session:
    """A session whose guide document holds ``entries``."""
    session = Session()
    session.document.guides = GuideDocument(modules=list(entries))
    return session


def test_empty_modules_raises():
    """An empty list is an error, never 'build everything'."""
    session = _session_with(_entry("aaa"))
    handle = session.add("kinematics")
    with pytest.raises(ActionExecutionError, match="names no modules"):
        session.run(handle.path)


def test_unknown_uuid_is_a_validation_problem():
    session = _session_with(_entry("aaa"))
    session.add("kinematics", modules=["nope"])
    assert any("nope" in item for item in session.validate())


def test_modules_field_stores_uuids():
    session = _session_with(_entry("aaa"), _entry("bbb", name="other"))
    handle = session.add("kinematics", modules=["aaa", "bbb"])
    assert handle.modules == ["aaa", "bbb"]


def test_guides_file_and_guide_roots_are_gone():
    """The two implicit-scope settings no longer exist."""
    from tik.trigger.core import registry

    fields = registry.get_action("kinematics").fields()
    assert "guides_file" not in fields
    assert "guide_roots" not in fields
    assert "modules" in fields
