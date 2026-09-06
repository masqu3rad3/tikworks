"""Module references: storage, resolution and diff-derived overrides. No Maya."""

import pytest

from tik.trigger.core.guide_document import (
    GuideDocument,
    GuideRecord,
    ModuleEntry,
    ModuleReference,
)


def _entry(instance_id, name="spine", module_type="toy_root", side="C"):
    return ModuleEntry(
        instance_id=instance_id, module_type=module_type, name=name, side=side
    )


def test_reference_round_trips():
    ref = ModuleReference(
        ref_id="r1",
        file="base.tr",
        version="latest",
        overrides={"aaa": {"enabled": False}},
    )
    again = ModuleReference.from_dict(ref.to_dict())
    assert again.ref_id == "r1"
    assert again.file == "base.tr"
    assert again.overrides == {"aaa": {"enabled": False}}


def test_document_round_trips_references_and_frames():
    document = GuideDocument(
        modules=[_entry("aaa")],
        references=[ModuleReference(ref_id="r1", file="base.tr")],
        frames={"r1": {"position": [10.0, 20.0], "collapsed": True}},
    )
    again = GuideDocument.from_dict(document.to_dict())
    assert [item.ref_id for item in again.references] == ["r1"]
    assert again.frames["r1"]["collapsed"] is True
    assert again.reference("r1").file == "base.tr"


def test_entry_runtime_fields_are_not_serialized():
    """origin, source and enabled are resolution state, not file content."""
    entry = _entry("aaa")
    entry.origin = "r1"
    entry.source = _entry("aaa")
    entry.enabled = False
    stored = entry.to_dict()
    assert "origin" not in stored and "source" not in stored
    assert "enabled" not in stored
    assert ModuleEntry.from_dict(stored).origin is None
    assert ModuleEntry.from_dict(stored).enabled is True


def test_a_referenced_entry_is_not_written_to_the_file():
    """The link plus its overrides is the storage; the entries are derived."""
    local = _entry("aaa")
    borrowed = _entry("bbb", name="arm")
    borrowed.origin = "r1"
    borrowed.source = _entry("bbb", name="arm")
    document = GuideDocument(
        modules=[local, borrowed],
        references=[ModuleReference(ref_id="r1", file="base.tr")],
    )
    stored = document.to_dict()
    assert [item["instance_id"] for item in stored["modules"]] == ["aaa"]


def test_comparing_entries_does_not_recurse_through_source():
    """The runtime fields must stay out of the generated __eq__."""
    one, two = _entry("aaa"), _entry("aaa")
    one.source = _entry("aaa")
    two.source = None
    assert one == two


def test_schema_2_rejects_a_newer_document():
    with pytest.raises(ValueError):
        GuideDocument.from_dict({"schema": 99})


# ----------------------------------------------------------------- resolution
def _document_with(*entries, references=()) -> GuideDocument:
    return GuideDocument(modules=list(entries), references=list(references))


def _loader(table):
    """A ``Document.load`` stand-in mapping a file name to a GuideDocument."""

    class _Doc:
        def __init__(self, guides):
            self.guides = guides

    def load(path):
        key = str(path).replace("\\", "/")
        for name, guides in table.items():
            if key.endswith(name):
                return _Doc(guides)
        raise FileNotFoundError(key)

    return load


def test_resolution_inserts_referenced_entries():
    from tik.trigger.core.guide_reference import resolve

    base = _document_with(_entry("bbb", name="arm"))
    host = _document_with(
        _entry("aaa"), references=[ModuleReference(ref_id="r1", file="base.tr")]
    )
    problems = resolve(host, "", loader=_loader({"base.tr": base}))
    assert problems == []
    assert [item.instance_id for item in host.modules] == ["aaa", "bbb"]
    borrowed = host.module("bbb")
    assert borrowed.origin == "r1"
    assert borrowed.source is not None and borrowed.source.name == "arm"


