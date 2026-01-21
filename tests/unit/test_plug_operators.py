"""Unit tests for Plug mathematical and connection operators."""

import maya.cmds as cmds
import pytest

import tik.maya as tm


class TestPlugMathOperatorsSingle:
    """Tests for mathematical operators on single-value Plugs."""

    def test_add_plug_to_plug(self, new_scene):
        """Test adding two single-value plugs creates an addDL node."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"].value = 10.0
        node_b["tx"].value = 5.0

        result_plug = node_a["tx"] + node_b["tx"]

        # Verify an addDL node was created
        assert "addDL" in result_plug._node.type or "addDoubleLinear" in result_plug._node.type
        # Verify connections
        input1_conns = cmds.listConnections(
            f"{result_plug._node.name}.input1", plugs=True, source=True
        )
        input2_conns = cmds.listConnections(
            f"{result_plug._node.name}.input2", plugs=True, source=True
        )
        assert input1_conns is not None
        assert input2_conns is not None
        # Verify output
        assert result_plug.attr == "output"
        assert result_plug.value == 15.0

    def test_add_plug_to_numeric(self, new_scene):
        """Test adding a plug and numeric value."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["tx"].value = 10.0

        result_plug = node_a["tx"] + 8

        # Verify input2 is set to 8, not connected
        assert cmds.getAttr(f"{result_plug._node.name}.input2") == 8.0
        assert cmds.listConnections(
            f"{result_plug._node.name}.input2", source=True
        ) is None
        assert result_plug.value == 18.0

    def test_radd_numeric_to_plug(self, new_scene):
        """Test reversed addition (numeric + plug)."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["tx"].value = 10.0

        result_plug = 5 + node_a["tx"]

        assert result_plug.value == 15.0

    def test_sub_plug_from_plug(self, new_scene):
        """Test subtracting two plugs creates a subtract node."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"].value = 10.0
        node_b["tx"].value = 3.0

        result_plug = node_a["tx"] - node_b["tx"]

        # Verify a subtract node was created
        assert "subtract" in result_plug._node.type
        assert result_plug.value == 7.0

    def test_rsub_numeric_from_plug(self, new_scene):
        """Test reversed subtraction (numeric - plug)."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["tx"].value = 3.0

        result_plug = 10 - node_a["tx"]

        # For reversed: 10 - 3 = 7
        assert cmds.getAttr(f"{result_plug._node.name}.input1") == 10.0
        assert result_plug.value == 7.0

    def test_mul_plug_by_plug(self, new_scene):
        """Test multiplying two plugs creates a multDL node."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"].value = 4.0
        node_b["tx"].value = 3.0

        result_plug = node_a["tx"] * node_b["tx"]

        # Verify a multDL node was created
        assert "multDL" in result_plug._node.type or "multDoubleLinear" in result_plug._node.type
        assert result_plug.value == 12.0

    def test_mul_plug_by_numeric(self, new_scene):
        """Test multiplying a plug by a numeric value."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["tx"].value = 5.0

        result_plug = node_a["tx"] * 2.5

        assert result_plug.value == 12.5

    def test_rmul_numeric_by_plug(self, new_scene):
        """Test reversed multiplication (numeric * plug)."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["tx"].value = 4.0

        result_plug = 3 * node_a["tx"]

        assert result_plug.value == 12.0

    def test_truediv_plug_by_plug(self, new_scene):
        """Test dividing two plugs creates a divide node."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"].value = 10.0
        node_b["tx"].value = 2.0

        result_plug = node_a["tx"] / node_b["tx"]

        # Verify a divide node was created
        assert "divide" in result_plug._node.type
        assert result_plug.value == 5.0

    def test_truediv_plug_by_numeric(self, new_scene):
        """Test dividing a plug by a numeric value."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["tx"].value = 15.0

        result_plug = node_a["tx"] / 3

        assert result_plug.value == 5.0

    def test_rtruediv_numeric_by_plug(self, new_scene):
        """Test reversed division (numeric / plug)."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["tx"].value = 5.0

        result_plug = 20 / node_a["tx"]

        # For reversed: 20 / 5 = 4
        assert cmds.getAttr(f"{result_plug._node.name}.input1") == 20.0
        assert result_plug.value == 4.0

    def test_pow_plug_to_plug(self, new_scene):
        """Test raising a plug to a power using another plug."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"].value = 2.0
        node_b["tx"].value = 3.0

        result_plug = node_a["tx"] ** node_b["tx"]

        # Verify a power node was created
        assert "power" in result_plug._node.type
        assert result_plug.value == 8.0

    def test_pow_plug_to_numeric(self, new_scene):
        """Test raising a plug to a numeric power."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["tx"].value = 3.0

        result_plug = node_a["tx"] ** 2

        assert result_plug.value == 9.0

    def test_rpow_numeric_to_plug(self, new_scene):
        """Test reversed power (numeric ** plug)."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["tx"].value = 3.0

        result_plug = 2 ** node_a["tx"]

        # For reversed: 2 ** 3 = 8
        assert result_plug.value == 8.0

    def test_mod_plug_by_plug(self, new_scene):
        """Test modulo of two plugs."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"].value = 10.0
        node_b["tx"].value = 3.0

        result_plug = node_a["tx"] % node_b["tx"]

        # Verify a modulo node was created
        assert "modulo" in result_plug._node.type
        assert result_plug.value == 1.0

    def test_mod_plug_by_numeric(self, new_scene):
        """Test modulo of a plug by a numeric value."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["tx"].value = 17.0

        result_plug = node_a["tx"] % 5

        assert result_plug.value == 2.0

    def test_rmod_numeric_by_plug(self, new_scene):
        """Test reversed modulo (numeric % plug)."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["tx"].value = 4.0

        result_plug = 10 % node_a["tx"]

        # For reversed: 10 % 4 = 2
        assert result_plug.value == 2.0


class TestPlugMathOperatorsCompound:
    """Tests for mathematical operators on compound (double3/float3) Plugs."""

    def test_add_compound_plugs(self, new_scene):
        """Test adding two compound plugs creates a plusMinusAverage node."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["translate"].value = (1.0, 2.0, 3.0)
        node_b["translate"].value = (4.0, 5.0, 6.0)

        result_plug = node_a["translate"] + node_b["translate"]

        # Verify a plusMinusAverage node was created
        assert "plusMinusAverage" in result_plug._node.type
        # Verify operation is Sum (1)
        assert cmds.getAttr(f"{result_plug._node.name}.operation") == 1
        # Verify compound output
        assert result_plug.attr == "output3D"
        result_value = result_plug.value
        assert result_value[0][0] == pytest.approx(5.0)
        assert result_value[0][1] == pytest.approx(7.0)
        assert result_value[0][2] == pytest.approx(9.0)

    def test_add_compound_to_scalar(self, new_scene):
        """Test adding a scalar to a compound plug."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["translate"].value = (1.0, 2.0, 3.0)

        result_plug = node_a["translate"] + 10.0

        result_value = result_plug.value
        assert result_value[0][0] == pytest.approx(11.0)
        assert result_value[0][1] == pytest.approx(12.0)
        assert result_value[0][2] == pytest.approx(13.0)

    def test_sub_compound_plugs(self, new_scene):
        """Test subtracting two compound plugs creates a plusMinusAverage node."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["translate"].value = (10.0, 20.0, 30.0)
        node_b["translate"].value = (1.0, 2.0, 3.0)

        result_plug = node_a["translate"] - node_b["translate"]

        # Verify operation is Subtract (2)
        assert cmds.getAttr(f"{result_plug._node.name}.operation") == 2
        result_value = result_plug.value
        assert result_value[0][0] == pytest.approx(9.0)
        assert result_value[0][1] == pytest.approx(18.0)
        assert result_value[0][2] == pytest.approx(27.0)

    def test_mul_compound_plugs(self, new_scene):
        """Test multiplying two compound plugs creates a multiplyDivide node."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["translate"].value = (2.0, 3.0, 4.0)
        node_b["translate"].value = (5.0, 6.0, 7.0)

        result_plug = node_a["translate"] * node_b["translate"]

        # Verify a multiplyDivide node was created
        assert "multiplyDivide" in result_plug._node.type
        # Verify operation is Multiply (1)
        assert cmds.getAttr(f"{result_plug._node.name}.operation") == 1
        result_value = result_plug.value
        assert result_value[0][0] == pytest.approx(10.0)
        assert result_value[0][1] == pytest.approx(18.0)
        assert result_value[0][2] == pytest.approx(28.0)

    def test_div_compound_plugs(self, new_scene):
        """Test dividing two compound plugs creates a multiplyDivide node."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["translate"].value = (10.0, 20.0, 30.0)
        node_b["translate"].value = (2.0, 4.0, 5.0)

        result_plug = node_a["translate"] / node_b["translate"]

        # Verify operation is Divide (2)
        assert cmds.getAttr(f"{result_plug._node.name}.operation") == 2
        result_value = result_plug.value
        assert result_value[0][0] == pytest.approx(5.0)
        assert result_value[0][1] == pytest.approx(5.0)
        assert result_value[0][2] == pytest.approx(6.0)

    def test_pow_compound_plugs(self, new_scene):
        """Test power operation on compound plugs creates a multiplyDivide node."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["translate"].value = (2.0, 3.0, 4.0)

        result_plug = node_a["translate"] ** 2

        # Verify operation is Power (3)
        assert cmds.getAttr(f"{result_plug._node.name}.operation") == 3
        result_value = result_plug.value
        assert result_value[0][0] == pytest.approx(4.0)
        assert result_value[0][1] == pytest.approx(9.0)
        assert result_value[0][2] == pytest.approx(16.0)

    def test_compound_to_compound_connection(self, new_scene):
        """Test that compound operations use compound-to-compound connections."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["translate"].value = (1.0, 2.0, 3.0)
        node_b["translate"].value = (4.0, 5.0, 6.0)

        result_plug = node_a["translate"] + node_b["translate"]

        # Verify that the compound attribute is connected, not children separately
        input0_conns = cmds.listConnections(
            f"{result_plug._node.name}.input3D[0]", plugs=True, source=True
        )
        input1_conns = cmds.listConnections(
            f"{result_plug._node.name}.input3D[1]", plugs=True, source=True
        )
        # Should have compound connection, not separate X/Y/Z
        assert input0_conns is not None
        assert input1_conns is not None
        assert any("translate" in conn for conn in input0_conns)
        assert any("translate" in conn for conn in input1_conns)


