"""Guide authoring preferences.

These change what you write into the session document, never what a build
makes from an already-saved one, so they stay inside the guarantee.
"""

from __future__ import annotations

from tik.core.fields import BoolField, FieldGroup
from tik.shared.prefs import PrefPage, register_page


@register_page
class GuidesPrefs(PrefPage):
    """Defaults for the Guide Designer's authoring toggles."""

    name, label, order = "guides", "Guides", 20

    AUTHORING = FieldGroup("Authoring")
    CONFIRMATIONS = FieldGroup("Confirmations")

    auto_sync = BoolField(
        True,
        group=AUTHORING,
        label="Auto Sync by default",
        help=(
            "Start new Guide Designers with Auto Sync on, capturing guide poses "
            "from the scene as you move them."
        ),
    )
    draw_on_create = BoolField(
        True,
        group=AUTHORING,
        label="Draw new modules",
        help="Draw a module's guides into the scene as soon as you create it.",
    )
    confirm_delete_all = BoolField(
        True,
        group=CONFIRMATIONS,
        label="Confirm Delete All Modules",
        help="Ask before deleting every module from the session document.",
    )
    confirm_reset_scene = BoolField(
        True,
        group=CONFIRMATIONS,
        label="Confirm Reset Scene",
        help="Ask before throwing the Maya scene away.",
    )
    migrated_from_qsettings = BoolField(
        False,
        hidden=True,
        label="Migrated",
        help="Set once the old QSettings designer toggles have been imported.",
    )
