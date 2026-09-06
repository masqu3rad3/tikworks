"""External tool preferences."""

from __future__ import annotations

from tik.core.fields import FieldGroup, StringField
from tik.shared.prefs import PrefPage, register_page


@register_page
class ToolsPrefs(PrefPage):
    """Programs Trigger hands files to."""

    name, label, order = "tools", "External Tools", 40

    EDITOR = FieldGroup("Editor")

    external_editor = StringField(
        "",
        group=EDITOR,
        label="External editor command",
        help=(
            "Command that opens a script file. Use {path} where the file goes, "
            "for example: code -g {path}. Empty uses your system's default."
        ),
    )
