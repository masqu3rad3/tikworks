"""Toy modules for tests that need a registered module but not a real rig.

They build through whatever object the caller hands them, so they work with
the real builder in Maya and with the Qt stub scene alike.
"""

from __future__ import annotations

from tik.trigger.core import GuideLayout, Input, IntField, Module

class ToyRoot(Module):
    label = "Toy Root"
    sided = False
    guides = GuideLayout("root")
    inputs = ()
    outputs = ("root",)
    space_controls = ("root",)

    def draw_guides(self, ctx):
        ctx.joint("root", (0, 0, 0))

    def build(self, ctx):
        ctx.controller("root")
        ctx.output("root", ctx.name("root", suffix="jnt"))


class ToyChain(Module):
    label = "Toy Chain"
    guides = GuideLayout("root", multi="segment", min=1)
    inputs = (Input("root", primary=True), Input("space", optional=True))
    outputs = ("root", "end")
    segments = IntField(2, min=1)

    def guide_count(self):
        return self.segments

    def draw_guides(self, ctx):
        ctx.joint("root", (0, 0, 0))
        for index in range(self.segments):
            ctx.joint("segment", (index + 1, 0, 0), index=index)

    def build(self, ctx):
        ctx.attach("root", ctx.name("root", suffix="grp"))
        ctx.attach("space", ctx.name("space", suffix="grp"))
        ctx.output("root", ctx.guide("root"))
        ctx.output("end", ctx.guides("segment")[-1])
        for joint in ctx.guides("segment"):
            ctx.deform_joint(joint)
