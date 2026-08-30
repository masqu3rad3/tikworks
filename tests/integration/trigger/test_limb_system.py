"""Integration tests for the IK/FK limb system."""

from maya import cmds

import tik.maya as tm
from tik.trigger.backends.maya import tags
from tik.trigger.systems.limb import build_ikfk_limb


def _limb(ctx, **kwargs):
    """A bent three-joint limb, so the RP solver has a plane to work in."""
    guides = tm.Joint.chain(
        [(0, 0, 0), (4, 0, -1), (8, 0, 0)], name_pattern="limb_guide_{index}"
    )
    binds = [
        ctx.bind_joint(f"bind{index}", match=guide) for index, guide in enumerate(guides)
    ]
    kwargs.setdefault("labels", ("upper", "lower", "end"))
    return build_ikfk_limb(ctx, guides, bind_joints=binds, name="limb", **kwargs), binds


def test_builds_exactly_two_puppet_chains(build_context):
    result, _binds = _limb(build_context())
    assert len(result.ik_joints) == 3
    assert len(result.fk_joints) == 3
    assert len(cmds.ls(type="ikHandle")) == 1


def test_switch_zero_follows_fk(build_context):
    result, binds = _limb(build_context())
    result.switch_plug.value = 0.0
    result.fk_controls[0].transform.rotate = (0, 0, 30)
    assert (
        binds[1].world_translation - result.fk_joints[1].world_translation
    ).length() < 1e-3


def test_switch_one_follows_ik(build_context):
    result, binds = _limb(build_context())
    result.switch_plug.value = 1.0
    assert (
        binds[2].world_translation - result.ik_joints[2].world_translation
    ).length() < 1e-3


def test_no_stretch_leaves_segment_lengths_at_rest(build_context):
    result, _binds = _limb(build_context(), stretch=False, squash=False)
    rest = result.ik_lengths.rest_plugs[0].value
    result.ik_control.transform.world_position = (40, 0, 0)
    assert abs(abs(result.ik_joints[1].translate.x) - rest) < 1e-3


def test_no_stretch_builds_no_stretch_attributes(build_context):
    result, _binds = _limb(build_context(), stretch=False, squash=False)
    control = result.ik_control.transform
    assert not control.has_attr("stretch")
    assert not control.has_attr("squash")
    assert not control.has_attr("stretchLimit")


def test_stretch_extends_beyond_reach(build_context):
    result, _binds = _limb(build_context(), stretch=True)
    result.ik_control.transform["stretch"].value = 1.0
    rest = result.ik_lengths.rest_plugs[0].value
    result.ik_control.transform.world_position = (40, 0, 0)
    assert abs(result.ik_joints[1].translate.x) > rest


def test_stretch_limit_caps_the_extension(build_context):
    result, _binds = _limb(build_context(), stretch=True)
    control = result.ik_control.transform
    control["stretch"].value = 1.0
    control["stretchLimit"].value = 10.0  # percent
    rest = result.ik_lengths.rest_plugs[0].value
    control.world_position = (200, 0, 0)
    assert abs(result.ik_joints[1].translate.x) <= rest * 1.1 + 1e-3


def test_squash_only_compresses(build_context):
    result, _binds = _limb(build_context(), squash=True)
    control = result.ik_control.transform
    rest = result.ik_lengths.rest_plugs[0].value
    control["squash"].value = 1.0
    control.world_position = (2, 0, 0)
    assert abs(result.ik_joints[1].translate.x) < rest


def test_squash_does_not_extend(build_context):
    """The compress factor is bounded above by 1.0."""
    result, _binds = _limb(build_context(), stretch=False, squash=True)
    control = result.ik_control.transform
    rest = result.ik_lengths.rest_plugs[0].value
    control["squash"].value = 1.0
    control.world_position = (40, 0, 0)
    assert abs(result.ik_joints[1].translate.x) <= rest + 1e-3


def test_segment_scale_works_without_stretch(build_context):
    """rest_i is a live plug, so per-segment scale needs no stretch network."""
    result, _binds = _limb(build_context(), stretch=False, squash=False)
    rest = result.ik_lengths.rest_plugs[0].value
    result.ik_control.transform["sUpper"].value = 2.0
    assert abs(abs(result.ik_joints[1].translate.x) - rest * 2.0) < 1e-3


def test_segment_scale_also_drives_the_fk_chain(build_context):
    """Both ChainLengths share rest plugs — the legacy was IK-only."""
    result, _binds = _limb(build_context(), stretch=False)
    rest = result.fk_lengths.rest_plugs[0].value
    result.ik_control.transform["sUpper"].value = 2.0
    assert abs(abs(result.fk_joints[1].translate.x) - rest * 2.0) < 1e-3


def test_pole_base_does_not_cycle(build_context):
    """The one failure a unit test would happily pass through."""
    _result, _binds = _limb(build_context())
    cmds.dgdirty(allPlugs=True)
    cycles = cmds.cycleCheck(all=True) or []
    assert not cycles, f"evaluation cycle: {cycles}"


