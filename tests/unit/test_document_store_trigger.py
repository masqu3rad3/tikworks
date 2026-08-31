"""The scene-side GuideDocument: module nodes plus holder layout."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core import registry
from tik.trigger.core.guide_document import GuideDocument, GuideRecord, ModuleEntry, SceneGroup
from tik.trigger.guides import document_store


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def fkchain(instance_id, name):
    entry = ModuleEntry(
        instance_id, "fkchain", name, "C",
        settings={"segments": 3},
        guides=[GuideRecord("root", position=(0.0, 0.0, 0.0))],
    )
    module = registry.get_module("fkchain")(
        instance_id=instance_id, name=name, settings=entry.settings
    )
    return entry, module


def test_empty_scene_reads_an_empty_document():
    document = document_store.read_document()
    assert document.modules == []
    assert document.scene_groups == []


def test_write_then_read_round_trips():
    entry, module = fkchain("id1", "tail")
    document = GuideDocument(
        modules=[entry],
        scene_groups=[SceneGroup("g1", "sceneNodes1", ["some_jnt"])],
        positions={"id1": [5.0, 6.0]},
        collapse={"id1": 1},
    )
    document_store.write_document(document, modules={"id1": module})
    restored = document_store.read_document()
    assert restored.module("id1").name == "tail"
    assert restored.module("id1").settings["segments"] == 3
    assert restored.group("g1").nodes == ["some_jnt"]
    assert restored.positions == {"id1": [5.0, 6.0]}
    assert restored.collapse == {"id1": 1}


def test_write_document_removes_entries_no_longer_present():
    first, first_module = fkchain("id1", "tail")
    second, second_module = fkchain("id2", "antenna")
    document_store.write_document(
        GuideDocument(modules=[first, second]),
        modules={"id1": first_module, "id2": second_module},
    )
    document_store.write_document(GuideDocument(modules=[first]), modules={"id1": first_module})
    restored = document_store.read_document()
    assert [entry.instance_id for entry in restored.modules] == ["id1"]


def test_single_entry_write_and_read():
    entry, module = fkchain("id1", "tail")
    document_store.write_entry(entry, module)
    assert document_store.read_entry("id1").name == "tail"
    document_store.remove_entry("id1")
    assert document_store.read_entry("id1") is None


def test_write_entry_updates_rather_than_duplicating():
    entry, module = fkchain("id1", "tail")
    document_store.write_entry(entry, module)
    entry.name = "renamed"
    document_store.write_entry(entry, module)
    document = document_store.read_document()
    assert len(document.modules) == 1
    assert document.modules[0].name == "renamed"


def test_the_whole_document_survives_a_write_read_cycle():
    """Serialization must be lossless -- the .trg is written from this."""
    entry, module = fkchain("id1", "tail")
    entry.inputs = {"root": "id9.end"}
    entry.guides = [
        GuideRecord("root", position=(1.0, 2.0, 3.0), rotation=(0.0, 90.0, 0.0),
                    rotate_order=2, attrs={"twistWeight": 0.25}),
        GuideRecord("segment", 0, parent=("root", 0)),
    ]
    document = GuideDocument(modules=[entry])
    document_store.write_document(document, modules={"id1": module})
    restored = document_store.read_document()
    assert restored.to_dict() == document.to_dict()
