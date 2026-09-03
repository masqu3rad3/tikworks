"""Document tree, old-format conversion, versioning (no Maya)."""

import json
from pathlib import Path

import pytest

from tik.trigger.core import versioning
from tik.trigger.core.document import SCHEMA_VERSION, ActionNode, Document
from tik.trigger.core.exceptions import SessionError, SessionLoadError

DATA = Path(__file__).resolve().parents[1] / "data"


def _doc():
    doc = Document()
    doc.add(ActionNode("import_model", "import_asset", settings={"file": "a.ma"}))
    doc.add(ActionNode("rename", "script"), parent="import_model")
    doc.add(ActionNode("kinematics", "kinematics"))
    doc.add(ActionNode("cleanup", "cleanup"))
    return doc


def test_walk_paths_find_parent():
    doc = _doc()
    assert doc.paths() == [
        "import_model",
        "import_model/rename",
        "kinematics",
        "cleanup",
    ]
    assert doc.find("import_model/rename").type == "script"
    assert doc.find("nope") is None
    assert doc.parent_of("import_model/rename").name == "import_model"
    assert doc.parent_of("kinematics") is None
    with pytest.raises(SessionError):
        doc.require("ghost")


def test_add_unique_names_and_index():
    doc = _doc()
    assert doc.add(ActionNode("kinematics", "kinematics")) == "kinematics1"
    assert doc.add(ActionNode("kinematics1", "kinematics")) == "kinematics2"
    assert doc.add(ActionNode("first", "script"), index=0) == "first"
    assert doc.paths()[0] == "first"
    assert (
        doc.add(ActionNode("rename", "script"), parent="import_model")
        == "import_model/rename1"
    )


def test_move_rename_remove_duplicate():
    doc = _doc()
    assert doc.move("cleanup", index=0) == "cleanup"
    assert doc.paths()[0] == "cleanup"
    assert doc.move("cleanup", parent="kinematics") == "kinematics/cleanup"
    assert doc.find("kinematics/cleanup") is not None
    with pytest.raises(SessionError):
        doc.move("kinematics", parent="kinematics/cleanup")
    assert doc.rename("kinematics", "kin") == "kin"
    assert doc.find("kin/cleanup") is not None
    with pytest.raises(SessionError):
        doc.rename("kin", "import_model")
    with pytest.raises(SessionError):
        doc.rename("kin", "a/b")
    assert doc.duplicate("kin") == "kin1"
    assert doc.find("kin1/cleanup") is not None
    doc.remove("kin1")
    assert doc.find("kin1") is None
    # move within same parent past its own position
    doc.add(ActionNode("last", "script"))
    doc.move("import_model", index=len(doc.actions))
    assert (
        doc.paths()[-1].startswith("import_model") or "import_model" in doc.paths()[-2]
    )


def test_roundtrip_and_schema_guard(tmp_path):
    doc = _doc()
    path = doc.save(tmp_path / "s.tr")
    loaded = Document.load(path)
    assert loaded.to_dict() == doc.to_dict()
    assert loaded.schema == SCHEMA_VERSION
    with pytest.raises(SessionLoadError):
        Document.from_dict({"schema": 99})
    with pytest.raises(SessionLoadError):
        Document.load(tmp_path / "missing.tr")


def test_old_flat_session_converts():
    doc = Document.load(DATA / "crabMonster_main_session_v002.tr")
    assert [node.type for node in doc.actions][:3] == [
        "master",
        "import_asset",
        "kinematics",
    ]
    kin = doc.find("kinematics1")
    assert kin.settings["guide_roots"] == ["base_c"]
    assert kin.children == [] and kin.enabled is True
    assert Document.from_dict(
        [{"name": "a", "type": "script", "data": {"x": 1}}]
    ).actions[0].settings == {"x": 1}


def test_versioning(tmp_path):
    assert versioning.parse("hero_v012.tr") == ("hero", 12, ".tr")
    assert versioning.parse("hero.tr") == ("hero", None, ".tr")
    assert versioning.with_version("x/hero.tr", 3).name == "hero_v003.tr"
    for number in (1, 2, 5):
        (tmp_path / f"hero_v{number:03d}.tr").write_text("{}")
    (tmp_path / "hero_v002.trg").write_text("{}")
    assert versioning.latest_version(tmp_path / "hero.tr").name == "hero_v005.tr"
    assert versioning.next_version(tmp_path / "hero.tr").name == "hero_v006.tr"
    assert versioning.next_version(tmp_path / "other.tr").name == "other_v001.tr"
    assert (
        versioning.resolve(tmp_path / "hero_v001.tr", "latest").name == "hero_v005.tr"
    )
    assert versioning.resolve(tmp_path / "hero_v001.tr", "v002").name == "hero_v002.tr"
    assert (
        versioning.resolve(tmp_path / "hero_v001.tr", "pinned").name == "hero_v001.tr"
    )
    assert [item.name for item in versioning.versions(tmp_path / "hero.tr")] == [
        "hero_v001.tr",
        "hero_v002.tr",
        "hero_v005.tr",
    ]


def test_document_guides_is_a_live_guide_document():
    from tik.trigger.core.document import Document
    from tik.trigger.core.guide_document import GuideDocument, ModuleEntry

    document = Document()
    assert isinstance(document.guides, GuideDocument)
    document.guides.modules.append(ModuleEntry("id1", "fkchain", "tail", "C"))
    assert document.to_dict()["guides"]["modules"][0]["name"] == "tail"


