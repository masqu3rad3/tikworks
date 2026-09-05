"""Reconcile: what the document says versus what the scene renders."""

from tik.trigger.core.guide_document import GuideDocument, GuideRecord, ModuleEntry
from tik.trigger.core.reconcile import RenderedGuide, reconcile


def entry(instance_id="id1", **kwargs):
    kwargs.setdefault("module_type", "fkchain")
    kwargs.setdefault("name", "tail")
    kwargs.setdefault("side", "C")
    kwargs.setdefault(
        "guides",
        [
            GuideRecord("root", position=(0.0, 0.0, 0.0)),
            GuideRecord("segment", 0, position=(5.0, 0.0, 0.0), parent=("root", 0)),
        ],
    )
    return ModuleEntry(instance_id, **kwargs)


def rendered(instance_id="id1", pairs=(("root", 0), ("segment", 0)), positions=None):
    positions = positions or {
        ("root", 0): (0.0, 0.0, 0.0),
        ("segment", 0): (5.0, 0.0, 0.0),
    }
    parents = {("root", 0): None, ("segment", 0): (instance_id, "root", 0)}
    return [
        RenderedGuide(
            instance_id=instance_id,
            role=role,
            index=index,
            node=f"{role}{index}_guide",
            position=positions[(role, index)],
            parent=parents.get((role, index)),
            key="tail",  # entry() names the module "tail" on the centre side
        )
        for role, index in pairs
    ]


def test_clean_document_and_scene_agree():
    diff = reconcile(GuideDocument(modules=[entry()]), rendered())
    assert diff.is_clean
    assert diff.stale == []
    assert diff.drifted == []


def test_module_with_nothing_rendered_is_absent():
    diff = reconcile(GuideDocument(modules=[entry()]), [])
    assert diff.modules["id1"].absent is True
    assert diff.not_drawn == ["id1"]
    assert diff.drifted == []


def test_deleted_guide_is_missing_and_stale():
    diff = reconcile(GuideDocument(modules=[entry()]), rendered(pairs=(("root", 0),)))
    module = diff.modules["id1"]
    assert module.missing == [("segment", 0)]
    assert module.is_stale is True
    assert diff.stale == ["id1"]


def test_extra_rendered_guide_is_unexpected_and_stale():
    scene = rendered() + [
        RenderedGuide("id1", "segment", 1, "segment1_guide", position=(9.0, 0.0, 0.0))
    ]
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    assert diff.modules["id1"].unexpected == [("segment", 1)]
    assert diff.stale == ["id1"]


def test_moved_guide_is_drift_not_stale():
    """The rigger dragged the elbow. Capture must win; regenerate must not run."""
    scene = rendered(
        positions={("root", 0): (0.0, 0.0, 0.0), ("segment", 0): (7.5, 1.0, 0.0)}
    )
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    module = diff.modules["id1"]
    assert module.drifted == [("segment", 0)]
    assert module.needs_capture is True
    assert module.is_stale is False
    assert diff.stale == []
    assert diff.drifted == ["id1"]


def test_changed_guide_attr_is_drift():
    document = GuideDocument(
        modules=[
            entry(
                guides=[
                    GuideRecord(
                        "root", position=(0.0, 0.0, 0.0), attrs={"twistWeight": 0.5}
                    ),
                ]
            )
        ]
    )
    scene = [
        RenderedGuide(
            "id1",
            "root",
            0,
            "root_guide",
            position=(0.0, 0.0, 0.0),
            attrs={"twistWeight": 0.9},
        )
    ]
    diff = reconcile(document, scene)
    assert diff.modules["id1"].drifted == [("root", 0)]
    assert diff.stale == []


def test_unposed_record_is_reported_so_capture_claims_it():
    """A guide the document has no pose for yet must be captured, not redrawn."""
    document = GuideDocument(modules=[entry(guides=[GuideRecord("root")])])
    scene = [RenderedGuide("id1", "root", 0, "root_guide", position=(3.0, 3.0, 3.0))]
    diff = reconcile(document, scene)
    assert diff.modules["id1"].drifted == [("root", 0)]
    assert diff.stale == []


def test_tiny_float_difference_is_not_drift():
    scene = rendered(
        positions={("root", 0): (0.0, 0.0, 0.0), ("segment", 0): (5.0 + 1e-9, 0.0, 0.0)}
    )
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    assert diff.modules["id1"].drifted == []


def test_wrong_intra_module_parent_is_stale():
    scene = rendered()
    scene[1] = RenderedGuide(
        "id1", "segment", 0, "segment0_guide", position=(5.0, 0.0, 0.0), parent=None
    )
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    assert diff.modules["id1"].parent_wrong is True
    assert diff.stale == ["id1"]


def test_root_parent_follows_the_primary_input():
    """The DAG is a rendering of the primary input connection (spec 4.4)."""
    document = GuideDocument(
        modules=[
            entry("child", inputs={"root": "parent.end"}),
            entry(
                "parent",
                name="spine",
                guides=[GuideRecord("root", position=(0.0, 0.0, 0.0))],
            ),
        ]
    )
    scene = rendered("child") + [
        RenderedGuide("parent", "root", 0, "spine_root_guide", position=(0.0, 0.0, 0.0))
    ]
    diff = reconcile(document, scene, primary_input_of=lambda entry: "root")
    assert diff.modules["child"].parent_wrong is True
    assert "child" in diff.stale


def test_orphan_joints_are_reported_never_regenerated():
    scene = rendered() + [RenderedGuide("ghost", "root", 0, "ghost_root_guide")]
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    assert diff.orphans == ["ghost_root_guide"]
    assert diff.stale == []
    assert diff.is_clean is False


def test_maya_duplicate_reports_duplicates_not_a_merge():
    """Duplicating a hierarchy copies trg_instance; the copies must not merge."""
    scene = rendered() + [
        RenderedGuide("id1", "root", 0, "root_guide1", position=(0.0, 0.0, 0.0)),
        RenderedGuide("id1", "segment", 0, "segment0_guide1", position=(5.0, 0.0, 0.0)),
    ]
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    assert sorted(diff.duplicates) == ["root_guide1", "segment0_guide1"]
    assert diff.modules["id1"].is_stale is False


def test_empty_document_and_empty_scene_is_clean():
    assert reconcile(GuideDocument(), []).is_clean


def test_absent_is_not_drawn_and_never_stale():
    diff = reconcile(GuideDocument(modules=[entry()]), [])
    assert diff.not_drawn == ["id1"]
    assert diff.stale == []
    assert diff.modules["id1"].is_stale is False


def test_missing_guide_is_stale_not_not_drawn():
    diff = reconcile(GuideDocument(modules=[entry()]), rendered(pairs=(("root", 0),)))
    assert diff.stale == ["id1"]
    assert diff.not_drawn == []


def test_not_drawn_is_not_clean():
    assert reconcile(GuideDocument(modules=[entry()]), []).is_clean is False


def test_renamed_entry_is_stale_when_the_joints_carry_the_old_key():
    document = GuideDocument(modules=[entry(name="frontLeg")])
    diff = reconcile(document, rendered())
    assert diff.stale == ["id1"]
    assert diff.modules["id1"].key_stale is True


def test_an_untagged_rendering_is_never_key_stale():
    """A guide with no recorded key says nothing about the name."""
    scene = rendered()
    for guide in scene:
        guide.key = ""
    diff = reconcile(GuideDocument(modules=[entry()]), scene)
    assert diff.modules["id1"].key_stale is False
