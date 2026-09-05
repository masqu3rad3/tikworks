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
    controls = ("root",)

    def draw_guides(self, guides):
        guides.joint("root", (0, 0, 0))

    def build(self, rig):
        rig.controller("root")
        rig.output("root", rig.name("root", suffix="jnt"))


class ToyChain(Module):
    label = "Toy Chain"
    guides = GuideLayout("root", multi="segment", min=1)
    inputs = (Input("root", primary=True), Input("space", optional=True))
    outputs = ("root", "end")
    segments = IntField(2, min=1)

    def guide_count(self):
        return self.segments

    def draw_guides(self, guides):
        guides.joint("root", (0, 0, 0))
        for index in range(self.segments):
            guides.joint("segment", (index + 1, 0, 0), index=index)

    def build(self, rig):
        rig.attach("root", rig.name("root", suffix="grp"))
        rig.attach("space", rig.name("space", suffix="grp"))
        rig.output("root", rig.guide("root"))
        rig.output("end", rig.chain("segment")[-1])
        for joint in rig.chain("segment"):
            rig.deform_joint(joint)