class TestPlugChainedOperations:
    """Tests for chained mathematical operations with correct precedence."""

    def test_chained_add_and_multiply(self, new_scene):
        """Test chaining add and multiply respects operator precedence."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"].value = 10.0
        node_b["tx"].value = 5.0

        # 10 + 5 * 2 = 10 + 10 = 20 (not 30)
        result_plug = node_a["tx"] + node_b["tx"] * 2.0

        assert result_plug.value == 20.0

    def test_chained_subtract_and_divide(self, new_scene):
        """Test chaining subtract and divide respects operator precedence."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"].value = 20.0
        node_b["tx"].value = 10.0

        # 20 - 10 / 2 = 20 - 5 = 15
        result_plug = node_a["tx"] - node_b["tx"] / 2.0

        assert result_plug.value == 15.0

    def test_chained_operations_with_connection(self, new_scene):
        """Test chaining math operations and connecting result."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        target = tm.create_node("transform", name="target")
        node_a["tx"].value = 10.0
        node_b["tx"].value = 5.0

        # Chain operations and connect
        node_a["tx"] + node_b["tx"] * 2.5 >> target["tz"]

        # 10 + 5 * 2.5 = 10 + 12.5 = 22.5
        assert target["tz"].value == 22.5

    def test_complex_expression(self, new_scene):
        """Test a more complex mathematical expression."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"].value = 4.0
        node_b["tx"].value = 2.0

        # (4 + 2) * 3 - 6 / 2 = 6 * 3 - 3 = 18 - 3 = 15
        result_plug = (node_a["tx"] + node_b["tx"]) * 3 - 6 / node_b["tx"]

        assert result_plug.value == 15.0


