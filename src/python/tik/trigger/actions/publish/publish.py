"""Publish the built rig: collect what the session needs, then deliver it.

``PublishAction`` is the base every publish destination subclasses. It runs
only as the tail of Build & Publish (the runner guarantees that), saves the
scene, exports the guides, builds a ``PublishSet`` and calls ``deliver``,
which is the one method a subclass writes. The generic ``publish`` action
delivers to a versioned folder with no version control system at all.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from tik.trigger.core import (
    Action,
    BoolField,
    FileField,
    register_action,
    registry,
    versioning,
)
from tik.trigger.core.action import ActionContext
from tik.trigger.core.document import BUILD
from tik.trigger.core.exceptions import ActionExecutionError
from tik.trigger.core.publish_set import STORE_DIR, PublishSet, write_bundle

TEMP_DIR = "_publish_tmp"


class PublishAction(Action):
    """Base class for publish destinations. Subclasses implement ``deliver``."""

    include_guides = BoolField(
        True, label="Include guides", help="Export the guides as a .trg element."
    )
    include_products = BoolField(
        True,
        label="Include products",
        help="Ask every build action for the files it wrote and publish them too.",
    )

    # --------------------------------------------------------- contract
    def deliver(self, publish_set: PublishSet, ctx: ActionContext) -> None:
        """Send ``publish_set`` where this action publishes. Paths only."""
        raise NotImplementedError

    # ----------------------------------------------------------- steps
    def validate(self, ctx: ActionContext) -> list[str]:
        problems = super().validate(ctx)
        session = ctx.session
        if session is None or session.file_path is None:
            problems.append(f"{self.action_type or 'publish'}: save the session first")
        return problems

    def run(self, ctx: ActionContext) -> None:
        session = ctx.session
        if session is None or session.file_path is None:
            raise ActionExecutionError("save the session first")
        name = Path(session.file_path).stem
        temp = Path(ctx.base_dir) / TEMP_DIR
        temp.mkdir(parents=True, exist_ok=True)
        rig = temp / f"{name}_rig.mb"
        _save_scene(rig)
        guides: Optional[Path] = None
        if self.include_guides:
            guides = temp / f"{name}.trg"
            _export_guides(session, guides)
        publish_set = self.collect(ctx, rig=rig, guides=guides)
        try:
            self.deliver(publish_set, ctx)
        except ActionExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - wrap with the action's name
            raise ActionExecutionError(f"{self.display_label()}: {error}") from error
        shutil.rmtree(temp, ignore_errors=True)
        ctx.log(f"Published {name}")

    def collect(
        self,
        ctx: ActionContext,
        rig: Optional[Path] = None,
        guides: Optional[Path] = None,
    ) -> PublishSet:
        """The publish set for the session, products included when asked."""
        session = ctx.session
        products = []
        if self.include_products:
            for path, node, _parent in session.document.walk(BUILD):
                if not node.enabled or not registry.is_action_registered(node.type):
                    continue
                action_cls = registry.get_action(node.type)
                if not action_cls.has_products():
                    continue
                node_ctx = ActionContext(
                    session=session,
                    events=ctx.events,
                    base_dir=ctx.base_dir,
                    path=path,
                    rig=ctx.rig,
                    scripts=ctx.scripts,
                )
                products.extend(action_cls(settings=node.settings).products(node_ctx))
        return PublishSet.collect(
            session.file_path,
            session.document,
            rig=rig,
            guides=guides,
            products=products,
        )


def _export_guides(session, target: Path) -> None:
    """Write the session's guides to ``target``, from the document.

    By the time a publish runs the build has usually deleted the guide joints
    -- ``kinematics.after_build`` defaults to ``delete`` -- so the scene has
    nothing left to serialise and the ``.trg`` would come out empty. The
    document still holds every pose, so draw it back and export that. When the
    build left no guides behind, the rendering goes away again afterwards:
    publishing must not change what the rigger is looking at.
    """
    from tik.trigger.guides.snapshot import snapshot

    was_drawn = bool(snapshot())
    session.guides.draw(poses="discard")
    session.guides.export(target)
    if not was_drawn:
        session.guides.clear_rendering()


def _save_scene(target: Path) -> None:
    """Save the current scene as ``target`` (binary) and restore its name."""
    from maya import cmds

    original = cmds.file(query=True, sceneName=True) or ""
    cmds.file(rename=str(target))
    try:
        cmds.file(save=True, type="mayaBinary", force=True)
    finally:
        cmds.file(rename=original)


@register_action("publish", category="finish", icon="publish", scope="publish")
class Publish(PublishAction):
    """Publish into a versioned folder. No version control system needed.

    Writes ``<folder>/<session>_v###/`` holding the session with its paths
    rewritten, the guides, the rig scene and a manifest; unchanged files are
    shared through ``<folder>/_store``.
    """

    label = "Publish"

    folder = FileField(
        "publish",
        mode="dir",
        label="Publish folder",
        help="Where versions go, relative to the session folder when not absolute.",
    )

    def summary(self) -> str:
        return self.folder

    def deliver(self, publish_set: PublishSet, ctx: ActionContext) -> None:
        folder = ctx.resolve(self.folder)
        store_root = folder / STORE_DIR
        # The store is part of the publish folder's shape, not a side effect of
        # having had a dependency to store: a version with none still publishes
        # into a folder that looks like every other one.
        store_root.mkdir(parents=True, exist_ok=True)
        target = versioning.next_version(folder / publish_set.name)
        write_bundle(publish_set, target, store_root=store_root)
        ctx.log(f"Bundle written: {target}")
