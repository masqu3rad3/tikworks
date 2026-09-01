"""Rebuilding a session out of what the scene carries. Pure: no Maya."""

import pytest

from tik.trigger.core.reconcile import RenderedGuide
from tik.trigger.core.scene_recovery import SceneModule, document_from_scene


@pytest.fixture(autouse=True)
def _registered_modules():
    """The test scenes reference real module types ("fkchain"); register them.

    This only registers module classes (pure Python decorators) -- it does not
    touch a Maya scene, so it does not compromise this file's Maya-free intent.
    """
    import tik.trigger as trigger

    trigger.load_plugins()


def rendered(instance_id, role, index=0, position=(1.0, 2.0, 3.0), parent=None):
    return RenderedGuide(
        instance_id=instance_id, role=role, index=index,
        node=f"|{role}{index}", position=position, rotation=(0.0, 0.0, 0.0),
        rotate_order=0, attrs={}, parent=parent,
    )


def test_a_breadcrumb_restores_name_settings_and_inputs():
    scene = [SceneModule("id1", "fkchain", "L", {
        "instance_id": "id1", "module_type": "fkchain", "name": "tail",
        "side": "L", "settings": {"segments": 2}, "inputs": {"parent": "id0.root"},
    })]
    document, report = document_from_scene(scene, [rendered("id1", "root")])
    entry = document.module("id1")
    assert entry.name == "tail"
    assert entry.settings == {"segments": 2}
    assert entry.inputs == {"parent": "id0.root"}
    assert report.is_lossless


def test_poses_come_from_the_joints_not_the_breadcrumb():
    """The breadcrumb has no poses by design; the rendering supplies them."""
    scene = [SceneModule("id1", "fkchain", "C", {
        "instance_id": "id1", "module_type": "fkchain", "name": "tail",
        "side": "C", "settings": {}, "inputs": {},
    })]
    document, _report = document_from_scene(
        scene, [rendered("id1", "root", position=(7.0, 8.0, 9.0))]
    )
    assert document.module("id1").guide("root", 0).position == pytest.approx((7.0, 8.0, 9.0))


def test_without_a_breadcrumb_it_degrades_and_says_so():
    """An older scene: type and side survive on the joints, nothing else does."""
    scene = [SceneModule("id1", "fkchain", "R", None)]
    document, report = document_from_scene(scene, [rendered("id1", "root")])
    entry = document.module("id1")
    assert entry.name == "fkchain"   # falls back to the module type
    assert entry.side == "R"         # trg_side is on every joint
    assert entry.settings == {}
    assert entry.inputs == {}
    assert not report.is_lossless
    assert [item.instance_id for item in report.partial] == ["id1"]


def test_a_mixed_scene_reports_a_mixed_result():
    scene = [
        SceneModule("id1", "fkchain", "C", {
            "instance_id": "id1", "module_type": "fkchain", "name": "tail",
            "side": "C", "settings": {}, "inputs": {},
        }),
        SceneModule("id2", "fkchain", "C", None),
    ]
    _document, report = document_from_scene(
        scene, [rendered("id1", "root"), rendered("id2", "root")]
    )
    assert len(report.complete) == 1
    assert len(report.partial) == 1
    assert not report.is_lossless


def test_an_unregistered_module_type_is_skipped_and_reported():
    scene = [SceneModule("id1", "nosuchmodule", "C", None)]
    document, report = document_from_scene(scene, [rendered("id1", "root")])
    assert document.modules == []
    assert report.unknown_types == ["nosuchmodule"]


def test_guide_parents_within_the_module_survive():
    scene = [SceneModule("id1", "fkchain", "C", None)]
    document, _report = document_from_scene(scene, [
        rendered("id1", "root"),
        rendered("id1", "segment", 0, parent=("id1", "root", 0)),
    ])
    assert document.module("id1").guide("segment", 0).parent == ("root", 0)


def test_a_parent_in_another_module_is_not_an_internal_parent():
    """RenderedGuide.parent is a global triple; GuideRecord.parent is module-local."""
    scene = [SceneModule("id1", "fkchain", "C", None)]
    document, _report = document_from_scene(
        scene, [rendered("id1", "root", parent=("id0", "root", 0))]
    )
    assert document.module("id1").guide("root", 0).parent is None
