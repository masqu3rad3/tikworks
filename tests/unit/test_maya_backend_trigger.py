"""Maya backend tests: guides as tagged joints, contexts, build pipeline."""

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.backends.maya import MayaBackend, tags
from tik.trigger.core import Builder, ParentRef, get_module


@pytest.fixture
def backend():
    trigger.load_plugins()
    return MayaBackend()


def test_create_guides_tags_and_parents(backend):
    base = get_module("base")(name="body")
    instance = backend.create_guides(base)
    joint = backend.guide_node(instance.instance_id, "root")
    assert joint.type == "joint"
    assert joint.meta[tags.KIND] == "guide"
    assert joint.meta[tags.MODULE] == "base"
    assert joint.meta[tags.NAME] == "body"
    assert joint.meta[tags.SETTINGS] == {"controller_size": 10.0}
    assert joint.parent.name == tags.GUIDE_HOLDER
    assert instance.guide_pairs == [("root", 0)]


def test_chain_guides_follow_settings_and_side(backend):
    chain = get_module("fkchain")(name="tail", side="R", settings={"segments": 4})
    instance = backend.create_guides(chain)
    assert len(instance.guides) == 5
    last = backend.guide_node(instance.instance_id, "segment", 3)
    assert last.world_position.x < 0  # right side mirrors along -X
    assert last.parent.meta[tags.ROLE] == "segment"
    assert instance.side == "R" and instance.settings["segments"] == 4


def test_find_instances_reads_hierarchy_and_poses(backend):
    root = backend.create_guides(get_module("base")(name="body"))
    child = backend.create_guides(
        get_module("fkchain")(name="tail", settings={"segments": 2}),
        parent=ParentRef(root.instance_id, "root"),
    )
    cmds.xform(backend.guide_node(child.instance_id, "segment", 1).long_name, ws=True, t=(0, 9, 0))
    found = {item.name: item for item in backend.find_instances()}
    assert set(found) == {"body", "tail"}
    assert found["tail"].parent == ParentRef(root.instance_id, "root", 0)
    poses = {(pose.role, pose.index): pose.position for pose in found["tail"].guides}
    assert poses[("segment", 1)][1] == pytest.approx(9.0)
    assert backend.guide_node(child.instance_id, "root").parent.name == backend.guide_node(root.instance_id, "root").name


def test_find_instances_scopes(backend):
    root = backend.create_guides(get_module("base")(name="body"))
    other = backend.create_guides(get_module("fkchain")(name="tail"))
    assert [item.name for item in backend.find_instances([other.instance_id])] == ["tail"]
    cmds.select(backend.guide_node(other.instance_id, "segment", 1).long_name)
    assert [item.name for item in backend.find_instances("selection")] == ["tail"]


def test_settings_roundtrip_and_delete_keeps_children(backend):
    root = backend.create_guides(get_module("base")(name="body"))
    child = backend.create_guides(get_module("fkchain")(name="tail"), parent=ParentRef(root.instance_id, "root"))
    backend.write_settings(root.instance_id, {"controller_size": 3.0})
    assert backend.read_settings(root.instance_id) == {"controller_size": 3.0}
    backend.delete_guides(root.instance_id)
    assert backend.find_instances([root.instance_id]) == []
    remaining = backend.find_instances()
    assert [item.name for item in remaining] == ["tail"]
    assert remaining[0].parent is None
    assert backend.guide_node(child.instance_id, "root").parent.name == tags.GUIDE_HOLDER


def test_duplicate_instance_rejected(backend):
    module = get_module("base")(name="body")
    backend.create_guides(module)
    with pytest.raises(trigger.TriggerError):
        backend.create_guides(module)


