"""
Unit tests for the tik.maya to maya.cmds converter.

Tests the conversion rules, helper expansion, and overall conversion accuracy.
"""


from tik.maya.utils.converter import Converter, convert
from tik.maya.utils.converter.rules import TransformCreateRule, JointCreateRule, MeshCreateRule, PlugGetRule, PlugSetRule, PlugConnectRule, PlugRshiftRule, TransformPropertySetRule, ResolveRule, RuleContext


class TestTransformCreateRule:
    """Tests for Transform.create() conversion."""

    def test_matches_transform_create(self):
        """Test that rule matches Transform.create() pattern."""
        import ast

        code = "Transform.create(name='test')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = TransformCreateRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        assert rule.matches(call_node, context)

    def test_convert_transform_create_with_name(self):
        """Test conversion of Transform.create(name='test')."""
        import ast

        code = "Transform.create(name='test')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = TransformCreateRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        result = rule.convert(call_node, context)

        assert "cmds.createNode('transform'" in result.converted_code
        assert "name='test'" in result.converted_code

    def test_convert_transform_create_no_args(self):
        """Test conversion of Transform.create() with no arguments."""
        import ast

        code = "Transform.create()"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = TransformCreateRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        result = rule.convert(call_node, context)

        assert result.converted_code == "cmds.createNode('transform')"


class TestJointCreateRule:
    """Tests for Joint.create() conversion."""

    def test_matches_joint_create(self):
        """Test that rule matches Joint.create() pattern."""
        import ast

        code = "Joint.create(name='joint1')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = JointCreateRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        assert rule.matches(call_node, context)

    def test_convert_joint_create(self):
        """Test conversion of Joint.create()."""
        import ast

        code = "Joint.create(name='joint1')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = JointCreateRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        result = rule.convert(call_node, context)

        assert "cmds.joint(" in result.converted_code
        assert "name='joint1'" in result.converted_code


class TestMeshCreateRule:
    """Tests for Mesh.create() conversion."""

    def test_matches_mesh_create(self):
        """Test that rule matches Mesh.create() pattern."""
        import ast

        code = "Mesh.create('polySphere')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = MeshCreateRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        assert rule.matches(call_node, context)

    def test_convert_mesh_create_poly_sphere(self):
        """Test conversion of Mesh.create('polySphere')."""
        import ast

        code = "Mesh.create('polySphere')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = MeshCreateRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        result = rule.convert(call_node, context)

        assert "cmds.polySphere()" in result.converted_code

    def test_convert_mesh_create_with_kwargs(self):
        """Test conversion of Mesh.create() with kwargs."""
        import ast

        code = "Mesh.create('polyCube', width=2)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = MeshCreateRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        result = rule.convert(call_node, context)

        assert "cmds.polyCube(" in result.converted_code
        assert "width=2" in result.converted_code


class TestPlugGetRule:
    """Tests for Plug.get() conversion."""

    def test_matches_plug_get(self):
        """Test that rule matches node['attr'].get() pattern."""
        import ast

        code = "node['translateX'].get()"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = PlugGetRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        assert rule.matches(call_node, context)

    def test_convert_plug_get(self):
        """Test conversion of node['attr'].get()."""
        import ast

        code = "node['translateX'].get()"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = PlugGetRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        result = rule.convert(call_node, context)

        assert "cmds.getAttr" in result.converted_code
        assert "translateX" in result.converted_code


class TestPlugSetRule:
    """Tests for Plug.set() conversion."""

    def test_matches_plug_set(self):
        """Test that rule matches node['attr'].set(value) pattern."""
        import ast

        code = "node['translateX'].set(5.0)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = PlugSetRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        assert rule.matches(call_node, context)

    def test_convert_plug_set(self):
        """Test conversion of node['attr'].set(value)."""
        import ast

        code = "node['translateX'].set(5.0)"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = PlugSetRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        result = rule.convert(call_node, context)

        assert "cmds.setAttr" in result.converted_code
        assert "translateX" in result.converted_code
        assert "5.0" in result.converted_code


class TestPlugConnectRule:
    """Tests for Plug.connect() conversion."""

    def test_matches_plug_connect(self):
        """Test that rule matches node['attr'].connect(other) pattern."""
        import ast

        code = "src['output'].connect(dst['input'])"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = PlugConnectRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        assert rule.matches(call_node, context)

    def test_convert_plug_connect(self):
        """Test conversion of plug.connect(other)."""
        import ast

        code = "src['output'].connect(dst['input'])"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = PlugConnectRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        result = rule.convert(call_node, context)

        assert "cmds.connectAttr" in result.converted_code
        assert "output" in result.converted_code
        assert "input" in result.converted_code


class TestPlugRshiftRule:
    """Tests for >> operator connection conversion."""

    def test_matches_rshift(self):
        """Test that rule matches src['attr'] >> dst['attr'] pattern."""
        import ast

        code = "src['output'] >> dst['input']"
        tree = ast.parse(code)
        binop_node = tree.body[0].value

        rule = PlugRshiftRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        assert rule.matches(binop_node, context)

    def test_convert_rshift(self):
        """Test conversion of >> operator."""
        import ast

        code = "src['output'] >> dst['input']"
        tree = ast.parse(code)
        binop_node = tree.body[0].value

        rule = PlugRshiftRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        result = rule.convert(binop_node, context)

        assert "cmds.connectAttr" in result.converted_code


