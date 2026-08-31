"""Twist module: N joints rolling about one axis, driven by a segment's ends.

Generic, not a limb accessory. ``twist_source`` says *which end drives* the
roll; ``extraction`` says *how the angle is read*. Position and weight are
fully independent: position comes from where the guide sits along the
segment, weight from an unclamped attribute on that guide, so a joint at 0.95
may carry a weight of 0.2, or a negative weight to reverse the twist.
"""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import (
    BoolField,
    ChoiceField,
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


def projected_position(start, end, probe) -> float:
    """Where ``probe`` falls along ``start`` -> ``end``, as a 0-1 fraction.

    Only the component along the axis counts, so a guide dragged sideways for
    visibility still reads correctly.
    """
    axis = end.world_position - start.world_position
    length_squared = axis * axis
    if length_squared < 1e-12:
        return 0.0
    fraction = ((probe.world_position - start.world_position) * axis) / length_squared
    return max(0.0, min(1.0, fraction))


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
                WEIGHT_ATTR,
                help="How much of the extracted twist this joint takes. "
                     "Unclamped; negative reverses it.",
            ),
        )
    }

    count = IntField(3, min=1, max=20, help="Number of twist joints")
    twist_source = ChoiceField(
        "end", choices=("start", "end"), label="Twist Source",
        help="'end' follows the child (forearm); 'start' counters the "
             "segment's own roll (upper arm)",
    )
    axis = ChoiceField("auto", choices=("auto", *AXES))
    extraction = ChoiceField(
        "auto", choices=SOURCES,
        help="'channel' is unbounded but needs an FK-style driver; "
             "'matrix' works anywhere and wraps past 180 degrees",
    )
    distribute_translation = BoolField(
        True, help="Slide the joints along when the segment stretches"
    )
    spacing = FloatField(10.0, min=0.01, help="Default guide distance, base to end")

    @classmethod
    def output_names(cls, settings=None):
        count = int((settings or {}).get("count", cls.count.default))
        return tuple(f"twist{index}" for index in range(count))

    def guide_count(self) -> int:
        return self.count

    # --------------------------------------------------------------- guides
    def draw_guides(self, guides) -> None:
        span = self.spacing * guides.side_mult
        base = guides.joint("base", (0, 0, 0))
        guides.joint("end", (span, 0, 0), parent=base)
        for index in range(self.count):
            fraction = (index + 1) / (self.count + 1)
            joint = guides.joint(
                "twist", (span * fraction, 0, 0), index=index, parent=base, radius=0.5
            )
            # The sensible default, freely overridable afterwards.
            joint[WEIGHT_ATTR].value = (
                fraction if self.twist_source == "end" else 1.0 - fraction
            )

    # ---------------------------------------------------------------- build
    def build(self, rig) -> None:
        base_guide, end_guide = rig.guides("base", "end")
        twist_guides = rig.chain("twist")

        base_socket = rig.socket("base", match=base_guide)
        end_socket = rig.socket("end", match=end_guide)

        axis = self.axis if self.axis != "auto" else dominant_axis(base_guide, end_guide)[0]

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

        measure = None
        if self.distribute_translation:
            # The sockets track the real segment ends, so their distance is
            # the live segment length and the joints redistribute on stretch.
            measure = tm.Measure.create(
                base_socket, end_socket, name=rig.name("segment")
            )

        for index, guide_node in enumerate(twist_guides):
            position = projected_position(base_guide, end_guide, guide_node)
            weight = guide_node[WEIGHT_ATTR].value
            joint = rig.bind_joint(f"twist{index}", match=guide_node, radius=0.5)
            joint["rotateOrder"].value = 0  # xyz -- roll innermost
            (angle * weight) >> joint[f"rotate{axis}"]
            if measure is not None:
                # Bind joints are oriented X down the chain; a mirrored side
                # aims back up it, so the sign comes from the module's side.
                (measure.distance * (position * rig.side_mult)) >> joint["translateX"]
            rig.output(f"twist{index}", joint)