def test_resolution_is_idempotent():
    from tik.trigger.core.guide_reference import resolve

    base = _document_with(_entry("bbb", name="arm"))
    host = _document_with(
        _entry("aaa"), references=[ModuleReference(ref_id="r1", file="base.tr")]
    )
    loader = _loader({"base.tr": base})
    resolve(host, "", loader=loader)
    resolve(host, "", loader=loader)
    assert [item.instance_id for item in host.modules] == ["aaa", "bbb"]


def test_source_is_a_deep_copy():
    """Editing the resolved entry must not touch what it is compared against."""
    from tik.trigger.core.guide_reference import resolve

    record = GuideRecord(role="root", position=(0.0, 0.0, 0.0))
    upstream = _entry("bbb", name="arm")
    upstream.guides = [record]
    host = _document_with(references=[ModuleReference(ref_id="r1", file="base.tr")])
    resolve(host, "", loader=_loader({"base.tr": _document_with(upstream)}))
    borrowed = host.module("bbb")
    borrowed.guides[0].position = (9.0, 9.0, 9.0)
    assert borrowed.source.guides[0].position == (0.0, 0.0, 0.0)
    assert record.position == (0.0, 0.0, 0.0)


def test_overrides_are_applied_on_resolution():
    from tik.trigger.core.guide_reference import resolve

    upstream = _entry("bbb", name="arm", side="L")
    upstream.guides = [GuideRecord(role="root", position=(0.0, 0.0, 0.0))]
    upstream.settings = {"segments": 3}
    host = _document_with(
        references=[
            ModuleReference(
                ref_id="r1",
                file="base.tr",
                overrides={
                    "bbb": {
                        "name": "wing",
                        "settings": {"segments": 5},
                        "inputs": {"root": "aaa.root"},
                        "guides": {"root:0": {"position": [1.0, 2.0, 3.0]}},
                        "enabled": False,
                    }
                },
            )
        ]
    )
    resolve(host, "", loader=_loader({"base.tr": _document_with(upstream)}))
    borrowed = host.module("bbb")
    assert borrowed.name == "wing"
    assert borrowed.settings["segments"] == 5
    assert borrowed.inputs["root"] == "aaa.root"
    assert borrowed.guides[0].position == (1.0, 2.0, 3.0)
    assert borrowed.enabled is False
    assert borrowed.source.name == "arm"
    assert borrowed.source.guides[0].position == (0.0, 0.0, 0.0)


def test_the_same_uuid_arriving_twice_is_dropped():
    """A diamond brings the same instance ids down two paths."""
    from tik.trigger.core.guide_reference import resolve

    shared = _document_with(_entry("bbb", name="arm"))
    host = _document_with(
        references=[
            ModuleReference(ref_id="r1", file="base.tr"),
            ModuleReference(ref_id="r2", file="props.tr"),
        ]
    )
    problems = resolve(
        host, "", loader=_loader({"base.tr": shared, "props.tr": shared})
    )
    assert [item.instance_id for item in host.modules] == ["bbb"]
    assert host.module("bbb").origin == "r1"
    assert any("already" in item for item in problems)


def test_a_missing_file_is_reported_not_raised():
    """A broken link must not stop the session opening."""
    from tik.trigger.core.guide_reference import resolve

    host = _document_with(
        _entry("aaa"), references=[ModuleReference(ref_id="r1", file="gone.tr")]
    )
    problems = resolve(host, "", loader=_loader({}))
    assert [item.instance_id for item in host.modules] == ["aaa"]
    assert any("gone.tr" in item for item in problems)


def test_a_cycle_is_reported():
    from tik.trigger.core.guide_reference import resolve

    inner = _document_with(references=[ModuleReference(ref_id="r2", file="self.tr")])
    host = _document_with(references=[ModuleReference(ref_id="r1", file="self.tr")])
    problems = resolve(host, "", loader=_loader({"self.tr": inner}))
    assert any("cycle" in item for item in problems)


