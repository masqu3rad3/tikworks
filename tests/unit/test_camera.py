import pytest
from maya import cmds
from tikmaya.types.camera import Camera
from tikmaya.types.transform import Transform

class TestCamera:
    def test_create_camera(self):
        cmds.file(new=True, force=True)
        cam = Camera.create(name="uniqueTestCam")
        assert isinstance(cam, Camera)
        assert cmds.nodeType(cam.name) == "camera"
        # Maya might append '1' even in a new scene depending on configuration/defaults
        assert cam.transform.name.startswith("uniqueTestCam")

    def test_lens_property(self):
        cam = Camera.create()
        # Default focal length is usually 35.0
        assert cam.lens == 35.0

        cam.lens = 50.0
        assert cam.lens == 50.0
        assert cmds.getAttr(f"{cam.name}.focalLength") == 50.0

    def test_fit_modes(self):
        cam = Camera.create()

        # Test valid modes
        cam.fit("fill")
        assert cmds.getAttr(f"{cam.name}.filmFit") == 0

        cam.fit("horizontal")
        assert cmds.getAttr(f"{cam.name}.filmFit") == 1

        cam.fit("vertical")
        assert cmds.getAttr(f"{cam.name}.filmFit") == 2

        cam.fit("overscan")
        assert cmds.getAttr(f"{cam.name}.filmFit") == 3

        # Test invalid mode
        with pytest.raises(ValueError, match="Invalid fit mode"):
            cam.fit("invalid")

    def test_set_controls_camera_only(self):
        cam = Camera.create()
        cam.set_controls("camera")
        # Should be just a camera, no parent lookAt
        assert cam.aim is None
        assert cam.up is None

    def test_set_controls_camera_and_aim(self):
        cam = Camera.create(name="aimCam")
        cam.set_controls("cameraAndAim")

        # This creates a group hierarchy with a lookAt node
        assert cam.aim is not None

        aim_node = cam.aim
        # Verify it's a transform (locator's transform)
        # Note: get_input() returns the node connected to the plug
        assert cmds.nodeType(aim_node.name) == "transform"

        # Check if it has a locator shape
        shapes = cmds.listRelatives(aim_node.name, shapes=True)
        assert shapes and cmds.nodeType(shapes[0]) == "locator"

        assert cam.up is None

    def test_set_controls_camera_aim_and_up(self):
        cam = Camera.create(name="aimUpCam")
        cam.set_controls("cameraAimAndUp")

        assert cam.aim is not None
        assert cam.up is not None

        up_node = cam.up
        assert up_node is not None
        assert cmds.nodeType(up_node.name) == "transform"

    def test_set_controls_invalid_mode(self):
        cam = Camera.create()
        with pytest.raises(ValueError, match="Invalid control mode"):
            cam.set_controls("invalid")

    def test_delete_camera_and_aim(self):
        cam = Camera.create(name="delCam")
        cam.set_controls("cameraAndAim")

        parent = cam.transform.parent
        assert parent is not None
        parent_name = parent.name

        # Delete the camera
        cam.delete()

        # Verify camera is gone
        assert not cmds.objExists("delCam")

        # Verify parent (lookAt group) is also gone
        assert not cmds.objExists(parent_name)

    def test_delete_normal_camera(self):
        cam = Camera.create(name="normalDelCam")
        cam.delete()
        assert not cmds.objExists("normalDelCam")

    def test_aim_property_returns_none_if_not_aim_camera(self):
        cam = Camera.create()
        # Parent is None (world) or just a transform
        assert cam.aim is None

        # Parent to a normal group
        grp = cmds.createNode("transform", name="normalGrp")
        cmds.parent(cam.transform.name, grp)

        assert cam.aim is None # Parent is "transform", not "lookAt"

    def test_up_property_returns_none_if_not_aim_up_camera(self):
        cam = Camera.create()
        assert cam.up is None

        grp = cmds.createNode("transform", name="normalGrp2")
        cmds.parent(cam.transform.name, grp)
        assert cam.up is None

