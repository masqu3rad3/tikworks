"""The rig scaffold: one fixed structure per scene, ensured and healed."""

import pytest
from maya import cmds

import tik.maya as tm
from tik.maya.roles.controller import Controller
from tik.trigger.core import EventBus
from tik.trigger.maya import scaffold, tags


@pytest.fixture(autouse=True)
def _fresh_scene():
    cmds.file(new=True, force=True)


PREFERENCE_DEFAULTS = {
    "cacheMode": 0,
    "controls": 1,
    "rig": 0,
    "rigDisplay": 0,
    "joints": 1,
    "jointsDisplay": 0,
    "geo": 1,
    "geoDisplay": 0,
}


def test_fresh_scene_gets_the_whole_scaffold():
    rig = scaffold.ensure_rig()
    assert rig.root.long_name == "|rig_grp"
    assert rig.trigger.long_name == "|rig_grp|trigger_grp"
    assert rig.geo.long_name == "|rig_grp|geo_grp"
    assert (
        rig.preferences.transform.long_name == "|rig_grp|trigger_grp|preferences_ctrl"
    )
    assert (
        rig.visibilities.transform.long_name == "|rig_grp|trigger_grp|visibilities_ctrl"
    )
    assert rig.root.meta[tags.KIND] == tags.RIG_ROOT
    assert rig.trigger.meta[tags.KIND] == tags.RIG_TRIGGER
    assert rig.geo.meta[tags.KIND] == tags.RIG_GEO
    assert rig.preferences.transform.meta[tags.KIND] == tags.PREFERENCES
    assert rig.visibilities.transform.meta[tags.KIND] == tags.VISIBILITIES
    assert Controller.is_controller(rig.preferences.transform)
    assert Controller.is_controller(rig.visibilities.transform)
    assert rig.preferences.shapes and rig.visibilities.shapes


def test_preference_attributes_exist_with_defaults():
    rig = scaffold.ensure_rig()
    node = rig.preferences.transform
    for name, default in PREFERENCE_DEFAULTS.items():
        plug = node[name]
        assert plug.exists(), name
        assert plug.value == default, name
        assert not plug.keyable, name
        assert plug.visible, name
    assert cmds.attributeQuery("rigDisplay", node=node.long_name, listEnum=True) == [
        "normal:template:reference"
    ]


def test_second_call_creates_nothing_and_keeps_values():
    first = scaffold.ensure_rig()
    first.preferences.transform["rig"].value = True
    first.preferences.transform["geoDisplay"].value = 2
    before = set(cmds.ls(long=True))
    second = scaffold.ensure_rig()
    assert set(cmds.ls(long=True)) == before
    assert second.root.long_name == first.root.long_name
    assert second.preferences.transform["rig"].value is True
    assert second.preferences.transform["geoDisplay"].value == 2


def test_untagged_rig_grp_is_adopted_with_a_warning():
    tm.Transform.create(name="rig_grp")
    logged = []
    events = EventBus()
    events.subscribe(
        "log", lambda level="", message="", **_kw: logged.append((level, message))
    )
    rig = scaffold.ensure_rig(events)
    assert rig.root.long_name == "|rig_grp"
    assert len(cmds.ls("rig_grp")) == 1
    assert rig.root.meta[tags.KIND] == tags.RIG_ROOT
    assert any(level == "warning" and "rig_grp" in message for level, message in logged)


def test_missing_pieces_are_healed():
    rig = scaffold.ensure_rig()
    rig.geo.delete()
    rig.preferences.transform["joints"].delete()
    healed = scaffold.ensure_rig()
    assert healed.geo.long_name == "|rig_grp|geo_grp"
    assert healed.preferences.transform["joints"].value == 1


def test_group_channels_are_locked_and_hidden():
    rig = scaffold.ensure_rig()
    for group in (rig.root, rig.trigger, rig.geo):
        for channel in tm.TRANSFORM_CHANNELS:
            assert group[channel].locked, f"{group.name}.{channel}"
            assert not group[channel].visible, f"{group.name}.{channel}"


def test_geometry_preferences_drive_geo_grp():
    rig = scaffold.ensure_rig()
    prefs = rig.preferences.transform
    assert rig.geo.visibility
    prefs["geo"].value = False
    assert not rig.geo.visibility
    assert rig.geo["overrideEnabled"].value
    prefs["geoDisplay"].value = 2
    assert rig.geo["overrideDisplayType"].value == 2
