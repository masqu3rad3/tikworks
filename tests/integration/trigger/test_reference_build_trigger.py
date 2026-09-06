"""A host rig built from another session's modules plus its own.

The point of module referencing: the hero rig is "the base rig plus wings",
and the wing is a local module whose input names a referenced module's output.
"""

import pytest
from maya import cmds

from tik.trigger.session import Session


def _base_session(tmp_path):
    """A saved session holding one ``base`` module called ``body``."""
    cmds.file(new=True, force=True)
    base = Session()
    body = base.guides.add("base", side="C", name="body")
    base.save(tmp_path / "base.tr")
    return base, body


def _host_linking_base(tmp_path):
    """A fresh session that links the base rig's modules."""
    cmds.file(new=True, force=True)
    host = Session()
    host.save(tmp_path / "hero.tr")
    host.link_modules(str(tmp_path / "base.tr"))
    return host


def test_a_referenced_module_builds(tmp_path):
    _base_session(tmp_path)
    host = _host_linking_base(tmp_path)

    borrowed = host.document.guides.by_key("body")
    assert borrowed is not None and borrowed.origin is not None

    host.add("kinematics", modules=[borrowed.instance_id])
    host.build()
    assert cmds.objExists("rig_grp")
    assert cmds.ls("*body*", long=True)


def test_a_local_module_attaches_to_a_referenced_one(tmp_path):
    _base_session(tmp_path)
    host = _host_linking_base(tmp_path)
    borrowed = host.document.guides.by_key("body")

    wing = host.guides.add("arm", side="L", name="wing")
    host.guides.connect(f"{wing.key}.root", "body.root")

    host.add("kinematics", modules=[borrowed.instance_id, wing.instance_id])
    host.build()

    assert cmds.objExists("rig_grp")
    built = cmds.ls("*wing*", long=True) or []
    assert any("|rig_grp|trigger_grp|" in name for name in built), built
    drivers = []
    for name in cmds.ls("L_wing_*socket*", long=True, type="transform") or []:
        drivers.extend(cmds.listConnections(name, source=True, destination=False) or [])
    assert drivers, cmds.ls("*socket*")


def test_a_pose_override_moves_the_built_rig(tmp_path):
    """An override is a local edit that the referenced file never learns about."""
    _base_session(tmp_path)
    host = _host_linking_base(tmp_path)
    borrowed = host.document.guides.by_key("body")
    borrowed.guides[0].position = (0.0, 12.0, 0.0)

    host.add("kinematics", modules=[borrowed.instance_id], after_build="keep")
    host.build()

    guides = cmds.ls("*body*guide*", long=True, type="joint") or []
    assert guides
    placed = cmds.xform(guides[0], query=True, worldSpace=True, translation=True)
    assert placed[1] == pytest.approx(12.0, abs=1e-3)

    # the referenced session on disk is untouched
    upstream = Session.open(str(tmp_path / "base.tr"))
    assert upstream.document.guides.modules[0].guides[0].position != (0.0, 12.0, 0.0)


def test_the_override_survives_a_reopen(tmp_path):
    _base_session(tmp_path)
    host = _host_linking_base(tmp_path)
    borrowed = host.document.guides.by_key("body")
    instance_id = borrowed.instance_id
    borrowed.name = "torso"
    host.save()

    cmds.file(new=True, force=True)
    reopened = Session.open(str(tmp_path / "hero.tr"))
    assert reopened.document.guides.module(instance_id).name == "torso"
    assert reopened.document.guides.module(instance_id).source.name == "body"


def test_a_trg_export_writes_referenced_modules_as_plain_ones(tmp_path):
    """A copy format cannot hold a link, so it holds the modules themselves."""
    _base_session(tmp_path)
    host = _host_linking_base(tmp_path)
    host.guides.add("arm", side="L", name="wing")
    borrowed = host.document.guides.by_key("body")
    host.guides.draw(scope=[borrowed.instance_id])

    # records are per guide joint; both modules must contribute, the
    # referenced one indistinguishable from the local one
    names = [item["name"] for item in host.guides.export_guide_records()]
    assert any(name.startswith("C_body") for name in names), names
    assert any(name.startswith("L_wing") for name in names), names
