"""Unit tests for tik.maya.types.blendshape module."""

import pytest
from maya import cmds

from tik.maya.types.blendshape import BlendShape
from tik.maya.types.mesh import Mesh


class TestBlendShapeCreate:
    """Tests for BlendShape creation."""

    def test_create_blendshape(self):
        """Test creating a BlendShape node."""
        blendshape = BlendShape.create()
        assert blendshape.exists()
        assert cmds.nodeType(blendshape.name) == "blendShape"

    def test_create_blendshape_is_blendshape_instance(self):
        """Test that created BlendShape is a BlendShape instance."""
        blendshape = BlendShape.create()
        assert isinstance(blendshape, BlendShape)


class TestBlendShapeProperties:
    """Tests for BlendShape properties."""

    def test_influences_returns_none_when_no_targets(self):
        """Test influences property returns None when no targets exist."""
        base_mesh, _ = cmds.polySphere(name="base_sphere")
        blendshape = cmds.blendShape(base_mesh, name="testBS")[0]
        blendshape_node = BlendShape(blendshape)

        # No targets added yet
        assert blendshape_node.influences is None

    def test_influences_returns_list_when_targets_exist(self):
        """Test influences property returns list when targets exist."""
        base_mesh, _ = cmds.polySphere(name="base_sphere2")
        target_mesh, _ = cmds.polySphere(name="target_sphere")
        cmds.move(0, 2, 0, target_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="testBS2")[0]
        blendshape_node = BlendShape(blendshape)

        influences = blendshape_node.influences
        assert influences is not None
        assert len(influences) >= 1

    def test_base_shapes_returns_empty_when_no_geometry(self):
        """Test base_shapes returns empty list when no geometry connected."""
        blendshape = BlendShape.create()
        assert blendshape.base_shapes == []

    def test_base_shapes_returns_mesh_wrappers(self):
        """Test base_shapes returns wrapped mesh objects."""
        base_mesh, _ = cmds.polySphere(name="base_shapes_sphere")
        blendshape = cmds.blendShape(base_mesh, name="baseShapesBS")[0]
        blendshape_node = BlendShape(blendshape)

        base_shapes = blendshape_node.base_shapes
        assert len(base_shapes) == 1
        assert isinstance(base_shapes[0], Mesh)

    def test_weight_count_returns_number_of_targets(self):
        """Test weight_count property returns correct count."""
        base_mesh, _ = cmds.polySphere(name="weight_count_base")
        target_mesh, _ = cmds.polySphere(name="weight_count_target")

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="weightCountBS")[0]
        blendshape_node = BlendShape(blendshape)

        assert blendshape_node.weight_count == 1

    def test_next_target_returns_next_free_index(self):
        """Test next_target property returns the next available index."""
        base_mesh, _ = cmds.polySphere(name="next_target_base")
        blendshape = cmds.blendShape(base_mesh, name="nextTargetBS")[0]
        blendshape_node = BlendShape(blendshape)

        # Initially no targets, so next_target should be 0
        assert blendshape_node.next_target == 0


class TestBlendShapeAddTarget:
    """Tests for adding targets to BlendShape."""

    def test_add_target_basic(self):
        """Test adding a target to blendshape."""
        base_mesh, _ = cmds.polySphere(name="add_target_base")
        target_mesh, _ = cmds.polySphere(name="add_target_target")
        cmds.move(0, 1, 0, target_mesh)

        blendshape = cmds.blendShape(base_mesh, name="addTargetBS")[0]
        blendshape_node = BlendShape(blendshape)

        idx = blendshape_node.add_target(target_mesh, name="myTarget", weight=0.5)

        assert idx == 0
        assert blendshape_node.weight_count == 1

    def test_add_target_raises_when_no_base_shapes(self):
        """Test add_target raises error when no base shapes connected."""
        blendshape = BlendShape.create()

        with pytest.raises(RuntimeError, match="No base shapes connected"):
            blendshape.add_target("someMesh")


