"""Camera node types wrapper."""

from maya import cmds
from maya import mel

from ..core.shapenode import ShapeNode
from ..core.registry import register


@register("camera")
class Camera(ShapeNode):
    """Wrapper for camera nodes."""
    film_fit_modes = {
        "fill": 0,
        "horizontal": 1,
        "vertical": 2,
        "overscan": 3
    }
    control_modes = {
        "camera": 1,
        "cameraAndAim": 2,
        "cameraAimAndUp": 3
    }

    @classmethod
    def create(cls, **kwargs):
        """Create a camera node.

        Args:
            **kwargs
                Additional keyword arguments passed to cmds.camera.

        Returns:
            Camera
                Instance of the created camera node.
        """
        _camera_transform, camera_shape = cmds.camera(**kwargs)
        return cls(camera_shape)

    def set_controls(self, mode="camera"):
        """Set the Controls for the camera.

        Args:
            mode (str): The control mode. Valid values are:
             "camera", "cameraAndAim", "cameraAimAndUp".
        """
        if mode not in self.control_modes:
            raise ValueError(f"Invalid control mode: {mode}")
        mel.eval(f'cameraMakeNode {self.control_modes[mode]} "{self.transform.name}"')

    def fit(self, mode="horizontal"):
        """Fit the camera view to the selected objects.

        Args:
            mode (str): The fit mode, either "horizontal" or "vertical".
        """
        if mode not in self.film_fit_modes:
            raise ValueError(f"Invalid fit mode: {mode}")
        self["filmFit"].value = self.film_fit_modes[mode]

    @property
    def aim(self):
        """Get the aim locator of the camera."""
        cam_parent = self.transform.parent
        if not cam_parent: # not an aim camera
            return None
        if not cam_parent.type != "lookAt": # not an aim camera
            return None


