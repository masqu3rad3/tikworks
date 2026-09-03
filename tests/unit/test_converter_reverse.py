"""
Unit tests for the maya.cmds to tik.maya converter (reverse direction).

Tests the reverse conversion rules and overall conversion accuracy.
"""

import ast

from tik.maya.utils.converter import convert_to_tik
from tik.maya.utils.converter.rules_reverse import CreateNodeToTransformRule, JointToJointCreateRule, PolySphereToMeshCreateRule, SetAttrToPlugSetRule, SetAttrLockToPlugLockRule, GetAttrToPlugGetRule, ConnectAttrToPlugConnectRule, MakeIdentityToFreezeRule, ReverseRuleContext


class TestCreateNodeToTransformRule:
    """Tests for cmds.createNode('transform') → Transform.create() conversion."""

    def test_matches_createnode_transform(self):
        """Test that rule matches cmds.createNode('transform') pattern."""
        code = "cmds.createNode('transform', name='test')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = CreateNodeToTransformRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        assert rule.matches(call_node, context)

    def test_convert_createnode_transform(self):
        """Test conversion of cmds.createNode('transform')."""
        code = "cmds.createNode('transform', name='test')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = CreateNodeToTransformRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        result = rule.convert(call_node, context)

        assert "Transform.create(" in result.converted_code
        assert "name='test'" in result.converted_code


class TestJointToJointCreateRule:
    """Tests for cmds.joint() → Joint.create() conversion."""

    def test_matches_joint(self):
        """Test that rule matches cmds.joint() pattern."""
        code = "cmds.joint(name='joint1')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = JointToJointCreateRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        assert rule.matches(call_node, context)

    def test_convert_joint(self):
        """Test conversion of cmds.joint()."""
        code = "cmds.joint(name='joint1')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = JointToJointCreateRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        result = rule.convert(call_node, context)

        assert "Joint.create(" in result.converted_code
        assert "name='joint1'" in result.converted_code


class TestPolySphereToMeshCreateRule:
    """Tests for cmds.polySphere() → Mesh.create('polySphere') conversion."""

    def test_matches_polysphere(self):
        """Test that rule matches cmds.polySphere() pattern."""
        code = "cmds.polySphere(radius=2)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = PolySphereToMeshCreateRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        assert rule.matches(call_node, context)

    def test_convert_polysphere(self):
        """Test conversion of cmds.polySphere()."""
        code = "cmds.polySphere(radius=2)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = PolySphereToMeshCreateRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        result = rule.convert(call_node, context)

        assert "Mesh.create('polySphere'" in result.converted_code
        assert "radius=2" in result.converted_code


class TestSetAttrToPlugSetRule:
    """Tests for cmds.setAttr() → plug.set() conversion."""

    def test_matches_setattr(self):
        """Test that rule matches cmds.setAttr() pattern."""
        code = "cmds.setAttr('pCube1.translateX', 5.0)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = SetAttrToPlugSetRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        assert rule.matches(call_node, context)

    def test_convert_setattr(self):
        """Test conversion of cmds.setAttr()."""
        code = "cmds.setAttr('pCube1.translateX', 5.0)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = SetAttrToPlugSetRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        result = rule.convert(call_node, context)

        assert "pCube1" in result.converted_code
        assert "['translateX']" in result.converted_code
        assert ".set(" in result.converted_code
        assert "5.0" in result.converted_code


class TestSetAttrLockToPlugLockRule:
    """Tests for cmds.setAttr(lock=True/False) → plug.lock()/unlock() conversion."""

    def test_matches_setattr_lock(self):
        """Test that rule matches cmds.setAttr(lock=True) pattern."""
        code = "cmds.setAttr('pCube1.translateX', lock=True)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = SetAttrLockToPlugLockRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        assert rule.matches(call_node, context)

    def test_convert_setattr_lock_true(self):
        """Test conversion of cmds.setAttr(lock=True)."""
        code = "cmds.setAttr('pCube1.translateX', lock=True)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = SetAttrLockToPlugLockRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        result = rule.convert(call_node, context)

        assert ".lock()" in result.converted_code

    def test_convert_setattr_lock_false(self):
        """Test conversion of cmds.setAttr(lock=False)."""
        code = "cmds.setAttr('pCube1.translateX', lock=False)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = SetAttrLockToPlugLockRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        result = rule.convert(call_node, context)

        assert ".unlock()" in result.converted_code


class TestGetAttrToPlugGetRule:
    """Tests for cmds.getAttr() → plug.get() conversion."""

    def test_matches_getattr(self):
        """Test that rule matches cmds.getAttr() pattern."""
        code = "cmds.getAttr('pCube1.translateX')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = GetAttrToPlugGetRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        assert rule.matches(call_node, context)

    def test_convert_getattr(self):
        """Test conversion of cmds.getAttr()."""
        code = "cmds.getAttr('pCube1.translateX')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = GetAttrToPlugGetRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        result = rule.convert(call_node, context)

        assert "pCube1" in result.converted_code
        assert "['translateX']" in result.converted_code
        assert ".get()" in result.converted_code