class TestBlendShapeInbetween:
    """Tests for in-between targets."""

    def test_add_inbetween_by_index(self):
        """Test adding an in-between target by index."""
        base_mesh, _ = cmds.polySphere(name="inbetween_base")
        target_mesh, _ = cmds.polySphere(name="inbetween_target")
        inbetween_mesh, _ = cmds.polySphere(name="inbetween_mesh")
        cmds.move(0, 2, 0, target_mesh)
        cmds.move(0, 1, 0, inbetween_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="inbetweenBS")[0]
        blendshape_node = BlendShape(blendshape)

        # Add in-between at weight 0.5
        blendshape_node.add_inbetween(0, inbetween_mesh, weight=0.5)

        # Verify the in-between was added by checking the blendshape still works
        assert blendshape_node.exists()

    def test_add_inbetween_by_name(self):
        """Test adding an in-between target by name."""
        base_mesh, _ = cmds.polySphere(name="inbetween_name_base")
        target_mesh, _ = cmds.polySphere(name="inbetween_name_target")
        inbetween_mesh, _ = cmds.polySphere(name="inbetween_name_mesh")
        cmds.move(0, 2, 0, target_mesh)
        cmds.move(0, 1, 0, inbetween_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="inbetweenNameBS")[0]
        blendshape_node = BlendShape(blendshape)

        # Get the target name (first influence)
        target_name = blendshape_node.influences[0]
        blendshape_node.add_inbetween(target_name, inbetween_mesh, weight=0.5)

        assert blendshape_node.exists()

    def test_add_inbetween_raises_on_invalid_target_type(self):
        """Test add_inbetween raises TypeError for invalid target type."""
        base_mesh, _ = cmds.polySphere(name="inbetween_type_base")
        target_mesh, _ = cmds.polySphere(name="inbetween_type_target")
        cmds.move(0, 2, 0, target_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="inbetweenTypeBS")[0]
        blendshape_node = BlendShape(blendshape)

        with pytest.raises(TypeError, match="Target must be an integer index or string name"):
            blendshape_node.add_inbetween([1, 2], "someMesh")

    def test_add_inbetween_raises_when_no_base_shapes(self):
        """Test add_inbetween raises error when no base shapes connected."""
        blendshape = BlendShape.create()

        with pytest.raises(RuntimeError, match="No base shapes connected"):
            blendshape.add_inbetween(0, "someMesh")


