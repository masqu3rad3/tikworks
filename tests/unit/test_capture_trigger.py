"""Capture: poses and guide attrs flow from the scene into the document."""

from tik.trigger.core.guide_document import GuideDocument, GuideRecord, ModuleEntry
from tik.trigger.core.reconcile import RenderedGuide
from tik.trigger.guides.capture import capture


def document():
    return GuideDocument(
        modules=[
            ModuleEntry(
                "id1",
                "fkchain",
                "tail",
                "C",
                guides=[
                    GuideRecord(
                        "root", position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)
                    ),
                    GuideRecord(
                        "segment", 0, position=(5.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)
                    ),
                ],
            )
        ]
    )


def test_capture_updates_a_moved_guide():
    doc = document()
    changed = capture(
        doc, [RenderedGuide("id1", "segment", 0, "n", position=(7.0, 1.0, 0.0))]
    )
    assert changed is True
    assert doc.module("id1").guide("segment", 0).position == (7.0, 1.0, 0.0)


def test_capture_is_additive_a_deleted_guide_keeps_its_pose():
    """The rule that makes deleting a joint lossless."""
    doc = document()
    capture(doc, [RenderedGuide("id1", "root", 0, "n", position=(0.0, 0.0, 0.0))])
    assert doc.module("id1").guide("segment", 0).position == (5.0, 0.0, 0.0)


def test_capture_never_drops_a_record():
    doc = document()
    capture(doc, [])
    assert doc.module("id1").pairs == [("root", 0), ("segment", 0)]


def test_capture_records_guide_attrs():
    doc = document()
    capture(
        doc,
        [
            RenderedGuide(
                "id1",
                "root",
                0,
                "n",
                position=(0.0, 0.0, 0.0),
                attrs={"twistWeight": 0.25},
            )
        ],
    )
    assert doc.module("id1").guide("root").attrs == {"twistWeight": 0.25}


def test_capture_marks_an_unposed_record_as_posed():
    doc = GuideDocument(
        modules=[
            ModuleEntry(
                "id1",
                "fkchain",
                "tail",
                "C",
                guides=[GuideRecord("root")],
            )
        ]
    )
    capture(doc, [RenderedGuide("id1", "root", 0, "n", position=(2.0, 0.0, 0.0))])
    record = doc.module("id1").guide("root")
    assert record.posed is True
    assert record.position == (2.0, 0.0, 0.0)


def test_capture_ignores_guides_of_unknown_modules():
    doc = document()
    assert (
        capture(doc, [RenderedGuide("ghost", "root", 0, "n", position=(1.0, 1.0, 1.0))])
        is False
    )


def test_capture_reports_no_change_when_nothing_moved():
    doc = document()
    scene = [
        RenderedGuide("id1", "root", 0, "n", position=(0.0, 0.0, 0.0)),
        RenderedGuide("id1", "segment", 0, "n2", position=(5.0, 0.0, 0.0)),
    ]
    assert capture(doc, scene) is False


def test_capture_records_rotation_and_order():
    doc = document()
    capture(
        doc,
        [
            RenderedGuide(
                "id1",
                "root",
                0,
                "n",
                position=(0.0, 0.0, 0.0),
                rotation=(10.0, 20.0, 30.0),
                rotate_order=3,
            )
        ],
    )
    record = doc.module("id1").guide("root")
    assert record.rotation == (10.0, 20.0, 30.0)
    assert record.rotate_order == 3


def test_capture_leaves_a_module_with_no_rendering_completely_alone():
    """A module whose guides are all gone must keep every stored pose."""
    doc = document()
    before = doc.module("id1").to_dict()
    capture(doc, [RenderedGuide("other", "root", 0, "n")])
    assert doc.module("id1").to_dict() == before


def test_first_capture_records_a_rotation_the_document_never_had():
    """``rotation is None`` means "no opinion"; filling it in is a real change."""
    doc = GuideDocument(
        modules=[
            ModuleEntry(
                "id1",
                "fkchain",
                "tail",
                "C",
                guides=[GuideRecord("root", position=(0.0, 0.0, 0.0))],
            )
        ]
    )
    assert doc.module("id1").guide("root").rotation is None
    assert (
        capture(doc, [RenderedGuide("id1", "root", 0, "n", position=(0.0, 0.0, 0.0))])
        is True
    )
    assert doc.module("id1").guide("root").rotation == (0.0, 0.0, 0.0)


def two_modules():
    """``id1`` and ``id2``, each with one guide at the origin."""
    return GuideDocument(
        modules=[
            ModuleEntry(
                instance_id,
                "fkchain",
                name,
                "C",
                guides=[
                    GuideRecord(
                        "root", position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)
                    )
                ],
            )
            for instance_id, name in (("id1", "tail"), ("id2", "neck"))
        ]
    )


def both_moved():
    return [
        RenderedGuide("id1", "root", 0, "n1", position=(1.0, 2.0, 3.0)),
        RenderedGuide("id2", "root", 0, "n2", position=(4.0, 5.0, 6.0)),
    ]


def test_scope_limits_which_modules_are_captured():
    doc = two_modules()
    assert capture(doc, both_moved(), scope=["id1"]) is True
    assert doc.module("id1").guide("root", 0).position == (1.0, 2.0, 3.0)
    assert doc.module("id2").guide("root", 0).position == (0.0, 0.0, 0.0)


def test_scope_none_captures_everything():
    doc = two_modules()
    assert capture(doc, both_moved()) is True
    assert doc.module("id2").guide("root", 0).position == (4.0, 5.0, 6.0)
