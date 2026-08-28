"""Import (or reference) a file into the scene."""

from __future__ import annotations

from pathlib import Path

from tik.trigger.core import Action, BoolField, StringField, register_action
from tik.trigger.core.exceptions import ActionExecutionError


@register_action("import_asset")
class ImportAsset(Action):
    """Bring model/asset files into the build scene."""

    label = "Import Asset"

    file_path = StringField("", label="File Path", help="Absolute path or relative to the session")
    namespace = StringField("", help="Optional namespace")
    reference = BoolField(False, help="Reference instead of import")

    def resolve_path(self, ctx) -> Path:
        path = Path(self.file_path)
        if not path.is_absolute() and ctx.paths.get("directory"):
            path = Path(ctx.paths["directory"]) / path
        return path

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
