"""Build the rig from a guides file (``.trg``)."""

from __future__ import annotations

from tik.trigger.core import (
    AFTERLIFE_MODES,
    Action,
    BoolField,
    Builder,
    ChoiceField,
    FileField,
    ListField,
    StringField,
    register_action,
)
from tik.trigger.core.exceptions import ActionExecutionError


@register_action("kinematics", category="build", icon="kinematics")
class Kinematics(Action):
    """Import a guides file and build every module in it (or only the given roots)."""

    label = "Kinematics"

    guides_file = FileField("", extensions=[".trg"], label="Guides file")
    guide_roots = ListField(item_type=str, help="Root guide names to build; empty = all")
    rig_name = StringField("trigger", label="Rig name")
    after_build = ChoiceField("delete", choices=list(AFTERLIFE_MODES), label="Guides after build")
    auto_switchers = BoolField(True, help="Create automatic space switchers")

    def run(self, ctx) -> None:
        from tik.trigger.guides import Guides

        if not self.guides_file:
            raise ActionExecutionError("kinematics: no guides file set.")
        guides = Guides(ctx.backend, ctx.events)
        handles = guides.import_(ctx.resolve(self.guides_file))
        if self.guide_roots:
            wanted = set(self.guide_roots)
            roots = [handle for handle in handles if handle.name in wanted or handle.root.name in wanted]
            if not roots:
                raise ActionExecutionError(
                    f"kinematics: none of the roots {self.guide_roots} found in the guides file."
                )
            scope = _descendants(guides, roots)
        else:
            scope = [handle.instance_id for handle in handles]
        report = Builder(ctx.backend, ctx.events).build(
            scope=scope, rig_name=self.rig_name, afterlife=self.after_build
        )
        ctx.log(f"Kinematics built {report.count} module(s) from {self.guides_file}.")


def _descendants(guides, roots) -> list[str]:
    """Instance ids of ``roots`` and everything parented under them."""
    all_instances = {handle.instance_id: handle.instance for handle in guides.instances()}
    wanted = {handle.instance_id for handle in roots}
    changed = True
    while changed:
        changed = False
        for instance_id, instance in all_instances.items():
            if instance_id not in wanted and instance.parent and instance.parent.instance_id in wanted:
                wanted.add(instance_id)
                changed = True
    return list(wanted)
