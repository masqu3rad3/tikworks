"""Control module: one controller and the joint it drives."""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import (
    BoolField,
    FloatField,
    GuideLayout,
    Input,
    Module,
    register_module,
)


@register_module("control", category="generic")
class Control(Module):
    """A controller, optionally a tweak under it, and one bind joint.

    The smallest useful module: a prop handle, an eye, a jaw, anything a rig
    needs to be one animatable thing. Everything beyond the controller and its
    joint comes from the manifest rather than from ``build`` -- ``space_controls``
    is left undeclared so the control is offered an animation space, and
    ``pivot_controls`` offers it a movable pivot that the rigger's preset rows
    are what actually build.

    Nothing here is ``shared``, so a copy owns its parent and its joint: one
    module can hold a whole shelf of props, each hanging off something else.
    """

    label = "Control"
    guides = GuideLayout("root")
    inputs = (Input("root", primary=True, help="What this control hangs from"),)
    outputs = ("root",)
    controls = ("root",)
    control_shapes = {"root": "Circle"}
    pivot_controls = {"root": "root"}

    tweak = BoolField(False, help="Add a secondary tweak controller")
    controller_size = FloatField(5.0, min=0.01, label="Controller Size")

    def draw_guides(self, guides) -> None:
        """A single joint: the control, its joint and its pivot all sit here."""
        guides.joint("root", (0, 0, 0))

    def build(self, rig) -> None:
        """One controller driving one bind joint, through the tweak if asked."""
        guide = rig.guide("root")
        socket = rig.socket("root", match=guide)
        controller = rig.controller(
            "root",
            size=self.controller_size,
            match=guide,
            mirror="behaviour",
        )
        tm.MatrixConstraint.create(socket, controller.offset, maintain_offset=True)
        # The tweak is what downstream reads when there is one: it is a finer
        # grip on the same control, and a rig that followed the main instead
        # would ignore every tweak the animator made.
        driver = rig.tweak_control(controller) if self.tweak else controller
        joint = rig.bind_joint("root", match=guide)
        tm.MatrixConstraint.create(driver, joint, maintain_offset=True)
        rig.output("root", joint)
