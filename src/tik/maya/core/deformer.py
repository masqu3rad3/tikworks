# TODO: Make sure all get/set deformer weights go through DeformerWeights and WeightsIO

"""Deformer is not an actual maya node representation. It is a base class for deformers like SkinCluster, BlendShape, etc.

The Deformer class itself is not a falloff targer for any nodes.
However, it is not an abstract class either. If wanted, deformer classes can be created directly from it.
"""


from __future__ import annotations

import array
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

from maya import cmds
from maya.api import OpenMaya

from tik.core import jsonio
from .node import Node
from ..core.apicommon import create_node_with_dg_modifier


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
            self._save_deformer_weights(temp_path, format="JSON")
            weights = WeightsIO.load_json(temp_path)
        return weights


class DeformerWeights:
    """Container for deformer weights enabling arithmetic operations.

    This class wraps weight data and provides dunder methods for intuitive
    weight manipulation. It uses array.array('d') for memory efficiency and
    performance in bulk operations.

    Works with all deformer types: skinCluster, blendShape, deltaMush, etc.

    Attributes:
        weights: Array of weight values (flat array using array.array('d')).
        channel_count: Number of channels (influences for skin, targets for blendshape).
        element_count: Number of elements (vertices, CVs, etc.).
        channel_names: Optional list of channel names (joint names, target names).
    """

    def __init__(
        self,
        weights: Union[List[float], array.array],
        channel_count: int,
        element_count: int,
        channel_names: Optional[List[str]] = None,
    ):
        """Initialize DeformerWeights container.

        Args:
            weights: Weight values (flat array). Can be list or array.array.
            channel_count: Number of channels (influences/targets).
            element_count: Number of elements (vertices/CVs).
            channel_names: Optional list of channel names for reference.
        """

        self._weights = array.array("d", weights)
        self._channel_count = channel_count
        self._element_count = element_count
        self._channel_names = list(channel_names) if channel_names else []

    # === Properties ===

    @property
    def weights(self) -> array.array:
        """The raw weight array (array.array of doubles)."""
        return self._weights

    @property
    def channel_count(self) -> int:
        """Number of channels (influences for skin, targets for blendshape)."""
        return self._channel_count

    @property
    def element_count(self) -> int:
        """Number of elements (vertices, CVs, etc.)."""
        return self._element_count

    @property
    def channel_names(self) -> List[str]:
        """Names of channels if available."""
        return self._channel_names

    # === Public Methods ===

    def get_element_weights(self, element_index: int) -> List[float]:
        """Get weights for a single element across all channels.

        Args:
            element_index: The element index to query (e.g., vertex index).

        Returns:
            List of weights for each channel at the specified element.
        """
        if element_index < 0 or element_index >= self._element_count:
            raise IndexError(
                f"Element index {element_index} out of range [0, {self._element_count})"
            )
        start_idx = element_index * self._channel_count
        return list(self._weights[start_idx : start_idx + self._channel_count])

    def get_channel_weights(self, channel_index: int) -> List[float]:
        """Get weights for a single channel across all elements.

        Args:
            channel_index: The channel index to query (e.g., influence index).

        Returns:
            List of weights for each element at the specified channel.
        """
        if channel_index < 0 or channel_index >= self._channel_count:
            raise IndexError(
                f"Channel index {channel_index} out of range "
                f"[0, {self._channel_count})"
            )
        return [
            self._weights[elem_idx * self._channel_count + channel_index]
            for elem_idx in range(self._element_count)
        ]

    def copy(self) -> "DeformerWeights":
        """Create a deep copy of this DeformerWeights instance."""
        return DeformerWeights(
            array.array("d", self._weights),
            self._channel_count,
            self._element_count,
            list(self._channel_names),
        )

    def clamp(self, min_value: float = 0.0, max_value: float = 1.0) -> "DeformerWeights":
        """Clamp all weight values to the specified range.

        Args:
            min_value: Minimum weight value.
            max_value: Maximum weight value.

        Returns:
            Self for method chaining.
        """
        for idx in range(len(self._weights)):
            self._weights[idx] = max(min_value, min(max_value, self._weights[idx]))
        return self

    def normalize(self) -> "DeformerWeights":
        """Normalize weights so each element sums to 1.0.

        Returns:
            Self for method chaining.
        """
        for elem_idx in range(self._element_count):
            start_idx = elem_idx * self._channel_count
            end_idx = start_idx + self._channel_count
            total = sum(self._weights[start_idx:end_idx])
            if total > 0:
                for idx in range(start_idx, end_idx):
                    self._weights[idx] /= total
        return self

    def to_list(self) -> List[float]:
        """Convert weights to a standard Python list."""
        return list(self._weights)

    def to_m_double_array(self) -> OpenMaya.MDoubleArray:
        """Convert weights to an OpenMaya.MDoubleArray."""
        return OpenMaya.MDoubleArray(self._weights)

    # === Dunder Methods ===

    def __len__(self) -> int:
        """Return total number of weight values."""
        return len(self._weights)

    def __getitem__(self, index: int) -> float:
        """Get weight at index."""
        return self._weights[index]

    def __setitem__(self, index: int, value: float) -> None:
        """Set weight at index."""
        self._weights[index] = value

    def __iter__(self):
        """Iterate over weight values."""
        return iter(self._weights)

    def __add__(self, other: Union["DeformerWeights", float]) -> "DeformerWeights":
        """Add weights or scalar to this instance."""
        result = self.copy()
        if isinstance(other, DeformerWeights):
            if len(other) != len(self):
                raise ValueError("DeformerWeights dimensions must match for addition.")
            for idx in range(len(result._weights)):
                result._weights[idx] = self._weights[idx] + other._weights[idx]
        else:
            scalar = float(other)
            for idx in range(len(result._weights)):
                result._weights[idx] = self._weights[idx] + scalar
        return result

    def __radd__(self, other: float) -> "DeformerWeights":
        """Right-add for scalar values."""
        return self.__add__(other)

    def __sub__(self, other: Union["DeformerWeights", float]) -> "DeformerWeights":
        """Subtract weights or scalar from this instance."""
        result = self.copy()
        if isinstance(other, DeformerWeights):
            if len(other) != len(self):
                raise ValueError("DeformerWeights dimensions must match for subtraction.")
            for idx in range(len(result._weights)):
                result._weights[idx] = self._weights[idx] - other._weights[idx]
        else:
            scalar = float(other)
            for idx in range(len(result._weights)):
                result._weights[idx] = self._weights[idx] - scalar
        return result

    def __rsub__(self, other: float) -> "DeformerWeights":
        """Right-subtract for scalar values."""
        result = self.copy()
        scalar = float(other)
        for idx in range(len(result._weights)):
            result._weights[idx] = scalar - self._weights[idx]
        return result

    def __mul__(self, other: Union["DeformerWeights", float]) -> "DeformerWeights":
        """Multiply weights by another DeformerWeights or scalar."""
        result = self.copy()
        if isinstance(other, DeformerWeights):
            if len(other) != len(self):
                raise ValueError(
                    "DeformerWeights dimensions must match for multiplication."
                )
            for idx in range(len(result._weights)):
                result._weights[idx] = self._weights[idx] * other._weights[idx]
        else:
            scalar = float(other)
            for idx in range(len(result._weights)):
                result._weights[idx] = self._weights[idx] * scalar
        return result

    def __rmul__(self, other: float) -> "DeformerWeights":
        """Right-multiply for scalar values."""
        return self.__mul__(other)

    def __truediv__(self, other: Union["DeformerWeights", float]) -> "DeformerWeights":
        """Divide weights by another DeformerWeights or scalar."""
        result = self.copy()
        if isinstance(other, DeformerWeights):
            if len(other) != len(self):
                raise ValueError("DeformerWeights dimensions must match for division.")
            for idx in range(len(result._weights)):
                if other._weights[idx] != 0:
                    result._weights[idx] = self._weights[idx] / other._weights[idx]
                else:
                    result._weights[idx] = 0.0
        else:
            divisor = float(other)
            if divisor == 0:
                raise ZeroDivisionError("Cannot divide DeformerWeights by zero.")
            for idx in range(len(result._weights)):
                result._weights[idx] = self._weights[idx] / divisor
        return result

    def __neg__(self) -> "DeformerWeights":
        """Invert weights (1.0 - weight)."""
        result = self.copy()
        for idx in range(len(result._weights)):
            result._weights[idx] = 1.0 - self._weights[idx]
        return result

    def __eq__(self, other: "DeformerWeights") -> bool:
        """Check equality with another DeformerWeights."""
        if not isinstance(other, DeformerWeights):
            return False
        if len(self) != len(other):
            return False
        tolerance = 1e-6
        for idx in range(len(self._weights)):
            if abs(self._weights[idx] - other._weights[idx]) > tolerance:
                return False
        return True

    def __repr__(self) -> str:
        """Debug representation."""
        return (
            f"<DeformerWeights elements={self._element_count} "
            f"channels={self._channel_count}>"
        )


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

    def dense_weights(self, total_count: int) -> array.array:
        """Return a dense weight array using the default value as a fill."""
        weights = array.array("d", [float(self.default_value)] * total_count)
        for point_index, point_value in self.points.items():
            if 0 <= point_index < total_count:
                weights[point_index] = float(point_value)
        return weights


