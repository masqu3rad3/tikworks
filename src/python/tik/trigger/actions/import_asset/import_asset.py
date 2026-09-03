"""Import (or reference) a file into the scene."""

from __future__ import annotations

from pathlib import Path

from tik.trigger.core import Action, BoolField, FileField, StringField, register_action
from tik.trigger.core.exceptions import ActionExecutionError


@register_action("import_asset", category="build", icon="import_model")
class ImportAsset(Action):
    """Bring model/asset files into the build scene."""

    label = "Import Model"

    file_path = FileField(
        "", extensions=[".ma", ".mb", ".fbx", ".obj", ".abc", ".usd"], label="File"
    )
    namespace = StringField("", help="Optional namespace")
    reference = BoolField(False, help="Reference instead of import")

    def resolve_path(self, ctx) -> Path:
        return ctx.resolve(self.file_path)

    def run(self, ctx) -> None:
        from maya import cmds

        path = self.resolve_path(ctx)
        if not path.exists():
            raise ActionExecutionError(f"File not found: {path}")
        kwargs = {"force": True}
        if self.namespace:
            kwargs["namespace"] = self.namespace
        if self.reference:
            cmds.file(str(path), reference=True, **kwargs)
        else:
            cmds.file(str(path), i=True, **kwargs)
        ctx.log(f"Imported {path}")