class TestConnectAttrToPlugConnectRule:
    """Tests for cmds.connectAttr() → plug.connect() conversion."""

    def test_matches_connectattr(self):
        """Test that rule matches cmds.connectAttr() pattern."""
        code = "cmds.connectAttr('src.translateX', 'dst.translateX')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = ConnectAttrToPlugConnectRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        assert rule.matches(call_node, context)

    def test_convert_connectattr(self):
        """Test conversion of cmds.connectAttr()."""
        code = "cmds.connectAttr('src.translateX', 'dst.translateX', force=True)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = ConnectAttrToPlugConnectRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        result = rule.convert(call_node, context)

        assert "src" in result.converted_code
        assert ".connect(" in result.converted_code
        assert "dst" in result.converted_code


class TestMakeIdentityToFreezeRule:
    """Tests for cmds.makeIdentity(apply=True) → transform.freeze() conversion."""

    def test_matches_makeidentity(self):
        """Test that rule matches cmds.makeIdentity(apply=True) pattern."""
        code = "cmds.makeIdentity('pCube1', apply=True)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = MakeIdentityToFreezeRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        assert rule.matches(call_node, context)

    def test_convert_makeidentity(self):
        """Test conversion of cmds.makeIdentity()."""
        code = "cmds.makeIdentity('pCube1', apply=True, translate=True, rotate=True)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = MakeIdentityToFreezeRule()
        context = ReverseRuleContext(
            variable_types={}, source_lines=[code], imports={}, node_variables={}
        )

        result = rule.convert(call_node, context)

        assert ".freeze(" in result.converted_code
        assert "translate=True" in result.converted_code
        assert "rotate=True" in result.converted_code


class TestFullReverseConversion:
    """Integration tests for the full reverse converter."""

    def test_simple_node_creation(self):
        """Test conversion of simple node creation."""
        source = """
from maya import cmds

node = cmds.createNode('transform', name='myNode')
"""
        result = convert_to_tik(source)

        assert "Transform.create(" in result.converted_code
        assert "name='myNode'" in result.converted_code
        assert result.success_count > 0

    def test_attribute_operations(self):
        """Test conversion of attribute operations."""
        source = """
from maya import cmds

cmds.setAttr('node.translateX', 5.0)
value = cmds.getAttr('node.translateX')
"""
        result = convert_to_tik(source)

        assert ".set(" in result.converted_code
        assert ".get()" in result.converted_code

    def test_connection_operations(self):
        """Test conversion of connection operations."""
        source = """
from maya import cmds

cmds.connectAttr('src.translateX', 'dst.translateX', force=True)
"""
        result = convert_to_tik(source)

        assert ".connect(" in result.converted_code

    def test_unsupported_operations_flagged(self):
        """Test that unsupported operations are flagged."""
        source = """
from maya import cmds

selection = cmds.ls(selection=True)
"""
        result = convert_to_tik(source)

        assert len(result.unsupported_operations) > 0
        assert any(
            "ls" in entry.message for entry in result.unsupported_operations
        )

    def test_report_summary(self):
        """Test that report summary is generated correctly."""
        source = """
from maya import cmds

node = cmds.createNode('transform', name='test')
"""
        result = convert_to_tik(source)
        summary = result.summary()

        assert "CONVERSION REPORT" in summary
        assert "Rules applied:" in summary


class TestRegressionVariableMapping:
    """Regression tests for variable mapping in reverse conversion."""

    def test_variable_mapping_for_named_node(self):
        """Ensure setAttr uses the assigned variable, not the raw node string."""
        source = """
from maya import cmds

node = cmds.createNode('transform', name='myNode')
cmds.setAttr('myNode.translateX', 5.0)
"""
        result = convert_to_tik(source)
        print("\nConverted Code:\n")
        print(result.converted_code)

        assert "node = Transform.create(name='myNode')" in result.converted_code
        assert "node['translateX'].set(5.0)" in result.converted_code

    def test_makeidentity_not_treated_as_assignment(self):
        """Ensure cmds.makeIdentity with apply=True doesn't get corrupted."""
        source = """
from maya import cmds

node = cmds.createNode('transform', name='myNode')
cmds.makeIdentity(node, apply=True)
cmds.setAttr('myNode.translateX', 5.0)
"""
        result = convert_to_tik(source)
        print("\nConverted Code:\n")
        print(result.converted_code)

        # The assignment should be preserved
        assert "node = Transform.create(name='myNode')" in result.converted_code
        # makeIdentity should become node.freeze(), NOT be mangled
        assert "node.freeze()" in result.converted_code
        # setAttr should use the variable name
        assert "node['translateX'].set(5.0)" in result.converted_code
        # Should NOT contain broken code
        assert "apply = node.freeze()" not in result.converted_code


