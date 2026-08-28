"""Run arbitrary Python: inline code and/or a file."""

from __future__ import annotations

from pathlib import Path

from tik.trigger.core import Action, StringField, register_action
from tik.trigger.core.exceptions import ActionExecutionError


@register_action("script")
class Script(Action):
    """Execute Python with ``ctx`` available as a global."""

    label = "Script"

    file_path = StringField("", label="Script File")
    code = StringField("", help="Inline code run after the file")

    def run(self, ctx) -> None:
        namespace = {"ctx": ctx, "__name__": "__trigger_script__"}
        if self.file_path:
            path = Path(self.file_path)
            if not path.is_absolute() and ctx.paths.get("directory"):
                path = Path(ctx.paths["directory"]) / path
            if not path.exists():
                raise ActionExecutionError(f"Script not found: {path}")
            exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
        if self.code:
            exec(compile(self.code, "<trigger script>", "exec"), namespace)
