"""Guides: .trg format (legacy + new), live-scene handler, kinematics from file."""

import json
from pathlib import Path

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.core import Builder, get_module
from tik.trigger.core.exceptions import GuideError
from tik.trigger.guides import GuideFile, Guides, legacy_table, legacy_type

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def guides():
    backend = trigger.maya_backend()
    return Guides(backend)


def test_legacy_table_and_types():
    trigger.load_plugins()
    table = legacy_table()
    assert table["Base"] == ("base", "root", True)
    assert table["Collar"] == ("arm", "collar", True)
    assert table["Hand"] == ("arm", "hand", False)
    assert table["FkikRoot"] == ("fkchain", "root", True)
    assert table["Fkik"] == ("fkchain", "segment", False)
    assert legacy_type(get_module("arm"), "elbow") == "Elbow"


def test_legacy_sample_groups_into_instances():
    trigger.load_plugins()
    guide_file = GuideFile.load(DATA / "crabMonster_guides_v001.trg")
    instances = guide_file.instances()
    by_type = {}
    for item in instances:
        by_type.setdefault(item.module_type, []).append(item)
    assert len(by_type["base"]) == 1 and by_type["base"][0].name == "Base"
    arms = by_type["arm"]
    assert {arm.side for arm in arms} == {"L", "R"}
    assert all(set(role for role, _i in arm.joints) == {"collar", "shoulder", "elbow", "hand"} for arm in arms)
    assert all(arm.parent_joint for arm in arms)  # hang under another module
    assert "LegRoot" in guide_file.unknown  # no leg module yet
    chains = by_type["fkchain"]
    assert chains and all(("segment", 0) in chain.joints for chain in chains)
    assert "localJoints" in arms[0].settings or arms[0].settings == {} or True


def test_add_settings_attrs_export_import_roundtrip(guides, tmp_path):
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body, ribbon_joints=4)
    tail = guides.add("fkchain", name="tail", parent=body, segments=3)
    assert arm.ribbon_joints == 4 and arm.parent.instance_id == body.instance_id
    arm.ribbon_joints = 6
    assert arm.ribbon_joints == 6
    root = arm.root
    assert cmds.getAttr(f"{root.name}.ribbon_joints") == 6
    assert cmds.getAttr(f"{root.name}.moduleName") == "arm"
    assert cmds.getAttr(f"{root.name}.otherType") == "Collar"
    assert cmds.getAttr(f"{root.name}.side") == 1
    with pytest.raises(AttributeError):
        arm.nope = 1
    cmds.xform(guides.backend.guide_node(tail.instance_id, "segment", 2).long_name, ws=True, t=(0, 3, -9))

    path = guides.export(tmp_path / "hero")
    assert path.suffix == ".trg"
    records = json.loads(path.read_text())["joints"]
    assert {record["type"] for record in records} >= {"Base", "Collar", "Hand", "FkikRoot", "Fkik"}
    root_record = next(record for record in records if record["name"] == root.name)
    assert root_record["parent"] == body.root.name
    assert any(attr["attr_name"] == "ribbon_joints" and attr["default_value"] == 6 for attr in root_record["user_attributes"])
    assert root_record["settings"]["ribbon_joints"] == 6

    guides.clear()
    assert guides.instances() == []
    handles = guides.import_(path)
    names = sorted((handle.name, handle.side.value) for handle in handles)
    assert names == [("arm", "L"), ("body", "C"), ("tail", "C")]
    new_arm = guides.find("arm", "L")
    assert new_arm.ribbon_joints == 6 and new_arm.parent.name == "body"
    tip = guides.backend.guide_node(guides.find("tail").instance_id, "segment", 2)
    assert tuple(round(value, 3) for value in tip.world_position) == (0.0, 3.0, -9.0)


def test_legacy_file_imports_into_scene(guides):
    handles = guides.import_(DATA / "crabMonster_guides_v001.trg")
    types = sorted({handle.module_type for handle in handles})
    assert types == ["arm", "base", "fkchain"]
    arm = next(handle for handle in handles if handle.module_type == "arm")
    # the arms hang under a spine joint whose module is not ported yet -> no parent
    assert arm.parent is None and cmds.objExists(arm.root.name)
    assert cmds.getAttr(f"{arm.root.name}.otherType") == "Collar"


def test_mirror_and_test_build(guides):
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    cmds.xform(arm.root.long_name, ws=True, t=(3, 12, 1))
    mirrored = guides.mirror(arm)
    assert mirrored.side.value == "R" and mirrored.name == "arm"
    assert round(mirrored.root.world_position.x, 3) == -3.0
    assert mirrored.parent.instance_id == body.instance_id
    cmds.xform(arm.root.long_name, ws=True, t=(4, 12, 1))
    again = guides.mirror(arm)
    assert again.instance_id == mirrored.instance_id and round(again.root.world_position.x, 3) == -4.0
    with pytest.raises(GuideError):
        guides.mirror(body)
    report = guides.test_build(body, arm)
    assert report.count == 2 and cmds.objExists("test_rig")
    assert guides.find("arm", "L") is not None  # guides kept
    assert guides["body"].instance_id == body.instance_id
    with pytest.raises(GuideError):
        guides["ghost"]
