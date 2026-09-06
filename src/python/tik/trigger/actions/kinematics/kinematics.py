"""Build the modules this action names. Nothing implicit, nothing else."""

from __future__ import annotations

from tik.trigger.core import (
    AFTERLIFE_MODES,
    Action,
    ChoiceField,
    FieldGroup,
    ListField,
    register_action,
)
from tik.trigger.core.exceptions import ActionExecutionError

BUILD_OPTIONS = FieldGroup("Build Options", collapsed=True)


@register_action("kinematics", category="build", icon="kinematics")
class Kinematics(Action):
    """Build the listed modules into the scene's one rig.

    The list is the whole scope: it does not matter whether a module is local
    to this session, referenced from another, or was imported from a guide
    library. If it is named here it builds, and if it is not, this action does
    not touch it -- not its guides, and not its afterlife.
    """

    label = "Kinematics"

    modules = ListField(
        item_type=str,
        label="Modules",
        help="Instance ids of the modules to build. Never empty.",
    )
    after_build = ChoiceField(
        "delete",
        choices=list(AFTERLIFE_MODES),
        label="GuideLayout after build",
        group=BUILD_OPTIONS,
    )

    def validate(self, ctx) -> list:
        """Report an empty scope, and any id this session does not hold."""
        if not self.modules:
            return ["kinematics names no modules; nothing would build."]
        document = self._document(ctx)
        if document is None:
            return []
        known = {entry.instance_id for entry in document.modules}
        return [
            f"kinematics names a module that is not in this session: '{item}'."
            for item in self.modules
            if item not in known
        ]

    def run(self, ctx) -> None:
        """Draw this action's modules, build them, then apply the afterlife."""
        from tik.trigger.guides import GuideScene
        from tik.trigger.maya.build import Builder

        if not self.modules:
            raise ActionExecutionError("kinematics names no modules; nothing to build.")
        document = self._document(ctx)
        if document is None:
            raise ActionExecutionError("kinematics has no session to build from.")
        scope = list(self.modules)
        known = {entry.instance_id for entry in document.modules}
        missing = [item for item in scope if item not in known]
        if missing:
            raise ActionExecutionError(
                f"kinematics names module(s) not in this session: {missing}."
            )
        guides = GuideScene(ctx.events, session=ctx.session)
        # Scoped, and only scoped. An earlier pass's guides are none of our
        # business whatever its afterlife was, so nothing here clears the scene.
        guides.draw(scope=scope)
        report = Builder(ctx.events).build(
            scope=scope, document=document, afterlife=self.after_build
        )
        ctx.log(f"Kinematics built {report.count} module(s).")

    @staticmethod
    def _document(ctx):
        """The guide document of the session being built, or None."""
        session = getattr(ctx, "session", None)
        document = getattr(session, "document", None)
        return getattr(document, "guides", None)

    def summary(self) -> str:
        """How many modules this action builds, for the pipeline list."""
        count = len(self.modules)
        return f"{count} module{'' if count == 1 else 's'}"
