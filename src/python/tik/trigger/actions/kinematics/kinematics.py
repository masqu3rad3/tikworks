"""Build the rig from the guides in the scene."""

from __future__ import annotations

from tik.trigger.core import (
    AFTERLIFE_MODES,
    Action,
    Builder,
    ChoiceField,
    StringField,
    register_action,
)


@register_action("kinematics")
class Kinematics(Action):
    """Run the module builder over the scene guides."""

    label = "Kinematics"

    rig_name = StringField("trigger", label="Rig Name")
    scope = ChoiceField("scene", choices=["scene", "selection"])
    afterlife = ChoiceField("delete", choices=list(AFTERLIFE_MODES), help="What happens to the guides")

    def run(self, ctx) -> None:
        report = Builder(ctx.backend, ctx.events).build(
            scope=self.scope, rig_name=self.rig_name, afterlife=self.afterlife
        )
        ctx.log(f"Kinematics built {report.count} module(s).")
