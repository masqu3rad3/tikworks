"""The pure guide document: records, entries, serialization, guide expansion."""

import pytest

from tik.trigger.core.guide_document import (
    SCHEMA_VERSION,
    GuideDocument,
    GuideRecord,
    ModuleEntry,
    SceneGroup,
    expand_guides,
)
from tik.trigger.core.manifest import GuideLayout


def test_record_pair_and_posed():
    unposed = GuideRecord(role="root")
    assert unposed.pair == ("root", 0)
    assert unposed.posed is False
    posed = GuideRecord(role="segment", index=2, position=(1.0, 2.0, 3.0))
    assert posed.pair == ("segment", 2)
    assert posed.posed is True


def test_record_radius_colour_orient_default_to_unauthored():
    """Concrete defaults would be indistinguishable from an authored value --
    same trap as pose, same fix: None means 'never authored'."""
    record = GuideRecord(role="root")
    assert record.radius is None
    assert record.color is None
    assert record.joint_orient is None


def test_record_radius_colour_orient_round_trip_through_dict():
    unauthored = GuideRecord(role="root")
    data = unauthored.to_dict()
    assert data["radius"] is None
    assert data["color"] is None
    assert data["joint_orient"] is None
    restored = GuideRecord.from_dict(data)
    assert restored.radius is None
    assert restored.color is None
    assert restored.joint_orient is None

    authored = GuideRecord(
        role="root", radius=2.5, color=6, joint_orient=(1.0, 2.0, 3.0)
    )
    data = authored.to_dict()
    assert data["radius"] == 2.5
    assert data["color"] == 6
    assert data["joint_orient"] == [1.0, 2.0, 3.0]
    restored = GuideRecord.from_dict(data)
    assert restored.radius == pytest.approx(2.5)
    assert restored.color == 6
    assert restored.joint_orient == (1.0, 2.0, 3.0)


def test_entry_key_follows_side():
    assert ModuleEntry("id1", "arm", "arm", "L").key == "L_arm"
    assert ModuleEntry("id2", "spine", "spine", "C").key == "spine"


def test_entry_guide_lookup():
    entry = ModuleEntry(
        "id1",
        "fkchain",
        "tail",
        "C",
        guides=[GuideRecord("root"), GuideRecord("segment", 1)],
    )
    assert entry.guide("segment", 1).index == 1
    assert entry.guide("segment", 9) is None
    assert entry.pairs == [("root", 0), ("segment", 1)]


def test_document_round_trip_preserves_everything():
    document = GuideDocument(
        modules=[
            ModuleEntry(
                "id1",
                "arm",
                "arm",
                "L",
                settings={"segments": 3},
                inputs={"root": "id2.hand"},
                guides=[
                    GuideRecord(
                        "root", position=(1.0, 0.0, 0.0), attrs={"twistWeight": 0.5}
                    )
                ],
            )
        ],
        scene_groups=[SceneGroup("g1", "sceneNodes1", ["some_jnt"])],
        positions={"id1": [10.0, 20.0]},
        collapse={"id1": 2},
    )
    restored = GuideDocument.from_dict(document.to_dict())
    assert restored.schema == SCHEMA_VERSION
    entry = restored.module("id1")
    assert entry.key == "L_arm"
    assert entry.settings == {"segments": 3}
    assert entry.inputs == {"root": "id2.hand"}
    assert entry.guide("root").position == (1.0, 0.0, 0.0)
    assert entry.guide("root").attrs == {"twistWeight": 0.5}
    assert restored.group("g1").nodes == ["some_jnt"]
    assert restored.positions == {"id1": [10.0, 20.0]}
    assert restored.collapse == {"id1": 2}


def test_document_by_key():
    document = GuideDocument(modules=[ModuleEntry("id1", "arm", "arm", "L")])
    assert document.by_key("L_arm").instance_id == "id1"
    assert document.by_key("nope") is None


def test_from_dict_rejects_newer_schema():
    with pytest.raises(ValueError, match="newer than supported"):
        GuideDocument.from_dict({"schema": SCHEMA_VERSION + 1})