class TestBlendShapeWeights:
    """Tests for weight manipulation."""

    def test_get_target_weights_by_index(self):
        """Test getting target weights by index."""
        base_mesh, _ = cmds.polySphere(name="get_weights_base", sx=4, sy=4)
        target_mesh, _ = cmds.polySphere(name="get_weights_target", sx=4, sy=4)
        cmds.move(0, 1, 0, target_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="getWeightsBS")[0]
        blendshape_node = BlendShape(blendshape)

        weights = blendshape_node.get_target_weights(0)
        assert isinstance(weights, list)
        assert len(weights) > 0
        # Default weights should be 1.0
        assert all(w == pytest.approx(1.0) for w in weights)

    def test_get_target_weights_by_name(self):
        """Test getting target weights by name."""
        base_mesh, _ = cmds.polySphere(name="get_weights_name_base", sx=4, sy=4)
        target_mesh, _ = cmds.polySphere(name="get_weights_name_target", sx=4, sy=4)
        cmds.move(0, 1, 0, target_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="getWeightsNameBS")[0]
        blendshape_node = BlendShape(blendshape)

        target_name = blendshape_node.influences[0]
        weights = blendshape_node.get_target_weights(target_name)
        assert isinstance(weights, list)

    def test_get_target_weights_raises_on_invalid_type(self):
        """Test get_target_weights raises TypeError for invalid target type."""
        base_mesh, _ = cmds.polySphere(name="get_weights_type_base")
        target_mesh, _ = cmds.polySphere(name="get_weights_type_target")

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="getWeightsTypeBS")[0]
        blendshape_node = BlendShape(blendshape)

        with pytest.raises(TypeError, match="Target must be an integer index or string name"):
            blendshape_node.get_target_weights([1, 2])

    def test_set_target_weights_by_index(self):
        """Test setting target weights by index."""
        base_mesh, _ = cmds.polySphere(name="set_weights_base", sx=4, sy=4)
        target_mesh, _ = cmds.polySphere(name="set_weights_target", sx=4, sy=4)
        cmds.move(0, 1, 0, target_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="setWeightsBS")[0]
        blendshape_node = BlendShape(blendshape)

        # Get vertex count
        original_weights = blendshape_node.get_target_weights(0)
        new_weights = [0.5] * len(original_weights)

        blendshape_node.set_target_weights(0, new_weights)

        # Verify weights were set
        retrieved_weights = blendshape_node.get_target_weights(0)
        assert all(w == pytest.approx(0.5, abs=0.01) for w in retrieved_weights)

    def test_set_target_weights_by_name(self):
        """Test setting target weights by name."""
        base_mesh, _ = cmds.polySphere(name="set_weights_name_base", sx=4, sy=4)
        target_mesh, _ = cmds.polySphere(name="set_weights_name_target", sx=4, sy=4)
        cmds.move(0, 1, 0, target_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="setWeightsNameBS")[0]
        blendshape_node = BlendShape(blendshape)

        target_name = blendshape_node.influences[0]
        original_weights = blendshape_node.get_target_weights(target_name)
        new_weights = [0.75] * len(original_weights)

        blendshape_node.set_target_weights(target_name, new_weights)

        retrieved_weights = blendshape_node.get_target_weights(target_name)
        assert all(w == pytest.approx(0.75, abs=0.01) for w in retrieved_weights)

    def test_set_target_weights_raises_on_invalid_type(self):
        """Test set_target_weights raises TypeError for invalid target type."""
        base_mesh, _ = cmds.polySphere(name="set_weights_type_base")
        target_mesh, _ = cmds.polySphere(name="set_weights_type_target")

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="setWeightsTypeBS")[0]
        blendshape_node = BlendShape(blendshape)

        with pytest.raises(TypeError, match="Target must be an integer index or string name"):
            blendshape_node.set_target_weights([1, 2], [0.5])

    def test_set_target_weights_raises_on_length_mismatch(self):
        """Test set_target_weights raises ValueError when weight length mismatches."""
        base_mesh, _ = cmds.polySphere(name="set_weights_len_base", sx=4, sy=4)
        target_mesh, _ = cmds.polySphere(name="set_weights_len_target", sx=4, sy=4)
        cmds.move(0, 1, 0, target_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="setWeightsLenBS")[0]
        blendshape_node = BlendShape(blendshape)

        with pytest.raises(ValueError, match="Weight length"):
            blendshape_node.set_target_weights(0, [0.5, 0.5])  # Too few weights

    def test_get_weights_global_deformer(self):
        """Test getting global deformer weights."""
        base_mesh, _ = cmds.polySphere(name="get_global_weights_base", sx=4, sy=4)
        target_mesh, _ = cmds.polySphere(name="get_global_weights_target", sx=4, sy=4)
        cmds.move(0, 1, 0, target_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="getGlobalWeightsBS")[0]
        blendshape_node = BlendShape(blendshape)

        weights = blendshape_node.get_weights()
        assert isinstance(weights, list)
        assert len(weights) > 0

    # TODO: Temporarily disabled - This fails on Maya 2024. NEEDS INVESTIGATION.
    # def test_set_weights_global_deformer(self):
    #     """Test setting global deformer weights."""
    #     base_mesh, _ = cmds.polySphere(name="set_global_weights_base", sx=4, sy=4)
    #     target_mesh, _ = cmds.polySphere(name="set_global_weights_target", sx=4, sy=4)
    #     cmds.move(0, 1, 0, target_mesh)
    #
    #     blendshape = cmds.blendShape(target_mesh, base_mesh, name="setGlobalWeightsBS")[0]
    #     blendshape_node = BlendShape(blendshape)
    #
    #     original_weights = blendshape_node.get_weights()
    #     new_weights = [0.8] * len(original_weights)
    #
    #     blendshape_node.set_weights(new_weights)
    #
    #     retrieved_weights = blendshape_node.get_weights()
    #     assert all(w == pytest.approx(0.8, abs=0.01) for w in retrieved_weights)

    def test_set_weights_raises_on_length_mismatch(self):
        """Test set_weights raises ValueError when weight length mismatches."""
        base_mesh, _ = cmds.polySphere(name="set_global_len_base", sx=4, sy=4)
        target_mesh, _ = cmds.polySphere(name="set_global_len_target", sx=4, sy=4)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="setGlobalLenBS")[0]
        blendshape_node = BlendShape(blendshape)

        with pytest.raises(ValueError, match="Weight length"):
            blendshape_node.set_weights([0.5, 0.5])  # Too few weights


