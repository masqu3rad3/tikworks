"""A session that links another session's modules: resolve, validate, unlink."""

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

    registry.ensure_registered(Kinematics)
    yield
    clear_registries()


def _entry(instance_id, name, module_type="toy_root", side="C"):
    entry = ModuleEntry(
        instance_id=instance_id, module_type=module_type, name=name, side=side
    )
    entry.guides = [GuideRecord(role="root", position=(0.0, 0.0, 0.0))]
    return entry


def _base_file(tmp_path, *entries):
    """A saved ``.tr`` holding ``entries`` and nothing else."""
    document = Document()
    document.guides = GuideDocument(modules=list(entries))
    path = tmp_path / "base.tr"
    document.save(path)
    return path


def _host_linking(tmp_path, base_path, *local):
    """A saved host session linking ``base_path``, reopened from disk."""
    host = Session()
    host.document.guides = GuideDocument(modules=list(local))
    host.file_path = tmp_path / "hero.tr"
    host.link_modules(str(base_path))
    host.document.save(host.file_path)
    return Session.open(str(tmp_path / "hero.tr"))


# ------------------------------------------------------------------ linking
def test_opening_a_session_resolves_its_references(tmp_path):
    base = _base_file(tmp_path, _entry("bbb", "arm"))
    host = _host_linking(tmp_path, base, _entry("aaa", "spine"))
    assert sorted(item.key for item in host.document.guides.modules) == ["arm", "spine"]
    assert host.document.guides.module("bbb").origin is not None
    assert host.document.guides.module("aaa").origin is None


def test_linking_the_same_file_twice_is_refused(tmp_path):
    base = _base_file(tmp_path, _entry("bbb", "arm"))
    host = Session()
    host.file_path = tmp_path / "hero.tr"
    host.link_modules(str(base))
    with pytest.raises(Exception, match="already linked"):
        host.link_modules(str(base))


def test_a_broken_link_does_not_stop_the_session_opening(tmp_path):
    base = _base_file(tmp_path, _entry("bbb", "arm"))
    _host_linking(tmp_path, base, _entry("aaa", "spine"))
    base.unlink()
    reopened = Session.open(str(tmp_path / "hero.tr"))
    assert [item.key for item in reopened.document.guides.modules] == ["spine"]
    assert any("base.tr" in item for item in reopened.validate())


# ------------------------------------------------------------- edit and undo
def test_an_override_survives_save_and_reopen(tmp_path):
    base = _base_file(tmp_path, _entry("bbb", "arm"))
    host = _host_linking(tmp_path, base)
    host.document.guides.module("bbb").guides[0].position = (1.0, 2.0, 3.0)
    host.document.save(host.file_path)

    reopened = Session.open(str(tmp_path / "hero.tr"))
    assert reopened.document.guides.module("bbb").guides[0].position == (1.0, 2.0, 3.0)
    # ... and the source still says what upstream says
    assert reopened.document.guides.module("bbb").source.guides[0].position == (
        0.0,
        0.0,
        0.0,
    )


def test_undo_and_redo_keep_referenced_modules_present(tmp_path):
    base = _base_file(tmp_path, _entry("bbb", "arm"))
    host = _host_linking(tmp_path, base)
    host.touch()
    host.document.guides.module("bbb").name = "wing"
    host.touch()
    assert host.undo()
    assert host.document.guides.module("bbb") is not None
    assert host.document.guides.module("bbb").name == "arm"
    assert host.redo()
    assert host.document.guides.module("bbb").name == "wing"


def test_upstream_changes_arrive_on_reopen(tmp_path):
    base = _base_file(tmp_path, _entry("bbb", "arm"))
    host = _host_linking(tmp_path, base)
    assert host.document.guides.module("bbb").name == "arm"

    upstream = Document.load(base)
    upstream.guides.modules[0].name = "forearm"
    upstream.save(base)

    reopened = Session.open(str(tmp_path / "hero.tr"))
    assert reopened.document.guides.module("bbb").name == "forearm"