class WeightsIO:
    """Deformer-agnostic container for sparse or dense weights I/O.

    This class handles serialization/deserialization of deformer weights to/from
    JSON files compatible with Maya's deformerWeights command.

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
    ) -> array.array:
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
    ) -> array.array:
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
    def from_dict(cls, data: Dict[str, object]) -> "WeightsIO":
        """Create WeightsIO from a dictionary.

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
        """Serialize WeightsIO to a dictionary matching Maya's deformerWeights format."""
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
    def from_json(cls, content: str) -> "WeightsIO":
        """Parse WeightsIO from JSON text."""
        data = jsonio.loads(content)
        return cls.from_dict(data)

    def to_json(self, indent: int = 4) -> str:
        """Serialize WeightsIO to JSON text."""
        return jsonio.dumps(self.to_dict(), indent=indent, sort_keys=False)

    @classmethod
    def load_json(cls, file_path: str | Path) -> "WeightsIO":
        """Load WeightsIO from a JSON file path."""
        data = jsonio.load(file_path)
        return cls.from_dict(data)

    def save_json(self, file_path: str | Path, indent: int = 4) -> None:
        """Write WeightsIO to a JSON file path."""
        jsonio.save(file_path, self.to_dict(), indent=indent, sort_keys=False)

    def to_m_array(self) -> OpenMaya.MDoubleArray:
        """Convert the WeightsIO to an MDoubleArray compatible with MFnSkinCluster."""
        json_data = self.to_dict()
        return self.__convert_to_m_array(json_data)

    def to_deformer_weights(self, shape_name: Optional[str] = None) -> DeformerWeights:
        """Convert WeightsIO to a DeformerWeights object for math operations.

        Args:
            shape_name: Optional shape name. If not provided, uses the first shape.

        Returns:
            DeformerWeights instance with dense weight data.
        """
        if not self._shape_order:
            raise ValueError("No shapes defined in WeightsIO.")

        target_shape = shape_name or self._shape_order[0]
        shape_info = self._shapes.get(target_shape)
        if shape_info is None:
            raise ValueError(f"Shape '{target_shape}' not found.")

        layers = self.layers_for_shape(target_shape)
        if not layers:
            raise ValueError(f"No weight layers found for shape '{target_shape}'.")

        element_count = shape_info.size
        channel_count = len(layers)
        channel_names = [layer.influence or f"channel_{idx}" for idx, layer in enumerate(layers)]

        # Build flat weight array: [elem0_ch0, elem0_ch1, ..., elem1_ch0, elem1_ch1, ...]
        weights = array.array("d")
        for elem_idx in range(element_count):
            for layer in layers:
                weight_value = layer.points.get(elem_idx, layer.default_value)
                weights.append(float(weight_value))

        return DeformerWeights(
            weights=weights,
            channel_count=channel_count,
            element_count=element_count,
            channel_names=channel_names,
        )

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