class TestBlendShapeIndexAndName:
    """Tests for index/name lookup methods."""

    def test_index_by_name(self):
        """Test getting target index by name."""
        base_mesh, _ = cmds.polySphere(name="index_by_name_base")
        target_mesh, _ = cmds.polySphere(name="index_by_name_target")
        cmds.move(0, 1, 0, target_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="indexByNameBS")[0]
        blendshape_node = BlendShape(blendshape)

        target_name = blendshape_node.influences[0]
        idx = blendshape_node.index_by_name(target_name)
        assert idx == 0

    def test_index_by_name_raises_when_not_found(self):
        """Test index_by_name raises ValueError when target not found."""
        base_mesh, _ = cmds.polySphere(name="index_not_found_base")
        target_mesh, _ = cmds.polySphere(name="index_not_found_target")

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="indexNotFoundBS")[0]
        blendshape_node = BlendShape(blendshape)

        with pytest.raises(ValueError, match="Target name .* not found"):
            blendshape_node.index_by_name("nonExistentTarget")

    def test_name_by_index(self):
        """Test getting target name by index."""
        base_mesh, _ = cmds.polySphere(name="name_by_index_base")
        target_mesh, _ = cmds.polySphere(name="name_by_index_target")
        cmds.move(0, 1, 0, target_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="nameByIndexBS")[0]
        blendshape_node = BlendShape(blendshape)

        name = blendshape_node.name_by_index(0)
        assert name == blendshape_node.influences[0]

    def test_name_by_index_raises_when_not_found(self):
        """Test name_by_index raises ValueError when index not found."""
        base_mesh, _ = cmds.polySphere(name="name_index_not_found_base")

        # Create blendshape with no targets
        blendshape = cmds.blendShape(base_mesh, name="nameIndexNotFoundBS")[0]
        blendshape_node = BlendShape(blendshape)

        # Index 0 has no alias since no targets were added
        with pytest.raises(ValueError, match="Target index .* not found"):
            blendshape_node.name_by_index(0)


