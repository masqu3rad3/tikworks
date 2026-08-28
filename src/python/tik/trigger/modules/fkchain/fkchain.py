"""FK chain module: N joints driven by nested FK controllers."""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import FloatField, Guides, IntField, Module, register_module


@register_module("fkchain")
class FkChain(Module):
    """A simple FK chain (tails, fingers, antennas...)."""

    label = "FK Chain"
    guides = Guides("root", multi="segment", min=1, max=50)
    plugs = ("root", "end")
    sockets = ("root",)
    legacy_types = {"root": "FkikRoot", "segment": "Fkik"}

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
        positions = [tuple(node.world_position) for node in guide_nodes]
        joints = tm.Joint.chain(
            positions, name_pattern=ctx.name("{index}", suffix="jnt"), parent=ctx.groups.joints
        )

        socket = tm.Transform.create(
            name=ctx.name("root", suffix="socket"), parent=ctx.groups.controllers.long_name
        )
        socket.align_to(joints[0])
        ctx.socket("root", socket)

        parent = socket
        for index, joint in enumerate(joints[:-1]):
            controller = ctx.controller(
                f"fk{index}", size=self.controller_size, parent=parent, match=joint
            )
            controller.transform.create_offset_group(name=ctx.name(f"fk{index}", suffix="offset"))
            tm.MatrixConstraint.create(controller.transform, joint, maintain_offset=True)
            parent = controller.transform

        for joint in joints:
            ctx.deform_joint(joint)
        ctx.plug("root", joints[0])
        ctx.plug("end", joints[-1])
