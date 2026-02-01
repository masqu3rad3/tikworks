"""Unit tests for tik.maya.types.skincluster."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pytest
from maya import cmds
from maya.api import OpenMaya

import tik.maya.types.skincluster as skincluster_module
from tik.maya.types.skincluster import SkinCluster, SkinWeights


def _create_joint_chain(prefix: str) -> List[str]:
    cmds.select(clear=True)
    root_joint = cmds.joint(name=f"{prefix}_root", position=(0.0, 0.0, 0.0))
    child_joint = cmds.joint(name=f"{prefix}_child", position=(1.0, 0.0, 0.0))
    return [root_joint, child_joint]


def _create_mesh(prefix: str) -> Dict[str, str]:
    mesh_transform, _mesh_shape = cmds.polyPlane(
        name=f"{prefix}_mesh", subdivisionsX=1, subdivisionsY=1
    )
    mesh_shape = cmds.listRelatives(mesh_transform, shapes=True, fullPath=False)[0]
    return {"transform": mesh_transform, "shape": mesh_shape}


@pytest.fixture
def skincluster_setup() -> Dict[str, object]:
    joint_names = _create_joint_chain("source")
    mesh_data = _create_mesh("source")
    skincluster = SkinCluster.create(
        geometry=mesh_data["transform"],
        influences=joint_names,
        name="source_skin",
    )
    return {
        "skincluster": skincluster,
        "mesh_transform": mesh_data["transform"],
        "mesh_shape": mesh_data["shape"],
        "joints": joint_names,
    }


def _build_weights(influence_count: int, vertex_count: int, primary: float) -> List[float]:
    weights = []
    for _vertex_index in range(vertex_count):
        weights.append(primary)
        weights.append(1.0 - primary)
    if influence_count != 2:
        raise ValueError("This helper assumes exactly two influences.")
    return weights


# === SkinWeights Tests ===


def test_skinweights_access_and_normalize():
    weights = [0.2, 0.8, 0.5, 0.5]
    skin_weights = SkinWeights(weights, influence_count=2, vertex_count=2)

    assert skin_weights.weights == weights
    assert skin_weights.influence_count == 2
    assert skin_weights.vertex_count == 2
    assert skin_weights.influence_names == []

    assert skin_weights.get_vertex_weights(1) == [0.5, 0.5]
    assert skin_weights.get_influence_weights(0) == [0.2, 0.5]

    assert len(skin_weights) == 4
    assert skin_weights[0] == 0.2
    skin_weights[0] = 0.4
    assert skin_weights[0] == 0.4
    assert list(iter(skin_weights)) == [0.4, 0.8, 0.5, 0.5]

    normalized = skin_weights.copy().normalize()
    assert normalized.get_vertex_weights(0) == pytest.approx([0.333333, 0.666666], rel=1e-3)

    zero_weights = SkinWeights([0.0, 0.0], influence_count=2, vertex_count=1)
    zero_weights.normalize()
    assert zero_weights.weights == [0.0, 0.0]

    clamped = SkinWeights([-1.0, 2.0], influence_count=2, vertex_count=1).clamp()
    assert clamped.weights == [0.0, 1.0]

    assert "SkinWeights" in repr(skin_weights)


def test_skinweights_index_errors():
    skin_weights = SkinWeights([0.1, 0.9], influence_count=2, vertex_count=1)
    with pytest.raises(IndexError):
        skin_weights.get_vertex_weights(-1)
    with pytest.raises(IndexError):
        skin_weights.get_vertex_weights(1)
    with pytest.raises(IndexError):
        skin_weights.get_influence_weights(-1)
    with pytest.raises(IndexError):
        skin_weights.get_influence_weights(2)


def test_skinweights_arithmetic_and_comparisons():
    weights_one = SkinWeights([0.2, 0.8], influence_count=2, vertex_count=1)
    weights_two = SkinWeights([0.1, 0.9], influence_count=2, vertex_count=1)

    assert (weights_one + weights_two).weights == [0.30000000000000004, 1.7000000000000002]
    assert (weights_one + 0.5).weights == [0.7, 1.3]
    assert (0.5 + weights_one).weights == [0.7, 1.3]

    assert (weights_one - weights_two).weights == [0.1, -0.09999999999999998]
    assert (weights_one - 0.1).weights == [0.1, 0.7000000000000001]
    assert (1.0 - weights_one).weights == [0.8, 0.19999999999999996]

    assert (weights_one * weights_two).weights == [0.020000000000000004, 0.7200000000000001]
    assert (weights_one * 2.0).weights == [0.4, 1.6]
    assert (2.0 * weights_one).weights == [0.4, 1.6]

    assert (weights_one / weights_two).weights == [2.0, 0.888888888888889]
    assert (weights_one / 2.0).weights == [0.1, 0.4]

    assert (-weights_one).weights == [0.8, 0.19999999999999996]

    assert weights_one == SkinWeights([0.2, 0.8], influence_count=2, vertex_count=1)
    assert weights_one != SkinWeights([0.2, 0.7], influence_count=2, vertex_count=1)
    assert weights_one != "not-skinweights"
    assert weights_one != SkinWeights([0.2], influence_count=1, vertex_count=1)

    mismatch = SkinWeights([0.1], influence_count=1, vertex_count=1)
    with pytest.raises(ValueError):
        _ = weights_one + mismatch
    with pytest.raises(ValueError):
        _ = weights_one - mismatch
    with pytest.raises(ValueError):
        _ = weights_one * mismatch
    with pytest.raises(ValueError):
        _ = weights_one / mismatch

    with pytest.raises(ZeroDivisionError):
        _ = weights_one / 0.0

    zero_divisor = SkinWeights([0.0, 0.0], influence_count=2, vertex_count=1)
    assert (weights_one / zero_divisor).weights == [0.0, 0.0]


# === SkinCluster Tests ===


def test_create_and_properties(skincluster_setup: Dict[str, object]):
    skincluster = skincluster_setup["skincluster"]
    mesh_shape = skincluster_setup["mesh_shape"]

    assert skincluster.name == "source_skin"
    assert set(skincluster.influences) == set(skincluster_setup["joints"])
    assert skincluster.influence_count == 2

    assert skincluster.geometry == mesh_shape
    assert mesh_shape in skincluster.geometries

    skincluster.skinning_method = 1
    assert skincluster.skinning_method == 1

    skincluster.normalize_weights = 2
    assert skincluster.normalize_weights == 2

    skincluster.max_influences = 2
    assert skincluster.max_influences == 2

    assert skincluster.vertex_count == cmds.polyEvaluate(mesh_shape, vertex=True)

    assert len(skincluster) == skincluster.influence_count
    assert list(iter(skincluster)) == skincluster.influences


def test_geometry_helpers_and_influence_indices(skincluster_setup: Dict[str, object]):
    skincluster = skincluster_setup["skincluster"]
    dag_path, vertex_component, skin_function = skincluster._get_geometry_dag_and_components()

    assert dag_path.isValid()
    assert vertex_component.apiType() == OpenMaya.MFn.kMeshVertComponent

    influence_indices = skincluster._get_influence_indices(skin_function)
    assert len(influence_indices) == skincluster.influence_count


def test_influence_index_add_remove_and_locking(
    skincluster_setup: Dict[str, object], monkeypatch: pytest.MonkeyPatch
):
    skincluster = skincluster_setup["skincluster"]
    joint_name = skincluster_setup["joints"][0]

    assert skincluster.influence_index(joint_name) >= 0

    extra_transform = cmds.spaceLocator(name="extra_locator")[0]
    with pytest.raises(ValueError):
        skincluster.influence_index(extra_transform)

    new_index = skincluster.add_influence(extra_transform, weight=0.0, lock_weights=False)
    assert extra_transform in skincluster
    assert new_index >= 0

    skincluster.lock_influence(joint_name, lock=True)
    assert skincluster.is_influence_locked(joint_name) is True
    skincluster.lock_influence(joint_name, lock=False)
    assert skincluster.is_influence_locked(joint_name) is False

    lock_weights_plug = f"{skincluster.name}.lockWeights[{new_index}]"
    connected_plugs = cmds.listConnections(
        lock_weights_plug, plugs=True, source=True, destination=False
    ) or []
    for source_plug in connected_plugs:
        cmds.disconnectAttr(source_plug, lock_weights_plug)
    cmds.setAttr(lock_weights_plug, lock=False)

    def attribute_query_override(attribute, node=None, exists=False, **kwargs):
        if attribute == "liw" and node == extra_transform and exists:
            return False
        return original_attribute_query(attribute, node=node, exists=exists, **kwargs)

    # Maya often adds a liw attribute to influences, so we force the fallback branch.
    original_attribute_query = skincluster_module.cmds.attributeQuery
    monkeypatch.setattr(skincluster_module.cmds, "attributeQuery", attribute_query_override)

    skincluster.lock_influence(extra_transform, lock=True)
    assert skincluster.is_influence_locked(extra_transform) is True

    skincluster.remove_influence(extra_transform)
    assert extra_transform not in skincluster


def test_get_set_weights_and_vertices(skincluster_setup: Dict[str, object]):
    skincluster = skincluster_setup["skincluster"]

    influence_count = skincluster.influence_count
    vertex_count = skincluster.vertex_count
    weight_values = _build_weights(influence_count, vertex_count, primary=0.25)

    skincluster.set_weights(weight_values, normalize=True)
    retrieved = skincluster.get_weights()
    assert retrieved.influence_count == influence_count
    assert retrieved.vertex_count == vertex_count
    assert len(retrieved.weights) == len(weight_values)
    assert set(retrieved.influence_names) == set(skincluster.influences)

    skin_weights = SkinWeights(
        weight_values,
        influence_count=influence_count,
        vertex_count=vertex_count,
        influence_names=skincluster.influences,
    )
    skincluster.set_weights(skin_weights, normalize=False)

    vertex_subset = [0, 1]
    subset_weights = _build_weights(influence_count, len(vertex_subset), primary=0.6)
    skincluster.set_vertex_weights(vertex_subset, subset_weights)

    subset_skin_weights = SkinWeights(
        subset_weights,
        influence_count=influence_count,
        vertex_count=len(vertex_subset),
    )
    skincluster.set_vertex_weights(vertex_subset, subset_skin_weights, normalize=False)

    retrieved_subset = skincluster.get_vertex_weights(vertex_subset)
    assert retrieved_subset.vertex_count == len(vertex_subset)
    assert retrieved_subset.influence_count == influence_count


def test_blend_weights_and_prune(skincluster_setup: Dict[str, object]):
    skincluster = skincluster_setup["skincluster"]

    blend_weights = [0.1] * skincluster.vertex_count
    skincluster.set_blend_weights(blend_weights)
    assert skincluster.get_blend_weights() == pytest.approx(blend_weights)

    skincluster.prune_weights(threshold=0.2)


def test_copy_mirror_reset_weights():
    source_joint_names = _create_joint_chain("copy")
    source_mesh = _create_mesh("copy_source")
    target_mesh = _create_mesh("copy_target")

    source_skin = SkinCluster.create(
        geometry=source_mesh["transform"],
        influences=source_joint_names,
        name="copy_source_skin",
    )
    target_skin = SkinCluster.create(
        geometry=target_mesh["transform"],
        influences=source_joint_names,
        name="copy_target_skin",
    )

    source_skin.copy_weights(target_skin)
    source_skin.mirror_weights(mirror_mode="YZ", mirror_inverse=True)
    source_skin.reset_weights(to_bind_pose=False)
    source_skin.reset_weights(to_bind_pose=True)


def test_save_and_load_weights(tmp_path: Path, skincluster_setup: Dict[str, object]):
    skincluster = skincluster_setup["skincluster"]

    export_path = tmp_path / "skin_weights.xml"
    skincluster.save_weights(export_path)

    exported_files = list(tmp_path.iterdir())
    assert exported_files

    skincluster.load_weights(export_path, method="index")


def test_save_weights_for_nurbs_surface(tmp_path: Path):
    joint_names = _create_joint_chain("nurbs")
    surface_transform, _surface_shape = cmds.nurbsPlane(name="nurbs_surface")
    skincluster = SkinCluster.create(
        geometry=surface_transform,
        influences=joint_names,
        name="nurbs_skin",
    )

    export_path = tmp_path / "nurbs_weights.xml"
    skincluster.save_weights(export_path)
    assert list(tmp_path.iterdir())


def test_bind_pose_and_rebind(skincluster_setup: Dict[str, object]):
    skincluster = skincluster_setup["skincluster"]

    bind_pose_node = skincluster.bind_pose()
    assert bind_pose_node

    skincluster.go_to_bind_pose()
    skincluster.rebind()

    cmds.delete(bind_pose_node)
    assert skincluster.bind_pose() is None
    skincluster.go_to_bind_pose()


def test_unbind_and_delete_history():
    joint_names = _create_joint_chain("unbind")
    mesh_data = _create_mesh("unbind")
    skincluster = SkinCluster.create(
        geometry=mesh_data["transform"],
        influences=joint_names,
        name="unbind_skin",
    )

    skincluster.unbind(delete_history=False)
    assert skincluster.exists() is False

    joint_names_delete = _create_joint_chain("unbind_delete")
    mesh_data_delete = _create_mesh("unbind_delete")
    skincluster_delete = SkinCluster.create(
        geometry=mesh_data_delete["transform"],
        influences=joint_names_delete,
        name="unbind_delete_skin",
    )

    skincluster_delete.unbind(delete_history=True)
    assert skincluster_delete.exists() is False


def test_empty_skincluster_errors():
    empty_skin = cmds.createNode("skinCluster", name="empty_skincluster")
    skincluster = SkinCluster(empty_skin)

    assert skincluster.vertex_count == 0
    with pytest.raises(RuntimeError):
        skincluster._get_geometry_dag_and_components()

    with pytest.raises(RuntimeError):
        skincluster.get_vertex_weights([0])

    with pytest.raises(RuntimeError):
        skincluster.set_vertex_weights([0], [1.0])
