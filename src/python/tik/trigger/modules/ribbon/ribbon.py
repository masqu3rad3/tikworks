"""Ribbon module: a deforming strip between two inputs.

The ``Ribbon`` construct lives in ``rig_grp`` as puppet, because its joints
sit in a non-inheriting group holding world-space channel values -- correct
for the construct, wrong for a bind hierarchy that has to bake and export
under a moving rig root. Real bind joints are created under
``rig.bind_parent`` and constrained from it, the pattern ``_blend_to_bind``
already uses in ``systems/limb.py``.
"""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import (
    BoolField,
    FieldGroup,
    FloatField,
    GuideLayout,
    Input,
    IntField,
    Module,
    register_module,
)
from tik.trigger.systems.twist import twist_plug

DEFORMATION = FieldGroup("Deformation", collapsed=True)
GUIDES = FieldGroup("Guides", collapsed=True)


@register_module("ribbon", category="generic")
class RibbonModule(Module):
    """A ribbon strip pinned between two inputs."""

    label = "Ribbon"
    guides = GuideLayout("start", "end")
    inputs = (
        Input("start", primary=True, help="What the ribbon start pins to"),
        Input("end", help="What the ribbon end pins to"),
        Input("reference", optional=True, help="Frame the start twist is read against"),
    )
    outputs = ("joint0",)

    joint_count = IntField(5, min=1, max=40, label="Joint Count")
    mid_count = IntField(1, min=0, max=10, label="Mid Controllers")
    start_controller = BoolField(
        False, label="Start Controller", help="An animatable control at the start pin"
    )
    end_controller = BoolField(
        False, label="End Controller", help="An animatable control at the end pin"
    )
    degree = IntField(3, min=1, max=3, group=DEFORMATION)
    scaleable = BoolField(
        True, help="Stretch-driven scaleX on the deform joints", group=DEFORMATION
    )
    preserve_volume = BoolField(
        False, help="Counter-scale Y/Z by ratio ** -0.5", group=DEFORMATION
    )
    twist = BoolField(True, help="Drive the ribbon twist from the pinned inputs")
    controller_size = FloatField(2.0, min=0.01, label="Controller Size", group=GUIDES)
    spacing = FloatField(
        10.0, min=0.01, help="Default distance between the guides", group=GUIDES
    )

    @classmethod
    def output_names(cls, settings=None):
        """One output per ribbon joint."""
        count = int((settings or {}).get("joint_count", cls.joint_count.default))
        return tuple(f"joint{index}" for index in range(count))

    @classmethod
    def control_names(cls, settings=None):
        """The end controls, when asked for, around one control per mid."""
        settings = settings or {}
        count = int(settings.get("mid_count", cls.mid_count.default))
        start = settings.get("start_controller", cls.start_controller.default)
        end = settings.get("end_controller", cls.end_controller.default)
        return (
            *(("start",) if start else ()),
            *(f"mid{index}" for index in range(count)),
            *(("end",) if end else ()),
        )

    # --------------------------------------------------------------- guides
    def draw_guides(self, guides) -> None:
        """A start and an end joint along X."""
        start = guides.joint("start", (0, 0, 0))
        guides.joint("end", (self.spacing * guides.side_mult, 0, 0), parent=start)

    # ---------------------------------------------------------------- build
    def build(self, rig) -> None:
        """A ribbon between the two sockets with its joints bound."""
        start_guide, end_guide = rig.guides("start", "end")
        start_socket = rig.socket("start", match=start_guide)
        end_socket = rig.socket("end", match=end_guide)

        ribbon = tm.Ribbon.create(
            start_guide,
            end_guide,
            name=rig.name("ribbon"),
            joint_count=self.joint_count,
            mid_count=self.mid_count,
            degree=self.degree,
            scaleable=self.scaleable,
            preserve_volume=self.preserve_volume,
            parent=rig.groups.rig,
        )
        def end_control(role, socket, guide):
            """A control between the socket and the pin, when asked for.

            Driven through its offset group, never parented under the socket:
            control_grp holds nothing but controllers and their offsets.
            """
            control = rig.controller(
                role,
                shape="Circle",
                size=self.controller_size,
                match=guide,
                mirror="behaviour",
            )
            tm.MatrixConstraint.create(socket, control.offset, maintain_offset=True)
            return control.transform

        start_driver = (
            end_control("start", start_socket, start_guide)
            if self.start_controller
            else start_socket
        )
        end_driver = (
            end_control("end", end_socket, end_guide)
            if self.end_controller
            else end_socket
        )
        ribbon.pin_start(start_driver)
        ribbon.pin_end(end_driver)

        if self.twist:
            # The construct exposes twist as bare float plugs and feeds
            # neither; the same extractor the twist module uses fills them, so
            # there is one implementation of swing-twist in the repo.
            reference = (
                rig.socket("reference")
                if rig.instance.inputs.get("reference")
                else start_socket.parent
            )
            # Read the *drivers*, not the sockets: with an end controller in
            # play the socket no longer carries the pinned frame, and reading
            # it would move the ribbon end without twisting it.
            if reference is not None:
                (
                    twist_plug(start_driver, reference, name=rig.name("startTwist"))
                    >> ribbon.start_twist
                )
            (
                twist_plug(end_driver, start_driver, name=rig.name("endTwist"))
                >> ribbon.end_twist
            )

        # Controllers belong to the module: tagged, side-coloured, in
        # control_grp, with an offset group. The offset rides the swinging
        # frame, so the controller still travels with the ribbon.
        for index, frame in enumerate(ribbon.mid_frames):
            controller = rig.controller(
                f"mid{index}",
                shape="Circle",
                size=self.controller_size,
                match=frame,
                mirror="behaviour",
            )
            tm.MatrixConstraint.create(frame, controller.offset, maintain_offset=False)
            tm.MatrixConstraint.create(
                controller, ribbon.mid_plugs[index], maintain_offset=False
            )

        for index, ribbon_joint in enumerate(ribbon.deformer_joints):
            joint = rig.bind_joint(f"joint{index}", match=ribbon_joint)
            tm.MatrixConstraint.create(ribbon_joint, joint, maintain_offset=True)
            rig.output(f"joint{index}", joint)
