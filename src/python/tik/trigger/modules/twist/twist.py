"""Twist module: N joints rolling about one axis between two inputs.

Generic, not a limb accessory. ``twist_source`` says *which end drives* the
roll; ``extraction`` says *how the angle is read*.

**Placement is an aim, not a guide pose.** The joints ride a frame that sits
at the base input and aims at the end input, with its up vector taken from the
base, so they stay on the base-to-end line in every pose. They cannot be
placed from the guides' own world transforms: the bind chain is aligned to the
guides rather than aimed down the bone (an arm's lowerarm X axis is only
0.98 aligned with the direction to the hand), so a joint parented to it with a
plain local offset drifts off the segment.

**Position and weight are authored, not derived.** A twist guide is a handle
on two numbers -- ``position`` along the segment and ``twistWeight`` -- and its
transform channels are locked, driven by ``position`` off the end guide.

**The guides constrain the shape they describe.** The base guide is free: the
rigger places and orients it, and its X axis is the segment. The end guide
moves in ``translateX`` only, so the segment cannot be anything but the base's
X axis and the twist axis cannot drift off it. Aiming is therefore done by
orienting the base, which is a single, visible decision rather than an
invariant a rigger has to remember.
"""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import (
    ChoiceField,
    FieldGroup,
    FloatField,
    GuideAttr,
    GuideLayout,
    Input,
    IntField,
    Module,
    register_module,
)
from tik.trigger.systems.twist import AXES, SOURCES, dominant_axis, twist_plug

WEIGHT_ATTR = "twistWeight"
POSITION_ATTR = "position"
#: The end guide is a length handle and nothing else: the segment always runs
#: down the base's X, which is what makes X the twist axis by construction
#: rather than by convention.
END_FREE = ("tx",)


EXTRACTION = FieldGroup("Extraction", collapsed=True)
GUIDES = FieldGroup("Guides", collapsed=True)


