"""Rebuilding a session out of what the scene carries. Pure: no Maya."""

import pytest

from toy_modules import ToyChain
from tik.trigger.core import clear_registries, register_module
from tik.trigger.core.reconcile import RenderedGuide
from tik.trigger.core.scene_recovery import SceneModule, document_from_scene


@pytest.fixture(autouse=True)
def _registered_modules():
    """These tests need *a* registered module type, not real module behaviour.

    ``document_from_scene`` only calls ``registry.is_module_registered`` --
    it never builds or draws anything -- so a toy module is the right double
    (same pattern as ``test_core_trigger.py``), not ``load_plugins()``. That
    would pull in every production module's import-time health and real
    ``fkchain`` behaviour this pure-core test does not need, and would leave
    the process-global registry populated afterwards. ``ToyChain``'s guide
    layout (``root``, multi ``segment``) happens to match the role names the
    tests already use.
    """
    clear_registries()
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


def rendered(instance_id, role, index=0, position=(1.0, 2.0, 3.0), parent=None):
    return RenderedGuide(
        instance_id=instance_id, role=role, index=index,
        node=f"|{role}{index}", position=position, rotation=(0.0, 0.0, 0.0),
        rotate_order=0, attrs={}, parent=parent,
    )


def test_a_breadcrumb_restores_name_settings_and_inputs():
    scene = [SceneModule("id1", "toy_chain", "L", {
        "instance_id": "id1", "module_type": "toy_chain", "name": "tail",
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
    scene = [SceneModule("id1", "toy_chain", "C", {
        "instance_id": "id1", "module_type": "toy_chain", "name": "tail",
        "side": "C", "settings": {}, "inputs": {},
    })]
    document, _report = document_from_scene(
        scene, [rendered("id1", "root", position=(7.0, 8.0, 9.0))]
    )
    assert document.module("id1").guide("root", 0).position == pytest.approx((7.0, 8.0, 9.0))


def test_without_a_breadcrumb_it_degrades_and_says_so():
    """An older scene: type and side survive on the joints, nothing else does."""
    scene = [SceneModule("id1", "toy_chain", "R", None)]
    document, report = document_from_scene(scene, [rendered("id1", "root")])
    entry = document.module("id1")
    assert entry.name == "toy_chain"   # falls back to the module type
    assert entry.side == "R"           # trg_side is on every joint
    assert entry.settings == {}
    assert entry.inputs == {}
    assert not report.is_lossless
    assert [item.instance_id for item in report.partial] == ["id1"]


def test_a_mixed_scene_reports_a_mixed_result():
    scene = [
        SceneModule("id1", "toy_chain", "C", {
            "instance_id": "id1", "module_type": "toy_chain", "name": "tail",
            "side": "C", "settings": {}, "inputs": {},
        }),
        SceneModule("id2", "toy_chain", "C", None),
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


def test_a_mixed_scene_with_an_unknown_type_is_not_lossless():
    """Isolates the unknown_types clause of is_lossless.

    A valid module alone would make ``report.modules`` non-empty and
    ``report.partial`` empty -- so with a known-good module present, only the
    ``unknown_types`` check can still pull ``is_lossless`` down to False.
    """
    scene = [
        SceneModule("id1", "toy_chain", "C", {
            "instance_id": "id1", "module_type": "toy_chain", "name": "tail",
            "side": "C", "settings": {}, "inputs": {},
        }),
        SceneModule("id2", "nosuchmodule", "C", None),
    ]
    document, report = document_from_scene(
        scene, [rendered("id1", "root"), rendered("id2", "root")]
    )
    assert document.module("id1") is not None
    assert report.unknown_types == ["nosuchmodule"]
    assert report.is_lossless is False


def test_an_empty_scene_is_not_lossless():
    document, report = document_from_scene([], [])
    assert document.modules == []
    assert report.is_lossless is False


def test_guide_parents_within_the_module_survive():
    scene = [SceneModule("id1", "toy_chain", "C", None)]
    document, _report = document_from_scene(scene, [
        rendered("id1", "root"),
        rendered("id1", "segment", 0, parent=("id1", "root", 0)),
    ])
    assert document.module("id1").guide("segment", 0).parent == ("root", 0)


def test_a_parent_in_another_module_is_not_an_internal_parent():
    """RenderedGuide.parent is a global triple; GuideRecord.parent is module-local."""
    scene = [SceneModule("id1", "toy_chain", "C", None)]
    document, _report = document_from_scene(
        scene, [rendered("id1", "root", parent=("id0", "root", 0))]
    )
    assert document.module("id1").guide("root", 0).parent is None
