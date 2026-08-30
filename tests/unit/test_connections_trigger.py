"""Explicit module inputs/outputs: connections in .trg, scene sources, mirror, pre-fill (Maya)."""

import json

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.core import Builder, ParentRef, get_module
from tik.trigger.core.exceptions import AttachError, GuideError
from tik.trigger.guides import GuideFile, Guides


@pytest.fixture
def guides():
    return Guides(trigger.maya_backend())


def test_manifest_inputs_outputs():
    trigger.load_plugins()
    arm = get_module("arm")
    assert arm.input_names() == ["root"] and arm.primary_input().name == "root"
    assert arm.outputs == ("collar", "upperarm", "lowerarm", "hand")
    assert arm.output_at_role("hand") == "hand" and arm.output_at_role("nope") == "collar"
    base = get_module("base")
    assert base.inputs == () and base.outputs == ("root",)


def test_prefill_connect_disconnect_and_keys(guides):
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    assert arm.key == "L_arm" and body.key == "body"
    assert arm.inputs == {"root": "body.root"}  # pre-filled from the parent guide
    guides.connect("L_arm.root", "some_jnt")
    assert arm.inputs == {"root": "some_jnt"}
    with pytest.raises(GuideError):
        guides.connect("L_arm.root", "body.nope")
    with pytest.raises(GuideError):
        guides.connect("L_arm.ghost", "body.root")
    guides.disconnect("L_arm.root")
    assert arm.inputs == {}
    assert guides.connections() == []
    guides.connect("L_arm.root", "body.root")
    assert guides.connections() == [{"input": "L_arm.root", "source": "body.root"}]


def test_build_connects_to_scene_node_and_errors(guides):
    body = guides.add("base", name="body")
    tail = guides.add("fkchain", name="tail", parent=body, segments=2)
    guides.connect("tail.root", "anchor_jnt")
    with pytest.raises(AttachError) as info:
        Builder(guides.backend).build(rig_name="a", afterlife="keep")
    assert "anchor_jnt" in str(info.value)
    anchor = tm.Joint.create(name="anchor_jnt")
    anchor.translate = (0, 20, 0)
    report = Builder(guides.backend).build(rig_name="a", afterlife="keep")
    assert report.connections == [("tail.root", "anchor_jnt")]
    socket = tm.Transform("C_tail_root_socket")
    before = socket.world_position
    anchor.translate = (0, 25, 0)
    assert socket.world_position.y == pytest.approx(before.y + 5)


def test_export_import_keeps_connections_and_mirror_maps_sides(guides, tmp_path):
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    guides.connect("L_arm.root", "chest_jnt")
    mirrored = guides.mirror(arm)
    assert mirrored.inputs == {"root": "chest_jnt"}
    guides.connect("L_arm.root", "body.root")
    mirrored = guides.mirror(arm)
    assert mirrored.inputs == {"root": "body.root"}
    tail = guides.add("fkchain", name="tail", parent=arm)
    assert tail.inputs == {"root": "L_arm.collar"}
    guides.connect("tail.root", "L_arm.hand")
    path = guides.export(tmp_path / "hero")
    data = json.loads(path.read_text())
    assert isinstance(data, dict) and {"input": "tail.root", "source": "L_arm.hand"} in data["connections"]
    guides.clear()
    handles = guides.import_(path)
    tail = guides.by_key("tail")
    assert tail.inputs == {"root": "L_arm.hand"}
    assert guides.by_key("R_arm").inputs == {"root": "body.root"}
    report = Builder(guides.backend).build(rig_name="hero", afterlife="keep")
    assert ("tail.root", "L_arm.hand") in report.connections
    # exporting a subset keeps only its connections
    subset = guides.export(tmp_path / "subset", guides.by_key("tail"))
    subset_data = json.loads(subset.read_text())
    assert [item["input"] for item in subset_data["connections"]] == ["tail.root"]


def test_fkchain_exposes_every_segment_as_output():
    from tik.trigger.modules.fkchain.fkchain import FkChain

    assert FkChain.output_names({"segments": 2}) == ("root", "segment1", "segment2", "end")
    assert FkChain.output_names() == ("root", "segment1", "segment2", "segment3", "end")
