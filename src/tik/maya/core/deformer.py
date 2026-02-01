"""Deformer is not an actual maya node representation. It is a base class for deformers like SkinCluster, BlendShape, etc.

The Deformer class itself is not a falloff targer for any nodes.
However, it is not an abstract class either. If wanted, deformer classes can be created directly from it.
"""


from __future__ import annotations

import tempfile

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from maya import cmds
from maya.api import OpenMaya
from tik.core import jsonio
from ..core.apicommon import create_node_with_dg_modifier

from .node import Node

class Deformer(Node):
    """Base class for all deformer nodes."""

    @classmethod
    def create(cls, deformer_type: str, **kwargs) -> Deformer:
        """Create a new deformer node of the specified type.

        Args:
            deformer_type (str): The type of deformer to create (e.g., 'skinCluster', 'blendShape').
            **kwargs: Additional keyword arguments to pass to the Maya command.

        Returns:
            Deformer: An instance of the created deformer node.
        """
        deformer_node = create_node_with_dg_modifier(deformer_type, **kwargs)
        return cls(deformer_node)

    def __split_path(self, file_path, validate=False):
        """Validate and split a file path into directory and filename."""
        if not isinstance(file_path, Path):
            file_path = Path(file_path)
        if validate:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        file_name = file_path.name
        file_dir = file_path.parent.as_posix()
        return file_dir, file_name

    def _save_deformer_weights(self, file_path: str | Path, **kwargs) -> None:
        """Save the deformer weights to a file.

        Args:
            file_path (str | Path): The path to the file where weights will be saved.
        """
        file_dir, file_name = self.__split_path(file_path, validate=True)

        cmds.deformerWeights(
            file_name, export=True, deformer=self.name, path=file_dir,
            **kwargs
        )
    def _load_deformer_weights(self, file_path: str | Path, method: str = "index", **kwargs) -> None:
        """Load deformer weights from a file.

        Args:
            file_path (str | Path): The path to the file from which weights will be loaded.
        """
        file_dir, file_name = self.__split_path(file_path, validate=False)

        cmds.deformerWeights(
            file_name,
            path=file_dir,
            im=True,
            deformer=self.name,
            method=method,
            **kwargs,
        )

    def create_weights_object(self):
        """Create the weights object with the most secure but least efficient way."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "temp_weights.json"
            self._save_deformer_weights(temp_path, format="json")
            weights = Weights.load_json(temp_path)
        return weights

@dataclass
class HeaderInfo:
    """Metadata for serialized deformer weight files."""

    file_name: Optional[str] = None
    world_matrix: Optional[List[float]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "HeaderInfo":
        """Create header info from a dictionary."""
        file_name = data.get("fileName") if data else None
        world_matrix = data.get("worldMatrix") if data else None
        return cls(file_name=file_name, world_matrix=world_matrix)

    def to_dict(self) -> Dict[str, object]:
        """Serialize header info to a dictionary."""
        data: Dict[str, object] = {}
        if self.file_name is not None:
            data["fileName"] = self.file_name
        if self.world_matrix is not None:
            data["worldMatrix"] = list(self.world_matrix)
        return data


@dataclass
class ShapeInfo:
    """Geometry metadata referenced by weight layers."""

    name: str
    group: int
    stride: int
    size: int
    max_index: int
    points: Dict[int, List[float]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "ShapeInfo":
        """Create ShapeInfo from a dictionary."""
        points_dict: Dict[int, List[float]] = {}
        for point_entry in data.get("points", []) or []:
            point_index = int(point_entry["index"])
            point_value = list(point_entry["value"])
            points_dict[point_index] = point_value
        return cls(
            name=str(data["name"]),
            group=int(data["group"]),
            stride=int(data["stride"]),
            size=int(data["size"]),
            max_index=int(data["max"]),
            points=points_dict,
        )

    def to_dict(self) -> Dict[str, object]:
        """Serialize ShapeInfo to a dictionary."""
        point_entries = [
            {"index": point_index, "value": self.points[point_index]}
            for point_index in sorted(self.points)
        ]
        return {
            "name": self.name,
            "group": self.group,
            "stride": self.stride,
            "size": self.size,
            "max": self.max_index,
            "points": point_entries,
        }


@dataclass
class WeightLayer:
    """Sparse weights for a single influence and shape."""

    shape: str
    layer: int
    default_value: float
    points: Dict[int, float] = field(default_factory=dict)
    size: Optional[int] = None
    max_index: Optional[int] = None
    influence: Optional[str] = None
    deformer: Optional[str] = None
    is_base: bool = False

    @classmethod
    def from_dict(
        cls, data: Dict[str, object], base_layer_names: Iterable[str]
    ) -> "WeightLayer":
        """Create a WeightLayer from a dictionary."""
        points_dict: Dict[int, float] = {}
        for point_entry in data.get("points", []) or []:
            point_index = int(point_entry["index"])
            point_value = float(point_entry["value"])
            points_dict[point_index] = point_value

        influence = data.get("source")
        is_base = influence in set(base_layer_names)

        return cls(
            shape=str(data["shape"]),
            layer=int(data.get("layer", 0)),
            default_value=float(data.get("defaultValue", 0.0)),
            points=points_dict,
            size=int(data.get("size")) if data.get("size") is not None else None,
            max_index=int(data.get("max")) if data.get("max") is not None else None,
            influence=str(influence) if influence is not None else None,
            deformer=str(data.get("deformer")) if data.get("deformer") else None,
            is_base=is_base,
        )

    def to_dict(self, base_layer_name: Optional[str] = None) -> Dict[str, object]:
        """Serialize WeightLayer to a dictionary."""
        source_name = self.influence
        if source_name is None and self.is_base and base_layer_name:
            source_name = base_layer_name

        point_entries = [
            {"index": point_index, "value": self.points[point_index]}
            for point_index in sorted(self.points)
        ]

        data: Dict[str, object] = {
            "shape": self.shape,
            "layer": self.layer,
            "defaultValue": self.default_value,
            "points": point_entries,
        }
        if self.deformer is not None:
            data["deformer"] = self.deformer
        if source_name is not None:
            data["source"] = source_name
        if self.size is not None:
            data["size"] = self.size
        if self.max_index is not None:
            data["max"] = self.max_index
        return data

    def dense_weights(self, total_count: int) -> List[float]:
        """Return a dense weight list using the default value as a fill."""
        weights = [float(self.default_value)] * total_count
        for point_index, point_value in self.points.items():
            if 0 <= point_index < total_count:
                weights[point_index] = float(point_value)
        return weights


class Weights:
    """Deformer-agnostic container for sparse or dense weights.

    The internal canonical structure is a list of WeightLayer entries, each with a
    sparse point map and a default value. Shapes store optional geometry metadata
    for reconstructing dense arrays.
    """

    def __init__(
        self,
        shapes: Optional[Iterable[ShapeInfo]] = None,
        layers: Optional[Iterable[WeightLayer]] = None,
        header: Optional[HeaderInfo] = None,
        base_layer_names: Optional[Iterable[str]] = None,
    ) -> None:
        self._header = header or HeaderInfo()
        shape_list = list(shapes or [])
        self._shapes = {shape_info.name: shape_info for shape_info in shape_list}
        self._shape_order = [shape_info.name for shape_info in shape_list]
        self._layers = list(layers or [])
        self._base_layer_names = list(base_layer_names or ["baseLayer"])

    # === Properties ===

    @property
    def header(self) -> HeaderInfo:
        """Header metadata for serialized data."""
        return self._header

    @property
    def shapes(self) -> List[ShapeInfo]:
        """Ordered list of shapes."""
        return [self._shapes[name] for name in self._shape_order]

    @property
    def layers(self) -> List[WeightLayer]:
        """List of weight layers."""
        return list(self._layers)

    @property
    def base_layer_names(self) -> List[str]:
        """Names used to tag base weight layers."""
        return list(self._base_layer_names)

    @property
    def influence_names(self) -> List[str]:
        """Unique influence names excluding base layers."""
        names = {
            layer.influence
            for layer in self._layers
            if layer.influence and not layer.is_base
        }
        return sorted(names)

    # === Public Methods ===

    def add_shape(self, shape_info: ShapeInfo) -> None:
        """Add or replace shape metadata."""
        if shape_info.name not in self._shapes:
            self._shape_order.append(shape_info.name)
        self._shapes[shape_info.name] = shape_info

    def add_layer(self, layer: WeightLayer) -> None:
        """Append a weight layer to the container."""
        self._layers.append(layer)

    def shape(self, name: str) -> Optional[ShapeInfo]:
        """Return ShapeInfo by name if present."""
        return self._shapes.get(name)

    def layers_for_shape(self, shape_name: str) -> List[WeightLayer]:
        """Return all layers associated with a shape."""
        return [layer for layer in self._layers if layer.shape == shape_name]

    def get_layer(
        self,
        shape_name: str,
        influence: Optional[str] = None,
        layer_index: int = 0,
        is_base: Optional[bool] = None,
    ) -> Optional[WeightLayer]:
        """Find a specific layer by shape, influence, and layer index."""
        for layer in self._layers:
            if layer.shape != shape_name:
                continue
            if layer.layer != layer_index:
                continue
            if influence is not None and layer.influence != influence:
                continue
            if is_base is not None and layer.is_base != is_base:
                continue
            return layer
        return None

    def dense_influence_weights(
        self,
        shape_name: str,
        influence: str,
        total_count: Optional[int] = None,
        layer_index: int = 0,
    ) -> List[float]:
        """Return dense weights for a specific influence and shape."""
        layer = self.get_layer(
            shape_name=shape_name, influence=influence, layer_index=layer_index
        )
        if layer is None:
            raise ValueError(f"No weights found for influence '{influence}'.")

        resolved_total = total_count
        if resolved_total is None:
            shape_info = self._shapes.get(shape_name)
            if shape_info:
                resolved_total = shape_info.size
        if resolved_total is None:
            raise ValueError("total_count is required when shape size is unknown.")

        return layer.dense_weights(resolved_total)

    def dense_base_weights(
        self,
        shape_name: str,
        total_count: Optional[int] = None,
        layer_index: int = 0,
    ) -> List[float]:
        """Return dense base weights for a specific shape."""
        layer = self.get_layer(
            shape_name=shape_name, influence=None, layer_index=layer_index, is_base=True
        )
        if layer is None:
            raise ValueError("No base weights found for the specified shape.")

        resolved_total = total_count
        if resolved_total is None:
            shape_info = self._shapes.get(shape_name)
            if shape_info:
                resolved_total = shape_info.size
        if resolved_total is None:
            raise ValueError("total_count is required when shape size is unknown.")

        return layer.dense_weights(resolved_total)

    # === Serialization ===

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "Weights":
        """Create Weights from a dictionary.

        Supports input with or without the top-level 'deformerWeight' key.
        """
        payload = data.get("deformerWeight") if "deformerWeight" in data else data
        header = HeaderInfo.from_dict(payload.get("headerInfo") or {})

        shapes = [
            ShapeInfo.from_dict(shape_entry)
            for shape_entry in payload.get("shapes", []) or []
        ]

        base_layer_names = ["baseLayer"]
        layers = [
            WeightLayer.from_dict(layer_entry, base_layer_names)
            for layer_entry in payload.get("weights", []) or []
        ]

        return cls(
            shapes=shapes,
            layers=layers,
            header=header,
            base_layer_names=base_layer_names,
        )

    def to_dict(self) -> Dict[str, object]:
        """Serialize Weights to a dictionary matching Maya's deformerWeights format."""
        header_info = self._header.to_dict()
        shape_entries = [shape_info.to_dict() for shape_info in self.shapes]
        layer_entries = [
            layer.to_dict(base_layer_name=self._base_layer_names[0])
            for layer in self._layers
        ]

        data: Dict[str, object] = {
            "headerInfo": header_info,
            "shapes": shape_entries,
            "weights": layer_entries,
        }
        return {"deformerWeight": data}

    @classmethod
    def from_json(cls, content: str) -> "Weights":
        """Parse Weights from JSON text."""
        data = jsonio.loads(content)
        return cls.from_dict(data)

    def to_json(self, indent: int = 4) -> str:
        """Serialize Weights to JSON text."""
        return jsonio.dumps(self.to_dict(), indent=indent, sort_keys=False)

    @classmethod
    def load_json(cls, file_path: str | Path) -> "Weights":
        """Load Weights from a JSON file path."""
        data = jsonio.load(file_path)
        return cls.from_dict(data)

    def save_json(self, file_path: str | Path, indent: int = 4) -> None:
        """Write Weights to a JSON file path."""
        jsonio.save(file_path, self.to_dict(), indent=indent, sort_keys=False)

    def to_m_array(self) -> OpenMaya.MDoubleArray:
        """Convert the Weights to an MDoubleArray compatible with MFnSkinCluster."""
        json_data = self.to_dict()
        return self.__convert_to_m_array(json_data)

    @staticmethod
    def __convert_to_m_array(json_data):
        """Converts the json data weights compatible to be applied with MFnSkincluster"""
        vertex_count = json_data["deformerWeight"]["shapes"][0]["size"]
        weights_data = json_data["deformerWeight"]["weights"]
        m_array = OpenMaya.MDoubleArray()
        # first create a base
        for vtx_id in range(vertex_count * len(weights_data)):
            m_array.append(0.0)
        # if there are 3 influences (jnt1, jnt2, jnt3):
        #  Vertex ID         vtx0   vtx1   vtx2   .....
        #  M Array           | | |  | | |  | | |  .....
        #  Influence (Layer) 1 2 3  1 2 3  1 2 3  .....
        inf_count = len(weights_data)
        for inf_data in weights_data:
            layer = inf_data.get("layer")
            for point_data in inf_data["points"]:
                data_index = (point_data["index"] * inf_count) + layer
                m_array[data_index] = point_data["value"]
        return m_array