class TestPlugConnectionOperators:
    """Tests for connection and disconnection operators."""

    def test_lshift_reverse_connection(self, new_scene):
        """Test << operator connects in reverse direction."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"].value = 42.0

        # node_b["tx"] << node_a["tx"] is equivalent to node_a["tx"] >> node_b["tx"]
        node_b["tx"] << node_a["tx"]

        assert node_b["tx"].value == 42.0
        connections = cmds.listConnections(
            node_b["tx"].path, plugs=True, source=True
        )
        # Maya may return the full attribute name (translateX)
        assert any("nodeA" in conn and "translate" in conn.lower() for conn in connections)

    def test_lshift_returns_self(self, new_scene):
        """Test << operator returns self for potential chaining."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")

        result = node_b["tx"] << node_a["tx"]

        assert result.path == node_b["tx"].path

    def test_floordiv_disconnect(self, new_scene):
        """Test // operator disconnects plugs."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"].value = 42.0

        # First connect
        node_a["tx"] >> node_b["tx"]
        assert node_b["tx"].value == 42.0

        # Now disconnect
        node_a["tx"] // node_b["tx"]

        # Verify disconnection
        connections = cmds.listConnections(
            node_b["tx"].path, plugs=True, source=True
        )
        assert connections is None

    def test_floordiv_returns_none(self, new_scene):
        """Test // operator returns None."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"] >> node_b["tx"]

        result = node_a["tx"] // node_b["tx"]

        assert result is None

    def test_lshift_type_error(self, new_scene):
        """Test << operator raises TypeError for non-Plug operand."""
        node_a = tm.create_node("transform", name="nodeA")

        with pytest.raises(TypeError):
            node_a["tx"] << 5

    def test_floordiv_type_error(self, new_scene):
        """Test // operator raises TypeError for non-Plug operand."""
        node_a = tm.create_node("transform", name="nodeA")

        with pytest.raises(TypeError):
            node_a["tx"] // 5