def test_nested_references_are_owned_by_the_top_link():
    """An entry arriving through a chain belongs to the link it came through."""
    from tik.trigger.core.guide_reference import resolve

    deep = _document_with(_entry("ccc", name="hand"))
    middle = _document_with(
        _entry("bbb", name="arm"),
        references=[ModuleReference(ref_id="inner", file="deep.tr")],
    )
    host = _document_with(references=[ModuleReference(ref_id="r1", file="middle.tr")])
    resolve(host, "", loader=_loader({"middle.tr": middle, "deep.tr": deep}))
    assert sorted(item.instance_id for item in host.modules) == ["bbb", "ccc"]
    assert {item.origin for item in host.modules} == {"r1"}


# ----------------------------------------------------------- diffed overrides
def _resolved_host(**override):
    """A host holding one referenced module, ready to be edited."""
    from tik.trigger.core.guide_reference import resolve

    upstream = _entry("bbb", name="arm", side="L")
    upstream.guides = [GuideRecord(role="root", position=(0.0, 0.0, 0.0))]
    host = _document_with(
        references=[
            ModuleReference(ref_id="r1", file="base.tr", overrides=dict(override))
        ]
    )
    resolve(host, "", loader=_loader({"base.tr": _document_with(upstream)}))
    return host


def test_an_untouched_reference_stores_no_overrides():
    from tik.trigger.core.guide_reference import overrides_for

    host = _resolved_host()
    assert overrides_for(host.module("bbb")) == {}
    assert host.to_dict()["references"][0]["overrides"] == {}


def test_moving_a_guide_produces_a_pose_override():
    host = _resolved_host()
    host.module("bbb").guides[0].position = (1.0, 2.0, 3.0)
    stored = host.to_dict()["references"][0]["overrides"]
    assert stored["bbb"]["guides"]["root:0"]["position"] == [1.0, 2.0, 3.0]


def test_moving_a_guide_back_removes_the_override():
    """Self-cleaning: an override must always mean a real difference."""
    host = _resolved_host()
    entry = host.module("bbb")
    entry.guides[0].position = (1.0, 2.0, 3.0)
    assert host.to_dict()["references"][0]["overrides"]
    entry.guides[0].position = (0.0, 0.0, 0.0)
    assert host.to_dict()["references"][0]["overrides"] == {}


def test_float_noise_does_not_mint_an_override():
    """A draw/sync round-trip carries noise; reconcile's tolerance applies."""
    host = _resolved_host()
    host.module("bbb").guides[0].position = (0.0, 1e-9, -1e-9)
    assert host.to_dict()["references"][0]["overrides"] == {}


def test_renaming_and_disabling_produce_overrides():
    host = _resolved_host()
    entry = host.module("bbb")
    entry.name = "wing"
    entry.enabled = False
    stored = host.to_dict()["references"][0]["overrides"]["bbb"]
    assert stored["name"] == "wing"
    assert stored["enabled"] is False


def test_an_input_rewire_produces_an_override():
    host = _resolved_host()
    host.module("bbb").inputs["root"] = "aaa.root"
    stored = host.to_dict()["references"][0]["overrides"]["bbb"]
    assert stored["inputs"] == {"root": "aaa.root"}


def test_an_unresolved_link_keeps_the_overrides_it_was_loaded_with():
    """Load and save without resolving must not erase somebody's edits."""
    document = GuideDocument(
        references=[
            ModuleReference(
                ref_id="r1", file="base.tr", overrides={"bbb": {"name": "wing"}}
            )
        ]
    )
    assert host_overrides(document) == {"bbb": {"name": "wing"}}


def host_overrides(document):
    """The stored overrides of the document's single link."""
    return document.to_dict()["references"][0]["overrides"]


def test_overrides_survive_a_document_round_trip():
    """Store, reload, resolve again: the edit is still there."""
    from tik.trigger.core.guide_reference import resolve

    host = _resolved_host()
    host.module("bbb").name = "wing"
    stored = host.to_dict()

    upstream = _entry("bbb", name="arm", side="L")
    upstream.guides = [GuideRecord(role="root", position=(0.0, 0.0, 0.0))]
    reloaded = GuideDocument.from_dict(stored)
    resolve(reloaded, "", loader=_loader({"base.tr": _document_with(upstream)}))
    assert reloaded.module("bbb").name == "wing"
    assert reloaded.module("bbb").source.name == "arm"
