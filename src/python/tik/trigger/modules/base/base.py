"""Base module: a single root controller + joint every rig starts from."""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import FloatField, GuideLayout, Module, register_module


@register_module("base")
class Base(Module):
    """Root of a rig. Everything else attaches to its ``root`` plug."""

    label = "Base"
    sided = False
    guides = GuideLayout("root")
    inputs = ()
    outputs = ("root",)

    controller_size = FloatField(10.0, min=0.01, label="Controller Size")

    def draw_guides(self, ctx) -> None:
        ctx.joint("root", (0, 0, 0), radius=2.0)

    def build(self, ctx) -> None:
        root_guide = ctx.guide("root")
        controller = ctx.controller(
            "root",
            shape="Circle",
            size=self.controller_size,
            match=root_guide,
            mirror="world",
        )
        joint = ctx.bind_joint("root", match=root_guide)
        tm.MatrixConstraint.create(controller.transform, joint, maintain_offset=True)
        ctx.output("root", joint)