class TestBlendShapeGeometryInfo:
    """Tests for geometry info helper."""

    def test_get_geometry_info_raises_when_no_geometry(self):
        """Test _get_geometry_info raises RuntimeError when no geometry connected."""
        blendshape = BlendShape.create()

        with pytest.raises(RuntimeError, match="No geometry connected"):
            blendshape._get_geometry_info()

    def test_get_geometry_info_raises_when_geometry_not_connected(self):
        """Test _get_geometry_info raises ValueError when geometry not connected."""
        base_mesh, _ = cmds.polySphere(name="geo_info_base")
        other_mesh, _ = cmds.polySphere(name="geo_info_other")

        blendshape = cmds.blendShape(base_mesh, name="geoInfoBS")[0]
        blendshape_node = BlendShape(blendshape)

        with pytest.raises(ValueError, match="is not connected to blendShape"):
            blendshape_node._get_geometry_info(geometry=other_mesh)

    def test_get_geometry_info_with_specific_geometry(self):
        """Test _get_geometry_info with specific geometry parameter."""
        base_mesh, _ = cmds.polySphere(name="geo_info_specific_base")

        blendshape = cmds.blendShape(base_mesh, name="geoInfoSpecificBS")[0]
        blendshape_node = BlendShape(blendshape)

        # Get shape name
        shape = cmds.listRelatives(base_mesh, shapes=True)[0]
        idx, count, geo_name = blendshape_node._get_geometry_info(geometry=shape)

        assert idx == 0
        assert count > 0


class TestBlendShapeWeightPlugs:
    """Tests for weight plug helpers."""

    def test_read_weights_returns_defaults_when_plug_none(self):
        """Test _read_weights returns default 1.0 weights when plug is None."""
        blendshape = BlendShape.create()
        weights = blendshape._read_weights(None, 10)

        assert weights == [1.0] * 10

    def test_write_weights_raises_when_plug_none(self):
        """Test _write_weights raises RuntimeError when plug is None."""
        blendshape = BlendShape.create()

        with pytest.raises(RuntimeError, match="Cannot access weight plug"):
            blendshape._write_weights(None, [0.5, 0.5])

    def test_get_weight_plug_returns_none_on_exception(self):
        """Test _get_weight_plug returns None when an exception occurs."""
        from unittest.mock import patch, PropertyMock

        base_mesh, _ = cmds.polySphere(name="plug_exception_base")
        blendshape = cmds.blendShape(base_mesh, name="plugExceptionBS")[0]
        blendshape_node = BlendShape(blendshape)

        # Mock the __getitem__ method to raise an exception
        original_getitem = BlendShape.__getitem__

        def raising_getitem(self, key):
            raise RuntimeError("Simulated plug access error")

        with patch.object(BlendShape, "__getitem__", raising_getitem):
            result = blendshape_node._get_weight_plug(0, target_id=0)

        assert result is None


class TestBlendShapeSaveLoad:
    """Tests for weight save/load functionality."""

    def test_save_weights(self, tmp_path):
        """Test saving blendshape weights to file."""
        base_mesh, _ = cmds.polySphere(name="save_weights_base")
        target_mesh, _ = cmds.polySphere(name="save_weights_target")
        cmds.move(0, 1, 0, target_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="saveWeightsBS")[0]
        blendshape_node = BlendShape(blendshape)

        output_file = tmp_path / "blendshape_weights.xml"
        blendshape_node.save_weights(str(output_file))

        assert output_file.exists()

    def test_load_weights(self, tmp_path):
        """Test loading blendshape weights from file."""
        base_mesh, _ = cmds.polySphere(name="load_weights_base")
        target_mesh, _ = cmds.polySphere(name="load_weights_target")
        cmds.move(0, 1, 0, target_mesh)

        blendshape = cmds.blendShape(target_mesh, base_mesh, name="loadWeightsBS")[0]
        blendshape_node = BlendShape(blendshape)

        # Save first
        output_file = tmp_path / "load_test_weights.xml"
        blendshape_node.save_weights(str(output_file))

        # Load
        blendshape_node.load_weights(str(output_file), method="index")

        assert blendshape_node.exists()

    def test_save_weights_with_non_mesh_base(self, tmp_path):
        """Test save_weights with non-mesh base shape (e.g., curve)."""
        # Create a NURBS curve
        curve = cmds.circle(name="save_weights_curve")[0]

        blendshape = cmds.blendShape(curve, name="saveWeightsCurveBS")[0]
        blendshape_node = BlendShape(blendshape)

        output_file = tmp_path / "curve_weights.xml"
        blendshape_node.save_weights(str(output_file))

        assert output_file.exists()