# -------------------------------------------------------------- validation
def test_building_a_disabled_module_is_an_error(tmp_path):
    base = _base_file(tmp_path, _entry("bbb", "arm"))
    host = _host_linking(tmp_path, base)
    host.document.guides.module("bbb").enabled = False
    host.add("kinematics", modules=["bbb"])
    assert any("deliberately left out" in item for item in host.validate())


def test_a_disabled_module_raises_no_unbuilt_warning(tmp_path):
    base = _base_file(tmp_path, _entry("bbb", "arm"))
    host = _host_linking(tmp_path, base, _entry("aaa", "spine"))
    host.document.guides.module("bbb").enabled = False
    host.add("kinematics", modules=["aaa"])
    assert not any("arm is built by no" in item for item in host.validate())


# ---------------------------------------------------------------- unlinking
def test_unlinking_drops_the_referenced_modules(tmp_path):
    base = _base_file(tmp_path, _entry("bbb", "arm"))
    host = _host_linking(tmp_path, base, _entry("aaa", "spine"))
    ref_id = host.document.guides.references[0].ref_id
    host.unlink_modules(ref_id)
    assert [item.key for item in host.document.guides.modules] == ["spine"]
    assert host.document.guides.references == []


def test_unlinking_can_bake_the_modules_in_with_new_ids(tmp_path):
    """Baking must not keep upstream's uuids, or re-linking would collide."""
    base = _base_file(tmp_path, _entry("bbb", "arm"))
    host = _host_linking(tmp_path, base, _entry("aaa", "spine"))
    ref_id = host.document.guides.references[0].ref_id
    host.unlink_modules(ref_id, bake=True)

    keys = sorted(item.key for item in host.document.guides.modules)
    assert keys == ["arm", "spine"]
    assert host.document.guides.module("bbb") is None
    baked = next(item for item in host.document.guides.modules if item.key == "arm")
    assert baked.origin is None and baked.source is None
    assert host.document.guides.references == []


def test_baking_rewrites_inputs_that_named_the_old_id(tmp_path):
    arm = _entry("bbb", "arm")
    hand = _entry("ccc", "hand")
    hand.inputs = {"root": "bbb.root"}
    base = _base_file(tmp_path, arm, hand)
    host = _host_linking(tmp_path, base)
    ref_id = host.document.guides.references[0].ref_id
    host.unlink_modules(ref_id, bake=True)

    baked_arm = next(item for item in host.document.guides.modules if item.key == "arm")
    baked_hand = next(
        item for item in host.document.guides.modules if item.key == "hand"
    )
    assert baked_hand.inputs["root"] == f"{baked_arm.instance_id}.root"


# ---------------------------------------------------- structural refusals
def test_removing_a_referenced_module_is_refused(tmp_path):
    from tik.trigger.core.exceptions import GuideError

    base = _base_file(tmp_path, _entry("bbb", "arm"))
    host = _host_linking(tmp_path, base, _entry("aaa", "spine"))
    handle = host.guides.get("bbb")
    with pytest.raises(GuideError, match="cannot be deleted"):
        host.guides.remove(handle)
    assert host.document.guides.module("bbb") is not None


def test_clearing_keeps_referenced_modules(tmp_path):
    """Clear is a local act; it must not silently unlink a rig."""
    base = _base_file(tmp_path, _entry("bbb", "arm"))
    host = _host_linking(tmp_path, base, _entry("aaa", "spine"))
    host.guides.clear()
    assert [item.key for item in host.document.guides.modules] == ["arm"]
    assert host.document.guides.references


def test_snapshot_from_scene_is_refused_while_references_exist(tmp_path):
    from tik.trigger.core.exceptions import GuideError

    base = _base_file(tmp_path, _entry("bbb", "arm"))
    host = _host_linking(tmp_path, base)
    with pytest.raises(GuideError, match="Unlink the reference"):
        host.guides.snapshot_from_scene()
