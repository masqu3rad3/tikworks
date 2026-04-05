"""Unit tests for tik.maya.core.deformer."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest
from maya import cmds
from maya.api import OpenMaya

from tik.maya.core.deformer import (
    Deformer,
    DeformerWeights,
    HeaderInfo,
    ShapeInfo,
    WeightLayer,
    WeightsIO,
)
from tik.maya.types.blendshape import BlendShape


def _create_blendshape_with_target(prefix: str) -> BlendShape:
    base_mesh, _base_shape = cmds.polySphere(name=f"{prefix}_base", sx=4, sy=4)
    target_mesh, _target_shape = cmds.polySphere(name=f"{prefix}_target", sx=4, sy=4)
    cmds.move(0, 1, 0, target_mesh)

    blendshape_name = cmds.blendShape(target_mesh, base_mesh, name=f"{prefix}_bs")[0]
    return BlendShape(blendshape_name)


def _build_weights_io(
    shape_name: str, vertex_count: int, influence_names: List[str]
) -> WeightsIO:
    shape_info = ShapeInfo(
        name=shape_name,
        group=0,
        stride=3,
        size=vertex_count,
        max_index=vertex_count - 1,
        points={0: [0.0, 0.0, 0.0]},
    )

    layers = []
    for layer_index, influence_name in enumerate(influence_names):
        points = {
            vertex_index: 1.0 if layer_index == 0 else 0.0
            for vertex_index in range(vertex_count)
        }
        layers.append(
            WeightLayer(
                shape=shape_name,
                layer=layer_index,
                default_value=0.0,
                points=points,
                influence=influence_name,
            )
        )

    return WeightsIO(shapes=[shape_info], layers=layers)


def test_deformer_create_and_split_path(tmp_path: Path) -> None:
    deformer = Deformer.create("blendShape", name="deformer_create_bs")
    assert cmds.nodeType(deformer.name) == "blendShape"

    target_path = tmp_path / "weights" / "file.json"
    file_dir, file_name = deformer._split_path(target_path, validate=True)
    assert Path(file_dir).exists()
    assert file_name == "file.json"


def test_deformer_save_load_and_weights_object(tmp_path: Path) -> None:
    blendshape_node = _create_blendshape_with_target("deformer_save")

    export_path = tmp_path / "blendshape_weights.json"
    blendshape_node._save_deformer_weights(export_path, format="JSON", defaultValue=-1.0)
    assert export_path.exists()

    blendshape_node._load_deformer_weights(export_path, method="index", ignoreName=True)

    weights_object = blendshape_node.create_weights_object()
    assert isinstance(weights_object, WeightsIO)
    assert weights_object.shapes
    assert weights_object.layers


def test_deformerweights_mdouble_array_and_list() -> None:
    weights = DeformerWeights([0.25, 0.75], channel_count=2, element_count=1)
    weight_list = weights.to_list()
    assert weight_list == [0.25, 0.75]

    m_array = weights.to_m_double_array()
    assert isinstance(m_array, OpenMaya.MDoubleArray)
    assert len(m_array) == len(weights)


def test_weights_io_roundtrip_and_dense(tmp_path: Path) -> None:
    header = HeaderInfo(file_name="weights.json", world_matrix=[1.0] * 16)
    shape_info = ShapeInfo(
        name="mesh_shape",
        group=0,
        stride=3,
        size=4,
        max_index=3,
        points={1: [1.0, 2.0, 3.0]},
    )
    influence_layer = WeightLayer(
        shape="mesh_shape",
        layer=0,
        default_value=0.5,
        points={2: 0.25},
        influence="joint1",
    )
    base_layer = WeightLayer(
        shape="mesh_shape",
        layer=1,
        default_value=1.0,
        points={3: 0.0},
        influence=None,
        is_base=True,
    )

    weights_io = WeightsIO(
        shapes=[shape_info],
        layers=[influence_layer, base_layer],
        header=header,
        base_layer_names=["baseLayer"],
    )

    dense_influence = weights_io.dense_influence_weights("mesh_shape", "joint1", total_count=4)
    assert list(dense_influence) == pytest.approx([0.5, 0.5, 0.25, 0.5], abs=1e-6)

    dense_base = weights_io.dense_base_weights("mesh_shape", total_count=4, layer_index=1)
    assert list(dense_base) == pytest.approx([1.0, 1.0, 1.0, 0.0], abs=1e-6)

    dict_payload = weights_io.to_dict()
    assert "deformerWeight" in dict_payload

    from_wrapped = WeightsIO.from_dict(dict_payload)
    assert from_wrapped.header.file_name == "weights.json"

    from_unwrapped = WeightsIO.from_dict(dict_payload["deformerWeight"])
    assert from_unwrapped.shapes[0].name == "mesh_shape"

    json_text = weights_io.to_json(indent=2)
    from_json = WeightsIO.from_json(json_text)
    assert from_json.layers

    json_path = tmp_path / "weights.json"
    weights_io.save_json(json_path)
    from_file = WeightsIO.load_json(json_path)
    assert from_file.header.file_name == "weights.json"

    deformer_weights = weights_io.to_deformer_weights()
    assert deformer_weights.channel_count == 2
    assert deformer_weights.element_count == 4


def test_weightlayer_base_layer_serialization() -> None:
    base_layer_data = {
        "shape": "mesh_shape",
        "layer": 0,
        "defaultValue": 1.0,
        "points": [],
        "source": "baseLayer",
    }
    base_layer = WeightLayer.from_dict(base_layer_data, ["baseLayer"])
    assert base_layer.is_base is True

    serialized = base_layer.to_dict(base_layer_name="baseLayer")
    assert serialized["source"] == "baseLayer"


def test_weightlayer_full_serialization() -> None:
    layer = WeightLayer(
        shape="mesh",
        layer=0,
        default_value=0.5,
        points={0: 1.0},
        size=10,
        max_index=9,
        influence="joint1",
        deformer="skinCluster1",
        is_base=False
    )
    data = layer.to_dict()
    assert data["size"] == 10
    assert data["max"] == 9
    assert data["deformer"] == "skinCluster1"
    assert data["source"] == "joint1"

    reconstructed = WeightLayer.from_dict(data, [])
    assert reconstructed.size == 10
    assert reconstructed.max_index == 9
    assert reconstructed.deformer == "skinCluster1"


def test_weights_io_get_layer_filtering() -> None:
    shape = ShapeInfo(name="mesh", group=0, stride=1, size=1, max_index=0)
    layer1 = WeightLayer(shape="mesh", layer=0, default_value=0.0, influence="j1")
    layer2 = WeightLayer(shape="mesh", layer=0, default_value=0.0, influence="j2")
    base = WeightLayer(shape="mesh", layer=1, default_value=1.0, is_base=True)

    io = WeightsIO(shapes=[shape], layers=[layer1, layer2, base])

    assert io.get_layer("mesh", influence="j1") is layer1
    assert io.get_layer("mesh", influence="j2") is layer2
    assert io.get_layer("mesh", influence="missing") is None
    assert io.get_layer("mesh", is_base=True, layer_index=1) is base
    assert io.get_layer("mesh", is_base=False, influence="j1") is layer1
    assert io.get_layer("other", influence="j1") is None
    assert io.get_layer("mesh", layer_index=5) is None


def test_weights_io_dense_weights_unknown_size() -> None:
    # Shape with no size info
    layer = WeightLayer(shape="mesh", layer=0, default_value=0.0, influence="inf")
    # Base layer for checking dense_base_weights
    base_layer = WeightLayer(shape="mesh", layer=0, default_value=0.0, is_base=True)
    io = WeightsIO(shapes=[], layers=[layer, base_layer])

    with pytest.raises(ValueError, match="total_count is required"):
        io.dense_influence_weights("mesh", "inf")

    with pytest.raises(ValueError, match="total_count is required"):
        io.dense_base_weights("mesh")


def test_weights_io_to_m_array_and_influence_names() -> None:
    weights_io = _build_weights_io("mesh_transform", 4, ["joint1", "joint2"])

    m_array = weights_io.to_m_array()
    assert isinstance(m_array, OpenMaya.MDoubleArray)
    assert len(m_array) == 8

    assert weights_io.influence_names == ["joint1", "joint2"]


def test_weights_io_to_deformer_weights_errors() -> None:
    empty_weights = WeightsIO()
    with pytest.raises(ValueError, match="No shapes defined"):
        empty_weights.to_deformer_weights()

    shape_info = ShapeInfo(
        name="mesh_shape",
        group=0,
        stride=3,
        size=2,
        max_index=1,
        points={},
    )
    no_layers = WeightsIO(shapes=[shape_info], layers=[])
    with pytest.raises(ValueError, match="No weight layers"):
        no_layers.to_deformer_weights()

    weights_io = _build_weights_io("mesh_shape", 2, ["joint1"])
    with pytest.raises(ValueError, match="Shape 'missing' not found"):
        weights_io.to_deformer_weights(shape_name="missing")


def test_weights_io_missing_layers_errors() -> None:
    shape_info = ShapeInfo(
        name="mesh_shape",
        group=0,
        stride=3,
        size=2,
        max_index=1,
        points={},
    )
    weights_io = WeightsIO(shapes=[shape_info], layers=[])

    with pytest.raises(ValueError, match="No weights found"):
        weights_io.dense_influence_weights("mesh_shape", "joint1", total_count=2)

    with pytest.raises(ValueError, match="No base weights found"):
        weights_io.dense_base_weights("mesh_shape", total_count=2)


def test_weights_io_get_layer_multiple_shapes() -> None:
    shape1 = ShapeInfo(name="mesh1", group=0, stride=1, size=1, max_index=0)
    shape2 = ShapeInfo(name="mesh2", group=0, stride=1, size=1, max_index=0)
    layer1 = WeightLayer(shape="mesh1", layer=0, default_value=0.0)
    layer2 = WeightLayer(shape="mesh2", layer=0, default_value=0.0)

    io = WeightsIO(shapes=[shape1, shape2], layers=[layer1, layer2])

    assert io.get_layer("mesh1") is layer1
    assert io.get_layer("mesh2") is layer2


def test_weights_io_from_dict_flat() -> None:
    # Test loading from dict without "deformerWeight" wrapper key
    data = {
        "headerInfo": {},
        "shapes": [],
        "weights": []
    }
    io = WeightsIO.from_dict(data)
    assert isinstance(io, WeightsIO)
