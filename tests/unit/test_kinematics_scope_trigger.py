"""The kinematics action builds exactly the modules it names."""

import pytest
from toy_modules import ToyChain, ToyRoot

from tik.trigger.actions.kinematics.kinematics import Kinematics
from tik.trigger.core import clear_registries, register_module, registry
from tik.trigger.core.exceptions import ActionExecutionError
from tik.trigger.core.guide_document import GuideDocument, ModuleEntry
from tik.trigger.session import Session


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
    reported = [item for item in session.validate() if "nope" in item]
    assert reported
    # the common cause is a pipeline reference whose modules were never
    # linked, so the message has to name the remedy, not just the absence
    assert "Reference Modules" in reported[0]


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


# ------------------------------------------------------- cross-action checks
def _scoped(entries, scopes) -> Session:
    """A session with ``entries`` and one kinematics action per scope list."""
    session = _session_with(*entries)
    for index, scope in enumerate(scopes):
        session.add("kinematics", name=f"pass{index}", modules=list(scope))
    return session


def test_double_build_is_an_error():
    session = _scoped([_entry("aaa", name="spine")], [["aaa"], ["aaa"]])
    assert any("more than one" in item for item in session.validate())


def test_module_in_no_pass_is_a_warning():
    entries = [_entry("aaa", name="spine"), _entry("bbb", name="wing")]
    session = _scoped(entries, [["aaa"]])
    reported = [item for item in session.validate() if "wing" in item]
    assert reported and all(item.startswith("warning:") for item in reported)
    assert any("built by no kinematics action" in item for item in reported)


def test_source_built_in_a_later_pass_is_an_error():
    spine = _entry("aaa", name="spine")
    wing = _entry("bbb", "toy_chain", name="wing")
    wing.inputs = {"root": "aaa.root"}
    session = _scoped([spine, wing], [["bbb"], ["aaa"]])
    assert any("later kinematics action" in item for item in session.validate())


def test_source_in_no_pass_is_an_error():
    spine = _entry("aaa", name="spine")
    wing = _entry("bbb", "toy_chain", name="wing")
    wing.inputs = {"root": "aaa.root"}
    session = _scoped([spine, wing], [["bbb"]])
    assert any("no kinematics action builds" in item for item in session.validate())


def test_key_collision_among_built_modules_is_an_error():
    entries = [_entry("aaa", name="spine"), _entry("bbb", name="spine")]
    session = _scoped(entries, [["aaa", "bbb"]])
    assert any("display key" in item for item in session.validate())


def test_a_collision_outside_the_build_is_not_reported():
    """Only modules that actually build can collide in the rig."""
    entries = [_entry("aaa", name="spine"), _entry("bbb", name="spine")]
    session = _scoped(entries, [["aaa"]])
    assert not any("display key" in item for item in session.validate())


def test_legacy_roots_are_reported():
    session = _scoped([_entry("aaa", name="spine")], [["aaa"]])
    session.document.actions[0].settings["legacy_roots"] = ["base_c"]
    assert any("could not be migrated" in item for item in session.validate())


def test_build_runs_the_cross_action_checks():
    """Nothing calls validate() before a build, so build must check itself."""
    from tik.trigger.core.exceptions import SessionError

    session = _scoped([_entry("aaa", name="spine")], [["aaa"], ["aaa"]])
    with pytest.raises(SessionError, match="more than one"):
        session.build()


def test_a_warning_alone_does_not_block_a_build():
    """An unbuilt module is worth saying, not worth refusing to build over."""
    entries = [_entry("aaa", name="spine"), _entry("bbb", name="wing")]
    session = _scoped(entries, [["aaa"]])
    assert any("warning:" in item for item in session.validate())
    session._scope_problems()  # must not raise


def test_no_pipeline_yet_means_no_unbuilt_warnings():
    """A session still being authored has no kinematics action to be absent from."""
    session = _session_with(_entry("aaa", name="spine"), _entry("bbb", name="wing"))
    assert not any("no kinematics action" in item for item in session.validate())


def test_a_legacy_guides_file_is_reported():
    """Its modules were never in the session, so the scope migrated to nothing."""
    from tik.trigger.core.document import Document

    data = _legacy_document([], [], guides_file="guides/hero.trg")
    session = Session()
    session.document = Document.from_dict(data)
    reported = [item for item in session.validate() if "hero.trg" in item]
    assert reported and "import the .trg" in reported[0]
