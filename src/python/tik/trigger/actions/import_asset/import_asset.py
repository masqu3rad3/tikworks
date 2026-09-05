"""Import (or reference) a file into the scene."""

from __future__ import annotations

from pathlib import Path

from tik.trigger.core import Action, BoolField, FileField, StringField, register_action
from tik.trigger.core.exceptions import ActionExecutionError


@register_action("import_asset", category="build")
class ImportAsset(Action):
    """Bring model/asset files into the build scene."""

    label = "Import Model"

    file_path = FileField(
        "", extensions=[".ma", ".mb", ".fbx", ".obj", ".abc", ".usd"], label="File"
    )
    namespace = StringField("", help="Optional namespace")
    reference = BoolField(False, help="Reference instead of import")
    parent_to_geo = BoolField(
        True,
        label="Parent to geo_grp",
        help="Move what the file brings in under the rig's geo_grp.",
    )

    def resolve_path(self, ctx) -> Path:
        """The asset path, made absolute against the session folder."""
        return ctx.resolve(self.file_path)

    def run(self, ctx) -> None:
        """Import or reference the file into the scene."""
        from maya import cmds

        path = self.resolve_path(ctx)
        if not path.exists():
            raise ActionExecutionError(f"File not found: {path}")
        kwargs = {"force": True, "returnNewNodes": True}
        if self.namespace:
            kwargs["namespace"] = self.namespace
        if self.reference:
            new_nodes = cmds.file(str(path), reference=True, **kwargs) or []
        else:
            new_nodes = cmds.file(str(path), i=True, **kwargs) or []
        if self.parent_to_geo and ctx.rig is not None:
            self._parent_top_nodes(new_nodes, ctx.rig.geo)
        ctx.log(f"Imported {path}")

    @staticmethod
    def _parent_top_nodes(new_nodes, geo) -> None:
        """Every world-level DAG node the file brought in goes under geo_grp."""
        from maya import cmds

        top = [
            node
            for node in cmds.ls(new_nodes, long=True, dag=True, type="transform")
            or []
            if node.count("|") == 1
        ]
        if top:
            cmds.parent(top, geo.long_name)