class TestTransformPropertySetRule:
    """Tests for transform property assignment conversion."""

    def test_matches_translate_assignment(self):
        """Test that rule matches node.translate = value pattern."""
        import ast

        code = "node.translate = (1, 2, 3)"
        tree = ast.parse(code)
        assign_node = tree.body[0]

        rule = TransformPropertySetRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        assert rule.matches(assign_node, context)

    def test_convert_translate_assignment(self):
        """Test conversion of node.translate = value."""
        import ast

        code = "node.translate = (1, 2, 3)"
        tree = ast.parse(code)
        assign_node = tree.body[0]

        rule = TransformPropertySetRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        result = rule.convert(assign_node, context)

        assert "cmds.setAttr" in result.converted_code
        assert "translate" in result.converted_code


class TestResolveRule:
    """Tests for resolve() conversion."""

    def test_matches_direct_resolve(self):
        """Test that rule matches resolve('nodeName') pattern."""
        import ast

        code = "resolve('myNode')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = ResolveRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        assert rule.matches(call_node, context)

    def test_matches_module_qualified_resolve(self):
        """Test that rule matches tm.resolve('nodeName') pattern."""
        import ast

        code = "tm.resolve('myNode')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = ResolveRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        assert rule.matches(call_node, context)

    def test_matches_full_path_resolve(self):
        """Test that rule matches tik.maya.resolve('nodeName') pattern."""
        import ast

        code = "tik.maya.resolve('myNode')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = ResolveRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        assert rule.matches(call_node, context)

    def test_convert_resolve(self):
        """Test conversion of resolve('nodeName')."""
        import ast

        code = "resolve('myNode')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = ResolveRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        result = rule.convert(call_node, context)

        assert result.converted_code == "'myNode'"

    def test_convert_module_qualified_resolve(self):
        """Test conversion of tm.resolve('nodeName')."""
        import ast

        code = "tm.resolve('myNode')"
        tree = ast.parse(code)
        call_node = tree.body[0].value

        rule = ResolveRule()
        context = RuleContext(variable_types={}, source_lines=[code], imports={})

        result = rule.convert(call_node, context)

        assert result.converted_code == "'myNode'"


class TestFullConversion:
    """Integration tests for the full converter."""

    def test_simple_transform_creation(self):
        """Test conversion of simple transform creation."""
        source = """
from tik.maya import Transform

node = Transform.create(name='myNode')
"""
        result = convert(source)

        assert "cmds.createNode('transform'" in result.converted_code
        assert "name='myNode'" in result.converted_code
        assert result.success_count > 0

    def test_attribute_operations(self):
        """Test conversion of attribute operations."""
        source = """
from tik.maya import Transform

node = Transform.create(name='myNode')
node['translateX'].set(5.0)
value = node['translateX'].get()
"""
        result = convert(source)

        assert "cmds.setAttr" in result.converted_code
        assert "cmds.getAttr" in result.converted_code

    def test_connection_operations(self):
        """Test conversion of connection operations."""
        source = """
from tik.maya import Transform

src = Transform.create(name='src')
dst = Transform.create(name='dst')
src['translateX'].connect(dst['translateX'])
"""
        result = convert(source)

        assert "cmds.connectAttr" in result.converted_code

    def test_unsupported_operations_flagged(self):
        """Test that unsupported operations are flagged."""
        source = """
from tik.maya import Mesh

mesh = Mesh.create('polySphere')
mesh.unlock_normals()
"""
        result = convert(source)

        assert len(result.unsupported_operations) > 0
        assert any(
            "unlock_normals" in entry.message
            for entry in result.unsupported_operations
        )

    def test_report_summary(self):
        """Test that report summary is generated correctly."""
        source = """
from tik.maya import Transform

node = Transform.create(name='test')
"""
        result = convert(source)
        summary = result.summary()

        assert "CONVERSION REPORT" in summary
        assert "Rules applied:" in summary

    def test_resolve_with_module_import(self):
        """Test conversion of resolve() with module import pattern."""
        source = """
import tik.maya as tm
node = tm.resolve('myNode')
node['translateX'].set(5.0)
node.scale_x = 2.0
"""
        result = convert(source)

        # Check that resolve was converted
        assert "'myNode'" in result.converted_code
        # Check that setAttr calls were generated
        assert "cmds.setAttr" in result.converted_code
        assert "translateX" in result.converted_code
        assert "scaleX" in result.converted_code


class TestConverterConfiguration:
    """Tests for converter configuration options."""

    def test_no_imports_option(self):
        """Test converter with add_imports=False."""
        source = """
node = Transform.create(name='test')
"""
        converter = Converter(add_imports=False)
        result = converter.convert(source)

        # Should not add cmds import since no tik imports in source
        # (would add if tik imports were present)
        assert result.converted_code is not None

    def test_no_header_option(self):
        """Test converter with add_header=False."""
        source = """
node = Transform.create(name='test')
"""
        converter = Converter(add_header=False)
        result = converter.convert(source)

        assert '"""' not in result.converted_code or "Auto-generated" not in result.converted_code


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_syntax_error_handling(self):
        """Test that syntax errors are handled gracefully."""
        source = "def broken("

        result = convert(source)

        assert len(result.warnings) > 0
        assert any("Syntax error" in entry.message for entry in result.warnings)

    def test_empty_source(self):
        """Test conversion of empty source."""
        source = ""

        result = convert(source)

        assert result.converted_code is not None
        assert result.failure_count == 0

    def test_non_tik_code_passthrough(self):
        """Test that non-tik code passes through unchanged."""
        source = """
import maya.cmds as cmds

cmds.createNode('transform')
"""
        result = convert(source)

        # Original cmds code should be preserved
        assert "cmds.createNode('transform')" in result.converted_code