def test_expand_guides_grows_keeping_existing_poses():
    layout = GuideLayout("root", multi="segment", min=1, max=50)
    entry = ModuleEntry(
        "id1",
        "fkchain",
        "tail",
        "C",
        guides=[
            GuideRecord("root", position=(0.0, 0.0, 0.0)),
            GuideRecord("segment", 0, position=(5.0, 0.0, 0.0)),
            GuideRecord("segment", 1, position=(10.0, 0.0, 0.0)),
        ],
    )
    expand_guides(entry, layout, 4)
    assert entry.pairs == [
        ("root", 0),
        ("segment", 0),
        ("segment", 1),
        ("segment", 2),
        ("segment", 3),
    ]
    assert entry.guide("segment", 0).position == (5.0, 0.0, 0.0)
    assert entry.guide("segment", 1).position == (10.0, 0.0, 0.0)
    assert entry.guide("segment", 2).posed is False
    assert entry.guide("segment", 3).posed is False


def test_expand_guides_shrinks():
    layout = GuideLayout("root", multi="segment", min=1, max=50)
    entry = ModuleEntry(
        "id1",
        "fkchain",
        "tail",
        "C",
        guides=[
            GuideRecord("root"),
            GuideRecord("segment", 0),
            GuideRecord("segment", 1),
        ],
    )
    expand_guides(entry, layout, 1)
    assert entry.pairs == [("root", 0), ("segment", 0)]


def test_expand_guides_keeps_fixed_roles():
    layout = GuideLayout("collar", "shoulder", "elbow", "hand")
    entry = ModuleEntry(
        "id1",
        "arm",
        "arm",
        "L",
        guides=[GuideRecord("collar", position=(1.0, 0.0, 0.0))],
    )
    expand_guides(entry, layout, 0)
    assert entry.pairs == [("collar", 0), ("shoulder", 0), ("elbow", 0), ("hand", 0)]
    assert entry.guide("collar").position == (1.0, 0.0, 0.0)


def test_expand_guides_appends_extra_roles_and_keeps_their_poses():
    entry = ModuleEntry(instance_id="one", module_type="toy", name="toy")
    layout = GuideLayout("root", "hand")
    expand_guides(entry, layout, 0, extra=("pivot_ik_tip", "pivot_ik_ball"))
    assert entry.pairs == [
        ("root", 0),
        ("hand", 0),
        ("pivot_ik_tip", 0),
        ("pivot_ik_ball", 0),
    ]

    entry.guide("pivot_ik_tip", 0).position = (1.0, 2.0, 3.0)
    # dropping the 'ball' row leaves 'tip' untouched
    expand_guides(entry, layout, 0, extra=("pivot_ik_tip",))
    assert entry.pairs == [("root", 0), ("hand", 0), ("pivot_ik_tip", 0)]
    assert entry.guide("pivot_ik_tip", 0).position == (1.0, 2.0, 3.0)

    # re-adding it restores the record, unposed, without disturbing 'tip'
    expand_guides(entry, layout, 0, extra=("pivot_ik_tip", "pivot_ik_ball"))
    assert entry.guide("pivot_ik_tip", 0).position == (1.0, 2.0, 3.0)
    assert entry.guide("pivot_ik_ball", 0).posed is False


def test_document_stores_module_groups_and_looks_them_up():
    from tik.trigger.core.module_group import ModuleGroup

    document = GuideDocument()
    document.modules = [
        ModuleEntry("a", "fkchain", "index", "L"),
        ModuleEntry("b", "fkchain", "middle", "L"),
    ]
    document.module_groups = [ModuleGroup("g1", "fingers", ["a", "b"])]
    assert document.module_group("g1").label == "fingers"
    assert document.module_group("nope") is None
    assert document.group_of("b").group_id == "g1"
    assert document.group_of("a").group_id == "g1"
    assert document.group_of("c") is None


def test_group_keys_join_node_ids_under_the_member_side():
    from tik.trigger.core.module_group import ModuleGroup

    document = GuideDocument()
    document.modules = [ModuleEntry("a", "fkchain", "index", "L")]
    document.module_groups = [ModuleGroup("g1", "fingers", ["a"])]
    assert document.node_ids()["L_fingers"] == "g1"


def test_document_round_trips_module_groups():
    from tik.trigger.core.module_group import ModuleGroup

    document = GuideDocument()
    document.modules = [ModuleEntry("a", "fkchain", "index", "L")]
    document.module_groups = [ModuleGroup("g1", "fingers", ["a"])]
    restored = GuideDocument.from_dict(document.to_dict())
    assert restored.module_groups == document.module_groups
    assert restored.schema == 3


def test_a_document_without_groups_loads_with_an_empty_list():
    """Old files predate the section; there is no migration."""
    restored = GuideDocument.from_dict({"schema": 2, "modules": []})
    assert restored.module_groups == []
