"""Build the rig from a guides file (``.trg``)."""

from __future__ import annotations

from tik.trigger.core import (
    AFTERLIFE_MODES,
    Action,
    ChoiceField,
    FieldGroup,
    FileField,
    ListField,
    register_action,
)
from tik.trigger.core.exceptions import ActionExecutionError

BUILD_OPTIONS = FieldGroup("Build Options", collapsed=True)


@register_action("kinematics", category="build", icon="kinematics")
class Kinematics(Action):
    """Import a guides file and build every module in it (or only the given roots)."""

    label = "Kinematics"

    guides_file = FileField(
        "",
        extensions=[".trg"],
        label="GuideLayout file",
        help="Leave empty to build this session's own guides; set a path to "
        "build a shared guide library instead.",
    )
    guide_roots = ListField(
        item_type=str,
        help="Root guide names to build; empty = all",
        group=BUILD_OPTIONS,
    )
    after_build = ChoiceField(
        "delete",
        choices=list(AFTERLIFE_MODES),
        label="GuideLayout after build",
        group=BUILD_OPTIONS,
    )

    def run(self, ctx) -> None:
        """Build the rig from the guides file, or from the session's own guides."""
        from tik.trigger.guides import GuideScene
        from tik.trigger.maya.build import Builder

        guides = GuideScene(ctx.events)
        if self.guides_file:
            handles = guides.import_(ctx.resolve(self.guides_file))
            document = guides.document
        else:
            handles = self._checkout_session_guides(guides, ctx)
            document = ctx.session.document.guides
        if self.guide_roots:
            wanted = set(self.guide_roots)
            roots = [
                handle
                for handle in handles
                if handle.name in wanted or handle.root.name in wanted
            ]
            if not roots:
                raise ActionExecutionError(
                    f"kinematics: none of the roots {self.guide_roots} "
                    "found in the guides."
                )
            scope = _descendants(guides, roots)
        else:
            scope = [handle.instance_id for handle in handles]
        report = Builder(ctx.events).build(
            scope=scope,
            document=document,
            afterlife=self.after_build,
        )
        source = self.guides_file or "this session"
        ctx.log(f"Kinematics built {report.count} module(s) from {source}.")

    @staticmethod
    def _checkout_session_guides(guides, ctx):
        """Render the guides stored in this session, with no file involved.

        The session is a self-contained rig description, so there is no version
        skew between it and a separate guides file to get wrong.
        """
        from tik.trigger.guides import regenerate

        document = getattr(ctx.session, "document", None)
        stored = getattr(document, "guides", None)
        if stored is None or not stored.modules:
            raise ActionExecutionError(
                "kinematics: no guides in this session and no guides file set."
            )
        session_guides = ctx.session.guides
        session_guides.clear_rendering()
        regenerate.regenerate_all(stored)
        return session_guides.instances()


def _descendants(guides, roots) -> list[str]:
    """Instance ids of ``roots`` and everything parented under them."""
    all_instances = {
        handle.instance_id: handle.instance for handle in guides.instances()
    }
    wanted = {handle.instance_id for handle in roots}
    changed = True
    while changed:
        changed = False
        for instance_id, instance in all_instances.items():
            if (
                instance_id not in wanted
                and instance.parent
                and instance.parent.instance_id in wanted
            ):
                wanted.add(instance_id)
                changed = True
    return list(wanted)