class TestPlugOperatorEdgeCases:
    """Tests for edge cases and error handling."""

    def test_math_with_invalid_type_raises_error(self, new_scene):
        """Test math operators raise TypeError for invalid operand types."""
        node_a = tm.create_node("transform", name="nodeA")

        with pytest.raises(TypeError):
            node_a["tx"] + "invalid"

    def test_math_with_float_and_int(self, new_scene):
        """Test math operators work with both float and int literals."""
        node_a = tm.create_node("transform", name="nodeA")
        node_a["tx"].value = 10.0

        result_int = node_a["tx"] + 5
        result_float = node_a["tx"] + 5.0

        assert result_int.value == 15.0
        assert result_float.value == 15.0

    def test_division_by_zero_plug(self, new_scene):
        """Test division when divisor plug is zero."""
        node_a = tm.create_node("transform", name="nodeA")
        node_b = tm.create_node("transform", name="nodeB")
        node_a["tx"].value = 10.0
        node_b["tx"].value = 0.0

        result_plug = node_a["tx"] / node_b["tx"]

        # Maya's divide node returns 0 for division by zero (with a warning)
        # This is expected Maya behavior
        import math
        result_value = result_plug.value
        # Accept inf, very large value, or 0 (Maya's divide node returns 0)
        assert math.isinf(result_value) or abs(result_value) >= 100000.0 or result_value == 0.0

