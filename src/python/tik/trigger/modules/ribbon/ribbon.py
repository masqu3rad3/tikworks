"""Ribbon module: a deforming strip between two inputs.

The ``Ribbon`` construct lives in ``rig_grp`` as puppet, because its joints
sit in a non-inheriting group holding world-space channel values -- correct
for the construct, wrong for a bind hierarchy that has to bake and export
under a moving rig root. Real bind joints are created under
``rig.bind_parent`` and constrained from it, the pattern ``_blend_to_bind``
already uses in ``systems/limb.py``.
"""

from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)

#: Rotate order applying X innermost, so ``rotateX`` is a pure roll about the strip.
ROTATE_ORDER_XYZ = 0

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
        Input("reference", help="Frame both twists are read against"),
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
    def outputs_for_copy(cls, settings=None):
        """One output per ribbon joint."""
        count = int((settings or {}).get("joint_count", cls.joint_count.default))
        return tuple(f"joint{index}" for index in range(count))

    @classmethod
    def controls_for_copy(cls, settings=None):
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

    @classmethod
    def control_shape_defaults_for_copy(cls, settings=None):
        """A circle for every control the settings ask for."""
        return {role: "Circle" for role in cls.controls_for_copy(settings)}

    @classmethod
    def pivot_controls_for_copy(cls, settings=None):
        """Only the end controls; a mid gets no movable pivot.

        A mid rides the surface rather than sitting on a guide, and moving its
        pivot does not behave the way a moved pivot should -- so offering one
        would be offering something that does not work. The ends pin to a
        guide each and behave normally.
        """
        return {
            role: (role, 0)
            for role in cls.controls_for_copy(settings)
            if role in ("start", "end")
        }

    @classmethod
    def pivot_exempt_for_copy(cls, settings=None):
        """The mids, on purpose: a moved pivot does not behave there.

        A mid control rides the ribbon surface rather than sitting on a guide
        of its own, so a pivot moved away from it does not rotate about where
        the animator put it. Offering the preset would be offering something
        that does not work.
        """
        return tuple(
            role for role in cls.controls_for_copy(settings) if role.startswith("mid")
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
            # Both ends are read against the same frame. The construct's up
            # frame is the start pin with its twist removed, so every joint
            # roll is that frame plus the interpolated twist: the end twist
            # therefore has to be the end's roll against the *reference*, not
            # against the start driver, or a twisted start under-twists the
            # end by exactly its own roll. Without a reference the sockets'
            # own group serves, which is static within the module.
            reference = (
                rig.socket("reference")
                if rig.instance.inputs.get("reference")
                else start_socket.parent
            )
            forward = end_guide.world_position - start_guide.world_position

            def pin_twist(role, socket, driver, against):
                """The socket's roll against ``against``, plus the control's own.

                The socket's share is matrix-derived and bounded to +/-180 by
                the representation. The controller's share is its ``rotateX``
                channel, a plain float that winds past 360 without a pop --
                the pattern the mid controllers already follow, and the only
                way a ribbon twists beyond 180.
                """
                angle = twist_plug(socket, against, name=rig.name(f"{role}Twist"))
                if driver is socket:
                    return angle
                roll = _control_roll(driver, forward, rig.name(role))
                return angle if roll is None else angle + roll

            (
                pin_twist("start", start_socket, start_driver, reference)
                >> ribbon.start_twist
            )
            pin_twist("end", end_socket, end_driver, reference) >> ribbon.end_twist

        # Controllers belong to the module: tagged, side-coloured, in
        # control_grp, with an offset group. The offset rides the swinging
        # frame, so the controller still travels with the ribbon.
        for index, frame in enumerate(ribbon.mid_frames):
            controller = rig.controller(
                f"mid{index}",
                size=self.controller_size,
                match=frame,
                mirror="behaviour",
            )
            tm.MatrixConstraint.create(frame, controller.offset, maintain_offset=False)
            # The offset *is* the frame and the plug's parent is the frame, so
            # the controller's local channels are the plug's local channels.
            # They are connected channel to channel rather than through a
            # matrix constraint because the construct reads the plug's
            # rotateX as the mid's own roll: a matrix would decompose it back
            # to +/-180 and the mid controller would flip past that.
            control = controller.transform
            plug = ribbon.mid_plugs[index]
            control["rotateOrder"].value = ROTATE_ORDER_XYZ
            for channel in tm.TRANSFORM_CHANNELS:
                control[channel] >> plug[channel]

        for index, ribbon_joint in enumerate(ribbon.deformer_joints):
            joint = rig.bind_joint(f"joint{index}", match=ribbon_joint)
            tm.MatrixConstraint.create(ribbon_joint, joint, maintain_offset=True)
            rig.output(f"joint{index}", joint)


def _control_roll(control, forward, name):
    """``control.rotateX`` as a roll along ``forward``, or None when it is not one.

    The channel is a pure roll about the strip only when the control's X runs
    along it and X is applied innermost. A control matched to a guide someone
    reoriented off the strip keeps the bounded matrix twist instead of reading
    a channel that means something else.
    """
    along = control.world_axis("x") * forward.normal()
    if abs(along) < 0.5:
        logger.warning(
            "%s: X does not run along the ribbon; its roll stays bounded.", name
        )
        return None
    control["rotateOrder"].value = ROTATE_ORDER_XYZ
    channel = control["rotateX"]
    return channel if along > 0 else channel * -1.0
