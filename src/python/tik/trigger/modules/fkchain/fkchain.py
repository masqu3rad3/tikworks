"""FK chain module: N joints driven by nested FK controllers."""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import FloatField, Guides, Input, IntField, Module, register_module


@register_module("fkchain")
class FkChain(Module):
    """A simple FK chain (tails, fingers, antennas...)."""

    label = "FK Chain"
    guides = Guides("root", multi="segment", min=1, max=50)
    inputs = (Input("root", primary=True, help="Where the chain hangs"),)
    outputs = ("root", "end")  # plus one "segment<N>" output per joint after the root

    @classmethod
    def output_names(cls, settings=None):
        count = int((settings or {}).get("segments", cls.segments.default))
        return ("root", *(f"segment{index + 1}" for index in range(count)), "end")

    segments = IntField(3, min=1, max=50, help="Number of joints after the root")
    spacing = FloatField(5.0, min=0.01, help="Default distance between guides")
    controller_size = FloatField(2.0, min=0.01, label="Controller Size")

    def guide_count(self) -> int:
        return self.segments

    def draw_guides(self, ctx) -> None:
        previous = ctx.joint("root", (0, 0, 0))
        for index in range(self.segments):
            offset = self.spacing * (index + 1) * ctx.side_mult
            previous = ctx.joint("segment", (offset, 0, 0), index=index, parent=previous)

    def build(self, ctx) -> None:
        guide_nodes = [ctx.guide("root"), *ctx.guides("segment")]

        socket = tm.Transform.create(
            name=ctx.name("root", suffix="socket"), parent=ctx.groups.socket.long_name
        )
        socket.align_to(guide_nodes[0])
        ctx.attach("root", socket)

        # Bind joints are created in their final hierarchy position: the root
        # falls back to ctx.bind_parent, which is the connected producer's bind
        # joint when this chain is attached to another module.
        joints = []
        parent_joint = None
        for index, guide_node in enumerate(guide_nodes):
            joint = ctx.bind_joint(str(index), parent=parent_joint, match=guide_node)
            joints.append(joint)
            parent_joint = joint

        # Controllers live in control_grp and are *driven* by the socket, never
        # parented under it: control_grp holds nothing but controllers and their
        # offset groups.
        parent = None
        for index, joint in enumerate(joints[:-1]):
            controller = ctx.controller(
                f"fk{index}",
                size=self.controller_size,
                parent=parent if parent is not None else ctx.groups.control,
                match=joint,
                mirror="behaviour",
            )
            offset = controller.transform.create_offset_group(
                name=ctx.name(f"fk{index}", suffix="offset")
            )
            if parent is None:
                tm.MatrixConstraint.create(socket, offset, maintain_offset=True)
            tm.MatrixConstraint.create(controller.transform, joint, maintain_offset=True)
            parent = controller.transform

        ctx.output("root", joints[0])
        for index, joint in enumerate(joints[1:]):
            ctx.output(f"segment{index + 1}", joint)
        ctx.output("end", joints[-1])
