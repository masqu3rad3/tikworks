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


def _legacy_document(roots, entries, guides_file=""):
    """A schema-6 ``.tr`` dict holding one kinematics action."""
    settings = {"guide_roots": list(roots), "after_build": "delete"}
    if guides_file:
        settings["guides_file"] = guides_file
    return {
        "schema": 6,
        "meta": {},
        "actions": [
            {
                "name": "kinematics",
                "type": "kinematics",
                "enabled": True,
                "settings": settings,
                "children": [],
            }
        ],
        "publish": [],
        "guides": {"schema": 1, "modules": [entry.to_dict() for entry in entries]},
    }


def test_empty_roots_migrates_to_every_module():
    """The old 'empty means all' keeps building the same rig."""
    from tik.trigger.core.document import Document

    entries = [_entry("aaa", name="spine"), _entry("bbb", name="arm", side="L")]
    document = Document.from_dict(_legacy_document([], entries))
    assert document.actions[0].settings["modules"] == ["aaa", "bbb"]
    assert "guide_roots" not in document.actions[0].settings


def test_named_root_matches_every_side():
    """'arm' selected L_arm and R_arm alike, and still does."""
    from tik.trigger.core.document import Document

    entries = [
        _entry("aaa", name="spine"),
        _entry("bbb", name="arm", side="L"),
        _entry("ccc", name="arm", side="R"),
    ]
    document = Document.from_dict(_legacy_document(["arm"], entries))
    assert sorted(document.actions[0].settings["modules"]) == ["bbb", "ccc"]


def test_named_root_pulls_its_subtree():
    """The old semantics included everything parented under the root."""
    from tik.trigger.core.document import Document

    spine = _entry("aaa", name="spine")
    arm = _entry("bbb", "toy_chain", name="arm", side="L")
    arm.inputs = {"root": "aaa.root"}
    document = Document.from_dict(_legacy_document(["spine"], [spine, arm]))
    assert sorted(document.actions[0].settings["modules"]) == ["aaa", "bbb"]


def test_unresolvable_root_is_kept_not_dropped():
    """A root joint name cannot be resolved headlessly; it must not vanish."""
    from tik.trigger.core.document import Document

    document = Document.from_dict(_legacy_document(["base_c"], []))
    settings = document.actions[0].settings
    assert settings["modules"] == []
    assert settings["legacy_roots"] == ["base_c"]


def test_migration_does_not_rerun_on_current_schema():
    """undo/redo/copy round-trip through from_dict and must not re-migrate."""
    from tik.trigger.core.document import Document

    entries = [_entry("aaa", name="spine")]
    document = Document.from_dict(_legacy_document([], entries))
    again = Document.from_dict(document.to_dict())
    assert again.actions[0].settings["modules"] == ["aaa"]
    assert "legacy_roots" not in again.actions[0].settings