def test_build_pipeline_creates_groups_controllers_and_attaches(backend):
    root = backend.create_guides(get_module("base")(name="body"))
    chain = get_module("fkchain")(name="tail", side="L", settings={"segments": 2})
    child = backend.create_guides(chain, parent=ParentRef(root.instance_id, "root"))
    cmds.xform(backend.guide_node(root.instance_id, "root").long_name, ws=True, t=(0, 10, 0))
    cmds.xform(backend.guide_node(child.instance_id, "root").long_name, ws=True, t=(2, 10, 0))

    report = Builder(backend).build(rig_name="hero", afterlife="delete")
    assert report.count == 2
    assert cmds.objExists("hero_rig")
    assert cmds.objExists("C_body_grp") and cmds.objExists("L_tail_grp")
    assert cmds.objExists("L_tail_control_grp")
    assert cmds.objExists("L_tail_0_jnt") and cmds.objExists("L_tail_2_jnt")
    assert cmds.objExists("L_tail_fk0_ctrl") and not cmds.objExists("L_tail_fk2_ctrl")
    assert not cmds.objExists(tags.GUIDE_HOLDER)

    # attachment: moving the body controller moves the tail socket
    body_ctrl = tm.Transform("C_body_root_ctrl")
    socket = tm.Transform("L_tail_root_socket")
    before = socket.world_position
    body_ctrl.translate = (0, 15, 0)
    assert socket.world_position.y == pytest.approx(before.y + 5)

    # tags on outputs
    assert tm.Joint("L_tail_0_jnt").meta[tags.KIND] == tags.OUTPUT
    assert socket.meta[tags.KIND] == tags.INPUT
    assert report.connections == [("L_tail.root", "body.root")]
    assert tm.Transform("L_tail_grp").meta[tags.INSTANCE] == child.instance_id
    assert tm.Transform("C_body_root_ctrl").meta[tags.KIND] == tags.CONTROLLER


def test_build_afterlife_keep_and_hide(backend):
    backend.create_guides(get_module("base")(name="body"))
    Builder(backend).build(rig_name="a", afterlife="keep")
    assert cmds.getAttr(f"{tags.GUIDE_HOLDER}.v")
    Builder(backend).build(rig_name="b", afterlife="hide")
    assert not cmds.getAttr(f"{tags.GUIDE_HOLDER}.v")
    assert cmds.objExists("a_rig") and cmds.objExists("b_rig")


def test_build_is_undoable(backend):
    backend.create_guides(get_module("base")(name="body"))
    Builder(backend).build(afterlife="keep")
    assert cmds.objExists("C_body_grp")
    cmds.undo()
    assert not cmds.objExists("C_body_grp")


def test_visibility_attributes(backend):
    backend.create_guides(get_module("base")(name="body"))
    Builder(backend).build(afterlife="keep")
    limb = tm.Transform("C_body_grp")
    limb["controlVisibility"].value = False
    assert not tm.Transform("C_body_control_grp").visibility
    assert not tm.Transform("C_body_rig_grp").visibility


# --------------------------------------------------------------- ground rules


def _built(backend, module_type="base", name="body", settings=None):
    """Build one instance and return its build context."""
    module = get_module(module_type)(name=name, settings=settings or {})
    instance = backend.create_guides(module)
    report = Builder(backend).build(rig_name="rules", afterlife="keep")
    return report.contexts[instance.instance_id]


def test_module_has_exactly_four_groups(backend):
    ctx = _built(backend)
    children = {
        path.split("|")[-1]
        for path in cmds.listRelatives(ctx.groups.limb.long_name, children=True, fullPath=True) or []
    }
    assert len(children) == 4
    assert ctx.groups.socket.name in children
    assert ctx.groups.control.name in children
    assert ctx.groups.rig.name in children
    assert ctx.groups.bind.name in children


def test_group_names_follow_the_convention(backend):
    ctx = _built(backend)
    assert ctx.groups.socket.name.endswith("_socket_grp")
    assert ctx.groups.control.name.endswith("_control_grp")
    assert ctx.groups.rig.name.endswith("_rig_grp")
    assert ctx.groups.bind.name.endswith("_bind_grp")


def test_old_scale_groups_are_gone(backend):
    ctx = _built(backend)
    for dropped in ("scale", "nonscale", "joints", "controllers"):
        assert not hasattr(ctx.groups, dropped)
    assert not cmds.objExists("C_body_scale_grp")
    assert not cmds.objExists("C_body_nonScale_grp")
    assert not cmds.objExists("C_body_joints_grp")


def test_visibility_attributes_drive_the_new_groups(backend):
    ctx = _built(backend)
    limb = ctx.groups.limb
    limb["controlVisibility"].value = False
    assert not ctx.groups.control.visibility
    limb["rigVisibility"].value = True
    assert ctx.groups.rig.visibility
    limb["bindVisibility"].value = False
    assert not ctx.groups.bind.visibility