def test_document_guides_round_trip(tmp_path):
    from tik.trigger.core.document import SCHEMA_VERSION, Document
    from tik.trigger.core.guide_document import GuideRecord, ModuleEntry

    document = Document()
    document.guides.modules.append(
        ModuleEntry(
            "id1",
            "fkchain",
            "tail",
            "C",
            settings={"segments": 3},
            guides=[GuideRecord("root", position=(1.0, 2.0, 3.0))],
        )
    )
    restored = Document.load(document.save(tmp_path / "hero.tr"))
    assert restored.schema == SCHEMA_VERSION
    assert restored.guides.module("id1").guide("root").position == (1.0, 2.0, 3.0)


def test_editing_guides_shows_up_in_the_documents_state():
    """This is what gives guide work the session's dirty flag and its undo."""
    from tik.trigger.core.document import Document
    from tik.trigger.core.guide_document import ModuleEntry

    document = Document()
    before = document.to_dict()
    document.guides.modules.append(ModuleEntry("id1", "fkchain", "tail", "C"))
    assert document.to_dict() != before


# --------------------------------------------------------------- phases
from tik.trigger.core.document import BUILD, PHASES, PUBLISH


def _mixed():
    doc = Document()
    doc.add(ActionNode("import_model", "import_asset"))
    doc.add(ActionNode("kinematics", "kinematics"))
    doc.add(ActionNode("export_fbx", "script"), phase=PUBLISH)
    doc.add(ActionNode("export_maya", "script"), phase=PUBLISH)
    return doc


def test_phase_constants():
    assert (BUILD, PUBLISH) == ("build", "publish")
    assert PHASES == (BUILD, PUBLISH)


def test_publish_list_is_separate_from_build():
    doc = _mixed()
    assert doc.paths() == ["import_model", "kinematics"]
    assert doc.paths(phase=PUBLISH) == ["export_fbx", "export_maya"]
    assert doc.find("export_fbx") is None
    assert doc.find("export_fbx", phase=PUBLISH).type == "script"
    assert [node.name for node in doc.roots(PUBLISH)] == ["export_fbx", "export_maya"]


def test_same_name_in_both_phases_does_not_collide():
    doc = Document()
    assert doc.add(ActionNode("export", "script")) == "export"
    assert doc.add(ActionNode("export", "script"), phase=PUBLISH) == "export"
    assert doc.paths() == ["export"]
    assert doc.paths(phase=PUBLISH) == ["export"]


def test_publish_tree_operations_mirror_build():
    doc = _mixed()
    doc.add(ActionNode("cleanup", "script"), parent="export_fbx", phase=PUBLISH)
    assert doc.paths(phase=PUBLISH) == [
        "export_fbx",
        "export_fbx/cleanup",
        "export_maya",
    ]
    assert doc.move("export_maya", index=0, phase=PUBLISH) == "export_maya"
    assert doc.paths(phase=PUBLISH)[0] == "export_maya"
    assert doc.rename("export_fbx", "fbx", phase=PUBLISH) == "fbx"
    assert doc.duplicate("fbx", phase=PUBLISH) == "fbx1"
    doc.remove("fbx1", phase=PUBLISH)
    assert doc.paths(phase=PUBLISH) == ["export_maya", "fbx", "fbx/cleanup"]
    assert doc.parent_of("fbx/cleanup", phase=PUBLISH).name == "fbx"
    # the build list is untouched throughout
    assert doc.paths() == ["import_model", "kinematics"]


def test_unknown_phase_raises():
    with pytest.raises(SessionError):
        Document().roots("nope")
    with pytest.raises(SessionError):
        Document().paths(phase="nope")


def test_an_action_is_invisible_from_the_other_phase():
    doc = _mixed()
    with pytest.raises(SessionError):
        doc.move("kinematics", index=0, phase=PUBLISH)
    with pytest.raises(SessionError):
        doc.rename("export_fbx", "x")  # build phase, where it does not exist


def test_schema_6_round_trip(tmp_path):
    doc = _mixed()
    loaded = Document.load(doc.save(tmp_path / "s.tr"))
    assert SCHEMA_VERSION == 6
    assert loaded.schema == 6
    assert loaded.paths() == ["import_model", "kinematics"]
    assert loaded.paths(phase=PUBLISH) == ["export_fbx", "export_maya"]


def test_schema_5_file_loads_with_an_empty_publish_list(tmp_path):
    path = tmp_path / "old.tr"
    path.write_text(
        json.dumps(
            {
                "schema": 5,
                "meta": {},
                "guides": {},
                "actions": [
                    {
                        "name": "kinematics",
                        "type": "kinematics",
                        "enabled": True,
                        "settings": {},
                        "children": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded = Document.load(path)
    assert loaded.paths() == ["kinematics"]
    assert loaded.publish == []
    assert loaded.schema == SCHEMA_VERSION


def test_copy_carries_both_lists():
    clone = _mixed().copy()
    assert clone.paths() == ["import_model", "kinematics"]
    assert clone.paths(phase=PUBLISH) == ["export_fbx", "export_maya"]
