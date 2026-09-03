import pytest
from maya import cmds

import tik.maya as tm
from tik.maya.roles.controller import Controller, replace_curve
from tik.maya.types.transform import Transform
from tik.maya.utils.control_shapes import ControlShapeLibrary


class TestController:

    @pytest.fixture(autouse=True)
    def mock_shape_library(self, monkeypatch):
        def mock_load(self, name):
            if name == "circle":
                return {
                    "curves": [
                        {
                            "point": [
                                (1.0, 0.0, 0.0),
                                (0.0, 0.0, 1.0),
                                (-1.0, 0.0, 0.0),
                                (0.0, 0.0, -1.0),
                            ],
                            "degree": 1,
                            "periodic": False,
                            # "knot": [0, 1, 2, 3, 4]
                        }
                    ]
                }
            return None

        monkeypatch.setattr(ControlShapeLibrary, "load", mock_load)

    @pytest.fixture(autouse=True)
    def setup(self):
        cmds.file(new=True, force=True)

    def test_create_controller(self):
        """Test basic controller creation."""
        ctrl = Controller.create("test_ctrl", shape="circle")
        assert cmds.objExists("test_ctrl")
        assert Controller.is_controller("test_ctrl")
        assert isinstance(ctrl, Controller)
        assert isinstance(ctrl.transform, Transform)

        # Verify default attributes
        assert cmds.getAttr("test_ctrl.isController") == True
        assert cmds.getAttr("test_ctrl.isHistoricallyInteresting") == 0

    def test_create_controller_with_dict_shape(self):
        """Test creating controller with explicit shape data."""
        shape_data = {
            "curves": [{"point": [(0, 0, 0), (1, 0, 0), (0, 1, 0)], "degree": 1}]
        }
        ctrl = Controller.create("dict_ctrl", shape=shape_data)
        assert len(ctrl.shapes) == 1
        assert cmds.nodeType(ctrl.shapes[0].name) == "nurbsCurve"

        # Verify CV positions (should be unscaled as size defaults to 1.0)
        cvs = cmds.getAttr(f"{ctrl.shapes[0].name}.cv[*]")
        # cmds.getAttr returns list of tuples [(x,y,z), ...]
        assert cvs[0] == (0.0, 0.0, 0.0)
        assert cvs[1] == (1.0, 0.0, 0.0)
        assert cvs[2] == (0.0, 1.0, 0.0)

    def test_create_controller_color(self):
        """Test controller creation with color."""
        # Test with index color
        ctrl = Controller.create("color_ctrl", color=17)  # Yellow
        assert ctrl.color == 17

        # Test with rgb color
        rgb = (1.0, 0.0, 0.0)
        ctrl2 = Controller.create("rgb_ctrl", color=rgb)
        # get_color might return tuple or list
        assert tuple(ctrl2.color) == rgb

    def test_from_node(self):
        """Test wrapping existing node."""
        # Create a regular transform
        transform = cmds.createNode("transform", name="regular_t")

        # Should fail
        with pytest.raises(RuntimeError):
            Controller.from_node("regular_t")

        # Tag it manually
        cmds.addAttr(
            transform, longName="isController", attributeType="bool", defaultValue=True
        )

        # Should succeed
        ctrl = Controller.from_node("regular_t")
        assert isinstance(ctrl, Controller)

    def test_init_validation(self):
        """Test validation in __init__."""
        # Create a mesh (transform + shape)
        m_trans = cmds.createNode("transform", name="mesh_trans")
        m_shape = cmds.createNode("mesh", parent=m_trans, name="mesh_shape")

        # Controller expects a Transform wrapper.
        # If we pass a node that resolves to something else (e.g. Camera), it should fail.
        # But Transform wraps "transform" nodes.
        # Let's try passing a shape node directly.

        # resolve("mesh_shape") returns a Mesh object (which inherits DagNode, not Transform).
        # Controller checks isinstance(node, Transform).

        with pytest.raises(TypeError):
            Controller("mesh_shape")

    def test_properties(self):
        """Test property accessors."""
        ctrl = Controller.create("prop_ctrl")

        # Color property setter/getter
        ctrl.color = 6
        assert ctrl.color == 6

        # Transform property
        assert ctrl.transform.name == "prop_ctrl"

        # Shapes property
        # Initially empty if "circle" not found in lib (likely in test env)
        # Let's add a shape to be sure
        ctrl.add_shape({"point": [(0, 0, 0)], "degree": 1})
        assert len(ctrl.shapes) > 0

        # Clear shapes
        ctrl.clear_shapes()
        assert len(ctrl.shapes) == 0

    def test_add_shape_scaling(self):
        """Test adding shape with scaling."""
        ctrl = Controller.create("scale_ctrl", shape={})
        ctrl.clear_shapes()

        curve_def = {"point": [(0, 1, 0)], "degree": 1}
        ctrl.add_shape(curve_def, size=2.0)

        assert len(ctrl.shapes) == 1
        cv_pos = cmds.pointPosition(f"{ctrl.shapes[0].name}.cv[0]", world=True)
        # (0, 1*2, 0)
        assert cv_pos == [0.0, 2.0, 0.0]

    def test_add_shape_with_knots(self):
        """Test adding shape with explicit knots."""
        ctrl = Controller.create("knot_ctrl", shape={})
        ctrl.clear_shapes()

        # Degree 1 curve with 2 points needs 0 knots if not periodic?
        # Actually degree 1 with 2 points has 2 CVs. Spans = CVs - degree = 2 - 1 = 1.
        # Knots = spans + 2*degree - 1 = 1 + 2 - 1 = 2 knots? No.
        # Number of knots = number of CVs + degree - 1.
        # For degree 1, 2 CVs: 2 + 1 - 1 = 2 knots. e.g. [0, 1]

        curve_def = {"point": [(0, 0, 0), (1, 0, 0)], "degree": 1, "knot": [0, 1]}
        ctrl.add_shape(curve_def)
        assert len(ctrl.shapes) == 1

        # Verify knots
        # cmds.getAttr(f"{ctrl.shapes[0].name}.knots") might work or use getAttr with multi-index
        # But just successful creation is enough to cover the line.

    def test_set_shape_string(self, monkeypatch):
        """Test set_shape with string name (mocking library)."""

        def mock_load(self, name):
            if name == "mock_shape":
                return {"curves": [{"point": [(0, 0, 0), (1, 1, 1)], "degree": 1}]}
            return None

        monkeypatch.setattr(ControlShapeLibrary, "load", mock_load)

        ctrl = Controller.create("lib_ctrl", shape="mock_shape")
        assert len(ctrl.shapes) == 1

        # Test invalid shape
        ctrl.set_shape("non_existent")
        # Should clear shapes and log error
        assert len(ctrl.shapes) == 0

    def test_set_shape_invalid_type(self):
        ctrl = Controller.create("type_ctrl", shape={})
        with pytest.raises(TypeError):
            ctrl.set_shape(123)

    def test_replace_shape(self):
        """Test replace_shape method."""
        shape1 = {"curves": [{"point": [(0, 0, 0), (1, 0, 0)], "degree": 1}]}
        ctrl = Controller.create("replace_ctrl", shape=shape1)
        original_shape_name = ctrl.shapes[0].name

        shape2 = {"curves": [{"point": [(0, 0, 0), (0, 1, 0)], "degree": 1}]}

        cmds.select(ctrl.node.name)
        ctrl.replace_shape(shape2, snap=True)

        # Verify selection kept
        assert cmds.ls(sl=True)[0] == ctrl.node.name

        # Verify shape changed (by checking CV position)
        # The original shape node might be reused or replaced depending on implementation details of replace_curve
        # But the geometry should match shape2
        cv_pos = cmds.pointPosition(f"{ctrl.shapes[0].name}.cv[1]", world=True)
        assert cv_pos == [0.0, 1.0, 0.0]

    def test_replace_curve_logic(self):
        """Test the standalone replace_curve function logic."""
        # Case 1: Equal shape count
        c1 = cmds.curve(p=[(0, 0, 0), (1, 0, 0)], d=1, name="c1")
        c2 = cmds.curve(p=[(0, 0, 0), (0, 1, 0)], d=1, name="c2")

        replace_curve(c1, c2, snap=False)
        pos = cmds.pointPosition(f"{c1}.cv[1]")
        assert pos == [0.0, 1.0, 0.0]

        # Case 2: Target has fewer shapes (needs to add)
        c1 = cmds.curve(p=[(0, 0, 0), (1, 0, 0)], d=1, name="c1_fewer")

        # Create c2 with 2 shapes
        c2 = cmds.curve(p=[(0, 0, 0), (0, 1, 0)], d=1, name="c2_more")
        # Add a second shape to c2
        temp = cmds.curve(p=[(0, 0, 0), (0, 0, 1)], d=1)
        temp_shape = cmds.listRelatives(temp, shapes=True)[0]
        cmds.parent(temp_shape, c2, relative=True, shape=True)
        cmds.delete(temp)

        assert len(cmds.listRelatives(c2, shapes=True)) == 2

        replace_curve(c1, c2, snap=False)

        # c1 should now have 2 shapes
        assert len(cmds.listRelatives(c1, shapes=True)) == 2

        # Case 3: Target has more shapes (needs to delete)
        c1 = cmds.curve(p=[(0, 0, 0)], d=1, name="c1_more")
        # Add extra shape
        temp = cmds.curve(p=[(0, 0, 0)], d=1)
        temp_shape = cmds.listRelatives(temp, shapes=True)[0]
        cmds.parent(temp_shape, c1, relative=True, shape=True)
        cmds.delete(temp)
        assert len(cmds.listRelatives(c1, shapes=True)) == 2

        c2 = cmds.curve(p=[(0, 0, 0)], d=1, name="c2_fewer")  # 1 shape

        replace_curve(c1, c2, snap=False)

        # c1 should now have 1 shape
        assert len(cmds.listRelatives(c1, shapes=True)) == 1

    def test_replace_curve_color_transfer(self):
        """Test color transfer in replace_curve."""
        c1 = cmds.curve(p=[(0, 0, 0)], d=1, name="c1")
        c2 = cmds.curve(p=[(0, 0, 0)], d=1, name="c2")

        cmds.setAttr(f"{c2}.overrideEnabled", 1)
        cmds.setAttr(f"{c2}.overrideColor", 17)  # Yellow

        replace_curve(c1, c2, transfer_color=True, snap=False)

        # Check shape color
        shape = cmds.listRelatives(c1, shapes=True)[0]
        assert cmds.getAttr(f"{shape}.overrideEnabled") == 1
        assert cmds.getAttr(f"{shape}.overrideColor") == 17

    def test_getattr_delegation(self):
        """Test __getattr__ delegation to node."""
        ctrl = Controller.create("getattr_ctrl")
        # Access 'name' which is on the node wrapper
        assert ctrl.name == "getattr_ctrl"
        # Access 'delete' which is on Node
        assert hasattr(ctrl, "delete")


def test_controller_plugs_pass_through_to_its_transform():
    """``control["tx"]`` reads the transform's plug.

    __getattr__ cannot cover indexing: Python looks dunder methods up on the
    type, so without __getitem__ a controller cannot be indexed or connected.
    Writes and type-checked APIs still need ``.transform`` — the role does not
    proxy __setattr__, and isinstance checks see a Controller, not a Transform.
    """
    control = Controller.create(name="passthrough_ctrl", shape="Circle")
    driven = tm.Transform.create(name="passthrough_driven")

    assert control["translateX"].value == control.transform["translateX"].value
    control["translateX"] >> driven["translateX"]
    control.transform.translate_x = 3.0
    assert round(driven.translate_x, 4) == 3.0