def test_pole_follow_rolls_with_the_wrist(build_context):
    result, _binds = _limb(build_context())
    control = result.ik_control.transform
    control["poleFollow"].value = 1.0
    before = result.pole_control.transform.world_translation
    control.rotate = (90, 0, 0)
    after = result.pole_control.transform.world_translation
    assert (after - before).length() > 0.5


def test_pole_follow_zero_is_a_fixed_space(build_context):
    result, _binds = _limb(build_context())
    control = result.ik_control.transform
    control["poleFollow"].value = 0.0
    before = result.pole_control.transform.world_translation
    control.rotate = (90, 0, 0)
    after = result.pole_control.transform.world_translation
    assert (after - before).length() < 1e-3


def test_controls_carry_mirror_tags(build_context):
    result, _binds = _limb(build_context())
    assert result.fk_controls[0].transform.meta[tags.MIRROR] == tags.BEHAVIOUR
    assert result.ik_control.transform.meta[tags.MIRROR] == tags.WORLD
    assert result.pole_control.transform.meta[tags.MIRROR] == tags.WORLD


def test_right_side_uses_negative_translate_x(build_context):
    """Mirrored behaviour: the aim axis points back up the chain."""
    result, _binds = _limb(build_context("fkchain", side="R"))
    assert result.ik_joints[1].translate.x < 0
    assert result.fk_joints[1].translate.x < 0


def test_empty_name_adds_no_token(build_context):
    """The default limb name contributes no extra name token."""
    ctx = build_context()
    guides = tm.Joint.chain(
        [(0, 0, 0), (4, 0, -1), (8, 0, 0)], name_pattern="noname_guide_{index}"
    )
    result = build_ikfk_limb(ctx, guides, labels=("upper", "lower", "end"))
    assert result.ik_control.transform.name == "C_probe_ik_ctrl"
    assert result.pole_control.transform.name == "C_probe_pole_ctrl"


# ------------------------------------------------------------- lock and hide
def _locked(transform, attr):
    return cmds.getAttr(f"{transform.long_name}.{attr}", lock=True)


def test_ik_control_locks_scale_and_visibility(build_context):
    result, _binds = _limb(build_context())
    control = result.ik_control.transform
    for attr in ("sx", "sy", "sz", "v"):
        assert _locked(control, attr)
    for attr in ("tx", "ty", "tz", "rx", "ry", "rz"):
        assert not _locked(control, attr)


def test_fk_controls_lock_translate(build_context):
    result, _binds = _limb(build_context())
    for control in (item.transform for item in result.fk_controls):
        for attr in ("tx", "ty", "tz", "sx", "sy", "sz", "v"):
            assert _locked(control, attr), f"{control.name}.{attr} should be locked"


def test_middle_fk_control_keeps_only_the_hinge(build_context):
    result, _binds = _limb(build_context())
    assert result.hinge_axis == "y"  # elbow bends in the XZ plane
    middle = result.fk_controls[1].transform
    assert not _locked(middle, "ry")
    assert _locked(middle, "rx") and _locked(middle, "rz")


def test_root_and_end_fk_keep_every_rotation(build_context):
    result, _binds = _limb(build_context())
    for control in (result.fk_controls[0].transform, result.fk_controls[-1].transform):
        for attr in ("rx", "ry", "rz"):
            assert not _locked(control, attr)


def test_straight_chain_locks_no_rotation(build_context):
    """No bend plane means no derivable hinge; locking two axes would guess."""
    ctx = build_context()
    guides = tm.Joint.chain(
        [(0, 0, 0), (4, 0, 0), (8, 0, 0)], name_pattern="straight_{index}"
    )
    result = build_ikfk_limb(ctx, guides, labels=("upper", "lower", "end"))
    assert result.hinge_axis is None
    middle = result.fk_controls[1].transform
    for attr in ("rx", "ry", "rz"):
        assert not _locked(middle, attr)


# ------------------------------------------------------ switch and separators
def test_no_separate_switch_control(build_context):
    result, _binds = _limb(build_context())
    assert result.switch_control is None
    assert result.switch_plug.node.name.endswith("_ik_ctrl")


def test_every_fk_control_proxies_the_switch(build_context):
    result, _binds = _limb(build_context())
    for control in (item.transform for item in result.fk_controls):
        assert control.has_attr("ikFk")
    result.switch_plug.value = 0.0
    for control in (item.transform for item in result.fk_controls):
        assert abs(control["ikFk"].value) < 1e-6


def test_switch_is_reachable_from_fk_when_ik_is_hidden(build_context):
    """The reason removing the switch control is safe."""
    result, _binds = _limb(build_context())
    result.switch_plug.value = 0.0
    assert not result.ik_control.transform.parent.visibility
    # An animator in FK flips it back through the proxy.
    result.fk_controls[0].transform["ikFk"].value = 1.0
    assert result.ik_control.transform.parent.visibility


def test_ik_control_has_separators(build_context):
    result, _binds = _limb(build_context())
    control = result.ik_control.transform
    for separator in ("ikfk_", "stretch_", "segments_", "pole_"):
        assert control.has_attr(separator), f"missing separator {separator}"