@register_module("twist")
class Twist(Module):
    """A strip of twist joints between two inputs."""

    label = "Twist"
    guides = GuideLayout("base", "end", multi="twist", min=1, max=20)
    inputs = (
        Input("base", primary=True, help="Segment start (upperarm, thigh, shaft)"),
        Input("end", help="Segment end (lowerarm, shin, hub)"),
        Input(
            "reference",
            optional=True,
            help="What a start-sourced twist is measured against; "
            "defaults to the base socket's parent",
        ),
    )
    outputs = ("twist0",)
    guide_attrs = {
        "twist": (
            GuideAttr(
                POSITION_ATTR,
                help="Where this joint sits between base and end, 0 to 1.",
            ),
            GuideAttr(
                WEIGHT_ATTR,
                help="How much of the extracted twist this joint takes. "
                "Unclamped; negative reverses it.",
            ),
        )
    }

    count = IntField(3, min=1, max=20, help="Number of twist joints")
    twist_source = ChoiceField(
        "end",
        choices=("start", "end"),
        label="Twist Source",
        group=EXTRACTION,
        help="'end' follows the child (forearm); 'start' counters the "
        "segment's own roll (upper arm)",
    )
    axis = ChoiceField("auto", choices=("auto", *AXES))
    extraction = ChoiceField(
        "auto",
        choices=SOURCES,
        group=EXTRACTION,
        help="'channel' is unbounded but needs an FK-style driver; "
        "'matrix' works anywhere and wraps past 180 degrees",
    )
    spacing = FloatField(
        10.0, min=0.01, help="Default guide distance, base to end", group=GUIDES
    )

    @classmethod
    def output_names(cls, settings=None):
        """One output per twist joint."""
        count = int((settings or {}).get("count", cls.count.default))
        return tuple(f"twist{index}" for index in range(count))

    def guide_count(self) -> int:
        """One twist guide per ``count``."""
        return self.count

    # --------------------------------------------------------------- guides
    def draw_guides(self, guides) -> None:
        """A base, an end, and ``count`` twist joints spread between them."""
        span = self.spacing * guides.side_mult
        base = guides.joint("base", (0, 0, 0), radius=1.5)
        guides.joint("end", (span, 0, 0), parent=base, radius=1.5)
        for index in range(self.count):
            fraction = (index + 1) / (self.count + 1)
            joint = guides.joint(
                "twist", (span * fraction, 0, 0), index=index, parent=base, radius=0.5
            )
            joint[POSITION_ATTR].value = fraction
            # The sensible default, freely overridable afterwards.
            joint[WEIGHT_ATTR].value = (
                fraction if self.twist_source == "end" else 1.0 - fraction
            )

    def wire_guides(self, guides) -> None:
        """Rail the twist guides between base and end.

        Runs on creation *and* on import, so the rig survives a ``.trg`` round
        trip -- the authored numbers persist as guide attributes and this
        rebuilds the connections over them.
        """
        end = guides.get(("end", 0))
        if end is None:
            return
        for (role, index), node in sorted(guides.items()):
            if role != "twist":
                continue
            if node["translate"].get_input() is not None:
                continue  # already railed
            mult = tm.create_node(
                "multiplyDivide", name=f"{node.name}_position_multiplyDivide"
            )
            end["translate"] >> mult["input1"]
            for channel in "XYZ":
                node[POSITION_ATTR] >> mult[f"input2{channel}"]
            mult["output"] >> node["translate"]
            for channel in tm.ALL_CHANNELS:
                plug = node[channel]
                plug.locked = True
                plug.visible = False

        base = guides.get(("base", 0))
        if base is not None:
            for channel in ("sx", "sy", "sz", "v"):
                plug = base[channel]
                plug.locked = True
                plug.visible = False
        if end["tx"].locked:
            return
        # Enforce the invariant before locking it: whatever a pose or an
        # import wrote into the off-axis channels is not part of the model.
        end.translate = (end.translate[0], 0.0, 0.0)
        end.rotate = (0.0, 0.0, 0.0)
        end.scale = (1.0, 1.0, 1.0)
        for channel in tm.ALL_CHANNELS:
            if channel in END_FREE:
                continue
            plug = end[channel]
            plug.locked = True
            plug.visible = False

    # ---------------------------------------------------------------- build
    def build(self, rig) -> None:
        """Twist extraction between the two sockets, spread over the twist joints."""
        base_guide, end_guide = rig.guides("base", "end")
        twist_guides = rig.chain("twist")

        base_socket = rig.socket("base", match=base_guide)
        end_socket = rig.socket("end", match=end_guide)

        axis = (
            self.axis
            if self.axis != "auto"
            else dominant_axis(base_guide, end_guide)[0]
        )

        if self.twist_source == "end":
            driver, reference = end_socket, base_socket
        else:
            driver = base_socket
            # Every declared input gets a socket whether or not it is wired,
            # so the instance's connections are what say if one is real.
            reference = (
                rig.socket("reference")
                if rig.instance.inputs.get("reference")
                else base_socket.parent
            )
        angle = twist_plug(
            driver, reference, name=rig.name("roll"), axis=axis, source=self.extraction
        )

        # The frame the joints ride: at the base, aimed at the end, up from
        # the base -- so it carries the base's roll and the extracted angle is
        # added on top of it.
        frame = tm.AimFrame.create(
            base_socket,
            end_socket,
            base_socket,
            aim_axis=(1.0 * rig.side_mult, 0.0, 0.0),
            twist_axis="X",
            parent=rig.groups.rig,
            name=rig.name("twistAim"),
        )
        measure = tm.Measure.create(base_socket, end_socket, name=rig.name("segment"))
        parent_joint = rig.bind_parent

        for index, guide_node in enumerate(twist_guides):
            position = guide_node[POSITION_ATTR].value
            weight = guide_node[WEIGHT_ATTR].value
            slot = tm.Transform.create(
                name=rig.name(f"twist{index}", suffix="slot"),
                parent=frame.transform.long_name,
            )
            (measure.distance * (position * rig.side_mult)) >> slot["translateX"]

            # Created without a match so joint orient stays zero and the whole
            # orientation lives in the rotate channels.
            joint = rig.bind_joint(f"twist{index}", radius=0.5)
            joint["rotateOrder"].value = 0  # xyz -- roll innermost

            local = tm.create_node(
                "multMatrix", name=rig.name(f"twist{index}", "local")
            )
            slot["worldMatrix[0]"] >> local["matrixIn[0]"]
            parent_joint["worldInverseMatrix[0]"] >> local["matrixIn[1]"]
            decompose = tm.create_node(
                "decomposeMatrix", name=rig.name(f"twist{index}", "decompose")
            )
            local["matrixSum"] >> decompose["inputMatrix"]
            decompose["outputTranslate"] >> joint["translate"]
            for channel in AXES:
                if channel == axis:
                    # Roll is added as a float after decomposition, the way
                    # Ribbon does it, so a channel-sourced twist stays
                    # unbounded past 180 degrees.
                    source = decompose[f"outputRotate{channel}"] + angle * weight
                else:
                    source = decompose[f"outputRotate{channel}"]
                source >> joint[f"rotate{channel}"]
            rig.output(f"twist{index}", joint)
