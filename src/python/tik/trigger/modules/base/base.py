"""Base module: a single root controller + joint every rig starts from."""

from __future__ import annotations

import tik.maya as tm
from tik.trigger.core import FloatField, GuideLayout, Module, register_module


@register_module("base", category="body")
class Base(Module):
    """Root of a rig. Everything else attaches to its ``root`` plug."""

    label = "Base"
    sided = False
    guides = GuideLayout("root")
    inputs = ()
    outputs = ("root",)
    controls = ("root",)

    controller_size = FloatField(10.0, min=0.01, label="Controller Size")

    def draw_guides(self, guides) -> None:
        """A single root joint."""
        guides.joint("root", (0, 0, 0), radius=2.0)

    def build(self, rig) -> None:
        """One root controller with a bind joint under it."""
        root_guide = rig.guide("root")
        controller = rig.controller(
            "root",
            shape="Circle",
            size=self.controller_size,
            match=root_guide,
            mirror="world",
        )
        joint = rig.bind_joint("root", match=root_guide)
        tm.MatrixConstraint.create(controller, joint, maintain_offset=True)
        rig.output("root", joint)
